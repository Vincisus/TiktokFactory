import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from app.core.orchestrator import job_store

router = APIRouter()
ROOT = Path("projects")
TASKS = set()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def load(path, default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def project(project_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", project_id):
        raise HTTPException(400, "ID progetto non valido")
    path = ROOT / project_id
    if not path.is_dir() or path.resolve().parent != ROOT.resolve():
        raise HTTPException(404, "Progetto non trovato")
    return path


def guard(request):
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Operazione consentita solo dalla pagina locale dello stesso server")


def busy():
    return any(j.get("status") in ("queued", "running") for j in job_store.values()) or any(ROOT.glob("*/.scene_recovery.lock"))


def summary(folder):
    brief = load(folder / "brief.json", {})
    concept = load(folder / "concept.json", {})
    status = load(folder / "resume_job.json") or load(folder / "job_status.json", {})
    locked = (folder / ".scene_recovery.lock").exists()
    stale = status.get("status") in ("queued", "running") and status.get("id") not in job_store and not locked
    return {"id": folder.name, "title": concept.get("title", folder.name), "ready": all((folder / n).is_file() for n in ("brief.json", "concept.json", "structure.json")) and brief.get("id") == folder.name, "status": "interrupted" if stale else status.get("status", "saved"), "locked": locked, "tracked": status.get("id") in job_store, "approved_scenes": len(list((folder / "scenes").glob("*_checkpoint_v2.json"))), "job": {**status, "status": "interrupted"} if stale else status, "titles": load(folder / "title_options.json", {}).get("titles") or load(folder / "metadata.json", {}).get("title_options", []), "script": (folder / "script.md").is_file()}


@router.get("/api/projects")
async def projects():
    ROOT.mkdir(parents=True, exist_ok=True)
    result = []
    for folder in sorted(ROOT.iterdir(), reverse=True):
        if folder.is_dir() and re.fullmatch(r"[A-Za-z0-9_-]+", folder.name) and (folder / "brief.json").is_file() and folder.resolve().parent == ROOT.resolve():
            try:
                result.append(summary(folder))
            except (ValueError, OSError):
                result.append({"id": folder.name, "title": folder.name, "status": "invalid", "ready": False, "locked": False, "titles": [], "job": {"error": "File di progetto non leggibili"}})
    return {"projects": result, "busy": busy()}


@router.get("/api/projects/{project_id}/files/{name}")
async def project_file(project_id, name):
    folder = project(project_id)
    if name not in {"script.md", "storyboard.json", "title_options.json", "resume_job.json"}:
        raise HTTPException(404, "File non esposto")
    path = folder / name
    if not path.is_file() or path.resolve().parent != folder.resolve():
        raise HTTPException(404, "File non disponibile")
    return FileResponse(path, filename=name)


def title_fallback(concept):
    base = str(concept.get("title") or "Una scelta difficile").strip()[:65]
    return [base, base + " — La mia versione", base + " — Quello che non sapevo", base + " — La scelta finale", base + " — Fiducia e conseguenze"]


async def make_titles(llm, folder, concept, structure):
    existing = load(folder / "title_options.json", {})
    if existing.get("titles"):
        return existing
    try:
        data = await llm.generate_json("Proponi cinque titoli italiani differenti per questa storia di fiction, massimo 100 caratteri ciascuno. Non inventare eventi, non promettere una storia vera. JSON con titles: lista di cinque stringhe. Concept: " + json.dumps(concept, ensure_ascii=False) + ". Piano: " + json.dumps(structure, ensure_ascii=False))
        values = data.get("titles")
        if not isinstance(values, list) or len(values) != 5 or not all(isinstance(x, str) and 1 <= len(x.strip()) <= 100 for x in values) or len({x.strip().casefold() for x in values}) != 5:
            raise ValueError("Proposte di titolo non valide")
        result = {"titles": [x.strip() for x in values], "source": "model"}
    except Exception as exc:
        result = {"titles": title_fallback(concept), "source": "template_fallback", "warning": str(exc)}
    save(folder / "title_options.json", result)
    return result


async def run_resume(folder, job, lock):
    def update(step, progress=None):
        job["current_step"] = step
        if progress is not None:
            job["progress"] = progress
        job["logs"] = (job["logs"] + [f"[{datetime.now().strftime('%H:%M:%S')}] {step}"])[-500:]
        save(folder / "resume_job.json", job)
    try:
        from app.core.story_brain import StoryBrain
        from app.services.llm_service import LLMService
        brief, concept, structure = [load(folder / name) for name in ("brief.json", "concept.json", "structure.json")]
        llm = LLMService()
        brain = StoryBrain(llm)
        if not hasattr(brain, "prepare_recovery_card"):
            raise RuntimeError("Motore di recupero non installato. Avvia con Avvia.bat per completare la configurazione automatica.")
        brain.on_progress = update
        job["status"] = "running"
        update("Ripresa dal piano salvato; scrittura e storyboard", 10)
        script = await brain.generate_script(concept, structure, brief)
        save(folder / "storyboard.json", await brain.generate_storyboard(script, structure, brief))
        (folder / "script.md").write_text(script, encoding="utf-8")
        update("Generazione di cinque proposte di titolo", 95)
        titles = await make_titles(llm, folder, concept, structure)
        job["result"] = {"project_id": folder.name, "scope": "narrative", "title_options": titles["titles"], "script": f"/api/projects/{folder.name}/files/script.md", "storyboard": f"/api/projects/{folder.name}/files/storyboard.json"}
        job["status"] = "completed"
        update("Scrittura, storyboard e titoli completati. Voce e video non generati da questa ripresa.", 100)
    except asyncio.CancelledError:
        job["status"] = "interrupted"
        update("Server arrestato: scene approvate conservate")
        raise
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = f"{type(exc).__name__}: {exc}"
        update("Interrotto: " + job["error"])
    finally:
        lock.unlink(missing_ok=True)


@router.post("/api/projects/{project_id}/resume")
async def resume_project(project_id, request: Request):
    guard(request)
    folder = project(project_id)
    if busy():
        raise HTTPException(409, "Un lavoro e gia attivo oppure esiste un lock di recupero. Non avviare due generazioni insieme.")
    info = summary(folder)
    if not info["ready"]:
        raise HTTPException(400, "Mancano brief, concept o struttura validi")
    lock = folder / ".scene_recovery.lock"
    try:
        with lock.open("x", encoding="utf-8") as handle:
            handle.write("web:" + str(__import__("os").getpid()))
    except FileExistsError:
        raise HTTPException(409, "Progetto gia in uso")
    job = {"id": uuid.uuid4().hex, "project_id": project_id, "status": "queued", "progress": 0, "current_step": "Ripresa in coda", "logs": [], "result": None, "error": None, "created_at": datetime.now(timezone.utc).isoformat()}
    try:
        save(folder / "resume_job.json", job)
        job_store[job["id"]] = job
        task = asyncio.create_task(run_resume(folder, job, lock))
        TASKS.add(task)
        task.add_done_callback(TASKS.discard)
    except BaseException:
        job_store.pop(job["id"], None)
        lock.unlink(missing_ok=True)
        raise
    return {"job_id": job["id"], "status": job["status"]}
