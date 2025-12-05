import contextlib
import json
from typing import AsyncIterator, Literal, Optional
from mcp.server.fastmcp import FastMCP
from dishka import make_async_container
from pydantic import BaseModel, Field
from src.ioc import RepositoryProvider, GeneralProvider, AppProvider
from src.services.world_query_service import WorldQueryService
from src.services.template_editor import TemplateEditorService

import logging
from mcp.server.streamable_http import EventCallback, EventMessage, EventStore
from mcp.types import JSONRPCMessage


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 1. Event Store (for stability of SSE) ---
StreamId = str
EventId = str

class InMemoryEventStore(EventStore):
    """Store events in the memory for reconnection ability."""
    def __init__(self) -> None:
        self._events: list[tuple[StreamId, EventId, JSONRPCMessage | None]] = []
        self._event_id_counter = 0

    async def store_event(self, stream_id: StreamId, message: JSONRPCMessage | None) -> EventId:
        self._event_id_counter += 1
        event_id = str(self._event_id_counter)
        self._events.append((stream_id, event_id, message))
        return event_id

    async def replay_events_after(self, last_event_id: EventId, send_callback: EventCallback) -> StreamId | None:
        target_stream_id = None
        for stream_id, event_id, _ in self._events:
            if event_id == last_event_id:
                target_stream_id = stream_id
                break
        if target_stream_id is None:
            return None
        last_event_id_int = int(last_event_id)
        for stream_id, event_id, message in self._events:
            if stream_id == target_stream_id and int(event_id) > last_event_id_int:
                if message is not None:
                    await send_callback(EventMessage(message, event_id))
        return target_stream_id

# TODO CHANGE!
class WorldGenPlan(BaseModel):
    existing_biomes_to_use: list[str] = Field(description="List of EXISTING biomes that are suitable")
    new_biomes_to_create: list[str] = Field(description="List of names for NEW biomes that are missing (for example 'Hill', 'Coast')")
    width: int = Field(default=3, description="Map width (usually 2-3)")
    height: int = Field(default=3, description="The height of the map (usually 2-3)")
    reasoning: str = Field(description="A brief explanation of the choice of biomes")


# --- 2. Lifespan ---
@contextlib.asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[None]:
    from src.template_loader import load_all_templates
    global container
    logger.info("Initializing DI Container...")
    
    logger.info("Loading templates and naming data...")
    load_all_templates()

    try:
        container = make_async_container(
            RepositoryProvider(), 
            GeneralProvider(), 
            AppProvider()
        )
        yield
    finally:
        logger.info("Closing DI Container...")
        if container:
            await container.close()

# --- 3. Server init ---
event_store = InMemoryEventStore()

mcp = FastMCP(
    "WorldBuilder Engine",
    lifespan=server_lifespan,
    event_store=event_store,
    retry_interval=1000 # 1 second
)

# --- 4. Tools ---

