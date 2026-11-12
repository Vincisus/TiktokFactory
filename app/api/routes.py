from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from app.core.orchestrator import Orchestrator, job_store
from app.core.project_console import router as project_router, guard, busy, ROOT, load

router = APIRouter()
router.include_router(project_router)


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=4000)
    series: str = Field(default="tradimenti_e_vendetta", max_length=100)
    duration_minutes: int = Field(default=12, ge=10, le=30)
    tiktok_clips: int = Field(default=4, ge=3, le=4)


class MediaResumeRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=100)
    tiktok_clips: int = Field(default=4, ge=3, le=4)


@router.post("/api/chat")
async def chat(payload: ChatRequest, request: Request):
    guard(request)
    if busy():
        raise HTTPException(409, "Un lavoro e gia attivo. Attendi che termini.")
    job = Orchestrator().start(payload.model_dump())
    return {"job_id": job["id"], "status": job["status"], "progress": job["progress"]}


@router.post("/api/resume-media")
async def resume_media(payload: MediaResumeRequest, request: Request):
    guard(request)
    if busy():
        raise HTTPException(409, "Un lavoro e gia attivo. Attendi che termini.")
    try:
        job = Orchestrator().start_media(payload.project_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"job_id": job["id"], "status": job["status"], "progress": job["progress"]}


@router.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    if job_id in job_store:
        return job_store[job_id]
    for name in ("resume_job.json", "job_status.json"):
        for path in ROOT.glob("*/" + name):
            if path.resolve().parent.parent != ROOT.resolve():
                continue
            try:
                job = load(path, {})
            except (ValueError, OSError):
                continue
            if job.get("id") == job_id:
                if job.get("status") in ("running", "queued"):
                    job["status"] = "interrupted"
                    job["current_step"] = "Lavoro non attivo in questo server; controlla i lock e riprendi dal progetto"
                return job
    raise HTTPException(404, "Job non trovato")


@router.get("/api/health")
async def health():
    return Orchestrator().health()
