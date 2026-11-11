const button = document.getElementById("generate");
const status = document.getElementById("status");
const log = document.getElementById("log");

function addLog(text) {
  const line = document.createElement("div");
  line.className = "line";
  line.textContent = text;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

button.addEventListener("click", async () => {
  button.disabled = true;
  status.textContent = "Generazione in corso…";
  addLog("Avvio pipeline…");

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: "Genera il prossimo video",
        series: "tradimenti_e_vendetta",
        duration_minutes: 12,
        tiktok_clips: 4
      })
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "Errore durante la generazione");
    }

    addLog("Progetto: " + data.project_id);
    addLog("Video YouTube: " + data.youtube_video);
    addLog("Clip TikTok: " + data.tiktok_clips.length);
    addLog("Stato: completato");
    status.textContent = "Completato";
  } catch (error) {
    addLog("Errore: " + error.message);
    status.textContent = "Errore";
  } finally {
    button.disabled = false;
  }
});
