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


def contains_term(text, terms):
    folded = text.casefold()
    return any(re.search(r"\b" + re.escape(term.casefold()) + r"\b", folded) for term in terms)


def public_context(concept, contracts, entry, part, beat, bounds):
    terms = entry.get("forbidden_terms", [])
    def visible_sentences(text):
        return " ".join(s for s in re.split(r"(?<=[.!?])\s+", text) if not contains_term(s, terms))
    characters = deepcopy(concept["characters"])
    authority = contracts.get("invariants", {}).get("decision_authority_id", "c3")
    for character in characters:
        role = entry["roles"][character["id"]]
        if character["id"] == authority:
            role = "Direttrice della clinica, responsabile delle decisioni organizzative."
        role = visible_sentences(role)
        if not role:
            raise ValueError("Ruolo corrente privo di una descrizione utilizzabile")
        character["role"] = role
    goal = visible_sentences(entry["goal"])
    if not goal:
        raise ValueError("Obiettivo della scena contiene soltanto riferimenti fuori perimetro")
    title = part["title"] if not contains_term(part["title"], terms) else f"Parte {part['part']}"
    ending = part["cliffhanger"] if beat == 3 else "Non concludere ancora la parte."
    if contains_term(ending, terms):
        ending = "La conseguenza della scelta resta da affrontare."
    public = {"setting": concept["setting"], "characters": characters, "premise": visible_sentences(contracts["premise"])}
    current = {"part": part["part"], "title": title, "summary": goal, "cliffhanger": ending, "scene_rules": {"pov_id": entry["pov_id"], "knowledge_before": visible_sentences(entry["knowledge_before"]), "word_range": list(bounds), "target_words": sum(bounds)//2, "scope": "Racconta solo l'obiettivo corrente. Non aggiungere eventi di altre scene e non commentare i vincoli di scrittura."}}
    if contains_term(json.dumps([public, current], ensure_ascii=False), terms):
        raise ValueError("Informazioni riservate ai controlli ancora presenti nel prompt: generazione non avviata")
    return public, current


class GuardedClient:
    def __init__(self, client, entry, schema, bounds=None):
        self.client, self.entry, self.schema, self.bounds = client, entry, schema, bounds

    def __getattr__(self, name):
        return getattr(self.client, name)

    async def ask(self, prompt, schema, max_tokens, label):
        if schema is self.schema:
            prompt += "\nRacconta solo l'obiettivo corrente, senza ipotizzare eventi non forniti e senza commentare le istruzioni."
            if self.bounds:
                prompt += f" Narrazione di circa {sum(self.bounds)//2} parole, obbligatoriamente tra {self.bounds[0]} e {self.bounds[1]}. Il conteggio riguarda solo narration, non i riepiloghi."
        value = await self.client.ask(prompt, schema, max_tokens, label)
        if schema is self.schema:
            if value.get("pov_id") != self.entry["pov_id"]:
                raise ValueError("Il narratore non corrisponde al contratto della scena")
            text = json.dumps({k: value.get(k) for k in ("narration", "facts", "knowledge_after")}, ensure_ascii=False)
            for term in self.entry.get("forbidden_terms", []):
                if contains_term(text, [term]):
                    raise ValueError(f"Anticipazione lessicale nella scena {self.entry['scene_id']}: {term}. Il filtro rileva una menzione, non prova da solo una contraddizione. Nessun rifacimento automatico.")
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
        public, current = public_context(concept, contracts, entry, part, beat, bounds)
        client.update(f"Scena {number}: contesto ripulito; lista dei filtri e finale non inviati allo scrittore")
        guarded = GuardedClient(client, entry, lean.SCENE, bounds)
        return await original(guarded, public, structure, state, number, current, beat, ids, bounds)

    one_scene.uses_scene_contract = True
    lean.one_scene = one_scene
