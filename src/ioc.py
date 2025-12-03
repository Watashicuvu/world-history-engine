from dishka import Provider, Scope, provide
from src.models.generation import World
from src.services.world_query_service import WorldQueryService
from src.services.simulation import SimulationService
from src.repositories.in_memory import InMemoryWorldRepository
from src.interfaces import IWorldRepository
from src.services.llm_service import LLMService
from src.services.storyteller import StorytellerService
from src.services.template_editor import TemplateEditorService

from config import api_key, base_url, model, fallback_template_path


class RepositoryProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def world_query(self, world: World) -> WorldQueryService:
        return WorldQueryService(world=world)

    @provide(scope=Scope.REQUEST)
    def user_repo(self) -> IWorldRepository:
        return InMemoryWorldRepository(fallback_template_path)
    

class GeneralProvider(Provider):
    @provide(scope=Scope.APP)
    def get_llm_service(self) -> LLMService:
        return LLMService(api_key=api_key, model_name=model, base_url=base_url)
    
    @provide(scope=Scope.APP)
    def get_world(self) -> World:
        return World()


class AppProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_sim_service(self) -> SimulationService:
        return SimulationService()

    @provide(scope=Scope.REQUEST)
    def get_editor_service(self) -> TemplateEditorService:
        return TemplateEditorService()
    
    @provide(scope=Scope.REQUEST)
    def get_storyteller_service(self, llm_service: LLMService, world_repo: IWorldRepository) -> StorytellerService:
        return StorytellerService(llm_service=llm_service, repo=world_repo)