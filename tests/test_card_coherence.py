import copy
import json
import tempfile
import unittest
from pathlib import Path
from app.core.card_coherence import CardCoherenceMixin, check_support
from app.core.story_brain import StoryBrain


def packet():
    card = {"scene_id": 1, "part": 1, "pov_id": "c1", "location": "Sala riunioni", "characters_present": ["c1", "c2"], "facts": ["Marta presenta la relazione e cita lo studio di Marco.", "Marco legge il documento e nota che non chiarisce il suo contributo iniziale."], "knowledge_before": ["Marco sa che Marta deve presentare la relazione."], "knowledge_after": ["Marco ha letto la relazione e sospetta che il suo contributo sia stato ridimensionato."], "withhold": ["Marco non comunica ancora a Marta il proprio sospetto."], "visual": "Sala riunioni"}
    return {"card": card, "support": [{"field": field, "index": 0, "sources": [{"field": "facts", "index": 1}]} for field in ("knowledge_after", "withhold")]}


class Brain(CardCoherenceMixin, StoryBrain):
    pass


class FakeLLM:
    def __init__(self, packets, verdicts):
        self.packets = iter(packets)
        self.verdicts = iter(verdicts)
        self.prompts = []
        self.calls = 0
    async def _request(self, prompt, temperature, schema):
        self.prompts.append(prompt)
        self.calls += 1
        return json.dumps(next(self.packets), ensure_ascii=False)
    @staticmethod
    def _extract_json(raw): return json.loads(raw)
    async def generate_json(self, prompt):
        self.prompts.append(prompt)
        return copy.deepcopy(next(self.verdicts))


class CoherenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_removed_reading_reference_rejected(self):
        value = packet()
        value["card"]["facts"].pop()
        with self.assertRaisesRegex(ValueError, "inesistente"):
            check_support(value, [])

    async def test_all_claims_need_support(self):
        value = packet()
        value["card"]["withhold"].append("Marco sta raccogliendo prove.")
        with self.assertRaisesRegex(ValueError, "Ogni conoscenza"):
            check_support(value, [])

    async def test_duplicate_support_rejected(self):
        value = packet()
        value["support"].append(copy.deepcopy(value["support"][0]))
        with self.assertRaises(ValueError): check_support(value, [])

    async def test_unknown_source_rejected(self):
        value = packet()
        value["support"][0]["sources"][0]["field"] = "future_events"
        with self.assertRaises(ValueError): check_support(value, [])

    async def test_reading_event_and_claim_have_valid_references(self):
        self.assertEqual(check_support(packet(), [])["scene_id"], 1)

    async def test_full_repair_updates_dependent_fields(self):
        first = packet()
        first["card"]["knowledge_after"][0] = "Marco ha raccolto prove definitive."
        fixed = packet()
        llm = FakeLLM([first, fixed], [{"ok": False, "issues": ["knowledge_after: prove definitive non sostenute dai fatti."]}, {"ok": True, "issues": []}])
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            brain = Brain(llm)
            brain.save(folder / "scenes/001_card.json", first["card"])
            result = await brain.prepare_recovery_card(folder, 1, 1, 1, ["c1", "c2"], {}, {}, [])
            self.assertEqual(result, fixed["card"])
            self.assertEqual(json.loads((folder / "scenes/001_card.json").read_text()), fixed["card"])
            self.assertEqual(len(list((folder / "scenes").glob('*_previous.json'))), 1)
            self.assertIn("TUTTE", llm.prompts[0])
            self.assertTrue(any("prove definitive non sostenute" in p for p in llm.prompts))

    async def test_stops_after_two_repairs_without_overwriting_card(self):
        bad = {"ok": False, "issues": ["knowledge_after: contraddizione non risolta."]}
        llm = FakeLLM([packet(), packet(), packet()], [bad, bad, bad])
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            brain = Brain(llm)
            old = packet()["card"]
            old["location"] = "Versione precedente"
            brain.save(folder / "scenes/001_card.json", old)
            with self.assertRaisesRegex(ValueError, "dopo due correzioni"):
                await brain.prepare_recovery_card(folder, 1, 1, 1, ["c1", "c2"], {}, {}, [])
            self.assertEqual(llm.calls, 3)
            self.assertEqual(json.loads((folder / "scenes/001_card.json").read_text()), old)

    async def test_reviewer_distinguishes_presentation_and_reading(self):
        llm = FakeLLM([], [{"ok": True, "issues": []}])
        await Brain(llm).review({}, "scena")
        self.assertIn("Ascoltare una presentazione non richiede", llm.prompts[0])
        self.assertIn("non prova la coerenza semantica", llm.prompts[0])


    async def test_install_preserves_recovery_script(self):
        from unittest.mock import patch
        from app.core.card_coherence import install
        class Existing:
            def prepare_recovery_card(self): pass
            def generate_script(self): pass
        original = Existing.generate_script
        with patch("app.core.story_brain.StoryBrain", Existing):
            self.assertTrue(install())
            self.assertTrue(install())
        self.assertIs(Existing.generate_script, original)
        self.assertIs(Existing.prepare_recovery_card, CardCoherenceMixin.prepare_recovery_card)

    async def test_install_does_not_pretend_recovery_is_present(self):
        from unittest.mock import patch
        from app.core.card_coherence import install
        class Unpatched: pass
        with patch("app.core.story_brain.StoryBrain", Unpatched):
            self.assertFalse(install())
        self.assertFalse(hasattr(Unpatched, "prepare_recovery_card"))


if __name__ == "__main__": unittest.main()
