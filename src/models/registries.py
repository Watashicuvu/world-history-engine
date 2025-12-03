from typing import Dict, TypeVar, Generic, Optional

T = TypeVar("T")

class Registry(Generic[T]):
    """Универсальное хранилище для шаблонов (биомов, локаций и т.д.)"""
    def __init__(self):
        self._items: Dict[str, T] = {}

    def register(self, key: str, item: T):
        if key in self._items:
            print(f"Warning: Overwriting {key} in registry")
        self._items[key] = item

    def get(self, key: str) -> Optional[T]:
        return self._items.get(key)

    def get_all(self) -> Dict[str, T]:
        return self._items

    def keys(self):
        return self._items.keys()

# Глобальные инстансы реестров
BIOME_REGISTRY = Registry()
LOCATION_REGISTRY = Registry()
RESOURCE_REGISTRY = Registry()
FACTION_REGISTRY = Registry()
BOSSES_REGISTRY = Registry()
TRANSFORMATION_REGISTRY = Registry()
BELIEF_REGISTRY = Registry()
TRAIT_REGISTRY = Registry()