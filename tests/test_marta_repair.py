import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

import repair_marta_project as repair
from app.core import scene_contract as policy


class PlanTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / repair.SOURCE_ID
        self.source.mkdir()
        values = {"brief.json": {"id": repair.SOURCE_ID, "duration_minutes": 12, "tiktok_clips": 4}, "concept.json": {"title": "Il quaderno di Marta", "characters": [{"id": x} for x in ("c1", "c2", "c3")]}, "structure.json": {"parts": []}}
        for name, value in values.items():
            (self.source / name).write_text(json.dumps(value), encoding="utf-8")

    def tearDown(self): self.temp.cleanup()

    async def test_migration_preserves_original_and_does_not_copy_old_scenes(self):
        (self.source / "scenes").mkdir()
        (self.source / "scenes/001_approved.txt").write_text("Old text")
        before = (self.source / "concept.json").read_bytes()
        target = repair.migrate(self.root, check_server=False)
        self.assertEqual((self.source / "concept.json").read_bytes(), before)
        self.assertFalse((target / "scenes").exists())
        self.assertEqual(json.loads((target / "brief.json").read_text())["id"], repair.TARGET_ID)

    async def test_second_run_does_not_reset_new_work(self):
        target = repair.migrate(self.root, check_server=False)
        (target / "lean").mkdir()
        (target / "lean/keep.txt").write_text("keep")
        self.assertEqual(repair.migrate(self.root, check_server=False), target)
        self.assertEqual((target / "lean/keep.txt").read_text(), "keep")

    async def test_existing_different_target_is_not_overwritten(self):
        target = repair.migrate(self.root, check_server=False)
        (target / "concept.json").write_text('{}')
        with self.assertRaises(ValueError): repair.migrate(self.root, check_server=False)
        self.assertEqual((target / "concept.json").read_text(), '{}')

    async def test_lock_blocks_migration(self):
        (self.source / ".scene_recovery.lock").write_text("active")
        with self.assertRaises(ValueError): repair.migrate(self.root, check_server=False)
        self.assertFalse((self.root / repair.TARGET_ID).exists())

    async def test_twelve_scenes_and_fixed_authority(self):
        concept, structure, contract = repair.corrected_plan(12)
        self.assertEqual(len(contract["scenes"]), 12)
        self.assertEqual(structure["scene_contract_sha256"], repair.digest(contract))
        self.assertEqual(contract["invariants"], {"study_author_id": "c1", "initial_coordinator_id": "c2", "decision_authority_id": "c3"})
        self.assertIn("Sanna", concept["resolution"])
        self.assertEqual(sum(p["duration_seconds"] for p in structure["parts"]), 720)

    def contract_context(self):
        target = repair.migrate(self.root, check_server=False)
        concept = json.loads((target / "concept.json").read_text())
        structure = json.loads((target / "structure.json").read_text())
        client = SimpleNamespace(folder=target / "lean_runs" / "job", update=lambda text: None)
        return concept, structure, client

    async def test_contract_modification_is_rejected(self):
        concept, structure, client = self.contract_context()
        structure["scene_contract_sha256"] = "wrong"
        with self.assertRaises(ValueError):
            policy.selected_contract(client, structure, 1, structure["parts"][0], 1, repair.digest)

    async def test_first_scene_prompt_does_not_include_global_revelation(self):
        import app.core
        concept, structure, client = self.contract_context()
        captured = []
        async def original(*args):
            captured.append(args)
            return {"ok": True}
        lean = SimpleNamespace(one_scene=original, digest=repair.digest, SCENE={})
        with patch.object(app.core, "lean_pipeline", lean, create=True), patch.dict(sys.modules, {"app.core.lean_pipeline": lean}):
            policy.install()
            policy.install()
            await lean.one_scene(client, concept, structure, [], 1, structure["parts"][0], 1, ["c1", "c2", "c3"], (112, 195))
        public = captured[0][1]
        self.assertNotIn("resolution", public)
        self.assertNotIn("turning_point", public)
        self.assertNotIn("logline", public)
        self.assertIn("Sanna apre", captured[0][5]["summary"])
        self.assertEqual(captured[0][5]["scene_rules"]["pov_id"], "c1")

    async def test_early_notebook_stops_without_second_request(self):
        schema = {}
        class Client:
            calls = 0
            async def ask(self, *args):
                self.calls += 1
                return {"pov_id": "c1", "narration": "Trovo il quaderno.", "facts": [], "knowledge_after": []}
        client = Client()
        guarded = policy.GuardedClient(client, {"scene_id": 1, "pov_id": "c1", "forbidden_terms": ["quaderno"]}, schema)
        with self.assertRaisesRegex(ValueError, "Anticipazione"):
            await guarded.ask("prompt", schema, 2048, "label")
        self.assertEqual(client.calls, 1)

    async def test_other_projects_keep_original_behavior(self):
        import app.core
        captured = []
        async def original(*args):
            captured.append(args)
            return "original"
        lean = SimpleNamespace(one_scene=original)
        concept = {"title": "Other"}
        with patch.object(app.core, "lean_pipeline", lean, create=True), patch.dict(sys.modules, {"app.core.lean_pipeline": lean}):
            policy.install()
            result = await lean.one_scene(None, concept, {}, [], 1, {}, 1, [], (1, 2))
        self.assertEqual(result, "original")
        self.assertIs(captured[0][1], concept)

    async def test_wrong_narrator_is_rejected(self):
        schema = {}
        class Client:
            async def ask(self, *args): return {"pov_id": "c2", "narration": "Testo"}
        guarded = policy.GuardedClient(Client(), {"pov_id": "c1"}, schema)
        with self.assertRaisesRegex(ValueError, "narratore"):
            await guarded.ask("prompt", schema, 2048, "label")


if __name__ == "__main__": unittest.main()
