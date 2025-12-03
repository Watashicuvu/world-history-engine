from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from dishka import AsyncContainer, make_async_container
from dishka.integrations.fastapi import setup_dishka as setup_fastapi
from src.handlers.edit_templates import router as template_routers
from src.handlers.llm_tools import router as llm_router
from src.handlers.simulation import router as sim_router
from src.ioc import AppProvider, GeneralProvider, RepositoryProvider


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    container: AsyncContainer = app.state.dishka_container
    yield
    await container.close()

container = make_async_container(
    RepositoryProvider(),
    GeneralProvider(),
    AppProvider()
)

app = FastAPI(
    title='Storytelling engine API!',
    lifespan=lifespan
)

setup_fastapi(container, app)

api_router = APIRouter()
api_router.include_router(template_routers)
api_router.include_router(llm_router)
api_router.include_router(sim_router)

app.include_router(api_router)

app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    # Запускаем сервер
    uvicorn.run(app, host="0.0.0.0", port=8000)