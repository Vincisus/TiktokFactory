import asyncio
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

from app.core.story_brain import StoryBrain
from app.core.story_state import StoryState
from app.core.quality_control import QualityControl
from app.services.llm_service import LLMService
from app.services.tts_service import TTSService
from app.services.subtitle_service import SubtitleService
from app.services.render_service import RenderService
from app.services.tiktok_service import TikTokService
from app.services.metadata_service import MetadataService


class Orchestrator:
    def __init__(self):
        self.llm = LLMService()
        self.brain = StoryBrain(self.llm)
        self.tts = TTSService()
        self.subtitles = SubtitleService()
        self.renderer = RenderService()
        self.tiktok = TikTokService()
        self.metadata = MetadataService(self.llm)
        self.qc = QualityControl()

    def health(self):
        return {
            "status": "ok",
            "llm_configured": bool(self.llm.base_url),
            "ffmpeg_available": self.renderer.ffmpeg_available(),
        }

    async def run(self, request: dict):
        project_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        project_dir = Path("projects") / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        brief = {
            "id": project_id,
            "request": request,
            "series": request.get("series", "tradimenti_e_vendetta"),
            "duration_minutes": max(10, int(request.get("duration_minutes", 12))),
            "tiktok_clips": max(3, int(request.get("tiktok_clips", 4))),
            "language": "it",
        }
        self._save(project_dir / "brief.json", brief)

        concept = await self.brain.generate_concept(brief)
        self._save(project_dir / "concept.json", concept)

        structure = await self.brain.generate_structure(concept, brief)
        self._save(project_dir / "structure.json", structure)

        script = await self.brain.generate_script(concept, structure, brief)
        self._save(project_dir / "script.md", script)

        storyboard = await self.brain.generate_storyboard(script, structure, brief)
        self._save(project_dir / "storyboard.json", storyboard)

        audio_path = await self.tts.generate_narration(
            script,
            project_dir / "audio" / "narration.mp3",
        )

        subtitle_path = self.subtitles.create_srt_from_script(
            script,
            project_dir / "subtitles" / "narration.srt",
            target_duration=brief["duration_minutes"] * 60,
        )

        render_path = await self.renderer.render_story_video(
            storyboard=storyboard,
            audio_path=audio_path,
            subtitle_path=subtitle_path,
            output_path=project_dir / "render" / "youtube_video.mp4",
            duration_seconds=brief["duration_minutes"] * 60,
        )

        clips = await self.tiktok.create_clips(
            render_path=render_path,
            structure=structure,
            output_dir=project_dir / "tiktok",
            clips_requested=brief["tiktok_clips"],
        )

        metadata = await self.metadata.generate_metadata(concept, structure)
        self._save(project_dir / "metadata.json", metadata)

        report = self.qc.evaluate(
            render_path=render_path,
            clips=clips,
            structure=structure,
            min_duration=brief["duration_minutes"] * 60,
        )
        self._save(project_dir / "quality_report.json", report)

        return {
            "status": "completed",
            "project_id": project_id,
            "project_dir": str(project_dir),
            "youtube_video": str(render_path),
            "tiktok_clips": [str(path) for path in clips],
            "quality_report": report,
            "metadata": metadata,
        }

    @staticmethod
    def _save(path: Path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, (dict, list)):
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            path.write_text(str(data), encoding="utf-8")
