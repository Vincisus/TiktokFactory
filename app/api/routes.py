from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.orchestrator import Orchestrator, job_store

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    series: str = "tradimenti_e_vendetta"
    duration_minutes: int = 12
    tiktok_clips: int = 4


@router.post("/api/chat")
async def chat(request: ChatRequest):
    orchestrator = Orchestrator()
    job = orchestrator.start(request.model_dump())
    return {"job_id": job["id"], "status": job["status"], "progress": job["progress"]}


@router.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job non trovato")
    return job


@router.get("/api/health")
async def health():
    orchestrator = Orchestrator()
    return orchestrator.health()
