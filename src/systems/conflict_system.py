import random
import itertools
from typing import List, Optional, Tuple

from src.models.templates_schema import CultureVector, LocationTemplate
from src.models.generation import Entity, EntityType
from src.services.world_query_service import WorldQueryService
from src.naming import NamingService
from src.models.registries import BOSSES_REGISTRY, LOCATION_REGISTRY
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
        events = []
        locations = [l for l in self.qs.graph.entities.values() if l.type == EntityType.LOCATION]
        
        # Предварительно группируем боссов по биомам для оптимизации (можно вынести в __init__)
        # Но для надежности делаем перебор внутри цикла (или кэшируем)
        
        for loc in locations:
            # 1. Пропускаем, если тут уже есть босс
            if "boss" in loc.tags or "disaster" in loc.tags: continue

            # 2. Логика шансов
            is_ruins = "ruins" in loc.tags
            current_chance = chance * 3.0 if is_ruins else chance
            
            factions_here = self.qs.get_children(loc.id, EntityType.FACTION)
            if factions_here: 
                current_chance /= 5.0
            
            if random.random() > current_chance: continue
            
            # 3. Получаем биом
            biome = self.qs.get_biome(loc)
            if not biome: continue
            
            # === ИЗМЕНЕНИЕ 1: Динамический поиск по шаблонам ===
            possible_boss_templates = []
            
            for tmpl in BOSSES_REGISTRY.get_all().values():
                # Если список биомов пуст - считаем, что босс глобальный (или наоборот, запрещаем)
                # Здесь логика: если биом локации есть в allowed_biomes босса
                if biome.definition_id in tmpl.allowed_biomes:
                    possible_boss_templates.append(tmpl)
            
            if not possible_boss_templates: continue
            
            boss_tmpl = random.choice(possible_boss_templates)

            # === ИЗМЕНЕНИЕ 2: Правильный вызов нейминга ===
            # Не присваиваем boss_tmpl.name_template напрямую!
            
            naming_context = {
                "biome_id": biome.definition_id,
                "name_template": boss_tmpl.name_template, # Передаем шаблон сервису
                "tags": boss_tmpl.tags,
                "creature_type": boss_tmpl.creature_type
            }
            
            # Генерируем финальное имя (например: "Чума «Черная Смерть»")
            final_name = self.naming_service.generate_name(EntityType.BOSS, naming_context)
            
            boss_entity = Entity(
                id=make_id("boss"),
                definition_id=boss_tmpl.id,
                type=EntityType.BOSS, 
                name=final_name, # Используем уже сгенерированное имя
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
                summary=f"В «{loc.name}» пробудилась угроза: {final_name}!",
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
                    name=f"Битва с {final_name}",
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
        
        candidates = []
        for loc in other_locations:
            cap = loc.data.get("limits", {}).get("Faction", 2)
            curr = len([f for f in self.qs.get_children(loc.id, EntityType.FACTION) if "absorbed" not in f.tags])
            if curr < cap:
                candidates.append(loc)
        
        target_loc = None
        if candidates:
            # Если есть свободные, выбираем из них
            target_loc = random.choice(candidates)
        else:
            # Если свободных нет, выбираем любую, но создаем ПЕРЕНАСЕЛЕНИЕ
            target_loc = random.choice(other_locations)
            # LifecycleSystem.process_overcrowding потом с этим разберется

        #new_loc = random.choice(other_locations)
        self.qs.move_entity(loser, target_loc, "faction_located_in")
        self.qs.add_relation(loser, target_loc, "fled_to")

    def _get_parent_coord(self, parent_id: str) -> Optional[tuple]:
        parent = self.qs.get_entity(parent_id)
        if parent and parent.data and "coord" in parent.data:
            return parent.data["coord"]
        return None

    def _apply_new_settlement(self, factions, biome, age):
        if not biome: 
            return
        
        from src.models.registries import BIOME_REGISTRY
        biome_tmpl = BIOME_REGISTRY.get(biome.definition_id)
        
        current_locs = self.qs.get_children(biome.id, EntityType.LOCATION)
        if biome_tmpl and len(current_locs) >= (biome_tmpl.capacity or 10):
            # Биом переполнен, новые поселения не могут быть основаны
            # Проигравшие становятся разбойниками или погибают
            if factions:
                loser = random.choice(factions)
                loser.tags.add("wandering_bandits")
                # Можно добавить событие "Ушли в леса"
            return
        
        # 1. Выбираем подходящий тип для нового поселения.
        # Чтобы не плодить "Деревни", проигравшие строят временные или малые убежища.
        # Можно добавить логику: если биом "wild", то "loc_hunter_camp", иначе "loc_hamlet".
        # TODO: убрать хардкод
        starter_templates = ["loc_hamlet", "loc_hunter_camp", "loc_village"]
        
        # Пытаемся найти валидный шаблон
        loc_def_id = random.choice(starter_templates)
        template: LocationTemplate = LOCATION_REGISTRY.get(loc_def_id)
        
        # Если вдруг шаблона нет (или реестр не загружен), фоллбек на хардкод, 
        # но лучше упасть с ошибкой или взять дефолт
        if not template:
            print(f"Warning: Template {loc_def_id} not found in registry")
            return

        # 2. Генерируем имя (используем naming_service как и раньше)
        loc_name = self.naming_service.generate_name(
            EntityType.LOCATION, 
            {"biome_id": biome.definition_id}
        )
        
        # 3. Честное создание сущности на основе шаблона
        # Объединяем теги шаблона с тегом события
        combined_tags = template.tags | {"new_settlement", "refugee_camp"}
        
        new_location = Entity(
            id=make_id("loc"),
            definition_id=loc_def_id,
            type=EntityType.LOCATION,
            name=loc_name,
            
            # ВАЖНО: Берем вместимость из шаблона
            capacity=template.capacity,
            
            tags=combined_tags,
            created_at=age,
            parent_id=biome.id,
            
            # Сохраняем лимиты в data, чтобы потом проверять их при наполнении
            data={
                "limits": template.limits,
                "origin_event": "conflict_flee"
            }
        )
        
        self.qs.add_entity(new_location)

        siblings = self.qs.get_children(biome.id, EntityType.LOCATION)
        spatial_data = self.qs.spatial.assign_slot(new_location, biome, siblings)
        if not new_location.data:
                new_location.data = {}
        new_location.data.update(spatial_data)
        self.qs._update_absolute_coordinates(new_location, biome)

        # 4. Перемещение проигравшей фракции
        if factions:
            loser = random.choice(factions)
            self.qs.move_entity(loser, new_location, "fled_to")
            
            # Опционально: можно снизить силу фракции, так как они бежали
            # loser.data["strength"] = max(1, loser.data.get("strength", 5) - 2)

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
    
    def calculate_power(self, faction: Entity) -> float:
        """
        Рассчитывает динамическую силу фракции.
        Формула: Base + (Leaders * 10) + (Vassals * 5) + (Resources * 2)
        """
        # 1. Базовая сила из шаблона (или дефолт)
        base_power = faction.data.get("base_power", 10)
        
        # 2. Сила Лидеров
        # Ищем всех персонажей, которые привязаны к фракции (parent_id) 
        # и не имеют тегов dead/inactive
        # (Используем qs.get_children, если он есть, или фильтруем вручную)
        leaders = [
            e for e in self.qs.graph.entities.values()
            if e.parent_id == faction.id 
            and e.type == EntityType.CHARACTER 
            and "inactive" not in e.tags
        ]
        # Каждый лидер дает ощутимый бонус. 
        # Если лидер имеет тег "general" или "hero", можно давать больше
        leader_power = sum(20 if "hero" in l.tags else 10 for l in leaders)

        # 3. Вассалы (поглощенные фракции)
        # Это фракции, у которых parent_id = наша фракция
        vassals = [
            e for e in self.qs.graph.entities.values()
            if e.parent_id == faction.id
            and e.type == EntityType.FACTION
            and "dead" not in e.tags
        ]
        vassal_power = len(vassals) * 15

        # 4. Ресурсы в локации (Опционально)
        # Если фракция владеет локацией, она получает силу от ресурсов
        # (Упрощенно: считаем ресурсы в локации, где сидит фракция)
        resource_power = 0
        location = self.qs.get_entity(faction.parent_id)
        if location:
            resources = [
                e for e in self.qs.graph.entities.values()
                if e.parent_id == location.id and e.type == EntityType.RESOURCE
            ]
            resource_power = len(resources) * 5

        total = base_power + leader_power + vassal_power + resource_power
        
        # Сохраняем в data для UI/Debugging
        faction.data["current_power"] = total
        return total
    
    def _check_imperial_stability(self, faction: Entity) -> float:
        """
        Возвращает риск распада (0.0 - 1.0).
        Чем больше владений превышает лимит, тем выше риск.
        """
        # 1. Считаем владения
        # Вассалы (другие фракции под контролем)
        vassals = [
            e for e in self.qs.graph.entities.values()
            if e.parent_id == faction.id and e.type == EntityType.FACTION
            and "dead" not in e.tags
        ]
        
        # Территории (локации под контролем)
        # Если ваша модель подразумевает, что фракция является "родителем" локации
        territories = [
            e for e in self.qs.graph.entities.values()
            if e.parent_id == faction.id and e.type == EntityType.LOCATION
        ]

        # 2. Вычисляем нагрузку (Strain)
        # Вассалами управлять сложнее, чем прямой территорией
        strain = len(territories) * 1.0 + len(vassals) * 2.5
        
        # 3. Вычисляем лимит (Capacity)
        # Базовая сила (из шаблона) + Бонусы от лидеров
        base_cap = faction.data.get("base_power", 10)
        # Умные лидеры помогают управлять империей
        leaders = [
            e for e in self.qs.graph.entities.values()
            if e.parent_id == faction.id and e.type == EntityType.CHARACTER
            and "dead" not in e.tags
        ]
        admin_bonus = len(leaders) * 5
        
        capacity = base_cap + admin_bonus
        
        # 4. Расчет риска
        if strain <= capacity:
            return 0.0
        
        # Перегрузка!
        overstretch = strain - capacity
        # Шанс растет на 5% за каждую единицу перегрузки
        risk = min(0.8, overstretch * 0.05) 
        
        return risk

    def _calculate_cultural_tension(self, f1, f2, active_global_wars: Optional[List[Entity]] = None) -> float:
        # 1. Получаем полные вектора (со сложением базы, веры и лидеров)
        c1 = self._get_effective_culture(f1)
        c2 = self._get_effective_culture(f2)
        
        # 2. Настраиваем веса для осей
        # Агрессия важнее магии для расчета шанса войны
        weights = {
            "aggression": 0.2,      # Агрессия вносит больший вклад
            "magic_affinity": 0.1, 
            "collectivism": 0.1
        }
        
        # 3. Элегантный расчет через метод класса
        base_tension = c1.distance_to(c2, weights)
        
        # Дополнительная логика для "Агрессоров" (по запросу: aggression обрабатывать особо)
        # Если обе фракции агрессивны (сумма > 10), напряжение растет само по себе,
        # даже если их уровни агрессии равны (distance = 0).
        total_aggression = c1.aggression + c2.aggression
        if total_aggression > 5:
            base_tension += total_aggression * 0.05

        # Нормализация
        final_tension = max(0.1, min(10.0, base_tension + 1.0))

        # 4. Влияние Религии (статус отношений)
        belief_mod = self._get_belief_tension_modifier(f1, f2, active_global_wars)
        
        return final_tension * belief_mod

    def _determine_dispute_reason(self, factions, loc) -> str:
        resources = self.qs.get_children(loc.id, EntityType.RESOURCE)
        if resources:
            return "res_conflict"
        for f in factions:
            if "power" in f.tags or "imperial" in f.tags:
                return "power_struggle"
        return "ideological"
    
    def _get_effective_culture(self, faction: Entity) -> CultureVector:
        # База
        # Pydantic сам подставит нули для отсутствующих полей
        culture = CultureVector(**faction.data.get("culture_vector", {}))

        # Вера (Сложение)
        if hasattr(self.qs, 'get_belief'):
            belief = self.qs.get_belief(faction)
            if belief and "modifiers" in belief.data:
                # modifiers веры могут содержать только часть полей, это ок
                belief_mods = CultureVector(**belief.data["modifiers"])
                culture = culture + belief_mods

        # Лидер (Сложение и Умножение)
        leader = self._find_leader(faction) 
        if leader:
            # Предположим, у лидера есть "traits_modifiers" (вектор)
            # и "influence" (скаляр, например, харизма/10)
            
            # Пример: Лидер "Warlord" добавляет агрессию
            if "culture_vector" in leader.data:
                leader_mods = CultureVector(**leader.data["culture_vector"])
                
                # Пример логики: безумный король влияет сильнее (умножение)
                influence_factor = 1.0
                if "mad" in leader.tags:
                    influence_factor = 1.5
                
                # (Culture + LeaderVec) * Influence ? 
                # Или просто Culture + (LeaderVec * Influence) - логичнее второе
                culture = culture + (leader_mods * influence_factor)

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