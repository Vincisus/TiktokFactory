import re
from pathlib import Path


class SubtitleService:
    def create_srt_from_script(self, script: str, output_path: Path, target_duration: float):
        if target_duration <= 0:
            raise ValueError("La durata dei sottotitoli deve essere positiva.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sentences = self._split_sentences(script) or ["Storia non disponibile."]
        total_chars = max(1, sum(len(sentence) for sentence in sentences))
        weights = [len(sentence) / total_chars for sentence in sentences]
        durations = [max(min(1.0, target_duration / len(sentences)), target_duration * weight) for weight in weights]
        scale = target_duration / sum(durations)
        durations = [duration * scale for duration in durations]
        blocks, current = [], 0.0
        for index, (sentence, duration) in enumerate(zip(sentences, durations), start=1):
            start = current
            end = target_duration if index == len(sentences) else min(target_duration, current + duration)
            current = end
            blocks.append(f"{index}\n{self._format_timestamp(start)} --> {self._format_timestamp(end)}\n{sentence}\n")
        output_path.write_text("\n".join(blocks), encoding="utf-8")
        return output_path

    @staticmethod
    def _split_sentences(script: str):
        text = re.sub(r"\s+", " ", script).strip()
        text = re.sub(r"(?m)^#{1,6}\s*", "", text)
        return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]

    @staticmethod
    def _format_timestamp(seconds: float):
        milliseconds = max(0, int(round(seconds * 1000)))
        hours, remainder = divmod(milliseconds, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        secs, millis = divmod(remainder, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"
