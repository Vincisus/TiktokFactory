from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from app.core.card_coherence import install

install()

from app.api.routes import router
from app.core.lean_pipeline import router as lean_router
from app.core.scene_contract import install as install_scene_contract

install_scene_contract()

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="TiktokFactory", version="0.3.1")
app.include_router(router)
app.include_router(lean_router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "web"), name="static")


@app.get("/")
async def index():
    return RedirectResponse("/static/lean.html")
