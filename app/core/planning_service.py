import json
import logging
from pathlib import Path

logger = logging.getLogger("uvicorn.error")


class PlanningService:
    def __init__(self, llm):
        self.llm = llm
        self.on_progress = None

    def notify(self, text):
        logger.info(text)
        if self.on_progress:
            self.on_progress(text)

    @staticmethod
    def save(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def check_concept(value):
        for key in ("title", "logline", "conflict", "turning_point", "resolution", "moral", "setting", "visual_style"):
            if not isinstance(value.get(key), str) or not value[key].strip():
                raise ValueError(f"Concept: manca {key}.")
        chars = value.get("characters")
        if not isinstance(chars, list) or not 2 <= len(chars) <= 5:
            raise ValueError("Servono 2-5 personaggi.")
        ids = []
        for char in chars:
            if not isinstance(char, dict) or any(not isinstance(char.get(k), str) or not char[k].strip() for k in ("id", "name", "role", "appearance")):
                raise ValueError("Personaggio incompleto.")
            ids.append(char["id"])
        if len(ids) != len(set(ids)):
            raise ValueError("ID personaggi duplicati.")

    @staticmethod
    def check_structure(value, count):
        parts = value.get("parts")
        if not isinstance(parts, list) or len(parts) != count:
            raise ValueError(f"Servono esattamente {count} parti.")
        for i, part in enumerate(parts, 1):
            if not isinstance(part, dict) or type(part.get("part")) is not int or part["part"] != i:
                raise ValueError("Numerazione delle parti errata.")
            if any(not isinstance(part.get(k), str) or not part[k].strip() for k in ("title", "summary", "cliffhanger")):
                raise ValueError(f"Parte {i} incompleta.")

    async def review(self, value, context, stage):
        report = await self.llm.generate_json(
            "Sei un revisore. Verifica solo errori BLOCCANTI: cronologia impossibile, "
            "ruoli scambiati, soluzione priva di causa, conoscenze non ancora acquisite, "
            "eventi ripetuti come nuovi, promessa centrale senza risoluzione. "
            "Distingui fatti oggettivi da sospetti e convinzioni: una rivelazione che smentisce "
            "il protagonista NON e una contraddizione se motivata. "
            "Non segnalare preferenze stilistiche, dettagli omessi non necessari o problemi ipotetici. "
            "Non approvare per cortesia e non inventare difetti. "
            "Ogni issue deve essere una frase completa e operativa di massimo 180 caratteri. "
            "JSON: ok booleano, issues lista di massimo 5 stringhe. ok=true solo con issues=[]. "
            f"Fase: {stage}. Contesto vincolante: {json.dumps(context, ensure_ascii=False)}. "
            f"Documento: {json.dumps(value, ensure_ascii=False)}"
        )
        if type(report.get("ok")) is not bool or not isinstance(report.get("issues"), list) or not all(isinstance(x, str) and x.strip() for x in report["issues"]):
            raise ValueError("Verdetto del revisore non valido.")
        if report["ok"] != (len(report["issues"]) == 0):
            raise ValueError("Verdetto del revisore contraddittorio.")
        return report

    async def refine(self, folder, stage, prompt, validator, context):
        current_prompt = prompt
        for attempt in range(3):
            label = f"Generazione {stage}" if attempt == 0 else f"Correzione {stage} {attempt}/2"
            self.notify(label)
            value = await self.llm.generate_json(current_prompt)
            self.save(folder / f"{stage}_{attempt:02}_draft.json", value)
            try:
                validator(value)
            except ValueError as exc:
                report = {"ok": False, "issues": [str(exc)]}
            else:
                self.notify(f"Revisione {stage}, versione {attempt + 1}")
                report = await self.review(value, context, stage)
            self.save(folder / f"{stage}_{attempt:02}_review.json", report)
            if report["ok"]:
                self.save(folder / f"{stage}_approved.json", value)
                return value
            if attempt < 2:
                current_prompt = (
                    prompt + "\nCORREZIONE MIRATA: mantieni schema, personaggi e premessa; "
                    "cambia soltanto quanto serve a risolvere i problemi indicati. "
                    "Aggiorna coerentemente tutte le sezioni coinvolte. Non aggiungere sottotrame "
                    "per nascondere le contraddizioni. Restituisci l'intero documento corretto. "
                    f"Versione precedente: {json.dumps(value, ensure_ascii=False)}. "
                    f"Problemi: {json.dumps(report['issues'], ensure_ascii=False)}"
                )
        raise ValueError(f"{stage} non approvato dopo due correzioni: " + "; ".join(report["issues"]) + f". Versioni salvate in {folder}")

    async def generate_concept(self, brief, project_dir):
        prompt = (
            "Crea una storia originale di fiction in italiano. "
            "Formato: racconto realistico in prima persona con segreti, relazioni, famiglia, "
            "amicizie, universita, lavoro o mistero domestico. Varia l'argomento, non usare "
            "fantasy, laboratori segreti o complotti su intere comunita. "
            "Pochi personaggi, luoghi quotidiani e conflitto concreto. Nessuna copia dei riferimenti. "
            "Esplicita nel conflict cosa crede il protagonista all'inizio e quale sia la verita. "
            "Il turning_point deve spiegare la scoperta con una prova comprensibile. "
            "La resolution deve indicare azione, conseguenza e costo personale concreto. "
            "Non distruggere l'unica prova e non risolvere problemi materiali con sole dichiarazioni. "
            "Non inserire dettagli operativi su veleni, violenza o reati. "
            f"Tema: {brief['series']}. Richiesta: {brief.get('request', {}).get('message', '')}. "
            "JSON con title, logline, conflict, turning_point, resolution, moral, setting, "
            "visual_style (stringhe), characters (2-5 oggetti con id, name, role, appearance). "
            "Decidi il finale prima di scrivere e mantieni le relazioni coerenti."
        )
        return await self.refine(Path(project_dir) / "planning", "concept", prompt, self.check_concept, {"format": "dramma realistico; fatti distinti dalle convinzioni"})

    async def generate_structure(self, concept, brief, project_dir):
        count = int(brief["tiktok_clips"])
        prompt = (
            f"Pianifica {count} parti consecutive della stessa storia. "
            f"Concept approvato e vincolante: {json.dumps(concept, ensure_ascii=False)}. "
            "Non cambiare la verita o la soluzione del concept. Descrivi eventi concreti in ordine; "
            "distingui sospetti iniziali e verita rivelate. Ogni evento decisivo avviene una volta. "
            "Separa scoperta, prova, decisione e conseguenza. L'ultima parte chiude il conflitto; "
            "il suo cliffhanger e una frase conclusiva, non un elenco di tratti fisici. "
            "JSON con parts: lista di oggetti con part (intero da 1), title, summary e cliffhanger."
        )
        value = await self.refine(Path(project_dir) / "planning", "structure", prompt, lambda data: self.check_structure(data, count), {"concept": concept})
        for part in value["parts"]:
            part["duration_seconds"] = brief["duration_minutes"] * 60 / count
        self.save(Path(project_dir) / "planning" / "structure_approved.json", value)
        return value
