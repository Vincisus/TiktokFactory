import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from app.core.story_brain import StoryBrain
from app.core.planning_service import PlanningService
from app.core.quality_control import QualityControl
from app.services.llm_service import LLMService
from app.services.tts_service import TTSService
from app.services.subtitle_service import SubtitleService
from app.services.render_service import RenderService
from app.services.tiktok_service import TikTokService
from app.services.metadata_service import MetadataService

job_store = {}
background_tasks = set()
logger = logging.getLogger("uvicorn.error")


def run_async_service(method, **kwargs):
    return asyncio.run(method(**kwargs))


class Orchestrator:
    def __init__(self):
        self.llm = LLMService()
        self.brain = StoryBrain(self.llm)
        self.planner = PlanningService(self.llm)
        self.tts = TTSService()
        self.subtitles = SubtitleService()
        self.renderer = RenderService()
        self.tiktok = TikTokService()
        self.metadata = MetadataService(self.llm)
        self.qc = QualityControl()

    def health(self):
        return {"status": "ok", "llm_configured": bool(self.llm.base_url), "ffmpeg_available": self.renderer.ffmpeg_available(), "note": "Non verifica una generazione reale del modello."}

    def start(self, request):
        job_id = uuid.uuid4().hex
        job = {"id": job_id, "status": "queued", "progress": 0, "current_step": "In coda", "logs": [], "result": None, "error": None, "created_at": datetime.now().isoformat()}
        job_store[job_id] = job
        task = asyncio.create_task(self._run(job_id, request))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)
        return job

    async def _run(self, job_id, request):
        job = job_store[job_id]
        job["status"] = "running"
        project_dir = None

        def persist():
            if project_dir is not None:
                self._save(project_dir / "job_status.json", job)

        def update(progress, step):
            job["progress"] = progress
            job["current_step"] = step
            job["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {step}")
            persist()

        self.brain.on_progress = lambda text: update(job["progress"], text)
        self.planner.on_progress = lambda text: update(job["progress"], text)
        try:
            project_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
            project_dir = Path("projects") / project_id
            project_dir.mkdir(parents=True, exist_ok=True)
            job["project_dir"] = str(project_dir)
            update(5, "Creazione progetto")
            brief = {"id": project_id, "request": request, "series": request.get("series", "tradimenti_e_vendetta"), "duration_minutes": max(10, int(request.get("duration_minutes", 12))), "tiktok_clips": min(4, max(3, int(request.get("tiktok_clips", 4)))), "language": "it"}
            self._save(project_dir / "brief.json", brief)
            update(12, "Pianificazione e revisione concept")
            concept = await self.planner.generate_concept(brief, project_dir)
            self._save(project_dir / "concept.json", concept)
            update(22, "Pianificazione e revisione struttura")
            structure = await self.planner.generate_structure(concept, brief, project_dir)
            self._save(project_dir / "structure.json", structure)
            update(32, "Scrittura scene")
            script = await self.brain.generate_script(concept, structure, brief)
            self._save(project_dir / "script.md", script)
            update(45, "Creazione storyboard con durate stimate")
            storyboard = await self.brain.generate_storyboard(script, structure, brief)
            self._save(project_dir / "storyboard.json", storyboard)
            update(55, "Generazione voce locale")
            audio_path = await self.tts.generate_narration(script, project_dir / "audio" / "narration.mp3")
            update(63, "Creazione sottotitoli con tempi stimati")
            subtitle_path = self.subtitles.create_srt_from_script(script, project_dir / "subtitles" / "narration.srt", target_duration=brief["duration_minutes"] * 60)
            update(72, "Rendering video di prova")
            render_path = await asyncio.to_thread(run_async_service, self.renderer.render_story_video, storyboard=storyboard, audio_path=audio_path, subtitle_path=subtitle_path, output_path=project_dir / "render" / "youtube_video.mp4", duration_seconds=brief["duration_minutes"] * 60)
            update(84, "Creazione clip TikTok")
            clips = await asyncio.to_thread(run_async_service, self.tiktok.create_clips, render_path=render_path, structure=structure, output_dir=project_dir / "tiktok", clips_requested=brief["tiktok_clips"])
            update(92, "Generazione metadati")
            metadata = await self.metadata.generate_metadata(concept, structure)
            self._save(project_dir / "metadata.json", metadata)
            update(97, "Controllo qualita")
            report = await asyncio.to_thread(self.qc.evaluate, render_path=render_path, clips=clips, structure=structure, min_duration=brief["duration_minutes"] * 60)
            self._save(project_dir / "quality_report.json", report)
            job["result"] = {"project_id": project_id, "project_dir": str(project_dir), "youtube_video": str(render_path), "tiktok_clips": [str(path) for path in clips], "quality_report": report, "metadata": metadata}
            if report.get("issues"):
                raise ValueError("Controllo qualita non superato: " + "; ".join(report["issues"]))
            job["status"] = "completed"
            update(100, "Completato: controllare manualmente il risultato")
        except Exception as exc:
            logger.exception("Pipeline interrotta")
            job["status"] = "failed"
            job["error"] = f"{type(exc).__name__}: {exc}"
            update(job["progress"], "Interrotto: " + job["error"])

    @staticmethod
    def _save(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, ensure_ascii=False, indent=2) if isinstance(data, (dict, list)) else str(data)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
