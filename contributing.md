# 🤝 Contributing to Locode

Thank you for contributing to Locode.

Locode is built on three principles:

1.  Fully local execution
2.  Deterministic + repairable output
3.  Clean developer experience

------------------------------------------------------------------------

## 🛠 Development Setup

Prerequisites:

-   Python 3.9+
-   Node.js 20 LTS
-   Ollama running

Clone & Run:

    git clone https://github.com/locode-dev/locode
    cd locode
    pip3 install -r requirements.txt
    python3 server.py

Open:

    http://localhost:7824

------------------------------------------------------------------------

## 🧠 Agent Overview

Refiner → Builder → Tester

agents/refiner.py\
agents/builder.py\
agents/tester.py

------------------------------------------------------------------------

## 🔄 Pull Request Guidelines

-   One feature per PR
-   No build artifacts
-   Test with at least one Ollama model
-   Include screenshots for UI changes

Do NOT commit:

-   dist/
-   dist-electron/
-   node_modules/
-   Playwright browsers
-   DMG files

------------------------------------------------------------------------

## 🐛 Reporting Issues

Include:

-   OS + version
-   Python version
-   Node version
-   Ollama model
-   Full error logs
-   Exact prompt used
