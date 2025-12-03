import json
import uuid
import yaml
from pathlib import Path
from typing import Any, Dict
from enum import Enum

from src.models.generation import (Entity, World, RelationType, EntityType, WorldGraph)
from src.spatial_layout_gen import SpatialLayout

def make_id(prefix: str) -> str:
    """Генерирует уникальный ID с префиксом."""
    return f"{prefix}_{str(uuid.uuid4())[:6]}"

def load_template_with_enum_keys(path: Path, key_enum: type[Enum]):
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return {key_enum[k]: v for k, v in raw.items()}

def register_all_relation_types(graph: WorldGraph):
    """Регистрирует все известные RelationType в графе."""
    # 1. Связи из исходного engine (экономика)
    graph.relation_types["is_mined_by"] = RelationType(
        id="is_mined_by",
        from_type=EntityType.RESOURCE,
        to_type=EntityType.METHOD,
        description="Добывается методом"
    )
    graph.relation_types["has_problem"] = RelationType(
        id="has_problem",
        from_type=EntityType.RESOURCE,
        to_type=EntityType.PROBLEM,
        description="Имеет проблему"
    )

    # 2. Связи из WorldGenerator (иерархия и культура)
    graph.relation_types["located_in"] = RelationType(
        id="located_in",
        from_type=EntityType.RESOURCE,
        to_type=EntityType.LOCATION,
        description="Находится в"
    )
    graph.relation_types["faction_located_in"] = RelationType(
        id="faction_located_in",
        from_type=EntityType.FACTION,
        to_type=EntityType.LOCATION,
        description="Базируется в"
    )
    graph.relation_types["ritual_performed_in"] = RelationType(
        id="ritual_performed_in",
        from_type=EntityType.RITUAL,
        to_type=EntityType.LOCATION,
        description="Проводится в"
    )
    graph.relation_types["belief_held_in"] = RelationType(
        id="belief_held_in",
        from_type=EntityType.BELIEF,
        to_type=EntityType.LOCATION,
        description="Исповедуется в"
    )
    graph.relation_types["worship_object_located_in"] = RelationType(
        id="worship_object_located_in",
        from_type=EntityType.OBJECT_OF_WORSHIP,
        to_type=EntityType.LOCATION,
        description="Почитается в"
    )

    # 3. Связи из NarrativeEngine
    graph.relation_types["leads"] = RelationType(
        id="leads",
        from_type=EntityType.CHARACTER,
        to_type=EntityType.FACTION,
        description="Предводитель"
    )
    graph.relation_types["joined"] = RelationType(
        id="joined",
        from_type=EntityType.CHARACTER,
        to_type=EntityType.FACTION,
        description="Присоединился к"
    )
    graph.relation_types["involved_in"] = RelationType(
        id="involved_in",
        from_type=EntityType.FACTION,
        to_type=EntityType.CONFLICT,
        description="Участвует в конфликте"
    )
    graph.relation_types["has_reason"] = RelationType(
        id="has_reason",
        from_type=EntityType.CONFLICT,
        to_type=EntityType.DISPUTE_REASON,
        description="Причина конфликта"
    )
    graph.relation_types["absorbed_by"] = RelationType(
        id="absorbed_by",
        from_type=EntityType.FACTION,
        to_type=EntityType.FACTION,
        description="Поглощена фракцией"
    )
    graph.relation_types["fled_to"] = RelationType(
        id="fled_to",
        from_type=EntityType.FACTION,
        to_type=EntityType.LOCATION,
        description="Сбежала в"
    )
    graph.relation_types["allied_with"] = RelationType(
        id="allied_with",
        from_type=EntityType.FACTION,
        to_type=EntityType.FACTION,
        description="В союзе с",
        is_symmetric=True
    )
    graph.relation_types["resolved_as"] = RelationType(
        id="resolved_as",
        from_type=EntityType.CONFLICT,
        to_type=EntityType.EVENT,
        description="Разрешён как событие"
    )
    graph.relation_types["featured_in"] = RelationType(
        id="featured_in",
        from_type=EntityType.CHARACTER,
        to_type=EntityType.EVENT,
        description="Фигурирует в событии"
    )
    graph.relation_types["occurred_at"] = RelationType(
        id="occurred_at",
        from_type=EntityType.EVENT,
        to_type=EntityType.LOCATION,
        description="Произошло в локации"
    )
    graph.relation_types["affected_by"] = RelationType(
        id="affected_by",
        from_type=EntityType.FACTION,
        to_type=EntityType.EVENT,
        description="Затронута событием"
    )
    graph.relation_types["has_belief"] = RelationType(
        id="has_belief",
        from_type=EntityType.RITUAL,
        to_type=EntityType.BELIEF,
        description="Основан на убеждении"
    )
    graph.relation_types["worships"] = RelationType(
        id="worships",
        from_type=EntityType.BELIEF,
        to_type=EntityType.OBJECT_OF_WORSHIP,
        description="Поклоняется"
    )