# TODO переделать!
@mcp.tool()
async def generate_new_world(description: str) -> str:
    """
    Creates a world based on the description. AUTOMATICALLY creates the missing biomes.
    Example: "A post-apocalyptic wasteland with radiation oases."
    This operation overwrites the current world!
    """
    from src.models.registries import (BIOME_REGISTRY, FACTION_REGISTRY)
    from src.models.templates_schema import BiomeTemplate
    from src.services.llm_service import LLMService
    from src.services.template_editor import TemplateEditorService
    from src.word_generator import WorldGenerator
    from src.models.generation import World
    from src.utils import save_world_to_json
    from config import fallback_template_path

    if not container:
        return "Error: Container not initialized"

    log_output = []

    async with container() as request_container:
        llm = await request_container.get(LLMService)
        generator = await request_container.get(WorldGenerator)
        editor = await request_container.get(TemplateEditorService) # Для сохранения новых шаблонов
        current_world = await request_container.get(World)

        # 1. Анализ существующих ресурсов
        # Мы больше не хардкодим, а берем реальные ключи из реестра
        available_ids = list(BIOME_REGISTRY.keys())
        avaibable_fraction_ids = list(FACTION_REGISTRY.keys())
        
        log_output.append(f"🔍 Analyzing request against {len(available_ids)} existing biomes...")

        # 2. Планирование (LLM решает, что взять, а что создать)
        try:
            prompt = (
                f"User wants: '{description}'.\n"
                f"Available Biome IDs: {', '.join(available_ids)}\n"
                f"Available Faction IDs: {', '.join(avaibable_fraction_ids)}\n"
                "Decide which existing biomes to use and which NEW ones to create to match the description."
            )
            plan: WorldGenPlan = await llm.generate_structure(prompt, WorldGenPlan)
        except Exception as e:
            return f"Planning Error: {e}"

        final_biome_ids = list(plan.existing_biomes_to_use)

        # 3. Цикл создания недостающих биомов (Chain of Thought в коде)
        if plan.new_biomes_to_create:
            log_output.append(f"🔨 Needs to create {len(plan.new_biomes_to_create)} new biomes: {plan.new_biomes_to_create}")
            
            for new_biome_name in plan.new_biomes_to_create:
                # Генерируем ID
                import uuid
                # Делаем читаемый ID (latin letters only ideally, but simple replace works for now)
                slug = new_biome_name.lower().replace(" ", "_")[:15]
                new_id = f"biome_{slug}_{str(uuid.uuid4())[:4]}"
                
                try:
                    template_data = await llm.generate_template(
                        f"Create a game design template for a biome named '{new_biome_name}'. "
                        f"Context: {description}. ID should be '{new_id}'.",
                        BiomeTemplate
                    )
                    
                    # Принудительно ставим ID (на случай если LLM ошиблась)
                    template_data['id'] = new_id
                    
                    # Сохраняем на диск через EditorService
                    # config_type='biomes' соответствует ключу в entity_templates.yaml или отдельному файлу
                    # В вашей архитектуре EditorService.append_template умеет писать в YAML
                    editor.append_template(
                        config_file="data/templates/biomes.yaml", # Путь к файлу биомов
                        config_type="templates", 
                        new_item=template_data
                    )
                    
                    # ВАЖНО: Регистрируем в реестре памяти немедленно!
                    # EditorService сохраняет файл, но нам нужно обновить Runtime Registry
                    # Pydantic модель валидирует данные
                    new_tmpl_obj = BiomeTemplate(**template_data)
                    BIOME_REGISTRY.register(new_id, new_tmpl_obj)
                    
                    final_biome_ids.append(new_id)
                    log_output.append(f"  ✅ Created and registered: {new_biome_name} ({new_id})")
                    
                except Exception as e:
                    log_output.append(f"  ❌ Failed to create {new_biome_name}: {e}")

        # 4. Финальная проверка перед генерацией
        if not final_biome_ids:
            # Fallback
            final_biome_ids = available_ids[:3]
            log_output.append("⚠️ No valid biomes found/created. Using defaults.")

        # 5. Генерация мира
        try:
            log_output.append(f"🌍 Generating world {plan.width}x{plan.height} with: {final_biome_ids}...")
            new_world_obj = generator.generate(
                biome_ids=final_biome_ids,
                world_width=plan.width,
                world_height=plan.height,
                num_biomes=plan.width * plan.height
            )
            
            # Hot Swap
            current_world.graph = new_world_obj.graph
            save_world_to_json(current_world, fallback_template_path)
            
        except Exception as e:
            return "\n".join(log_output) + f"\n💥 Critical Generation Error: {e}"

        return "\n".join(log_output) + "\n✨ World Generation Complete!"

@mcp.tool()
async def get_world_metadata() -> str:
    """Available Tags, EntityTypes, and RelationTypes."""
    if not container:
        return "Error: Server not initialized (Container missing)"
        
    async with container() as request_container:
        service = await request_container.get(WorldQueryService)
        meta = service.get_world_metadata()
        return json.dumps(meta, indent=2, ensure_ascii=False)

