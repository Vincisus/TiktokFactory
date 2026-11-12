from pathlib import Path
from moviepy import VideoFileClip


class QualityControl:
    MIN_CLIP_SECONDS = 5

    def evaluate(self, render_path: Path, clips: list[Path], structure: dict, min_duration: int, required_clips: int = 3):
        report = {
            "youtube_video_exists": render_path.is_file(),
            "youtube_video_bytes": render_path.stat().st_size if render_path.is_file() else 0,
            "tiktok_clips_count": len(clips),
            "required_clips": required_clips,
            "youtube_duration_seconds": 0,
            "passes_minimum_duration": False,
            "clip_checks": [],
            "issues": [],
            "warnings": [],
        }
        if not report["youtube_video_exists"] or report["youtube_video_bytes"] < 1024:
            report["issues"].append("Il file video principale manca o è vuoto.")
            return report
        try:
            with VideoFileClip(str(render_path)) as video:
                report["youtube_duration_seconds"] = round(float(video.duration or 0), 2)
                if video.w <= 0 or video.h <= 0 or video.fps <= 0:
                    report["issues"].append("Il video principale ha dimensioni o FPS non validi.")
                if video.audio is None:
                    report["issues"].append("Il video principale non contiene una traccia audio.")
        except Exception as exc:
            report["issues"].append(f"Il video principale non è decodificabile: {exc}")
            return report
        report["passes_minimum_duration"] = report["youtube_duration_seconds"] >= min_duration
        if not report["passes_minimum_duration"]:
            report["warnings"].append(f"Durata effettiva {report['youtube_duration_seconds']} s inferiore ai {min_duration} s richiesti; il video resta esportato.")
        for path in clips:
            item = {"file": path.name, "exists": path.is_file(), "bytes": path.stat().st_size if path.is_file() else 0}
            if not item["exists"] or item["bytes"] < 1024:
                item["valid"] = False
                report["issues"].append(f"Clip mancante o vuota: {path.name}")
            else:
                try:
                    with VideoFileClip(str(path)) as clip:
                        item["duration_seconds"] = round(float(clip.duration or 0), 2)
                        item["has_audio"] = clip.audio is not None
                        item["valid"] = self.MIN_CLIP_SECONDS <= item["duration_seconds"] <= 60.5 and item["has_audio"]
                        if not item["valid"]:
                            report["issues"].append(f"Clip non valida per durata/audio: {path.name}")
                except Exception as exc:
                    item["valid"] = False
                    report["issues"].append(f"Clip non decodificabile {path.name}: {exc}")
            report["clip_checks"].append(item)
        if len(clips) < required_clips:
            report["issues"].append(f"Generate {len(clips)} clip TikTok su {required_clips} richieste.")
        return report
