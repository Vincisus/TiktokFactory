"""Windows/local launcher: prepare recovery once, then start a single local server."""
import importlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser


def main():
    os.chdir(Path(__file__).resolve().parent)
    if not Path(".env").exists():
        shutil.copyfile(".env.example", ".env")
        from dotenv import set_key
        try:
            with urllib.request.urlopen("http://127.0.0.1:1234/v1/models", timeout=5) as r:
                import json
                models = json.load(r).get("data", [])
            if len(models) == 1:
                chosen = models[0]["id"]
            else:
                print("Modelli disponibili:", [m.get("id") for m in models])
                chosen = input("Incolla l'API Model Identifier da LM Studio: ").strip()
            if not chosen:
                raise ValueError("Identificatore vuoto")
            set_key(".env", "LMSTUDIO_MODEL", chosen)
        except Exception as exc:
            print("Configurazione modello non completata:", exc)
            print("Apri .env, imposta LMSTUDIO_MODEL e riavvia Avvia.bat.")
            return 1
    # Patch only before launching the server; never rewrite code during a running job.
    source = Path("app/core/story_brain.py").read_text(encoding="utf-8-sig")
    if "async def prepare_recovery_card(" not in source:
        import apply_scene_recovery as patcher
        patcher.CHECKPOINT_LOAD = patcher.CHECKPOINT_LOAD.replace('"\n\n"', '"\\n\\n"')
        patcher.install()
    from dotenv import load_dotenv
    load_dotenv()
    model = os.getenv("LMSTUDIO_MODEL", "")
    if not model or model in {"local-model", "NOME_ESATTO_DEL_MODELLO"}:
        print("Imposta LMSTUDIO_MODEL in .env con l'identificatore esatto di LM Studio.")
        return 1
    if not shutil.which("ffmpeg"):
        print("Avviso: FFmpeg non trovato nel PATH. Il recupero narrativo funziona; il video richiede FFmpeg.")
    def open_page():
        for _ in range(30):
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/", timeout=1):
                    webbrowser.open("http://127.0.0.1:8000/static/index.html")
                    return
            except Exception:
                time.sleep(1)
    threading.Thread(target=open_page, daemon=True).start()
    return subprocess.call([sys.executable, "-m", "uvicorn", "app.main:app", "--env-file", ".env", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("Avvio interrotto:", exc)
        sys.exit(1)
