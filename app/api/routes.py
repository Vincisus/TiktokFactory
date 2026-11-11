from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.orchestrator import Orchestrator

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    series: str = "tradimenti_e_vendetta"
    duration_minutes: int = 12
    tiktok_clips: int = 4


@router.post("/api/chat")
async def chat(request: ChatRequest):
    orchestrator = Orchestrator()
    try:
        result = await orchestrator.run(request.model_dump())
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/health")
async def health():
    orchestrator = Orchestrator()
    return orchestrator.health()
