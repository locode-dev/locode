<div align="center">

<img src="assets/locode.png" alt="Locode Logo" width="100" />

# ⚡ Locode

**The first fully local AI app builder — powered entirely by your Ollama models.**

![License](https://img.shields.io/badge/license-MIT-22d3ee?style=flat-square)
![Python](https://img.shields.io/badge/python-3.9+-4ade80?style=flat-square&logo=python&logoColor=white)
![Node](https://img.shields.io/badge/node-20_LTS-4ade80?style=flat-square&logo=node.js&logoColor=white)
![Ollama](https://img.shields.io/badge/powered_by-Ollama-a78bfa?style=flat-square)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-22d3ee?style=flat-square)

*No cloud. No API keys. No subscriptions. Just your machine and your imagination.*

<br>

[![Download for macOS](https://img.shields.io/badge/⬇_Download_Locode-macOS_DMG-000000?style=for-the-badge&logo=apple&logoColor=white)](https://github.com/locode-dev/locode/releases/download/v1.0.0/Locode-v1.0.0-arm64.dmg)

**v1.0.0 · Apple Silicon (arm64)**

</div>

---

## ✨ What is Locode?

Locode is an open-source, fully local alternative to tools like Lovable or v0 — except everything runs on your machine using Ollama.

You describe an app in plain English → Locode generates a complete **React + Tailwind + Vite** project → It tests it → Fixes it → Iterates with you.

All locally. Always free.

---

## 🏗️ Features

| Feature | Description |
|---|---|
| 🏗️ **Full Project Generation** | Build complete React + Tailwind + Vite projects from a plain-English description |
| ✏️ **Smart Reprompt** | Three modes — patch (instant), modify (targeted), feature (new component) |
| 🧭 **Intent Classification** | Automatically routes your request: text/color tweaks skip the full rebuild cycle |
| 🔧 **Auto-Fix Pipeline** | Playwright + LLM catch and fix errors automatically |
| ➕ **Feature Injection** | Add new sections or features to existing projects via natural language |
| 📦 **ZIP Export** | Download your generated project as a ready-to-use ZIP |
| 👀 **Live Preview** | Real-time preview across desktop, tablet, and mobile |
| 📄 **Streaming Code Viewer** | Watch your code generate live, token by token |
| 💰 **Savings Calculator** | See how much you saved vs. ChatGPT, Claude API, and Lovable after every build |
| 💻 **Native macOS DMG** | Install and run as a native desktop app |

---

## 💻 Installation (macOS)

[![Download for macOS](https://img.shields.io/badge/⬇_Download_Locode-macOS_DMG-000000?style=for-the-badge&logo=apple&logoColor=white)](https://github.com/locode-dev/locode/releases/download/v1.0.0/Locode-v1.0.0-arm64.dmg)

1. Click the **Download** button above
2. Open [`Locode-v1.0.0-arm64.dmg`](https://github.com/locode-dev/locode/releases/download/v1.0.0/Locode-v1.0.0-arm64.dmg)
3. Drag **Locode** to your Applications folder
4. Make sure [Ollama](https://ollama.ai) is running with at least one model pulled
5. Open Locode and start building

> **First launch:** If macOS blocks the app ("Apple could not verify"):
> 1. Right-click (or Control-click) **Locode** in your Applications folder
> 2. Select **Open** from the menu
> 3. Click **Open** again in the warning dialog

Alternatively, go to **System Settings → Privacy & Security** and scroll down to click **Open Anyway**.

### 🧹 Full Uninstallation / Reset

To completely remove all Locode data (including generated projects and settings) on macOS:

```bash
rm -rf ~/Library/Application\ Support/locode*
```

*(You can also use the **Maintenance → Factory Reset** menu option inside the app.)*

---

## 🚀 Run from Source

### Prerequisites

- Python 3.9+
- Node.js 20 LTS
- [Ollama](https://ollama.ai) installed and running

### 1. Pull your preferred models

Locode works with any open-source model supported by [Ollama](https://ollama.ai). For the best results, use a code-specialised model for generation:

```bash
# Recommended setup
ollama pull llama3.1:8b          # Idea refinement (fast, low VRAM)
ollama pull qwen2.5-coder:14b    # React/Tailwind code generation (best quality)
```

You can mix and match — select different models for the **Refine** and **Build** stages inside the app. Any model in the Ollama library will work.

### 2. Clone and install

```bash
git clone https://github.com/locode-dev/locode
cd locode
npm install
pip3 install -r requirements.txt
```

### 3. Run

```bash
python3 server.py
```

### 4. Open in browser

```
http://localhost:7824
```

---

## ✏️ Reprompt Modes

Once an app is built, the toolbar gives you three ways to iterate:

| Tab | When to use | How it works |
|---|---|---|
| **Reprompt** | Change text, colors, layout, logic | Auto-classifies as `patch` (instant HMR) or `modify` (targeted rebuild) |
| **Feature** | Add a brand-new section or component | Always creates a new component matched to the existing visual style |
| **Fix Bugs** | Something looks broken | Runs the full auto-fix pipeline: npm build check → LLM fix → Playwright retest |

### Intent classification

The Reprompt tab automatically classifies your request so the right amount of work happens:

- **patch** — `"change the button color to blue"` → surgical file edit + Vite HMR. Done in ~2 seconds, no test loop.
- **modify** — `"redesign the hero section layout"` → targeted LLM rewrite of that component + Vite restart + test.
- **feature** — anything from the Feature tab → new component scaffolded and injected into App.jsx.

---

## 💰 Savings Calculator

After every build, Locode shows a popup comparing what the same token usage would have cost on paid APIs:

| Service | Pricing basis |
|---|---|
| ChatGPT (GPT-4o) | $5 input / $15 output per 1M tokens |
| Claude (Sonnet) | $3 input / $15 output per 1M tokens |
| Lovable | ~$40 per 1M tokens equivalent |
| **Locode** | **$0.00** |

A typical build uses 50k–150k tokens across the Refiner + Builder + Tester agents. The savings add up fast.

---

## 🏗 Architecture

```
locode/
├── server.py              # Main server — HTTP :7824, WebSocket :7825
├── agents/
│   ├── refiner.py         # Classifies idea, enriches spec via LLM
│   ├── builder.py         # Generates React + Tailwind + Vite project
│   └── tester.py          # Playwright browser tests + validation
├── ui/
│   └── index.html         # Frontend interface
├── electron/              # Electron wrapper for macOS DMG
├── production-ready/      # Generated project output directory
└── logs/                  # Run logs
```

### Agent Pipeline

```
User prompt
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Refiner  (refiner.py)                              │
│  • Keyword + LLM intent detection                   │
│  • Classifies site type (tool / game / app / saas…) │
│  • Produces detailed spec: description, features,   │
│    component details, color scheme, style           │
└────────────────────────┬────────────────────────────┘
                         │ enriched spec (JSON)
                         ▼
┌─────────────────────────────────────────────────────┐
│  Builder  (builder.py)                              │
│  • Generates App.jsx + all section components       │
│  • Streams each file live to the UI                 │
│  • Writes config (package.json, vite.config, CSS)   │
└────────────────────────┬────────────────────────────┘
                         │ project on disk
                         ▼
┌─────────────────────────────────────────────────────┐
│  Tester   (tester.py)                               │
│  • Waits for Vite dev server (port polling)         │
│  • Playwright headless Chromium: load, mount, check │
│  • Reports real JS errors only (filters HMR noise)  │
│  • On failure → Builder fix loop (up to MAX_FIX)    │
└─────────────────────────────────────────────────────┘
```

### Update Pipeline (Reprompt / Feature / Fix)

```
User reprompt
    │
    ▼
_classify_intent()          ← keyword-based, no LLM call
    │
    ├── patch   ──▶  _decide_targets() (existing only)
    │               _build_update_prompt() (surgical)
    │               write file → Vite HMR → done (~2s)
    │
    ├── modify  ──▶  _decide_targets() (existing only)
    │               _build_update_prompt() (preserve rest)
    │               write file → Vite restart → test loop
    │
    └── feature ──▶  _decide_targets() (may create new)
                    _build_update_prompt() (new component)
                    _inject_component_into_app()
                    Vite restart → test loop
```

---

## 📄 License

[MIT](LICENSE) — free to use, modify, and distribute.

---

<div align="center">

⚡ Built with Ollama · React · Vite · Playwright · Electron

</div>