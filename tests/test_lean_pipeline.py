import asyncio
import json
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx
from app.core import lean_pipeline as l


class LeanTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / "story"
        self.folder.mkdir()
        self.root_patch = patch.object(l.store, "ROOT", self.root)
        self.root_patch.start()
        for name, value in {"brief.json": {"id": "story", "duration_minutes": 1, "tiktok_clips": 1}, "concept.json": {"title": "Storia", "characters": [{"id": "c1", "name": "Marco"}]}, "structure.json": {"parts": [{"part": 1, "title": "T", "summary": "S", "cliffhanger": "C"}]}}.items():
            l.store.save(self.folder / name, value)

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    def config(self, mode="ok"):
        calls = []
        def handle(request):
            payload = json.loads(request.content)
            calls.append(payload)
            props = payload["response_format"]["json_schema"]["schema"]["properties"]
            if "narration" in props:
                n = int(re.search(r"scena (\d+),", payload["messages"][1]["content"]).group(1))
                value = {"scene_id": n, "part": 1, "pov_id": "c1", "location": "Stanza", "narration": "parola " * (10 if mode == "short" else 120), "facts": [f"Evento {n}"], "knowledge_after": [f"Conoscenza {n}"], "visual": "Interno"}
            else:
                value = {"ok": mode != "reject", "issues": ["Contraddizione simulata"] if mode == "reject" else []}
                if "titles" in props: value["titles"] = [f"Titolo {i}" for i in range(5)]
            return httpx.Response(200, json={"choices": [{"finish_reason": "length" if mode == "length" else "stop", "message": {"content": json.dumps(value)}}]})
        config = SimpleNamespace(base_url="http://127.0.0.1:1234/v1", api_key="test", transport=httpx.MockTransport(handle), _clean_text=lambda text: text.strip(), _extract_json=json.loads)
        return config, calls

    async def execute(self, config, mode="probe"):
        job = {"id": __import__("uuid").uuid4().hex, "model": "lfm-test", "mode": mode, "status": "queued", "calls": [], "logs": [], "result": None, "error": None}
        lock = self.folder / ".scene_recovery.lock"
        lock.write_text("test")
        await l.run(self.folder, job, lock, config)
        return job

    async def test_probe_uses_exactly_two_calls(self):
        config, calls = self.config()
        job = await self.execute(config)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(len(calls), 2)
        self.assertFalse(calls[0]["stream"])
        self.assertEqual(calls[0]["model"], "lfm-test")
        self.assertEqual([x["max_tokens"] for x in calls], [2048, 768])
        self.assertTrue((self.folder / "lean/latest_probe.json").exists())
        self.assertFalse((self.folder / "script.md").exists())
        self.assertFalse((self.folder / ".scene_recovery.lock").exists())

    async def test_short_draft_stops_after_one_call(self):
        config, calls = self.config("short")
        job = await self.execute(config)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(len(calls), 1)

    async def test_rejected_scene_is_not_rewritten(self):
        config, calls = self.config("reject")
        job = await self.execute(config)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(len(calls), 2)
        self.assertFalse(l.store.load(self.folder / "lean/latest_probe.json")["approved"])

    async def test_truncated_response_not_retried(self):
        config, calls = self.config("length")
        job = await self.execute(config)
        self.assertEqual(job["status"], "failed")
        self.assertEqual(len(calls), 1)

    async def test_continue_reuses_probe_and_completed_scenes(self):
        config, calls = self.config()
        await self.execute(config)
        job = await self.execute(config, "resume")
        self.assertEqual(job["status"], "completed")
        self.assertEqual(len(job["calls"]), 5)
        self.assertEqual(len(calls), 7)
        self.assertTrue((self.folder / "lean/script.md").exists())
        self.assertTrue((self.folder / "lean/storyboard.json").exists())
        again = await self.execute(config, "resume")
        self.assertEqual(again["status"], "completed")
        self.assertEqual(len(again["calls"]), 1)

    async def test_continue_requires_successful_probe(self):
        config, calls = self.config()
        job = await self.execute(config, "resume")
        self.assertEqual(job["status"], "failed")
        self.assertEqual(len(calls), 0)

    async def test_altered_checkpoint_is_not_reused(self):
        config, calls = self.config()
        await self.execute(config)
        path = self.folder / "lean/latest_probe.json"
        saved = l.store.load(path)
        saved["scene"]["narration"] += "alterato"
        l.store.save(path, saved)
        job = await self.execute(config, "resume")
        self.assertEqual(job["status"], "failed")
        self.assertEqual(len(job["calls"]), 0)

    async def test_jobs_read_back_after_restart(self):
        config, calls = self.config()
        job = await self.execute(config)
        read = await l.job_status(job["id"])
        self.assertEqual(read["status"], "completed")
        self.assertEqual(len(read["calls"]), 2)


if __name__ == "__main__": unittest.main()
