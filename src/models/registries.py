from typing import Dict, Iterator, TypeVar, Generic, Optional

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
    
    def __contains__(self, key: str) -> bool:
        """Позволяет использовать конструкцию: if key in registry"""
        return key in self._items

    def __getitem__(self, key: str) -> T:
        """Позволяет получать элемент через registry[key]"""
        return self._items[key]

    def __iter__(self) -> Iterator[str]:
        """Позволяет итерироваться по ключам: for key in registry"""
        return iter(self._items)

    def __len__(self) -> int:
        """Позволяет использовать len(registry)"""
        return len(self._items)

# Глобальные инстансы реестров
# чтобы можно было легко подменять
# и держать в памяти несколько экземпляров
BIOME_REGISTRY = Registry()
LOCATION_REGISTRY = Registry()
RESOURCE_REGISTRY = Registry()
FACTION_REGISTRY = Registry()
BOSSES_REGISTRY = Registry()
TRANSFORMATION_REGISTRY = Registry()
BELIEF_REGISTRY = Registry()
TRAIT_REGISTRY = Registry()
CALENDAR_REGISTRY = Registry()