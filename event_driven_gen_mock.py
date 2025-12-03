# MOCKING (Для демонстрации)
from models.mechanics import EventType, GameEvent
from quest_engine import QuestGenerator

# тут много что ещё менять надо, но как бейзлайн терпимо

class MockWorld:
    def get_creature(self, id): 
        # Возвращает объект Creatures из mechanics.py
        from src.models.mechanics import Creatures, Inventory
        return Creatures(id=id, name="Торговец Ганс", creature_type=1, inventory=Inventory(character_id=id, items=[], capacity=10), location_id=1)
    
    def get_item(self, id):
        from src.models.mechanics import Item
        return Item(id=id, value=50, unique=True, item_type=["weapon"], other={"name": "Золотой Кинжал"}, on_skin=False)

# 1. Инициализация
world_db = MockWorld()
generator = QuestGenerator(world_db)

# 2. Происходит событие (например, Logic Engine решил, что произошла кража)
# Это событие создается "за кадром" твоей симуляцией жизни
event = GameEvent(
    timestamp=102,
    type=EventType.THEFT,
    actor_id=505,   # Вор
    target_id=101,  # Торговец
    location_id=12, # Таверна
    data={"item_id": 99} # Украденный кинжал
)

# 3. Генерация квеста
quest = generator.process_event(event)

# 4. Результат для Игрового движка (JSON)
print(f"=== SYSTEM DATA ===\nQuest ID: {quest.id}")
print(f"Objective: {quest.objectives[0].verb} -> ID:{quest.objectives[0].target_id}")

# 5. Результат для LLM (Prompt)
print(f"\n=== LLM PROMPT ===\n{quest.to_llm_prompt()}")