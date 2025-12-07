import contextlib
import json
import traceback
from typing import AsyncIterator, List, Literal, Optional, Set
from mcp.server.fastmcp import FastMCP
from dishka import make_async_container
from pydantic import BaseModel, Field
from src.models.generation import World
from src.services.llm_service import LLMService
from src.ioc import RepositoryProvider, GeneralProvider, AppProvider
from src.services.world_query_service import WorldQueryService
from src.services.template_editor import TemplateEditorService
from src.models.registries import (
    BIOME_REGISTRY, LOCATION_REGISTRY, FACTION_REGISTRY, 
    RESOURCE_REGISTRY, BOSSES_REGISTRY, BELIEF_REGISTRY, 
    TRAIT_REGISTRY, CALENDAR_REGISTRY, TRANSFORMATION_REGISTRY
)
from src.models.templates_schema import BiomeTemplate, FactionTemplate, LocationTemplate

import logging
from mcp.server.streamable_http import EventCallback, EventMessage, EventStore
from mcp.types import JSONRPCMessage
# Утилиты и конфиг
from src.utils import save_world_to_json
# Предполагаем, что config доступен. Если нет, путь можно хардкодить или передавать через ENV
try:
    from config import fallback_template_path
except ImportError:
    # Fallback, если config.py не найден в контексте запуска
    from pathlib import Path
    fallback_template_path = Path("world_output/world_graph.json")
    

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

class NewEntityRequest(BaseModel):
    """Request to create a missing dependency."""
    name: str = Field(description="Name of the entity, e.g., 'Neon Bar'")
    type: Literal["biome", "location", "faction"] = Field(description="Type of template")
    context: str = Field(description="Brief description of what this is")

class WorldGenPlan(BaseModel):
    existing_biomes_to_use: list[str] = Field(description="List of EXISTING biome IDs to use")
    
    # Теперь мы явно просим LLM подумать о недостающих частях
    new_biomes: list[str] = Field(description="Names of NEW biomes to create")
    
    width: int = Field(default=3, description="Map width (usually 2-3)")
    height: int = Field(default=3, description="The height of the map (usually 2-3)")
    reasoning: str = Field(description="Explanation of the world composition")

# --- Helper for Saving ---
def _save_current_world_state(world: World):
    """
    Helper to persist world state to disk.
    Uses str(path) because open() typically needs a path string, not a URI.
    """
    try:
        # Приводим путь к строке файловой системы
        # Если fallback_template_path это Path объект
        path_str = str(fallback_template_path)
        save_world_to_json(world, path_str)
        logger.info(f"💾 World state saved to {path_str}")
    except Exception as e:
        logger.error(f"❌ Failed to save world state: {e}")
        traceback.print_exc()

async def resolve_dependencies(
    llm: LLMService, 
    editor: TemplateEditorService, 
    biome_ids: List[str],
    log_output: List[str]
) -> None:
    """
    Рекурсивно проверяет зависимости выбранных биомов.
    """
    required_locations: Set[str] = set()
    required_factions: Set[str] = set()

    # 1. Сбор требований
    for b_id in biome_ids:
        tmpl: BiomeTemplate = BIOME_REGISTRY.get(b_id)
        if not tmpl: continue
        
        for loc_id in tmpl.allowed_locations:
            required_locations.add(loc_id)
        for rule in tmpl.factions:
            required_factions.add(rule.definition_id)

    # 2. Разрешение ЛОКАЦИЙ
    for loc_id in required_locations:
        if loc_id not in LOCATION_REGISTRY:
            log_output.append(f"  Start creating missing LOCATION: {loc_id}...")
            try:
                readable_name = loc_id.replace("loc_", "").replace("_", " ").title()
                
                new_tmpl_data = await llm.generate_template(
                    prompt_text=f"Create a LocationTemplate for '{readable_name}'. ID must be '{loc_id}'.",
                    model_class=LocationTemplate
                )
                new_tmpl_data['id'] = loc_id
                
                # ИСПРАВЛЕНО: используем ключ 'locations' вместо пути к файлу
                editor.append_template("locations", new_tmpl_data)
                
                # Обновляем реестр в памяти
                LOCATION_REGISTRY.register(loc_id, LocationTemplate(**new_tmpl_data))
                log_output.append(f"    ✅ Created Location: {loc_id}")
            except Exception as e:
                 log_output.append(f"    ❌ Failed Location {loc_id}: {e}")

    # 3. Разрешение ФРАКЦИЙ
    for fac_id in required_factions:
        if fac_id not in FACTION_REGISTRY:
            log_output.append(f"  Start creating missing FACTION: {fac_id}...")
            try:
                readable_name = fac_id.replace("fac_", "").replace("_", " ").title()
                
                new_tmpl_data = await llm.generate_template(
                    prompt_text=f"Create a FactionTemplate for '{readable_name}'. ID must be '{fac_id}'.",
                    model_class=FactionTemplate
                )
                new_tmpl_data['id'] = fac_id
                
                # ИСПРАВЛЕНО: используем ключ 'factions'
                editor.append_template("factions", new_tmpl_data)
                
                FACTION_REGISTRY.register(fac_id, FactionTemplate(**new_tmpl_data))
                log_output.append(f"    ✅ Created Faction: {fac_id}")
            except Exception as e:
                 log_output.append(f"    ❌ Failed Faction {fac_id}: {e}")

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
    retry_interval=250 # 0.25 second
)

