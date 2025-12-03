from pathlib import Path
from typing import List, Dict, Any, Literal
import yaml

# Импортируем все новые схемы
from src.models.naming_schemas import (
    BiomeLexiconEntry, 
    FactionNamingEntry, 
    ResourceNamingEntry, 
    EntityTemplateEntry, 
    CharacterNamesConfig
)
from src.models.templates_schema import (
    BiomeTemplate, FactionTemplate, LocationTemplate, 
    ResourceTemplate, BossesTemplate, TransformationRule
)

class TemplateEditorService:
    def __init__(self, base_dir: Path = Path("data/")):
        self.base_dir = base_dir
        
        # Format: "slug": ("filename", ModelClass, is_dict_structure?)
        # is_dict_structure=True означает, что YAML выглядит как {"key": {...}}, 
        # и мы преобразуем его в [{"id": "key", ...}] для редактора.
        
        self.config_map = {
            # --- Основные шаблоны ---
            "biomes": ("templates/biomes.yaml", BiomeTemplate, False),
            "factions": ("templates/factions.yaml", FactionTemplate, False),
            "locations": ("templates/locations.yaml", LocationTemplate, False),
            "resources": ("templates/resources.yaml", ResourceTemplate, False),
            "bosses": ("templates/bosses.yaml", BossesTemplate, False),
            "transformations": ("templates/transformations.yaml", TransformationRule, False),
            
            # --- Нейминг (data/naming/) ---
            "naming_biomes": ("naming/biome_lexicons.yaml", BiomeLexiconEntry, True),
            "naming_factions": ("naming/faction_rules.yaml", FactionNamingEntry, True),
            "naming_resources": ("naming/resource_naming.yaml", ResourceNamingEntry, True),
            "naming_entities": ("naming/entity_templates.yaml", EntityTemplateEntry, True),
            
            # Особый случай: character_names - это один большой объект, а не словарь объектов
            # Мы будем читать его как список из 1 элемента
            "naming_characters": ("naming/character_names.yaml", CharacterNamesConfig, False),
        }

    def _get_config_entry(self, config_type: str):
        if config_type not in self.config_map:
            raise ValueError(f"Unknown config type: {config_type}")
        
        entry = self.config_map[config_type]
        filename = entry[0]
        model_class = entry[1]
        is_dict = entry[2] if len(entry) > 2 else False
        
        return filename, model_class, is_dict

    def get_available_configs(self) -> List[str]:
        return list(self.config_map.keys())

    def get_schema(self, config_type: str) -> Dict[str, Any]:
        _, model_class, _ = self._get_config_entry(config_type)
        return {
            "type": "array",
            "title": f"List of {config_type}",
            "items": model_class.model_json_schema()
        }

    def get_data(self, config_type: str) -> List[Dict[str, Any]]:
        filename, _, is_dict = self._get_config_entry(config_type)
        
        # base_dir у нас "data/templates", а файл может быть "../naming/file.yaml"
        # resolve() поможет построить правильный путь
        path = (self.base_dir / filename).resolve()
        
        if not path.exists():
            return []
            
        with open(path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}

        # 1. Если это словарь {"key": val}, а мы хотим список [{id: key, ...val}]
        if is_dict and isinstance(raw_data, dict):
            converted_list = []
            for key, value in raw_data.items():
                item = value.copy() if isinstance(value, dict) else {"value": value}
                item['id'] = key
                converted_list.append(item)
            return converted_list
        
        # 2. Если файл возвращает dict, но это НЕ словарь объектов (как character_names),
        # а просто один конфиг-объект, мы оборачиваем его в список [obj]
        if isinstance(raw_data, dict) and not is_dict:
            return [raw_data]

        # 3. Обычный список
        return raw_data if isinstance(raw_data, list) else []

    def save_data(self, config_type: str, data: List[Dict[str, Any]]):
        filename, model_class, is_dict = self._get_config_entry(config_type)
        
        # Валидация
        validated_list = [model_class.model_validate(item).model_dump(mode='json') for item in data]
        
        path = (self.base_dir / filename).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data_to_save = validated_list

        # Конвертация обратно: List -> Dict
        if is_dict:
            data_to_save = {}
            for item in validated_list:
                # Если в схеме есть 'id', используем его как ключ
                if 'id' in item:
                    key = item.pop('id')
                    data_to_save[key] = item
                else:
                    # Fallback на случай странных схем
                    pass

        # Конвертация обратно: List[OneObj] -> OneObj (для character_names)
        if not is_dict and len(validated_list) == 1 and config_type == "naming_characters":
             data_to_save = validated_list[0]
             if 'id' in data_to_save: 
                 del data_to_save['id'] # удаляем служебный id

        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data_to_save, f, allow_unicode=True, sort_keys=False)

    def _get_file_path(self, config_file: str, config_type: str) -> Path:
        if config_type not in self.config_map:
            raise ValueError(f"Unknown config type: {config_type}")
        return self.base_dir / f"{config_type}" / f"{config_file}.yaml"

    def append_template(
            self, config_file: str, 
            config_type: Literal['templates'], 
            new_item: Dict[str, Any]
        ):
        """
        Безопасно добавляет один новый шаблон.
        1. Валидирует через Pydantic.
        2. Проверяет уникальность ID.
        3. Дописывает в файл.
        """
        model_class = self.config_map.get(config_file)
        if not model_class:
            raise ValueError(f"Unknown config type: {config_file}")

        # 1. Валидация структуры
        try:
            validated_obj = model_class(**new_item)
            item_dict = validated_obj.model_dump(mode="json") # Превращаем в чистый dict (без сетов)
        except Exception as e:
            raise ValueError(f"Validation failed for {config_file}: {e}")

        # 2. Чтение существующих и проверка дубликатов
        current_data = self.get_data(config_file)
        
        # Проверка на дубликат ID
        if any(item.get("id") == item_dict["id"] for item in current_data):
            raise ValueError(f"Template with id '{item_dict['id']}' already exists in {config_type}")

        current_data.append(item_dict)

        # 3. Сохранение (перезапись файла с новым элементом)
        file_path = self._get_file_path(config_file=config_file, config_type=config_type)
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(current_data, f, allow_unicode=True, sort_keys=False)
            
        return item_dict["id"]