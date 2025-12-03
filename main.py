import json
import shutil
from pathlib import Path
from typing import List

from src.word_generator import WorldGenerator
from src.narrative_engine import NarrativeEngine
from src.naming import ContextualNamingService
from src.utils import save_world_to_json
from src.template_loader import load_all_templates, load_naming_data

def setup_directories():
    """Создает папки для вывода, очищая старые данные."""
    output_dir = Path("world_output")
    snapshots_dir = output_dir / "snapshots"
    
    # Очистка и пересоздание
    if output_dir.exists():
        shutil.rmtree(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    
    return output_dir, snapshots_dir

def main():
    # 0. Подготовка папок
    output_dir, snapshots_dir = setup_directories()
    history_file = output_dir / "history.jsonl"

    # 1. Генерация иерархического мира
    print("🌍 Генерация мира...")
    load_all_templates()
    
    naming_service = ContextualNamingService()
    load_naming_data(naming_service)

    world_gen = WorldGenerator(naming_service=naming_service)
    
    # Генерируем начальное состояние
    world = world_gen.generate(num_biomes=-1, layout_to_json=True)
    
    # Сохраняем "Нулевой километр" (изначальный мир до истории)
    save_world_to_json(world, snapshots_dir / "world_epoch_0.json")

    print(f"Биомы: {len([e for e in world.graph.entities.values() if e.type == 'Biome'])}")
    print(f"Локации: {len([e for e in world.graph.entities.values() if e.type == 'Location'])}")
    print(f"Фракции: {len([e for e in world.graph.entities.values() if e.type == 'Faction'])}")

    # 2. Запуск нарративного двигателя
    total_ages = 100
    snapshot_interval = 10
    
    print(f"\n⏳ Запуск эволюции мира ({total_ages} эпох)...")
    narrative_engine = NarrativeEngine(world=world, world_generator=world_gen, naming_service=naming_service)
    
    # Открываем файл истории для потоковой записи
    with open(history_file, "w", encoding="utf-8") as f_hist:
        
        # Цикл по одной эпохе, чтобы перехватывать управление
        for age in range(1, total_ages + 1):
            
            # Эволюционируем на 1 шаг
            # Важно: evolve внутри себя делает self.age += 1, поэтому передаем num_ages=1
            events = narrative_engine.evolve(num_ages=1)
            
            # 1. Логируем события в консоль и в файл
            print("\n📜 События истории:")
            for event in events:
                # Консоль
                summary = event.data.get("summary", event.name)
                print(f"Эпоха {age}: {summary}") # Можно раскомментировать, если нужно видеть прогресс
                
                # Файл JSONL (каждая строка - валидный JSON события)
                # Преобразуем Pydantic модель в dict, затем в JSON строку
                # model_dump_json() удобен, но иногда лучше контролировать через dict
                event_data = event.model_dump(mode='json')
                f_hist.write(json.dumps(event_data, ensure_ascii=False) + "\n")

            # 2. Делаем Снэпшот (полное сохранение графа)
            # if age % snapshot_interval == 0:
            #     filename = f"world_epoch_{age}.json"
            #     save_world_to_json(world, snapshots_dir / filename)
            #     print(f"📸 Снэпшот сохранен: {filename} (Событий за цикл: {len(events)})")

    # 3. Финальное сохранение (перезаписываем основной output для удобства)
    save_world_to_json(world, output_dir / "world_final.json")
    print(f"\n✅ История завершена. Данные в папке '{output_dir}'")

if __name__ == "__main__":
    main()