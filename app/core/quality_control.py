from pathlib import Path

from moviepy import VideoFileClip


class QualityControl:
    def evaluate(self, render_path: Path, clips: list[Path], structure: dict, min_duration: int):
        report = {
            "youtube_video_exists": render_path.exists(),
            "tiktok_clips_count": len(clips),
            "required_clips": len(structure.get("parts", [])),
            "youtube_duration_seconds": 0,
            "passes_minimum_duration": False,
            "issues": [],
        }

        if render_path.exists():
            with VideoFileClip(str(render_path)) as video:
                report["youtube_duration_seconds"] = round(video.duration, 2)

        report["passes_minimum_duration"] = (
            report["youtube_duration_seconds"] >= min_duration
        )

        if not report["passes_minimum_duration"]:
            report["issues"].append("Il video YouTube è più corto della durata minima richiesta.")

        if len(clips) < 3:
            report["issues"].append("Sono state generate meno di 3 clip TikTok.")

        return report
