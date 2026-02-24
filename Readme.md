# ⚡ Hateable

**A local, open-source alternative to Lovable / v0 — powered entirely by your Ollama models.**

No cloud. No API keys. No subscriptions. Just your machine and your imagination.

![Hateable Screenshot](https://placeholder.com/screenshot.png)

---

## ✨ Features

- 🏗️ **Build** — Describe an app in plain English, get a full React + Tailwind + Vite project
- ✏️ **Reprompt** — Iteratively refine any part of your generated app with natural language
- 🔧 **Auto-Fix** — One-click bug detection and repair pipeline using Playwright + LLM
- ➕ **Add Features** — Request new sections, components, or functionality
- 📦 **Download ZIP** — Export the full project to run anywhere
- 👀 **Live Preview** — Instant in-app preview with desktop / tablet / mobile viewports
- 📄 **Code View** — Live streaming code viewer with syntax highlighting
- 🔄 **Dual Model** — Separate models for idea refinement and code generation

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+
- [Ollama](https://ollama.ai) installed and running

### 1. Install Ollama models

```bash
# Fast refine model
ollama pull llama3.1:8b

# Best code generation model
ollama pull qwen2.5-coder:14b

# Or use smaller models for less VRAM:
ollama pull qwen2.5-coder:7b
```

### 2. Install & run

```bash
git clone https://github.com/your/hateable
cd hateable
pip3 install -r requirements.txt
python3 server.py
```

Then open: **http://localhost:7824**

---

## 🏗️ Architecture

```
hateable/
├── server.py          # Main server: HTTP :7824 + WebSocket :7825
├── agents/
│   ├── refiner.py     # Agent 1: turns raw idea → structured JSON spec
│   ├── builder.py     # Agent 2: generates React components from spec
│   └── tester.py      # Agent 3: Playwright browser testing
├── ui/
│   └── index.html     # Single-file frontend UI
├── production-ready/  # Generated projects live here
└── logs/              # Build logs
```

### Pipeline

```
User prompt
    → Refiner (LLM 1) → JSON spec with sections, colors, style
    → Builder  (LLM 2) → React + Tailwind + Vite project files
    → npm install
    → Vite dev server starts
    → Tester (Playwright) → browser tests
    → Fix loop (up to 3 attempts if errors found)
    → Live preview in UI
```

---

## 🎨 How It Works

### Reprompt
The **Reprompt** tab lets you chat with your generated project. Under the hood, the LLM reads the existing codebase and selectively modifies only the relevant component(s).

### Auto-Fix
The **Fix Bugs** button runs the full error detection pipeline:
1. `npm run build` to catch compile errors
2. Playwright to catch runtime / blank-page issues
3. LLM re-generates the broken component with full error context

### Add Feature
The **Feature** tab adds brand new components or capabilities. The LLM decides whether to modify an existing component or create a new one, then injects it into `App.jsx` automatically.

---

## 🔧 Configuration

Edit `server.py` to change defaults:

```python
DEFAULT_REFINE = "llama3.1:8b"        # Model for idea refinement
DEFAULT_BUILD  = "qwen2.5-coder:14b"  # Model for code generation
MAX_FIX        = 3                    # Max auto-fix attempts
DEV_PORT       = 5173                 # Vite dev server port
UI_PORT        = 7824                 # Hateable UI port
WS_PORT        = 7825                 # WebSocket port
OLLAMA_URL     = "http://localhost:11434"
```

---

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Good first issues:**
- Add more example prompts / quick-start chips
- Improve the icon sanitizer in `builder.py`
- Add more site type detectors in `refiner.py`
- Better error messages in the UI
- Dark/light theme toggle

---

## 📄 License

MIT — do whatever you want with it.

---

## 🙏 Acknowledgments

Built on top of:
- [Ollama](https://ollama.ai) — local LLM runtime
- [Vite](https://vitejs.dev) — lightning-fast React dev server
- [Tailwind CSS](https://tailwindcss.com) — utility-first styling
- [Framer Motion](https://www.framer.com/motion/) — animations
- [Playwright](https://playwright.dev) — browser automation testing
- [React Icons](https://react-icons.github.io/react-icons/) — icon library