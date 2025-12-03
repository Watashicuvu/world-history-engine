from typing import Optional
import uuid

from models.mechanics import EventType, GameEvent, GeneratedQuest, QuestObjective, QuestVerb
# Предполагаем, что у нас есть доступ к "Базе данных" мира (все сущности)
# from src.world import WorldDB 

class QuestGenerator:
    def __init__(self, world_db):
        self.world = world_db # Доступ к entities, factions, items

    def process_event(self, event: GameEvent) -> Optional[GeneratedQuest]:
        """Фабричный метод: превращает событие в квест"""
        
        if event.type == EventType.THEFT:
            return self._gen_theft_quest(event)
        
        elif event.type == EventType.RESOURCE_DEPLETED:
            return self._gen_scarcity_quest(event)
            
        elif event.type == EventType.FACTION_CONFLICT:
            return self._gen_mercenary_quest(event)
            
        return None

    def _gen_theft_quest(self, event: GameEvent) -> GeneratedQuest:
        # 1. Извлекаем данные
        thief_id = event.actor_id
        victim_id = event.target_id
        item_id = event.data.get("item_id")
        
        victim = self.world.get_creature(victim_id)
        item = self.world.get_item(item_id)
        
        # 2. Формируем цель (Вернуть предмет)
        # В реальности мы бы проверили, не сбежал ли вор в другую локацию
        obj = QuestObjective(
            verb=QuestVerb.FIND_ITEM,
            target_id=item_id,
            target_name=item.other.get("name", "Unknown Item"),
            description=f"Вернуть украденный предмет: {item.other.get('name')}"
        )

        # 3. Собираем контекст для LLM
        summary = (
            f"В локации {event.location_id} произошла кража. "
            f"Персонаж {victim.name} (Архетип: {victim.archetype}) потерял {item.other.get('name')}. "
            f"Виновник: {self.world.get_creature(thief_id).name}."
        )

        # 4. Создаем объект квеста
        return GeneratedQuest(
            id=str(uuid.uuid4()),
            initiator_id=victim_id,
            location_id=event.location_id,
            objectives=[obj],
            rewards=[], # Тут логика генерации награды based on Item.value
            context_summary=summary,
            hidden_info="Вор все еще прячется в городе, но планирует уйти ночью."
        )

    def _gen_scarcity_quest(self, event: GameEvent) -> GeneratedQuest:
        """Пример интеграции с твоим log_example.txt (Ресурс истощен)"""
        # Лог: "Ресурс Мята в Hunter Camp истощен"
        location = self.world.get_location(event.location_id)
        res_name = event.data.get("resource_name")
        
        # Кто страдает? Лидер местной фракции
        faction = self.world.get_ruling_faction(location.id)
        leader = self.world.get_faction_leader(faction.id)
        
        if not leader:
            return None # Некому дать квест

        obj = QuestObjective(
            verb=QuestVerb.GO_TO,
            target_id=event.location_id, # Нужно найти новое место
            target_name="Новое месторождение",
            description=f"Найти новый источник ресурса: {res_name}"
        )

        return GeneratedQuest(
            id=str(uuid.uuid4()),
            initiator_id=leader.id,
            location_id=event.location_id,
            objectives=[obj],
            rewards=[], 
            context_summary=f"Фракция {faction.name} страдает от нехватки {res_name}. Лидер {leader.name} в отчаянии.",
            hidden_info="Если ресурс не найти, фракция нападет на соседей."
        )