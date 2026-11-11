"""Create a coherent, separate Marta project. Never overwrite the original."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import socket
import tempfile

CONCEPT = {
    "title": "Il quaderno di Marta — piano corretto",
    "logline": "Marco, autore di uno studio clinico, scambia il ruolo di coordinatrice di Marta per un'appropriazione del proprio lavoro. La sua accusa provoca la sospensione della collega; quando verifica i documenti completi, deve ritrattare e rinunciare all'incarico retribuito che potrebbe sostituirla.",
    "conflict": "Fatto iniziale: Marco ha scritto lo studio di ricerca; Marta coordina una proposta applicativa distinta che usa e cita quello studio. Marco vede solo le slide introduttive e sospetta un furto di paternita. Il sospetto non e la verita: Marta non rivendica lo studio come proprio. Marco presenta comunque un'accusa scritta, e Sanna sospende provvisoriamente Marta. Solo dopo Marco verifica la relazione completa e riconosce il proprio errore.",
    "turning_point": "Dopo la sospensione, Marta mostra volontariamente a Marco il quaderno con la cronologia della proposta e il riferimento alla relazione completa. Il quaderno e un indizio, non una prova conclusiva. Marco legge poi la relazione e gli allegati: lo studio originale e attribuito a lui, mentre Marta ha sviluppato e coordinato l'applicazione. Questa verifica smentisce l'accusa di plagio.",
    "resolution": "Marco invia a Sanna una rettifica scritta, rinuncia all'offerta di coordinamento temporaneo e al relativo compenso aggiuntivo futuro, e ammette l'errore davanti a Marta. Sanna, unica titolare della decisione organizzativa, revoca la sospensione e reintegra Marta. Lo stipendio ordinario di Marco non viene revocato; il costo e la rinuncia all'incarico extra e alla sua giustificazione di vendetta. Marta non concede un perdono immediato: concordano regole trasparenti per lavorare insieme.",
    "moral": "Verificare prima di accusare; riparare un danno richiede una rettifica concreta, non soltanto parole.",
    "setting": "Clinica privata di una citta universitaria di provincia, sala riunioni e uffici, fine inverno.",
    "visual_style": "Interni quotidiani, luce fredda, gesti semplici, documenti e mani; nessuna azione spettacolare.",
    "characters": [
        {"id": "c1", "name": "Marco Ferri", "role": "Protagonista e narratore, ricercatore autore dello studio originale; non e il coordinatore iniziale della proposta.", "appearance": "Trentenne, magro, occhiali sottili e giacca scura."},
        {"id": "c2", "name": "Marta Lanza", "role": "Collega di Marco e coordinatrice iniziale della proposta applicativa; non e autrice dello studio originale di Marco.", "appearance": "Trentadue anni, capelli corti e maglione azzurro."},
        {"id": "c3", "name": "Dottoressa Sanna", "role": "Direttrice della clinica; decide sospensione e reintegro del coordinamento.", "appearance": "Cinquantaquattro anni, abito grigio e voce ferma."}
    ]
}
PARTS = [
    {"part": 1, "title": "Il sospetto", "summary": "Sanna apre la riunione della proposta coordinata da Marta. Marco, autore dello studio di base, vede le slide introduttive senza aver letto la relazione completa. Confonde la visibilita di Marta come coordinatrice con una pretesa di paternita e chiede una verifica; non ha ancora prove di plagio.", "cliffhanger": "Sanna richiede una verifica formale delle attribuzioni prima di approvare la proposta."},
    {"part": 2, "title": "Il quaderno e la verifica", "summary": "Marco invia un'accusa scritta senza aver verificato gli allegati. Sanna sospende provvisoriamente Marta, senza dichiararla colpevole. Marta mostra a Marco il quaderno con la cronologia del lavoro; Marco legge quindi la relazione completa e scopre che il suo studio e citato e distinto dall'applicazione sviluppata da Marta.", "cliffhanger": "Marco deve decidere se correggere l'accusa che ha provocato la sospensione."},
    {"part": 3, "title": "La rettifica", "summary": "Sanna offre a Marco un incarico temporaneo di coordinamento con compenso aggiuntivo mentre Marta e sospesa. Marco prepara una rettifica documentata, poi la invia e rinuncia all'offerta e al compenso futuro. Sanna convoca entrambi per riesaminare il provvedimento.", "cliffhanger": "La rettifica e stata inviata: ora la decisione sul reintegro spetta a Sanna."},
    {"part": 4, "title": "Riparare", "summary": "Nella riunione Marco distingue il proprio studio dal lavoro di Marta e si assume la responsabilita dell'accusa. Sanna revoca la sospensione e reintegra Marta. I due colleghi concordano una verifica congiunta delle attribuzioni; il progetto puo ripartire, ma la fiducia richiede tempo.", "cliffhanger": "Marco firma una presentazione con ruoli e contributi espliciti, senza chiedere che Marta lo perdoni subito."}
]
BEATS = [
    ("Sanna apre la riunione; Marco riconosce Marta come coordinatrice e se stesso come autore dello studio di base.", "Marco sa soltanto che Marta deve presentare la proposta; non ha letto la relazione completa.", ["quaderno", "taccuino", "reintegro", "reintegrata"]),
    ("Marta presenta le slide introduttive come coordinatrice, senza dichiararsi autrice dello studio. Marco interpreta la propria scarsa visibilita come un possibile torto, non come prova.", "Marco ha assistito all'apertura; non ha verificato gli allegati e Marta non e sospesa.", ["quaderno", "taccuino", "reintegro", "reintegrata"]),
    ("Marco chiede chiarimenti sulle attribuzioni; Sanna richiede una verifica formale prima dell'approvazione. Nessuna sospensione e ancora decisa.", "Marco e sospettoso ma non dispone di prove di plagio.", ["quaderno", "taccuino", "reintegro", "reintegrata"]),
    ("Marco invia un'accusa scritta senza leggere gli allegati; Sanna sospende provvisoriamente Marta in attesa di verifica, senza accertare un plagio.", "Sono stati richiesti chiarimenti; Marta e ancora coordinatrice all'inizio della scena.", ["quaderno", "taccuino", "reintegro", "reintegrata"]),
    ("Marta mostra volontariamente il quaderno con la cronologia della proposta e indica dove consultare la relazione completa. Marco considera il quaderno un indizio da verificare.", "Marta e sospesa; Marco non ha ancora verificato la relazione completa.", ["reintegro", "reintegrata"]),
    ("Marco legge la relazione completa e gli allegati: il suo studio e citato correttamente, mentre Marta ha sviluppato la proposta applicativa. Riconosce che l'accusa di plagio non e sostenuta.", "Il quaderno ha indicato i documenti, ma non ha ancora dimostrato da solo l'innocenza di Marta.", ["reintegro", "reintegrata"]),
    ("Sanna offre a Marco il coordinamento temporaneo con un compenso extra durante la sospensione. Marco ascolta l'offerta senza accettarla e ne avverte il conflitto con cio che ha scoperto.", "Marco ha verificato gli allegati; Marta e ancora sospesa e Sanna non ha ancora ricevuto una rettifica.", ["reintegro", "reintegrata"]),
    ("Marco prepara una rettifica che cita i documenti controllati e distingue studio originale e proposta applicativa. Non la invia ancora e non riceve ancora un reintegro.", "Marco sa che la sua accusa e infondata; l'offerta temporanea non e stata accettata.", ["reintegro", "reintegrata"]),
    ("Marco invia la rettifica a Sanna e rinuncia esplicitamente all'incarico temporaneo e al relativo compenso futuro. Sanna riceve il messaggio e convoca una riunione.", "La rettifica esiste solo come bozza; Marta e ancora sospesa. Lo stipendio ordinario di Marco non e in discussione.", ["reintegro", "reintegrata"]),
    ("In riunione Marco ammette l'errore e chiarisce davanti a Marta e Sanna i contributi di ciascuno. Chiede scusa senza esigere un perdono immediato.", "Sanna ha ricevuto la rettifica ma non ha ancora revocato formalmente la sospensione.", ["reintegrata"]),
    ("Sanna verifica la rettifica, revoca formalmente la sospensione e reintegra Marta come coordinatrice. Marco non assegna o restituisce personalmente il ruolo.", "Marta e ancora sospesa all'inizio; Marco ha ammesso l'errore e rinunciato all'offerta.", []),
    ("Marco e Marta concordano una verifica congiunta delle attribuzioni e firmano una presentazione con ruoli espliciti. Il lavoro puo ripartire; la fiducia non torna automaticamente.", "Marta e stata reintegrata da Sanna; Marco resta autore dello studio e ha rinunciato soltanto al compenso dell'incarico extra.", [])
]
SOURCE_ID = "20261111_185213_a263d6"
TARGET_ID = SOURCE_ID + "_repaired_v1"


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def corrected_plan(duration):
    contracts = {"version": "marta-v1", "invariants": {"study_author_id": "c1", "initial_coordinator_id": "c2", "decision_authority_id": "c3"}, "premise": "Marco ha scritto lo studio originale. Marta coordina una proposta applicativa distinta. Sanna decide gli incarichi. La visibilita di Marta non dimostra un furto di paternita.", "scenes": []}
    for number, (goal, before, forbidden) in enumerate(BEATS, 1):
        contracts["scenes"].append({"scene_id": number, "part": (number-1)//3+1, "beat": (number-1)%3+1, "pov_id": "c1", "goal": goal, "knowledge_before": before, "roles": {"c1": "Ricercatore autore dello studio originale e narratore.", "c2": "Coordinatrice sospesa provvisoriamente." if 5 <= number <= 11 else "Coordinatrice della proposta applicativa.", "c3": "Direttrice, unica autorita su sospensione e reintegro."}, "forbidden_terms": list(forbidden)})
    parts = deepcopy(PARTS)
    for part in parts:
        part["duration_seconds"] = duration * 60 / 4
    structure = {"parts": parts, "contract_version": "marta-v1", "scene_contract_sha256": digest(contracts)}
    return deepcopy(CONCEPT), structure, contracts


def migrate(root=Path("projects"), check_server=True):
    root = Path(root).resolve()
    source, target = root / SOURCE_ID, root / TARGET_ID
    if source.resolve().parent != root or not source.is_dir() or source.is_symlink():
        raise ValueError("Progetto sorgente non trovato o percorso non consentito")
    if any(root.glob("*/.scene_recovery.lock")):
        raise ValueError("Esiste un lock: fermare tutti i lavori prima della migrazione")
    if check_server:
        with socket.socket() as sock:
            sock.settimeout(1)
            if sock.connect_ex(("127.0.0.1", 8000)) == 0:
                raise ValueError("Ferma prima Uvicorn con Ctrl+C; LM Studio puo restare acceso")
    def read(name):
        return json.loads((source / name).read_text(encoding="utf-8-sig"))
    brief, old_concept, old_structure = read("brief.json"), read("concept.json"), read("structure.json")
    if brief.get("id") != SOURCE_ID or old_concept.get("title") != "Il quaderno di Marta" or int(brief.get("tiktok_clips", 0)) != 4:
        raise ValueError("Il progetto non corrisponde alla storia prevista: nulla modificato")
    if not {"c1", "c2", "c3"}.issubset({c.get("id") for c in old_concept.get("characters", [])}):
        raise ValueError("Personaggi sorgenti inattesi")
    duration = int(brief["duration_minutes"])
    if not 10 <= duration <= 30:
        raise ValueError("Durata sorgente fuori intervallo 10-30 minuti")
    concept, structure, contracts = corrected_plan(duration)
    if target.exists():
        if target.is_symlink():
            raise ValueError("La destinazione non puo essere un collegamento")
        def existing(name):
            return json.loads((target / name).read_text(encoding="utf-8"))
        if existing("concept.json") == concept and existing("structure.json") == structure and existing("scene_contract.json") == contracts:
            return target
        raise ValueError("La destinazione esiste con contenuti diversi: non viene sovrascritta")
    new_brief = deepcopy(brief)
    new_brief["id"] = TARGET_ID
    new_brief["source_project_id"] = SOURCE_ID
    stage = Path(tempfile.mkdtemp(prefix=".marta_repair_", dir=root))
    try:
        documents = {"brief.json": new_brief, "concept.json": concept, "structure.json": structure, "scene_contract.json": contracts, "migration.json": {"source_project_id": SOURCE_ID, "created_at": datetime.now(timezone.utc).isoformat(), "source_plan_sha256": digest([old_concept, old_structure]), "policy": "assistant-curated coherent rewrite; not a guarantee of model output", "reused_generated_scenes": 0}}
        for name, value in documents.items():
            (stage / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        stage.rename(target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        print("Progetto corretto pronto:", migrate())
        print("Il progetto originale e i suoi tentativi sono rimasti intatti.")
        print("Avvia Avvia.bat, apri /static/lean.html e seleziona il progetto con suffisso _repaired_v1.")
        print("Prova una sola scena con LFM. Nessuna generazione viene avviata da questo script.")
    except Exception as exc:
        raise SystemExit("Migrazione interrotta: " + str(exc))
