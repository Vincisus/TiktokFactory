# Profilo di prova LFM e limite token

Questa patch riduce la lunghezza richiesta a concept e struttura e ritenta UNA volta una generazione troncata con istruzioni piu compatte. Non approva automaticamente documenti e non usa JSON incompleto. Le revisioni mantengono gli stessi errori bloccanti.

## Configurazione locale

Il file .env.example non modifica .env esistente. Con il server fermo, modificare manualmente .env accanto a requirements.txt, evitando chiavi duplicate:

```env
LMSTUDIO_MAX_TOKENS=8192
LMSTUDIO_IDLE_TIMEOUT=900
LMSTUDIO_TOTAL_TIMEOUT=3600
```

8192 e un budget massimo di output di prova, non una misura verificata del fabbisogno. Prompt e output devono stare entrambi nel contesto caricato. Provare contesto 16384 soltanto se LM Studio stima memoria sufficiente; altrimenti mantenere budget e contesto piu piccoli e confrontare un piano breve. Non impostare il massimo contesto teorico del modello.

Per LFM2.5-24B-A2B Liquid AI raccomanda temperature=0.1, top_k=50, repetition_penalty=1.05:
https://docs.liquid.ai/lfm/models/lfm25-24b-a2b

ATTENZIONE: llm_service.py invia temperature=0.2 nelle richieste JSON e temperature=0.8 per generate_text se il chiamante non specifica altro. I preset della UI LM Studio non garantiscono che tali valori siano sostituiti. Questa patch non modifica il sampling del client e non forza parametri proprietari non verificati.

## Verifica

1. Riavviare il server dopo aver aggiornato codice e .env.
2. Provare un nuovo progetto breve con 3 parti prima di una storia completa.
3. In caso di blocco leggere il JSON diagnostico indicato: finish_reason, reasoning_characters, response ed elapsed_seconds.
4. Se la risposta finale e vuota e reasoning_characters e elevato, distinguere esaurimento nel reasoning da output JSON troppo lungo. Aumentare token alla cieca non risolve necessariamente il problema.
5. Conservare il file diagnostico e le versioni draft/review: una revisione negativa non equivale a errore di trasporto o di limite token.

Non e stato eseguito un test sul PC dell'utente. Questa patch non dimostra che TTS, rendering e pipeline completa funzionino. Non cambia modello, non scarica pesi, non tocca i progetti salvati.
