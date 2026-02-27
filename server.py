#!/usr/bin/env python3
"""
WebForge Server  —  HTTP :7824  |  WebSocket :7825
- Dual model selection (refine + build)
- Auto-pull Ollama models if missing
- Stop/unload model immediately after each stage (VRAM conservation)
- Fix loop uses npm run build for real errors + full codebase context
"""
import atexit
import signal
import sys, json, asyncio, logging, threading, time, re, subprocess, os, urllib3
urllib3.disable_warnings()
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

try:
    import websockets
except ImportError:
    subprocess.run([sys.executable,"-m","pip","install","websockets",
                    "--break-system-packages","-q"])
    import websockets

sys.path.insert(0, str(Path(__file__).parent))
from agents.refiner  import RefinerAgent
from agents.builder  import BuilderAgent, set_stream_callback
from agents.tester   import TesterAgent, set_emit as set_tester_emit
import shutil

def _maybe_set_playwright_env():
    # If Electron didn't set them for some reason, try to infer from app bundle.
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") and os.environ.get("PLAYWRIGHT_NODEJS_PATH"):
        return

    # When packaged, the backend is typically:
    # /Applications/Locode.app/Contents/Resources/backend/locode-backend-v4
    exe = Path(sys.argv[0]).resolve()
    # .../Resources/backend -> .../Resources
    resources = exe.parent.parent

    pw = resources / "ms-playwright"
    node = resources / "node" / "bin" / "node"

    if pw.exists():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(pw))
        os.environ.setdefault("PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD", "1")

    if node.exists():
        os.environ.setdefault("PLAYWRIGHT_NODEJS_PATH", str(node))

_maybe_set_playwright_env()
def resolve_node_binaries():
    # Packaged mode
    if getattr(sys, "frozen", False):
        exe_path = Path(sys.argv[0]).resolve()
        resources_dir = exe_path.parent.parent  # backend → Resources

        node_bin_dir = resources_dir / "node" / "bin"

        npm_path = node_bin_dir / "npm"
        node_path = node_bin_dir / "node"

        if npm_path.exists() and node_path.exists():
            return str(npm_path), str(node_path)

    # Dev mode fallback
    return shutil.which("npm") or "npm", shutil.which("node") or "node"


NPM_BIN, NODE_BIN = resolve_node_binaries()

print("DEBUG: sys.executable =", sys.executable)
print("DEBUG: Using NPM_BIN  =", NPM_BIN)
print("DEBUG: Using NODE_BIN =", NODE_BIN)

# Ensure PATH includes bundled node
node_dir = str(Path(NODE_BIN).parent)
if node_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{node_dir}:{os.environ.get('PATH','')}"

if hasattr(sys, "_MEIPASS"):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent

print(f"DEBUG: BASE_DIR = {BASE_DIR}")
print(f"DEBUG: UI_DIR = {BASE_DIR / 'ui'}")
PROD_DIR = BASE_DIR / "production-ready"
LOGS_DIR = BASE_DIR / "logs"
OLLAMA_URL = "http://localhost:11434"
DEFAULT_REFINE = "llama3.1:8b"
DEFAULT_BUILD  = "qwen2.5-coder:14b"
MAX_FIX    = 3
DEV_PORT   = 5173
UI_PORT    = 7824
WS_PORT    = 7825

for d in [PROD_DIR, LOGS_DIR]: d.mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("server")

clients    = set()
MAIN_LOOP  = None
active_vite = {"proc": None, "stderr_lines": []}


# ── Broadcast helpers ─────────────────────────────────────────────────────────

def emit(msg: dict):
    if MAIN_LOOP is None: return
    data = json.dumps(msg, ensure_ascii=False)
    async def _s():
        dead = set()
        for ws in list(clients):
            try: await ws.send(data)
            except: dead.add(ws)
        clients.difference_update(dead)
    asyncio.run_coroutine_threadsafe(_s(), MAIN_LOOP)

def elog(lvl, txt):       emit({"type":"log",         "level":lvl,  "text":txt})
def estep(s, st):         emit({"type":"step",         "step":s,     "status":st})
def efile(n, sz, c=""):   emit({"type":"file",         "name":n,     "size":sz,   "content":c})
def edetect(t, s):        emit({"type":"detected",     "site_type":t,"strategy":s})
def eprog(lbl, pct):      emit({"type":"progress",     "step":lbl,   "pct":pct})
def edone(url, proj):     emit({"type":"done",         "url":url,    "project":proj})
def eerr(txt):            emit({"type":"error",        "text":txt})
def estream_start(fname): emit({"type":"stream_start", "file":fname})
def estream(fname, tok):  emit({"type":"stream",       "file":fname, "token":tok})
def estream_end(f, c):    emit({"type":"stream_end",   "file":f,     "content":c})


# ── Token streaming ───────────────────────────────────────────────────────────

_cur_stream = {"name": None, "buf": ""}

