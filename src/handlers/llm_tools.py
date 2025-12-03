from typing import Dict, Any, Type
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute

# Импортируем ваши модели шаблонов
from src.services.world_query_service import WorldQueryService
from src.models.naming_schemas import BiomeLexiconEntry
from src.models.templates_schema import (
    BiomeTemplate, FactionTemplate, LocationTemplate, 
    ResourceTemplate, BossesTemplate, TransformationRule
)
from src.services.llm_service import LLMService
from src.services.storyteller import StorytellerService

router = APIRouter(prefix="/api/llm", route_class=DishkaRoute)

# Маппинг строковых ключей (как в URL) на Pydantic классы
TEMPLATE_MAP: Dict[str, Type[BaseModel]] = {
    "biomes": BiomeTemplate,
    "factions": FactionTemplate,
    "locations": LocationTemplate,
    "resources": ResourceTemplate,
    "bosses": BossesTemplate,
    "transformations": TransformationRule,
    "naming_biomes": BiomeLexiconEntry,
}

class SuggestRequest(BaseModel):
    prompt: str

@router.post("/suggest/{config_type}")
async def suggest_template(
    config_type: str,
    request: SuggestRequest,
    service: FromDishka[LLMService]
):
    """
    Генерирует заполненный шаблон на основе текстового описания.
    Пример: POST /api/llm/suggest/factions
    Body: { "prompt": "Агрессивные гномы-пироманты, живущие в вулкане" }
    """
    model_class = TEMPLATE_MAP.get(config_type)
    if not model_class:
        raise HTTPException(status_code=400, detail=f"Unknown template type: {config_type}")

    try:
        data = await service.generate_template(request.prompt, model_class)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/describe/{entity_id}")
async def describe_entity(
    entity_id: str,
    service: FromDishka[StorytellerService]
):
    """
    Получить художественное описание сущности по её ID.
    Используется в контекстном меню графа.
    """
    description = await service.describe_entity(entity_id)
    return {"text": description}

@router.post("/agent/command")
async def agent_command(
    request: SuggestRequest, # { prompt: "Убей короля орков" }
    llm_service: FromDishka[LLMService],
    query_service: FromDishka[WorldQueryService]
):
    # 1. Собираем инструменты из QueryService
    # Нам нужно обернуть методы сервиса, чтобы LangChain видел их docstrings и типы
    
    # Примечание: Лучше вынести создание tools в отдельный файл utils/tools.py,
    # но для примера покажу тут.
    from langchain_core.tools import tool

    @tool
    def search_tool(query: str, exclude_dead: bool = True):
        """Search for entities. If exclude_dead is True, filters out dead/inactive."""
        excl = ["dead", "inactive", "absorbed"] if exclude_dead else []
        return query_service.query_entities(exclude_tags=excl, limit=10)

    @tool
    def update_status_tool(entity_id: str, add_tags: list[str]):
        """Updates entity tags."""
        return query_service.update_tags(entity_id, add_tags, [])

    # 2. Запускаем агента
    tools = [search_tool, update_status_tool] # И другие...
    
    response = await llm_service.run_world_agent(
        user_query=request.prompt,
        tools=tools
    )
    
    return {"response": response}