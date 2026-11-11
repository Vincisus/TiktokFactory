import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Literal

from app.core import project_console as store
from app.core.story_brain import word_count, validate_parts
from app.services.llm_service import LLMService, obj, validate, REVIEW

router = APIRouter(prefix="/api/lean")
TASKS = set()
TEXT = {"type": "string", "minLength": 1}
LINES = {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string", "minLength": 1, "maxLength": 180}}
SCENE = obj({"scene_id": {"type": "integer", "minimum": 1}, "part": {"type": "integer", "minimum": 1}, "pov_id": TEXT, "location": TEXT, "narration": TEXT, "facts": LINES, "knowledge_after": LINES, "visual": TEXT})
FINAL = obj({"ok": {"type": "boolean"}, "issues": REVIEW["properties"]["issues"], "titles": {"type": "array", "minItems": 5, "maxItems": 5, "items": {"type": "string", "minLength": 1, "maxLength": 100}}})


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def limits(brief, parts):
    target = max(100, round(int(brief["duration_minutes"]) * 60 / (len(parts) * 3) * 2.5))
    return int(target * .75), int(target * 1.3)


def check_scene(scene, number, part, ids, bounds):
    validate(scene, SCENE)
    if scene["scene_id"] != number or scene["part"] != part or scene["pov_id"] not in ids:
        raise ValueError("Identita, numero o parte della scena non validi")
    length = word_count(scene["narration"])
    if not bounds[0] <= length <= bounds[1]:
        raise ValueError(f"Lunghezza {length}: richieste {bounds[0]}-{bounds[1]} parole. Nessun rifacimento automatico.")
    return scene


def check_review(value):
    validate(value, REVIEW)
    if value["ok"] != (not value["issues"]):
        raise ValueError("Verdetto contraddittorio")
    if not value["ok"]:
        raise ValueError("Controllo non superato: " + "; ".join(value["issues"]))


class LeanClient:
    def __init__(self, config, model, folder, metrics, update):
        self.config, self.model, self.folder = config, model, folder
        self.metrics, self.update = metrics, update

    async def ask(self, prompt, schema, max_tokens, label):
        number = len(self.metrics) + 1
        record = {"call": number, "step": label, "model": self.model, "max_output_tokens": max_tokens}
        self.metrics.append(record)
        self.update(label)
        started = time.monotonic()
        try:
            payload = {"model": self.model, "messages": [{"role": "system", "content": "Rispondi in italiano con il JSON finale richiesto. Sii conciso; non dilungarti nell'analisi."}, {"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": max_tokens, "stream": False, "response_format": {"type": "json_schema", "json_schema": {"name": "lean_response", "strict": True, "schema": schema}}}
            timeout = float(os.getenv("LMSTUDIO_TOTAL_TIMEOUT", "1800"))
            async with asyncio.timeout(timeout):
                async with httpx.AsyncClient(transport=self.config.transport, timeout=httpx.Timeout(timeout, connect=15)) as client:
                    response = await client.post(self.config.base_url + "/chat/completions", headers={"Authorization": "Bearer " + self.config.api_key}, json=payload)
                    if response.is_error:
                        raise ValueError(f"LM Studio HTTP {response.status_code}: {response.text[:500]}")
                    choice = response.json()["choices"][0]
            message = choice.get("message") or {}
            content = message.get("content") or ""
            if not isinstance(content, str):
                raise ValueError("Content del modello non testuale")
            record.update(response=content, finish_reason=choice.get("finish_reason"), reasoning_characters=len(message.get("reasoning_content") or message.get("reasoning") or ""))
            if choice.get("finish_reason") != "stop":
                raise ValueError("Risposta incompleta: " + repr(choice.get("finish_reason")))
            clean = self.config._clean_text(content)
            if not clean or "<think>" in clean or "</think>" in clean:
                raise ValueError("Risposta finale vuota o reasoning non chiuso; nessun riutilizzo del reasoning")
            return validate(self.config._extract_json(clean), schema)
        except Exception as exc:
            record["error"] = str(exc)
            raise
        finally:
            record["seconds"] = round(time.monotonic() - started, 2)
            store.save(self.folder / f"call_{number:03}.json", record)
            self.update(label + " — richiesta terminata")


async def one_scene(client, concept, structure, state, number, part, beat, ids, bounds):
    context = {"concept": concept, "parte_corrente": part, "scene_precedenti": [{"scene_id": s["scene_id"], "facts": s["facts"], "knowledge_after": s["knowledge_after"]} for s in state]}
    prompt = (
        f"Scrivi la scena {number}, segmento {beat}/3 della parte {part['part']}. "
        f"Narrazione italiana in prima persona, {bounds[0]}-{bounds[1]} parole, senza titoli o commenti. "
        "Genera INSIEME narrazione e breve riepilogo dei fatti realmente raccontati. "
        "Un solo evento centrale. Solo il segmento 3 conclude la parte; non anticipare il finale. "
        "Non ripetere eventi gia conclusi. Le nuove conoscenze devono derivare da cio che avviene. "
        "Una preparazione precedente non deve essere mostrata di nuovo. Una menzogna esplicita "
        "di un personaggio non e una contraddizione dell'autore. Distinguere sospetti e prove. "
        f"JSON scene_id={number}, part={part['part']}, pov_id tra {ids}, location, narration, facts, knowledge_after, visual. "
        "facts e knowledge_after: massimo tre frasi brevi ciascuno. Contesto: " + json.dumps(context, ensure_ascii=False)
    )
    scene = await client.ask(prompt, SCENE, 2048, f"Scena {number}: testo e fatti in una sola chiamata")
    store.save(client.folder / f"scene_{number:03}_draft.json", scene)
    check_scene(scene, number, part["part"], ids, bounds)
    review = await client.ask(
        "Verifica soltanto contraddizioni bloccanti nel seguente testo rispetto ai fatti e al contesto. "
        "Preparare prima e presentare dopo non e un errore. Una menzogna dichiarata non cambia "
        "l'autore reale del lavoro. Una nuova conoscenza e lecita se acquisita nella scena. "
        "Non richiedere che ogni premessa sia mostrata. Non respingere stile o grammatica comprensibili. "
        "Segnala invece letture, prove o azioni dichiarate nel riepilogo ma non avvenute, ruoli scambiati "
        "e anticipazioni decisive del finale. JSON ok booleano, issues lista di frasi brevi; "
        "ok=true se e solo se issues e vuoto. Contesto: " + json.dumps(context, ensure_ascii=False) + ". Scena: " + json.dumps(scene, ensure_ascii=False),
        REVIEW, 768, f"Scena {number}: unico controllo semantico"
    )
    store.save(client.folder / f"scene_{number:03}_review.json", review)
    check_review(review)
    return scene


def snapshot(scene, fingerprint, prior, model):
    return {"fingerprint": fingerprint, "prefix": digest(prior), "scene": scene, "checksum": digest(scene), "model": model, "approved": True}


def restore(value, fingerprint, prior, number, part, ids, bounds):
    if not value or value.get("approved") is not True or value.get("fingerprint") != fingerprint or value.get("prefix") != digest(prior) or value.get("checksum") != digest(value.get("scene")):
        raise ValueError("Checkpoint leggero incompatibile o alterato; non sovrascritto")
    return check_scene(value["scene"], number, part, ids, bounds)


class RunRequest(BaseModel):
    model: str
    mode: Literal["probe", "resume"] = "probe"


@router.get("/models")
async def models():
    config = LLMService()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(config.base_url + "/models", headers={"Authorization": "Bearer " + config.api_key})
            response.raise_for_status()
            values = response.json().get("data", [])
        return {"models": [m["id"] for m in values if isinstance(m.get("id"), str)]}
    except Exception as exc:
        raise HTTPException(502, "LM Studio non raggiungibile: " + str(exc))


@router.get("/projects")
async def projects():
    result = await store.projects()
    for item in result["projects"]:
        folder = store.project(item["id"])
        probe = store.load(folder / "lean/latest_probe.json", {})
        item["probe_model"] = probe.get("model") if probe.get("approved") else None
    return result


@router.get("/jobs/{job_id}")
async def job_status(job_id: str):
    if job_id in store.job_store:
        return store.job_store[job_id]
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(404, "Job non trovato")
    for path in store.ROOT.glob(f"*/lean_runs/{job_id}/job.json"):
        if path.resolve().parents[3] != store.ROOT.resolve():
            continue
        job = store.load(path)
        if job["status"] in ("running", "queued"):
            job["status"] = "interrupted"
        return job
    raise HTTPException(404, "Job non trovato")


@router.get("/projects/{project_id}/script")
async def script_file(project_id):
    path = store.project(project_id) / "lean/script.md"
    if not path.is_file() or path.resolve().parent != (store.project(project_id) / "lean").resolve():
        raise HTTPException(404, "Script leggero non ancora completo")
    return FileResponse(path, filename=project_id + "_script.md")


async def run(folder, job, lock, config):
    run_folder = folder / "lean_runs" / job["id"]
    started = time.monotonic()
    def update(text):
        job["current_step"] = text
        job["elapsed_seconds"] = round(time.monotonic() - started, 1)
        job["logs"] = (job["logs"] + [text])[-200:]
        store.save(run_folder / "job.json", job)
    client = LeanClient(config, job["model"], run_folder, job["calls"], update)
    try:
        job["status"] = "running"
        brief, concept, structure = [store.load(folder / name) for name in ("brief.json", "concept.json", "structure.json")]
        parts = validate_parts(structure, int(brief["tiktok_clips"]))
        ids = [c["id"] for c in concept["characters"]]
        bounds = limits(brief, parts)
        fingerprint = digest([brief, concept, structure, "lean-v1"])
        work = folder / "lean"
        if work.resolve().parent != folder.resolve() or run_folder.resolve().parent.parent != folder.resolve():
            raise ValueError("Cartelle leggere fuori dal progetto")
        if job["mode"] == "probe":
            store.save(work / "latest_probe.json", {"approved": False, "model": job["model"], "fingerprint": fingerprint})
            scene = await one_scene(client, concept, structure, [], 1, parts[0], 1, ids, bounds)
            saved = snapshot(scene, fingerprint, [], job["model"])
            store.save(run_folder / "probe_approved.json", saved)
            store.save(work / "latest_probe.json", saved)
            job["result"] = {"scope": "probe", "scene": scene, "message": "Una scena approvata. Puoi continuare con lo stesso modello; nessun video generato."}
        else:
            probe = store.load(work / "latest_probe.json")
            if not probe or probe.get("model") != job["model"]:
                raise ValueError("Prima completa il test di una scena con il modello selezionato")
            restore(probe, fingerprint, [], 1, parts[0]["part"], ids, bounds)
            state = []
            for number, (part, beat) in enumerate(((p, b) for p in parts for b in range(1, 4)), 1):
                path = work / f"checkpoint_{number:03}.json"
                saved = store.load(path)
                if saved:
                    scene = restore(saved, fingerprint, state, number, part["part"], ids, bounds)
                    update(f"Scena {number}: recuperata dal checkpoint leggero")
                elif number == 1:
                    scene = restore(probe, fingerprint, state, 1, part["part"], ids, bounds)
                    update("Scena 1: riutilizzo della prova approvata, nessuna nuova chiamata")
                else:
                    scene = await one_scene(client, concept, structure, state, number, part, beat, ids, bounds)
                store.save(path, snapshot(scene, fingerprint, state, job["model"]))
                state.append(scene)
                write_text(work / "script_partial.md", "\n\n".join(s["narration"] for s in state))
            final = await client.ask("Controlla continuita e risoluzione dei seguenti fatti rispetto al piano. Non inventare difetti stilistici. JSON ok booleano, issues lista (vuota se ok), titles cinque titoli italiani entro 100 caratteri, senza promettere fatti veri. Piano: " + json.dumps(structure, ensure_ascii=False) + ". Fatti: " + json.dumps([{"facts": s["facts"], "knowledge_after": s["knowledge_after"]} for s in state], ensure_ascii=False), FINAL, 1024, "Unico controllo finale e cinque titoli")
            store.save(run_folder / "final_review.json", final)
            check_review({"ok": final["ok"], "issues": final["issues"]})
            text = "\n\n".join(s["narration"] for s in state)
            path = work / "script.md"
            write_text(path, text)
            store.save(work / "scenes.json", state)
            total = sum(word_count(s["narration"]) for s in state)
            duration, current, board = int(brief["duration_minutes"]) * 60, 0.0, []
            for scene in state:
                end = current + duration * word_count(scene["narration"]) / total
                board.append({"scene_id": scene["scene_id"], "part": scene["part"], "start": current, "end": end, "narration": scene["narration"], "visual": scene["visual"], "timing_source": "estimated_word_count"})
                current = end
            board[-1]["end"] = duration
            store.save(work / "storyboard.json", {"scenes": board, "timing_source": "estimated_word_count", "note": "Nessun allineamento audio reale o immagine generata."})
            store.save(work / "title_options.json", {"titles": final["titles"]})
            job["result"] = {"scope": "narrative", "titles": final["titles"], "script_url": f"/api/lean/projects/{folder.name}/script", "message": "Narrazione e titoli completati. Nessuna voce, immagine o video generati."}
        job["status"] = "completed"
        update("Completato")
    except asyncio.CancelledError:
        job["status"] = "interrupted"
        update("Interrotto: checkpoint leggeri conservati")
        raise
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        update("Interrotto senza altre riscritture automatiche: " + str(exc))
    finally:
        lock.unlink(missing_ok=True)


@router.post("/projects/{project_id}/run")
async def start(project_id, payload: RunRequest, request: Request):
    store.guard(request)
    folder = store.project(project_id)
    if not store.summary(folder)["ready"]:
        raise HTTPException(400, "Piano salvato incompleto")
    config = LLMService()
    available = (await models())["models"]
    if payload.model not in available:
        raise HTTPException(400, "Seleziona un identificatore esposto da LM Studio")
    if store.busy():
        raise HTTPException(409, "Un lavoro e gia attivo o un lock e presente")
    lock = folder / ".scene_recovery.lock"
    try:
        with lock.open("x", encoding="utf-8") as handle:
            handle.write("lean:" + str(os.getpid()))
    except FileExistsError:
        raise HTTPException(409, "Progetto gia in uso")
    job = {"id": uuid.uuid4().hex, "project_id": project_id, "model": payload.model, "mode": payload.mode, "status": "queued", "current_step": "In coda", "elapsed_seconds": 0, "calls": [], "logs": [], "result": None, "error": None, "created_at": datetime.now(timezone.utc).isoformat()}
    try:
        store.save(folder / "lean_runs" / job["id"] / "job.json", job)
        store.job_store[job["id"]] = job
        task = asyncio.create_task(run(folder, job, lock, config))
        TASKS.add(task)
        task.add_done_callback(TASKS.discard)
    except BaseException:
        store.job_store.pop(job["id"], None)
        lock.unlink(missing_ok=True)
        raise
    return {"job_id": job["id"]}
