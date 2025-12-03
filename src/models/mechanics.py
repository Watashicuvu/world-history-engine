from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field

from src.models.generation import LocType

class Archetype(str, Enum):
    '''Может быть, игроки всё же смогут выбирать для отыгрыша'''
    SAGE = "Sage"
    HERO = "Hero"
    TRICKSTER = "Trickster"
    BADGUY = "BadGuy"
    FEMMEFATALE = "FemmeFatale"
    DAMSELINDISTRESS = "DamselInDistress"
    FATHERFIGURE = "FatherFigure" # ну и мать тоже, но, надеюсь, не нужно будет уточнять
    ...

class SkillNameEnum(str, Enum):
    CONCEALMENT = 'concealment'
    CONTACTS = 'contacts'
    HANDICRAFT = 'handicraft'
    DECEPTION = 'deception'
    RIDING = 'riding'
    EMPATHY = 'empathy'
    LORE = 'lore'
    ATTENTION = 'attention'
    PROVOKE = 'provoke'

# concealment: int = Field(description='воровство сюда же')
# contacts: int = Field(description='легче скрыться от стражи, дать взятку; обнаружить своё «знакомство»')
# handicraft: int = Field(description='На сколько хорошо работает руками; подробности зависят от навыков')
# deception: int = Field(description='Обман')
# riding: int = Field(description='способность оседлать кого-либо; подробности в навыках')
# empathy: int = Field(description='Легче понять, врет ли кто-то')
# lore: int = Field(description='Глубина познаний')
# attention: int = Field(description='внимательность; но вопрос, надо ли')
# provoke: int = Field(description='способность действовать на толпу')

class Language(str, Enum):
    '''Это тоже навыки'''
    COMMON = "Common"
    LIZARD = "Lizard"
    BIRD = "Bird"
    SEA = "Sea"
    BEAST = "Beast"
    ORCISH = "Orcish"
    ELVISH = "Elvish"
    DWARFISH = "Dwarfish"  

class Characteristics(BaseModel):
    strength: Optional[int]
    intellect: Optional[int]
    vitality: Optional[int]
    will: Optional[int]
    luck: Optional[int] = Field(description='Влияет на шанс крита и мб что-то ещё')

    hp: Optional[int] = Field(description='вычисляется; реген тоже', default_factory=int)
    mp: Optional[int] = Field(description='вычисляется', default_factory=int)
    satiety: Optional[int] = Field(description='вычисляется; сытость; мб только немного дебаф / баф', default_factory=int)
    armor: Optional[int] = Field(description='вычисляется', default_factory=int)

class Skill(BaseModel):
    name: str
    description: str

class StandardSkill(Skill):
    # задаются энамом, влияют на проверки и частично зависят от основных характеристик 
    value: int = Field(ge=0)

# лучше всё же разделить:
# Рекомендация: Раздели Effect (то, что происходит) и Ability/Skill (то, что вызывает эффект).
# Ability: Имеет cost, cooldown, requirements. Она порождает Эффект.
# Effect: Это конкретное изменение состояния (MomentState). Урон — это мгновенный эффект. Отравление — длительный.
class Effect(BaseModel):
    id: int
    effect_type: str = Field(description="Для упрощения бизнес-логики типа бафф / урон ...")
    affected_characteristics: Optional[Characteristics] = Field(description="Вычитает или убавляет характеристики")
    passive_skills: Optional[List[StandardSkill]]
    affected_unique_skills: Optional[List[int]]
    affected_languages: Optional[List[Language]]
    distance: int
    aoe: int
    cooldown: Optional[datetime]
    activation_conditions: Optional[List[StandardSkill]] = Field(description='Сложность проверки, иначе говоря')
    creature_id: int = Field(description='Если ликантропия, то проще подменить персонажей')
    cost_in: Optional[Characteristics]
    cost_out: Optional[List[int]] # ай ди предметов, которые расходуются 
    other: Optional[Dict[str, Any]]

class UniqueSkill(Skill):
    id: int
    on_skin: bool
    effect: Effect

class Skills(BaseModel):
    '''Как пассивные, так и активные; зависят от предыстории (фракций), ибо классов нет'''
    passive_skills: List[StandardSkill]
    active_skills: List[UniqueSkill]  
    languages: List[Language]

class MomentState(BaseModel):
    '''Отравлен, горит, превращён в свинью...'''
    name: str
    description: str
    hidden: bool
    effect: Effect 
    on_skin: bool
    durration: datetime
    start_time: datetime

