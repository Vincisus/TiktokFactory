import tempfile
from pathlib import Path
import pytest
from app.services.subtitle_service import SubtitleService
from app.services.tiktok_service import TikTokService


def test_subtitle_generation():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "captions.srt"
        result = SubtitleService().create_srt_from_script("Ciao. Questo è un test. La storia continua.", path, 30)
        assert result == path
        content = path.read_text(encoding="utf-8")
        assert "00:00:30,000" in content
        assert "Ciao." in content


def test_subtitle_generation_rejects_non_positive_duration():
    with tempfile.TemporaryDirectory() as directory:
        with pytest.raises(ValueError):
            SubtitleService().create_srt_from_script("Test.", Path(directory) / "x.srt", 0)


def test_select_parts():
    assert TikTokService._select_parts(10, 4) == [0, 2, 5, 7]
    assert TikTokService._select_parts(4, 4) == [0, 1, 2, 3]
    assert TikTokService._select_parts(0, 4) == []
