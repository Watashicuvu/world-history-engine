import json
from pathlib import Path
from typing import List, Optional, Tuple, Dict
from src.interfaces import IWorldRepository
from src.models.generation import Entity, EntityType

class InMemoryWorldRepository(IWorldRepository):
    def __init__(self, snapshot_path: Path):
        self.snapshot_path = snapshot_path
        self._entities: Dict[str, Entity] = {}
        self._relations: List[dict] = [] 
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded or not self.snapshot_path.exists():
            return
        
        with open(self.snapshot_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            raw_entities = data.get("graph", {}).get("entities", {})
            self._entities = {
                k: Entity(**v) for k, v in raw_entities.items()
            }
            self._relations = data.get("graph", {}).get("relations", [])
        self._loaded = True

    async def get_entity(self, entity_id: str) -> Optional[Entity]:
        self._ensure_loaded()
        return self._entities.get(entity_id)

    async def get_entities_by_type(self, type_: EntityType) -> List[Entity]:
        self._ensure_loaded()
        return [e for e in self._entities.values() if e.type == type_]

    async def get_neighbors(self, entity_id: str) -> List[Tuple[str, Entity]]:
        """Упрощенная версия для визуализации"""
        self._ensure_loaded()
        neighbors = []
        for rel in self._relations:
            f_id = rel['from_entity']['id']
            t_id = rel['to_entity']['id']
            rel_desc = rel['relation_type']['description']

            if f_id == entity_id:
                target = self._entities.get(t_id)
                if target: neighbors.append((f"-> {rel_desc}", target))
            elif t_id == entity_id:
                source = self._entities.get(f_id)
                if source: neighbors.append((f"<- {rel_desc}", source))
        return neighbors

    # --- НОВАЯ РЕАЛИЗАЦИЯ ДЛЯ STORYTELLER ---
    async def get_neighbors_with_rel(self, entity_id: str) -> List[Tuple[str, Entity, str]]:
        """
        Возвращает (relation_id, entity, description_string)
        """
        self._ensure_loaded()
        results = []
        
        for rel in self._relations:
            # Безопасное извлечение данных, так как структура json может плавать
            src_data = rel.get('from_entity', {})
            dst_data = rel.get('to_entity', {})
            rtype_data = rel.get('relation_type', {})
            
            f_id = src_data.get('id')
            t_id = dst_data.get('id')
            
            # Если ID связи нет в JSON, генерируем фейковый, но лучше если он там есть
            rel_id = rel.get('id', 'unknown_rel')
            base_desc = rtype_data.get('description', 'related')

            if f_id == entity_id:
                target = self._entities.get(t_id)
                # Стрелка -> показывает исходящую связь
                if target: results.append((rel_id, target, f"-> {base_desc}"))
            
            elif t_id == entity_id:
                source = self._entities.get(f_id)
                # Стрелка <- показывает входящую связь
                if source: results.append((rel_id, source, f"<- {base_desc}"))
                
        return results

    async def get_lineage(self, entity_id: str) -> List[Entity]:
        self._ensure_loaded()
        chain = []
        current = self._entities.get(entity_id)
        while current and current.parent_id:
            parent = self._entities.get(current.parent_id)
            if parent:
                chain.append(parent)
                current = parent
            else:
                break
        return chain
    
    async def get_global_context(self) -> str:
        self._ensure_loaded()
        biomes = [e.name for e in self._entities.values() if e.type == EntityType.BIOME]
        factions = [e.name for e in self._entities.values() if e.type == EntityType.FACTION]
        
        ctx = "Мир состоит из регионов: " + ", ".join(biomes) + ". "
        ctx += "Ключевые силы: " + ", ".join(factions) + "."
        return ctx