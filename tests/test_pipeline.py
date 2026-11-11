from app.services.subtitle_service import SubtitleService
from app.services.tiktok_service import TikTokService


def test_subtitle_generation():
    service = SubtitleService()
    output = service.create_srt_from_script(
        "Ciao. Questo è un test. La storia continua.",
        output_path=None,
        target_duration=30,
    )
    assert output is not None


def test_select_parts():
    assert TikTokService._select_parts(10, 4) == [0, 2, 5, 7]
    assert TikTokService._select_parts(4, 4) == [0, 1, 2, 3]
