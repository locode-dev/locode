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

## 💻 Installation (macOS)

[![Download for macOS](https://img.shields.io/badge/⬇_Download_Locode-macOS_DMG-000000?style=for-the-badge&logo=apple&logoColor=white)](https://github.com/locode-dev/locode/releases/download/v1.0.0/Locode-v1.0.0-arm64.dmg)

1. Click the **Download** button above
2. Open [`Locode-v1.0.0-arm64.dmg`](https://github.com/locode-dev/locode/releases/download/v1.0.0/Locode-v1.0.0-arm64.dmg)
3. Drag **Locode** to your Applications folder
4. Make sure [Ollama](https://ollama.ai) is running
5. Open Locode and start building

> **First launch:** If macOS blocks the app ("Apple could not verify"):
> 1. Right-click (or Control-click) **Locode** in your Applications folder
> 2. Select **Open** from the menu
> 3. Click **Open** again in the warning dialog

Alternatively, go to **System Settings → Privacy & Security** and scroll down to click **Open Anyway**.

### 🧹 Full Uninstallation / Reset
To completely remove all Locode data (including generated projects and settings) on macOS, run this in Terminal:
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

Locode works with any open-source models supported by [Ollama](https://ollama.ai). For the best experience, we recommend using a code-specialized model for generation:

```bash
# Recommended models
ollama pull llama3.1:8b          # For idea refinement
ollama pull qwen2.5-coder:14b    # For React/Tailwind generation
```

*Note: You can use any model available in the Ollama library.*

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