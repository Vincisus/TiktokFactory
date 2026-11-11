from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.card_coherence import install

# Run after Avvia.bat has installed recovery, before creating any web jobs.
install()

from app.api.routes import router

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="TiktokFactory", version="0.2.1")
app.include_router(router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "web"), name="static")


@app.get("/")
async def index():
    return {"message": "TiktokFactory is running", "ui": "/static/index.html"}
