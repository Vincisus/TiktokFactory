import copy
import json
import unittest
from app.core.scene_contract import public_context, contains_term, GuardedClient


def fixtures():
    concept = {"setting": "Clinica", "characters": [{"id": "c1", "role": "Autore"}, {"id": "c2", "role": "Coordinatrice"}, {"id": "c3", "role": "Direttrice"}]}
    contracts = {"premise": "Marco e autore, Marta coordina e Sanna decide.", "invariants": {"decision_authority_id": "c3"}}
    entry = {"scene_id": 1, "pov_id": "c1", "goal": "Sanna apre la riunione.", "knowledge_before": "Marta deve presentare la proposta.", "roles": {"c1": "Ricercatore autore dello studio.", "c2": "Coordinatrice della proposta.", "c3": "Direttrice, unica autorita su sospensione e reintegro."}, "forbidden_terms": ["quaderno", "taccuino", "reintegro", "reintegrata"]}
    part = {"part": 1, "title": "Il sospetto", "cliffhanger": "Sanna richiede una verifica."}
    return concept, contracts, entry, part


class PromptIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_control_terms_are_not_in_public_context(self):
        concept, contracts, entry, part = fixtures()
        public, current = public_context(concept, contracts, entry, part, 1, (112, 195))
        text = json.dumps([public, current], ensure_ascii=False)
        self.assertNotIn("forbidden_terms", text)
        self.assertFalse(contains_term(text, entry["forbidden_terms"]))

    async def test_authority_role_does_not_leak_future_topics(self):
        concept, contracts, entry, part = fixtures()
        old = copy.deepcopy(entry)
        public, current = public_context(concept, contracts, entry, part, 1, (112, 195))
        self.assertEqual(public["characters"][2]["role"], "Direttrice della clinica, responsabile delle decisioni organizzative.")
        self.assertEqual(entry, old)

    async def test_part_title_does_not_leak_notebook(self):
        concept, contracts, entry, part = fixtures()
        part.update(part=2, title="Il quaderno e la verifica")
        public, current = public_context(concept, contracts, entry, part, 1, (112, 195))
        self.assertEqual(current["title"], "Parte 2")

    async def test_negative_future_clause_is_not_sent_to_writer(self):
        concept, contracts, entry, part = fixtures()
        entry["goal"] = "Marco prepara la rettifica. Non la invia ancora e non riceve ancora un reintegro."
        public, current = public_context(concept, contracts, entry, part, 2, (112, 195))
        self.assertEqual(current["summary"], "Marco prepara la rettifica.")
        self.assertFalse(contains_term(json.dumps(current), ["reintegro"]))

    async def test_future_cliffhanger_is_not_sent_early(self):
        concept, contracts, entry, part = fixtures()
        part["cliffhanger"] = "Sanna decidera il reintegro."
        public, current = public_context(concept, contracts, entry, part, 3, (112, 195))
        self.assertNotIn("reintegro", current["cliffhanger"])

    async def test_generation_gets_word_target_not_control_vocabulary(self):
        concept, contracts, entry, part = fixtures()
        public, current = public_context(concept, contracts, entry, part, 1, (112, 195))
        class Client:
            prompts = []
            async def ask(self, prompt, *args):
                self.prompts.append(prompt)
                return {"pov_id": "c1", "narration": "Sanna apre la riunione.", "facts": [], "knowledge_after": []}
        client = Client()
        schema = {}
        await GuardedClient(client, entry, schema, (112, 195)).ask(json.dumps([public, current]), schema, 2048, "test")
        self.assertIn("circa 153 parole", client.prompts[0])
        self.assertFalse(contains_term(client.prompts[0], entry["forbidden_terms"]))
        self.assertEqual(len(client.prompts), 1)

    async def test_real_out_of_scope_mention_remains_blocked(self):
        class Client:
            async def ask(self, *args): return {"pov_id": "c1", "narration": "Marta e stata reintegrata.", "facts": [], "knowledge_after": []}
        schema = {}
        entry = fixtures()[2]
        with self.assertRaisesRegex(ValueError, "Anticipazione lessicale"):
            await GuardedClient(Client(), entry, schema).ask("prompt", schema, 2048, "label")

    async def test_review_request_is_not_rewritten(self):
        class Client:
            async def ask(self, prompt, *args):
                self.prompt = prompt
                return {"ok": True, "issues": []}
        client = Client()
        scene_schema, review_schema = {}, {}
        result = await GuardedClient(client, fixtures()[2], scene_schema, (112, 195)).ask("Review unchanged", review_schema, 768, "review")
        self.assertEqual(client.prompt, "Review unchanged")
        self.assertTrue(result["ok"])


if __name__ == "__main__": unittest.main()
