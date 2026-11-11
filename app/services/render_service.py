import shutil
import subprocess
from pathlib import Path

from moviepy import ImageClip, AudioFileClip, TextClip, CompositeVideoClip


class RenderService:
    def __init__(self, width: int = 1080, height: int = 1920, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps

    def ffmpeg_available(self):
        return shutil.which("ffmpeg") is not None

    async def render_story_video(
        self,
        storyboard: dict,
        audio_path: Path,
        subtitle_path: Path,
        output_path: Path,
        duration_seconds: int,
    ):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        scenes = storyboard.get("scenes", [])

        if not scenes:
            background = ImageClip(self._solid_frame()).with_duration(duration_seconds)
            audio = AudioFileClip(str(audio_path))
            final = background.with_audio(audio)
            final.write_videofile(
                str(output_path),
                fps=self.fps,
                codec="libx264",
                audio_codec="aac",
                logger=None,
            )
            return output_path

        clips = []
        for scene in scenes:
            start = float(scene.get("start", 0))
            end = float(scene.get("end", start + 6))
            duration = max(1, end - start)

            background = ImageClip(self._solid_frame()).with_duration(duration)
            text = scene.get("on_screen_text") or scene.get("narration", "")

            if text:
                text_clip = (
                    TextClip(
                        text=text,
                        font_size=54,
                        color="white",
                        size=(self.width - 120, None),
                        method="caption",
                    )
                    .with_duration(duration)
                    .with_position(("center", "center"))
                )
                background = CompositeVideoClip([background, text_clip])

            clips.append(background.with_start(start))

        audio = AudioFileClip(str(audio_path))
        final = CompositeVideoClip(clips, size=(self.width, self.height)).with_audio(audio)
        final = final.with_duration(min(duration_seconds, audio.duration))

        final.write_videofile(
            str(output_path),
            fps=self.fps,
            codec="libx264",
            audio_codec="aac",
            logger=None,
        )
        return output_path

    def _solid_frame(self):
        from PIL import Image

        image = Image.new("RGB", (self.width, self.height), (11, 11, 18))
        temp_path = Path("temp_background.png")
        image.save(temp_path)
        return str(temp_path)
