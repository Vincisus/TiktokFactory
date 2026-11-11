from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.routes import router

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="TiktokFactory", version="0.1.0")
app.include_router(router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "web"), name="static")


@app.get("/")
async def index():
    return {"message": "TiktokFactory is running", "ui": "/static/index.html"}
