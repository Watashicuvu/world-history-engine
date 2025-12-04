import random
import uuid
from typing import List, Optional

from src.models.generation import EntityType, Entity
from src.services.world_query_service import WorldQueryService
from src.naming import NamingService
from src.models.registries import RESOURCE_REGISTRY, BIOME_REGISTRY, LOCATION_REGISTRY
from src.utils import make_id


class LifecycleSystem:
    def __init__(self, query_service: WorldQueryService, naming_service: NamingService):
        self.qs = query_service
        self.naming_service = naming_service

    def process_leader_decay(self, age: int, chance: float = 0.02) -> List[Entity]:
        events = []
        leaders = [e for e in self.qs.graph.entities.values() 
                   if e.type == EntityType.CHARACTER and "inactive" not in e.tags]
        
        for leader in leaders:
             if random.random() < chance:
                leader.tags.add("inactive")
                leader.tags.add("dead")
                
                # === БЕЗОПАСНОЕ УДАЛЕНИЕ СВЯЗИ ===
                new_relations = []
                for r in self.qs.graph.relations:
                    try:
                        # Защита от отсутствия атрибутов
                        r_type_id = r.relation_type.id if hasattr(r.relation_type, 'id') else str(r.relation_type)
                        
                        # Если это связь лидера - пропускаем (удаляем)
                        if r.from_entity.id == leader.id and r_type_id == "leads":
                            continue
                        new_relations.append(r)
                    except Exception:
                        continue # Удаляем битые связи
                
                self.qs.graph.relations = new_relations
                # ================================
                
                faction_id = leader.data.get("faction_id")
                faction = self.qs.get_entity(faction_id) if faction_id else None

                events.append(
                    self.qs.register_event(
                        event_type="leader_death",
                        summary=f"Умер лидер {leader.name}",
                        age=age,
                        primary_entity=leader,
                        secondary_entities=[faction] if faction else []
                    )
                )
        return events

    def _handle_conquered_leaders(self, loser_faction_id: str, winner_faction: Optional[Entity] = None, age: int = 0):
        """
        Решает судьбу элиты уничтоженной фракции.
        """
        # 1. Находим живых персонажей, принадлежащих этой фракции
        # Проверяем parent_id и тип CHARACTER
        leaders = [
            e for e in self.qs.graph.entities.values() 
            if e.parent_id == loser_faction_id 
            and e.type == EntityType.CHARACTER 
            and "dead" not in e.tags
        ]

        if not leaders:
            return

        print(f"[Lifecycle] Processing fate for {len(leaders)} leaders of {loser_faction_id}")

        for leader in leaders:
            # Если победителя нет (развал), то 50/50 казнь или изгнание. 
            # Если есть победитель — шанс на вербовку.
            roll = random.random()
            
            if not winner_faction:
                fate = "exile" if roll > 0.5 else "execution"
            else:
                if roll < 0.3:
                    fate = "execution"
                elif roll < 0.7:
                    fate = "exile"
                else:
                    fate = "recruit"

            # === ЛОГИКА СУДЕБ ===
            if fate == "execution":
                leader.tags.add("dead")
                leader.tags.add("executed")
                leader.tags.discard("active")
                # Технически можно оставить parent_id как "могилу" или null
                
                self.qs.register_event(
                    event_type="execution",
                    summary=f"{leader.name} был казнен после падения фракции.",
                    age=age,
                    primary_entity=leader,
                    secondary_entities=[winner_faction] if winner_faction else []
                )

            elif fate == "exile":
                # Лидер сбегает в случайную локацию
                # Пытаемся найти локацию, отличную от текущей (если возможно)
                all_locs = [e for e in self.qs.graph.entities.values() if e.type == EntityType.LOCATION]
                if all_locs:
                    new_home = random.choice(all_locs)
                    leader.parent_id = new_home.id
                    leader.tags.add("exile")
                    leader.tags.add("wanderer")
                    # Удаляем связь 'leads', если она была
                    # (Логика очистки связей должна быть в remove_relation, но здесь мы просто меняем parent)
                    
                    self.qs.register_event(
                        event_type="exile",
                        summary=f"{leader.name} бежал в изгнание в {new_home.name}.",
                        age=age,
                        primary_entity=leader,
                        secondary_entities=[new_home]
                    )

            elif fate == "recruit" and winner_faction:
                # Переход на сторону врага
                leader.parent_id = winner_faction.id
                leader.tags.add("traitor") # Клеймо
                leader.tags.add("vassal")
                
                self.qs.register_event(
                    event_type="recruitment",
                    summary=f"{leader.name} преклонил колено перед {winner_faction.name}.",
                    age=age,
                    primary_entity=leader,
                    secondary_entities=[winner_faction]
                )

    def process_overcrowding(self, age: int) -> List[Entity]:
        """
        Компенсирующий механизм: если локация переполнена, запускает кризис.
        """
        events = []
        locations = [l for l in self.qs.graph.entities.values() if l.type == EntityType.LOCATION]

        for loc in locations:
            # Получаем лимиты из шаблона (или сохраненные в data)
            if not loc.data:
                loc.data = {}

            loc_limits = loc.data.get("limits", {})
            if not loc_limits:
                # Пытаемся достать из реестра, если в data пусто
                tmpl = LOCATION_REGISTRY.get(loc.definition_id)
                if tmpl: loc_limits = tmpl.limits
            
            # Лимит фракций
            max_factions = loc_limits.get("Faction", 2)
            factions = self.qs.get_children(loc.id, EntityType.FACTION)
            active_factions = [f for f in factions if "absorbed" not in f.tags and "dead" not in f.tags]

            if len(active_factions) > max_factions:
                # === КРИЗИС ПЕРЕНАСЕЛЕНИЯ ===
                loc.tags.add("overcrowded")
                
                # Шанс на событие уменьшения популяции (голод/болезнь/бунт)
                if random.random() < 0.5:
                    victim = random.choice(active_factions)
                    
                    # Два варианта: изгнание или гибель
                    #if random.random() < 0.5:
                    victim.tags.add("dead")
                    victim.tags.add("starved")
                    summary = f"Фракция {victim.name} вымерла от голода из-за перенаселения в {loc.name}"
                    ev_type = "famine"
                    # else:
                    #     # Принудительное выселение (попытка миграции)
                    #     # TODO ну тут безобразие снова
                    #     # В простейшем случае - просто удаляем (ушли в неизвестность)
                    #     victim.tags.add("exiled_by_crowd")
                    #     victim.parent_id = None # Ушли в никуда (или можно сделать логику flight)
                    #     summary = f"{victim.name} были вынуждены покинуть переполненный {loc.name}"
                    #     ev_type = "forced_migration"

                    events.append(self.qs.register_event(
                        event_type=ev_type,
                        summary=summary,
                        age=age,
                        primary_entity=loc,
                        secondary_entities=[victim]
                    ))
            else:
                loc.tags.discard("overcrowded")

        return events

    def process_resource_decay(self, age: int, chance: float = 0.03) -> List[Entity]:
        events = []
        active_resources = [
            e for e in self.qs.graph.entities.values()
            if e.type == EntityType.RESOURCE and "depleted" not in e.tags
        ]
        
        for res in active_resources:
            if random.random() < chance:
                res.tags.add("depleted")
                
                # Если ресурс не возобновляемый — помечаем как "inactive" (удаляем навсегда)
                tmpl = RESOURCE_REGISTRY.get(res.definition_id)
                # Если в шаблоне нет флага renewable, считаем его конечным
                is_renewable = getattr(tmpl, 'renewable', False) if tmpl else False
                
                if not is_renewable:
                    res.tags.add("inactive")
                
                loc = self.qs.get_location_of(res)
                
                events.append(self.qs.register_event(
                    event_type="resource_depleted",
                    summary=f"Ресурс «{res.name}» истощён",
                    age=age,
                    primary_entity=res,
                    secondary_entities=[loc] if loc else []
                ))
        return events

    def process_resource_regrowth(self, age: int, chance: float = 0.1) -> List[Entity]:
        events = []
        depleted_resources = [
            e for e in self.qs.graph.entities.values()
            if e.type == EntityType.RESOURCE 
            and "depleted" in e.tags 
            and "inactive" not in e.tags # Только те, что еще живы
        ]
        
        for res in depleted_resources:
            if random.random() < chance:
                res.tags.discard("depleted")
                loc = self.qs.get_location_of(res)
                
                events.append(self.qs.register_event(
                    event_type="resource_regrowth",
                    summary=f"Ресурс «{res.name}» восстановился",
                    age=age,
                    primary_entity=res,
                    secondary_entities=[loc] if loc else []
                ))
        return events

    def process_new_resources(self, age: int, chance: float = 0.05) -> List[Entity]:
        events = []
        locations = [l for l in self.qs.graph.entities.values() if l.type == EntityType.LOCATION]
        
        for loc in locations:
            if random.random() >= chance: continue
            
            # Проверка слотов (limits)
            loc_tmpl = LOCATION_REGISTRY.get(loc.definition_id)
            if loc_tmpl:
                max_res = loc_tmpl.limits.get("Resource", 1)
                curr_res = len(self.qs.get_children(loc.id, EntityType.RESOURCE))
                if curr_res >= max_res: continue

            biome = self.qs.get_biome(loc)
            if not biome: continue
            
            biome_tmpl = BIOME_REGISTRY.get(biome.definition_id)
            if not biome_tmpl or not biome_tmpl.available_resources: continue

            res_def_id = random.choice(biome_tmpl.available_resources)
            res_tmpl = RESOURCE_REGISTRY.get(res_def_id)
            if not res_tmpl: continue

            # Выбор редкости
            rarities = [opt.rarity for opt in res_tmpl.rarity_options]
            weights = [opt.weight for opt in res_tmpl.rarity_options]
            chosen_rarity = random.choices(rarities, weights=weights, k=1)[0]

            context = {
                "biome_id": biome.definition_id,
                "base_resource": res_tmpl.name_key,
                "rarity": chosen_rarity
            }
            name = self.naming_service.generate_name(EntityType.RESOURCE, context) or res_tmpl.name_key
            
            entity = Entity(
                id=make_id("res"),
                definition_id=res_def_id,
                type=EntityType.RESOURCE,
                name=name,
                tags=res_tmpl.tags | {chosen_rarity.value},
                created_at=age,
                parent_id=loc.id
            )
            self.qs.add_entity(entity)
            self.qs.add_relation(entity, loc, "located_in") # Явная связь для ресурса
            
            events.append(self.qs.register_event(
                event_type="resource_discovered",
                summary=f"В {loc.name} найден новый ресурс: {name}",
                age=age,
                primary_entity=entity,
                secondary_entities=[loc]
            ))
        return events