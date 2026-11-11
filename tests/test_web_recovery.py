import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import HTTPException
from app.core import project_console as c


class FakeBrain:
    prepare_recovery_card = True
    def __init__(self, llm): self.on_progress = None
    async def generate_script(self, concept, structure, brief):
        self.on_progress("Scena recuperata")
        return "Una storia di prova."
    async def generate_storyboard(self, script, structure, brief): return {"scenes": []}


class FakeLLM:
    async def generate_json(self, prompt): return {"titles": [f"Titolo {i}" for i in range(5)]}


class WebRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.root_patch = patch.object(c, "ROOT", self.root)
        self.root_patch.start()
        self.jobs_patch = patch.object(c, "job_store", {})
        self.jobs_patch.start()
        self.folder = self.root / "test_1"
        self.folder.mkdir()
        for name, value in {"brief.json": {"id": "test_1"}, "concept.json": {"title": "Storia"}, "structure.json": {"parts": []}}.items():
            c.save(self.folder / name, value)
        self.request = SimpleNamespace(headers={}, base_url="http://test/")

    def tearDown(self):
        self.jobs_patch.stop()
        self.root_patch.stop()
        self.temp.cleanup()

    async def test_list_saved_projects(self):
        data = await c.projects()
        self.assertTrue(data["projects"][0]["ready"])
        self.assertFalse(data["busy"])

    async def test_resume_writes_results_and_releases_lock(self):
        with patch("app.core.story_brain.StoryBrain", FakeBrain), patch("app.services.llm_service.LLMService", FakeLLM):
            response = await c.resume_project("test_1", self.request)
            self.assertIn("job_id", response)
            await asyncio.gather(*list(c.TASKS))
        status = c.load(self.folder / "resume_job.json")
        self.assertEqual(status["status"], "completed")
        self.assertEqual(len(status["result"]["title_options"]), 5)
        self.assertFalse((self.folder / ".scene_recovery.lock").exists())
        self.assertTrue((self.folder / "script.md").exists())

    async def test_existing_lock_blocks_resume(self):
        (self.folder / ".scene_recovery.lock").write_text("terminal")
        with self.assertRaises(HTTPException) as caught:
            await c.resume_project("test_1", self.request)
        self.assertEqual(caught.exception.status_code, 409)

    async def test_active_generation_blocks_resume(self):
        c.job_store["other"] = {"status": "running"}
        with self.assertRaises(HTTPException) as caught:
            await c.resume_project("test_1", self.request)
        self.assertEqual(caught.exception.status_code, 409)

    async def test_cross_origin_post_rejected(self):
        self.request.headers = {"origin": "https://other.example"}
        with self.assertRaises(HTTPException) as caught:
            await c.resume_project("test_1", self.request)
        self.assertEqual(caught.exception.status_code, 403)

    async def test_download_allowlist_and_path_validation(self):
        with self.assertRaises(HTTPException):
            await c.project_file("test_1", "brief.json")
        with self.assertRaises(HTTPException):
            c.project("../test_1")

    async def test_interrupted_job_visible_after_restart(self):
        c.save(self.folder / "resume_job.json", {"id": "old", "status": "running"})
        self.assertEqual(c.summary(self.folder)["status"], "interrupted")

    async def test_titles_have_fallback_on_model_failure(self):
        class Broken:
            async def generate_json(self, prompt): raise ValueError("model unavailable")
        result = await c.make_titles(Broken(), self.folder, {"title": "Storia"}, {})
        self.assertEqual(len(result["titles"]), 5)
        self.assertEqual(result["source"], "template_fallback")


if __name__ == "__main__": unittest.main()
