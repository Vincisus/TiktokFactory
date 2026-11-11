# TiktokFactory

Applicazione locale per generare storie narrate in video verticali per TikTok e video lunghi per YouTube.

## Funzionalità

- Interfaccia web locale
- Comando `Genera il prossimo video`
- Barra di progresso e log in tempo reale
- Job asincroni
- Integrazione con LM Studio tramite API OpenAI-compatible
- Generazione concept, struttura, script e storyboard
- Voce narrante locale tramite pyttsx3
- Sottotitoli SRT
- Rendering MP4 verticale 1080x1920
- Generazione di 4 clip TikTok
- Metadati per YouTube e TikTok
- Nessuna API cloud richiesta per la voce

## Requisiti

- Python 3.12 consigliato
- FFmpeg installato e disponibile nel PATH
- LM Studio con server locale attivo su `http://127.0.0.1:1234`

## Installazione

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

## Avvio

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Apri:

```text
http://127.0.0.1:8000/static/index.html
```

## Uso

Premi `Genera il prossimo video`.

La barra mostrerà l’avanzamento delle fasi:

1. Concept
2. Struttura
3. Script
4. Storyboard
5. Voce
6. Sottotitoli
7. Rendering
8. Clip TikTok
9. Metadati
10. Controllo qualità

## Configurazione LM Studio

Modifica `.env`:

```env
LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1
LMSTUDIO_API_KEY=lm-studio
LMSTUDIO_MODEL=NOME_ESATTO_DEL_MODELLO
```

## Note

Il progetto genera contenuti originali. Le voci usate da pyttsx3 dipendono dalle voci installate nel sistema Windows.