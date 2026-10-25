from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import engine
from models.link import Link
from routers.analytics import router as analytics_router
from routers.links import router as links_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Link.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="URLClippr", lifespan=lifespan)

app.include_router(links_router)
app.include_router(analytics_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
