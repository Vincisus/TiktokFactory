# Modalita leggera: LFM e prova di una sola scena

Aprire http://127.0.0.1:8000/ oppure /static/lean.html. La vecchia console resta in /static/index.html; Avvia.bat potrebbe aprire ancora quel vecchio indirizzo, quindi passare alla nuova pagina.

1. Fermare lavori precedenti e non avviare due server.
2. In LM Studio espellere gli altri modelli, caricare LFM e avviare il server locale.
3. Se il modello lo supporta, impostare il reasoning a 256 in LM Studio. La modalita leggera non impone quel parametro tramite API e non garantisce che le preferenze della chat siano applicate dal server.
4. Nella nuova pagina selezionare l'identificatore LFM esposto dal server: non si modifica .env.
5. Selezionare il progetto giusto, per esempio 20261111_185213_a263d6.
6. Premere Prova una sola scena. Massimo due chiamate generative: testo e fatti insieme, poi un controllo. Se fallisce un controllo locale o il modello tronca la risposta, puo fermarsi dopo la prima chiamata. Nessuna correzione automatica o fallback a JSON libero.
7. Leggere la scena, il verdetto, i tempi e il numero di chiamate. Una bozza respinta e mostrata come NON approvata.
8. Solo dopo una prova approvata, usare Continua con lo stesso modello. La prima scena approvata e riutilizzata se non esiste gia un checkpoint leggero; le altre richiedono due chiamate ciascuna. Un'unica chiamata finale controlla la continuita e propone cinque titoli.

Per dodici scene, il percorso narrativo senza errori da piano gia salvato richiede complessivamente 25 chiamate (inclusa la prova), contro almeno 49 del vecchio percorso completo con scheda separata. Non e una previsione del tempo: dipende dal modello e dal suo ragionamento.

Gli output sono separati in projects/ID/lean e le diagnostiche in projects/ID/lean_runs. Non si sovrascrivono script, schede o checkpoint della vecchia modalita. In lean si salvano script, storyboard con tempi stimati, titoli e checkpoint. Nessuna voce, immagine, animazione o video viene generato qui. Nessuna pubblicazione automatica.

Il limite output e 2048 token per la generazione, 768 per la verifica e 1024 per il controllo finale; ragionamento e comportamento effettivo dipendono dal server. Una risposta incompleta viene rifiutata, non utilizzata come testo valido. Il contesto 4096 e un punto di partenza per la prova breve, non una garanzia per un progetto lungo.

Test: .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_lean_pipeline.py" -v

I test sono simulati e verificano conteggio delle chiamate, arresti, checkpoint e isolamento dei file. Non sono un collaudo del modello LFM reale, del browser o della pipeline multimediale.
