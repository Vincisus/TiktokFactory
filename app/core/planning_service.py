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
            "Distingui fatti oggettivi da sospetti e convinzioni. Una rivelazione motivata "
            "che smentisce il protagonista non e una contraddizione. "
            "Non segnalare preferenze stilistiche o dettagli non necessari. "
            "Non inventare difetti e non approvare per cortesia. "
            "Risposta finale breve: ok booleano, issues massimo 5 stringhe di 180 caratteri. "
            "ok=true solo con issues=[]. Non riscrivere il documento. "
            f"Fase: {stage}. Contesto: {json.dumps(context, ensure_ascii=False)}. "
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
            self.notify(f"Generazione {stage}" if attempt == 0 else f"Correzione {stage} {attempt}/2")
            try:
                value = await self.llm.generate_json(current_prompt)
            except RuntimeError as exc:
                if "Limite token raggiunto" not in str(exc):
                    raise
                self.notify(f"{stage}: limite token; un solo tentativo con risposta compatta")
                value = await self.llm.generate_json(
                    current_prompt + "\nRISPOSTA COMPATTA: solo JSON finale; nessuna spiegazione. "
                    "Massimo 45 parole per summary, 12 per cliffhanger, 8 per title; "
                    "per gli altri campi massimo 45 parole. Non scrivere il racconto completo."
                )
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
                    prompt + "\nCORREZIONE MIRATA: mantieni schema, personaggi e premessa. "
                    "Risolvi solo i problemi segnalati senza aggiungere sottotrame. "
                    "Rispetta i limiti di lunghezza originali e restituisci il documento intero. "
                    f"Versione: {json.dumps(value, ensure_ascii=False)}. "
                    f"Problemi: {json.dumps(report['issues'], ensure_ascii=False)}"
                )
        raise ValueError(f"{stage} non approvato dopo due correzioni: " + "; ".join(report["issues"]) + f". Versioni salvate in {folder}")

    async def generate_concept(self, brief, project_dir):
        prompt = (
            "Crea una storia originale di fiction in italiano. "
            "Racconto realistico in prima persona: relazioni, famiglia, amicizie, universita, "
            "lavoro o mistero domestico. Niente fantasy o complotti su intere comunita. "
            "Pochi personaggi, luoghi quotidiani, conflitto concreto. "
            "Esplicita in conflict convinzione iniziale e verita; nel turning_point una prova "
            "comprensibile; nella resolution azione, conseguenza e costo personale. "
            "Non distruggere l'unica prova. Niente dettagli operativi su violenza o reati. "
            f"Tema: {brief['series']}. Richiesta: {brief.get('request', {}).get('message', '')}. "
            "JSON con title, logline, conflict, turning_point, resolution, moral, setting, "
            "visual_style (stringhe), characters (2-5 oggetti: id, name, role, appearance). "
            "Non scrivere il racconto: massimo 8 parole per title, 60 per conflict, "
            "45 per turning_point e resolution, 25 per ogni altro campo; "
            "massimo 20 parole per ogni campo del personaggio. Decidi il finale ora."
        )
        return await self.refine(Path(project_dir) / "planning", "concept", prompt, self.check_concept, {"format": "dramma realistico; fatti distinti dalle convinzioni"})

    async def generate_structure(self, concept, brief, project_dir):
        count = int(brief["tiktok_clips"])
        if not 1 <= count <= 12:
            raise ValueError("La pianificazione supporta da 1 a 12 parti per progetto.")
        prompt = (
            f"Pianifica {count} parti consecutive della stessa storia. "
            f"Concept vincolante: {json.dumps(concept, ensure_ascii=False)}. "
            "Non cambiare verita o soluzione. Eventi concreti in ordine; distingui sospetti "
            "e verita rivelate. Ogni evento decisivo avviene una volta. "
            "Separa scoperta, prova, decisione e conseguenza. L'ultima parte chiude il conflitto. "
            "JSON con parts: oggetti con part (intero consecutivo da 1), title, summary, cliffhanger. "
            "Questo e un piano, NON la sceneggiatura: massimo 8 parole per title, "
            "60 per summary e 15 per cliffhanger. Ultimo cliffhanger: frase conclusiva. "
            "La durata finale verra ottenuta nella scrittura delle scene, non allungando questo JSON."
        )
        value = await self.refine(Path(project_dir) / "planning", "structure", prompt, lambda data: self.check_structure(data, count), {"concept": concept})
        for part in value["parts"]:
            part["duration_seconds"] = brief["duration_minutes"] * 60 / count
        self.save(Path(project_dir) / "planning" / "structure_approved.json", value)
        return value
