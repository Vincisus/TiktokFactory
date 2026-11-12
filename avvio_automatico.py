import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import venv
import webbrowser

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
PYTHON = ROOT / '.venv' / 'Scripts' / 'python.exe'


def run(command):
    subprocess.run(command, check=True, cwd=ROOT)


def main():
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('Avvia.bat deve usare Python 3.12.')
    if not PYTHON.exists():
        print('Creazione ambiente Python locale...', flush=True)
        venv.EnvBuilder(with_pip=True).create(ROOT / '.venv')
    version = subprocess.check_output([str(PYTHON), '-c', 'import sys;print(sys.version_info[:2] == (3,12))'], text=True).strip()
    if version != 'True':
        raise RuntimeError('La .venv esistente non usa Python 3.12. Con server fermo, rinomina .venv e riprova. Nessun file e stato cancellato.')
    requirements = ROOT / 'requirements.txt'
    fingerprint = hashlib.sha256(requirements.read_bytes()).hexdigest()
    marker = ROOT / '.venv' / 'launcher_requirements.sha256'
    if not marker.exists() or marker.read_text().strip() != fingerprint:
        print('Installazione dipendenze: attendere...', flush=True)
        run([str(PYTHON), '-m', 'pip', 'install', '-r', str(requirements)])
        run([str(PYTHON), '-m', 'pip', 'check'])
        marker.write_text(fingerprint)
    if Path(sys.executable).resolve() != PYTHON.resolve():
        return subprocess.call([str(PYTHON), str(Path(__file__).resolve())], cwd=ROOT)
    from dotenv import load_dotenv
    import imageio_ffmpeg
    envfile = ROOT / '.env'
    if not envfile.exists():
        example = ROOT / '.env.example'
        text = example.read_text(encoding='utf-8') if example.exists() else 'LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1\n'
        envfile.write_text(text, encoding='utf-8')
    load_dotenv(envfile)
    env = os.environ.copy()
    env.setdefault('LMSTUDIO_MAX_TOKENS', '8192')
    env.setdefault('LMSTUDIO_IDLE_TIMEOUT', '900')
    env.setdefault('LMSTUDIO_TOTAL_TIMEOUT', '3600')
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    run([ffmpeg, '-version'])
    tools = ROOT / '.venv' / 'factory_tools'
    tools.mkdir(exist_ok=True)
    import shutil
    target = tools / 'ffmpeg.exe'
    if not target.exists():
        shutil.copy2(ffmpeg, target)
    env['PATH'] = str(tools) + os.pathsep + env.get('PATH', '')
    env['FFMPEG_BINARY'] = str(target)
    env['IMAGEIO_FFMPEG_EXE'] = str(target)
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', 8000))
        except OSError as exc:
            raise RuntimeError('Porta 8000 occupata. Chiudi il vecchio server con CTRL+C e riprova. Nessun processo e stato terminato.') from exc
    url = 'http://127.0.0.1:8000/static/index.html'
    print('Avvio console COMPLETA. Lascia aperta questa finestra.', flush=True)
    print('LM Studio deve essere acceso con server locale e modello caricato.', flush=True)
    process = subprocess.Popen([str(PYTHON), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'], cwd=ROOT, env=env)
    def open_when_ready():
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(120):
            if process.poll() is not None:
                return
            try:
                with opener.open(url, timeout=1) as response:
                    if response.status == 200:
                        webbrowser.open(url)
                        return
            except Exception:
                time.sleep(1)
        print('Browser non aperto: controlla gli errori del server. URL: ' + url, flush=True)
    threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        return process.wait()
    except KeyboardInterrupt:
        if process.poll() is None:
            process.terminate()
        return process.wait()


if __name__ == '__main__':
    try:
        sys.exit(main() or 0)
    except Exception as exc:
        print('\nAVVIO INTERROTTO: ' + str(exc), flush=True)
        sys.exit(1)
