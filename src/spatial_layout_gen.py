import random
from typing import Dict, List, Set, Tuple, Optional, Callable, Any
# Импортируем только Registry, Enums больше не нужны для контента
from src.models.registries import BIOME_REGISTRY
from src.models.templates_schema import BiomeTemplate

Coord = Tuple[int, int]

class SpatialLayout:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        # Изменено: храним str (ID биома), а не Enum
        self.cells: Dict[Coord, Optional[str]] = {}
        self.edge_cells: Set[Coord] = set()
        self._init_cells()

    def _init_cells(self):
        # Инициализируем только валидные координаты (прямоугольник)
        # Пустоты (None) будут означать отсутствие земли
        for y in range(self.height):
            for x in range(self.width):
                self.cells[(x, y)] = None

    def is_valid(self, coord: Coord) -> bool:
        return coord in self.cells

    def is_edge(self, coord: Coord) -> bool:
        # Теперь край — это не просто границы массива, а грани с "пустотой" (None)
        if coord not in self.cells: return False
        x, y = coord
        
        # Если сосед за пределами карты или он == None (вырезан маской)
        neighbors = [(x-1, y), (x+1, y), (x, y-1), (x, y+1)]
        for nx, ny in neighbors:
            if (nx, ny) not in self.cells: # За границей массива или вырезан
                return True
        
        return x == 0 or x == self.width - 1 or y == 0 or y == self.height - 1

    def neighbors(self, coord: Coord) -> List[Coord]:
        x, y = coord
        candidates = [(x-1, y), (x+1, y), (x, y-1), (x, y+1)]
        return [
            (nx, ny)
            for nx, ny in candidates
            if 0 <= nx < self.width and 0 <= ny < self.height
        ]

    def occupied_cells(self) -> Dict[Coord, str]:
        return {c: b for c, b in self.cells.items() if b is not None}

    def free_cells(self) -> List[Coord]:
        return [c for c, b in self.cells.items() if b is None]


class SpatialLayoutGenerator:
    def __init__(self):
        self.biome_templates = BIOME_REGISTRY.get_all()
        self.constraints = self._build_constraints()

    def _build_constraints(self) -> Dict[str, Callable[[Coord, SpatialLayout], bool]]:
        constraints = {}
        for biome_id, tmpl in self.biome_templates.items():
            tags = tmpl.tags 
            forbidden_neighbors = tmpl.forbidden_neighbors

            def make_constraint(tags_local=tags, forbidden_local=forbidden_neighbors):
                def constraint(coord: Coord, layout: SpatialLayout) -> bool:
                    # Edge check
                    is_edge = layout.is_edge(coord)
                    if "edge_only" in tags_local and not is_edge: return False
                    if "no_edge" in tags_local and is_edge: return False

                    # Neighbors check
                    for nb in layout.neighbors(coord):
                        # ИСПРАВЛЕНИЕ: используем .get(), так как nb может быть вырезан маской (отсутствовать в keys)
                        neighbor_id = layout.cells.get(nb) 
                        if neighbor_id is not None and neighbor_id in forbidden_local:
                            return False
                    return True
                return constraint
            constraints[biome_id] = make_constraint()
        return constraints

    def _apply_organic_mask(self, layout: SpatialLayout):
        """
        Вырезает углы.
        ИСПРАВЛЕНИЕ: Для малых карт делаем маску мягче, иначе она удаляет всё.
        """
        # Если карта слишком узкая, не применяем маску или делаем её минимальной
        if layout.width <= 4 or layout.height <= 4:
            return

        center_x = layout.width / 2
        center_y = layout.height / 2
        
        max_dist_x = layout.width / 2
        max_dist_y = layout.height / 2
        
        for y in range(layout.height):
            for x in range(layout.width):
                dx = (x - center_x) / max_dist_x
                dy = (y - center_y) / max_dist_y
                dist_sq = dx*dx + dy*dy
                
                noise = random.uniform(-0.1, 0.1)
                
                # Было > 0.85. Увеличим порог для надежности на краях
                if dist_sq + noise > 0.90: 
                    if (x, y) in layout.cells:
                        del layout.cells[(x, y)]
    
    def _can_place_biome(self, biome_id: str, coord: Coord, layout: SpatialLayout) -> bool:
        # Проверяем базовые ограничения
        constraint_func = self.constraints.get(biome_id)
        if constraint_func and not constraint_func(coord, layout):
            return False

        # Специальная логика для coastal
        tmpl = self.biome_templates.get(biome_id)
        if tmpl and "coastal" in tmpl.tags:
            # Coastal должен иметь соседа, который является краем карты или водой
            for nb in layout.neighbors(coord):
                if layout.is_edge(nb):
                    # Проверяем .get() на случай если сосед тоже удален (хотя is_edge должен вернуть False)
                    nb_biome_id = layout.cells.get(nb)
                    if nb_biome_id is not None:
                        nb_tmpl = self.biome_templates.get(nb_biome_id)
                        if nb_tmpl and "coastal" not in nb_tmpl.tags:
                            return False
            return True
            
        return True

    def generate_layout(
        self,
        width: int,
        height: int,
        biome_pool: List[str],  
        fill_ratio: float = 1.0,
        fallback_biome_id: str = "biome_plains" 
    ) -> SpatialLayout:
        layout = SpatialLayout(width, height)
        
        # 1. Применяем маску (делаем форму острова)
        self._apply_organic_mask(layout)

        # Доступные для застройки клетки (те, что не удалены маской)
        available_coords = list(layout.cells.keys())
        total_cells = len(available_coords)
        
        cells_to_fill = int(total_cells * fill_ratio)

        # Убедимся, что fallback есть в ограничениях (создадим пустышку, если нет)
        if fallback_biome_id not in self.constraints:
            self.constraints[fallback_biome_id] = lambda coord, layout: True

        # --- Шаг 1: гарантированное размещение ---
        unique_biomes = list(set(biome_pool))
        random.shuffle(unique_biomes)

        # Разделяем на край (теперь это край острова) и центр
        # Пересчитываем edge_cells, так как мы удалили часть клеток
        layout.edge_cells = {c for c in available_coords if layout.is_edge(c)}
        
        edge_coords = list(layout.edge_cells)
        inner_coords = [c for c in available_coords if c not in layout.edge_cells]
        
        random.shuffle(edge_coords)
        random.shuffle(inner_coords)
        all_coords_ordered = edge_coords + inner_coords

        placed = 0

        for biome_id in unique_biomes:
            if placed >= cells_to_fill:
                break
            placed_one = False
            for coord in all_coords_ordered:
                if layout.cells[coord] is not None:
                    continue
                if self._can_place_biome(biome_id, coord, layout):
                    layout.cells[coord] = biome_id
                    placed += 1
                    placed_one = True
                    break
            
            # Fallback для гарантированных
            if not placed_one and placed < cells_to_fill:
                for coord in all_coords_ordered:
                    if layout.cells[coord] is None:
                        layout.cells[coord] = fallback_biome_id
                        placed += 1
                        break

        # --- Шаг 2: заполнение ---
        remaining_coords = [c for c in all_coords_ordered if layout.cells[c] is None]
        for coord in remaining_coords:
            if placed >= cells_to_fill:
                break

            candidates = unique_biomes[:]
            random.shuffle(candidates)
            chosen = None
            for biome_id in candidates:
                if self._can_place_biome(biome_id, coord, layout):
                    chosen = biome_id
                    break
            
            if chosen is None:
                chosen = fallback_biome_id

            layout.cells[coord] = chosen
            placed += 1

        return layout