from fastapi import FastAPI

from routers.analytics import router as analytics_router
from routers.links import router as links_router

app = FastAPI(title="URLClippr")

app.include_router(links_router)
app.include_router(analytics_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
