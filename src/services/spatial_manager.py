import math
import random
from typing import Any, List, Tuple, Dict, Optional
from src.models.generation import Entity, EntityType

Coord = Tuple[float, float]

class SpatialManager:
    """
    Отвечает за распределение сущностей в пространстве.
    Работает с локальными координатами от 0.0 до 1.0 внутри родителя.
    """
    
    @staticmethod
    def get_layout_slots(capacity: int, layout_type: str = "ring") -> List[Coord]:
        """
        Генерирует список координат (x, y) для заданной вместимости.
        Координаты нормализованы (0.0 - 1.0), центр - 0.5.
        """
        slots = []
        center = (0.5, 0.5)
        
        if capacity <= 0: return []
        if capacity == 1: return [center]

        # Вариант 1: Кольцо (хорошо для деревень вокруг центра биома или районов города)
        if layout_type == "ring":
            radius = 0.3 # Радиус круга внутри квадрата 1x1
            for i in range(capacity):
                angle = (2 * math.pi / capacity) * i
                # Сдвиг + Центр
                x = center[0] + radius * math.cos(angle)
                y = center[1] + radius * math.sin(angle)
                slots.append((x, y))
        
        # Вариант 2: Сетка (хорошо для строгого расположения)
        elif layout_type == "grid":
            grid_size = math.ceil(math.sqrt(capacity))
            step = 1.0 / (grid_size + 1)
            for y_i in range(grid_size):
                for x_i in range(grid_size):
                    if len(slots) >= capacity: break
                    x = step * (x_i + 1)
                    y = step * (y_i + 1)
                    slots.append((x, y))
                    
        # Добавляем небольшой джиттер (шум), чтобы не выглядело слишком искусственно
        return [(x + random.uniform(-0.02, 0.02), y + random.uniform(-0.02, 0.02)) for x, y in slots]

    def assign_slot(self, entity: Entity, parent: Entity, siblings: List[Entity]) -> Dict[str, Any]:
        """
        Находит свободное место в родителе и возвращает обновленные данные для entity.
        """
        # 1. Определяем вместимость родителя
        # Сначала ищем в data (для динамики), потом в шаблоне (через capacity поле сущности)
        capacity = parent.capacity or parent.data.get("limits", {}).get("Faction", 4)
        
        # Для Биомов capacity обычно не прописан явно в поле, берем из конфига или дефолт
        if parent.type == EntityType.BIOME:
            capacity = 5 # Скажем, макс 5 локаций на биом

        # 2. Генерируем слоты
        layout = "grid" if parent.type == EntityType.BIOME else "ring"
        possible_slots = self.get_layout_slots(capacity, layout)
        
        # 3. Смотрим, какие слоты заняты
        occupied_indices = set()
        for sib in siblings:
            if sib.id == entity.id: continue # Пропускаем себя
            idx = sib.data.get("spatial_slot_index")
            if idx is not None:
                occupied_indices.add(idx)
        
        # 4. Выбираем первый свободный
        chosen_index = -1
        for i in range(len(possible_slots)):
            if i not in occupied_indices:
                chosen_index = i
                break
        
        # Если мест нет, берем рандомный (перенаселение)
        if chosen_index == -1:
            chosen_index = random.randint(0, len(possible_slots) - 1) if possible_slots else 0

        # 5. Возвращаем данные координат
        local_pos = possible_slots[chosen_index] if possible_slots else (0.5, 0.5)
        
        return {
            "spatial_slot_index": chosen_index,
            "local_coord": local_pos # x, y внутри родителя (0.0-1.0)
        }