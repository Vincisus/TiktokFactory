import re
from pathlib import Path


class SubtitleService:
    def create_srt_from_script(self, script: str, output_path: Path, target_duration: int):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sentences = self._split_sentences(script)

        if not sentences:
            sentences = ["Storia non disponibile."]

        total_chars = sum(len(sentence) for sentence in sentences)
        if total_chars == 0:
            total_chars = 1

        durations = []
        remaining = target_duration
        for sentence in sentences:
            share = len(sentence) / total_chars
            duration = max(1.5, round(target_duration * share, 2))
            durations.append(duration)

        scale = target_duration / sum(durations)
        durations = [duration * scale for duration in durations]

        srt_blocks = []
        current = 0.0
        for index, (sentence, duration) in enumerate(zip(sentences, durations), start=1):
            start = current
            end = min(target_duration, current + duration)
            current = end
            srt_blocks.append(
                f"{index}\n"
                f"{self._format_timestamp(start)} --> {self._format_timestamp(end)}\n"
                f"{sentence}\n"
            )

        output_path.write_text("\n".join(srt_blocks), encoding="utf-8")
        return output_path

    @staticmethod
    def _split_sentences(script: str):
        text = re.sub(r"\s+", " ", script).strip()
        parts = re.split(r"(?<=[.!?])\s+", text)
        return [part.strip() for part in parts if part.strip()]

    @staticmethod
    def _format_timestamp(seconds: float):
        milliseconds = int(round(seconds * 1000))
        hours, remainder = divmod(milliseconds, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        secs, millis = divmod(remainder, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"
