import shutil
import json
import traceback # <--- ВАЖНО: Добавлено для отладки
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.services.world_query_service import WorldQueryService
from src.word_generator import WorldGenerator
from src.narrative_engine import NarrativeEngine
from src.naming import ContextualNamingService
from src.utils import save_world_to_json
from src.template_loader import load_all_templates, load_naming_data

class SimulationService:
    def __init__(self):
        self.is_running = False
        self.output_dir = Path("world_output")
        self.snapshots_dir = self.output_dir / "snapshots"
        self.history_file = self.output_dir / "history.jsonl"
        self.layout_file = Path("layouts/layout.json")
        self._world_cache = None
        self.active_world = None

    def _ensure_directories(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    def check_existing_world(self) -> bool:
        return (self.snapshots_dir / "world_epoch_0.json").exists()

    def generate_world_only(self, width: int = 3, height: int = 3, biome_ids: Optional[List[str]] = None):
        self._ensure_directories()
        load_all_templates()
        naming_service = ContextualNamingService()
        load_naming_data(naming_service)

        world_gen = WorldGenerator(naming_service=naming_service)
        world = world_gen.generate(
            num_biomes=-1, 
            world_width=width,
            world_height=height,
            biome_ids=biome_ids,
            layout_to_json=True
        )
        
        self.active_world = world 
        
        save_world_to_json(world, self.snapshots_dir / "world_epoch_0.json")
        save_world_to_json(world, self.output_dir / "world_final.json")
        return {
            "status": "created", 
            "size": f"{width}x{height}",
            "biomes_count": len(world.graph.entities)
        }

    def _restore_params_from_layout(self) -> Dict[str, Any]:
        params = {"width": 3, "height": 3, "biome_ids": None}
        if self.layout_file.exists():
            try:
                with open(self.layout_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    params["width"] = data.get("width", 3)
                    params["height"] = data.get("height", 3)
                    cells = data.get("cells", {})
                    unique_biomes = list(set(val for val in cells.values() if val is not None))
                    if unique_biomes:
                        params["biome_ids"] = unique_biomes
            except Exception as e:
                print(f"Warning: Failed to restore layout params: {e}")
        return params

    def run_simulation(self, target_epochs: int = 50):
        if self.is_running:
            raise Exception("Симуляция уже идет")
        
        self.is_running = True
        try:
            if not self.check_existing_world():
                print("No existing world found, generating new one...")
                self.generate_world_only()

            restore_data = self._restore_params_from_layout()
            w = restore_data["width"]
            h = restore_data["height"]
            b_ids = restore_data["biome_ids"]

            print("Loading templates...")
            load_all_templates()
            naming_service = ContextualNamingService()
            load_naming_data(naming_service)
            
            world_gen = WorldGenerator(naming_service=naming_service)
            
            print("Regenerating world structure for simulation...")
            world = world_gen.generate(
                num_biomes=-1, 
                world_width=w, 
                world_height=h,
                biome_ids=b_ids,
                layout_to_json=True 
            )

            self.active_world = world
            
            query_service = WorldQueryService(world)
            
            # NarrativeEngine регистрирует типы связей внутри __init__
            narrative = NarrativeEngine(
                world, 
                naming_service=naming_service, 
                world_generator=world_gen,
                query_service=query_service
            )
            
            # Проверка, что типы связей действительно зарегистрировались
            if "involved_in" not in world.graph.relation_types:
                raise RuntimeError("Narrative relations failed to register! 'involved_in' missing.")

            print(f"Starting simulation for {target_epochs} epochs...")
            
            with open(self.history_file, "w", encoding="utf-8") as f_hist:
                pass
            
            try:
                with open(self.history_file, "a", encoding="utf-8") as f_hist:
                    for age in range(1, target_epochs + 1):
                        # Эволюция мира
                        events = narrative.evolve(num_ages=1)
                        
                        # Запись событий
                        for event in events:
                            event_data = event.model_dump(mode='json')
                            f_hist.write(json.dumps(event_data, ensure_ascii=False) + "\n")
                        
                        # (Опционально) Можно делать flush в active_world, если нужны тяжелые вычисления,
                        # но объекты Python и так изменяются по ссылке.
                            
            except Exception as e:
                print("\n!!! CRITICAL SIMULATION ERROR !!!")
                traceback.print_exc() # <--- Показываем полный стек вызова ошибки
                
                error_event = {
                    "age": narrative.age,
                    "event_type": "CRITICAL_ERROR",
                    "summary": f"Симуляция прервана ошибкой: {str(e)}",
                    "data": {"error": str(e)}
                }
                with open(self.history_file, "a", encoding="utf-8") as f_hist:
                    f_hist.write(json.dumps(error_event, ensure_ascii=False) + "\n")
            
            save_world_to_json(world, self.output_dir / "world_final.json")
            print("Simulation finished.")
            
        finally:
            self.is_running = False

    def get_latest_graph_data(self) -> Dict[str, Any]:
        """
        Если симуляция активна (или мир загружен в память) - отдаем из памяти.
        Иначе читаем с диска.
        """
        if self.active_world:
            # Сериализуем граф из памяти в dict
            # Используем model_dump, так как World - это Pydantic модель (обычно)
            # Или вручную собираем структуру, если World не Pydantic
            try:
                # Предполагаем, что world.graph имеет метод dict() или model_dump()
                # Если graph это объект Graph с entities (dict) и relations (list)
                return {
                    "entities": {k: v.model_dump(mode='json') for k, v in self.active_world.graph.entities.items()},
                    "relations": [r.model_dump(mode='json') for r in self.active_world.graph.relations]
                }
            except Exception as e:
                print(f"Error dumping active world: {e}")
                # Fallback to disk reading below

        final_path = self.output_dir / "world_final.json"
        
        if not final_path.exists():
            if not self.snapshots_dir.exists():
                return {"entities": {}, "relations": []}
            snapshots = sorted(self.snapshots_dir.glob("world_epoch_*.json"))
            if not snapshots:
                return {"entities": {}, "relations": []}
            final_path = snapshots[-1]

        try:
            with open(final_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("graph", {})
        except Exception as e:
            print(f"Error reading graph: {e}")
            return {"entities": {}, "relations": []}

    def get_latest_layout(self) -> Dict[str, Any]:
        if not self.layout_file.exists():
            return {"width": 10, "height": 10, "cells": {}}
        try:
            with open(self.layout_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"width": 10, "height": 10, "cells": {}}

    def get_all_entities_list(self) -> List[Dict[str, Any]]:
        """
        Аналогично - берем из памяти для скорости
        """
        if self.active_world:
            return [
                e.model_dump(mode='json') 
                for e in self.active_world.graph.entities.values()
            ]
            
        graph_data = self.get_latest_graph_data()
        entities_dict = graph_data.get("entities", {})
        # Если get_latest_graph_data вернул словарь из файла, values() уже dict
        if isinstance(entities_dict, dict):
            return list(entities_dict.values())
        return []