from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import Base, engine
from models.click import ClickEvent
from models.link import Link
from routers.analytics import router as analytics_router
from routers.links import router as links_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="URLClippr", lifespan=lifespan)


@app.get("/health")
def health_check():
    return {"status": "ok"}


app.include_router(analytics_router)
app.include_router(links_router)
