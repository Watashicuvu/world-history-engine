from src.models.generation import Entity

# TODO: внедрить эту логику

SYSTEM_TAGS_BLACKLIST = {
    # Геометрия / Граф
    "no_edge", "isolated", "edge_only", "has_port",
    # Состояния (обычно передаются отдельным полем Status, а не как стиль)
    "active", "inactive", "dead", "absorbed", "fled", "resolved",
    # Маркеры спавна
    "new_settlement", "boss_spawned", "generated"
}

def get_narrative_tags(entity: Entity) -> list[str]:
    """Возвращает только атмосферные тэги для промпта."""
    if not entity.tags:
        return []
    return [t for t in entity.tags if t not in SYSTEM_TAGS_BLACKLIST]