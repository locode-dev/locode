<div align="center">

# 🤝 Contributing to Locode

Thank you for contributing to Locode.

</div>

Locode is built on three principles:

1. **Fully local execution** — nothing leaves your machine
2. **Deterministic + repairable output** — every failure has a fix path
3. **Clean developer experience** — fast feedback loops, no magic

---

## 🛠 Development Setup

**Prerequisites:**
- Python 3.9+
- Node.js 20 LTS
- [Ollama](https://ollama.ai) running with at least one model

**Clone & Run:**

```bash
git clone https://github.com/locode-dev/locode
cd locode
npm install
pip3 install -r requirements.txt
python3 server.py
```

Open: `http://localhost:7824`

---

## 🧠 Agent Overview

```
User prompt
    │
    ▼
Refiner  ──▶  Builder  ──▶  Tester
```

| Agent | File | Responsibility |
|---|---|---|
| **Refiner** | `agents/refiner.py` | Classifies site type, enriches spec with LLM, produces `component_details` + `special_instructions` |
| **Builder** | `agents/builder.py` | Generates all React components, config files, handles the fix loop |
| **Tester** | `agents/tester.py` | Playwright headless tests — validates render, checks for real JS errors (not HMR noise) |

---

## 🗺 Codebase Map

```
locode/
├── server.py              # HTTP :7824, WebSocket :7825, all pipeline orchestration
├── agents/
│   ├── refiner.py         # Prompt refinement + site-type classification
│   ├── builder.py         # Code generation, extraction, sanitization, fix loop
│   └── tester.py          # Playwright browser testing
├── ui/
│   └── index.html         # Full frontend (single file — no build step)
├── electron/              # Electron shell for macOS DMG
│   └── main.cjs           # Cross-platform Electron main process
├── production-ready/      # Generated projects land here
├── scripts/               # Build helpers (build-mac.sh, build-win.bat, etc.)
└── assets/                # Icons (locode.icns, locode.ico, locode.png)
```

---

## ⚡ Key Concepts

### Intent classification (reprompt pipeline)

Every reprompt is classified before any LLM work happens:

| Intent | Signal | What happens |
|---|---|---|
| `patch` | "change the color / text / title…" | Surgical file edit → Vite HMR → done in ~2s, no test loop |
| `modify` | Generic update request | Targeted component rewrite → Vite restart → test loop |
| `feature` | "add a / create a / new section…" | New component created and injected into App.jsx |

`_classify_intent()` in `server.py` is pure keyword matching — no LLM call, no latency.

### Token tracking

`BuilderAgent.token_usage` accumulates `prompt_eval_count` + `eval_count` from every Ollama streaming response. `edone()` in `server.py` reads this and calculates cost comparisons (GPT-4o, Claude Sonnet, Lovable) for the savings popup shown in the UI.

### Tester noise filtering

`tester.py` distinguishes real JS errors from HMR noise. Only errors matching signals like `"is not defined"`, `"Cannot read properties"`, `"Failed to resolve import"` trigger the fix loop. Vite's own logs, React dev warnings, and network/CDN errors are ignored.

---

## 🔄 Pull Request Guidelines

- One feature or fix per PR
- No build artifacts committed
- Test with at least one Ollama model end-to-end
- Include screenshots for any UI changes

### What NOT to commit

```
dist/
dist-electron/
release/
node_modules/
production-ready/
build/
*.dmg  *.exe  *.pkg
ms-playwright/
bundled-node/
logs/
test_screenshot.png
```

---

## 🐛 Reporting Issues

Please include:

| Field | Example |
|---|---|
| OS + version | macOS 15.3 (arm64) |
| Python version | 3.11.4 |
| Node version | 20.11.0 |
| Ollama model(s) | refine: llama3.1:8b · build: qwen2.5-coder:14b |
| Full error logs | complete stack trace from terminal |
| Exact prompt used | the input that triggered the issue |
| Mode | first build / reprompt / feature / fix |

---

## 🧪 Testing Locally

Run a quick end-to-end test by running the app and building a simple prompt:

```bash
python3 server.py
# In browser: http://localhost:7824
# Prompt: "a simple todo list app"
# Verify: app builds, Vite starts, Playwright passes, savings popup appears
```

For Playwright-specific testing, Locode installs Chromium automatically on first run in dev mode. In packaged builds, Chromium must be bundled — see `build-mac.sh`.

---

## 📦 Building the DMG / EXE

```bash
# macOS
bash scripts/build-mac.sh

# Windows
scripts\build-win.bat
```

See `BUILD.md` for full packaging prerequisites, icon creation, and troubleshooting.