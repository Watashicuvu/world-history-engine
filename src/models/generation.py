from typing import Dict, List, Optional, Set, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator


"""
В основе всего лежат два понятия:

Entity (Сущность): Атомарный элемент мира (Ресурс, Фракция, Ритуал...).
Relation (Связь): Определённое отношение между двумя сущностями.
"""

class Rarity(Enum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"

class EntityType(str, Enum):
    BIOME = "Biome"
    LOCATION = "Location"
    RESOURCE = "Resource" # "Древесина", "Руда", "Тайные знания такие-то"
    METHOD = "Method" # "Рудник", "Лесоповал"
    PROBLEM = "Problem" # "Истощается", "Монополия гильдии", "Утечка кадров"
    FACTION = "Faction" # "Аристократы", "Гильдия воров"
    DISPUTE_REASON = "DisputeReason" # "Власть", "Ресурс"
    RITUAL = "Ritual" # "Праздник", "Жертвоприношение" // НЕ ИСПОЛЬЗУЕТСЯ
    OBJECT_OF_WORSHIP = "ObjectOfWorship" # "Божество", "Предок" // НЕ ИСПОЛЬЗУЕТСЯ
    BELIEF = "Belief" 
    GLOBAL_CONFLICT = "global_conflict"
    CREATURE = "Creature"
    CHARACTER = "Character"       # ключевые фигуры
    CONFLICT = "Conflict"         # конфликт между фракциями
    EVENT = "Event"               # нарративное событие (опционально)
    ITEM = "Item"         # Предмет, который может служить отправной точкой для квестов и исторического контекста

# --- Core Models ---
class Entity(BaseModel):
    id: str                 # Уникальный ID экземпляра (напр. "loc_village_8d7a")
    definition_id: str      # <--- НОВОЕ ПОЛЕ: ID шаблона (напр. "loc_village" или "biome_tundra")
    type: EntityType        # Тип сущности (системный)
    name: str               # Отображаемое имя (напр. "Мрачная деревня")
    tags: Set[str] = Field(default_factory=set)
    capacity: Optional[int] = None
    parent_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = Field(default=None) # Доп. свойства
    created_at: int = 0  # Эпоха создания (0 для стартовых)

class RelationType(BaseModel):
    id: str
    from_type: EntityType
    to_type: EntityType
    description: str
    is_symmetric: bool = False

class RelationInstance(BaseModel):
    from_entity: Entity
    to_entity: Entity
    relation_type: RelationType

    @field_validator('from_entity', 'to_entity')
    def validate_entity_types(cls, v, info):
        relation_type = info.data.get('relation_type')
        if not relation_type:
            return v

        expected_type = relation_type.from_type if info.field_name == 'from_entity' else relation_type.to_type
        if v.type != expected_type:
            raise ValueError(f"Entity {v.id} is of type {v.type}, but {relation_type.id} expects {expected_type}")
        return v

# --- Constraint System ---
class EntityFilter(BaseModel):
    type: Optional[EntityType] = None
    tags: Set[str] = Field(default_factory=set)
    id: Optional[str] = None

    def matches(self, entity: Entity) -> bool:
        if self.id and entity.id != self.id:
            return False
        if self.type and entity.type != self.type:
            return False
        if self.tags and not self.tags.issubset(entity.tags):
            return False
        return True

class RelationPreference(BaseModel):
    relation: str  # ID RelationType
    from_filters: EntityFilter = Field(default_factory=EntityFilter)
    to_filters: EntityFilter = Field(default_factory=EntityFilter)
    weight: float = 1.0

class GenerationContext(BaseModel):
    biome: str
    # остальные ограничения
    assigned_slots: Dict[str, Entity] = Field(default_factory=dict)
    world_graph: 'WorldGraph'

class Constraint(BaseModel):
    name: str
    condition: Dict[str, Any] = Field(default_factory=dict)  # Упрощённо. Можно заменить на callable.
    preferences: List[RelationPreference] = Field(default_factory=list)

    def is_applicable(self, context: GenerationContext) -> bool:
        # Базовая реализация: проверяем биом
        biome_condition = self.condition.get("biome")
        if biome_condition and context.biome != biome_condition:
            return False
        
        # Можно добавить логику проверки существующих связей в context.world_graph
        # Пока возвращаем True для простоты
        return True

# --- World & Graph ---
class WorldGraph(BaseModel):
    entities: Dict[str, Entity] = Field(default_factory=dict)
    relation_types: Dict[str, RelationType] = Field(default_factory=dict)
    relations: List[RelationInstance] = Field(default_factory=list)

    def add_entity(self, entity: Entity):
        self.entities[entity.id] = entity
    
    def count_children_of_type(self, parent_id: str, entity_type: EntityType) -> int:
        return sum(
            1 for e in self.entities.values()
            if e.parent_id == parent_id
            and e.type == entity_type
            and "inactive" not in e.tags  
        )

    def count_children(self, parent_id: str) -> int:
        """Считает количество сущностей с заданным parent_id."""
        return sum(1 for e in self.entities.values() if e.parent_id == parent_id)

    def add_relation(self, from_entity: Entity, to_entity: Entity, relation_type_id: str):
        rel_type = self.relation_types[relation_type_id]
        rel_instance = RelationInstance(
            from_entity=from_entity,
            to_entity=to_entity,
            relation_type=rel_type
        )
        self.relations.append(rel_instance)
        return rel_instance

    def get_entities_by_filter(self, entity_filter: EntityFilter) -> List[Entity]:
        return [e for e in self.entities.values() if entity_filter.matches(e)]

class World(BaseModel):
    graph: WorldGraph = Field(default_factory=WorldGraph)
    constraints: List[Constraint] = Field(default_factory=list)

# --- Template System ---
class TemplateSlot(BaseModel):
    role: str
    type: EntityType

class TemplateRelation(BaseModel):
    from_role: str
    to_role: str
    relation_type: str  # ID RelationType

class GenerationTemplate(BaseModel):
    name: str
    slots: List[TemplateSlot]
    relations: List[TemplateRelation]

class SlotAssignment(BaseModel):
    template: GenerationTemplate
    assignments: Dict[str, Entity] = Field(default_factory=dict)