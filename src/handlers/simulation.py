import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from pydantic import BaseModel
from src.services.world_query_service import WorldQueryService
from src.services.simulation import SimulationService
from src.services.storyteller import StorytellerService


class NarrateRequest(BaseModel):
    events: List[Dict[str, Any]] 
    setting: str = "dark fantasy" 
    examples: Optional[List[str]] = None

class EntityDescRequest(BaseModel):
    entity_id: str
    
class BuildWorldRequest(BaseModel):
    width: int = 3
    height: int = 3
    # ИСПРАВЛЕНИЕ 1: Разрешаем None (null), который шлет JS
    biome_ids: Optional[List[str]] = None 

class RunSimRequest(BaseModel):
    epochs: int = 50

router = APIRouter(prefix="/api/simulation", route_class=DishkaRoute)

# --- Нарратив ---

@router.post("/build")
async def build_world(
    req: BuildWorldRequest, 
    background_tasks: BackgroundTasks,
    service: FromDishka[SimulationService]
):
    """Генерирует структуру мира с учетом размеров и биомов"""
    # Валидация размеров
    w = max(2, min(req.width, 20)) 
    h = max(2, min(req.height, 20))
    
    # Передаем параметры в сервис
    result = service.generate_world_only(
        width=w, 
        height=h, 
        # Если пришел None, сервис сам разберется (или передаст None дальше)
        biome_ids=req.biome_ids 
    )
    return result

@router.post("/narrate")
async def narrate_history(
    request: NarrateRequest, 
    service: FromDishka[StorytellerService]
):
    try:
        text = await service.narrate_history(
            events=request.events,
            setting=request.setting,
            examples=request.examples
        )
        return {"text": text}
    except Exception as e:
        print(f"Narrate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metadata")
async def get_metadata(
    service: FromDishka[WorldQueryService]
):
    try:
        text = service.get_world_metadata()
        return text
    except Exception as e:
        print(f"Narrate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history_logs")
async def get_history_logs():
    """Возвращает содержимое history.jsonl"""
    history_file = Path("world_output/history.jsonl")
    if not history_file.exists():
        return {"logs": []}
    
    logs = []
    try:
        with open(history_file, "r", encoding="utf-8") as f:
            # ИСПРАВЛЕНИЕ 2: Читаем весь файл.
            # Для "Машины времени" нам нужна полная история, чтобы
            # построить состояние на любой эпохе.
            for line in f:
                if line.strip():
                    logs.append(line.strip())
    except Exception as e:
        return {"logs": [f"Error reading logs: {e}"]}
        
    return {"logs": logs}

@router.post("/describe_entity")
async def describe_entity(
    request: EntityDescRequest,
    service: FromDishka[StorytellerService]
):
    try:
        text = await service.describe_entity(request.entity_id)
        return {"text": text}
    except Exception as e:
        print(f"Description error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Управление симуляцией ---

@router.post("/run")
async def run_simulation(
    req: RunSimRequest,
    background_tasks: BackgroundTasks,
    service: FromDishka[SimulationService]
):
    # Логика запуска истории
    background_tasks.add_task(service.run_simulation, req.epochs)
    return {"message": "History simulation started"}

@router.get("/status")
async def get_status(service: FromDishka[SimulationService]):
    return {"running": service.is_running}

# --- Данные для Визуализации (Simulation Tab) ---

@router.get("/latest_layout")
async def get_layout(service: FromDishka[SimulationService]):
    """Для отрисовки сетки биомов"""
    layout = service.get_latest_layout()
    return {"layout": layout}

@router.get("/latest_entities")
async def get_entities(service: FromDishka[SimulationService]):
    """Для отрисовки иконок локаций поверх карты"""
    # ИСПРАВЛЕНИЕ 3: Используем метод сервиса, который умеет читать из памяти (active_world)
    entities = service.get_all_entities_list()
    return {"entities": entities}

# --- Данные для Хроник (Chronicles Tab) ---

@router.get("/latest_graph")
async def get_latest_graph(service: FromDishka[SimulationService]):
    # ИСПРАВЛЕНИЕ 4: Делегируем логику сервису.
    # Ранее тут был код чтения файла, который игнорировал In-Memory состояние.
    # Теперь мы получаем самые свежие данные.
    graph_data = service.get_latest_graph_data()
    return graph_data

@router.get("/world/graph")
async def get_world_graph(
    service: FromDishka[WorldQueryService],
    exclude_tags: Optional[List[str]] = Query(default=["dead", "inactive", "absorbed"])
):
    """
    Возвращает JSON графа с примененными фильтрами.
    """
    return service.get_graph_snapshot(exclude_tags=exclude_tags)