# --- 4. Tools ---

@mcp.tool()
async def generate_new_world(description: str) -> str:
    """
    Creates a new world. 
    1. Analyzes request.
    2. Generates MISSING Biomes.
    3. Recursively generates MISSING Locations/Factions required by those biomes.
    4. Builds the world graph.
    """
    from src.services.template_editor import TemplateEditorService
    from src.word_generator import WorldGenerator
    from src.models.generation import World
    from src.utils import save_world_to_json
    from config import fallback_template_path

    if not container: return "Error: Container not initialized"

    log_output = []
    
    async with container() as request_container:
        llm = await request_container.get(LLMService)
        generator = await request_container.get(WorldGenerator)
        editor = await request_container.get(TemplateEditorService)
        current_world = await request_container.get(World)

        # 1. Planning
        available_biomes = list(BIOME_REGISTRY.keys())
        log_output.append(f"🔍 Planning world for: '{description}'...")
        
        try:
            plan: WorldGenPlan = await llm.generate_structure(
                f"User request: '{description}'.\n"
                f"Available Biomes: {available_biomes}\n"
                "Create a plan. If you need a biome not in the list, add it to 'new_biomes'.",
                WorldGenPlan
            )
        except Exception as e:
            return f"Planning Error: {e}"

        final_biome_ids = list(plan.existing_biomes_to_use)

        # 2. Create NEW Biomes (First Pass)
        for new_biome_name in plan.new_biomes:
            # Generate ID
            slug = new_biome_name.lower().replace(" ", "_")[:20]
            new_id = f"biome_{slug}" # Убрали UUID для чистоты, если имена уникальны
            
            if new_id in BIOME_REGISTRY:
                final_biome_ids.append(new_id)
                continue

            log_output.append(f"🔨 Generating Biome: {new_biome_name} ({new_id})...")
            try:
                # ВАЖНО: Просим LLM сразу придумать ID для локаций и фракций, даже если их нет
                template_data = await llm.generate_template(
                    f"Create BiomeTemplate for '{new_biome_name}'. "
                    f"Context: {description}. ID: '{new_id}'. "
                    f"Make sure to invent IDs for 'allowed_locations' (e.g., ['loc_{slug}_ruins']) "
                    f"and 'factions' (e.g., definition_id='fac_{slug}_natives').",
                    BiomeTemplate
                )
                editor.append_template("biomes", template_data)
            
                BIOME_REGISTRY.register(new_id, BiomeTemplate(**template_data))
                final_biome_ids.append(new_id)
                
            except Exception as e:
                log_output.append(f"  ❌ Error creating biome {new_biome_name}: {e}")

        # 3. Dependency Resolution (The Fix)
        log_output.append("🔗 Resolving dependencies (Locations/Factions)...")
        await resolve_dependencies(llm, editor, final_biome_ids, log_output)

        # 4. Final Generation
        if not final_biome_ids:
            return "❌ Error: No biomes available to generate world."

        try:
            log_output.append(f"🌍 Assembling world map ({plan.width}x{plan.height})...")
            new_world_obj = generator.generate(
                biome_ids=final_biome_ids,
                world_width=plan.width,
                world_height=plan.height,
                num_biomes=plan.width * plan.height
            )
            
            current_world.graph = new_world_obj.graph
            save_world_to_json(current_world, fallback_template_path.as_uri())
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return "\n".join(log_output) + f"\n💥 Core Generation Error: {e}"

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
async def define_new_archetype(config_type: str, template_json: str) -> str:
    """
    Add a NEW template to the database.
    Args:
        config_type: One of ['biomes', 'locations', 'factions', 'resources', 'belief', 'trait']
        template_json: The JSON body of the template.
    """
    async with container() as request_container:
        service = await request_container.get(TemplateEditorService)
        try:
            data = json.loads(template_json)
            # ИСПРАВЛЕНО: Убрали лишний аргумент config_file
            new_id = service.append_template(config_type=config_type, new_item=data)
            return f"Success: Template '{new_id}' saved to '{config_type}'."
        except Exception as e:
            return f"Error: {str(e)}"

@mcp.tool()
async def get_entity_details(entity_id: str) -> str:
    """Get the FULL JSON dump of a specific entity."""
    async with container() as request_container:
        service = await request_container.get(WorldQueryService)
        return service.get_entity_details(entity_id)

@mcp.tool()
# проблема при добавлении кастомной сущности мб тут
async def add_entity_instance(
    definition_id: str, 
    parent_id: str, 
    entity_type: str,
    name: Optional[str] = None,
    extra_data_json: str = "{}"
) -> str:
    """Spawn a specific instance into the world AND save state."""
    async with container() as request_container:
        service = await request_container.get(WorldQueryService)
        try:
            data = json.loads(extra_data_json)
            result = service.spawn_entity(definition_id, parent_id, entity_type, name, data)
            
            # --- FIX: Save Changes ---
            _save_current_world_state(service.world)
            # -------------------------
            
            return result
        except Exception as e:
            return f"Spawn Error: {str(e)}"