def on_token(token: str):
    if token.startswith("\x00START:"):
        fname = token[7:]
        _cur_stream["name"] = fname
        _cur_stream["buf"]  = ""
        estream_start(fname)
    elif token == "\x00END":
        fname = _cur_stream["name"]
        content = _cur_stream["buf"]
        estream_end(fname, content)
        _cur_stream["name"] = None
        _cur_stream["buf"]  = ""
    else:
        _cur_stream["buf"] += token
        estream(_cur_stream["name"] or "generating…", token)


# ── Ollama model management ───────────────────────────────────────────────────

def ensure_model(model: str) -> bool:
    """Check Ollama tags; pull model if missing. Returns True if ready."""
    import requests as req
    try:
        r = req.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        names = [m["name"] for m in r.json().get("models", [])]
        if any(model == n or model.split(":")[0] == n.split(":")[0] for n in names):
            elog("INFO", f"   ✅ Model ready: {model}")
            return True
    except Exception as e:
        elog("WARN", f"   Ollama check failed: {e}")

    elog("INFO", f"   📥 Pulling {model} from Ollama (first time only)…")
    try:
        r = req.post(f"{OLLAMA_URL}/api/pull",
                     json={"name": model}, stream=True, timeout=600)
        last_pct = -1
        for line in r.iter_lines():
            if not line: continue
            try:
                chunk = json.loads(line)
                status = chunk.get("status", "")
                if chunk.get("total"):
                    pct = int(chunk.get("completed", 0) / chunk["total"] * 100)
                    if pct != last_pct and pct % 10 == 0:
                        elog("INFO", f"   📥 {model}: {pct}%")
                        last_pct = pct
                if "success" in status:
                    elog("INFO", f"   ✅ {model} pulled!")
                    return True
            except: pass
        return True
    except Exception as e:
        elog("ERROR", f"   ❌ Pull failed: {e}")
        return False

def stop_model(model: str):
    """Unload model from VRAM immediately after use."""
    import requests as req
    try:
        req.post(f"{OLLAMA_URL}/api/generate",
                 json={"model": model, "keep_alive": 0}, timeout=8)
        elog("INFO", f"   🗑️  Unloaded {model}")
    except: pass

