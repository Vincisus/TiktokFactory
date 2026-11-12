import hashlib
import json
import logging
import re
from pathlib import Path
from app.core.planning_service import PlanningService

logger = logging.getLogger("uvicorn.error")
POLICY = "scene-repair-v2"


def word_count(text):
    return len(re.findall(r"\b[\wÀ-ÿ]+(?:[’'-][\wÀ-ÿ]+)*\b", text))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def validate_parts(value, expected):
    parts = value.get("parts")
    if not isinstance(parts, list) or len(parts) != expected:
        raise ValueError(f"Struttura: richieste {expected} parti.")
    for i, part in enumerate(parts, 1):
        if not isinstance(part, dict) or type(part.get("part")) is not int or part["part"] != i:
            raise ValueError("Numerazione delle parti non valida.")
        if any(not isinstance(part.get(k), str) or not part[k].strip() for k in ("title", "summary", "cliffhanger")):
            raise ValueError(f"Parte {i} incompleta.")
    return parts


def validate_card(card, known_ids, number):
    if type(card.get("scene_id")) is not int or card["scene_id"] != number:
        raise ValueError("Identificatore scena non valido.")
    if card.get("pov_id") not in known_ids:
        raise ValueError("Punto di vista sconosciuto.")
    if not isinstance(card.get("location"), str) or not card["location"].strip():
        raise ValueError("Luogo della scena mancante.")
    for key in ("facts", "knowledge_before", "knowledge_after"):
        items = card.get(key)
        if not isinstance(items, list) or not items or not all(isinstance(x, str) and x.strip() for x in items):
            raise ValueError(f"Scena {number}: {key} non valido.")
    present = card.get("characters_present")
    if not isinstance(present, list) or not present or any(x not in known_ids for x in present):
        raise ValueError("Personaggi presenti non validi.")
    if card["pov_id"] not in present:
        raise ValueError("Il narratore deve essere presente nella scena.")
    if not isinstance(card.get("withhold"), list) or not all(isinstance(x, str) for x in card["withhold"]):
        raise ValueError("Campo withhold non valido.")
    if not isinstance(card.get("visual"), str) or not card["visual"].strip():
        raise ValueError("Descrizione visiva mancante.")
    return card


