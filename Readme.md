<div align="center">

<img src="locode.png" alt="Locode Logo" width="100" />

# ⚡ Locode

**The first fully local AI app builder — powered entirely by your Ollama models.**

![License](https://img.shields.io/badge/license-MIT-22d3ee?style=flat-square)
![Python](https://img.shields.io/badge/python-3.9+-4ade80?style=flat-square&logo=python&logoColor=white)
![Node](https://img.shields.io/badge/node-20_LTS-4ade80?style=flat-square&logo=node.js&logoColor=white)
![Ollama](https://img.shields.io/badge/powered_by-Ollama-a78bfa?style=flat-square)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-22d3ee?style=flat-square)

*No cloud. No API keys. No subscriptions. Just your machine and your imagination.*

</div>

---

## ✨ What is Locode?

Locode is an open-source, fully local alternative to tools like Lovable or v0 — except everything runs on your machine using Ollama.

You describe an app in plain English → Locode generates a complete **React + Tailwind + Vite** project → It tests it → Fixes it → Iterates with you.

All locally. Always.

---

## 🏗️ Features

| Feature | Description |
|---|---|
| 🏗️ **Full Project Generation** | Build complete React + Tailwind + Vite projects from a plain-English description |
| ✏️ **Iterative Refinement** | Reprompt and refine components until they're exactly right |
| 🔧 **Auto-Fix Pipeline** | Playwright + LLM catch and fix errors automatically |
| ➕ **Feature Injection** | Add new features to existing projects via natural language |
| 📦 **ZIP Export** | Download your generated project as a ready-to-use ZIP |
| 👀 **Live Preview** | Real-time preview across desktop, tablet, and mobile |
| 📄 **Streaming Code Viewer** | Watch your code generate live |
| 💻 **Native macOS DMG** | Install as a native desktop app |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Node.js 20 LTS
- [Ollama](https://ollama.ai) installed and running

### 1. Pull the required models

```bash
ollama pull llama3.1:8b
ollama pull qwen2.5-coder:14b
```

### 2. Clone and install

```bash
git clone https://github.com/locode-dev/locode
cd locode
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

## 🏗 Architecture

```
locode/
├── server.py            # Main server entrypoint
├── agents/              # Refiner, Builder, Tester agents
├── ui/                  # Frontend interface
├── electron/            # macOS DMG packaging
├── production-ready/    # Generated project output
└── logs/                # Run logs
```

### Agent Pipeline

```
Refiner  ──▶  Builder  ──▶  Tester
refiner.py    builder.py    tester.py
```

| Agent | Role |
|---|---|
| **Refiner** | Classifies your idea, detects site type, enriches specs via LLM |
| **Builder** | Generates the full React + Tailwind + Vite project |
| **Tester** | Runs Playwright browser tests and validates visual output |

---

## 📄 License

[MIT](LICENSE) — free to use, modify, and distribute.

---

<div align="center">

⚡ Built with Ollama · React · Vite · Playwright

</div>