@mcp.tool()
async def query_entities(
    type_filter: Optional[str] = None,
    include_tags: list[str] = [],
    exclude_tags: list[str] = ["dead", "inactive", "absorbed"],
    limit: int = 50
) -> str:
    """Find entities in the graph."""
    async with container() as request_container:
        service = await request_container.get(WorldQueryService)
        return service.query_entities(include_tags, exclude_tags, type_filter, limit)

@mcp.tool()
async def define_new_archetype(config_type: Literal['templates'], config_file: str, template_json: str) -> str:
    """Add a NEW template to the database."""
    async with container() as request_container:
        service = await request_container.get(TemplateEditorService)
        try:
            data = json.loads(template_json)
            new_id = service.append_template(config_file=config_file, config_type=config_type, new_item=data)
            return f"Success: Template '{new_id}' saved."
        except Exception as e:
            return f"Error: {str(e)}"

@mcp.tool()
async def get_entity_details(entity_id: str) -> str:
    """Get the FULL JSON dump of a specific entity."""
    async with container() as request_container:
        service = await request_container.get(WorldQueryService)
        return service.get_entity_details(entity_id)

@mcp.tool()
async def add_entity_instance(
    definition_id: str, 
    parent_id: str, 
    entity_type: str,
    name: Optional[str] = None,
    extra_data_json: str = "{}"
) -> str:
    """Spawn a specific instance into the world."""
    async with container() as request_container:
        service = await request_container.get(WorldQueryService)
        try:
            data = json.loads(extra_data_json)
            return service.spawn_entity(definition_id, parent_id, entity_type, name, data)
        except Exception as e:
            return f"Spawn Error: {str(e)}"

@mcp.tool()
async def update_entity_tags(
    entity_id: str,
    add_tags: list[str] = [],
    remove_tags: list[str] = []
) -> str:
    """Update tags."""
    async with container() as request_container:
        service = await request_container.get(WorldQueryService)
        try:
            tags = service.update_tags(entity_id, add_tags, remove_tags)
            return f"Updated {entity_id}. Tags: {tags}"
        except Exception as e:
            return f"Error: {e}"

@mcp.tool()
async def register_new_relation(relation_id: str, description: str) -> str:
    """Register a new relation TYPE."""
    async with container() as request_container:
        service = await request_container.get(WorldQueryService)
        service.register_relation_type(relation_id, description)
        return f"Relation type '{relation_id}' registered."

@mcp.tool()
async def add_fact(from_id: str, to_id: str, relation_type: str) -> str:
    """Create a relationship between two entities."""
    async with container() as request_container:
        service = await request_container.get(WorldQueryService)
        e1 = service.get_entity(from_id)
        e2 = service.get_entity(to_id)
        if not e1 or not e2:
            return "Error: Entities not found."
        
        if relation_type not in service.graph.relation_types:
             return f"Error: Unknown relation '{relation_type}'. Register it first."

        service.add_relation(e1, e2, relation_type)
        return f"Linked: {e1.name} --[{relation_type}]--> {e2.name}"

@mcp.tool()
# TODO: в какой-то момент будет не хватать имён
async def get_relationship_table(
    source_type: Optional[str] = None, 
    target_type: Optional[str] = None
) -> str:
    """Get a Markdown table of relationships."""
    async with container() as request_container:
        service = await request_container.get(WorldQueryService)
        return service.analyze_relationships(source_type, target_type)

@mcp.tool()
async def list_template_schemas(config_type: str) -> str:
    """Get JSON Schema for a template."""
    async with container() as request_container:
        service = await request_container.get(TemplateEditorService)
        try:
            schema = service.get_schema(config_type)
            return json.dumps(schema, indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

@mcp.tool()
async def get_template_list(config_type: str) -> str:
    """Get list of existing templates."""
    async with container() as request_container:
        service = await request_container.get(TemplateEditorService)
        try:
            data = service.get_data(config_type)
            summary = [f"{item.get('id')}: {item.get('name', 'No Name')}" for item in data]
            return "\n".join(summary)
        except Exception as e:
            return f"Error: {str(e)}"

# --- 5. Start ---
if __name__ == "__main__":
    mcp.run(transport="sse")