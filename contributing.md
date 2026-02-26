<div align="center">

# 🤝 Contributing to Locode

Thank you for contributing to Locode.

</div>

Locode is built on three principles:

1. **Fully local execution**
2. **Deterministic + repairable output**
3. **Clean developer experience**

---

## 🛠 Development Setup

**Prerequisites:**
- Python 3.9+
- Node.js 20 LTS
- Ollama running

**Clone & Run:**

```bash
git clone https://github.com/locode-dev/locode
cd locode
pip3 install -r requirements.txt
python3 server.py
```

Open: `http://localhost:7824`

---

## 🧠 Agent Overview

```
Refiner  ──▶  Builder  ──▶  Tester
```

| Agent | File |
|---|---|
| **Refiner** | `agents/refiner.py` |
| **Builder** | `agents/builder.py` |
| **Tester** | `agents/tester.py` |

---

## 🔄 Pull Request Guidelines

- One feature per PR
- No build artifacts
- Test with at least one Ollama model
- Include screenshots for UI changes

**Do NOT commit:**

```
dist/
dist-electron/
node_modules/
Playwright browsers
DMG files
```

---

## 🐛 Reporting Issues

Include:

| Field | Example |
|---|---|
| OS + version | macOS 14.2 |
| Python version | 3.11.4 |
| Node version | 20.10.0 |
| Ollama model | llama3.1:8b (or your chosen model) |
| Full error logs | complete stack trace |
| Exact prompt used | the input that caused the issue |