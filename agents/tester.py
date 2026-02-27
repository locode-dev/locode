#!/usr/bin/env python3
"""
Tester Agent — Python Playwright API only. No JS files, no require(), no ES module issues.
Streams all output live to UI. Retries until clean or max attempts reached.
"""
import subprocess, sys, time, logging, json
from pathlib import Path

log = logging.getLogger("tester")
_emit = None

def set_emit(fn):
    global _emit
    _emit = fn

def elog(lvl, txt):
    if _emit:
        _emit({"type": "log", "level": lvl, "text": txt})
    log.info(f"[{lvl}] {txt}")

def etest(status, msg, detail=""):
    """Emit a structured test result event to the UI."""
    if _emit:
        _emit({"type": "test_result", "status": status, "msg": msg, "detail": detail})


class TesterAgent:
    def __init__(self, project_dir: Path, port: int = 5173):
        self.project_dir = project_dir
        self.port        = port
        self.base_url    = f"http://localhost:{port}"

    def test(self) -> list:
        errors = []

        # ── 1. Wait for Vite to be ready ─────────────────────────────────────
        elog("INFO", f"⏳ Waiting for Vite at {self.base_url}...")
        ok, err = self._wait_for_server(timeout=30)
        if not ok:
            elog("WARN", f"❌ Vite not reachable: {err}")
            etest("fail", "HTTP check", f"Server not reachable: {err}")
            errors.append(f"HTTP check failed: {err}")
            return errors
        elog("INFO", "✅ HTTP 200 — Vite is serving")
        etest("pass", "HTTP 200 OK")

        # ── 2. Playwright browser tests ───────────────────────────────────────
        if not self._ensure_playwright():
            elog("WARN", "⚠ Playwright unavailable — skipping browser tests")
            etest("skip", "Playwright unavailable")
            return []  # NOT errors — don't trigger a fix loop just because Playwright is missing

        errors.extend(self._run_browser_tests())
        return errors

    # ── Internals ─────────────────────────────────────────────────────────────

    def _wait_for_server(self, timeout=30):
        import urllib.request, urllib.error
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = urllib.request.urlopen(self.base_url, timeout=5)
                if resp.status == 200:
                    return True, None
            except Exception:
                pass
            time.sleep(1.5)
        return False, f"timeout after {timeout}s"

    def _ensure_playwright(self) -> bool:
        try:
            import playwright  # noqa
            elog("INFO", "✅ Playwright Python package present")
            return True
        except ImportError:
            pass

        elog("INFO", "📦 Installing playwright Python package...")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "playwright",
             "--break-system-packages", "-q"],
            capture_output=True, timeout=120
        )
        if r.returncode != 0:
            elog("WARN", f"pip install failed: {r.stderr.decode()[:120]}")
            return False

        elog("INFO", "📦 Installing Chromium browser (may take a minute)...")
        r = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"],
            capture_output=True, text=True, timeout=300
        )
        if r.returncode != 0:
            elog("WARN", f"Chromium install failed: {r.stderr[:120]}")
            return False

        elog("INFO", "✅ Playwright + Chromium ready")
        return True

    def _run_browser_tests(self) -> list:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

        elog("INFO", "🎭 Launching Chromium (headless)...")
        etest("run", "Browser launch")
        errors = []
        console_errors = []

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                ctx = browser.new_context(viewport={"width": 1280, "height": 720})
                page = ctx.new_page()

                page.on("console", lambda m: console_errors.append(m.text)
                        if m.type == "error" else None)
                page.on("pageerror", lambda e: console_errors.append(f"PageError: {e}"))

                # Navigate — use "load" so JS has run before we check anything.
                # Don't use "networkidle": Vite HMR keeps a WS open forever.
                elog("INFO", f"→ Navigating to {self.base_url}...")
                try:
                    resp = page.goto(self.base_url, timeout=30000, wait_until="load")
                    code = resp.status if resp else "?"
                    if resp and resp.status >= 400:
                        msg = f"Page returned HTTP {code}"
                        errors.append(msg); etest("fail", msg)
                        browser.close(); return errors
                    elog("INFO", f"✅ Page loaded (HTTP {code})")
                    etest("pass", f"Page loaded HTTP {code}")
                except PWTimeout:
                    msg = "Page load timeout — Vite may still be compiling"
                    errors.append(msg); etest("fail", msg)
                    browser.close(); return errors
                except Exception as e:
                    msg = f"Navigation error: {e}"
                    errors.append(msg); etest("fail", msg)
                    browser.close(); return errors

                # React mount — try several selectors; some apps don't use #root
                elog("INFO", "→ Waiting for app to render...")
                react_mounted = False
                for _sel in ["#root > *", "#app > *", "canvas", "svg", "main"]:
                    try:
                        page.wait_for_selector(_sel, timeout=8000)
                        react_mounted = True
                        elog("INFO", f"✅ App rendered (selector: {_sel})")
                        etest("pass", "App rendered")
                        break
                    except PWTimeout:
                        continue
                if not react_mounted:
                    # Last resort: body has any children at all
                    if page.evaluate("() => document.body.children.length") > 0:
                        react_mounted = True
                        elog("INFO", "✅ Body has children — assuming rendered")
                        etest("pass", "App rendered")
                    else:
                        msg = "App never rendered — likely a compile/runtime error"
                        errors.append(msg); etest("fail", msg)
                        elog("WARN", f"❌ {msg}")

                # Vite error overlay (shadow DOM only — no raw HTML scan which
                # causes false positives on Vite source maps / inline JS strings)
                vite_err_txt = ""
                try:
                    vite_err_txt = page.evaluate("""() => {
                        const ov = document.querySelector('vite-error-overlay');
                        if (ov && ov.shadowRoot) {
                            const el = ov.shadowRoot.querySelector('.message-body,.message,pre,.err-message');
                            return el ? el.textContent.trim().slice(0,600)
                                      : ov.shadowRoot.textContent.trim().slice(0,600);
                        }
                        return '';
                    }""") or ""
                except Exception:
                    pass

                if vite_err_txt and len(vite_err_txt) > 15:
                    errors.append(f"Vite compile error: {vite_err_txt[:500]}")
                    etest("fail", "Vite compile error", vite_err_txt[:120])
                    elog("WARN", f"❌ Vite compile error: {vite_err_txt[:120]}")
                else:
                    etest("pass", "No Vite error overlay")

                # Blank page check — ONLY fail if BOTH:
                #   • no element has a visible bounding box (truly nothing rendered)
                #   • body text is completely empty
                # This avoids false positives for canvas/SVG/icon-only apps which
                # render rich content but have little innerText.
                if react_mounted:
                    try:
                        has_visible = page.evaluate("""() => {
                            const sels = ['#root *', '#app *', 'body > div *', 'canvas', 'svg'];
                            for (const s of sels) {
                                for (const el of document.querySelectorAll(s)) {
                                    const r = el.getBoundingClientRect();
                                    if (r.width > 5 && r.height > 5) return true;
                                }
                            }
                            return false;
                        }""")
                        body_text = ""
                        try:
                            body_text = page.inner_text("body").strip()
                        except Exception:
                            pass
                        if not has_visible and len(body_text) < 10:
                            msg = "Page appears completely blank — nothing rendered"
                            errors.append(msg); etest("fail", msg)
                            elog("WARN", f"❌ {msg}")
                        else:
                            info = f"{len(body_text)} chars" if body_text else "visual content only"
                            elog("INFO", f"✅ Content visible ({info})")
                            etest("pass", "Content visible")
                    except Exception:
                        pass

                # Console errors — only report real JS exceptions that broke the app.
                # Ignore HMR noise, React dev warnings, network/CDN errors.
                noise = [
                    "favicon", "Warning:", "DevTools", "Download the React",
                    "ReactDOM.render", "StrictMode", "[HMR]", "[vite]", "vite",
                    "hot update", "connecting", "react-refresh",
                    "net::ERR_", "Failed to load resource",
                    "Cross-Origin", "Content-Security-Policy",
                ]
                real_signals = [
                    "is not defined", "is not a function",
                    "Cannot read prop", "Cannot read properties",
                    "SyntaxError", "ReferenceError", "TypeError",
                    "Failed to resolve import", "does not provide an export",
                ]
                # Filter: must NOT match noise AND MUST match a real signal
                real_errors = [
                    e for e in console_errors
                    if not any(n.lower() in e.lower() for n in noise)
                    and any(s in e for s in real_signals)
                ]
                if real_errors:
                    for ce in real_errors[:5]:
                        short = ce[:160]
                        elog("WARN", f"⚠ JS error: {short}")
                        etest("fail", "JS runtime error", short)
                        errors.append(f"Console error: {short}")
                else:
                    elog("INFO", "✅ No blocking JS errors")
                    etest("pass", "No JS errors")

                # Screenshot
                try:
                    ss_path = self.project_dir / "test_screenshot.png"
                    page.screenshot(path=str(ss_path), full_page=False)
                    elog("INFO", f"📸 Screenshot saved → test_screenshot.png")
                    etest("pass", "Screenshot captured")
                except Exception as e:
                    elog("WARN", f"Screenshot failed: {e}")

                browser.close()

        except Exception as e:
            msg = f"Playwright runtime error: {e}"
            elog("WARN", f"⚠ {msg}")
            etest("fail", msg)
            errors.append(msg)

        if errors:
            elog("WARN", f"❌ {len(errors)} issue(s) found")
        else:
            elog("INFO", "🎉 All browser tests passed!")
            etest("pass", "All tests passed!")

        return errors