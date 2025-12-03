import asyncio
from typing import List, Dict, Set, Optional
from langchain_core.prompts import ChatPromptTemplate
from src.services.llm_service import LLMService
from src.interfaces import IWorldRepository
from langchain_core.output_parsers import StrOutputParser
from src.models.generation import EntityType

class StorytellerService:
    def __init__(self, llm_service: LLMService, repo: IWorldRepository):
        self.llm = llm_service
        self.repo = repo

    def _extract_ids_from_event(self, event: Dict) -> Set[str]:
        """
        Вытаскиваем все ID сущностей, упомянутых в событии.
        Это позволит нам подтянуть контекст только для участников драмы.
        """
        ids = set()
        
        # 1. ID самого события (если оно есть в графе)
        if "id" in event:
            ids.add(event["id"])
            
        # 2. Поля данных (conflict_id, location_id, faction_id...)
        data = event.get("data", {})
        
        # Перебираем известные ключи, где могут лежать ID
        target_keys = [
            "location_id", "faction_id", "target_faction_id", 
            "character_id", "conflict_id", "resource_id", 
            "ritual_id", "belief_id"
        ]
        
        for k, v in data.items():
            if k in target_keys and isinstance(v, str) and v.startswith(("loc_", "fac_", "char_", "con_", "res_")):
                ids.add(v)
            # Иногда ID лежат в списках (например, allies: ["fac_1", "fac_2"])
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, str) and item.startswith(("loc_", "fac_", "char_")):
                        ids.add(item)
                        
        return ids

    async def _format_entity_knowledge(self, entity_id: str) -> Optional[str]:
        """
        Формирует текстовое описание сущности и её связей для LLM.
        Пример вывода:
        [Faction] "Клан Железа" (Role: mining).
           - Предводитель: Король Торин
           - Базируется в: Гора Черепа
           - В союзе с: Гномы холмов
        """
        entity = await self.repo.get_entity(entity_id)
        if not entity:
            return None

        # Базовая инфо
        tags_str = ", ".join(entity.tags)
        info = f"[{entity.type.value}] \"{entity.name}\""
        if tags_str:
            info += f" (Tags: {tags_str})"
            
        # Добавляем специфику из data (например, вектор культуры)
        if entity.type == EntityType.FACTION and entity.data:
             culture = entity.data.get("culture_vector", {})
             # Упрощаем вывод культуры, если она есть
             if culture:
                 # Фильтруем нули
                 cult_traits = [f"{k}:{v}" for k,v in culture.items() if isinstance(v, int) and v != 0]
                 if cult_traits:
                     info += f" [Culture: {', '.join(cult_traits)}]"

        # Получаем связи (Ключевой момент!)
        neighbors = await self.repo.get_neighbors_with_rel(entity_id)
        
        relations_desc = []
        for rel_id, neighbor, rel_desc in neighbors:
            # Форматируем связь. Например: "- Предводитель: [Character] Торин"
            relations_desc.append(f"   - {rel_desc}: {neighbor.name} ({neighbor.type.value})")

        if relations_desc:
            info += "\n" + "\n".join(relations_desc)
            
        return info

    async def _build_event_context(self, events: List[Dict]) -> str:
        """Собирает граф знаний для конкретного набора событий."""
        
        # 1. Глобальный контекст (фон)
        global_ctx = await self.repo.get_global_context()
        
        # 2. Сбор уникальных ID участников
        involved_ids = set()
        for ev in events:
            involved_ids.update(self._extract_ids_from_event(ev))
        
        # 3. Получение детализированной информации по каждому ID
        knowledge_snippets = []
        
        # Асинхронно собираем инфу (для скорости)
        tasks = [self._format_entity_knowledge(eid) for eid in involved_ids]
        results = await asyncio.gather(*tasks)
        
        for res in results:
            if res:
                knowledge_snippets.append(res)

        # Собираем итоговый текст
        context_str = f"""
=== ГЛОБАЛЬНЫЙ ФОН ===
{global_ctx}

=== ДЕЙСТВУЮЩИЕ ЛИЦА И МЕСТА ===
{chr(10).join(knowledge_snippets)}
"""
        return context_str

    async def describe_entity(self, entity_id: str) -> str:
        """
        Генерирует художественное описание конкретной сущности (Локации, Фракции, Биома).
        """
        # 1. Формируем контекст именно для этой сущности
        # Мы используем уже написанный нами метод _format_entity_knowledge
        # + добавляем немного глобального контекста
        
        global_ctx = await self.repo.get_global_context()
        local_ctx = await self._format_entity_knowledge(entity_id)
        
        if not local_ctx:
            return "Сущность не найдена или о ней нет информации."

        # 2. Формируем промпт
        prompt = ChatPromptTemplate.from_messages([
            ("system", 
             "Ты — рассказчик в игре (Lore Master). Твоя задача — дать глубокое, атмосферное "
             "описание места или организации, на которую смотрит игрок.\n"
             "Используй предоставленные факты (связи, ресурсы, культуру), но оберни их в художественный текст.\n"
             "Не перечисляй списком. Пиши одним-двумя абзацами."
            ),
            ("user", 
             f"ГЛОБАЛЬНЫЙ МИР:\n{global_ctx}\n\n"
             f"ОБЪЕКТ ДЛЯ ОПИСАНИЯ:\n{local_ctx}\n\n"
             "Опиши это."
            )
        ])

        chain = prompt | self.llm.llm | StrOutputParser() # Обращаемся к сырой llm, а не structured
        
        return await chain.ainvoke({})

    async def narrate_history(
        self, 
        events: List[Dict], # Список сырых JSON событий
        setting: str = "dark fantasy", 
        examples: Optional[List[str]] = None
    ) -> str:
        
        if not events:
            return "В эту эпоху ничего не произошло."

        print(f"Constructing context for {len(events)} events...")
        
        # Строим контекст на основе графа
        context_str = await self._build_event_context(events)
        
        # Отправляем в LLM
        story = await self.llm.narrate_epoch(
            world_context=context_str,
            events_json=events,
            setting=setting,
            examples=examples
        )
        
        return story