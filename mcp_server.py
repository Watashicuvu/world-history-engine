import contextlib
import json
from typing import AsyncIterator, Literal, Optional
from mcp.server.fastmcp import FastMCP
from dishka import make_async_container
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


# --- 2. Lifespan ---
@contextlib.asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[None]:
    global container
    logger.info("Initializing DI Container...")
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
