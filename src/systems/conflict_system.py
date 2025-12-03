import random
import itertools
from typing import List, Optional, Tuple

from src.models.templates_schema import CultureVector
from src.models.generation import Entity, EntityType
from src.services.world_query_service import WorldQueryService
from src.naming import NamingService
from src.models.registries import BOSSES_REGISTRY
from src.utils import make_id

class ConflictSystem:
    def __init__(self, query_service: WorldQueryService, naming_service: NamingService):
        self.qs = query_service
        self.naming_service = naming_service

    # === PUBLIC API ===

    def process_conflicts_spawn(self, age: int) -> List[Entity]:
        events = []
        # 1. Сначала проверяем начало глобальных религиозных войн (редкое событие)
        events.extend(self._spawn_religious_wars(age))
        
        # 2. Гражданские войны
        events.extend(self._spawn_civil_wars(age))
        
        # 3. Политические конфликты (с учетом новых глобальных войн)
        events.extend(self._spawn_political_conflicts(age))
        
        return events

    def process_raids(self, age: int) -> List[Entity]:
        return self._spawn_raids(age)

    def process_bosses(self, age: int) -> List[Entity]:
        return self._spawn_bosses(age)

    def resolve_conflicts(self, age: int) -> List[Entity]:
        events = []
        graph = self.qs.graph
        
        # Фильтруем активные локальные конфликты
        active_conflicts = [
            e for e in graph.entities.values()
            if e.type == EntityType.CONFLICT and e.data and e.data.get("status") == "active"
        ]
        
        for conflict in active_conflicts:
            outcome = self._resolve_single_conflict(conflict, age)
            
            if outcome == "aborted":
                continue
                
            if conflict.data is None: conflict.data = {}
            conflict.data["status"] = "resolved"
            conflict.data["outcome"] = outcome
            
            # Генерируем описание
            summary = self._generate_summary(conflict, outcome)
            
            participants = []
            for pid in conflict.data.get("participants", []):
                p_ent = self.qs.get_entity(pid)
                if p_ent: participants.append(p_ent)
            
            event = self.qs.register_event(
                event_type="conflict_resolved",
                summary=summary,
                age=age,
                primary_entity=conflict,
                secondary_entities=participants,
                data={"conflict_id": conflict.id, "outcome": outcome}
            )
            self.qs.add_relation(conflict, event, "resolved_as")
            events.append(event)
            
        return events

    # === SPAWN LOGIC ===

    def _spawn_religious_wars(self, age: int) -> List[Entity]:
        """
        Проверяет возможность начала глобальной религиозной войны (Crusade).
        """
        # Шанс невелик, но последствия глобальны
        if random.random() > 0.05: 
            return []

        # Получаем все религии
        beliefs = [e for e in self.qs.graph.entities.values() if e.type == EntityType.BELIEF]
        if len(beliefs) < 2: 
            return []

        # Проверяем, нет ли уже активной войны
        existing_wars = [
            e for e in self.qs.graph.entities.values() 
            if e.type == EntityType.GLOBAL_CONFLICT and e.data.get("status") == "active"
        ]
        if existing_wars: 
            return [] # Одна война за раз

        # Выбираем инициатора и цель
        attacker = random.choice(beliefs)
        defender = random.choice([b for b in beliefs if b.id != attacker.id])

        # Создаем Глобальный Конфликт
        war_id = make_id("global_war")
        war_name = f"Священная война: {attacker.name} против {defender.name}"
        
        global_war = Entity(
            id=war_id,
            definition_id="global_religious_war",
            type=EntityType.GLOBAL_CONFLICT,
            name=war_name,
            created_at=age,
            data={
                "status": "active",
                "type": "religious",
                "initiator_belief": attacker.id,
                "target_belief": defender.id,
                "participants": [attacker.id, defender.id] # Сюда входят ID верований
            }
        )
        self.qs.add_entity(global_war)
        
        # Связываем веры с войной
        self.qs.add_relation(attacker, global_war, "involved_in")
        self.qs.add_relation(defender, global_war, "involved_in")

        # Событие старта
        event = self.qs.register_event(
            event_type="global_war_start",
            summary=f"ОБЪЯВЛЕНА СВЯЩЕННАЯ ВОЙНА! Последователи {attacker.name} идут войной на {defender.name}.",
            age=age,
            primary_entity=global_war,
            secondary_entities=[attacker, defender]
        )
        
        return [event]

    def _spawn_civil_wars(self, age: int) -> List[Entity]:
        new_conflicts = []
        if age % 20 == 0:
            absorbed = [f for f in self.qs.graph.entities.values() 
                        if f.type == EntityType.FACTION and "absorbed" in f.tags]
            
            for f in absorbed:
                if random.random() < 0.1:
                    f.tags.discard("absorbed")
                    f.tags.add("rebel")
                    
                    parent_loc = self.qs.get_location_of(f)
                    if not parent_loc: continue
                    
                    overlord_id = f.data.get("absorbed_by")
                    overlord = self.qs.get_entity(overlord_id)
                    
                    if overlord and overlord.parent_id == f.parent_id:
                        conflict = self._create_conflict_entity(
                            f, overlord, parent_loc, "civil_war", age, tension=5.0
                        )
                        new_conflicts.append(conflict)
        return new_conflicts

    def _spawn_political_conflicts(self, age: int, base_chance=0.25) -> List[Entity]:
        new_conflicts = []
        locations = [e for e in self.qs.graph.entities.values() if e.type == EntityType.LOCATION]
        
        # Кэшируем активные глобальные войны для оптимизации
        active_global_wars = [
            e for e in self.qs.graph.entities.values() 
            if e.type == EntityType.GLOBAL_CONFLICT and e.data.get("status") == "active"
        ]

        for loc in locations:
            factions_in_loc = [
                e for e in self.qs.get_children(loc.id, EntityType.FACTION)
                if "absorbed" not in e.tags and "fled" not in e.tags
            ]

            if len(factions_in_loc) < 2:
                continue

            active_pairs = set()
            for r in self.qs.graph.relations:
                if (r.relation_type.id == "involved_in" 
                    and r.to_entity.type == EntityType.CONFLICT
                    and r.to_entity.data.get("status") == "active"):
                    participants = sorted(r.to_entity.data.get("participants", []))
                    if len(participants) >= 2:
                        active_pairs.add(frozenset(participants))

            for f1, f2 in itertools.combinations(factions_in_loc, 2):
                pair = frozenset([f1.id, f2.id])
                if pair in active_pairs:
                    continue 

                # Передаем список глобальных войн в расчет напряжения
                tension = self._calculate_cultural_tension(f1, f2, active_global_wars)
                
                # Если напряжение экстремальное (глобальная война), шанс 100%
                current_chance = base_chance * tension
                if tension >= 10.0: 
                    current_chance = 1.0

                if random.random() < current_chance:
                    reason_id = self._determine_dispute_reason([f1, f2], loc)
                    
                    # Если причина в глобальной войне, меняем reason_id
                    if tension >= 10.0:
                        reason_id = "religious_crusade"

                    conflict = self._create_conflict_entity(f1, f2, loc, reason_id, age, tension)
                    
                    # Если это часть глобальной войны, линкуем
                    if tension >= 10.0 and active_global_wars:
                        # Берем первую попавшуюся (упрощение)
                        self.qs.add_relation(conflict, active_global_wars[0], "part_of_global")
                        
                    new_conflicts.append(conflict)
        
        return new_conflicts

    def _create_conflict_entity(self, f1, f2, loc, reason, age, tension):
        conflict = Entity(
            id=make_id("conflict"),
            definition_id=f'conflict_{reason}',
            type=EntityType.CONFLICT,
            name=f"Конфликт: {f1.name} vs {f2.name}",
            created_at=age,
            data={
                "participants": [f1.id, f2.id],
                "location_id": loc.id,
                "reason_id": reason,
                "status": "active",
                "age_started": age,
                "cultural_tension": tension
            }
        )
        self.qs.add_entity(conflict)
        self.qs.add_relation(f1, conflict, "involved_in")
        self.qs.add_relation(f2, conflict, "involved_in")
        return conflict

    def _spawn_raids(self, age: int, raid_chance=0.1) -> List[Entity]:
        events = []
        raiders = [
            f for f in self.qs.graph.entities.values() 
            if f.type == EntityType.FACTION 
            and f.data.get("culture_vector", {}).get("aggression", 0) > 3
            and "absorbed" not in f.tags
        ]

        # можно использова это:
        # eff_culture = self._get_effective_culture(f)
        
        for raider_faction in raiders:
            if random.random() > raid_chance: continue
            
            loc = self.qs.get_location_of(raider_faction)
            if not loc: continue
            
            current_biome = self.qs.get_biome(loc)
            if not current_biome: continue
            
            neighbor_ids = current_biome.data.get("neighbor_biomes", [])
            if not neighbor_ids: continue
            
            target_biome_id = random.choice(neighbor_ids)
            target_biome = self.qs.get_entity(target_biome_id)
            if not target_biome: continue
            
            target_locs = [
                e for e in self.qs.get_children(target_biome.id, EntityType.LOCATION)
                if "destroyed" not in e.tags
            ]
            if not target_locs: continue
            target_loc = random.choice(target_locs)
            
            victims = [
                f for f in self.qs.get_children(target_loc.id, EntityType.FACTION)
                if "absorbed" not in f.tags
            ]
            if not victims: continue 
            victim = random.choice(victims)
            
            # В рейде тоже учитываем веру (не грабим единоверцев так часто)
            belief_mod = self._get_belief_tension_modifier(raider_faction, victim)
            if belief_mod < 1.0 and random.random() > 0.2: # 80% шанс отменить рейд на "своих"
                continue

            conflict = Entity(
                id=make_id("raid"),
                definition_id='conflict_raid',
                type=EntityType.CONFLICT,
                name=f"Набег {raider_faction.name} на {target_loc.name}",
                created_at=age,
                data={
                    "participants": [raider_faction.id, victim.id],
                    "location_id": target_loc.id,
                    "reason_id": "raid",
                    "status": "active",
                    "age_started": age,
                    "is_raid": True
                }
            )
            self.qs.add_entity(conflict)
            self.qs.add_relation(raider_faction, conflict, "involved_in")
            self.qs.add_relation(victim, conflict, "involved_in")
            
            events.append(self.qs.register_event(
                event_type="raid_start",
                summary=f"«{raider_faction.name}» совершает набег на соседей в «{target_loc.name}»!",
                age=age,
                primary_entity=conflict,
                secondary_entities=[raider_faction, victim]
            ))
            
        return events

    def _spawn_bosses(self, age: int, chance=0.03) -> List[Entity]:
        # Логика боссов осталась без изменений, она самодостаточна
        events = []
        # TODO: добавить эти шаблоны
        biome_boss_map = {
            "biome_mountains": ["boss_dragon_red", "disaster_volcano"],
            "biome_coast": ["boss_kraken"],
            "biome_swamp": ["disaster_plague"],
            "default": []
        }
        
        locations = [l for l in self.qs.graph.entities.values() if l.type == EntityType.LOCATION]
        
        for loc in locations:
            if "boss" in loc.tags or "disaster" in loc.tags: continue

            is_ruins = "ruins" in loc.tags
            current_chance = chance * 3.0 if is_ruins else chance
            
            factions_here = self.qs.get_children(loc.id, EntityType.FACTION)
            if factions_here: 
                current_chance /= 5.0
            
            if random.random() > current_chance: continue
            
            biome = self.qs.get_biome(loc)
            if not biome: continue
            
            possible_bosses = biome_boss_map.get(biome.definition_id, [])
            if not possible_bosses: continue
            
            boss_def_id = random.choice(possible_bosses)
            boss_tmpl = BOSSES_REGISTRY.get(boss_def_id)
            if not boss_tmpl: continue

            name = boss_tmpl.name_template or boss_tmpl.id
            
            boss_entity = Entity(
                id=make_id("boss"),
                definition_id=boss_def_id,
                type=EntityType.FACTION,
                name=name,
                tags=boss_tmpl.tags | {"boss", "hostile"},
                created_at=age,
                parent_id=loc.id,
                data={
                    "culture_vector": boss_tmpl.culture.model_dump(),
                    "role": boss_tmpl.role
                }
            )
            self.qs.add_entity(boss_entity)
            
            if "disaster" in boss_tmpl.tags:
                loc.tags.add("under_siege")
                
            events.append(self.qs.register_event(
                event_type="boss_spawn",
                summary=f"В «{loc.name}» пробудилась угроза: {name}!",
                age=age,
                primary_entity=boss_entity,
                secondary_entities=[loc]
            ))
            
            for victim in factions_here:
                 conflict = Entity(
                    id=make_id("conflict"),
                    definition_id='conflict_boss',
                    type=EntityType.CONFLICT,
                    created_at=age,
                    name=f"Битва с {name}",
                    data={
                        "participants": [boss_entity.id, victim.id],
                        "location_id": loc.id,
                        "reason_id": "survival",
                        "status": "active",
                        "age_started": age
                    }
                )
                 self.qs.add_entity(conflict)
                 self.qs.add_relation(boss_entity, conflict, "involved_in")
                 self.qs.add_relation(victim, conflict, "involved_in")

        return events

    # === RESOLVE LOGIC ===

    def _resolve_single_conflict(self, conflict: Entity, age: int) -> str:
        # Без изменений, базовая логика разрешения работает хорошо
        # Можно добавить влияние веры на шанс "Truce" (перемирия), 
        # но пока оставим как есть для простоты.
        participant_ids = conflict.data["participants"]
        location_id = conflict.data["location_id"]
        location = self.qs.get_entity(location_id)

        if not location: return "aborted"
        
        factions = []
        for fid in participant_ids:
            entity = self.qs.get_entity(fid)
            if (entity and entity.type == EntityType.FACTION and
                entity.parent_id == location_id and
                "absorbed" not in entity.tags and "fled" not in entity.tags and "inactive" not in entity.tags):
                factions.append(entity)
        
        if len(factions) < 2: return "aborted"

        biome = self.qs.get_biome(location)

        if conflict.data.get("is_raid"):
            attacker = factions[0] 
            defender = factions[1]
            att_val = attacker.data.get("culture_vector", {}).get("aggression", 0) + random.randint(1, 10)
            def_val = defender.data.get("culture_vector", {}).get("aggression", 0) + random.randint(1, 10)
            
            if att_val > def_val:
                resources = self.qs.get_children(location.id, EntityType.RESOURCE)
                if resources:
                    stolen_res = random.choice(resources)
                    raider_home = self.qs.get_location_of(attacker)
                    if raider_home:
                        self.qs.move_entity(stolen_res, raider_home, "located_in")
                        stolen_res.tags.add("stolen")
                        return "raid_success_loot"
                return "raid_success_plunder"
            else:
                return "raid_repelled"

        weights = {
            "truce": 20, 
            "absorption": 40, 
            "flight": 20, 
            "new_settlement": 15, 
            "destruction": 5
        }
        
        # Если это Глобальная Война (Крестовый поход), шанс на Перемирие падает до 0
        if conflict.data.get("reason_id") == "religious_crusade":
            weights["truce"] = 0
            weights["destruction"] += 15 # Ярость фанатиков
            weights["absorption"] += 5
        
        outcomes = list(weights.keys())
        probs = list(weights.values())
        chosen = random.choices(outcomes, weights=probs, k=1)[0]

        if chosen == "absorption":
            self._apply_absorption(factions, age)
        elif chosen == "flight":
            self._apply_flight(factions, location, biome)
        elif chosen == "new_settlement":
            self._apply_new_settlement(factions, biome, age)
        elif chosen == "destruction":
            self._apply_destruction(location, age)
        elif chosen == "truce":
            self._apply_truce(factions)

        if location.data is None: location.data = {}
        location.data["last_conflict_age"] = age

        return chosen

    # === ACTIONS ===

    def _apply_absorption(self, factions, age):
        winner = random.choice(factions)
        losers = [f for f in factions if f != winner]
        for loser in losers:
            loser.data["absorbed_by"] = winner.id
            loser.tags.add("absorbed")
            # Переподчиняем детей (персонажей и ресурсы)
            for e in self.qs.get_children(loser.id):
                e.parent_id = winner.id
            self.qs.add_relation(loser, winner, "absorbed_by")

    def _apply_flight(self, factions, location, biome):
        loser = random.choice(factions)
        winner = [f for f in factions if f != loser][0]
        
        if not biome: 
            # Если биома нет, бежать некуда -> поглощение
            return self._apply_absorption([winner, loser], 0)

        # Ищем соседей
        other_locations = [
            e for e in self.qs.get_children(biome.id, EntityType.LOCATION)
            if e.id != location.id
        ]

        if not other_locations:
            # Бежать некуда -> либо смерть, либо поглощение
            if random.random() < 0.5:
                 self._apply_absorption([winner, loser], 0)
            else:
                 # Фракция погибает в пустошах
                 loser.tags.add("inactive")
                 loser.tags.add("dead")
            return

        new_loc = random.choice(other_locations)
        self.qs.move_entity(loser, new_loc, "faction_located_in")
        self.qs.add_relation(loser, new_loc, "fled_to")

    def _apply_new_settlement(self, factions, biome, age):
        if not biome: return
        
        # Генерируем имя
        loc_name = self.naming_service.generate_name(EntityType.LOCATION, {"biome_id": biome.definition_id})
        
        new_location = Entity(
            id=make_id("loc"),
            definition_id="loc_village", 
            type=EntityType.LOCATION,
            name=loc_name,
            tags={"settlement", "new_settlement"},
            created_at=age,
            parent_id=biome.id
        )
        self.qs.add_entity(new_location)

        # Проигравший уходит строить деревню
        if factions:
            loser = random.choice(factions)
            self.qs.move_entity(loser, new_location, "fled_to")

    def _apply_destruction(self, location, age):
        if location.data is None: location.data = {}
        old_name = location.name
        
        location.data["destroyed_in_age"] = age
        location.definition_id = "loc_ruins"
        location.tags = {"ruins", "dangerous", "hidden"}
        location.name = f"Руины «{old_name}»"
        
        # Все в локации умирают
        for e in self.qs.get_children(location.id):
            if e.type in [EntityType.FACTION, EntityType.CHARACTER]:
                e.tags.add("inactive")
                e.tags.add("dead")
            elif e.type == EntityType.RESOURCE:
                e.tags.add("buried") # Ресурс становится кладом

    def _apply_truce(self, factions):
        if len(factions) < 2: return
        for f in factions: f.tags.add("allied")
        for i, f1 in enumerate(factions):
            for f2 in factions[i+1:]:
                self.qs.add_relation(f1, f2, "allied_with")

    # === HELPERS ===

    def _find_belief_id(self, faction: Entity) -> Optional[str]:
        """Локальный помощник для поиска ID веры, если метода нет в QS"""
        if hasattr(self.qs, 'get_belief'):
            b = self.qs.get_belief(faction)
            return b.id if b else None
        
        # Fallback: ищем вручную
        for r in self.qs.graph.relations:
            r_type = r.relation_type.id if hasattr(r.relation_type, 'id') else str(r.relation_type)
            if r.from_entity.id == faction.id and r_type == "believes_in":
                return r.to_entity.id
        return None

    def _get_belief_tension_modifier(self, f1: Entity, f2: Entity, active_wars: List[Entity] = None) -> float:
        b1_id = self._find_belief_id(f1)
        b2_id = self._find_belief_id(f2)

        # 1. Если нет веры - нейтрально
        if not b1_id or not b2_id:
            return 1.0

        # 2. Одна вера - союзники
        if b1_id == b2_id:
            return 0.5 

        # 3. Проверка Глобальных Войн
        if active_wars:
            for war in active_wars:
                # Структура данных войны: {initiator: id, target: id}
                # Проверяем, находятся ли фракции по разные стороны баррикад
                init = war.data.get("initiator_belief")
                target = war.data.get("target_belief")
                
                if (b1_id == init and b2_id == target) or (b1_id == target and b2_id == init):
                    # ЭТО СВЯЩЕННАЯ ВОЙНА! Напряжение запредельное.
                    return 20.0 

        # 4. Разные веры (по умолчанию)
        return 1.2

    def _calculate_cultural_tension(self, f1, f2, active_global_wars: List[Entity] = None) -> float:
        tension = 0.0
        
        # Получаем эффективные вектора (уже с учетом религии!)
        c1 = self._get_effective_culture(f1)
        c2 = self._get_effective_culture(f2)
        
        # 1. Базовые оси (теперь обращаемся как к атрибутам)
        # Агрессивные фракции в принципе создают больше напряжения
        tension += (c1.aggression + c2.aggression) * 0.05

        # Разница в магии (маги vs технократы/варвары)
        if abs(c1.magic_affinity - c2.magic_affinity) > 5:
            tension += 0.5
            
        # Разница в коллективизме (индивидуалисты vs улей)
        if abs(c1.collectivism - c2.collectivism) > 5:
            tension += 0.5

        # 2. Табу и Фетиши (Идеологический конфликт)
        # CultureVector хранит это как set, так что работаем с множествами
        
        # Если то, что одни почитают (revered), для других табу (taboo)
        conflict_ideas = len(c1.taboo & c2.revered) + len(c2.taboo & c1.revered)
        tension += conflict_ideas * 1.0 # Сильный штраф за нарушение табу
        
        # Бонус за общие ценности (снижает напряжение)
        shared_values = len(c1.revered & c2.revered)
        tension -= shared_values * 0.2

        # 3. Различие в тегах (как и раньше)
        diff_tags = len(set(f1.tags) ^ set(f2.tags))
        tension += diff_tags * 0.05
        
        # Нормализация (чтобы не ушло в минус)
        base_tension = max(0.1, min(5.0, tension + 1.0))
        
        # 4. ВЛИЯНИЕ РЕЛИГИИ (Как "Свой-Чужой")
        # Мы уже учли цифры (aggression), но теперь нужен именно статус отношений
        belief_mod = self._get_belief_tension_modifier(f1, f2, active_global_wars)
        
        final_tension = base_tension * belief_mod
        return final_tension

    def _determine_dispute_reason(self, factions, loc) -> str:
        resources = self.qs.get_children(loc.id, EntityType.RESOURCE)
        if resources:
            return "res_conflict"
        for f in factions:
            if "power" in f.tags or "imperial" in f.tags:
                return "power_struggle"
        return "ideological"
    
    def _get_effective_culture(self, faction: Entity) -> CultureVector:
        # 1. База фракции
        base_data = faction.data.get("culture_vector", {})
        culture = CultureVector(**base_data)

        # 2. Религия
        if hasattr(self.qs, 'get_belief'):
            belief = self.qs.get_belief(faction)
            if belief and "modifiers" in belief.data:
                belief_mods = CultureVector(**belief.data["modifiers"])
                culture = culture + belief_mods

        # 3. === НОВОЕ: Влияние Лидера ===
        # Нам нужен хелпер get_leader в WorldQueryService, или ищем вручную
        leader = self._find_leader(faction) 
        if leader and "culture_vector" in leader.data:
            leader_mods = CultureVector(**leader.data["culture_vector"])
            
            # ВАЖНО: Личность лидера накладывается сверху
            # Можно добавить коэффициент влияния (например, x0.5 или x1.0)
            culture = culture + leader_mods

        return culture

    def _find_leader(self, faction: Entity) -> Optional[Entity]:
        # Простой поиск по связям "leads" (инверсия leads -> faction)
        # Так как связь направлена Leader -> Faction ("leads"), ищем:
        for r in self.qs.graph.relations:
            # r.from = Leader, r.to = Faction
            if r.to_entity.id == faction.id and str(r.relation_type) == "leads":
                # Проверяем, жив ли он
                if "dead" not in r.from_entity.tags:
                    return r.from_entity
        return None

    def _generate_summary(self, conflict, outcome):
        loc_id = conflict.data.get('location_id')
        loc = self.qs.get_entity(loc_id)
        loc_name = loc.name if loc else "???"
        
        participants = conflict.data.get("participants", [])
        names = []
        for pid in participants:
            p = self.qs.get_entity(pid)
            if p: names.append(p.name)
        
        names_str = " vs ".join(names)
        
        map_outcome = {
            "truce": "Заключено перемирие",
            "absorption": "Одна сторона поглотила другую",
            "flight": "Проигравшие бежали",
            "new_settlement": "Проигравшие основали новое поселение",
            "destruction": "Локация уничтожена",
            "raid_success_loot": "Успешный грабеж ресурсов",
            "raid_success_plunder": "Разграбление поселения",
            "raid_repelled": "Набег отбит"
        }
        
        text = map_outcome.get(outcome, outcome)
        return f"Конфликт ({names_str}) в {loc_name}: {text}"