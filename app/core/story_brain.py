import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from pathlib import Path
from app.core.planning_service import PlanningService
from app.core.scene_policy import review_scene, writer_prompt

logger = logging.getLogger("uvicorn.error")
POLICY = "scene-evidence-v3"


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
    if not isinstance(card, dict) or type(card.get("scene_id")) is not int or card["scene_id"] != number:
        raise ValueError("Identificatore scena non valido.")
    if card.get("pov_id") not in known_ids:
        raise ValueError("Punto di vista sconosciuto.")
    for key in ("location", "visual"):
        if not isinstance(card.get(key), str) or not card[key].strip():
            raise ValueError(f"Scena: manca {key}.")
    for key in ("facts", "knowledge_before", "knowledge_after"):
        values = card.get(key)
        if not isinstance(values, list) or not values or not all(isinstance(x, str) and x.strip() for x in values):
            raise ValueError(f"Scena: {key} non valido.")
    present = card.get("characters_present")
    if not isinstance(present, list) or not present or any(x not in known_ids for x in present) or card["pov_id"] not in present:
        raise ValueError("Personaggi presenti non validi.")
    if not isinstance(card.get("withhold"), list) or not all(isinstance(x, str) for x in card["withhold"]):
        raise ValueError("Campo withhold non valido.")
    return card


