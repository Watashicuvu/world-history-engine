from typing import Any, Dict, List
from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from fastapi import APIRouter, HTTPException
from src.services.template_editor import TemplateEditorService

# костыль; лучше разбить на два роутера, чем оставлять такой общий роутер
router = APIRouter(prefix="/api", route_class=DishkaRoute)


# 1. Получение списка доступных конфигов (biomes, factions и т.д.)
@router.get("/configs")
async def list_configs(
    service: FromDishka[TemplateEditorService]
):
    return service.get_available_configs()

# 2. Получение схемы (JSON Schema) для редактора
@router.get("/configs/{config_type}/schema")
async def get_schema(
    config_type: str, 
    service: FromDishka[TemplateEditorService]
):
    try:
        return service.get_schema(config_type)
    except ValueError:
        raise HTTPException(status_code=404, detail="Config not found")

# 3. Получение данных (содержимое YAML)
@router.get("/configs/{config_type}/data")
async def get_data(
    config_type: str, 
    service: FromDishka[TemplateEditorService]
):
    try:
        return service.get_data(config_type)
    except ValueError:
        raise HTTPException(status_code=404, detail="Config not found")

# 4. Сохранение данных
@router.post("/configs/{config_type}/data")
async def save_data(
    config_type: str, 
    data: List[Dict[str, Any]], 
    service: FromDishka[TemplateEditorService]
):
    try:
        service.save_data(config_type, data)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
