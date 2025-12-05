import random
import uuid
from typing import List, Optional

# Новые импорты
from src.models.registries import BIOME_REGISTRY, LOCATION_REGISTRY, RESOURCE_REGISTRY, FACTION_REGISTRY
from src.models.templates_schema import BiomeTemplate, FactionTemplate, LocationTemplate, ResourceTemplate
from src.models.generation import (
    EntityType, Entity, RelationType, World, WorldGraph
)
from src.naming import ContextualNamingService, NamingService
from src.spatial_layout_gen import SpatialLayout, SpatialLayoutGenerator
from src.utils import save_spatial_layout_to_json
from src.template_loader import load_all_templates 

def make_id(prefix: str) -> str:
    return f"{prefix}_{str(uuid.uuid4())[:6]}"

class WorldGenerator:
    def __init__(self, naming_service: Optional[NamingService] = None):
        self.naming_service = naming_service or ContextualNamingService()
        
        # 1. Загрузка данных в Реестры (если еще не загружены)
        # Лучше вынести это во внешний main.py, но для надежности можно тут
        if not BIOME_REGISTRY.get_all():
             load_all_templates() # Ваша функция, которая читает YAML и делает REGISTRY.register(...)
    
    def _generate_unique_biome_name(self, base_name: str, biome_id: str, all_names: List[str]) -> str:
        # Пытаемся сгенерировать красивое имя 10 раз
        for _ in range(10):
            context = {"biome_id": biome_id, "base_name": base_name}
            name = self.naming_service.generate_name(EntityType.BIOME, context)
            if name not in all_names:
                return name
        
        # Если не вышло (закончились варианты), используем цифры
        counter = 1
        while f"{base_name} {counter}" in all_names:
            counter += 1
        return f"{base_name} {counter}"

    def generate_from_spatial_layout(self, layout: SpatialLayout) -> World:
        graph = WorldGraph()
        biomes_entities: List[Entity] = []
        used_names: List[str] = []
        biome_id_to_entity_id = {} # map: biome_def_id -> entity_uuid (так не пойдет, нужен coord -> uuid)
        coord_to_entity_id = {}

        occupied = layout.occupied_cells()
        if not occupied:
            raise ValueError("Spatial layout has no biomes placed")

        # 1. Генерация сущностей БИОМОВ
        for coord, biome_id in occupied.items():
            # Получаем шаблон из реестра (Pydantic модель)
            tmpl: BiomeTemplate = BIOME_REGISTRY.get(biome_id)
            if not tmpl:
                print(f"Error: Biome '{biome_id}' missing in registry")
                continue

            unique_name = self._generate_unique_biome_name(tmpl.name, biome_id, used_names)
            used_names.append(unique_name)

            biome_entity = Entity(
                id=make_id("biome"),
                definition_id=biome_id, # Храним ID шаблона
                type=EntityType.BIOME,
                name=unique_name,
                tags=tmpl.tags,
                capacity=tmpl.capacity,
                data={"coord": coord}
            )
            coord_to_entity_id[coord] = biome_entity.id
            graph.add_entity(biome_entity)
            biomes_entities.append(biome_entity)

        # 2. Генерация ЛОКАЦИЙ
        for biome_entity in biomes_entities:
            coord = biome_entity.data["coord"]
            neighbors_coords = layout.neighbors(coord)
            neighbor_ids = []
            for nc in neighbors_coords:
                if nc in coord_to_entity_id:
                    neighbor_ids.append(coord_to_entity_id[nc])
            
            biome_entity.data["neighbor_biomes"] = neighbor_ids # Сохраняем список ID сущностей-соседей
            
            tmpl: BiomeTemplate = BIOME_REGISTRY.get(biome_entity.definition_id)
            
            # В новой схеме allowed_locations — это список строк ID (["loc_village", ...])
            possible_loc_ids = tmpl.allowed_locations 
            if not possible_loc_ids:
                continue

            num_locations = random.randint(2, min(3, tmpl.capacity or 3))
            
            for i in range(num_locations): # Используем i как индекс слота
                loc_def_id = random.choice(possible_loc_ids)
                loc_tmpl: LocationTemplate = LOCATION_REGISTRY.get(loc_def_id)
                if not loc_tmpl: continue

                location = Entity(
                    id=make_id("loc"),
                    definition_id=loc_def_id,
                    type=EntityType.LOCATION,
                    name=f"{loc_tmpl.name} в {biome_entity.name}",
                    tags=loc_tmpl.tags,
                    capacity=loc_tmpl.capacity, 
                    parent_id=biome_entity.id,
                    # Добавляем slot_index для визуализации (0 - центр, 1 - сбоку и т.д.)
                    data={"slot_index": i} 
                )
                graph.add_entity(location)
                
                # Заполняем локацию контентом
                self._add_location_contents(graph, location, tmpl, loc_tmpl)

        self._setup_relations(graph)
        return World(graph=graph)

    def _add_location_contents(
        self, 
        graph: WorldGraph, 
        location: Entity, 
        biome_tmpl: BiomeTemplate, 
        loc_tmpl: LocationTemplate
    ):
        """
        Ключевое место изменений. Работаем с полями Pydantic, а не словарём.
        """
        
        # === 1. РЕСУРСЫ ===
        # Используем limits из схемы LocationTemplate
        # Было: loc_tmpl["resource_capacity"] -> Стало: loc_tmpl.limits.get(...)
        max_resources = loc_tmpl.limits.get("Resource", 1)
        current_resources = graph.count_children_of_type(location.id, EntityType.RESOURCE)

        if max_resources > current_resources:
            # Было: biome_tmpl["resources"] -> Стало: biome_tmpl.available_resources
            pool = biome_tmpl.available_resources # Список ID строк ["res_wood", ...]
            
            if pool:
                num_to_add = min(random.randint(1, 2), max_resources - current_resources)
                for _ in range(num_to_add):
                    res_def_id = random.choice(pool)
                    res_tmpl: ResourceTemplate = RESOURCE_REGISTRY.get(res_def_id)
                    if not res_tmpl: continue

                    # Выбор редкости (с учетом весов)
                    rarities = [opt.rarity for opt in res_tmpl.rarity_options]
                    weights = [opt.weight for opt in res_tmpl.rarity_options]
                    chosen_rarity = random.choices(rarities, weights=weights, k=1)[0]

                    context = {
                        "biome_id": biome_tmpl.id,
                        "base_resource": res_tmpl.name_key,
                        "rarity": chosen_rarity
                    }
                    name = self.naming_service.generate_name(EntityType.RESOURCE, context) or res_tmpl.name_key

                    res_tags = res_tmpl.tags.copy()
                    res_tags.add(chosen_rarity.value)

                    entity = Entity(
                        id=make_id("res"),
                        definition_id=res_def_id,
                        type=EntityType.RESOURCE,
                        name=name,
                        tags=res_tags,
                        parent_id=location.id
                    )
                    graph.add_entity(entity)

        # === 2. ФРАКЦИИ ===
        max_factions = loc_tmpl.limits.get("Faction", 2)
        current_factions = graph.count_children_of_type(location.id, EntityType.FACTION)

        if max_factions > current_factions and random.random() < 0.75:
            # Было: biome_tmpl["factions"] (список диктов)
            # Стало: biome_tmpl.factions (список объектов FactionSpawnRule)
            spawn_rules = biome_tmpl.factions 
            
            if spawn_rules:
                # Взвешенный выбор фракции (если у spawn_rule есть weight)
                # Упрощенно: random.choice
                rule = random.choice(spawn_rules)
                
                # rule.definition_id -> "fac_dwarves"
                # rule.role -> "mining"

                fac_tmpl: FactionTemplate = FACTION_REGISTRY.get(rule.definition_id)
                # Если шаблона нет, создаем пустышку или пропускаем
                if not fac_tmpl:
                    print(f"Warning: Faction template '{rule.definition_id}' not found.")
                else:
                    # Подготовка данных для Entity
                    # Мы копируем вектор культуры в data, чтобы NarrativeEngine мог считать его
                    # .model_dump() (v2) или .dict() (v1) преобразует Pydantic модель в словарь
                    faction_data = {
                        "role": rule.role,
                        "creature_type": fac_tmpl.creature_type,
                        # ВАЖНО: сохраняем вектор культуры
                        "culture_vector": fac_tmpl.culture.model_dump() 
                    }

                    context = {
                        "biome_id": biome_tmpl.id,
                        "role": rule.role,
                        "creature_type": fac_tmpl.creature_type
                    }
                    
                    name = self.naming_service.generate_name(EntityType.FACTION, context)
                    
                    entity = Entity(
                        id=make_id("fac"),
                        definition_id=rule.definition_id,
                        type=EntityType.FACTION,
                        name=name,
                        # Объединяем теги из шаблона + теги из правила спавна (в биоме)
                        tags={"faction"} | fac_tmpl.tags | rule.override_tags,
                        parent_id=location.id,
                        data=faction_data # <--- Передаем сюда
                    )
                    graph.add_entity(entity)

    def generate(
        self,
        biome_ids: Optional[List[str]] = None, # TYPE CHANGED: Biome -> str
        num_biomes: Optional[int] = None,
        world_width: int = 3,
        world_height: int = 3,
        layout_to_json: bool = False
    ) -> World:
        
        # Если biome_ids не переданы, берем все ключи из реестра
        if biome_ids is None:
            biome_ids = list(BIOME_REGISTRY.keys())
            if not biome_ids:
                print("Warning: BIOME_REGISTRY is empty!")

        if num_biomes is not None:
            if num_biomes == -1:
                num_biomes = len(biome_ids)
            
            layout_gen = SpatialLayoutGenerator()
            layout = layout_gen.generate_layout(
                width=world_width,
                height=world_height,
                biome_pool=biome_ids,
                fill_ratio=1.0,
                # Fallback на первый попавшийся биом, если списка нет
                fallback_biome_id=biome_ids[0] if biome_ids else "biome_plains"
            )
            if layout_to_json:
                save_spatial_layout_to_json(layout, './layouts/layout.json')
            
            return self.generate_from_spatial_layout(layout)
        else:
            # Упрощенный режим (без лейаута) можно реализовать аналогично
            return World(graph=WorldGraph())

    def _setup_relations(self, graph: WorldGraph):
        self._init_relation_types(graph)
        locations = [e for e in graph.entities.values() if e.type == EntityType.LOCATION]
        for loc in locations:
            children = [e for e in graph.entities.values() if e.parent_id == loc.id]
            for child in children:
                relation_id = None
                if child.type == EntityType.RESOURCE: relation_id = "located_in"
                elif child.type == EntityType.FACTION: relation_id = "faction_located_in"
                
                if relation_id:
                    graph.add_relation(child, loc, relation_id)

    def _init_relation_types(self, graph: WorldGraph):
        graph.relation_types["located_in"] = RelationType(
            id="located_in", from_type=EntityType.RESOURCE, to_type=EntityType.LOCATION, description="Находится в"
        )
        graph.relation_types["faction_located_in"] = RelationType(
            id="faction_located_in", from_type=EntityType.FACTION, to_type=EntityType.LOCATION, description="Базируется в"
        )