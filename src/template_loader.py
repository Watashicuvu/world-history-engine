import yaml
import logging
from pathlib import Path
from typing import List, Dict, Any

# Импорт реестров
from src.models.registries import (
    BELIEF_REGISTRY,
    BIOME_REGISTRY,
    BOSSES_REGISTRY, 
    LOCATION_REGISTRY, 
    RESOURCE_REGISTRY, 
    FACTION_REGISTRY,
    TRAIT_REGISTRY,
    TRANSFORMATION_REGISTRY,
    CALENDAR_REGISTRY
)

# Импорт схем
from src.models.templates_schema import (
    BeliefTemplate,
    BiomeTemplate,
    BossesTemplate,
    CalendarTemplate,
    FactionTemplate, 
    LocationTemplate, 
    ResourceTemplate,
    TraitTemplate,
    TransformationRule,
    # Для фракций можно добавить шаблон, если он есть, или использовать Dict
)
#from src.naming import ContextualNamingService # Если нужно наполнять сервис нейминга

logger = logging.getLogger(__name__)

class TemplateLoader:
    def __init__(self, base_dir: str = "data/templates"):
        self.base_dir = Path(base_dir)

    def load_all(self):
        """Загружает всё в правильном порядке"""
        logger.info("Starting template loading...")
        self.load_resources()
        self.load_locations()
        # Фракции (шаблоны архетипов, например "fac_druids")
        self.load_factions() 
        self.load_biomes()
        self.load_bosses()
        self.load_transformations()
        self.load_traits()
        self.load_beliefs()
        #self.load_calendars()
        logger.info("Template loading finished.")

    def _load_yaml(self, filename: str) -> List[Dict[str, Any]]:
        path = self.base_dir / filename
        if not path.exists():
            logger.warning(f"File not found: {path}")
            return []
        
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        # Если YAML содержит один объект или список
        if isinstance(data, dict):
            return [data]
        return data if data else []

    def load_transformations(self):
        data = self._load_yaml("transformations.yaml")
        for item in data:
            try:
                rule = TransformationRule(**item)
                TRANSFORMATION_REGISTRY.register(rule.id, rule)
            except Exception as e:
                logger.error(f"Error loading transformation {item.get('id')}: {e}")

    def load_traits(self):
        data = self._load_yaml("traits.yaml")
        count = 0
        for item in data:
            try:
                tmpl = TraitTemplate(**item)
                TRAIT_REGISTRY.register(tmpl.id, tmpl)
                count += 1
            except Exception as e:
                logger.error(f"Failed to load belief template {item.get('id')}: {e}")
        logger.info(f"Loaded {count} belief templates.")

    def load_beliefs(self):
        data = self._load_yaml("belief.yaml")
        count = 0
        for item in data:
            try:
                tmpl = BeliefTemplate(**item)
                BELIEF_REGISTRY.register(tmpl.id, tmpl)
                count += 1
            except Exception as e:
                logger.error(f"Failed to load belief template {item.get('id')}: {e}")
        logger.info(f"Loaded {count} belief templates.")

    def load_resources(self):
        data = self._load_yaml("resources.yaml")
        count = 0
        for item in data:
            try:
                # Валидация через Pydantic
                tmpl = ResourceTemplate(**item)
                RESOURCE_REGISTRY.register(tmpl.id, tmpl)
                count += 1
            except Exception as e:
                logger.error(f"Failed to load resource {item.get('id')}: {e}")
        logger.info(f"Loaded {count} resources.")

    def load_locations(self):
        data = self._load_yaml("locations.yaml")
        count = 0
        for item in data:
            try:
                tmpl = LocationTemplate(**item)
                LOCATION_REGISTRY.register(tmpl.id, tmpl)
                count += 1
            except Exception as e:
                logger.error(f"Failed to load location {item.get('id')}: {e}")
        logger.info(f"Loaded {count} locations.")
    
    def load_factions(self):
        data = self._load_yaml("factions.yaml")
        for item in data:
            if 'id' in item:
                try:
                    # Сразу создаем модель при загрузке
                    tmpl = FactionTemplate(**item)
                    FACTION_REGISTRY.register(tmpl.id, tmpl) # Сохраняем объект, а не dict
                except Exception as e:
                    logger.error(f"Error loading faction {item.get('id')}: {e}")
    
    def load_bosses(self):
        data = self._load_yaml("bosses.yaml")
        for item in data:
            if 'id' in item:
                try:
                    # Сразу создаем модель при загрузке
                    tmpl = BossesTemplate(**item)
                    BOSSES_REGISTRY.register(tmpl.id, tmpl) # Сохраняем объект, а не dict
                except Exception as e:
                    logger.error(f"Error loading faction {item.get('id')}: {e}")

    def load_biomes(self):
        data = self._load_yaml("biomes.yaml")
        count = 0
        for item in data:
            try:
                tmpl = BiomeTemplate(**item)
                BIOME_REGISTRY.register(tmpl.id, tmpl)
                count += 1
            except Exception as e:
                logger.error(f"Failed to load biome {item.get('id')}: {e}")
        logger.info(f"Loaded {count} biomes.")

    # def load_calendars(self):
    #     data = self._load_yaml("calendar.yaml")
    #     count = 0
    #     for item in data:
    #         try:
    #             # Валидация через Pydantic
    #             calendar = CalendarTemplate(**item)
    #             CALENDAR_REGISTRY.register(calendar.id, calendar)
    #             count += 1
    #         except Exception as e:
    #             logger.error(f"Failed to load calendar {item.get('id')}: {e}")
        
    #     logger.info(f"Loaded {count} calendars.")

# Функции для загрузки NamingService (лексиконы)
def load_naming_data(naming_service, base_dir: str = "data/naming"):
    from src.naming import ContextualNamingService as naming
    naming_service: naming
    base_path = Path(base_dir)
    
    # 1. Биомные лексиконы
    with open(base_path / "biome_lexicons.yaml", "r", encoding="utf-8") as f:
        naming_service.biome_lexicons = yaml.safe_load(f) or {}

    # 2. Имена персонажей
    with open(base_path / "character_names.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
        naming_service.character_names_by_faction = data.get("by_faction", {})
        naming_service.character_names_by_creature_type = data.get("by_creature_type", {})
    
    # 3. Правила именования фракций
    with open(base_path / "faction_rules.yaml", "r", encoding="utf-8") as f:
        naming_service.faction_naming_rules = yaml.safe_load(f) or {}
        
    # 4. Шаблоны для сущностей (Locations, Items...)
    with open(base_path / "entity_templates.yaml", "r", encoding="utf-8") as f:
        naming_service.templates = yaml.safe_load(f) or {}

    # 5. Ресурсы
    with open(base_path / "resource_naming.yaml", "r", encoding="utf-8") as f:
        naming_service.resource_naming_map = yaml.safe_load(f) or {}

def load_all_templates():
    loader = TemplateLoader()
    loader.load_all()