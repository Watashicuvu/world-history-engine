from typing import List, Dict, Optional
from pydantic import BaseModel, Field

# --- 1. Лексиконы Биомов ---
class BiomeLexiconEntry(BaseModel):
    id: str = Field(..., description="ID биома (напр. biome_forest)")
    adjectives: List[str] = Field(default_factory=list, description="Прилагательные (только Мужской род!)")
    nouns: List[str] = Field(default_factory=list, description="Существительные (только Мужской род!)")
    symbols: List[str] = Field(default_factory=list, description="Символы (напр. 'Тьмы', 'Света')")
    deity_prefixes: List[str] = Field(default_factory=list, description="Титулы (напр. 'Дух', 'Хранитель')")

# --- 2. Правила именования Фракций (Доработано) ---
class FactionNamingRule(BaseModel):
    role: str = Field(..., description="Роль фракции (напр. military, religious, default)")
    templates: List[str] = Field(..., description="Шаблоны (напр. '{adj} {noun}')")

class FactionNamingEntry(BaseModel):
    id: str = Field(..., description="Тип существа (напр. humanoid, undead)")
    rules: List[FactionNamingRule] = Field(default_factory=list)

# --- 3. Именование ресурсов ---
class ResourceNamingEntry(BaseModel):
    id: str = Field(..., description="ID ресурса (напр. res_iron)")
    # Например, синонимы или прилагательные, описывающие ресурс
    descriptors: List[str] = Field(default_factory=list, description="Прилагательные (ржавый, сияющий)")
    names: List[str] = Field(default_factory=list, description="Варианты названий (Руда, Жила)")

# --- 4. Шаблоны сущностей (Entity Templates) ---
class EntityTemplateEntry(BaseModel):
    id: str = Field(..., description="Тип сущности (напр. weapon_sword, location_ruins)")
    templates: List[str] = Field(default_factory=list, description="Список шаблонов генерации имен")

# --- 5. Имена персонажей (Сложная структура) ---
# Файл character_names.yaml содержит две секции.
# Для редактора мы можем сделать общую модель конфига.

class CharacterNamesConfig(BaseModel):
    # Т.к. этот файл один на всё, поле id тут формальное, но оно нужно для списка редактора
    id: str = Field(default="global_character_names", description="Служебный ID")
    
    by_faction: Dict[str, List[str]] = Field(
        default_factory=dict, 
        description="Имена по фракциям (ключ - ID фракции)"
    )
    by_creature_type: Dict[str, List[str]] = Field(
        default_factory=dict, 
        description="Имена по типу существа (ключ - creature_type)"
    )