import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException
from dishka import FromDishka
from dishka.integrations.fastapi import DishkaRoute
from pydantic import BaseModel
from src.services.simulation import SimulationService
from src.services.storyteller import StorytellerService


class NarrateRequest(BaseModel):
    events: List[Dict[str, Any]] # Список событий
    setting: str = "dark fantasy" # Опционально
    examples: Optional[List[str]] = None

class EntityDescRequest(BaseModel):
    entity_id: str
    
class BuildWorldRequest(BaseModel):
    width: int = 3
    height: int = 3
    biome_ids: List[str] = []

class RunSimRequest(BaseModel):
    epochs: int = 50

router = APIRouter(prefix="/api/simulation", route_class=DishkaRoute)

# --- Нарратив ---

@router.post("/build")
async def build_world(
    req: BuildWorldRequest, # Используем новую модель
    background_tasks: BackgroundTasks,
    service: FromDishka[SimulationService]
):
    """Генерирует структуру мира с учетом размеров и биомов"""
    # Валидация размеров (чтобы не повесить сервер)
    w = max(2, min(req.width, 20)) 
    h = max(2, min(req.height, 20))
    
    # Передаем параметры в сервис
    result = service.generate_world_only(
        width=w, 
        height=h, 
        biome_ids=req.biome_ids if req.biome_ids else None
    )
    return result

@router.post("/narrate")
async def narrate_history(
    request: NarrateRequest, # <-- FastAPI теперь знает, как парсить body
    service: FromDishka[StorytellerService]
):
    try:
        # Передаем данные из модели в сервис
        text = await service.narrate_history(
            events=request.events,
            setting=request.setting,
            examples=request.examples
        )
        return {"text": text}
    except Exception as e:
        # Логируем ошибку для отладки
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
            for line in f:
                logs.append(line.strip())
    except Exception as e:
        return {"logs": [f"Error reading logs: {e}"]}
        
    # Возвращаем последние 100 строк, чтобы не грузить браузер
    return {"logs": logs[-100:]}

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
    entities = service.get_all_entities_list()
    return {"entities": entities}

# --- Данные для Хроник (Chronicles Tab) ---

@router.get("/latest_graph")
async def get_latest_graph(service: FromDishka[SimulationService]):
    # Читаем файл снапшота (или берем из памяти сервиса)
    snapshot_path = service.output_dir / "world_final.json"
    if not snapshot_path.exists():
         # Если финал не готов, берем 0 эпоху или возвращаем ошибку
         snapshot_path = service.snapshots_dir / "world_epoch_0.json"
    
    if not snapshot_path.exists():
         return {"entities": {}, "relations": []}

    with open(snapshot_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data["graph"] # Возвращаем только часть graph
