# ⚡ Locode

**The first fully local AI app builder --- powered entirely by your
Ollama models.**

No cloud.\
No API keys.\
No subscriptions.\
Just your machine and your imagination.

------------------------------------------------------------------------

## ✨ What is Locode?

Locode is an open-source, fully local alternative to tools like Lovable
or v0 --- except everything runs on your machine using Ollama.

You describe an app in plain English.\
Locode generates a complete React + Tailwind + Vite project.\
It tests it. Fixes it. Iterates with you.

All locally.

------------------------------------------------------------------------

## ✨ Features

-   🏗️ Build full React + Tailwind + Vite projects
-   ✏️ Reprompt and iteratively refine components
-   🔧 Auto-Fix pipeline using Playwright + LLM
-   ➕ Feature injection via natural language
-   📦 Download generated project as ZIP
-   👀 Live preview (desktop / tablet / mobile)
-   📄 Live streaming code viewer
-   💻 Native macOS DMG support

------------------------------------------------------------------------

## 🚀 Run Locode (Developer Mode)

### Prerequisites

-   Python 3.9+
-   Node.js 20 LTS
-   Ollama installed and running

### Install models

    ollama pull llama3.1:8b
    ollama pull qwen2.5-coder:14b

### Run

    git clone https://github.com/locodehq/locode
    cd locode
    pip3 install -r requirements.txt
    python3 server.py

Open:

    http://localhost:7824

------------------------------------------------------------------------

## 🏗 Architecture

locode/ ├── server.py ├── agents/ ├── ui/ ├── electron/ ├──
production-ready/ └── logs/

------------------------------------------------------------------------

## 📄 License

MIT License.
