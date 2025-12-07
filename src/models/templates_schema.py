from pydantic import BaseModel, Field, model_validator
from typing import Any, Dict, List, Set, Optional
from src.models.generation import Rarity

# --- Resource Template ---
class ResourceRarityOption(BaseModel):
    rarity: Rarity = Field(..., description="Уровень редкости (common, rare и т.д.)")
    weight: int = Field(..., ge=1, description="Вес для рандома. Чем больше, тем чаще встречается.")

class ResourceTemplate(BaseModel):
    id: str = Field(..., description="Уникальный ID ресурса (напр. 'res_wood')")
    name_key: str = Field(..., description="Читаемое название ресурса")
    renewable: bool = Field(..., description="Возобновляется ли ресурс со временем")
    icon: Optional[str] = Field(None, description="Emoji или путь к иконке")
    rarity_options: List[ResourceRarityOption] = Field(..., description="Список вариантов редкости для разных биомов")
    tags: Set[str] = Field(default_factory=set, description="Тэги для фильтрации (напр. 'construction', 'fuel')")

# --- 1. Вектор Культуры ---
class CultureVector(BaseModel):
    # === Числовые оси (Axes) ===
    # Делаем default=0, чтобы Trait мог содержать только aggression, например.
    aggression: int = Field(
        default=0, 
        ge=-20, le=20, 
        description="Агрессивность. Отрицательные значения — миролюбие."
    )
    magic_affinity: int = Field(
        default=0, 
        ge=-20, le=20, 
        description="Склонность к магии. Влияет на частоту магических событий."
    )
    collectivism: int = Field(
        default=0, 
        ge=-20, le=20, 
        description="Коллективизм. Высокий — ульи/империи, низкий — одиночки/анархисты."
    )
    
    # Можно добавить generic поле для будущих осей, которых нет в схеме
    # extra_axes: Dict[str, float] = Field(default_factory=dict)

    # === Категориальные множества (Sets) ===
    taboo: Set[str] = Field(
        default_factory=set,
        description="Набор запретных тем/действий (напр. 'cannibalism', 'technology')"
    )
    revered: Set[str] = Field(
        default_factory=set, 
        description="Набор почитаемых вещей (напр. 'ancestors', 'fire', 'gold')"
    )

    def get_numerical_axes(self) -> Dict[str, float]:
        """Возвращает словарь только с числовыми осями для итерации."""
        return {
            k: v for k, v in self.model_dump().items() 
            if isinstance(v, (int, float)) and k not in ['taboo', 'revered']
        }

    # === Операторы ===

    def __add__(self, other: 'CultureVector') -> 'CultureVector':
        """Сложение векторов (например, База + Вера + Черты)."""
        if not isinstance(other, CultureVector):
            return self

        new_data = {}
        
        # 1. Складываем числа
        my_axes = self.get_numerical_axes()
        other_axes = other.get_numerical_axes()
        all_keys = set(my_axes.keys()) | set(other_axes.keys())
        
        for k in all_keys:
            val = my_axes.get(k, 0.0) + other_axes.get(k, 0.0)
            # Можно добавить клемпинг (ограничение), например от -10 до 10, если нужно
            new_data[k] = val

        # 2. Объединяем множества
        new_data['taboo'] = self.taboo | other.taboo
        new_data['revered'] = self.revered | other.revered
        
        return CultureVector(**new_data)

    def __mul__(self, scalar: float) -> 'CultureVector':
        """Умножение на скаляр (например, влияние слабого лидера: culture * 0.5)."""
        new_data = {}
        
        # Умножаем только числа
        for k, v in self.get_numerical_axes().items():
            new_data[k] = v * scalar
            
        # Множества остаются без изменений (нельзя умножить табу на 0.5)
        new_data['taboo'] = self.taboo
        new_data['revered'] = self.revered
        
        return CultureVector(**new_data)

    def distance_to(self, other: 'CultureVector', weights: Optional[Dict[str, float]] = None) -> float:
        """
        Рассчитывает культурное напряжение (расстояние).
        Используем Манхэттенское расстояние (сумма модулей разностей), 
        так как оно интуитивнее для игровых параметров, чем Евклидово.
        """
        if weights is None:
            weights = {}
            
        tension = 0.0
        
        # 1. Числовые оси
        my_axes = self.get_numerical_axes()
        other_axes = other.get_numerical_axes()
        all_keys = set(my_axes.keys()) | set(other_axes.keys())

        for k in all_keys:
            v1 = my_axes.get(k, 0)
            v2 = other_axes.get(k, 0)
            diff = abs(v1 - v2)
            
            # Если разница незначительна (например < 2), напряжение не растет
            # Это аналог вашего "if abs > 5", но более плавный
            if diff > 2.0:
                # Вес по умолчанию 1.0, для aggression можно передать другой
                w = weights.get(k, 0.1) 
                tension += (diff - 2.0) * w

        # 2. Идеологические конфликты (Sets)
        # Табу одной стороны vs Святыни другой
        conflict_set_1 = self.taboo & other.revered
        conflict_set_2 = other.taboo & self.revered
        
        # Каждое пересечение дает большой скачок напряжения
        tension += (len(conflict_set_1) + len(conflict_set_2)) * 1.5
        
        # Общие ценности снижают напряжение
        shared_values = self.revered & other.revered
        tension -= len(shared_values) * 0.5

        return max(0.0, tension)
    
