# Contributing to Hateable

Thanks for your interest! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/your/hateable
cd hateable
pip3 install -r requirements.txt
python3 server.py
```

The UI at `ui/index.html` is a single file — no build step required. Just edit and reload.

## Project Structure

| File | Purpose |
|------|---------|
| `server.py` | HTTP + WebSocket server, pipeline orchestration |
| `agents/refiner.py` | Converts free-text idea → JSON spec |
| `agents/builder.py` | Generates React components via Ollama |
| `agents/tester.py` | Playwright browser testing |
| `ui/index.html` | Single-file frontend (vanilla JS) |

## Key Concepts

### Adding a new site type
In `agents/refiner.py`, add to `SITE_TYPES` and `SECTION_MAP`:
```python
SITE_TYPES = {
    ...
    "mytype": ["keyword1", "keyword2"],
}
SECTION_MAP = {
    ...
    "mytype": ["Hero", "MySection", "Contact"],
}
```

### Improving the fix pipeline
`agents/builder.py → _fix_component()` — this is where LLM-assisted repairs happen.
The `_sanitize_jsx()` method does deterministic post-processing (no LLM needed).

### Adding UI features
The frontend is pure vanilla JS in `ui/index.html`. WebSocket messages follow this format:
```js
// From server to client:
{type: 'log', level: 'INFO', text: '...'}
{type: 'step', step: 'build', status: 'active'}
{type: 'file', name: 'src/App.jsx', size: '2.1KB', content: '...'}
{type: 'done', url: 'http://localhost:5173', project: 'my-app'}

// From client to server:
{type: 'build', prompt: '...', refine_model: '...', build_model: '...'}
{type: 'update', project: 'my-app', prompt: '...', build_model: '...'}
```

## Pull Request Guidelines

- Keep PRs focused — one feature or fix per PR
- Test with at least one Ollama model before submitting
- UI changes: screenshot before/after in the PR description
- Agent changes: describe what prompted/fixed and how you tested it

## Reporting Issues

Please include:
- Your OS and Python version
- Which Ollama model(s) you're using
- The exact prompt that caused the issue
- Any error messages from the terminal