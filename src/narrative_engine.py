import random
from typing import List, Optional, Union, Tuple, Dict
import logging

from src.models.registries import (TRAIT_REGISTRY, CALENDAR_REGISTRY)
from src.models.templates_schema import CalendarTemplate, CultureVector, Season
from src.models.generation import EntityType, Entity, RelationType, World
from src.naming import NamingService
from src.word_generator import WorldGenerator
from src.services.world_query_service import WorldQueryService
from src.systems.conflict_system import ConflictSystem
from src.utils import make_id
from src.systems.lifecycle_system import LifecycleSystem
from src.systems.transformation_system import TransformationSystem
from src.systems.belief_system import BeliefSystem

# Настройка логгера
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
        
        # (Director Logic)
        self.base_event_weights = {
            "GLOBAL_WAR_START": 100,
            "BOSS_SPAWN": 80,
            "LEADER_DEATH": 70,
            "FACTION_CONFLICT": 60,
            "DISCOVERY": 55,
            "NEW_LEADER": 50,
            "CONFLICT_RESOLVED": 45,
            "RAID_START": 40,
            "EXPANSION": 35,
            "RESOURCE_DEPLETED": 20,
            "RESOURCE_REGROWTH": 20,
            "DEFAULT": 30
        }
        
        factions_count = len([e for e in self.world.graph.entities.values() if self._check_type(e, EntityType.FACTION)])
        logger.info(f"NarrativeEngine initialized. Factions: {factions_count}")

    def _check_type(self, entity: Entity, target_type: Union[EntityType, str]) -> bool:
        if entity.type == target_type:
            return True
        return str(entity.type) == str(target_type)

    def _check_rel_type(self, relation, type_id: str) -> bool:
        if hasattr(relation.relation_type, 'id'):
            return relation.relation_type.id == type_id
        return str(relation.relation_type) == type_id

    def _register_narrative_relation_types(self):
        graph = self.world.graph
        rt = graph.relation_types

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
            ("believes_in", EntityType.FACTION, EntityType.BELIEF, "Исповедует"),
            ("opposes_belief", EntityType.BELIEF, EntityType.BELIEF, "Враждует с верой"),
            ("part_of_global", EntityType.CONFLICT, EntityType.GLOBAL_CONFLICT, "Часть глобальной войны"),
            ("active_participant", EntityType.FACTION, EntityType.GLOBAL_CONFLICT, "Участник войны"),
        ]

        for rid, from_t, to_t, desc in defs:
            if rid not in rt:
                rt[rid] = RelationType(id=rid, from_type=from_t, to_type=to_t, description=desc)

    def _sync_spatial_data(self):
        graph = self.qs.graph
        locating_relations = ["located_in", "fled_to", "occurred_at"]
        
        for entity in graph.entities.values():
            if entity.type in [EntityType.LOCATION, EntityType.BIOME]:
                continue
            target_location = None
            for rel in graph.relations:
                if rel.from_entity.id == entity.id:
                    rel_type_id = rel.relation_type.id if hasattr(rel.relation_type, 'id') else str(rel.relation_type)
                    if rel_type_id in locating_relations:
                        target_location = rel.to_entity
                        break
            
            if target_location and target_location.data:
                loc_x = target_location.data.get("x") or target_location.data.get("grid_x")
                loc_y = target_location.data.get("y") or target_location.data.get("grid_y")
                if loc_x is not None and loc_y is not None:
                    if entity.data is None: entity.data = {}
                    entity.data["x"] = loc_x
                    entity.data["y"] = loc_y
                    entity.data["last_moved_at"] = self.age

    # === EVOLVE LOOP (UPDATED) ===
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
            
            # От перенаселения подчищаем каждую эпоху
            crysis = self.lifecycle_system.process_overcrowding(self.age)
            all_events.extend(crysis)

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

    # ломает визуализацию и пока баг со схемой, но принцип неплохой
    # def evolve(self, num_ages: int = 3) -> List[Entity]:
    #     """
    #     Запускает симуляцию на num_ages вперед.
    #     Возвращает ВСЕ события, но обогащенные метаданными о важности (weight, tier)
    #     и сгруппированные по времени (age, season).
    #     """
    #     all_history_events = [] 

    #     # Пытаемся получить календарь
    #     global_calendar: Optional[CalendarTemplate] = CALENDAR_REGISTRY.get("cal_standard")
        
    #     for _ in range(num_ages):
    #         self.age += 1
    #         age_events = [] # События конкретно этой эпохи

    #         # 1. Определение контекста времени (Сезон)
    #         current_season: Optional[Season] = None
    #         season_name = "Unknown Season"
    #         modifiers = {}
            
    #         if global_calendar:
    #             current_season = global_calendar.get_season_by_age(self.age)
    #             season_name = current_season.name
    #             modifiers = current_season.modifiers
                
    #         logger.info(f"--- Processing Age {self.age}: {season_name} ---")

    #         # 2. Сбор "сырых" событий от систем
    #         # Системы меняют граф и возвращают Entity типа EVENT
            
    #         # --- Жизненный цикл ---
    #         age_events.extend(self.lifecycle_system.process_leader_decay(self.age))
    #         age_events.extend(self.lifecycle_system.process_resource_decay(self.age))

    #         # --- Религия ---
    #         age_events.extend(self.belief_system.process_beliefs(self.age))
            
    #         # --- Политика и конфликты ---
    #         self._ensure_leaders()
            
    #         age_events.extend(self.conflict_system.process_conflicts_spawn(self.age))
    #         age_events.extend(self.conflict_system.process_raids(self.age))
    #         age_events.extend(self.conflict_system.process_bosses(self.age))

    #         # --- Рост (раз в 5 лет/эпох) ---
    #         if self.age % 5 == 0:
    #             age_events.extend(self.transformation_system.process_new_land_discovery(self.age))
    #             age_events.extend(self.lifecycle_system.process_new_resources(self.age))
    #             age_events.extend(self.lifecycle_system.process_resource_regrowth(self.age))

    #         age_events.extend(self.lifecycle_system.process_overcrowding(self.age))
            
    #         # --- Трансформация ---
    #         age_events.extend(self.transformation_system.process_transformations(self.age))
    #         age_events.extend(self.transformation_system.process_expansions(self.age))

    #         # --- Разрешение конфликтов ---
    #         age_events.extend(self.conflict_system.resolve_conflicts(self.age))

    #         self._sync_spatial_data()

    #         # 3. ПОСТ-ОБРАБОТКА: Взвешивание и Группировка
    #         # Мы не удаляем события, а сортируем и размечаем их.

    #         weighted_events = []
    #         for event in age_events:
    #             weight = self._calculate_importance(event, modifiers)
    #             weighted_events.append((weight, event))
            
    #         # Сортировка: Самые важные события эпохи идут первыми
    #         weighted_events.sort(key=lambda x: x[0], reverse=True)
            
    #         # 4. Присвоение Tier (Уровня важности) и обогащение данными
    #         # Это поможет UI/LLM группировать их визуально
    #         total_events = len(weighted_events)
            
    #         for rank, (weight, evt) in enumerate(weighted_events):
    #             if evt.data is None: evt.data = {}
                
    #             # Сохраняем контекст времени прямо в событие
    #             evt.data["age"] = self.age
    #             evt.data["season_id"] = current_season.id if current_season else "unknown"
    #             evt.data["season_name"] = season_name
    #             evt.data["narrative_weight"] = round(weight, 2)
                
    #             # Логика Tiers (Ярусов)
    #             # Top 20% или вес > 80 -> "Major" (Хедлайны эпохи)
    #             # Середина -> "Average"
    #             # Хвост -> "Minor" (Фоновый шум)
                
    #             if weight >= 60: # Можно настроить порог
    #                 tier = "Major"
    #             elif weight >= 25:
    #                 tier = "Average"
    #             else:
    #                 tier = "Minor"
                
    #             # Дополнительная проверка: если событий очень мало, даже мелкие могут стать Major
    #             if total_events < 3:
    #                 tier = "Major"
                    
    #             evt.data["narrative_tier"] = tier
                
    #             # Формируем человекочитаемый заголовок для логов
    #             evt.data["display_date"] = f"[{season_name}, Age {self.age}]"

    #             all_history_events.append(evt)

    #     # Возвращаем плоский список, но он:
    #     # 1. Отсортирован хронологически (по Age)
    #     # 2. Внутри Age отсортирован по важности (Major -> Minor)
    #     # 3. Содержит метаданные для группировки на фронте/в промпте
    #     # TODO:
    #     # Группировка по важности (The "News Feed" approach):
    #     # События с narrative_tier == "Major" можно показывать заголовками или отправлять в LLM для генерации подробного текста.
    #     # События с narrative_tier == "Minor" можно схлопывать в одну строку: "Также произошло 4 стычки на границах и истощилась одна жила руды."
    #     return all_history_events

    def _calculate_importance(self, event: Entity, modifiers: Dict[str, float]) -> float:
        """
        Вычисляет вес события на основе его типа, данных и модификаторов сезона.
        """
        # Определяем ключ типа события
        # Обычно он лежит в data['event_type'], либо используем системный тип (менее точно)
        event_key = "DEFAULT"
        if event.data and "event_type" in event.data:
            # Приводим к верхнему регистру для матчинга с словарем
            key_candidate = str(event.data["event_type"]).upper()
            if key_candidate in self.base_event_weights:
                event_key = key_candidate
            # Попытка маппинга частичных совпадений (например "raid_start" -> "RAID")
            elif "RAID" in key_candidate: event_key = "RAID"
            elif "CONFLICT" in key_candidate: event_key = "FACTION_CONFLICT"
            elif "DEATH" in key_candidate: event_key = "LEADER_DEATH"
        
        # Базовый вес
        base_weight = self.base_event_weights.get(event_key, 10)
        
        # Применяем модификаторы сезона
        # Например, если сезон {"conflict_weight": 1.5}, то события войны важнее
        multiplier = 1.0
        
        if modifiers:
            if "conflict" in event_key.lower() or "raid" in event_key.lower():
                multiplier *= modifiers.get("conflict_weight", 1.0)
            if "resource" in event_key.lower():
                multiplier *= modifiers.get("resource_weight", 1.0)
            if "belief" in event_key.lower():
                multiplier *= modifiers.get("magic_weight", 1.0)

        final_weight = base_weight * multiplier
        
        # Небольшой шум (jitter), чтобы события с одинаковым весом не всегда выходили в одном порядке
        jitter = random.uniform(0.9, 1.1)
        
        return final_weight * jitter

    def _ensure_leaders(self) -> int:
        factions = [e for e in self.qs.graph.entities.values() 
                if self._check_type(e, EntityType.FACTION) and "absorbed" not in e.tags]
        
        created_count = 0
        all_traits = list(TRAIT_REGISTRY.get_all().values()) 

        if not all_traits:
            return 0

        traits_count = random.choices([1, 2], weights=[0.7, 0.3])[0]
        k = min(traits_count, len(all_traits))
        selected_traits = random.sample(all_traits, k=k)
        
        leader_vector = CultureVector()
        trait_names = []
        
        for trait in selected_traits:
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
            
            leader = Entity(
                id=make_id("char"),
                definition_id="char_leader",
                type=EntityType.CHARACTER,
                name=name,
                data={
                    "faction_id": faction.id, 
                    "role": "leader",
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