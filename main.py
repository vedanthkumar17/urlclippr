from fastapi import FastAPI

from routers.links import router as links_router

app = FastAPI(title="URLClippr")

app.include_router(links_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
