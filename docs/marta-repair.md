# Correzione del piano: Il quaderno di Marta

Questa e una riscrittura editoriale del progetto noto, non una garanzia che qualsiasi modello generi sempre testo corretto.

Ruoli univoci: Marco autore dello studio; Marta coordinatrice iniziale della proposta applicativa; Sanna unica autorita che puo sospendere o reintegrare. La sospensione deriva dall'accusa di Marco. Il quaderno indica documenti da verificare, non dimostra da solo l'innocenza. Il costo finale e la rinuncia a un incarico extra, non sei mesi di stipendio sottratti senza spiegazione.

Con Uvicorn e ogni generazione fermi:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_marta_repair.py" -v
.\.venv\Scripts\python.exe .\repair_marta_project.py
.\Avvia.bat
```

Il comando crea projects/20261111_185213_a263d6_repaired_v1 e non modifica l'originale. Non trasferisce scene, prove o checkpoint prodotti dal piano sbagliato. Ripetere il comando non azzera il nuovo progetto: se i file del piano corrispondono, conserva il lavoro; se differiscono, si ferma.

Aprire http://127.0.0.1:8000/static/lean.html, selezionare LFM e il progetto con suffisso _repaired_v1, quindi provare una sola scena. Non selezionare il vecchio ID per verificare questa correzione.

scene_contract.json assegna dodici scene. La generazione e la revisione ricevono soltanto premessa, stato precedente e obiettivo corrente, non la logline e il finale del concept. Un controllo locale blocca narratore errato e termini anticipati esplicitamente vietati; non e un verificatore semantico completo. Si mantengono le due chiamate massime della prova e nessun rifacimento automatico.

Lo storyboard resta stimato e non si producono audio, immagini o video. I dieci test sono test di migrazione e dei vincoli con risposte simulate, non un collaudo di LFM sul PC dell'utente. Nessun risultato del modello reale e garantito.
