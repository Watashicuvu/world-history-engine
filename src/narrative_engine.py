import random
from typing import List, Optional, Union
import logging

from src.models.registries import TRAIT_REGISTRY
from src.models.templates_schema import CultureVector
from src.models.generation import EntityType, Entity, RelationType, World
from src.naming import NamingService
from src.word_generator import WorldGenerator
from src.services.world_query_service import WorldQueryService
from src.systems.conflict_system import ConflictSystem
from src.utils import make_id
from src.systems.lifecycle_system import LifecycleSystem
from src.systems.transformation_system import TransformationSystem
from src.systems.belief_system import BeliefSystem

# Настройка простого логгера для отладки нарратива
logger = logging.getLogger("NarrativeEngine")
logger.setLevel(logging.INFO)
if not logger.handlers:
    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(levelname)s: %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

class NarrativeEngine:
    def __init__(
        self, 
        world: World,
        naming_service: NamingService, 
        world_generator: 'WorldGenerator',
        query_service: Optional[WorldQueryService] = None
    ):
        self.world = world
        self.age = 0
        self.naming_service = naming_service
        self.world_generator = world_generator
        
        if query_service:
            self.qs = query_service
        else:
            self.qs = WorldQueryService(world)

        self.lifecycle_system = LifecycleSystem(self.qs, self.naming_service)
        self.conflict_system = ConflictSystem(self.qs, self.naming_service)
        self.transformation_system = TransformationSystem(self.qs, self.naming_service)
        self.belief_system = BeliefSystem(self.qs, self.naming_service)
        
        self._register_narrative_relation_types()
        
        # ДИАГНОСТИКА ПРИ СТАРТЕ
        factions_count = len([e for e in self.world.graph.entities.values() if self._check_type(e, EntityType.FACTION)])
        logger.info(f"NarrativeEngine initialized. World has {len(self.world.graph.entities)} entities.")
        logger.info(f"Factions detected: {factions_count}. (If 0, simulation will be empty)")

    def _check_type(self, entity: Entity, target_type: Union[EntityType, str]) -> bool:
        """
        Универсальная проверка типа. Сравнивает и Enum, и строковое значение.
        Решает проблему, когда после JSON-десериализации Enum превращается в строку.
        """
        if entity.type == target_type:
            return True
        # Сравнение строковых представлений
        return str(entity.type) == str(target_type)

    def _check_rel_type(self, relation, type_id: str) -> bool:
        """Безопасная проверка типа связи (работает и с объектом, и со строкой)"""
        if hasattr(relation.relation_type, 'id'):
            return relation.relation_type.id == type_id
        return str(relation.relation_type) == type_id

    def _register_narrative_relation_types(self):
        graph = self.world.graph
        rt = graph.relation_types

        # Определяем типы, если их нет
        defs = [
            ("joined", EntityType.CHARACTER, EntityType.FACTION, "Присоединился к"),
            ("leads", EntityType.CHARACTER, EntityType.FACTION, "Предводитель"),
            ("involved_in", EntityType.FACTION, EntityType.CONFLICT, "Участвует в конфликте"),
            ("resolved_as", EntityType.CONFLICT, EntityType.EVENT, "Разрешён как событие"),
            ("affected_by", EntityType.FACTION, EntityType.EVENT, "Затронута событием"),
            ("occurred_at", EntityType.EVENT, EntityType.LOCATION, "Произошло в локации"),
            ("allied_with", EntityType.FACTION, EntityType.FACTION, "В союзе с"),
            ("fled_to", EntityType.FACTION, EntityType.LOCATION, "Сбежала в"),
            ("absorbed_by", EntityType.FACTION, EntityType.FACTION, "Поглощена фракцией"),
            ("expanded_to", EntityType.FACTION, EntityType.LOCATION, "Расширилась в"),
            ("splintered_from", EntityType.FACTION, EntityType.FACTION, "Откололась от"),
            ("located_in", EntityType.RESOURCE, EntityType.LOCATION, "Находится в"),
            #
            # Верования
            ("believes_in", EntityType.FACTION, EntityType.BELIEF, "Исповедует"),
            ("opposes_belief", EntityType.BELIEF, EntityType.BELIEF, "Враждует с верой"),
            
            # Глобальные конфликты
            ("part_of_global", EntityType.CONFLICT, EntityType.GLOBAL_CONFLICT, "Часть глобальной войны"),
            ("active_participant", EntityType.FACTION, EntityType.GLOBAL_CONFLICT, "Участник войны"),
        ]

        for rid, from_t, to_t, desc in defs:
            if rid not in rt:
                rt[rid] = RelationType(id=rid, from_type=from_t, to_type=to_t, description=desc)

    def _sync_spatial_data(self):
        """
        Проходит по графу и обновляет координаты (data.x, data.y) 
        для подвижных сущностей (персонажи, армии), 
        синхронизируя их с локацией, в которой они находятся.
        """
        graph = self.qs.graph # Используем QueryService для доступа к графу
        
        # Типы связей, определяющие местоположение
        locating_relations = ["located_in", "fled_to", "occurred_at"]
        
        for entity in graph.entities.values():
            # Пропускаем сущности, которые сами являются локациями или биомами
            if entity.type in [EntityType.LOCATION, EntityType.BIOME]:
                continue
                
            # Ищем, где находится сущность
            target_location = None
            
            # Перебираем связи "исходящие от сущности"
            # (Это упрощенный перебор, в идеале использовать graph.get_relations_from(entity.id))
            for rel in graph.relations:
                if rel.from_entity.id == entity.id:
                    # Проверяем ID связи (строка или объект)
                    rel_type_id = rel.relation_type.id if hasattr(rel.relation_type, 'id') else str(rel.relation_type)
                    
                    if rel_type_id in locating_relations:
                        target_location = rel.to_entity
                        break
            
            # Если нашли локацию и у неё есть координаты, копируем их
            if target_location and target_location.data:
                loc_x = target_location.data.get("x") or target_location.data.get("grid_x")
                loc_y = target_location.data.get("y") or target_location.data.get("grid_y")
                
                if loc_x is not None and loc_y is not None:
                    if entity.data is None:
                        entity.data = {}
                    
                    # Обновляем координаты сущности
                    entity.data["x"] = loc_x
                    entity.data["y"] = loc_y
                    # Можно добавить метку времени обновления
                    entity.data["last_moved_at"] = self.age

    # === EVOLVE LOOP ===

    def evolve(self, num_ages: int = 3) -> List[Entity]:
        all_events = []
        for _ in range(num_ages):
            self.age += 1
            logger.info(f"--- Processing Age {self.age} ---")
            
            # --- 1. ЖИЗНЕННЫЙ ЦИКЛ ---
            leaders_died = self.lifecycle_system.process_leader_decay(self.age)
            resources_died = self.lifecycle_system.process_resource_decay(self.age)
            all_events.extend(leaders_died)
            all_events.extend(resources_died)

            # --- 1.5 РЕЛИГИЯ ---
            belief_events = self.belief_system.process_beliefs(self.age)
            all_events.extend(belief_events)
            if belief_events:
                logger.info(f"Religious shifts: {len(belief_events)}")
            
            # --- 2. ПОЛИТИКА ---
            # Гарантируем лидеров
            leaders_created = self._ensure_leaders()
            if leaders_created > 0:
                logger.info(f"Created {leaders_created} new leaders.")

            conflicts = self.conflict_system.process_conflicts_spawn(self.age)
            raids = self.conflict_system.process_raids(self.age)
            bosses = self.conflict_system.process_bosses(self.age)
            
            all_events.extend(conflicts)
            all_events.extend(raids)
            all_events.extend(bosses)
            
            if conflicts or raids:
                logger.info(f"Conflicts started: {len(conflicts)}, Raids: {len(raids)}")

            # --- 3. РОСТ ---
            if self.age % 5 == 0:
                discovered = self.transformation_system.process_new_land_discovery(self.age)
                new_res = self.lifecycle_system.process_new_resources(self.age)
                regrown = self.lifecycle_system.process_resource_regrowth(self.age)
                all_events.extend(discovered)
                all_events.extend(new_res)
                all_events.extend(regrown)
            
            # --- 4. ТРАНСФОРМАЦИЯ ---
            transforms = self.transformation_system.process_transformations(self.age)
            expansions = self.transformation_system.process_expansions(self.age)
            all_events.extend(transforms)
            all_events.extend(expansions)

            # --- 5. РАЗРЕШЕНИЕ КОНФЛИКТОВ ---
            resolved = self.conflict_system.resolve_conflicts(self.age)
            all_events.extend(resolved)
            
            if resolved:
                logger.info(f"Conflicts resolved: {len(resolved)}")

            self._sync_spatial_data()
            
        return all_events

    def _ensure_leaders(self) -> int:
        factions = [e for e in self.qs.graph.entities.values() 
                if self._check_type(e, EntityType.FACTION) and "absorbed" not in e.tags]
        
        created_count = 0
        all_traits = list(TRAIT_REGISTRY.get_all().values()) 

        # Если реестр пуст - выходим или пропускаем
        if not all_traits:
            return 0 # или continue, в зависимости от контекста

        # Выбираем количество черт (1 или 2)
        traits_count = random.choices([1, 2], weights=[0.7, 0.3])[0]
        
        # Берем выборку. Поскольку all_traits теперь список ОБЪЕКТОВ, sample вернет объекты
        # k не может быть больше размера популяции, поэтому ставим min
        k = min(traits_count, len(all_traits))
        selected_traits = random.sample(all_traits, k=k)
        
        # 2. Собираем итоговый вектор лидера
        leader_vector = CultureVector()
        trait_names = []
        
        for trait in selected_traits:
            # Теперь trait - это объект TraitTemplate, и у него есть .modifiers
            leader_vector = leader_vector + trait.modifiers
            trait_names.append(trait.name)

        for faction in factions:
            has_leader = False
            for r in self.qs.graph.relations:
                if r.to_entity.id == faction.id and self._check_rel_type(r, "leads"):
                    has_leader = True
                    break
            
            if has_leader: continue

            name = self.naming_service.generate_name(EntityType.CHARACTER, {"faction": faction.id})
            
            # 3. Создаем сущность
            leader = Entity(
                id=make_id("char"),
                definition_id="char_leader",
                type=EntityType.CHARACTER,
                name=name,
                data={
                    "faction_id": faction.id, 
                    "role": "leader",
                    # Сохраняем и вектор (для математики), и имена (для LLM/Логов)
                    "culture_vector": leader_vector.model_dump(), 
                    "traits": trait_names 
                },
                created_at=self.age,
                parent_id=faction.parent_id
            )
            self.qs.add_entity(leader)
            self.qs.add_relation(leader, faction, "leads")
            created_count += 1
            
        return created_count