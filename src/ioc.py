from dishka import Provider, Scope, provide
from src.naming import ContextualNamingService
from src.models.generation import World
from src.services.world_query_service import WorldQueryService
from src.services.simulation import SimulationService
from src.repositories.in_memory import InMemoryWorldRepository
from src.interfaces import IWorldRepository
from src.services.llm_service import LLMService
from src.services.storyteller import StorytellerService
from src.services.template_editor import TemplateEditorService
from src.word_generator import WorldGenerator

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
    def get_naming_service(self) -> ContextualNamingService:
        from src.template_loader import load_naming_data, load_all_templates
        service = ContextualNamingService()
        load_naming_data(service)
        load_all_templates() 
        return service

    @provide(scope=Scope.APP)
    def get_world_generator(self, naming_service: ContextualNamingService) -> WorldGenerator:
        return WorldGenerator(naming_service=naming_service)

    @provide(scope=Scope.APP)
    def get_world(self) -> World:
        """
        Loads the world from JSON, restoring the referential integrity of the graph.
        If you just make a World(**json), then COPIES of entities will be created in Relations,
        and changes to entities will not be reflected in relations.
        """
        import json
        from src.models.generation import (Entity, RelationType, 
                                           RelationInstance, WorldGraph)

        if not fallback_template_path.exists():
            print(f"[Warning] World file not found at {fallback_template_path}. Starting with empty world.")
            return World()
        
        try:
            print(f"[System] Loading world from {fallback_template_path}...")
            with open(fallback_template_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            graph_data = data.get('graph', {})
            
            # 1. Load Entities (Dict ID -> Object)
            raw_entities = graph_data.get('entities', {})
            entities_map = {}
            for eid, edata in raw_entities.items():
                entities_map[eid] = Entity(**edata)
            
            # 2. Load Types of Realtions
            raw_rtypes = graph_data.get('relation_types', {})
            rtypes_map = {}
            for rid, rdata in raw_rtypes.items():
                rtypes_map[rid] = RelationType(**rdata)
                
            # 3. Fix Relations using created objects
            raw_relations = graph_data.get('relations', [])
            relations_list = []
            
            for r in raw_relations:
                f_data = r.get('from_entity')
                t_data = r.get('to_entity')
                rt_data = r.get('relation_type')

                f_id = f_data.get('id') if isinstance(f_data, dict) else f_data
                t_id = t_data.get('id') if isinstance(t_data, dict) else t_data
                rt_id = rt_data.get('id') if isinstance(rt_data, dict) else rt_data
                
                from_obj = entities_map.get(f_id)
                to_obj = entities_map.get(t_id)
                rtype_obj = rtypes_map.get(rt_id)
                
                if from_obj and to_obj and rtype_obj:
                    rel_instance = RelationInstance.model_construct(
                        from_entity=from_obj,
                        to_entity=to_obj,
                        relation_type=rtype_obj
                    )
                    relations_list.append(rel_instance)
            
            # 4. Construct the Graph
            world_graph = WorldGraph(
                entities=entities_map,
                relation_types=rtypes_map,
                relations=relations_list
            )
            
            print(f"[System] World loaded! Entities: {len(entities_map)}, Relations: {len(relations_list)}")
            return World(graph=world_graph)
            
        except Exception as e:
            print(f"[Error] Failed to load world: {e}")
            import traceback
            traceback.print_exc()
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