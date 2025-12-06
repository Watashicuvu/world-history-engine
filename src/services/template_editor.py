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
    BeliefTemplate, BiomeTemplate, FactionTemplate, LocationTemplate, 
    ResourceTemplate, BossesTemplate, TraitTemplate, TransformationRule
)

from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import yaml
import logging

# Импорты всех схем
from src.models.naming_schemas import (
    BiomeLexiconEntry, FactionNamingEntry, ResourceNamingEntry, 
    EntityTemplateEntry, CharacterNamesConfig
)
from src.models.templates_schema import (
    BeliefTemplate, BiomeTemplate, FactionTemplate, LocationTemplate, 
    ResourceTemplate, BossesTemplate, TraitTemplate, TransformationRule
)

logger = logging.getLogger(__name__)

class TemplateEditorService:
    def __init__(self, read_roots: Optional[List[str]] = None, write_root: str = "data/custom"):
        """
        read_roots: список папок для чтения (по порядку приоритета: Core -> Custom)
        write_root: папка, куда сохраняются ВСЕ изменения (Custom)
        """
        if read_roots is None:
            # Сначала читаем базу, потом кастом (чтобы кастом перекрывал при мерже)
            read_roots = ["data/templates", "data/naming"] # ЭТО НЕПРАВИЛЬНО ДЛЯ НОВОЙ ЛОГИКИ
            # Правильная логика для Relative Paths:
            read_roots = ["data", "data/custom"]
            
        self.read_dirs = [Path(d) for d in read_roots]
        self.write_dir = Path(write_root)
        
        # Format: "slug": ("relative/path.yaml", ModelClass, is_dict_structure)
        # is_dict_structure=True означает, что в YAML это Dict {id: data}, а в API это List [{id:..., ...data}]
        self.config_map = {
            # --- Игровые шаблоны (обычно в templates/) ---
            "biomes": ("templates/biomes.yaml", BiomeTemplate, False),
            "locations": ("templates/locations.yaml", LocationTemplate, False),
            "factions": ("templates/factions.yaml", FactionTemplate, False),
            "resources": ("templates/resources.yaml", ResourceTemplate, False),
            "bosses": ("templates/bosses.yaml", BossesTemplate, False),
            "belief": ("templates/belief.yaml", BeliefTemplate, False),
            "trait": ("templates/traits.yaml", TraitTemplate, False),
            "transformations": ("templates/transformations.yaml", TransformationRule, False),
            
            # --- Нейминг (обычно в naming/) ---
            "naming_biomes": ("naming/biome_lexicons.yaml", BiomeLexiconEntry, True),
            "naming_factions": ("naming/faction_rules.yaml", FactionNamingEntry, True),
            "naming_resources": ("naming/resource_naming.yaml", ResourceNamingEntry, True),
            "naming_entities": ("naming/entity_templates.yaml", EntityTemplateEntry, True),
            
            # Особый случай: character_names (один большой объект)
            "naming_characters": ("naming/character_names.yaml", CharacterNamesConfig, False),
        }

    def save_data(self, config_type: str, data: List[Dict[str, Any]]) -> None:
        """
        Сохраняет список данных в файл слоя Custom.
        Автоматически преобразует List -> Dict, если того требует формат файла.
        
        ВНИМАНИЕ: Этот метод полностью перезаписывает файл в папке write_dir
        теми данными, которые вы передали.
        """
        rel_filename, model_class, is_dict = self._get_config_entry(config_type)
        
        # 1. Валидация данных через Pydantic перед сохранением
        # Это гарантирует, что мы не запишем битый YAML
        validated_items = []
        try:
            for item in data:
                # model_validate проверяет типы
                # model_dump(mode='json') готовит данные для сериализации (преобразует set в list и т.д.)
                obj = model_class.model_validate(item)
                validated_items.append(obj.model_dump(mode='json'))
        except Exception as e:
            raise ValueError(f"Validation failed for '{config_type}': {e}")

        # 2. Подготовка структуры данных для записи (List vs Dict)
        data_to_save = None

        if is_dict:
            # Превращаем список обратно в словарь: [{"id": "k", "val": 1}] -> {"k": {"val": 1}}
            data_to_save = {}
            for item in validated_items:
                if 'id' not in item:
                    # Для dict-структур ID обязателен, так как он становится ключом
                    continue 
                
                key = item.pop('id')
                
                # Эвристика для упрощения: 
                # Если объект состоял только из ID и Value (как в простых маппингах),
                # сохраняем его как значение, а не как вложенный объект.
                if len(item) == 1 and 'value' in item:
                    data_to_save[key] = item['value']
                else:
                    data_to_save[key] = item

        elif config_type == 'naming_characters':
            # Особый случай (Singleton): сохраняем первый элемент списка как корень файла
            if validated_items:
                data_to_save = validated_items[0]
                # Убираем служебный ID, если он есть
                if 'id' in data_to_save:
                    del data_to_save['id']
            else:
                data_to_save = {}
        
        else:
            # Стандартный список (List): сохраняем как есть
            data_to_save = validated_items

        # 3. Запись в файл (ВСЕГДА в папку Custom)
        target_path = self.write_dir / rel_filename
        
        # Создаем вложенные папки, если их нет (например data/custom/naming/)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        with open(target_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                data_to_save, 
                f, 
                allow_unicode=True, 
                sort_keys=False, 
                default_flow_style=False
            )

    def _get_config_entry(self, config_type: str):
        if config_type not in self.config_map:
            raise ValueError(f"Unknown config type: {config_type}")
        return self.config_map[config_type]

    def get_data(self, config_type: str) -> List[Dict[str, Any]]:
        """
        Возвращает объединенные данные (Core + Custom).
        Всегда возвращает список объектов с полем 'id'.
        """
        rel_filename, _, is_dict = self._get_config_entry(config_type)
        
        merged_items = {} # id -> dict (для дедупликации)
        
        # Проходим по слоям: Base -> Custom. Custom перезаписывает Base по ID.
        for root in self.read_dirs:
            path = root / rel_filename
            if not path.exists():
                continue
                
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
                
            # Нормализация данных текущего слоя в список [{id:..., ...}]
            layer_items = []
            if is_dict and isinstance(raw, dict):
                for k, v in raw.items():
                    item = v.copy() if isinstance(v, dict) else {"value": v}
                    item['id'] = k
                    layer_items.append(item)
            elif isinstance(raw, list):
                layer_items = raw
            elif isinstance(raw, dict) and not is_dict: # Single object (char names)
                # Для синглтонов ID обычно фиктивный или один
                item = raw.copy()
                item['id'] = 'singleton' 
                layer_items = [item]

            # Мерж в общий список
            for item in layer_items:
                if 'id' in item:
                    merged_items[item['id']] = item
                    
        return list(merged_items.values())

    def get_available_configs(self) -> List[str]:
        return list(self.config_map.keys())

    def get_schema(self, config_type: str) -> Dict[str, Any]:
        _, model_class, _ = self._get_config_entry(config_type)
        return {
            "type": "array",
            "title": f"List of {config_type}",
            "items": model_class.model_json_schema()
        }

    def append_template(self, config_type: str, new_item: Dict[str, Any]) -> str:
        """
        Добавляет или обновляет шаблон в слое Custom.
        """
        rel_filename, model_class, is_dict = self._get_config_entry(config_type)
        
        # 1. Валидация Pydantic
        try:
            # Для валидации нужен чистый объект без лишних полей
            # Если это именованный конфиг, id сидит в new_item['id']
            obj = model_class(**new_item)
            item_dict = obj.model_dump(mode='json')
        except Exception as e:
            raise ValueError(f"Validation failed for {config_type}: {e}")

        # ID обязателен для сохранения
        obj_id = item_dict.get('id')
        if not obj_id and not (config_type == 'naming_characters'):
             # Если ID не пришел (а он должен быть в схеме), пробуем сгенерировать или ругаемся
             raise ValueError("Object must have an 'id' field")

        # 2. Читаем ТОЛЬКО файл Custom (мы редактируем только его)
        custom_path = self.write_dir / rel_filename
        custom_data_raw = {}
        
        if custom_path.exists():
            with open(custom_path, "r", encoding="utf-8") as f:
                custom_data_raw = yaml.safe_load(f) or {}

        # 3. Модификация данных в памяти (в зависимости от структуры)
        if is_dict:
            # Структура Dict: {"orc": {...}}
            if not isinstance(custom_data_raw, dict): custom_data_raw = {}
            
            # Подготовка значения (удаляем ID, так как он будет ключом)
            val_to_save = item_dict.copy()
            del val_to_save['id']
            
            # Если остался только value (для простых маппингов), упрощаем
            if len(val_to_save) == 1 and 'value' in val_to_save:
                val_to_save = val_to_save['value']
                
            custom_data_raw[obj_id] = val_to_save
            
        elif config_type == 'naming_characters':
            # Структура Singleton
            # Просто перезаписываем весь объект кастомными данными
             if 'id' in item_dict: del item_dict['id']
             custom_data_raw = item_dict
             
        else:
            # Структура List: [- id: orc, ...]
            if not isinstance(custom_data_raw, list): custom_data_raw = []
            
            # Удаляем старую версию если есть (update)
            custom_data_raw = [x for x in custom_data_raw if x.get('id') != obj_id]
            custom_data_raw.append(item_dict)

        # 4. Сохранение
        custom_path.parent.mkdir(parents=True, exist_ok=True)
        with open(custom_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(custom_data_raw, f, allow_unicode=True, sort_keys=False)
            
        return obj_id or "success"  