@mcp.tool()
async def update_entity_tags(
    entity_id: str,
    add_tags: list[str] = [],
    remove_tags: list[str] = []
) -> str:
    """Update tags AND save state."""
    async with container() as request_container:
        service = await request_container.get(WorldQueryService)
        try:
            tags = service.update_tags(entity_id, add_tags, remove_tags)
            
            # --- FIX: Save Changes ---
            _save_current_world_state(service.world)
            # -------------------------

            return f"Updated {entity_id}. Tags: {tags}"
        except Exception as e:
            return f"Error: {e}"

@mcp.tool()
async def register_new_relation(relation_id: str, description: str) -> str:
    """Register a new relation TYPE. (Note: Only updates Runtime, usually doesn't need save unless types are persisted separately)"""
    async with container() as request_container:
        service = await request_container.get(WorldQueryService)
        service.register_relation_type(relation_id, description)
        
        # Если типы связей хранятся внутри world.graph.relation_types, то тоже надо сохранить
        _save_current_world_state(service.world)
        
        return f"Relation type '{relation_id}' registered and saved."

@mcp.tool()
async def add_fact(from_id: str, to_id: str, relation_type: str) -> str:
    """Create a relationship between two entities AND save state."""
    async with container() as request_container:
        service = await request_container.get(WorldQueryService)
        e1 = service.get_entity(from_id)
        e2 = service.get_entity(to_id)
        if not e1 or not e2:
            return "Error: Entities not found."
        
        if relation_type not in service.graph.relation_types:
             return f"Error: Unknown relation '{relation_type}'. Register it first."

        service.add_relation(e1, e2, relation_type)
        
        # --- FIX: Save Changes ---
        _save_current_world_state(service.world)
        # -------------------------

        return f"Linked: {e1.name} --[{relation_type}]--> {e2.name}"

@mcp.tool()
async def get_registry_status(selected_ent: List[str] = []) -> str:
    """
    Returns contents of registries.
    Args:
        selected_ent: List of registries to inspect (e.g. ["factions", "resources"]). 
                      If empty, returns a summary count of all.
                      Valid keys: biomes, locations, factions, resources, bosses, beliefs, traits, calendar.
    """
    if not container: return "Error: Container not init"
    
    # Карта реестров
    registry_map = {
        "biomes": BIOME_REGISTRY,
        "locations": LOCATION_REGISTRY,
        "factions": FACTION_REGISTRY,
        "resources": RESOURCE_REGISTRY,
        "bosses": BOSSES_REGISTRY,
        "beliefs": BELIEF_REGISTRY,
        "traits": TRAIT_REGISTRY,
        "calendar": CALENDAR_REGISTRY,
        "transformations": TRANSFORMATION_REGISTRY
    }

    summary = []
    
    # Режим 1: Краткая сводка (если ничего не выбрано)
    if not selected_ent:
        summary.append("📊 **Registry Summary (Counts)**:")
        for key, reg in registry_map.items():
            if reg: # Если реестр не None
                summary.append(f"- **{key.title()}**: {len(reg)} templates")
        summary.append("\n💡 *Tip: Call with selected_ent=['factions'] to see IDs.*")
        return "\n".join(summary)

    # Режим 2: Детальный список выбранных
    for key in selected_ent:
        key_lower = key.lower()
        if key_lower in registry_map:
            reg = registry_map[key_lower]
            items = list(reg.keys())
            # Ограничиваем вывод, если там тысячи элементов (на всякий случай)
            display_items = items[:50] 
            
            summary.append(f"📂 **{key.title()}** ({len(items)}):")
            summary.append(", ".join(display_items))
            if len(items) > 50:
                summary.append(f"... and {len(items)-50} more.")
            summary.append("") # Пустая строка для отступа
        else:
            summary.append(f"⚠️ Unknown registry category: {key}")

    return "\n".join(summary)


@mcp.tool()
async def get_relationship_table(
    source_type: Optional[str] = None, 
    target_type: Optional[str] = None,
    include_tags: List[str] = [],
    min_age: Optional[int] = None,
    max_age: Optional[int] = None
) -> str:
    """
    Get a Markdown table of relationships with filtering.
    Useful for tracking events in specific epochs or filtering by importance tags.
    
    Args:
        source_type: Filter by source entity type (e.g. 'Faction')
        target_type: Filter by target entity type (e.g. 'Event')
        include_tags: Only show relations where at least one entity has these tags (e.g. ["Major", "War"])
        min_age: Show relations involving entities created after this age.
        max_age: Show relations involving entities created before this age.
    """
    async with container() as request_container:
        service = await request_container.get(WorldQueryService)
        return service.analyze_relationships(
            source_type=source_type, 
            target_type=target_type,
            include_tags=include_tags,
            min_age=min_age,
            max_age=max_age
        )

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