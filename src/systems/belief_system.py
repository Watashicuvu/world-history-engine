import random
from typing import List, Dict

from src.models.templates_schema import BeliefTemplate
from src.models.registries import BELIEF_REGISTRY
from src.models.generation import Entity, EntityType
from src.services.world_query_service import WorldQueryService
from src.naming import NamingService
from src.utils import make_id

class BeliefSystem:
    def __init__(self, query_service: WorldQueryService, naming_service: NamingService):
        self.qs = query_service
        self.naming_service = naming_service
    
    # === PUBLIC API ===

    def process_beliefs(self, age: int) -> List[Entity]:
        """
        Главный метод цикла. Отвечает за появление и распространение веры.
        """
        events = []
        
        # 1. Генезис: Если религий мало или нет, создаем новые
        # (Обычно происходит в 0-ю эпоху, но может случиться, если старые боги "умерли")
        beliefs = [e for e in self.qs.graph.entities.values() if e.type == EntityType.BELIEF]
        if len(beliefs) < 2:  # Хотим хотя бы 2 религии для конфликтов
            new_beliefs = self._genesis_phase(age, target_amount=2 - len(beliefs))
            events.extend(new_beliefs)

        # 2. Распространение: Миссионерство и давление соседей
        conversion_events = self._spread_phase(age)
        events.extend(conversion_events)
        
        return events

    # === LOGIC ===

    def _genesis_phase(self, age: int, target_amount: int) -> List[Entity]:
        """
        Создает новые религии, выбирая подходящие шаблоны для пророков.
        """
        events = []
        
        # 1. Ищем кандидатов в пророки (Фракции без веры)
        candidates = []
        for f in self.qs.graph.entities.values():
            if f.type != EntityType.FACTION: continue
            if "absorbed" in f.tags or "inactive" in f.tags: continue
            if self.qs.get_belief(f): continue
            candidates.append(f)
        
        if not candidates: return []

        # Выбираем случайных пророков
        prophets = random.sample(candidates, k=min(len(candidates), target_amount))
        
        for prophet_faction in prophets:
            # === ШАГ 1: Подбор шаблона (Archetype Matching) ===
            faction_role = prophet_faction.data.get("role", "default")
            
            # Фильтруем шаблоны по роли фракции (Воинам -> Воинственные культы)
            suitable_templates = [
                t for t in (BELIEF_REGISTRY.get_all()).values() 
                if faction_role in t.preferred_roles
            ]
            
            # Если специфичных нет, берем все доступные
            if not suitable_templates:
                print('problem with filters')
                suitable_templates = list(BELIEF_REGISTRY.get_all().values())
            
            if not suitable_templates:
                print("Warning: No belief templates registered!")
                continue

            selected_tmpl: BeliefTemplate = random.choice(suitable_templates)

            # === ШАГ 2: Расчет модификаторов (Vector Math) ===
            # Берем базу шаблона
            final_modifiers = selected_tmpl.base_modifiers
            variation_name = "Orthodox"

            # Если есть вариации, выбираем одну и СКЛАДЫВАЕМ вектора
            if selected_tmpl.variations:
                variation = random.choice(selected_tmpl.variations)
                variation_name = variation.name
                
                # Магия Python: срабатывает __add__ из CultureVector
                # Складываются цифры, объединяются множества (taboo/revered)
                final_modifiers = final_modifiers + variation.modifiers

            # === ШАГ 3: Генерация имени (Contextual Naming) ===
            name_context = {
                "naming_style": selected_tmpl.naming_style,
                "culture": prophet_faction.data.get("culture_vector"), # Для вдохновения
                # Генерируем имя божества "на лету"
                "deity": self.naming_service.generate_name(EntityType.CHARACTER, {"creature_type": "spirit"}) 
            }
            # Используем NamingService с учетом стиля (martial/arcane/etc)
            name = self.naming_service.generate_name(EntityType.BELIEF, name_context)

            # === ШАГ 4: Создание Сущности ===
            belief_id = make_id("belief")
            belief = Entity(
                id=belief_id,
                definition_id=selected_tmpl.id,
                type=EntityType.BELIEF,
                name=name,
                created_at=age,
                data={
                    # Сохраняем итоговый вектор как словарь
                    "modifiers": final_modifiers.model_dump(), 
                    "origin_faction_id": prophet_faction.id,
                    "naming_style": selected_tmpl.naming_style,
                    "deity_name": name_context["deity"],
                    "variation": variation_name
                }
            )
            self.qs.add_entity(belief)
            
            # Пророк принимает веру первым
            self.qs.add_relation(prophet_faction, belief, "believes_in")
            
            # Логируем событие
            events.append(self.qs.register_event(
                event_type="religion_founded",
                summary=f"«{prophet_faction.name}» основывает культ «{name}» ({selected_tmpl.name}, {variation_name}).",
                age=age,
                primary_entity=belief,
                secondary_entities=[prophet_faction]
            ))
            
        return events

    def _spread_phase(self, age: int) -> List[Entity]:
        """Механика распространения веры через соседство."""
        events = []
        
        # Получаем все фракции
        factions = [f for f in self.qs.graph.entities.values() 
                    if f.type == EntityType.FACTION and "absorbed" not in f.tags]
        
        random.shuffle(factions)
        
        for faction in factions:
            current_belief = self.qs.get_belief(faction)
            
            # Шанс смены веры мал, если вера уже есть
            resistance = 0.9 if current_belief else 0.2
            
            if random.random() < resistance: continue

            # Ищем соседей (географических)
            location = self.qs.get_location_of(faction)
            if not location: continue
            
            # Кто еще живет в этой локации?
            neighbors = self.qs.get_children(location.id, EntityType.FACTION)
            
            # Кто живет в соседних локациях того же биома? (расширенный поиск)
            biome = self.qs.get_biome(location)
            if biome:
                for loc in self.qs.get_children(biome.id, EntityType.LOCATION):
                    if loc.id == location.id: continue
                    neighbors.extend(self.qs.get_children(loc.id, EntityType.FACTION))

            # Собираем статистику веры соседей
            belief_pressure: Dict[str, float] = {}
            
            for neighbor in neighbors:
                if neighbor.id == faction.id: continue
                n_belief = self.qs.get_belief(neighbor)
                if n_belief:
                    # Давление зависит от авторитета соседа (можно брать population или размер армии)
                    pressure = 1.0 
                    # Если сосед союзник, давление выше
                    if "allied" in neighbor.tags: pressure += 0.5
                    
                    belief_pressure[n_belief.id] = belief_pressure.get(n_belief.id, 0) + pressure

            if not belief_pressure: continue

            # Выбираем самую влиятельную веру
            strongest_belief_id = max(belief_pressure, key=belief_pressure.get)
            total_pressure = sum(belief_pressure.values())
            
            # Порог принятия (чем больше соседей верят, тем выше шанс)
            if total_pressure > 2.0: # Магическое число порога конверсии
                new_belief = self.qs.get_entity(strongest_belief_id)
                
                # Если это смена веры
                if current_belief and current_belief.id != strongest_belief_id:
                     # Удаляем старую связь (в WorldQueryService нужен метод move_entity или аналог для удаления связей)
                     # Здесь используем удаление через пересоздание отношений или спец метод
                     self._change_faith(faction, new_belief)
                     
                     events.append(self.qs.register_event(
                        event_type="religion_conversion",
                        summary=f"«{faction.name}» отрекается от {current_belief.name} и принимает {new_belief.name}!",
                        age=age,
                        primary_entity=faction,
                        secondary_entities=[new_belief]
                    ))
                
                # Если веры не было
                elif not current_belief:
                    self.qs.add_relation(faction, new_belief, "believes_in")
                    events.append(self.qs.register_event(
                        event_type="religion_adopted",
                        summary=f"«{faction.name}» принимает веру: {new_belief.name}.",
                        age=age,
                        primary_entity=faction,
                        secondary_entities=[new_belief]
                    ))

        return events

    def _change_faith(self, faction: Entity, new_belief: Entity):
        """Технический метод замены связи believes_in"""
        # Находим и удаляем старую связь. 
        # Т.к. в graph.relations нет метода remove, мы фильтруем список.
        # Это не супер-эффективно для гигантских графов, но для нарратива (<10k связей) ок.
        new_relations = []
        for r in self.qs.graph.relations:
            # Проверка типа связи
            r_type = r.relation_type.id if hasattr(r.relation_type, 'id') else str(r.relation_type)
            
            if r.from_entity.id == faction.id and r_type == "believes_in":
                continue # Пропускаем старую веру
            new_relations.append(r)
        
        self.qs.graph.relations = new_relations
        self.qs.add_relation(faction, new_belief, "believes_in")