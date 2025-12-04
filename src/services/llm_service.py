from typing import Any, Callable, Dict, List, Type, Optional
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr
from langgraph.prebuilt import create_react_agent

from src.models.naming_schemas import BiomeLexiconEntry


class LLMService:
    def __init__(
            self, api_key: SecretStr, 
            model_name: str = "gpt-4o", base_url: Optional[str] = None
        ):
        # Инициализация модели. 
        # В будущем здесь можно добавить переключатель на Ollama/Anthropic
        self.llm = ChatOpenAI(
            api_key=api_key, 
            model=model_name, 
            temperature=0.7,
            base_url=base_url
        )

    async def generate_template(self, prompt_text: str, 
                                model_class: Type[BaseModel],
                                setting: str = 'мрачного фэнтези',
        ) -> Dict[str, Any]:
        structured_llm = self.llm.with_structured_output(model_class)

        # Базовый системный промпт
        system_instructions = (
            f"You are a sophisticated game design assistant for a {setting} world engine. "
            "Generate a configuration template based on the user's request."
        )

        # СПЕЦИАЛЬНОЕ ПРАВИЛО ДЛЯ ЛЕКСИКОНОВ
        if model_class == BiomeLexiconEntry:
            system_instructions += (
                "\n\nLINGUISTIC RULES (RUSSIAN):"
                "\n1. All 'adjectives' MUST be in MASCULINE gender (Мужской род, e.g., 'Черный', 'Мертвый')."
                "\n2. All 'nouns' MUST be in MASCULINE gender (Мужской род, e.g., 'Лес', 'Замок', 'Курган')."
                "\n3. This is critical so they can be combined as '{adj} {noun}' without grammar errors."
                "\n4. Be poetic, dark, and atmospheric."
            )

        chain = ChatPromptTemplate.from_messages([
            ("system", system_instructions),
            ("user", prompt_text)
        ]) | structured_llm

        result = await chain.ainvoke({})
        return result.model_dump(mode='json')

    async def generate_structure(self, prompt_text: str, pydantic_model: Type[BaseModel]) -> BaseModel:
        """
        Генерация строго структурированных данных (для редактора шаблонов).
        """
        parser = PydanticOutputParser(pydantic_object=pydantic_model)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a world-building assistant. Output strictly valid JSON."),
            ("user", "{query}\n\n{format_instructions}")
        ])

        chain = prompt | self.llm | parser

        return await chain.ainvoke({
            "query": prompt_text,
            "format_instructions": parser.get_format_instructions()
        })

    async def narrate_epoch(
            self, world_context: str, events_json: List[Dict], 
            examples: Optional[List[str]],
            setting: str = 'мрачного фэнтези',
        ) -> str:
        """
        Олитературивание событий эпохи.
        """
        # TODO: не хардкодить сеттинг во фронтэнде
        if not examples:
            examples = ['Dark Souls', 'Dwarf Fortress']

        examples_str = ', '.join(examples)
        prompt = ChatPromptTemplate.from_messages([
            ("system", 
             "Ты — летописец {setting}. Твоя задача — превратить сухие логи "
             "системных событий в захватывающую короткую хронику.\n"
             "Стиль: Лаконичный, немного пафосный, как в {examples_str}.\n"
             "Используй контекст мира, чтобы описывать места красочно."
            ),
            ("user", 
             "КОНТЕКСТ МИРА:\n{context}\n\n"
             "СОБЫТИЯ ЭПОХИ:\n{events}"
            )
        ])

        chain = prompt | self.llm | StrOutputParser()

        # Превращаем список dict в строку JSON для промпта
        import json
        events_str = json.dumps(events_json, ensure_ascii=False, indent=2)

        return await chain.ainvoke({
            "setting": setting,
            "examples_str": examples_str,
            "context": world_context,
            "events": events_str
        })
    
    async def run_world_agent(
        self, 
        user_query: str, 
        tools: List[Any], 
        chat_history: List[Dict] = []
    ) -> Any:
        """
        Запускает LLM в режиме Агента с доступом к инструментам через LangGraph.
        """
        
        # 1. Формируем системный промпт
        # В LangGraph системный промпт передается как state_modifier или SystemMessage
        agent_system_prompt = (
            "You are the World Engine Architect. Your goal is to manage the internal world database. "
            "You have direct access to the graph via tools. "
            "CRITICAL: Always use 'query_entities' with 'exclude_tags=['dead', 'absorbed']' "
            "to filter context unless asked for history. "
            "Never hallucinate IDs. Check 'get_world_metadata' for valid tags."
            f"\nCurrent Date/Epoch: Use context if available."
        )

        # 2. Создаем Граф Агента (ReAct pattern)
        # create_react_agent автоматически биндит инструменты к модели
        agent_app = create_react_agent(
            self.llm, 
            tools=tools, 
            state_modifier=agent_system_prompt
        )

        # 3. Подготавливаем входные данные
        # LangGraph ожидает список сообщений
        messages = chat_history.copy() if chat_history else []
        messages.append(HumanMessage(content=user_query))

        # 4. Запуск (invoke/ainvoke)
        # config={"recursion_limit": 10} защищает от бесконечных циклов вызова инструментов
        result = await agent_app.ainvoke(
            {"messages": messages},
            config={"recursion_limit": 15}
        )

        # 5. Извлекаем последний ответ
        # result["messages"] содержит всю переписку, последнее сообщение - ответ ИИ
        last_message = result["messages"][-1]
        
        return last_message.content