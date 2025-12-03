from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Dict
from src.models.generation import Entity, RelationInstance, EntityType

class IWorldRepository(ABC):
    """
    Абстракция для доступа к данным мира.
    Позволяет в будущем заменить In-Memory словарь на Neo4j или Postgres.
    """
    
    @abstractmethod
    async def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Получить сущность по ID."""
        pass

    @abstractmethod
    async def get_entities_by_type(self, type_: EntityType) -> List[Entity]:
        """Получить все сущности определенного типа (например, все Фракции)."""
        pass

    @abstractmethod
    async def get_neighbors(self, entity_id: str) -> List[Tuple[str, Entity]]:
        """
        Получить соседей по графу.
        Возвращает список кортежей (Описание связи, Соседняя сущность).
        """
        pass
        
    @abstractmethod
    async def get_lineage(self, entity_id: str) -> List[Entity]:
        """Получить цепочку родителей (кто владеет этой локацией/к кому относится)."""
        pass

    @abstractmethod
    async def get_global_context(self) -> str:
        """Вернуть общее описание состояния мира (эпоха, доминирующие силы)."""
        pass

    @abstractmethod
    async def get_neighbors_with_rel(self, entity_id: str) -> List[Tuple[str, Entity, str]]:
        """
        Возвращает детальный список связей для Storyteller: 
        [(RelationID, NeighborEntity, RelationDescription)]
        """
        pass