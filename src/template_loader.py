import yaml
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

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
    def __init__(self):
        # Слои: Base -> Custom
        self.layers = [Path("data"), Path("data/custom")]

    def _load_merged_yaml(self, rel_path: str, is_dict: bool = False) -> Any:
        """
        Читает файл из всех слоев и объединяет результаты.
        Если is_dict=True, делает dict.update() (Custom перетирает ключи Base).
        Если is_dict=False (список), делает list append (Custom добавляет элементы).
        """
        merged_dict = {}
        merged_list = []
        
        found_any = False

        for layer in self.layers:
            path = layer / rel_path
            if not path.exists():
                continue
            
            found_any = True
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    
                if not data: continue

                if is_dict:
                    if isinstance(data, dict):
                        merged_dict.update(data)
                else:
                    if isinstance(data, list):
                        # Для списков: если ID совпадает, Custom должен заменить Base?
                        # В простом варианте - просто добавляем, а Registry при регистрации перезапишет.
                        merged_list.extend(data)
                    elif isinstance(data, dict):
                        merged_list.append(data)
                        
            except Exception as e:
                logger.error(f"Error loading layer {path}: {e}")

        if is_dict:
            return merged_dict
        return merged_list

    def load_all(self):
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

    def load_transformations(self):
        data = self._load_merged_yaml("templates/transformations.yaml")
        for item in data:
            try:
                rule = TransformationRule(**item)
                TRANSFORMATION_REGISTRY.register(rule.id, rule)
            except Exception as e:
                logger.error(f"Error loading transformation {item.get('id')}: {e}")

    def load_traits(self):
        data = self._load_merged_yaml("templates/traits.yaml")
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
        data = self._load_merged_yaml("templates/belief.yaml")
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
        data = self._load_merged_yaml("templates/resources.yaml")
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
        data = self._load_merged_yaml("templates/locations.yaml")
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
        data = self._load_merged_yaml("templates/factions.yaml")
        for item in data:
            if 'id' in item:
                try:
                    # Сразу создаем модель при загрузке
                    tmpl = FactionTemplate(**item)
                    FACTION_REGISTRY.register(tmpl.id, tmpl) # Сохраняем объект, а не dict
                except Exception as e:
                    logger.error(f"Error loading faction {item.get('id')}: {e}")
    
    def load_bosses(self):
        data = self._load_merged_yaml("templates/bosses.yaml")
        for item in data:
            if 'id' in item:
                try:
                    # Сразу создаем модель при загрузке
                    tmpl = BossesTemplate(**item)
                    BOSSES_REGISTRY.register(tmpl.id, tmpl) # Сохраняем объект, а не dict
                except Exception as e:
                    logger.error(f"Error loading faction {item.get('id')}: {e}")

    def load_biomes(self):
        # Используем путь относительно корня data/
        data = self._load_merged_yaml("templates/biomes.yaml", is_dict=False)
        for item in data:
            try:
                tmpl = BiomeTemplate(**item)
                BIOME_REGISTRY.register(tmpl.id, tmpl)
            except Exception as e:
                logger.error(f"Error biome {item.get('id')}: {e}")

    # def load_calendars(self):
    #     data = self._load_merged_yaml("templates/calendar.yaml")
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
def load_naming_data(naming_service, base_dirs: Optional[List[Path]] = None):
    """
    Загружает лексиконы в сервис нейминга, учитывая слои.
    naming_service: экземпляр ContextualNamingService
    """
    if base_dirs is None:
        base_dirs = [Path("data"), Path("data/custom")]
        
    def _merge_dicts(rel_path):
        final = {}
        for root in base_dirs:
            p = root / rel_path
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    d = yaml.safe_load(f) or {}
                    final.update(d)
        return final

    # 1. Biome Lexicons
    naming_service.biome_lexicons = _merge_dicts("naming/biome_lexicons.yaml")
    
    # 2. Faction Rules
    naming_service.faction_naming_rules = _merge_dicts("naming/faction_rules.yaml")

    # 3. Entity Templates
    naming_service.templates = _merge_dicts("naming/entity_templates.yaml")

    # 4. Resources
    naming_service.resource_naming_map = _merge_dicts("naming/resource_naming.yaml")

    # 5. Characters (Особый случай - глубокий мерж или полная замена?)
    # Для простоты делаем update верхнего уровня (by_faction, by_creature_type)
    chars_data = _merge_dicts("naming/character_names.yaml")
    naming_service.character_names_by_faction = chars_data.get("by_faction", {})
    naming_service.character_names_by_creature_type = chars_data.get("by_creature_type", {})

def load_all_templates():
    loader = TemplateLoader()
    loader.load_all()