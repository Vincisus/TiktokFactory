import json
import re
from copy import deepcopy

VERSION = "marta-v1"


def selected_contract(client, structure, number, part, beat, digest):
    folder = client.folder.parent.parent
    path = folder / "scene_contract.json"
    if not path.is_file() or path.resolve().parent != folder.resolve():
        raise ValueError("Contratto delle scene mancante o fuori dal progetto")
    contracts = json.loads(path.read_text(encoding="utf-8"))
    if contracts.get("version") != VERSION or digest(contracts) != structure.get("scene_contract_sha256"):
        raise ValueError("Contratto delle scene alterato o incompatibile con il piano")
    entries = contracts.get("scenes", [])
    if len(entries) != 12 or {s.get("scene_id") for s in entries} != set(range(1, 13)):
        raise ValueError("Il piano corretto deve avere dodici scene univoche")
    entry = next(s for s in entries if s["scene_id"] == number)
    if entry["part"] != part["part"] or entry["beat"] != beat:
        raise ValueError("Scena non corrispondente alla parte o al segmento")
    return contracts, entry


class GuardedClient:
    def __init__(self, client, entry, schema):
        self.client, self.entry, self.schema = client, entry, schema

    def __getattr__(self, name):
        return getattr(self.client, name)

    async def ask(self, prompt, schema, max_tokens, label):
        value = await self.client.ask(prompt, schema, max_tokens, label)
        if schema is self.schema:
            if value.get("pov_id") != self.entry["pov_id"]:
                raise ValueError("Il narratore non corrisponde al contratto della scena")
            text = json.dumps({k: value.get(k) for k in ("narration", "facts", "knowledge_after")}, ensure_ascii=False).casefold()
            for term in self.entry.get("forbidden_terms", []):
                if re.search(r"\b" + re.escape(term.casefold()) + r"\b", text):
                    raise ValueError(f"Anticipazione vietata nella scena {self.entry['scene_id']}: {term}. Nessun rifacimento automatico.")
        return value


def install():
    from app.core import lean_pipeline as lean
    if getattr(lean.one_scene, "uses_scene_contract", False):
        return
    original = lean.one_scene

    async def one_scene(client, concept, structure, state, number, part, beat, ids, bounds):
        if structure.get("contract_version") != VERSION:
            return await original(client, concept, structure, state, number, part, beat, ids, bounds)
        contracts, entry = selected_contract(client, structure, number, part, beat, lean.digest)
        characters = deepcopy(concept["characters"])
        for character in characters:
            character["role"] = entry["roles"][character["id"]]
        public_concept = {"setting": concept["setting"], "characters": characters, "premise": contracts["premise"]}
        current_part = {"part": part["part"], "title": part["title"], "summary": entry["goal"], "cliffhanger": part["cliffhanger"] if beat == 3 else "Non concludere ancora la parte.", "scene_rules": {"pov_id": entry["pov_id"], "knowledge_before": entry["knowledge_before"], "forbidden_terms": entry["forbidden_terms"]}}
        client.update(f"Scena {number}: contratto attivo; nessuna logline o risoluzione futura nel prompt")
        guarded = GuardedClient(client, entry, lean.SCENE)
        return await original(guarded, public_concept, structure, state, number, current_part, beat, ids, bounds)

    one_scene.uses_scene_contract = True
    lean.one_scene = one_scene