class StateBlock(BaseModel):
    '''Агрегирует разные наследуемые и персональные свойства'''
    creature_id: int
    level: int = Field(description='Эвристика-индекс')
    skills: Skills = Field(description='В том числе и языки')
    characteristics: Characteristics
    current_states: Optional[MomentState] = None

class TradeConditions(BaseModel):
    '''Класс для сбора эвристик условий продажи предметов'''
    creature_id: int = Field(description="Для быстрого поиска")
    item_id: Optional[int]
    location_id: Optional[int]
    faction_id: Optional[int] = Field(description='Фракции для продажи при выполнении условия')
    current_stock: int = Field(description='Подтягивается из инвентаря; для быстрого доступа')
    rent: bool = Field(description='Можно ли базово взять в аренду')
    trade: bool = Field(description='Можно ли базово купить')

class Rank(BaseModel):
    # так же нужна отдельная таблица рангов конкретных существ
    id: int
    faction_id: int
    name: str
    description: str
    trade_conditions: TradeConditions 
    max_participants: Optional[int] = Field(description='Для рас и стран не будет ограничений (наверное)')
    effects: List[Effect] # то, что даруется её членам по "наследству"

class Consequence(BaseModel):
    condition: str # enum; при обнаруженном нарушении проверяется фракция и её структура
    punishment: Any # эффект, тюрьма и другие вещи, которые нужно думать, как кодить

class Structure(BaseModel):
    '''
    Критерии вступления (типы квестов, ачивки, репутация и прочее)
    Ранги (если предусмотрено, но один всегда есть)
    Последствия нарушений
    Критерии повышения (если есть ранги, так что опциональное)
    Связь с локациями и предметами (владения)
    '''
    lore_types: List[str]
    ranks: List[Rank]
    consequences = List[Consequence]
    main_location: Optional[int]

class Faction(BaseModel):
    id: int
    parent_faction: Optional[int] = Field(description='так как расы тоже относятся к фракциям; связь с родителями родителей зависит от структуры')
    name: str
    nowaday_description: str = Field(description='для быстрого обогащения контекста и резюме для игроков')
    relations: Dict[int, int] = Field(description='описывает отношение между фракциями; глубина рекурсии 1, остальное подсчитывается при необходимости')
    fields: List[str] = Field(description='описывает поле деятельности; нужно для первичной генерации истории и квестов')
    power: int = Field(description='ещё один триггер квестов')
    structure: Structure = Field(description='структура управления: где база, есть ли; кто глава, есть ли')
    value: int = Field(description='Базовая цена продажи, если возможна продажа')
    # есть так же связь с локациями и предметами: владение или расположение

class Environment(BaseModel):
    # легкое ограничение; должна быть разумная стохастичность для разнообразия
    name: str
    item_types: List[str]
    creature_types: List[int]
    assets_for_generation: Optional[List[int]]
    filters: List[int] # типа темных тонов / кислотных оттенков
    music: List[int]

class LocationMechanic(BaseModel):
    id: int
    loc_type: LocType
    parent_location: int
    threat_level: int
    faction_id: List[int]
    environments: List[Environment]
    description: str = Field(description="для контекста и игроков")
    value: int = Field(description='цена, если можно купить')
    other: Optional[Dict[str, Any]] = Field(description='разрушаемо? внутри существа?', default=None)
    
class Item(BaseModel):
    '''То, что можно поместить в инвентарь, но не всегда в личный; для таких вещей можно придумать хитрые механики'''
    # опциональная связь с фракцией и нынешнее расположение / привязка к персонажу
    id: int
    effect: Optional[Effect]
    creature_id: Optional[int]
    location_id: Optional[int]
    on_skin: bool
    value: int = Field(description='Цена в единицах ценности')
    unique: bool = Field(description='Влияет на тип квеста')
    item_type: List[str] = Field(description='может быть чем-то вроде "часть трупа", ресурсом')
    other: Dict[str, Any] = Field(description='физика? размер? можно создать?')

class Inventory(BaseModel):
    '''Зависит от фракции, локации и много чего ещё'''
    character_id: int
    items: List[Item]
    capacity: int = Field(description='Количество слотов')   

