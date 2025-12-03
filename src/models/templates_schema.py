from pydantic import BaseModel, Field
from typing import Dict, List, Set, Optional
from src.models.generation import Rarity

# --- Resource Template ---
class ResourceRarityOption(BaseModel):
    rarity: Rarity 
    weight: int

class ResourceTemplate(BaseModel):
    id: str       
    name_key: str 
    renewable: bool 
    icon: Optional[str] = None 
    rarity_options: List[ResourceRarityOption]
    tags: Set[str] = Field(default_factory=set)

# --- 1. Вектор Культуры (С МАТЕМАТИКОЙ) ---
class CultureVector(BaseModel):
    aggression: int = 0
    magic_affinity: int = 0
    collectivism: int = 0
    # Используем Set для быстрого пересечения множеств
    taboo: Set[str] = Field(default_factory=set)
    revered: Set[str] = Field(default_factory=set)

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
            taboo=self.taboo | other.taboo,       # Объединение множеств
            revered=self.revered | other.revered  # Объединение множеств
        )

# --- 2. Шаблон Веры (НОВЫЙ) ---
class BeliefVariation(BaseModel):
    """Подвид веры (ересь, секта, ортодоксы)"""
    name: str
    modifiers: CultureVector # Используем тот же класс для описания изменений

class BeliefTemplate(BaseModel):
    id: str
    name: str            # Название архетипа ("Воинственный культ")
    naming_style: str    # "martial", "nature", "arcane" (для NamingService)
    
    # Кто склонен к этой вере? (для авто-выбора при генерации)
    preferred_roles: List[str] = Field(default_factory=list) 
    
    # Базовые модификаторы, которые эта вера дает
    base_modifiers: CultureVector = Field(default_factory=CultureVector)
    
    # Вариации (опционально)
    variations: List[BeliefVariation] = Field(default_factory=list)

# --- 3. Шаблон Фракции ---
class FactionTemplate(BaseModel):
    id: str                  
    creature_type: str       
    role: str                
    icon: Optional[str] = None 
    tags: Set[str] = Field(default_factory=set)
    
    # Базовая культура вида (например, Орки агрессивны сами по себе)
    culture: CultureVector = Field(default_factory=CultureVector)
    
    # Если у фракции есть жестко заданная религия (опционально)
    default_belief_id: Optional[str] = None

class BossesTemplate(FactionTemplate):
    name_template: str

class TraitTemplate(BaseModel):
    id: str       # "trait_paranoid"
    name: str     # "Параноик" (для UI/Логов)
    modifiers: CultureVector # { aggression: 2, collectivism: -3 }
    conflict_tags: Set[str] = Field(default_factory=set, description='С какими тэгами несовместим (напр. "trusting")') # С какими тэгами несовместим (напр. "trusting")

# --- Faction Template (вложенный в биом) ---
class FactionSpawnRule(BaseModel):
    definition_id: str 
    role: str          
    weight: float = 1.0
    override_tags: Set[str] = Field(default_factory=set) 

# --- Location Template ---
class LocationTemplate(BaseModel):
    id: str         
    name: str       
    capacity: int
    limits: Dict[str, int] = Field(default_factory=dict) 
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
    capacity: int
    tags: Set[str] = Field(default_factory=set)
    icon: Optional[str] = None 
    allowed_locations: List[str] 
    forbidden_neighbors: Set[str] = Field(default_factory=set)
    available_resources: List[str] 
    factions: List[FactionSpawnRule]

class TransformationRule(BaseModel):
    id: str 
    requires_tag: str
    needs_faction: bool
    min_age_empty: Optional[int] = None
    target_def: str 
    chance: float
    verb: str 
    narrative: str