import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from app.services.llm_service import LLMService, REVIEW, schema_for, validate


def response_event(content, finish="stop"):
    event = {"choices": [{"delta": {"content": content}, "finish_reason": finish}]}
    return "data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n"


class FormatTests(unittest.TestCase):
    def test_fenced_json(self):
        self.assertEqual(LLMService._extract_json('```json\n{"ok": true}\n```'), {"ok": True})

    def test_invalid_json(self):
        with self.assertRaises(ValueError):
            LLMService._extract_json('{"ok": true "issues": []}')

    def test_reject_extra_text(self):
        with self.assertRaises(ValueError):
            LLMService._extract_json('{"ok": true} garbage')

    def test_reject_string_boolean(self):
        with self.assertRaises(ValueError):
            validate({"ok": "true", "issues": []}, REVIEW)

    def test_review_schema_selected(self):
        self.assertEqual(schema_for('Sei un revisore. Controlla'), REVIEW)

    def test_part_count_schema(self):
        self.assertEqual(schema_for('Pianifica 4 parti')['properties']['parts']['maxItems'], 4)


class APITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"LMSTUDIO_BASE_URL": "http://127.0.0.1:1234/v1", "LLM_DIAGNOSTIC_DIR": self.temp.name})
        self.env.start()

    async def asyncTearDown(self):
        self.env.stop()
        self.temp.cleanup()

    async def test_schema_sent_and_raw_saved(self):
        def handle(request):
            payload = json.loads(request.content)
            self.assertEqual(payload['response_format']['type'], 'json_schema')
            self.assertEqual(payload['response_format']['json_schema']['schema'], REVIEW)
            return httpx.Response(200, text=response_event('{"ok":true,"issues":[]}'))
        service = LLMService(transport=httpx.MockTransport(handle))
        self.assertEqual(await service.generate_json('Sei un revisore.'), {"ok": True, "issues": []})
        files = list(Path(self.temp.name).glob('*.json'))
        self.assertEqual(len(files), 1)
        self.assertIn('response', json.loads(files[0].read_text()))

    async def test_one_repair_only(self):
        calls = []
        def handle(request):
            calls.append(request)
            return httpx.Response(200, text=response_event('{"ok":true "issues":[]}'))
        service = LLMService(transport=httpx.MockTransport(handle))
        with self.assertRaises(ValueError):
            await service.generate_json('Sei un revisore.')
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(list(Path(self.temp.name).glob('*.json'))), 2)

    async def test_no_silent_fallback(self):
        calls = []
        def handle(request):
            calls.append(request)
            return httpx.Response(400, text='schema unsupported')
        with self.assertRaisesRegex(RuntimeError, 'HTTP 400'):
            await LLMService(transport=httpx.MockTransport(handle)).generate_json('Sei un revisore.')
        self.assertEqual(len(calls), 1)

    async def test_truncation_rejected(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, text=response_event('{"ok":', 'length')))
        with self.assertRaisesRegex(RuntimeError, 'Limite token'):
            await LLMService(transport=transport).generate_json('Sei un revisore.')


if __name__ == '__main__':
    unittest.main()
