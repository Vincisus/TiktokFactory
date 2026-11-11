import asyncio
from pathlib import Path

import pyttsx3


class TTSService:
    def __init__(self, voice: str | None = None):
        self.voice = voice

    async def generate_narration(self, script: str, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        text = self._clean_script(script)
        await asyncio.to_thread(self._synthesize, text, output_path)
        return output_path

    def _synthesize(self, text: str, output_path: Path):
        engine = pyttsx3.init()
        engine.setProperty("rate", 165)
        engine.setProperty("volume", 1.0)

        if self.voice:
            voices = engine.getProperty("voices")
            for voice in voices:
                if self.voice.lower() in voice.id.lower() or self.voice.lower() in voice.name.lower():
                    engine.setProperty("voice", voice.id)
                    break

        engine.save_to_file(text, str(output_path))
        engine.runAndWait()

    @staticmethod
    def _clean_script(script: str):
        return "\n".join(
            line.strip()
            for line in script.splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