# --- 2. Шаблон Веры (НОВЫЙ) ---
class BeliefVariation(BaseModel):
    """Подвид веры (ересь, секта, ортодоксы)"""
    name: str = Field(..., description="Название вариации, напр. 'Ортодоксальное учение'")
    modifiers: CultureVector = Field(..., description="Как эта ересь меняет базовые ценности веры")

class BeliefTemplate(BaseModel):
    id: str = Field(..., description="ID шаблона веры")
    name: str = Field(..., description="Название архетипа (напр. 'Воинственный культ')")
    naming_style: str = Field(..., description="Стиль нейминга для генератора ('martial', 'nature', 'arcane')")
    
    preferred_roles: List[str] = Field(
        default_factory=list, 
        description="Роли фракций, склонных к этой вере (напр. 'military', 'bandits')"
    ) 
    
    base_modifiers: CultureVector = Field(
        default_factory=CultureVector,
        description="Базовые ценности, которые эта вера прививает последователям"
    )
    
    variations: List[BeliefVariation] = Field(
        default_factory=list,
        description="Список возможных ответвлений или сект"
    )

# --- 3. Шаблон Фракции ---
class FactionTemplate(BaseModel):
    id: str = Field(..., description="ID шаблона фракции")
    creature_type: str = Field(..., description="Тип существ (humanoid, beast, undead, spirit)")
    role: str = Field(..., description="Социальная роль (bandits, nobility, commoners)")
    icon: Optional[str] = None 
    tags: Set[str] = Field(default_factory=set)
    
    culture: CultureVector = Field(
        default_factory=CultureVector,
        description="Базовая культура вида (например, Орки агрессивны сами по себе)"
    )
    
    default_belief_id: Optional[str] = Field(
        None, 
        description="Если задано, фракция всегда стартует с этой религией"
    )

# Исправили BossesTemplate с учетом предыдущего диалога про allowed_biomes
class BossesTemplate(FactionTemplate):
    name_template: str = Field(..., description="Шаблон имени, напр. 'Дракон {name}' или 'Ужас {adj} глубин'")
    allowed_biomes: List[str] = Field(
        default_factory=list, 
        description="Список ID биомов, где может появиться этот босс. Если пусто - везде."
    )

class TraitTemplate(BaseModel):
    id: str = Field(..., description="ID черты, напр. 'trait_paranoid'")
    name: str = Field(..., description="Отображаемое имя, напр. 'Параноик'")
    modifiers: CultureVector = Field(
        ..., 
        description="Влияние на культуру. Здесь значения могут быть ОТРИЦАТЕЛЬНЫМИ (напр. aggression: -5)"
    )
    conflict_tags: Set[str] = Field(
        default_factory=set, 
        description="С какими тэгами других черт несовместимо (напр. 'trusting')"
    )

