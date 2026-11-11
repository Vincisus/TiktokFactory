# TiktokFactory

Applicazione locale per generare storie narrate in video verticali per TikTok e video lunghi per YouTube.

## Funzionalità MVP

- Interfaccia web locale con chat
- Comando `genera il prossimo video`
- Integrazione con LM Studio tramite API OpenAI-compatible
- Generazione di concept, struttura, script e storyboard
- Voce narrante italiana con edge-tts
- Sottotitoli SRT
- Rendering MP4 verticale 1080x1920
- Generazione di 4 clip TikTok
- Metadati per YouTube e TikTok
- Test automatici di base

## Requisiti

- Python 3.11+
- FFmpeg installato e disponibile nel PATH
- LM Studio con server locale attivo su `http://127.0.0.1:1234`
- Un modello LLM caricato in LM Studio

## Installazione

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

## Avvio

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Apri poi:

```text
http://127.0.0.1:8000
```

## Comando nella chat

```text
Genera il prossimo video
```

Il sistema creerà una nuova cartella in `projects/`, genererà la storia, la voce, i sottotitoli, il video YouTube e quattro clip TikTok.

## Configurazione

Modifica `.env` e `config/settings.yaml` per cambiare modello, voce, durata e stile visivo.

## Note

Il progetto genera contenuti originali. Non copiare storie, testi o formati specifici di altri creatori.