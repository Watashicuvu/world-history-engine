from typing import List, Optional, Dict, Any
import uuid

from src.services.spatial_manager import SpatialManager
from src.models.generation import Entity, EntityType, World

class WorldQueryService:
    def __init__(self, world: World):
        self.world = world
        self.graph = world.graph
        self.spatial = SpatialManager()

    # === READ (Навигация) ===

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        if not entity_id: return None
        return self.graph.entities.get(entity_id)

    def get_biome(self, location: Entity) -> Optional[Entity]:
        """Рекурсивно ищет родительский биом для любой сущности."""
        if not location: return None
        current_id = location.parent_id
        depth = 0
        while current_id and depth < 5:
            parent = self.get_entity(current_id)
            if not parent:
                return None
            if parent.type == EntityType.BIOME:
                return parent
            current_id = parent.parent_id
            depth += 1
        return None
    
    def get_belief(self, faction: Entity) -> Optional[Entity]:
        """Находит религию фракции."""
        if not faction: return None
        # Ищем связь "believes_in" (from FACTION -> to BELIEF)
        # Примечание: в твоем графе связи направленные.
        # Если faction believes_in Belief, то faction=from, belief=to
        for r in self.graph.relations:
            if r.from_entity.id == faction.id:
                 # Проверка типа связи (учитывая твой фикс с строками/объектами)
                 r_type = r.relation_type.id if hasattr(r.relation_type, 'id') else str(r.relation_type)
                 if r_type == "believes_in":
                     return r.to_entity
        return None

    def get_factions_by_belief(self, belief_id: str) -> List[Entity]:
        """Возвращает всех последователей веры."""
        factions = []
        for r in self.graph.relations:
            r_type = r.relation_type.id if hasattr(r.relation_type, 'id') else str(r.relation_type)
            if r_type == "believes_in" and r.to_entity.id == belief_id:
                factions.append(r.from_entity)
        return factions

    # === ANALYTICS & CONTEXT TOOLS (Для MCP) ===

    # TODO: добавить почти везде (в запросах контекста, ui...), а не только в MCP !!!
    def get_world_metadata(self) -> Dict[str, List[str]]:
        """
        Возвращает "словарь" мира: какие теги и типы связей вообще существуют.
        Нужно, чтобы LLM знала, как правильно фильтровать (какие теги использовать).
        """
        all_tags = set()
        for entity in self.graph.entities.values():
            all_tags.update(entity.tags)
        
        # Собираем ID типов связей
        rel_types = set(self.graph.relation_types.keys())
        # Также сканируем живые связи, на случай если есть динамические
        for r in self.graph.relations:
            r_id = r.relation_type.id if hasattr(r.relation_type, 'id') else str(r.relation_type)
            rel_types.add(r_id)

        return {
            "available_tags": sorted(list(all_tags)),
            "relation_types": sorted(list(rel_types)),
            "entity_types": [t.value for t in EntityType]
        }

    # TODO: добавить это в GUI отрисованного графа!
    def query_entities(
        self, 
        include_tags: Optional[List[str]] = None, 
        exclude_tags: Optional[List[str]] = None, 
        type_filter: Optional[str] = None,
        limit: int = 50
    ) -> str:
        """
        Возвращает сжатый список сущностей для контекста.
        Формат: "ID | Name | Type | [Tags]"
        """
        results = []
        
        # Превращаем списки в множества для скорости
        inc_set = set(include_tags) if include_tags else set()
        exc_set = set(exclude_tags) if exclude_tags else set()
        
        count = 0
        for entity in self.graph.entities.values():
            if count >= limit:
                break

            # 1. Фильтр по Типу
            if type_filter and entity.type != type_filter:
                continue
            
            # 2. Фильтр "Исключить" (Черный список) - Самый важный для сжатия
            # Если пересечение множества тегов сущности и черного списка НЕ пустое -> пропускаем
            if exc_set and not exc_set.isdisjoint(entity.tags):
                continue
                
            # 3. Фильтр "Включить" (Белый список)
            # Если белый список задан, entity.tags должны содержать ВСЕ теги из него (AND логика)
            # (Можно поменять на isdisjoint для OR логики, но для поиска обычно нужен AND)
            if inc_set and not inc_set.issubset(entity.tags):
                continue

            # Формируем строку
            tags_str = ", ".join(sorted(entity.tags))
            # Добавляем родителя для контекста (где это находится)
            parent_info = f" (in {entity.parent_id})" if entity.parent_id else ""
            
            line = f"- {entity.id}: {entity.name} [{entity.type}]{parent_info} | Tags: {{{tags_str}}}"
            results.append(line)
            count += 1
            
        if not results:
            return "No entities found matching criteria."
            
        header = f"Found {len(results)} entities (Limit: {limit}):"
        return header + "\n" + "\n".join(results)

    def analyze_relationships(
        self, 
        source_type: Optional[str] = None, 
        target_type: Optional[str] = None,
        relation_filter: Optional[str] = None,
        # Новые фильтры
        include_tags: Optional[List[str]] = None,
        min_age: Optional[int] = None,
        max_age: Optional[int] = None
    ) -> str:
        """
        Строит Markdown-таблицу связей с фильтрацией по типам, тегам и эпохам.
        """
        rows = []
        
        # Подготовка множества тегов для быстрого поиска
        tags_set = set(include_tags) if include_tags else None
        
        for r in self.graph.relations:
            # 1. Базовая фильтрация по типам (как было раньше)
            r_type_id = r.relation_type.id if hasattr(r.relation_type, 'id') else str(r.relation_type)
            
            if relation_filter and r_type_id != relation_filter:
                continue
            if source_type and r.from_entity.type != source_type:
                continue
            if target_type and r.to_entity.type != target_type:
                continue
            
            # 2. Фильтрация по Времени (Эпохе)
            # Логика: Если задан фильтр времени, показываем связь, если хотя бы одна из сущностей
            # была создана в этот период. Это полезно для поиска событий (Events).
            if min_age is not None or max_age is not None:
                # Берем created_at, если его нет - считаем 0
                t1 = getattr(r.from_entity, 'created_at', 0)
                t2 = getattr(r.to_entity, 'created_at', 0)
                
                # Проверяем source
                source_ok = True
                if min_age is not None and t1 < min_age: source_ok = False
                if max_age is not None and t1 > max_age: source_ok = False
                
                # Проверяем target
                target_ok = True
                if min_age is not None and t2 < min_age: target_ok = False
                if max_age is not None and t2 > max_age: target_ok = False
                
                # Если ни один край связи не попадает в эпоху - пропускаем
                if not source_ok and not target_ok:
                    continue

            # 3. Фильтрация по Тегам
            # Логика: Если заданы теги (например, "Major"), показываем связь, 
            # если хотя бы одна сущность имеет этот тег.
            if tags_set:
                t1_tags = set(r.from_entity.tags)
                t2_tags = set(r.to_entity.tags)
                # Пересечение: есть ли искомый тег хоть где-то?
                if tags_set.isdisjoint(t1_tags) and tags_set.isdisjoint(t2_tags):
                    continue

            # Формируем строку таблицы
            # Добавим (Age: X) к имени, чтобы LLM видела хронологию
            src_name = f"{r.from_entity.name}"
            if hasattr(r.from_entity, 'created_at'): src_name += f" <sup>T{r.from_entity.created_at}</sup>"
            
            tgt_name = f"{r.to_entity.name}"
            if hasattr(r.to_entity, 'created_at'): tgt_name += f" <sup>T{r.to_entity.created_at}</sup>"

            rows.append(f"| {src_name} | **{r_type_id}** | {tgt_name} |")

        if not rows:
            return "No relationships found for these criteria."

        # Сборка таблицы
        header = f"Found {len(rows)} relations"
        if min_age is not None: header += f" (Age {min_age}-{max_age if max_age else 'Now'})"
        if include_tags: header += f" (Tags: {include_tags})"
        
        table_md = "| Source Entity | Relation Type | Target Entity |\n|---|---|---|\n" + "\n".join(rows)
        return f"{header}\n{table_md}"

    def update_tags(self, entity_id: str, add_tags: List[str], remove_tags: List[str]):
        entity = self.get_entity(entity_id)
        if not entity:
            raise ValueError(f"Entity {entity_id} not found")
        
        # Удаление
        for t in remove_tags:
            entity.tags.discard(t)
            
        # Добавление
        for t in add_tags:
            entity.tags.add(t)
            
        return list(entity.tags)

    def register_relation_type(self, type_id: str, description: str, is_symmetric: bool = False):
        """
        Позволяет динамически добавлять новые типы связей.
        Это нужно для LLM, если она придумала новый тип отношений.
        """
        from src.models.generation import RelationType, EntityType # Локальный импорт во избежание циклов

        # Если такой тип уже есть - не делаем ничего (или обновляем описание)
        if type_id in self.graph.relation_types:
            return

        # Создаем "универсальный" тип связи.
        # Т.к. мы не знаем типы from/to заранее, можно использовать базовый тип или игнорировать проверку
        # В твоей модели RelationType требует from_type/to_type.
        # Для гибкости можно ввести "Any" или просто использовать FACTION как дефолт,
        # если связь предполагается социальной.
        
        new_rel = RelationType(
            id=type_id,
            description=description,
            from_type=EntityType.FACTION, # Дефолт, LLM должна понимать контекст
            to_type=EntityType.FACTION,
            is_symmetric=is_symmetric
        )
        
        self.graph.relation_types[type_id] = new_rel
        print(f"[QueryService] Dynamic relation registered: {type_id}")

    def get_children(self, parent_id: str, type_filter: Optional[EntityType] = None) -> List[Entity]:
        """Возвращает всех детей (опционально фильтруя по типу)."""
        if not parent_id: return []
        return [
            e for e in self.graph.entities.values()
            if e.parent_id == parent_id
            and (type_filter is None or e.type == type_filter)
            and "inactive" not in e.tags
        ]
    
    def get_location_of(self, entity: Entity) -> Optional[Entity]:
        """Находит локацию, в которой находится сущность."""
        if not entity or not entity.parent_id: return None
        parent = self.get_entity(entity.parent_id)
        if parent and parent.type == EntityType.LOCATION:
            return parent
        return None

    # === WRITE (Изменения графа) ===

    def add_entity(self, entity: Entity):
        self.graph.add_entity(entity)

    def add_relation(self, from_e: Entity, to_e: Entity, rel_type_id: str):
        """
        Безопасное создание связи с логированием ошибок.
        """
        if not from_e or not to_e:
            print(f"[QueryService] Error: Attempt to link None entities. From: {from_e}, To: {to_e}")
            return

        # Проверка наличия типа связи
        if rel_type_id not in self.graph.relation_types:
            # КРИТИЧНО: Если типа нет, мы должны видеть это в логах ярко
            print(f"!!! CRITICAL WARNING: Relation type '{rel_type_id}' MISSING in registry. Relation NOT created.")
            # Можно временно создать тип, чтобы не крашить симуляцию, 
            # но лучше исправить регистрацию в NarrativeEngine.
            return
            
        try:
            self.graph.add_relation(from_e, to_e, rel_type_id)
        except Exception as e:
            print(f"[QueryService] Exception adding relation {rel_type_id}: {e}")
            raise e

    def move_entity(self, entity: Entity, new_parent: Entity, relation_type: str = "faction_located_in"):
        """
        Перемещает сущность, безопасно удаляя старые связи.
        """
        if not entity or not new_parent: return

        # Безопасная фильтрация связей
        # Проверяем наличие атрибутов, чтобы избежать AttributeError, если граф поврежден
        new_relations = []
        for r in self.graph.relations:
            try:
                # Проверяем, что r.relation_type это объект и имеет id, либо это строка
                r_type_id = r.relation_type.id if hasattr(r.relation_type, 'id') else str(r.relation_type)
                
                # Если это та самая связь, которую надо удалить — пропускаем её
                if r.from_entity.id == entity.id and r_type_id == relation_type:
                    continue
                
                new_relations.append(r)
            except AttributeError:
                # Если связь битая, удаляем её
                continue
        
        self.graph.relations = new_relations
        
        entity.parent_id = new_parent.id
        self.add_relation(entity, new_parent, relation_type)

        # Получаем всех будущих соседей (кто уже сидит в new_parent)
        siblings = self.get_children(new_parent.id, entity.type)
        
        # Просим SpatialManager найти место
        spatial_data = self.spatial.assign_slot(entity, new_parent, siblings)
        
        # Обновляем data сущности
        if entity.data is None: entity.data = {}
        entity.data.update(spatial_data)
        
        # Если родитель имеет глобальные координаты,
        # мы можем закэшировать "абсолютные" координаты для ребенка
        self._update_absolute_coordinates(entity, new_parent)

    def _update_absolute_coordinates(self, entity: Entity, parent: Entity):
        """
        Вычисляет абсолютные мировые координаты для удобства отрисовки.
        Biome (Global X, Y) -> Location (Offset) -> Entity (Offset)
        """
        # Базовые координаты родителя
        parent_global = parent.data.get("geo_coord") # Допустим, храним тут (float, float)
        
        # Если у родителя нет float-координат, но это Биом с integer (x, y)
        if not parent_global and "coord" in parent.data:
            # Превращаем grid (5, 3) в float (5.5, 3.5) - центр клетки
            grid_pos = parent.data["coord"]
            parent_global = (float(grid_pos[0]), float(grid_pos[1]))

        if parent_global and "local_coord" in entity.data:
            loc_x, loc_y = entity.data["local_coord"]
            # Смещение относительно родителя (допустим, локация занимает 0.8 размера клетки)
            # Это упрощенная формула
            abs_x = parent_global[0] + (loc_x - 0.5) * 0.8
            abs_y = parent_global[1] + (loc_y - 0.5) * 0.8
            
            entity.data["abs_coord"] = (abs_x, abs_y)

    def register_event(
        self, 
        event_type: str, 
        summary: str, 
        age: int, 
        primary_entity: Entity, 
        secondary_entities: Optional[List[Entity]] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> Entity:
        if data is None: data = {}
            
        data.update({
            "age": age,
            "event_type": event_type,
            "summary": summary
        })

        # === НОВОЕ: Автоматическое определение локации ===
        # Пытаемся понять, где произошло событие, и записать это в data,
        # чтобы фронтенд мог нарисовать иконку в нужном месте.
        location_id = data.get("location_id")
        
        if not location_id and primary_entity:
            # 1. Если главный объект - Локация
            if primary_entity.type == EntityType.LOCATION:
                location_id = primary_entity.id
            # 2. Если главный объект внутри чего-то (Фракция, Ресурс)
            else:
                loc = self.get_location_of(primary_entity)
                if loc:
                    location_id = loc.id
        
        # Если не нашли по первичному, ищем во вторичных (например, цель набега)
        if not location_id and secondary_entities:
            for ent in secondary_entities:
                if ent.type == EntityType.LOCATION:
                    location_id = ent.id
                    break
        
        # Если нашли локацию, сохраняем ID в данные события
        if location_id:
            data["location_id"] = location_id
            # ОПЦИОНАЛЬНО: Можно сразу сохранить координаты, чтобы не зависеть от кэша фронта
            # loc_ent = self.get_entity(location_id)
            # if loc_ent and loc_ent.data and "coord" in loc_ent.data:
            #    data["target_coord"] = loc_ent.data["coord"]
        # ================================================

        event_id = f"evt_{str(uuid.uuid4())[:8]}"
        event = Entity(
            id=event_id,
            definition_id="sys_event",
            type=EntityType.EVENT,
            name=f"Эпоха {age}: {summary}",
            created_at=age,
            data=data
        )
        self.add_entity(event)

        if primary_entity:
            rel_name = "affected_by" if primary_entity.type == EntityType.FACTION else "occurred_at"
            self.add_relation(primary_entity, event, rel_name)

        if secondary_entities:
            for entity in secondary_entities:
                if entity:
                    rel_name = "affected_by" if entity.type == EntityType.FACTION else "occurred_at"
                    self.add_relation(entity, event, rel_name)

        return event
    
    # === GOD MODE TOOLS ===

    def get_entity_details(self, entity_id: str) -> str:
        """Возвращает полный JSON сущности для детального изучения."""
        entity = self.get_entity(entity_id)
        if not entity:
            return f"Error: Entity {entity_id} not found."
        
        # model_dump_json() - это стандартный метод Pydantic
        return entity.model_dump_json(indent=2)

    def spawn_entity(
        self, 
        definition_id: str, 
        parent_id: str, 
        entity_type: str, 
        name: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Ручной спавн сущности.
        """
        import uuid
        from src.models.generation import Entity, EntityType

        parent = self.get_entity(parent_id)
        if not parent and parent_id != "root": # "root" для корневых биомов
             return f"Error: Parent {parent_id} not found."

        # Генерация ID
        unique_suffix = str(uuid.uuid4())[:6]
        new_id = f"{definition_id}_{unique_suffix}"
        
        # Если имя не задано, берем definition_id (в идеале тут нужен NamingService, 
        # но для ручного спавна LLM обычно сама дает имя)
        final_name = name if name else f"{definition_id} instance"

        new_entity = Entity(
            id=new_id,
            definition_id=definition_id,
            type=EntityType(entity_type), # Конвертация строки в Enum
            name=final_name,
            parent_id=parent_id if parent_id != "root" else None,
            created_at=0, # Или текущая эпоха
            data=data or {}
        )
        
        self.add_entity(new_entity)
        return f"Spawned: {new_entity.name} (ID: {new_entity.id}) in {parent_id}"
    
    # def get_graph_snapshot(self, exclude_tags: Optional[List[str]] = None) -> Dict[str, Any]:
    #     """
    #     Возвращает граф в формате, готовом для JSON-сериализации и отправки на фронт.
    #     Фильтрует сущности по тегам.
    #     """
    #     if exclude_tags is None:
    #         exclude_tags = ["dead", "inactive"] # Твои дефолтные значения

    #     exc_set = set(exclude_tags)
        
    #     # 1. Фильтруем сущности
    #     filtered_entities = {}
    #     for entity_id, entity in self.graph.entities.items():
    #         # Если есть пересечение с черным списком тегов — пропускаем
    #         if exc_set and not exc_set.isdisjoint(entity.tags):
    #             continue
    #         filtered_entities[entity_id] = entity

    #     # 2. Собираем только актуальные связи
    #     # (оба конца связи должны существовать в отфильтрованном списке)
    #     filtered_relations = []
    #     for r in self.graph.relations:
    #         if r.from_entity.id in filtered_entities and r.to_entity.id in filtered_entities:
    #             filtered_relations.append(r)

    #     # Возвращаем структуру, идентичную той, что в world_output/*.json
    #     return {
    #         "graph": {
    #             "entities": filtered_entities, # Pydantic сериализует это автоматически при return из FastAPI
    #             "relations": filtered_relations,
    #             "relation_types": self.graph.relation_types
    #         }
    #     }
    def get_graph_snapshot(self, exclude_tags: Optional[List[str]] = None) -> Dict[str, Any]:
        if exclude_tags is None:
            exclude_tags = []
        
        exc_set = set(exclude_tags)
        
        # 1. Фильтрация узлов
        filtered_entities = {}
        for entity_id, entity in self.graph.entities.items():
            # Если есть пересечение с черным списком тегов — пропускаем
            if exc_set and not exc_set.isdisjoint(entity.tags):
                continue
            filtered_entities[entity_id] = entity

        # 2. Фильтрация связей
        filtered_relations = []
        for r in self.graph.relations:
            # Связь валидна только если оба конца существуют в отфильтрованном списке
            if r.from_entity.id in filtered_entities and r.to_entity.id in filtered_entities:
                filtered_relations.append(r)
        
        print(f"[API] Serving graph snapshot. Nodes: {len(filtered_entities)}, Edges: {len(filtered_relations)}")

        # ВАЖНО: Возвращаем плоскую структуру, которую ждет JS
        return {
            "entities": filtered_entities,
            "relations": filtered_relations
        }