# --- Faction Template (вложенный в биом) ---
class FactionSpawnRule(BaseModel):
    definition_id: str = Field(..., description="ID шаблона фракции для спавна")
    role: str = Field(..., description="Роль, с которой она появится (может перезаписывать шаблон)")
    weight: float = Field(1.0, ge=0.0, description="Шанс появления относительно других правил")
    override_tags: Set[str] = Field(default_factory=set, description="Дополнительные тэги, присваиваемые при спавне")

# --- Location Template ---
class LocationTemplate(BaseModel):
    id: str 
    name: str       
    capacity: int = Field(..., ge=1, description="Сколько сущностей (фракций/ресурсов) вмещает")
    limits: Dict[str, int] = Field(
        default_factory=dict, 
        description="Лимиты по типам. {'Resource': 2, 'Faction': 1}"
    )
    icon: Optional[str] = None 
    tags: Set[str] = Field(default_factory=set)

    @property
    def resource_capacity(self): return self.limits.get("Resource", 0)
    
    @property
    def faction_capacity(self): return self.limits.get("Faction", 0)

# --- Biome Template ---
class BiomeTemplate(BaseModel):
    id: str         
    name: str       
    capacity: int = Field(..., ge=1)
    tags: Set[str] = Field(default_factory=set)
    icon: Optional[str] = None 
    allowed_locations: List[str] = Field(..., description="ID локаций, допустимых в этом биоме")
    forbidden_neighbors: Set[str] = Field(default_factory=set, description="Биомы, которые не могут быть рядом")
    available_resources: List[str] = Field(..., description="ID ресурсов, появляющихся здесь")
    factions: List[FactionSpawnRule] = Field(..., description="Правила спавна населения")

class TransformationRule(BaseModel):
    id: str 
    requires_tag: str = Field(..., description="Тэг, наличие которого запускает трансформацию (напр. 'corruption')")
    needs_faction: bool = Field(False, description="Нужен ли контроль фракции над локацией")
    min_age_empty: Optional[int] = Field(None, description="Если указано, локация должна пустовать N эпох")
    target_def: str = Field(..., description="ID новой локации, в которую превратится старая")
    chance: float = Field(..., ge=0.0, le=1.0, description="Вероятность срабатывания (0.0 - 1.0)")
    verb: str = Field(..., description="Глагол для логов ('разрушилась', 'заросла')")
    narrative: str = Field(..., description="Текст события для хроники")

# --- Calendar Template ---

class Season(BaseModel):
    # ID делаем Optional, так как в YAML его нет внутри блока
    id: Optional[str] = Field(description='example: season_fire', default=None) 
    name: str = Field(description='example: Season of the Fire')
    description: str = Field(description='lore decription', default='')
    modifiers: Dict[str, float] = Field(description= 'example: {"conflict_weight": 0.5}', default_factory=dict)

class CalendarTemplate(BaseModel):
    id: Optional[str] = None
    name: str
    epochs_per_year: int
    
    # ИСПРАВЛЕНИЕ: Убрали alias="season_rotation", так как в YAML у вас season_order
    season_order: List[str] 
    
    seasons: Dict[str, Season]

    @model_validator(mode='after')
    def fill_missing_ids(self):
        """
        Автоматически проставляет ID, используя ключи словаря,
        если они не указаны явно в YAML.
        """
        # 1. Заполняем ID сезонов из ключей словаря (spring, summer...)
        if self.seasons:
            for key, season_obj in self.seasons.items():
                if not season_obj.id:
                    season_obj.id = key
        
        return self

    def get_season_by_age(self, age: int) -> Optional[Season]:
        if not self.season_order:
            return None
        # age - 1, т.к. эпохи обычно с 1, а массив с 0
        idx = (age - 1) % len(self.season_order)
        season_id = self.season_order[idx]
        return self.seasons.get(season_id)

    @model_validator(mode='before')
    @classmethod
    def prepare_data(cls, data: Any) -> Any:
        """
        Инжектим ID из ключей словаря, если они не заданы явно.
        """
        if isinstance(data, dict):
            # Если поле id не передано, но мы знаем, что оно должно быть
            # (обычно оно проставляется в Loader, но на всякий случай)
            if 'seasons' in data and isinstance(data['seasons'], dict):
                for key, val in data['seasons'].items():
                    if isinstance(val, dict) and 'id' not in val:
                        val['id'] = key
        return data