class StoryBrain:
    def __init__(self, llm):
        self.llm, self.on_progress = llm, None

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
        if "card" in data:
            return await review_scene(self.llm, data)
        planner = PlanningService(self.llm)
        planner.on_progress = self.on_progress
        return await planner.review(data, {"rules": "Verifica continuita, identita, causalita e risoluzione; non inventare problemi."}, kind)

    async def prepare_card(self, folder, number, part, beat, ids, concept, structure, state, feedback=None):
        base = (
            f"Genera la scheda della scena {number}, segmento {beat}/3 della parte {part['part']}. "
            f"Concept: {json.dumps(concept, ensure_ascii=False)}. Piano: {json.dumps(structure, ensure_ascii=False)}. "
            f"Fatti precedenti VINCOLANTI: {json.dumps(state, ensure_ascii=False)}. "
            "Una sola azione nuova e concreta. Non ripetere scoperte concluse. Se si riesamina una prova, "
            "dichiaralo senza cambiare chi vi compare. knowledge_after deriva solo da facts o fatti precedenti. "
            "Non inserire decisioni/azioni nuove soltanto in knowledge_after. Ogni foto ha soggetti coerenti. "
            "Solo segmento 3 conclude la parte; solo ultima scena risolve la storia. "
            "characters_present: solo persone fisicamente presenti. Nei facts chiarisci chi comunica a chi e cosa. "
            "Non confondere verita fattuale e dolore personale. withhold: solo informazioni specifiche "
            "non comunicate a un destinatario; non istruzioni vaghe o azioni da nascondere al lettore. "
            f"JSON: scene_id={number}, part={part['part']}, pov_id tra {ids}, location, "
            "characters_present (ID), facts, knowledge_before, knowledge_after, withhold (liste), visual. "
            "Massimo 5 elementi per lista e 30 parole per elemento."
        )
        prompt = base + ("\nProblemi da risolvere senza cambiare fatti precedenti: " + json.dumps(feedback, ensure_ascii=False) if feedback else "")
        run = uuid.uuid4().hex[:10]
        issues = []
        for attempt in range(3):
            self.notify(f"Scena {number}: scheda con evidenze, tentativo {attempt+1}/3")
            card = await self.llm.generate_json(prompt)
            prefix = folder / "scenes" / f"{number:03}_{run}_card_{attempt+1}"
            self.save(prefix.with_suffix(".json"), card)
            try:
                validate_card(card, ids, number)
                if card.get("part") != part["part"]:
                    raise ValueError("Parte della scena errata.")
            except ValueError as exc:
                report = {"ok": False, "issues": [str(exc)]}
            else:
                report = await self.review({"concept": concept, "structure": structure, "previous_facts": state, "card": card}, "scheda scena")
            self.save(prefix.with_name(prefix.name + "_review.json"), report)
            issues = report["issues"]
            if report["ok"]:
                self.save(folder / "scenes" / f"{number:03}_card.json", card)
                self.save(folder / "scenes" / f"{number:03}_card_review.json", report)
                return card
            prompt = base + "\nRicostruisci la scheda risolvendo i problemi, non modificare scene precedenti. " + json.dumps({"draft": card, "issues": report}, ensure_ascii=False)
        raise ValueError(f"Scena {number}: scheda non approvata: " + "; ".join(issues))

    async def write_scene(self, folder, number, part, beat, ids, concept, structure, state, previous, bounds):
        minimum, maximum, target = bounds
        card = await self.prepare_card(folder, number, part, beat, ids, concept, structure, state)
        errors, text, repairs = [], "", 0
        attempts = max(1, min(10, int(os.getenv("SCENE_TEXT_ATTEMPTS", "6"))))
        run = uuid.uuid4().hex[:10]
        for attempt in range(attempts):
            self.notify(f"Scena {number}: narrazione con stato condiviso, tentativo {attempt+1}/{attempts}")
            prompt = writer_prompt(concept, card, state, previous, minimum, maximum, target)
            if errors:
                prompt += "\nCorreggi questa bozza senza conservare errori: " + json.dumps({"text": text, "issues": errors}, ensure_ascii=False)
            text = (await self.llm.generate_text(prompt)).strip()
            prefix = folder / "scenes" / f"{number:03}_{run}_text_{attempt+1}"
            self.save(prefix.with_suffix(".txt"), text)
            report = await self.review({"concept": concept, "structure": structure, "previous_facts": state, "card": card, "text": text}, "narrazione")
            count = word_count(text)
            errors = list(report["issues"])
            if not minimum <= count <= maximum:
                errors.append(f"Lunghezza {count}: richieste {minimum}-{maximum} parole.")
            self.save(prefix.with_name(prefix.name + "_review.json"), {**report, "ok": not errors, "issues": errors, "word_count": count})
            if not errors:
                return card, text
            if any(i["target"] == "card" for i in report.get("details", [])) and repairs < 2 and attempt+1 < attempts:
                repairs += 1
                self.notify(f"Scena {number}: difetto nei vincoli; ricostruzione scheda {repairs}/2")
                card = await self.prepare_card(folder, number, part, beat, ids, concept, structure, state, {"card": card, "review": report})
                text, errors = "", []
        raise ValueError(f"Scena {number}: narrazione non approvata dopo {attempts} tentativi: " + "; ".join(errors))

    async def generate_script(self, concept, structure, brief):
        folder = self.folder(brief)
        folder.mkdir(parents=True, exist_ok=True)
        parts = validate_parts(structure, int(brief["tiktok_clips"]))
        ids = [c["id"] for c in concept["characters"]]
        plan_hash = digest({"concept": concept, "structure": structure, "duration": brief["duration_minutes"], "policy": POLICY})
        state, approved, cards = [], [], []
        target = max(100, round(brief["duration_minutes"] * 60 / (len(parts)*3) * 2.5))
        bounds = (int(target*.75), int(target*1.3), target)
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
                        if candidate.get("part") != part["part"] or not bounds[0] <= word_count(candidate_text) <= bounds[1]:
                            raise ValueError("Checkpoint incompatibile.")
                        binding = {"context": context_hash, "card": digest(candidate), "text": hashlib.sha256(candidate_text.encode()).hexdigest()}
                        reused = checkpoint.is_file() and json.loads(checkpoint.read_text(encoding="utf-8")) == binding
                        if not reused:
                            self.notify(f"Scena {number}: nuova verifica con evidenze del materiale salvato")
                            c = await self.review({"concept": concept, "structure": structure, "previous_facts": state, "card": candidate}, "checkpoint scheda")
                            t = await self.review({"concept": concept, "structure": structure, "previous_facts": state, "card": candidate, "text": candidate_text}, "checkpoint testo")
                            self.save(prefix.with_name(prefix.name + "_evidence_migration.json"), {"card": c, "text": t})
                            reused = c["ok"] and t["ok"]
                        if reused:
                            card, text = candidate, candidate_text
                            self.notify(f"Scena {number}: checkpoint verificato, nessuna riscrittura")
                    except (OSError, ValueError) as exc:
                        self.notify(f"Scena {number}: checkpoint non riutilizzabile: {exc}")
                if not reused:
                    for old in (card_path, text_path, checkpoint):
                        if old.is_file():
                            self.save(folder / "scenes" / "backups" / (uuid.uuid4().hex + "_" + old.name), old.read_text(encoding="utf-8"))
                    try:
                        async with asyncio.timeout(max(60, float(os.getenv("SCENE_TOTAL_TIMEOUT", "1800")))):
                            card, text = await self.write_scene(folder, number, part, beat, ids, concept, structure, state, approved[-1][-1000:] if approved else "Inizio storia", bounds)
                    except TimeoutError as exc:
                        raise ValueError(f"Scena {number}: budget temporale esaurito, bozze e checkpoint precedenti conservati.") from exc
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
        self.save(folder / "narrative_manifest.json", {"script_sha256": hashlib.sha256(script.encode()).hexdigest(), "scene_count": len(cards), "policy": POLICY, "note": "Citazioni verificate non provano da sole la coerenza semantica; revisione dello stesso LLM."})
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
        return {"scenes": scenes, "timing_source": "estimated_word_count", "note": "Immagini e allineamento audio reale non generati da questo modulo."}