class StoryBrain:
    def __init__(self, llm):
        self.llm = llm
        self.on_progress = None

    def notify(self, text):
        logger.info(text)
        if self.on_progress:
            self.on_progress(text)

    @staticmethod
    def save(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else value
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def folder(brief):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", brief["id"]):
            raise ValueError("ID progetto non valido.")
        return Path("projects") / brief["id"]

    async def generate_concept(self, brief):
        return await PlanningService(self.llm).generate_concept(brief, self.folder(brief))

    async def generate_structure(self, concept, brief):
        return await PlanningService(self.llm).generate_structure(concept, brief, self.folder(brief))

    async def review(self, data, kind):
        planner = PlanningService(self.llm)
        planner.on_progress = self.on_progress
        return await planner.review(data, {"rules": "characters_present contiene solo persone fisicamente presenti. Persone citate, autori di messaggi e interlocutori remoti non devono essere aggiunti se assenti. Nei facts ogni comunicazione decisiva deve rendere ricostruibili mittente, destinatario e contenuto. Non inventare presenze per risolvere un rilievo. knowledge_before precede i fatti; knowledge_after puo derivare dai fatti correnti. withhold non vieta al narratore di esprimere pensieri gia acquisiti. Non rifiutare una semplice menzione di un personaggio assente."}, kind)

    async def prepare_card(self, folder, number, part, beat, ids, concept, structure, state):
        base = (
            f"Genera la scheda della scena {number}, segmento {beat}/3 della parte {part['part']}. "
            f"Concept: {json.dumps(concept, ensure_ascii=False)}. Piano: {json.dumps(structure, ensure_ascii=False)}. "
            f"Fatti precedenti: {json.dumps(state, ensure_ascii=False)}. "
            "Una sola azione centrale con passaggi necessari espliciti. Non ripetere eventi conclusi. "
            "Solo il segmento 3 conclude la parte. Ultima scena: risoluzione. "
            "characters_present indica SOLO persone fisicamente presenti, non persone citate o remote. "
            "Nei facts specifica per messaggi e telefonate decisivi CHI comunica, A CHI, e COSA. "
            "Un autore assente puo essere nominato nei facts senza entrare in characters_present. "
            "Non inventare persone presenti. Mantieni convinzioni distinte dai fatti. "
            f"JSON: scene_id={number}, part={part['part']}, pov_id tra {ids}, location, "
            "characters_present (ID), facts, knowledge_before, knowledge_after, withhold (liste di stringhe), visual. "
            "Massimo 5 elementi per lista, 30 parole per elemento."
        )
        prompt = base
        issues = []
        for attempt in range(3):
            self.notify(f"Scena {number}: scheda e revisione, tentativo {attempt + 1}/3")
            card = await self.llm.generate_json(prompt)
            self.save(folder / "scenes" / f"{number:03}_card_draft_{attempt + 1}.json", card)
            try:
                validate_card(card, ids, number)
                if card.get("part") != part["part"]:
                    raise ValueError("Parte della scena errata.")
            except ValueError as exc:
                report = {"ok": False, "issues": [str(exc)]}
            else:
                report = await self.review({"concept": concept, "structure": structure, "previous_facts": state, "card": card}, "scheda scena")
            self.save(folder / "scenes" / f"{number:03}_card_review_{attempt + 1}.json", report)
            issues = report["issues"]
            if report["ok"]:
                self.save(folder / "scenes" / f"{number:03}_card.json", card)
                self.save(folder / "scenes" / f"{number:03}_card_review.json", report)
                return card
            prompt = base + "\nRicostruisci coerentemente la scheda correggendo solo i problemi reali. Non aggiungere una presenza fisica se la persona e solo menzionata. Aggiorna tutte le conseguenze dei fatti modificati. " + f"Bozza: {json.dumps(card, ensure_ascii=False)}. Problemi: {json.dumps(issues, ensure_ascii=False)}"
        raise ValueError(f"Scena {number}: scheda rifiutata dopo due correzioni: " + "; ".join(issues))

    async def generate_script(self, concept, structure, brief):
        folder = self.folder(brief)
        folder.mkdir(parents=True, exist_ok=True)
        parts = validate_parts(structure, int(brief["tiktok_clips"]))
        ids = [c["id"] for c in concept["characters"]]
        plan_hash = digest({"concept": concept, "structure": structure, "duration": brief["duration_minutes"], "policy": POLICY})
        state, approved, cards = [], [], []
        target = max(100, round(brief["duration_minutes"] * 60 / (len(parts) * 3) * 2.5))
        minimum, maximum = int(target * .75), int(target * 1.3)
        legacy_plan_matches = False
        try:
            legacy_plan_matches = json.loads((folder / "concept.json").read_text(encoding="utf-8")) == concept and json.loads((folder / "structure.json").read_text(encoding="utf-8")) == structure
        except (OSError, ValueError):
            pass
        number = 0
        for part in parts:
            for beat in range(1, 4):
                number += 1
                prefix = folder / "scenes" / f"{number:03}"
                card_path = prefix.with_name(prefix.name + "_card.json")
                text_path = prefix.with_name(prefix.name + "_approved.txt")
                checkpoint = prefix.with_name(prefix.name + "_checkpoint_v2.json")
                context_hash = digest({"plan": plan_hash, "previous": state, "scene": number})
                card, text, reused = None, "", False
                if card_path.is_file() and text_path.is_file():
                    try:
                        candidate = json.loads(card_path.read_text(encoding="utf-8"))
                        candidate_text = text_path.read_text(encoding="utf-8")
                        validate_card(candidate, ids, number)
                        if candidate.get("part") != part["part"] or not minimum <= word_count(candidate_text) <= maximum:
                            raise ValueError("Checkpoint incompatibile con parte o lunghezza.")
                        binding = {"context": context_hash, "card": digest(candidate), "text": hashlib.sha256(candidate_text.encode()).hexdigest()}
                        if checkpoint.is_file():
                            reused = json.loads(checkpoint.read_text(encoding="utf-8")) == binding
                        elif legacy_plan_matches:
                            self.notify(f"Scena {number}: verifica checkpoint precedente prima del riutilizzo")
                            card_report = await self.review({"concept": concept, "structure": structure, "previous_facts": state, "card": candidate}, "checkpoint scheda scena")
                            text_report = await self.review({"characters": concept["characters"], "card": candidate, "previous_facts": state, "text": candidate_text}, "checkpoint narrazione")
                            self.save(prefix.with_name(prefix.name + "_migration_review.json"), {"card": card_report, "text": text_report})
                            reused = card_report["ok"] and text_report["ok"]
                        if reused:
                            card, text = candidate, candidate_text
                            self.notify(f"Scena {number}: checkpoint verificato, nessuna riscrittura")
                    except (OSError, ValueError) as exc:
                        self.notify(f"Scena {number}: checkpoint non riutilizzabile: {exc}")
                if not reused:
                    card = await self.prepare_card(folder, number, part, beat, ids, concept, structure, state)
                    errors = []
                    for attempt in range(3):
                        self.notify(f"Scena {number}/{len(parts)*3}: scrittura e revisione, tentativo {attempt+1}/3")
                        prompt = (
                            f"Scrivi solo narrazione italiana in prima persona, {minimum}-{maximum} parole, obiettivo {target}. "
                            "Rispetta esattamente la scheda e non anticipare withhold. Nessun titolo o commento. "
                            "Non riassumere scene precedenti. Dialoghi naturali. Persone solo menzionate non sono presenti. "
                            f"Personaggi: {json.dumps(concept['characters'], ensure_ascii=False)}. Scheda: {json.dumps(card, ensure_ascii=False)}. "
                            f"Fine scena precedente: {approved[-1][-1000:] if approved else 'Inizio storia'}."
                        )
                        if attempt:
                            prompt += f" Riscrivi la bozza correggendo questi problemi: {json.dumps(errors, ensure_ascii=False)}. Bozza: {text}"
                        text = (await self.llm.generate_text(prompt)).strip()
                        self.save(prefix.with_name(prefix.name + f"_draft_{attempt+1}.txt"), text)
                        count = word_count(text)
                        errors = [] if minimum <= count <= maximum else [f"Lunghezza {count}: richieste {minimum}-{maximum} parole."]
                        report = await self.review({"characters": concept["characters"], "card": card, "previous_facts": state, "text": text}, "racconto della scena rispetto ai fatti vincolanti")
                        errors.extend(report["issues"])
                        self.save(prefix.with_name(prefix.name + f"_review_{attempt+1}.json"), {"word_count": count, "issues": errors, "ok": not errors})
                        if not errors:
                            break
                    else:
                        raise ValueError(f"Scena {number} non approvata dopo due correzioni: " + "; ".join(errors))
                self.save(text_path, text)
                self.save(checkpoint, {"context": context_hash, "card": digest(card), "text": hashlib.sha256(text.encode()).hexdigest()})
                approved.append(text)
                cards.append(card)
                state.append({"scene_id": number, "facts": card["facts"], "knowledge_after": card["knowledge_after"]})
                self.save(folder / "story_state.json", state)
                self.save(folder / "scene_cards.json", cards)
                self.save(folder / "script_partial.md", "\n\n".join(approved))
        script = "\n\n".join(approved)
        report = await self.review({"plan": structure, "facts": state}, "continuita complessiva e risoluzione")
        self.save(folder / "continuity_report.json", report)
        if not report["ok"]:
            raise ValueError("Continuita complessiva rifiutata: " + "; ".join(report["issues"]))
        self.save(folder / "narrative_manifest.json", {"script_sha256": hashlib.sha256(script.encode()).hexdigest(), "scene_count": len(cards), "policy": POLICY, "note": "Revisione dello stesso LLM, non garanzia di qualita; durate stimate."})
        return script

    async def generate_storyboard(self, script, structure, brief):
        folder = self.folder(brief)
        cards = json.loads((folder / "scene_cards.json").read_text(encoding="utf-8"))
        texts = [(folder / "scenes" / f"{c['scene_id']:03}_approved.txt").read_text(encoding="utf-8") for c in cards]
        total = sum(word_count(t) for t in texts)
        if not total:
            raise ValueError("Narrazione vuota.")
        duration = brief["duration_minutes"] * 60
        scenes, current = [], 0.0
        for card, text in zip(cards, texts):
            end = current + duration * word_count(text) / total
            scenes.append({"scene_id": card["scene_id"], "part": card["part"], "start": current, "end": end, "narration": text, "visual": card.get("visual", card["location"]), "camera": "slow_zoom", "on_screen_text": "", "sound": "", "emotion": "", "image_prompt": "", "timing_source": "estimated_word_count"})
            current = end
        scenes[-1]["end"] = duration
        return {"scenes": scenes, "timing_source": "estimated_word_count", "note": "Nessuna immagine generata da questo modulo. Allineamento audio reale non implementato."}