def spatial_layout_to_dict(layout: SpatialLayout) -> Dict[str, Any]:
    """Преобразует SpatialLayout в словарь, пригодный для сериализации в JSON."""
    occupied = {}
    for coord, biome in layout.occupied_cells().items():
        if biome is not None:
            occupied[f"{coord[0]},{coord[1]}"] = biome 

    edge_cells = [f"{x},{y}" for x, y in layout.edge_cells]

    return {
        "width": layout.width,
        "height": layout.height,
        "occupied": occupied,
        "edge_cells": edge_cells
    }

def save_spatial_layout_to_json(layout, path: str):
    """
    Сохраняет Layout так, чтобы JS мог легко прочитать ключи координат.
    Преобразует ключи (x, y) -> "x,y" (строка без пробелов).
    """
    cells_data = {}
    for coord, biome_id in layout.cells.items():
        if biome_id is not None:
            # Формат "x,y" самый простой для парсинга
            key = f"{coord[0]},{coord[1]}"
            cells_data[key] = biome_id

    data = {
        "width": layout.width,
        "height": layout.height,
        "cells": cells_data
    }

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_entity_icon(entity: Entity) -> str:
    """
    Возвращает эмодзи для сущности. 
    Если иконка есть в data, берем её. Иначе генерируем детерминировано.
    """
    if entity.data and "icon" in entity.data and entity.data["icon"]:
        return entity.data["icon"]
    
    # Fallback генератор (если в шаблоне забыли иконку)
    icons_map = {
        'Biome': ['🌲', '🌵', '🏔️', '🌊', '🌴', '🌑', '❄️', '🌋', '🍄', '🌾'],
        'Location': ['🛖', '🏰', '🗿', '⛺', '🏛️', '🏚️', '🌲', '🕳️', '🏠', '🗼'],
        'Faction': ['⚔️', '🛡️', '👑', '🧙', '🧝', '👁️', '🏹', '⚒️'],
        'Bosses': ['💀','🐉'],
        'Resource': ['🪵', '💎', '🍖', '💧', '🌾', '⛏️', '💊', '📜'],
        'default': ['❓', '✨', '🎲', '🌀']
    }
    
    pool = icons_map.get(entity.type.value, ["❓"])
    # Детерминированный выбор на основе ID, чтобы иконка не скакала
    idx = abs(hash(entity.id)) % len(pool)
    return pool[idx]

def load_spatial_layout_from_json(filepath: str, biome_enum_class) -> SpatialLayout:
    """
    (Опционально) Загружает SpatialLayout из JSON.
    Требует передачи класса Biome для восстановления enum.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    layout = SpatialLayout(data["width"], data["height"])
    # Очистим автоматически сгенерированные edge_cells и восстановим из файла (если нужно)
    layout.edge_cells = {tuple(map(int, cell.split(','))) for cell in data.get("edge_cells", [])}

    for coord_str, biome_value in data.get("occupied", {}).items():
        x, y = map(int, coord_str.split(','))
        biome_enum = biome_enum_class[biome_value]  # восстанавливаем enum
        layout.cells[(x, y)] = biome_enum

    return layout

def save_world_to_json(world: World, filepath: str | Path):
    """Сохраняет мир в JSON-файл."""
    data = world.model_dump(mode="json", exclude_none=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ Мир сохранён в {filepath}")

def load_world_from_json(filepath: str | Path) -> World:
    """Загружает мир из JSON и восстанавливает RelationType."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    world = World.model_validate(data)
    # Восстанавливаем типы связей
    register_all_relation_types(world.graph)
    print(f"✅ Мир загружен из {filepath}, RelationType восстановлены")
    return world