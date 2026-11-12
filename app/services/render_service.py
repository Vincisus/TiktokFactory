import re
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import AudioFileClip, CompositeVideoClip, ImageClip


class RenderService:
    def __init__(self, width: int = 1080, height: int = 1920, fps: int = 30):
        self.width, self.height, self.fps = width, height, fps

    def ffmpeg_available(self):
        return shutil.which("ffmpeg") is not None

    async def render_story_video(self, storyboard: dict, audio_path: Path, subtitle_path: Path, output_path: Path, duration_seconds: int):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.ffmpeg_available():
            raise RuntimeError("FFmpeg non è disponibile nel PATH.")
        if not audio_path.is_file() or audio_path.stat().st_size == 0:
            raise FileNotFoundError(f"Audio mancante o vuoto: {audio_path}")
        audio = AudioFileClip(str(audio_path))
        scene_clips, subtitle_clips, final = [], [], None
        try:
            duration = min(float(duration_seconds), float(audio.duration))
            if duration <= 0:
                raise ValueError("La traccia audio ha durata nulla.")
            scenes = storyboard.get("scenes") or [{"start": 0, "end": duration, "visual": "Storia"}]
            for index, scene in enumerate(scenes, start=1):
                start = max(0.0, float(scene.get("start", 0)))
                end = min(duration, float(scene.get("end", start + 6)))
                if end <= start:
                    continue
                frame = self._scene_frame(index, scene.get("visual") or scene.get("narration") or "Storia")
                scene_clips.append(ImageClip(np.asarray(frame)).with_start(start).with_duration(end - start))
            if not scene_clips:
                scene_clips.append(ImageClip(np.asarray(self._scene_frame(1, "Storia"))).with_duration(duration))
            for start, end, caption in self._read_srt(subtitle_path):
                start, end = max(0.0, start), min(duration, end)
                if end <= start:
                    continue
                rgb, alpha = self._subtitle_frame(caption)
                image = ImageClip(rgb).with_duration(end - start).with_start(start)
                mask = ImageClip(alpha, is_mask=True).with_duration(end - start).with_start(start)
                subtitle_clips.append(image.with_mask(mask))
            final = CompositeVideoClip(scene_clips + subtitle_clips, size=(self.width, self.height)).with_audio(audio).with_duration(duration)
            final.write_videofile(str(output_path), fps=self.fps, codec="libx264", audio_codec="aac", preset="medium", threads=2, logger=None, temp_audiofile=str(output_path.with_suffix(".temp-audio.m4a")), remove_temp=True)
        finally:
            if final is not None:
                final.close()
            for clip in subtitle_clips + scene_clips:
                try:
                    clip.close()
                except Exception:
                    pass
            audio.close()
        if not output_path.is_file() or output_path.stat().st_size < 1024:
            raise RuntimeError("FFmpeg non ha prodotto un MP4 valido.")
        return output_path

    def _scene_frame(self, number: int, visual: str):
        image = Image.new("RGB", (self.width, self.height), (11, 11, 18))
        draw = ImageDraw.Draw(image)
        for y in range(self.height):
            shade = int(11 + 18 * y / max(1, self.height))
            draw.line((0, y, self.width, y), fill=(shade, shade, min(40, shade + 12)))
        draw.rounded_rectangle((60, 90, self.width - 60, 170), radius=24, fill=(255, 209, 102))
        draw.text((90, 105), f"SCENA {number:02}", font=self._font(42), fill=(15, 15, 22))
        lines = self._wrap(draw, str(visual)[:500], self._font(58), self.width - 160)[:8]
        y = self.height // 2 - len(lines) * 41
        for line in lines:
            draw.text((80, y), line, font=self._font(58), fill="white", stroke_width=2, stroke_fill=(0, 0, 0))
            y += 82
        return image

    def _subtitle_frame(self, text: str):
        image, alpha = Image.new("RGB", (self.width, self.height), (0, 0, 0)), Image.new("L", (self.width, self.height), 0)
        draw, mask = ImageDraw.Draw(image), ImageDraw.Draw(alpha)
        font, line_height = self._font(42), 56
        lines = self._wrap(draw, text, font, self.width - 150)[:3]
        box_height, top = line_height * len(lines) + 44, self.height - (line_height * len(lines) + 44) - 150
        draw.rounded_rectangle((45, top, self.width - 45, top + box_height), radius=24, fill=(0, 0, 0))
        mask.rounded_rectangle((45, top, self.width - 45, top + box_height), radius=24, fill=205)
        y = top + 20
        for line in lines:
            draw.text((75, y), line, font=font, fill="white")
            y += line_height
        return np.asarray(image), np.asarray(alpha)

    @staticmethod
    def _font(size: int):
        for candidate in ("arial.ttf", "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                pass
        return ImageFont.load_default()

    @staticmethod
    def _wrap(draw, text: str, font, max_width: int):
        lines, current = [], ""
        for word in re.findall(r"\S+", text):
            candidate = f"{current} {word}".strip()
            if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    @staticmethod
    def _read_srt(path: Path):
        if not path or not path.is_file():
            return []
        timestamp = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})")
        result = []
        for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip()):
            lines = block.splitlines()
            match = next((timestamp.search(line) for line in lines if timestamp.search(line)), None)
            if not match:
                continue
            v = [int(item) for item in match.groups()]
            start = v[0]*3600 + v[1]*60 + v[2] + v[3]/1000
            end = v[4]*3600 + v[5]*60 + v[6] + v[7]/1000
            text = " ".join(lines[2:]).strip()
            if text:
                result.append((start, end, text))
        return result
