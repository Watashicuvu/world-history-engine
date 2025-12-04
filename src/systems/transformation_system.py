import random
import uuid
from typing import List

from src.models.generation import EntityType, Entity
from src.services.world_query_service import WorldQueryService
from src.naming import NamingService
from src.models.registries import TRANSFORMATION_REGISTRY, BIOME_REGISTRY, LOCATION_REGISTRY
from src.utils import make_id

def make_id(prefix: str) -> str:
    return f"{prefix}_{str(uuid.uuid4())[:6]}"

class TransformationSystem:
    def __init__(self, query_service: WorldQueryService, naming_service: NamingService):
        self.qs = query_service
        self.naming_service = naming_service

    def process_transformations(self, age: int) -> List[Entity]:
        events = []
        locations = [l for l in self.qs.graph.entities.values() if l.type == EntityType.LOCATION]
        rules = list(TRANSFORMATION_REGISTRY.get_all().values())
        
        for loc in locations:
            for rule in rules:
                # 1. Проверка тега
                if rule.requires_tag not in loc.tags: continue
                
                # 2. Проверка населения
                occupants = self.qs.get_children(loc.id, EntityType.FACTION)
                has_faction = len(occupants) > 0
                if rule.needs_faction != has_faction: continue
                
                # 3. Время (если указано)
                if rule.min_age_empty:
                    destroyed_at = loc.data.get("destroyed_in_age", 0) if loc.data else 0
                    if age - destroyed_at < rule.min_age_empty: continue

                # 4. Шанс
                if random.random() > rule.chance: continue
                
                # === ПРИМЕНЕНИЕ ===
                target_def_id = rule.target_def
                
                # Особый случай: природа забирает руины
                if target_def_id == "loc_wild_ruins":
                    loc.tags.discard(rule.requires_tag)
                    loc.tags.add("wild")
                    loc.name = f"Заросшие {loc.name}"
                    events.append(self.qs.register_event(
                        "nature_reclaim", 
                        f"«{loc.name}» окончательно поглощена природой", 
                        age, 
                        loc
                    ))
                    continue

                # Трансформация в поселение
                target_tmpl = LOCATION_REGISTRY.get(target_def_id)
                if not target_tmpl: continue
                
                loc.definition_id = target_def_id
                loc.tags = target_tmpl.tags.copy() | {"transformed"}
                loc.capacity = target_tmpl.capacity
                
                builder = occupants[0] if occupants else None
                old_name = loc.name
                
                # Генерация нового имени
                base_name = self.naming_service.generate_name(EntityType.LOCATION, {"biome_id": "default"})
                # Чистим старое имя от префиксов
                clean_old = old_name.replace("Руины ", "").replace("Неизведанная ", "")
                loc.name = f"{base_name} (бывш. {clean_old})"
                
                events.append(self.qs.register_event(
                    event_type="transformation",
                    summary=f"{rule.narrative} «{old_name}» -> «{loc.name}»",
                    age=age,
                    primary_entity=loc,
                    secondary_entities=[builder] if builder else []
                ))
                break # Только одна трансформация за ход для локации
        return events

    def process_new_land_discovery(self, age: int, chance_per_biome: float = 0.1) -> List[Entity]:
        events = []
        biomes = [e for e in self.qs.graph.entities.values() if e.type == EntityType.BIOME]
        
        for biome in biomes:
            if random.random() > chance_per_biome: continue
            
            # Проверяем capacity биома
            tmpl = BIOME_REGISTRY.get(biome.definition_id)
            current_locs = len(self.qs.get_children(biome.id, EntityType.LOCATION))
            if tmpl and tmpl.capacity and current_locs >= tmpl.capacity:
                continue

            if not tmpl or not tmpl.allowed_locations: continue
            
            # Фильтруем только "дикие" типы для открытия
            wild_candidates = []
            for loc_id in tmpl.allowed_locations:
                l_tmpl = LOCATION_REGISTRY.get(loc_id)
                if l_tmpl and ("hidden" in l_tmpl.tags or "nature" in l_tmpl.tags or "resource" in l_tmpl.tags):
                    wild_candidates.append(l_tmpl)
            
            target_tmpl = random.choice(wild_candidates) if wild_candidates else LOCATION_REGISTRY.get(random.choice(tmpl.allowed_locations))
            if not target_tmpl: continue

            # Создаем новую локацию
            new_loc_name = self.naming_service.generate_name(EntityType.LOCATION, {"biome_id": biome.definition_id})
            if "hidden" in target_tmpl.tags: 
                new_loc_name = f"Неизведанная {new_loc_name}"

            new_loc = Entity(
                id=make_id("loc"),
                definition_id=target_tmpl.id,
                type=EntityType.LOCATION,
                name=new_loc_name,
                tags=target_tmpl.tags | {"wild", "discovered"},
                capacity=target_tmpl.capacity,
                parent_id=biome.id,
                created_at=age
            )
            self.qs.add_entity(new_loc)
            
            siblings = self.qs.get_children(biome.id, EntityType.LOCATION)
            spatial_data = self.qs.spatial.assign_slot(new_loc, biome, siblings)
            if not new_loc.data:
                new_loc.data = {}
            new_loc.data.update(spatial_data)
            self.qs._update_absolute_coordinates(new_loc, biome)
            
            events.append(self.qs.register_event(
                event_type="discovery",
                summary=f"Открыта новая локация в {biome.name}: {new_loc_name}",
                age=age,
                primary_entity=new_loc,
                secondary_entities=[biome]
            ))
            
        return events

    def process_expansions(self, age: int, expansion_chance=0.1) -> List[Entity]:
        events = []
        factions = [f for f in self.qs.graph.entities.values() 
                   if f.type == EntityType.FACTION and "absorbed" not in f.tags]
        
        for faction in factions:
            if random.random() > expansion_chance: continue
            
            loc = self.qs.get_location_of(faction)
            if not loc: continue
            
            biome = self.qs.get_biome(loc)
            if not biome: continue
            
            neighbors = self.qs.get_children(biome.id, EntityType.LOCATION)
            possible_targets = [l for l in neighbors if l.id != loc.id]
            
            # ИСПРАВЛЕНИЕ: Проверяем, есть ли куда расширяться
            valid_targets = []
            for t in possible_targets:
                # Получаем лимит
                limit = 2 # Дефолт
                tmpl = LOCATION_REGISTRY.get(t.definition_id) 
                if tmpl: limit = tmpl.limits.get("Faction", 2)
                elif t.data and "limits" in t.data: limit = t.data["limits"].get("Faction", 2)
                
                curr = len(self.qs.get_children(t.id, EntityType.FACTION))
                if curr < limit:
                    valid_targets.append(t)
            
            if possible_targets:
                target = random.choice(possible_targets)
                
                context = {"biome_id": biome.definition_id, "role": faction.data.get("role", "default")}
                new_name = self.naming_service.generate_name(EntityType.FACTION, context)
                
                new_faction = Entity(
                    id=make_id("faction"),
                    definition_id=faction.definition_id,
                    type=EntityType.FACTION,
                    name=f"{new_name} (Филиал)",
                    tags=faction.tags.copy(),
                    parent_id=target.id,
                    created_at=age,
                    data=faction.data.copy() if faction.data else {}
                )
                self.qs.add_entity(new_faction)
                
                self.qs.add_relation(faction, target, "expanded_to") 
                self.qs.add_relation(new_faction, faction, "splintered_from") 

                events.append(self.qs.register_event(
                    event_type="expansion",
                    summary=f"{faction.name} открыла филиал в {target.name}",
                    age=age,
                    primary_entity=faction,
                    secondary_entities=[target, new_faction]
                ))

        return events