def ensure_node_deps(proj_dir: Path) -> bool:
    vite_bin = proj_dir / "node_modules" / ".bin" / (
        "vite.cmd" if os.name == "nt" else "vite"
    )

    if vite_bin.exists():
        return True

    elog("INFO", "📦 Installing dependencies (npm install)…")

    try:
        r = subprocess.run(
            [NPM_BIN, "install"],
            cwd=proj_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if r.returncode == 0:
            elog("INFO", "   ✅ npm install complete")
            return True
        elog("ERROR", f"   ❌ npm install failed:\n{r.stderr[:300]}")
        return False
    except Exception as e:
        elog("ERROR", f"   ❌ npm install crashed: {e}")
        return False
# ── Vite management ───────────────────────────────────────────────────────────

def start_vite(proj_dir: Path):
    """Kill old Vite, start fresh. Capture stdout+stderr separately."""
    if active_vite["proc"]:
        try: active_vite["proc"].terminate()
        except: pass
        time.sleep(1)
    active_vite["stderr_lines"] = []

    def _run():
        try:
            p = subprocess.Popen(
                [NPM_BIN, "run", "dev", "--", "--port", str(DEV_PORT), "--host"],
                cwd=proj_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            active_vite["proc"] = p

            def _stderr():
                for line in p.stderr:
                    l = line.strip()
                    if l:
                        active_vite["stderr_lines"].append(l)
                        if any(k in l for k in ["Error","error","failed","SyntaxError"]):
                            elog("WARN", f"   [vite] {l[:120]}")
            threading.Thread(target=_stderr, daemon=True).start()

            for line in p.stdout:
                l = line.strip()
                if l: elog("INFO", f"   [vite] {l}")
        except Exception as e:
            elog("ERROR", f"   Vite crashed: {e}")

    threading.Thread(target=_run, daemon=True).start()

def vite_stderr() -> str:
    lines = active_vite.get("stderr_lines", [])
    err = [l for l in lines if any(k in l for k in
        ["Error","error","SyntaxError","ReferenceError","TypeError",
         "Cannot find","is not defined","failed","plugin:vite"])]
    return "\n".join(err[-40:])


# ── UIBuilder: BuilderAgent subclass that emits to WebSocket ─────────────────

class UIBuilder(BuilderAgent):
    """Thin wrapper — overrides _on_write and _install_deps to emit UI events."""

    def _on_write(self, fname: str, sz: str, content: str):
        efile(fname, sz, content)

    def _install_deps(self) -> bool:
        estep("install", "active")
        eprog("npm install…", 60)
        elog("INFO", "📦 npm install…")
        try:
            r = subprocess.run(
                [NPM_BIN, "install"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if r.returncode == 0:
                estep("install", "done")
                eprog("Dependencies ready", 75)
                elog("INFO", "   ✅ npm install complete")
                return True
            estep("install", "error")
            elog("ERROR", f"   npm failed: {r.stderr[:200]}")
            return False
        except FileNotFoundError:
            estep("install", "error")
            elog("ERROR", f"   npm binary not found at: {NPM_BIN}")
            return False


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline(prompt: str, refine_model: str, build_model: str):
    set_stream_callback(on_token)
    set_tester_emit(emit)
    try:
        elog("INFO", "━" * 40)
        elog("INFO", f"💡 {prompt[:90]}")
        elog("INFO", f"🧠 Refine: {refine_model}   🏗️  Build: {build_model}")
        elog("INFO", "━" * 40)

        # ── Stage 1: Ensure refine model, refine prompt ───────────────────────
        eprog("Checking refine model…", 3)
        if not ensure_model(refine_model):
            eerr(f"Cannot load refine model: {refine_model}"); return

        estep("refine", "active")
        eprog("Refining idea…", 8)
        elog("INFO", f"🧠 Agent 1 — {refine_model}")

        refiner = RefinerAgent(OLLAMA_URL, refine_model)
        refined = refiner.refine(prompt)
        if not refined:
            eerr("Refiner failed — is Ollama running?"); return

        estep("refine", "done")
        try:
            s = json.loads(refined)
            edetect(s.get("site_type", "?"), s.get("strategy", "?"))
            elog("INFO", f"   type={s.get('site_type')}  strategy={s.get('strategy')}")
        except: pass

        # ── Stop refine model immediately ─────────────────────────────────────
        stop_model(refine_model)

        # ── Stage 2: Ensure build model, generate code ────────────────────────
        eprog("Checking build model…", 18)
        if not ensure_model(build_model):
            eerr(f"Cannot load build model: {build_model}"); return

        spec = {}
        try: spec = json.loads(refined)
        except: pass

        raw_name = spec.get("project_name",
                   re.sub(r"[^a-z]", "", prompt[:15].lower()))
        pname = re.sub(r"[^a-z0-9]", "", raw_name)[:20] or "project"
        proj_dir = PROD_DIR / pname
        proj_dir.mkdir(parents=True, exist_ok=True)
        elog("INFO", f"   📁 {proj_dir}")

        estep("build", "active")
        eprog("Generating components…", 22)
        elog("INFO", f"🏗️  Agent 2 — {build_model}")

        builder = UIBuilder(OLLAMA_URL, build_model, proj_dir)
        if not builder.build(refined):
            eerr("Build failed"); return

        estep("build", "done")
        eprog("Components ready", 55)

        # ── Stop build model after generation ─────────────────────────────────
        stop_model(build_model)

        # ── Stage 3: Start Vite ───────────────────────────────────────────────
        estep("serve", "active")
        eprog("Starting Vite…", 72)
        elog("INFO", f"🌐 Starting Vite on :{DEV_PORT}")
        if not ensure_node_deps(proj_dir):
            eerr("Failed to install dependencies"); return
        start_vite(proj_dir)
        time.sleep(8)  # Give Vite time to compile

        # ── Stage 4: Test + Fix loop ──────────────────────────────────────────
        estep("test", "active")
        eprog("Running tests…", 80)
        elog("INFO", "🧪 Agent 3 — Playwright")
        emit({"type": "test_start"})

        tester = TesterAgent(proj_dir, DEV_PORT)

        for attempt in range(1, MAX_FIX + 2):
            elog("INFO", f"   🔬 Test run #{attempt}")
            emit({"type": "test_run", "attempt": attempt})

            errors = tester.test()

            if not errors:
                elog("INFO", "   🎉 All tests passed!")
                estep("test", "done")
                break

            if attempt > MAX_FIX:
                elog("WARN", f"   ⚠ Max fix attempts ({MAX_FIX}) reached — writing guaranteed fallbacks")
                # Nuclear option: replace every still-broken component with a safe
                # working fallback so the user sees SOMETHING instead of blank page.
                from agents.builder import _safe_component
                for fpath, src in list(builder.built_files.items()):
                    if not (fpath.startswith("src/components/") and fpath.endswith(".jsx")):
                        continue
                    comp_name = fpath.split("/")[-1].replace(".jsx", "")
                    fp = proj_dir / fpath
                    # Only overwrite if the file is tiny (thin wrapper) or
                    # the last Vite build still failed
                    if len(src.strip()) < 400 or npm_errors.strip():
                        safe = _safe_component(comp_name)
                        fp.write_text(safe, encoding="utf-8")
                        builder.built_files[fpath] = safe
                        elog("WARN", f"   🛟 Safe fallback written → {fpath}")
                estep("test", "done")
                break

            # Collect real error context: npm build + Vite stderr
            npm_errors = builder._npm_build_errors()
            vs_errors  = vite_stderr()
            all_errors = "\n".join(errors) + "\n" + npm_errors + "\n" + vs_errors

            elog("INFO", f"   📋 npm build output:\n{npm_errors[:300] or '  (none)'}")

            emit({"type": "test_fixing", "attempt": attempt,
                  "errors": errors[:5]})
            elog("INFO", f"   🔧 Fixing (attempt {attempt}/{MAX_FIX})…")

            # Reload build model for fix pass
            if not ensure_model(build_model):
                elog("WARN", "   Cannot load build model for fix — skipping")
                break

            builder.fix_with_errors(all_errors)
            stop_model(build_model)

            # Restart Vite so it recompiles
            elog("INFO", "   🔄 Restarting Vite…")
            if not ensure_node_deps(proj_dir):
                eerr("Dependency install failed")
                return
            start_vite(proj_dir)
            time.sleep(8)

        # ── Done ──────────────────────────────────────────────────────────────
        url = f"http://localhost:{DEV_PORT}"
        estep("serve", "done")
        eprog("Done!", 100)
        elog("INFO", f"🎉 Live at {url}")
        edone(url, pname)

    except Exception as e:
        eerr(f"Pipeline error: {e}")
        log.exception("Pipeline error")
    finally:
        set_stream_callback(None)


# ── Project listing + file reading ───────────────────────────────────────────

def list_projects() -> list:
    """Return all projects in production-ready/ with metadata."""
    projects = []
    if not PROD_DIR.exists():
        return projects
    for d in sorted(PROD_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        pkg = d / "package.json"
        title = d.name
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text())
                title = data.get("name", d.name)
            except: pass
        # Count source files
        src_files = list((d / "src").rglob("*.jsx")) + list((d / "src").rglob("*.css")) if (d / "src").exists() else []
        projects.append({
            "name": d.name,
            "title": title,
            "mtime": int(d.stat().st_mtime),
            "file_count": len(src_files),
        })
    return projects


def get_project_files(proj_name: str) -> dict:
    """Read all source files from a project directory, return as {path: content}."""
    proj_dir = PROD_DIR / proj_name
    if not proj_dir.exists():
        return {}
    files = {}
    important = ["src/App.jsx", "src/main.jsx", "src/index.css",
                 "index.html", "package.json", "vite.config.js", "tailwind.config.js"]
    # First add important files in order
    for rel in important:
        fp = proj_dir / rel
        if fp.exists():
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
                sz = f"{len(content)//1024:.1f}KB" if len(content) >= 1024 else f"{len(content)}B"
                files[rel] = {"content": content, "size": sz}
            except: pass
    # Then component files
    comp_dir = proj_dir / "src" / "components"
    if comp_dir.exists():
        for fp in sorted(comp_dir.glob("*.jsx")):
            rel = f"src/components/{fp.name}"
            if rel not in files:
                try:
                    content = fp.read_text(encoding="utf-8", errors="replace")
                    sz = f"{len(content)//1024:.1f}KB" if len(content) >= 1024 else f"{len(content)}B"
                    files[rel] = {"content": content, "size": sz}
                except: pass
    return files


# ── Update pipeline ───────────────────────────────────────────────────────────

def _classify_intent(prompt: str) -> str:
    """
    Keyword-based intent classification — no LLM call needed, instant.
    Returns:
      'patch'  — tiny change: text / color / style / typo
      'feature'— explicit new section / feature / page requested
      'modify' — anything else (default: update existing component)
    """
    pl = prompt.lower()

    # Explicit NEW thing requested
    create_kw = [
        "add a ", "add an ", "add new ", "create a ", "create an ",
        "new section", "new feature", "new component", "new page",
        "new tab", "new button", "new card", "new block",
        "include a ", "build a ", "implement a ", "introduce a ",
    ]
    if any(k in pl for k in create_kw):
        return "feature"

    # Tiny surgical change — text / color / style / spelling
    patch_kw = [
        "change the text", "change the color", "change the colour",
        "change the title", "change the heading", "change the label",
        "change the button text", "change the background",
        "update the text", "update the color", "update the colour",
        "rename ", "make it ", "set the color", "set background",
        "font size", "font color", "change font",
        "replace the text", "fix the text", "fix typo",
        "spelling", "lighter", "darker", "bigger text", "smaller text",
        "make the text", "make the color", "make the background",
    ]
    if any(k in pl for k in patch_kw):
        return "patch"

    return "modify"


def _decide_targets(update_prompt: str, components: list, codebase_ctx: str,
                    build_model: str, intent: str = "modify") -> list:
    """
    Ask the LLM which component(s) to touch. Intent biases the decision:
      patch/modify → must return an EXISTING component name
      feature      → may return a new PascalCase name
    """
    import requests as req

    comp_list = ", ".join(components) if components else "(none)"

    if intent == "feature":
        bias = (
            "The user wants to ADD something new. You may return a new PascalCase "
            "component name if no existing component is appropriate."
        )
    else:
        # patch or modify: must stay in existing components
        bias = (
            "The user wants to MODIFY existing UI. You MUST return only names from "
            "the existing component list. Do NOT invent new names."
        )

    system = (
        "You are a JSON API. Output ONLY a raw JSON array of strings. "
        'No explanation, no markdown, no preamble. Example: ["Hero", "Features"]'
    )
    user = (
        f"Existing components: {comp_list}\n\n"
        f"User request: {update_prompt}\n\n"
        f"Rule: {bias}\n\n"
        f"Codebase:\n{codebase_ctx[:900]}\n\n"
        "Which component(s) to change? JSON array only:"
    )

    try:
        r = req.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model":   build_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                "stream":  False,
                "options": {"temperature": 0.0, "num_predict": 150},
            },
            timeout=45,
        )
        r.raise_for_status()
        raw = r.json()["message"]["content"].strip()
        # Strip markdown fences if model added them
        raw = re.sub(r"```[a-z]*\s*", "", raw).replace("```", "").strip()
        # Find the JSON array — try full parse first, then regex
        try:
            arr = json.loads(raw)
            if isinstance(arr, list):
                names = arr
            else:
                raise ValueError("not a list")
        except Exception:
            m = re.search(r'\[([^\]]+)\]', raw)
            names = json.loads(f"[{m.group(1)}]") if m else []
        result = [n.strip() for n in names if isinstance(n, str) and n.strip()]
        log.info(f"   _decide_targets → {result} (intent={intent})")
        return result
    except Exception as e:
        log.warning(f"   _decide_targets failed: {e}")
    return []


def _build_update_prompt(component_name: str, existing_code: str,
                         update_request: str, codebase_ctx: str,
                         is_new: bool, intent: str = "modify") -> str:
    """
    Build an LLM prompt tuned to the intent:
      patch   — surgical: change only specific text/color/value, no restructuring
      modify  — meaningful update: change layout/logic but preserve the rest
      feature — new component that matches existing visual style
    """
    import textwrap as tw

    if is_new:
        return tw.dedent(f"""\
            Create a NEW React component called '{component_name}'.

            USER REQUEST: {update_request}

            EXISTING CODEBASE — match this style exactly (colors, fonts, design language):
            {codebase_ctx[:2000]}

            Requirements:
            - Export default function {component_name}()
            - Mirror the exact color scheme and visual style of the existing components above
            - framer-motion animations, Tailwind CSS, react-icons/fi
            - Real specific content — no placeholder text
            - Outermost element must have an explicit dark background
            - Output ONLY the complete JSX starting with import statements
            """)

    if intent == "patch":
        # Surgical change — give full existing code so LLM sees exactly what to touch
        return tw.dedent(f"""\
            Make this SMALL change to the '{component_name}' React component:

            CHANGE: {update_request}

            CURRENT FULL CODE (change ONLY what is described above, nothing else):
            {existing_code}

            STRICT RULES:
            - Change ONLY what is explicitly asked — do not restructure, rename, or restyle anything else
            - Keep every import, every function, every className unchanged unless the request mentions it
            - Do not add new features, animations, or sections not in the request
            - Export default function {component_name}()
            - Output the COMPLETE updated JSX starting with import statements
            """)

    # intent == "modify" — meaningful change, preserve everything else
    return tw.dedent(f"""\
        Update the '{component_name}' component as described.

        REQUEST: {update_request}

        CURRENT CODE (read this carefully — implement the request, preserve everything else):
        {existing_code}

        OTHER PROJECT FILES (context only — do NOT change these):
        {codebase_ctx[:1200]}

        RULES:
        - Implement the requested changes fully
        - Preserve ALL existing functionality, content, and styling not mentioned in the request
        - Do not add unrelated features or change the visual design of untouched sections
        - Export default function {component_name}()
        - Output the COMPLETE updated JSX starting with import statements
        """)


def run_update_pipeline(proj_name: str, update_prompt: str, build_model: str, intent_override: str = ""):
    """
    Load an existing project, decide which components to change, re-generate
    each one through the standard builder._gen() → _write_one() pipeline,
    then test and fix exactly like a fresh build.
    """
    set_stream_callback(on_token)
    set_tester_emit(emit)

    proj_dir = PROD_DIR / proj_name
    if not proj_dir.exists():
        eerr(f"Project not found: {proj_name}"); return

    try:
        elog("INFO", "━" * 40)
        elog("INFO", f"✏️  Updating: {proj_name}")
        elog("INFO", f"📝 Request: {update_prompt[:80]}")
        elog("INFO", f"🏗️  Model: {build_model}")
        elog("INFO", "━" * 40)

        # ── Step 1: Load all existing files into builder ──────────────────────
        estep("refine", "active")
        eprog("Loading project…", 5)

        builder = UIBuilder(OLLAMA_URL, build_model, proj_dir)

        # Populate built_files from disk — builder needs this for context + fix loop
        file_data = get_project_files(proj_name)
        for rel, info in file_data.items():
            builder.built_files[rel] = info["content"]
            # Emit to UI so the file sidebar populates
            efile(rel, info["size"], info["content"])

        comp_dir   = proj_dir / "src" / "components"
        components = sorted(f.stem for f in comp_dir.glob("*.jsx")) if comp_dir.exists() else []
        elog("INFO", f"   📂 Loaded {len(file_data)} files | Components: {components}")

        estep("refine", "done")
        eprog("Analysing request…", 15)

        # ── Step 2: Load model + decide which components to touch ─────────────
        if not ensure_model(build_model):
            eerr(f"Cannot load build model: {build_model}"); return

        codebase_ctx = builder._build_codebase_context()

        estep("build", "active")
        eprog("Deciding targets…", 22)

        # Classify intent — use frontend override if provided, else auto-classify
        intent = intent_override if intent_override in ("patch", "modify", "feature")                  else _classify_intent(update_prompt)
        elog("INFO", f"   🧭 Intent: {intent}")

        targets = _decide_targets(update_prompt, components, codebase_ctx, build_model, intent)
        targets = [t for t in targets if re.match(r"^[A-Z][A-Za-z0-9_]*$", t)]

        # For patch/modify: reject any invented new names — LLM must pick existing ones
        if intent != "feature":
            targets = [t for t in targets if t in components]

        if not targets:
            pl = update_prompt.lower()
            # 1. Component name mentioned directly in prompt
            for comp in components:
                if comp.lower() in pl:
                    targets = [comp]; break
            # 2. Semantic keyword → component mapping
            if not targets:
                sem = [
                    (["hero","banner","header","headline","title","cta button","main button"], ["Hero"]),
                    (["nav","navbar","menu","link","navigation"],                              ["Navbar"]),
                    (["feature","benefit","service","card","grid"],                           ["Features"]),
                    (["about","story","mission","team","who we"],                             ["About"]),
                    (["price","pricing","plan","tier","subscription"],                        ["Pricing"]),
                    (["contact","form","email","reach","touch"],                              ["Contact"]),
                    (["footer","copyright","social link","bottom"],                           ["Footer"]),
                    (["testimonial","review","quote","customer"],                             ["Testimonials"]),
                    (["gallery","image","photo","portfolio item"],                            ["Gallery"]),
                    (["faq","question","answer","accordion"],                                 ["FAQ"]),
                ]
                for kws, cands in sem:
                    if any(k in pl for k in kws):
                        matched = [c for c in cands if c in components]
                        if matched:
                            targets = [matched[0]]; break
            # 3. For feature intent — generate a new name from the prompt
            if not targets and intent == "feature":
                words = [w.strip(".,!?") for w in update_prompt.split()
                         if w[0].isupper() and len(w) > 3]
                new_name = words[0] if words else "NewSection"
                targets = [new_name]
                elog("INFO", f"   ➕ Feature: creating new component {new_name}")
            # 4. Last resort — first component (not largest, that was wrong)
            if not targets and components:
                targets = [components[0]]
                elog("WARN", f"   Could not infer target — defaulting to: {targets[0]}")
            elif not targets:
                eerr("No components found in project"); return

        elog("INFO", f"   🎯 Targets: {targets}")

        # ── Step 3: Generate each target component ────────────────────────────
        updated_count = 0
        pct_per_comp  = max(1, 30 // len(targets))   # divide build progress across targets

        for i, comp_name in enumerate(targets):
            fpath    = f"src/components/{comp_name}.jsx"
            is_new   = comp_name not in components
            existing = builder.built_files.get(fpath, "")

            if is_new:
                elog("INFO", f"   ➕ Creating new component: {comp_name}")
            else:
                elog("INFO", f"   ✏️  Updating: {fpath}")

            eprog(f"Generating {comp_name}…", 25 + i * pct_per_comp)

            prompt = _build_update_prompt(
                comp_name, existing, update_prompt, codebase_ctx, is_new, intent
            )

            # _gen() handles: streaming to UI, token emission, extraction, raw output caching
            new_code = builder._gen(comp_name, prompt)

            if not new_code:
                elog("WARN", f"   LLM returned nothing for {comp_name} — skipping")
                continue

            # _write_one() handles: _extract_valid_component, _sanitize_jsx,
            # built_files update, disk write, UI file event via _on_write
            builder._write_one(fpath, new_code)
            updated_count += 1
            elog("INFO", f"   ✓ {fpath} written")

            # If it's a new component, add it to App.jsx imports/rendering
            if is_new:
                _inject_component_into_app(builder, proj_dir, comp_name)

        if updated_count == 0:
            eerr("No components were updated — LLM may have failed to generate valid JSX")
            return

        stop_model(build_model)

        estep("build", "done")
        eprog("Components updated", 58)
        elog("INFO", f"   ✅ {updated_count}/{len(targets)} component(s) updated")

        # ── Step 4: Vite hot-reload or restart ────────────────────────────────
        estep("serve", "active")
        if intent == "patch":
            # Vite HMR picks up file changes automatically — no restart needed
            # Just wait a moment for HMR to propagate
            elog("INFO", "⚡ Patch change — Vite HMR will reload automatically")
            eprog("Hot reloading…", 70)
            time.sleep(2)
            estep("serve", "done")
            estep("test", "done")
            eprog("Done!", 100)
            url = f"http://localhost:{DEV_PORT}"
            elog("INFO", f"✅ Patch applied → {url}")
            edone(url, proj_name, builder)
            return
        else:
            eprog("Restarting Vite…", 65)
            elog("INFO", "🌐 Restarting Vite…")
            if not ensure_node_deps(proj_dir):
                eerr("Dependency install failed")
                return
            start_vite(proj_dir)
            wait_for_vite(35)

        # ── Step 5: Test + fix loop ────────────────────────────────────────────
        estep("test", "active")
        eprog("Testing…", 75)
        elog("INFO", "🧪 Testing updated build…")
        emit({"type": "test_start"})

        tester = TesterAgent(proj_dir, DEV_PORT)
        npm_errors = ""

        for attempt in range(1, MAX_FIX + 2):
            elog("INFO", f"   🔬 Test run #{attempt}")
            emit({"type": "test_run", "attempt": attempt})

            errors = tester.test()

            if not errors:
                elog("INFO", "   🎉 All tests passed!")
                estep("test", "done")
                break

            if attempt > MAX_FIX:
                elog("WARN", f"   ⚠ Max fix attempts reached — applying safe fallbacks")
                from agents.builder import _safe_component
                for fpath_s, src in list(builder.built_files.items()):
                    if not (fpath_s.startswith("src/components/") and fpath_s.endswith(".jsx")):
                        continue
                    comp_name_s = fpath_s.split("/")[-1].replace(".jsx", "")
                    if len(src.strip()) < 400 or npm_errors.strip():
                        safe = _safe_component(comp_name_s)
                        (proj_dir / fpath_s).write_text(safe, encoding="utf-8")
                        builder.built_files[fpath_s] = safe
                        elog("WARN", f"   🛟 Safe fallback → {fpath_s}")
                estep("test", "done")
                break

            npm_errors = builder._npm_build_errors()
            vs_errors  = vite_stderr()
            all_errors = "\n".join(errors) + "\n" + npm_errors + "\n" + vs_errors

            elog("INFO", f"   📋 npm build:\n{npm_errors[:250] or '  (none)'}")
            emit({"type": "test_fixing", "attempt": attempt, "errors": errors[:5]})
            elog("INFO", f"   🔧 Fixing attempt {attempt}/{MAX_FIX}…")

            if not ensure_model(build_model):
                elog("WARN", "   Cannot reload build model — skipping fix")
                break

            builder.fix_with_errors(all_errors)
            stop_model(build_model)

            elog("INFO", "   🔄 Restarting Vite after fix…")
            if not ensure_node_deps(proj_dir):
                eerr("Dependency install failed")
                return
            start_vite(proj_dir)
            time.sleep(8)

        # ── Done ──────────────────────────────────────────────────────────────
        url = f"http://localhost:{DEV_PORT}"
        estep("serve", "done")
        eprog("Done!", 100)
        elog("INFO", f"🎉 Updated → {url}")
        edone(url, proj_name, builder)

    except Exception as e:
        eerr(f"Update error: {e}")
        log.exception("Update pipeline error")
    finally:
        set_stream_callback(None)


def _inject_component_into_app(builder, proj_dir: Path, comp_name: str):
    """
    When a new component is created, add it to App.jsx so it renders.
    Adds an import line and a <CompName /> tag inside the main div.
    Only modifies App.jsx — safe no-op if the component is already referenced.
    """
    app_path = proj_dir / "src" / "App.jsx"
    if not app_path.exists():
        return

    app_code = app_path.read_text(encoding="utf-8")

    # Skip if already imported
    if f"import {comp_name}" in app_code:
        return

    try:
        # Add import after the last existing import line
        last_import = max(
            (i for i, l in enumerate(app_code.splitlines()) if l.strip().startswith("import")),
            default=0
        )
        lines = app_code.splitlines()
        lines.insert(last_import + 1, f"import {comp_name} from './components/{comp_name}'")

        new_app = "\n".join(lines)

        # Add <CompName /> just before </div> of the main wrapper (last closing div)
        # Find last </div> and insert before it
        insert_tag = f"      <{comp_name} />\n"
        last_div   = new_app.rfind("</div>")
        if last_div != -1:
            new_app = new_app[:last_div] + insert_tag + new_app[last_div:]

        app_path.write_text(new_app, encoding="utf-8")
        builder.built_files["src/App.jsx"] = new_app
        sz = f"{len(new_app)//1024:.1f}KB" if len(new_app) >= 1024 else f"{len(new_app)}B"
        efile("src/App.jsx", sz, new_app)
        log.info(f"   ✓ Injected {comp_name} into App.jsx")
    except Exception as e:
        log.warning(f"   _inject_component_into_app failed: {e}")


# ── WebSocket handler ─────────────────────────────────────────────────────────

async def ws_handler(websocket, path=None):
    clients.add(websocket)
    log.info(f"WS connected ({len(clients)})")
    try:
        await websocket.send(json.dumps({
            "type": "log", "level": "INFO",
            "text": "✅ WebForge connected — enter a prompt and click Build"
        }))
        async for raw in websocket:
            try:
                msg = json.loads(raw)
                if msg.get("type") == "build":
                    p  = msg.get("prompt", "").strip()
                    rm = msg.get("refine_model", DEFAULT_REFINE)
                    bm = msg.get("build_model",  DEFAULT_BUILD)
                    if p:
                        threading.Thread(
                            target=run_pipeline, args=(p, rm, bm), daemon=True
                        ).start()
                elif msg.get("type") == "update":
                    proj   = msg.get("project", "").strip()
                    p      = msg.get("prompt", "").strip()
                    bm     = msg.get("build_model", DEFAULT_BUILD)
                    # Frontend can override intent (e.g. feature tab always sets "feature")
                    intent = msg.get("intent", "")  # "" = auto-classify in server
                    if proj and p:
                        threading.Thread(
                            target=run_update_pipeline, args=(proj, p, bm, intent), daemon=True
                        ).start()
            except json.JSONDecodeError: pass
    except websockets.exceptions.ConnectionClosed: pass
    finally:
        clients.discard(websocket)
        log.info(f"WS disconnected ({len(clients)})")


# ── HTTP handler ──────────────────────────────────────────────────────────────

class UIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(BASE_DIR / "ui"), **k)
    def log_message(self, *a): pass
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
    def do_GET(self):
        if self.path == "/projects":
            data = json.dumps(list_projects()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        elif self.path.startswith("/files/"):
            proj_name = self.path[7:].strip("/")
            files = get_project_files(proj_name)
            data = json.dumps(files).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        else:
            # Disable caching so Electron always gets fresh index.html
            if self.path in ("/", "/index.html", "") or self.path.endswith(".html"):
                self.send_response(200)
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
            super().do_GET()
    def do_POST(self):
        if self.path == "/build":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            threading.Thread(
                target=run_pipeline,
                args=(body.get("prompt",""),
                      body.get("refine_model", DEFAULT_REFINE),
                      body.get("build_model",  DEFAULT_BUILD)),
                daemon=True
            ).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        elif self.path == "/upload-project":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            name = body.get("name", "imported")
            files = body.get("files", {})
            
            # Sanitize project name
            pname = re.sub(r"[^a-z0-9]", "", name.lower())[:20] or "imported"
            proj_dir = PROD_DIR / pname
            proj_dir.mkdir(parents=True, exist_ok=True)
            
            # Write files to disk
            for rel_path, content in files.items():
                fp = proj_dir / rel_path
                fp.parent.mkdir(parents=True, exist_ok=True)
                try:
                    fp.write_text(content, encoding="utf-8")
                except Exception as e:
                    log.error(f"Failed to write {rel_path}: {e}")
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok":True, "project": pname}).encode())
        elif self.path == "/update":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            threading.Thread(
                target=run_update_pipeline,
                args=(body.get("project",""),
                      body.get("prompt",""),
                      body.get("build_model", DEFAULT_BUILD)),
                daemon=True
            ).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

def start_http():
    try:
        httpd = HTTPServer(("127.0.0.1", UI_PORT), UIHandler)
        print(f"HTTP server listening on 127.0.0.1:{UI_PORT}")
        httpd.serve_forever()
    except Exception as e:
        print(f"HTTP server failed: {e}")
# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()
    threading.Thread(target=start_http, daemon=True).start()
    print(f"\n{'━'*46}")
    print(f"  ⚡ Locode v1.0.0 Starting...")
    print(f"  ⚡ UI Server   →  http://127.0.0.1:{UI_PORT}")
    print(f"  🔌 WebSocket   →  ws://127.0.0.1:{WS_PORT}")
    print(f"  🧠 Refine      :  {DEFAULT_REFINE}")
    print(f"  🏗️  Build       :  {DEFAULT_BUILD}")
    print(f"  📝 Local development mode")
    print(f"{'━'*46}\n")
    async with websockets.serve(ws_handler, "127.0.0.1", WS_PORT):
        await asyncio.Future()

        import atexit
import signal

def shutdown_all():
    print("\n🛑 Shutting down Locode backend...")

    # Kill Vite
    if active_vite.get("proc"):
        try:
            active_vite["proc"].terminate()
            active_vite["proc"].wait(timeout=5)
            print("   ✅ Vite stopped")
        except:
            pass

    # Unload models (best effort)
    try:
        stop_model(DEFAULT_REFINE)
        stop_model(DEFAULT_BUILD)
        print("   ✅ Ollama models unloaded")
    except:
        pass

atexit.register(shutdown_all)

def handle_signal(sig, frame):
    shutdown_all()
    sys.exit(0)

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⛔ Stopped.")
        if active_vite["proc"]:
            try: active_vite["proc"].terminate()
            except: pass