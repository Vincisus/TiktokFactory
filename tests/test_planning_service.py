import asyncio
import copy
import tempfile
import unittest
from pathlib import Path
from app.core.planning_service import PlanningService


class FakeLLM:
    def __init__(self, values):
        self.values = iter(values)
        self.prompts = []

    async def generate_json(self, prompt):
        self.prompts.append(prompt)
        return copy.deepcopy(next(self.values))


GOOD = {"ok": True, "issues": []}
BAD = {"ok": False, "issues": ["Correggi la cronologia."]}


class PlanningTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_pass_saved(self):
        llm = FakeLLM([{"version": 1}, GOOD])
        with tempfile.TemporaryDirectory() as temp:
            value = await PlanningService(llm).refine(Path(temp), "concept", "Crea una storia", lambda x: None, {})
            self.assertEqual(value["version"], 1)
            self.assertTrue((Path(temp)/"concept_approved.json").exists())

    async def test_repair_then_approve(self):
        llm = FakeLLM([{"version": 1}, BAD, {"version": 2}, GOOD])
        service = PlanningService(llm)
        messages = []
        service.on_progress = messages.append
        with tempfile.TemporaryDirectory() as temp:
            value = await service.refine(Path(temp), "structure", "Pianifica 4 parti", lambda x: None, {})
            self.assertEqual(value["version"], 2)
            self.assertIn("Correggi la cronologia.", llm.prompts[2])
            self.assertTrue(llm.prompts[2].startswith("Pianifica 4"))
            self.assertIn("Correzione structure 1/2", messages)

    async def test_stops_after_two_repairs(self):
        llm = FakeLLM([{}, BAD, {}, BAD, {}, BAD])
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "dopo due correzioni"):
                await PlanningService(llm).refine(Path(temp), "concept", "Crea una storia", lambda x: None, {})
            self.assertEqual(len(llm.prompts), 6)
            self.assertEqual(len(list(Path(temp).glob('*_draft.json'))), 3)
            self.assertFalse((Path(temp)/"concept_approved.json").exists())

    async def test_structural_error_can_be_repaired(self):
        llm = FakeLLM([{"parts": []}, {"parts": [{"part": 1, "title": "T", "summary": "S", "cliffhanger": "C"}]}, GOOD])
        with tempfile.TemporaryDirectory() as temp:
            result = await PlanningService(llm).refine(Path(temp), "structure", "Pianifica 1 parti", lambda x: PlanningService.check_structure(x,1), {})
            self.assertEqual(len(result["parts"]), 1)
            self.assertEqual(len(llm.prompts), 3)

    async def test_contradictory_verdict_rejected(self):
        with self.assertRaises(ValueError):
            await PlanningService(FakeLLM([{"ok": True, "issues": ["errore"]}])).review({}, {}, "test")

    async def test_format_and_beliefs_in_prompt(self):
        service = PlanningService(FakeLLM([]))
        captured = []
        async def capture(folder, stage, prompt, validator, context):
            captured.append(prompt)
            return {}
        service.refine = capture
        with tempfile.TemporaryDirectory() as temp:
            await service.generate_concept({"series": "famiglia", "request": {}}, temp)
        self.assertTrue(captured[0].startswith("Crea una storia originale di fiction"))
        self.assertIn("cosa crede il protagonista", captured[0])

    async def test_reviewer_distinguishes_beliefs(self):
        llm = FakeLLM([GOOD])
        await PlanningService(llm).review({}, {}, "concept")
        self.assertIn("NON e una contraddizione", llm.prompts[0])


if __name__ == '__main__':
    unittest.main()
