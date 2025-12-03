import random
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List

# Biome убрали, так как теперь это просто строка
from src.models.generation import EntityType, Rarity
from src.template_loader import load_naming_data

class NamingService(ABC):
    # Словарь теперь: { "biome_id": { "adjectives": [...], ... } }
    biome_lexicons: Dict[str, Any] 
    
    @abstractmethod
    def generate_name(self, entity_type: EntityType, context: Optional[dict] = None) -> str:
        pass

    
class ContextualNamingService(NamingService):
    def __init__(self):
        self.templates = None
        self.character_names_by_faction = None
        self.character_names_by_creature_type = None
        self.faction_naming_rules = None
        self.resource_naming_map = None
        load_naming_data(self)

        # Создаем минимальный fallback-лексикон на случай, если файлы пусты или ID кривые
        self._default_lexicon = {
            "adjectives": ["Древний", "Тайный", "Забытый"],
            "nouns": ["Место", "Земля", "Край"],
            "symbols": ["Тьмы", "Света", "Времени"],
            "deity_prefixes": ["Дух", "Тень"],
        }

    def _generate_procedural_name(self, style: str = "fantasy") -> str:
        """Простая генерация по слогам C-V-C"""
        vowels = "aeiouy"
        consonants = "bcdfghjklmnpqrstvwxz"
        
        if style == "orc" or style == "beast":
            consonants = "zgkrstbh"
            vowels = "auo"
        elif style == "elf" or style == "spirit":
            consonants = "lmnrstvwy"
            vowels = "aeio"

        # Структура: C-V-C-V-C (3-5 букв)
        length = random.randint(2, 3) # количество слогов
        name = ""
        for i in range(length):
            if i == 0:
                name += random.choice(consonants).upper()
            else:
                name += random.choice(consonants)
            name += random.choice(vowels)
            
        # Иногда добавляем закрывающую согласную
        if random.random() < 0.5:
             name += random.choice(consonants)
             
        return name

    def _get_lexicon(self, biome_id: Optional[str]) -> Dict[str, List[str]]:
        """Безопасное получение лексикона. Если ID неверен, возвращает дефолтный."""
        if biome_id and biome_id in self.biome_lexicons:
            return self.biome_lexicons[biome_id]
        
        # Если биом не найден (или None), берем первый доступный из загруженных
        if self.biome_lexicons:
            # Возвращаем значения первого ключа (для стабильности можно сортировать, но это оверхед)
            return next(iter(self.biome_lexicons.values()))
        
        return self._default_lexicon

    def generate_name(self, entity_type: EntityType, context: Optional[Dict[str, Any]] = None) -> str:
        if context is None:
            context = {}

        # Теперь мы ожидаем строку ID, а не Enum
        # Поддерживаем и старый ключ "biome", и новый "biome_id"
        biome_id = context.get("biome_id") or context.get("biome")
        if isinstance(biome_id, str) is False:
             # Если вдруг прилетел Enum или None, пытаемся привести к строке или игнорим
             biome_id = str(biome_id) if biome_id else None

        lexicon = self._get_lexicon(biome_id)
        
        # Шаблоны тоже хранятся по строковым ключам
        # structure: templates[EntityType][BiomeID] -> List[str]
        type_templates = self.templates.get(entity_type, {})
        
        # Пытаемся найти шаблоны для конкретного биома, иначе ищем "default" или берем fallback
        templates_list = type_templates.get(biome_id)
        if not templates_list:
            templates_list = type_templates.get("default", ["{base}"])

        # Подготовка переменных для подстановки
        variables = {
            "adj": random.choice(lexicon.get("adjectives", ["Strange"])),
            "noun": random.choice(lexicon.get("nouns", ["Place"])),
            "symbol": random.choice(lexicon.get("symbols", ["Thing"])),
            "deity_prefix": random.choice(lexicon.get("deity_prefixes", ["Great"])),
            "deity": context.get("deity", "Неизвестного"),
            "base": context.get("base_name", "Нечто") # base_name часто нужен для ресурсов
        }

        # === 1. CHARACTER ===
        if entity_type == EntityType.CHARACTER:
            faction = context.get("faction")
            creature_type = context.get("creature_type", "humanoid")
            
            names = []
            if faction and faction in self.character_names_by_faction:
                names = self.character_names_by_faction[faction]
            elif creature_type in self.character_names_by_creature_type:
                names = self.character_names_by_creature_type[creature_type]
            
            # ШАНС НА ПРОЦЕДУРНОЕ ИМЯ (20%) или если список пуст
            if not names or random.random() < 0.2:
                # Определяем стиль по типу существа
                style = "fantasy"
                if creature_type in ["beast", "undead"]: style = "orc"
                if creature_type in ["spirit", "fey"]: style = "elf"
                return self._generate_procedural_name(style)

            return random.choice(names)
        
        # === 2. ITEM ===
        # if entity_type == EntityType.ITEM:
        #     type_templates
        #     return 'Легендарный предмет'
        
        # === 3. FACTION ===
        if entity_type == EntityType.FACTION:
            creature_type = context.get("creature_type", "humanoid")
            role = context.get("role", "default")

            # Выбираем правила
            rules = self.faction_naming_rules.get(creature_type)
            if not rules:
                rules = self.faction_naming_rules.get("default", {})

            fac_templates = rules.get(role)
            if not fac_templates:
                fac_templates = rules.get("default", ["{adj} {noun}"])

            template = random.choice(fac_templates)
            try:
                name = template.format(**variables)
            except KeyError:
                name = f"{variables['adj']} {variables['noun']}"
            return name

        # === 4. RESOURCE ===
        if entity_type == EntityType.RESOURCE:
            base_type = context.get("base_resource", "resource") # например "wood"
            rarity = context.get("rarity", Rarity.COMMON) # Enum Rarity остается

            naming_options = None
            
            # self.resource_naming_map: Dict[str_res_id, Dict[str_biome_id, Dict[Rarity, List[str]]]]
            if base_type in self.resource_naming_map:
                res_map = self.resource_naming_map[base_type]
                
                # 1. Точное совпадение биома
                if biome_id and biome_id in res_map:
                    if rarity in res_map[biome_id]:
                        naming_options = res_map[biome_id][rarity]
                
                # 2. Fallback на "default" или None (смотря как загрузчик сохранил глобальные варианты)
                # Проверяем оба варианта ключа
                if not naming_options:
                    for fallback_key in [None, "default", "global"]:
                        if fallback_key in res_map:
                            if rarity in res_map[fallback_key]:
                                naming_options = res_map[fallback_key][rarity]
                                break

            if naming_options:
                name = random.choice(naming_options)
            else:
                # Генеративный фолбэк
                base_fallback = base_type.capitalize()
                rarity_labels = {
                    Rarity.COMMON: "",
                    Rarity.UNCOMMON: "Необычный",
                    Rarity.RARE: "Редкий",
                    Rarity.EPIC: "Эпический"
                }
                adj = rarity_labels.get(rarity, "")
                name = f"{adj} {base_fallback}".strip()

            return name
        
        # === 5. BELIEF (НОВАЯ СЕКЦИЯ) ===
        if entity_type == EntityType.BELIEF:
            # Получаем стиль из контекста (передан из BeliefSystem)
            # Если стиль не передан, пытаемся угадать или берем дефолт
            style = context.get("naming_style", "default")
            
            # Получаем шаблоны для конкретного стиля из entity_templates.yaml
            # Структура: templates[BELIEF][style] -> List[str]
            belief_templates = self.templates.get(EntityType.BELIEF, {})
            style_options = belief_templates.get(style)
            
            if not style_options:
                style_options = belief_templates.get("default", ["Cult of {noun}"])
            
            template = random.choice(style_options)
            
            # Для религий часто нужны специфические переменные
            # Например, имя божества
            local_vars = variables.copy()
            if "{deity}" in template and "deity" not in context:
                 # Генерируем имя божества "на лету", если его нет
                 local_vars["deity"] = self._generate_procedural_name(style="fantasy")

            try:
                name = template.format(**local_vars)
            except KeyError:
                name = f"Вера {local_vars['noun']}"
            
            return name

        # === DEFAULT GENERIC ===
        if not templates_list:
             return f"{variables['adj']} {variables['noun']}"

        template = random.choice(templates_list)
        try:
            name = template.format(**variables)
        except KeyError as e:
            # Fallback если шаблон кривой
            name = f"{variables.get('adj', '')} {variables.get('noun', 'Место')}".strip()

        return name