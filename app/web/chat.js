const button = document.getElementById("generate");
const status = document.getElementById("status");
const log = document.getElementById("log");
const progressFill = document.getElementById("progress-fill");
const progressText = document.getElementById("progress-text");
const currentStep = document.getElementById("current-step");

function addLog(text) {
  const line = document.createElement("div");
  line.className = "line";
  line.textContent = text;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

function updateProgress(job) {
  progressFill.style.width = job.progress + "%";
  progressText.textContent = job.progress + "%";
  currentStep.textContent = job.current_step;
  status.textContent = job.status === "completed" ? "Completato" : "In corso";
}

button.addEventListener("click", async () => {
  button.disabled = true;
  status.textContent = "Avvio…";
  log.innerHTML = "";

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
    if (!response.ok) throw new Error(data.detail || "Errore durante l’avvio");

    addLog("Job avviato: " + data.job_id);

    const interval = setInterval(async () => {
      const statusResponse = await fetch("/api/jobs/" + data.job_id);
      const job = await statusResponse.json();

      updateProgress(job);
      log.innerHTML = "";
      job.logs.forEach(addLog);

      if (job.status === "completed") {
        clearInterval(interval);
        button.disabled = false;
        addLog("Video YouTube: " + job.result.youtube_video);
        addLog("Clip TikTok generate: " + job.result.tiktok_clips.length);
      }

      if (job.status === "failed") {
        clearInterval(interval);
        button.disabled = false;
        status.textContent = "Errore";
        addLog("Errore: " + job.error);
      }
    }, 1500);

  } catch (error) {
    status.textContent = "Errore";
    addLog("Errore: " + error.message);
    button.disabled = false;
  }
});
