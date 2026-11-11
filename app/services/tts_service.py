import asyncio
from pathlib import Path

import edge_tts


class TTSService:
    def __init__(self, voice: str = "it-IT-ElsaNeural"):
        self.voice = voice

    async def generate_narration(self, script: str, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        text = self._clean_script(script)

        communicate = edge_tts.Communicate(text, self.voice)
        await communicate.save(str(output_path))
        return output_path

    @staticmethod
    def _clean_script(script: str):
        return "\n".join(
            line.strip()
            for line in script.splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