class Creatures(BaseModel):
    id: int
    playable: bool = False
    name: str
    description: str = Field(description="Краткое описание на сегодняшний день")
    location_id: int = Field(description="id локации, где *сейчас* находится существо")
    trader: bool = Field(description="Может ли существо торговать?", default=False)
    fighter: bool = Field(description="Будет ли существо бить в ответ", default=True)
    language: List[Language] = Field(description="Частично наследуется, как и другие НАВЫКИ; для быстрого доступа")
    creature_type: int
    factions: List[int] = Field(description="Список фракций, втч семья и страна")
    personal_relations: Dict[int, int] = Field(description="ID существа -> Уровень симпатии (-100 to 100)")
    archetype: Optional[Archetype] = Field(description="Для игроков не определён", default=None)
    key: bool = Field(description="Не броня; запускает проверку правдивости", default=False)
    state: Optional[StateBlock] = Field(description="None, если мёртв", default=None)
    inventory: Inventory
    other: Optional[Dict[str, Any]] = None

# creatures_to_locations

class Merchant(BaseModel):
    id: int = Field(description="id существа, если оно может торговать")
    currency_type: List[Item] = Field(description="Любой предмет может быть валютой, но есть и более традиционные вроде очков влияния и денег")
    buy_modifier: float = 0.3
    sell_modifier: float = 1.5

class CulturalValues(BaseModel):
    aggression: int = Field(ge=-10, le=10) # -10 (Пацифисты) <-> +10 (Милитаристы)
    magic_affinity: int = Field(ge=-10, le=10) # -10 (Технократы/Отрицание) <-> +10 (Магократия)
    collectivism: int = Field(ge=-10, le=10) # -10 (Индивидуалисты) <-> +10 (Улей/Рой)
    
    # Ключевое для LLM: Табу и Фетиши
    taboo: List[str] # ["necromancy", "eating_pork", "cutting_trees"]
    revered: List[str] # ["ancestors", "gold", "moon"]

# === 1. События (То, что запускает генерацию) ===

class EventType(str, Enum):
    THEFT = "theft"
    MURDER = "murder"
    RESOURCE_DEPLETED = "resource_depleted" # Из твоего лога
    FACTION_CONFLICT = "faction_conflict"   # Из твоего лога
    ITEM_FOUND = "item_found"

class GameEvent(BaseModel):
    """Событие, которое произошло в симуляции"""
    timestamp: int # Или datetime, как у тебя в логах (Эпоха)
    type: EventType
    actor_id: Optional[int] = None      # Кто совершил (вор)
    target_id: Optional[int] = None     # Жертва / Цель
    location_id: int                    # Где произошло
    data: Dict[str, Any] = {}           # Детали: {item_id: 55, amount: 100}

# === 2. Структура Квеста (Для движка) ===

class QuestVerb(str, Enum):
    KILL = "kill"
    TALK = "talk"
    FIND_ITEM = "find_item"
    GO_TO = "go_to"
    STEAL = "steal"

class QuestObjective(BaseModel):
    """Атомарная цель, понятная коду"""
    verb: QuestVerb
    target_id: int          # ID существа, предмета или локации
    target_name: str        # Кешируем имя для удобства
    count_required: int = 1
    count_current: int = 0
    description: str        # Техническое описание: "Kill Goblin ID:105"

class Quest(BaseModel):
    id: int
    initiator_id: int # Кто выдал (Creature или Faction)
    objectives: List[QuestObjective]
    rewards: List[Item] # Или experience / reputation
    status: str # "active", "completed", "failed"
    deadline: Optional[datetime] # Если time-based
    # Text fields for LLM generation later
    generated_title: Optional[str] 
    generated_description: Optional[str]

class QuestStatus(str, Enum):
    AVAILABLE = "available"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"

class GeneratedQuest(BaseModel):
    """Готовый квест, который выдается игроку"""
    id: str
    initiator_id: int           # NPC/Фракция, выдающая квест
    location_id: int            # Где взять квест
    
    # Жесткая логика
    objectives: List[QuestObjective]
    rewards: List[Item]         # Ссылка на твои Items
    status: QuestStatus = QuestStatus.AVAILABLE
    
    # Для LLM (Контекст)
    context_summary: str        # "Вор украл меч у торговца в Эпоху 10"
    hidden_info: str            # "Вор на самом деле работает на стражу" (секрет)

    # это только драфт; нужно доработать
    def to_llm_prompt(self) -> str:
        """Генерирует инструкцию для LLM"""
        objs = "\n".join([f"- {o.description}" for o in self.objectives])
        return (
            f"GENERATE QUEST DIALOGUE:\n"
            f"Context: {self.context_summary}\n"
            f"Secret Info: {self.hidden_info}\n"
            f"Objectives for Player:\n{objs}\n"
            f"Task: Write a dramatic quest offer from the initiator's perspective."
        )