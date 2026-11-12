import asyncio
import wave
from pathlib import Path

import pyttsx3


class TTSService:
    def __init__(self, voice: str | None = None):
        self.voice = voice

    async def generate_narration(self, script: str, output_path: Path):
        output_path = output_path.with_suffix(".wav")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        text = self._clean_script(script)
        if not text:
            raise ValueError("La sceneggiatura è vuota: impossibile generare la voce.")
        output_path.unlink(missing_ok=True)
        await asyncio.to_thread(self._synthesize, text, output_path)
        if not output_path.is_file() or output_path.stat().st_size < 44:
            raise RuntimeError("Il motore TTS non ha prodotto un file WAV valido.")
        try:
            with wave.open(str(output_path), "rb") as audio:
                if audio.getnframes() <= 0 or audio.getframerate() <= 0:
                    raise RuntimeError("Il file WAV generato non contiene audio.")
        except (wave.Error, EOFError) as exc:
            raise RuntimeError(f"Il file TTS non è un WAV leggibile: {exc}") from exc
        return output_path

    def _synthesize(self, text: str, output_path: Path):
        engine = pyttsx3.init()
        try:
            engine.setProperty("rate", 165)
            engine.setProperty("volume", 1.0)
            if self.voice:
                for voice in engine.getProperty("voices"):
                    if self.voice.lower() in voice.id.lower() or self.voice.lower() in voice.name.lower():
                        engine.setProperty("voice", voice.id)
                        break
            engine.save_to_file(text, str(output_path))
            engine.runAndWait()
        finally:
            engine.stop()

    @staticmethod
    def duration_seconds(audio_path: Path) -> float:
        with wave.open(str(audio_path), "rb") as audio:
            return audio.getnframes() / float(audio.getframerate())

    @staticmethod
    def _clean_script(script: str):
        return "\n".join(line.strip() for line in script.splitlines() if line.strip() and not line.strip().startswith("#"))
