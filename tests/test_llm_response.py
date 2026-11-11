import pytest

from app.services.llm_service import LLMService


def test_json_with_reasoning_and_fence():
    text = '<think>analisi</think>\n```json\n{"parts": []}\n```'
    assert LLMService._extract_json(text) == {'parts': []}


def test_malformed_json_has_details():
    with pytest.raises(ValueError, match='JSON del modello non valido'):
        LLMService._extract_json('{"parts":')


def test_no_json():
    with pytest.raises(ValueError, match='oggetto JSON'):
        LLMService._extract_json('solo testo')


def test_clean_narration():
    assert LLMService._clean_text('<think>analisi</think> Storia.') == 'Storia.'
