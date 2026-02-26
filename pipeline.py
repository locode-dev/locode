#!/usr/bin/env python3
import sys, time, logging, subprocess, threading, webbrowser
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from agents.refiner import RefinerAgent
from agents.builder import BuilderAgent
from agents.tester  import TesterAgent
import atexit
import signal
import os   
import warnings
warnings.filterwarnings("ignore")

BASE_DIR     = Path(__file__).parent
IDEAS_DIR    = BASE_DIR / "ideas"
PROD_DIR     = BASE_DIR / "production-ready"
LOGS_DIR     = BASE_DIR / "logs"
OLLAMA_URL   = "http://localhost:11434"
REFINE_MODEL = "llama3.1:8b"
BUILD_MODEL  = "qwen2.5-coder:14b"
MAX_FIX      = 2
DEV_PORT     = 5173

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "pipeline.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger("pipeline")
active_proc = {"proc": None}


class IdeaFileHandler(FileSystemEventHandler):
    def __init__(self): self.processing = set()
    def on_created(self, event):  self._handle(event.src_path)
    def on_modified(self, event): self._handle(event.src_path)
    def _handle(self, path):
        p = Path(path)
        if p.suffix == ".txt" and p not in self.processing:
            time.sleep(0.5)
            self.processing.add(p)
            try: run_pipeline(p)
            finally: self.processing.discard(p)


def run_pipeline(idea_file: Path):
    log.info("=" * 60)
    log.info("🚀 PIPELINE STARTED")
    log.info("=" * 60)
    raw_idea = idea_file.read_text(encoding="utf-8").strip()
    if not raw_idea:
        log.warning("Idea file is empty. Skipping.")
        return
    log.info(f"💡 Idea: {raw_idea[:200]}...")

    log.info(f"\n🧠 AGENT 1 — Refining with {REFINE_MODEL}...")
    refined = RefinerAgent(OLLAMA_URL, REFINE_MODEL).refine(raw_idea)
    if not refined:
        log.error("Refiner failed.")
        return
    log.info("✅ Refined OK")

    project_name = idea_file.stem.replace(" ", "_").lower()
    project_dir  = PROD_DIR / project_name / "src"
    project_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"\n🏗️  AGENT 2 — Building with {BUILD_MODEL}...")
    builder = BuilderAgent(OLLAMA_URL, BUILD_MODEL, project_dir)
    if not builder.build(refined):
        log.error("Build failed.")
        return
    log.info(f"✅ Built at: {project_dir}")

    start_vite(project_dir)
    time.sleep(6)

    log.info("\n🧪 AGENT 3 — Testing...")
    tester = TesterAgent(project_dir, DEV_PORT)
    for attempt in range(1, MAX_FIX + 1):
        errors = tester.test()
        if not errors:
            log.info("✅ All tests passed!")
            break
        log.warning(f"⚠️  Attempt {attempt}/{MAX_FIX} — {len(errors)} issue(s):")
        for e in errors: log.warning(f"   • {e}")
        if attempt == MAX_FIX:
            log.warning("⚠️  Max attempts reached. Serving anyway.")
            break
        builder.fix(errors)

    write_readme(project_name, project_dir, raw_idea)

    def open_later():
        time.sleep(3)
        webbrowser.open(f"http://localhost:{DEV_PORT}")
        log.info(f"🖥️  Opened browser → http://localhost:{DEV_PORT}")
    threading.Thread(target=open_later, daemon=True).start()

    log.info("=" * 60)
    log.info(f"🎉 DONE!  http://localhost:{DEV_PORT}")
    log.info(f"   📁 Code: production-ready/{project_name}/src/")
    log.info("=" * 60)

active_proc = {"proc": None}


def stop_vite():
    proc = active_proc.get("proc")
    if not proc:
        return

    try:
        log.info("🛑 Stopping existing Vite process...")

        if os.name != "nt":
            # Kill full process group (macOS/Linux)
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            # Windows
            proc.terminate()

        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            log.warning("⚠ Force killing Vite...")
            if os.name != "nt":
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()

        log.info("   ✅ Vite stopped")

    except Exception as e:
        log.warning(f"   ⚠ Could not fully stop Vite: {e}")

    active_proc["proc"] = None

def start_vite(project_dir: Path):
    # Stop any running instance first
    if active_proc.get("proc"):
        stop_vite()
        time.sleep(1)

    log.info(f"🌐 Starting Vite on port {DEV_PORT}...")

    def run():
        try:
            if os.name != "nt":
                proc = subprocess.Popen(
                    ["npm", "run", "dev", "--", "--port", str(DEV_PORT), "--host"],
                    cwd=project_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    preexec_fn=os.setsid  # new process group
                )
            else:
                proc = subprocess.Popen(
                    ["npm", "run", "dev", "--", "--port", str(DEV_PORT), "--host"],
                    cwd=project_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )

            active_proc["proc"] = proc

            # Stream stdout
            for line in proc.stdout:
                line = line.strip()
                if line:
                    log.info(f"   [vite] {line}")

        except FileNotFoundError:
            log.error("❌ npm not found! Install Node.js: https://nodejs.org")
        except Exception as e:
            log.error(f"❌ Vite error: {e}")

    threading.Thread(target=run, daemon=True).start()


# ── Clean shutdown hooks ──────────────────────────────────────────────────────

def shutdown_backend():
    log.info("🛑 Backend shutting down...")
    stop_vite()


atexit.register(shutdown_backend)


def handle_signal(sig, frame):
    shutdown_backend()
    sys.exit(0)


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def write_readme(project_name, project_dir, raw_idea):
    (project_dir.parent / "README.md").write_text(
        f"# {project_name.replace('_',' ').title()}\n\n"
        f"## Idea\n{raw_idea}\n\n"
        f"## Run\n```bash\ncd src\nnpm install\nnpm run dev\n```\n"
    )


if __name__ == "__main__":
    for d in [IDEAS_DIR, PROD_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    log.info("🤖 Web Agent Pipeline — React Edition")
    log.info(f"   👁️  Watching : {IDEAS_DIR}")
    log.info(f"   📦 Output   : {PROD_DIR}")
    log.info(f"   🧠 Refiner  : {REFINE_MODEL}")
    log.info(f"   🏗️  Builder  : {BUILD_MODEL}")
    log.info(f"   🌐 Dev URL  : http://localhost:{DEV_PORT}")
    log.info("\nDrop a .txt file into ideas/ to start!")
    log.info("Types: tool, game, app, ecommerce, saas, restaurant,")
    log.info("       portfolio, blog, agency, startup, corporate\n")

    handler = IdeaFileHandler()
    observer = Observer()
    observer.schedule(handler, str(IDEAS_DIR), recursive=False)
    observer.start()
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        log.info("\n⛔ Stopping...")
        if active_proc["proc"]:
            try: active_proc["proc"].terminate()
            except: pass
        observer.stop()
    observer.join()