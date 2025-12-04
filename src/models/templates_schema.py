from pydantic import BaseModel, Field
from typing import Dict, List, Set, Optional
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
    """
    Описывает культурные/психологические параметры сущности или модификаторы.
    Диапазон обычно от -10 до 10.
    """
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
    # Используем Set для быстрого пересечения множеств
    taboo: Set[str] = Field(
        default_factory=set, 
        description="Набор запретных тем/действий (напр. 'cannibalism', 'technology')"
    )
    revered: Set[str] = Field(
        default_factory=set, 
        description="Набор почитаемых вещей (напр. 'ancestors', 'fire', 'gold')"
    )

    def __add__(self, other: 'CultureVector') -> 'CultureVector':
        """
        Магический метод сложения двух культур.
        Числа складываются, множества (Sets) объединяются.
        """
        if not isinstance(other, CultureVector):
            return self

        return CultureVector(
            aggression=self.aggression + other.aggression,
            magic_affinity=self.magic_affinity + other.magic_affinity,
            collectivism=self.collectivism + other.collectivism,
            taboo=self.taboo | other.taboo,       
            revered=self.revered | other.revered  
        )

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