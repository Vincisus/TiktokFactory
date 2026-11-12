from pathlib import Path
from moviepy import VideoFileClip


class TikTokService:
    MIN_CLIP_SECONDS = 5
    MAX_CLIP_SECONDS = 60

    async def create_clips(self, render_path: Path, structure: dict, output_dir: Path, clips_requested: int = 4):
        output_dir.mkdir(parents=True, exist_ok=True)
        if not render_path.is_file() or render_path.stat().st_size == 0:
            raise FileNotFoundError(f"Video sorgente mancante o vuoto: {render_path}")
        parts = structure.get("parts", [])
        if not parts:
            raise ValueError("La struttura non contiene parti: impossibile creare clip.")
        created = []
        with VideoFileClip(str(render_path)) as source:
            total = float(source.duration or 0)
            if total < self.MIN_CLIP_SECONDS:
                raise ValueError("Il video sorgente è troppo corto per creare clip TikTok.")
            for index in self._select_parts(len(parts), clips_requested):
                part_start, part_end = total * index / len(parts), total * (index + 1) / len(parts)
                available = part_end - part_start
                if available < self.MIN_CLIP_SECONDS:
                    continue
                length = min(self.MAX_CLIP_SECONDS, available)
                start = part_start + max(0.0, (available - length) / 2)
                output_path = output_dir / f"tiktok_part_{index + 1:02}.mp4"
                clip = source.subclipped(start, min(total, start + length))
                try:
                    clip.write_videofile(str(output_path), fps=source.fps or 30, codec="libx264", audio_codec="aac", preset="medium", threads=2, logger=None)
                finally:
                    clip.close()
                if not output_path.is_file() or output_path.stat().st_size < 1024:
                    raise RuntimeError(f"Clip TikTok non valida: {output_path.name}")
                created.append(output_path)
        return created

    @staticmethod
    def _select_parts(total_parts: int, requested: int):
        if total_parts <= 0 or requested <= 0:
            return []
        if total_parts <= requested:
            return list(range(total_parts))
        step = total_parts / requested
        return sorted({min(total_parts - 1, int(index * step)) for index in range(requested)})
