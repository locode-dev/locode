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
            return errors

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

                # Navigate
                elog("INFO", f"→ Navigating to {self.base_url}...")
                try:
                    resp = page.goto(self.base_url, timeout=25000, wait_until="domcontentloaded")
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

                # React mount
                elog("INFO", "→ Checking React mount (#root)...")
                try:
                    page.wait_for_selector("#root > *", timeout=12000)
                    elog("INFO", "✅ React mounted successfully")
                    etest("pass", "React mounted")
                except PWTimeout:
                    msg = "React root never mounted — likely a compile/runtime error"
                    errors.append(msg); etest("fail", msg)
                    elog("WARN", f"❌ {msg}")

                # Vite error overlay — shadow DOM + page source fallback
                vite_err_txt = ""
                try:
                    vite_err_txt = page.evaluate("""() => {
                        const ov = document.querySelector('vite-error-overlay');
                        if (ov && ov.shadowRoot) {
                            const msg = ov.shadowRoot.querySelector('.message-body,.message,pre,.err-message');
                            return msg ? msg.textContent : ov.shadowRoot.textContent.slice(0,600);
                        }
                        const pre = document.querySelector('pre');
                        if (pre && pre.textContent.length > 20) return pre.textContent.slice(0,600);
                        return '';
                    }""") or ""
                except Exception:
                    pass

                if not vite_err_txt:
                    try:
                        import urllib.request, re as _re
                        raw = urllib.request.urlopen(self.base_url, timeout=5).read().decode("utf-8", errors="replace")
                        for pat in [r'SyntaxError[^<\n]{0,250}', r'ReferenceError[^<\n]{0,250}',
                                    r'TypeError[^<\n]{0,250}', r'Plugin vite[^<\n]{0,250}',
                                    r'"message"\s*:\s*"([^"]{20,250})"']:
                            m = _re.search(pat, raw, _re.IGNORECASE)
                            if m:
                                vite_err_txt = _re.sub(r'<[^>]+>', '', m.group(0)).strip()
                                break
                    except Exception:
                        pass

                if vite_err_txt and len(vite_err_txt) > 10:
                    errors.append(f"Vite compile error: {vite_err_txt[:500]}")
                    etest("fail", "Vite compile error", vite_err_txt[:120])
                    elog("WARN", f"❌ Vite compile error: {vite_err_txt[:120]}")
                else:
                    etest("pass", "No Vite compile error")

                # Blank page check — two signals:
                # 1. text length < 30 (definitely blank)
                # 2. no element has a non-zero bounding box (invisible rendering)
                try:
                    body_text = page.inner_text("body").strip()
                    has_visible_box = page.evaluate("""() => {
                        const els = document.querySelectorAll('#root *');
                        for (const el of els) {
                            const r = el.getBoundingClientRect();
                            if (r.width > 10 && r.height > 10) return true;
                        }
                        return false;
                    }""")
                    if len(body_text) < 30 and not has_visible_box:
                        msg = "Page appears blank — no visible content rendered"
                        errors.append(msg); etest("fail", msg)
                        elog("WARN", f"❌ {msg}")
                    elif len(body_text) < 30 and has_visible_box:
                        # Elements exist but no readable text — likely invisible text
                        msg = "Page has elements but no readable text (possible color issue)"
                        errors.append(msg); etest("fail", msg)
                        elog("WARN", f"⚠ {msg}")
                    else:
                        elog("INFO", f"✅ Content visible ({len(body_text)} chars)")
                        etest("pass", f"Content visible ({len(body_text)} chars)")
                except Exception:
                    pass

                # Console errors
                noise = ["favicon", "Warning:", "DevTools", "Download the React",
                         "ReactDOM.render", "StrictMode", "[HMR]"]
                real_errors = [e for e in console_errors
                               if not any(n in e for n in noise)]
                if real_errors:
                    for ce in real_errors[:5]:
                        short = ce[:160]
                        elog("WARN", f"⚠ Console error: {short}")
                        etest("fail", f"Console error", short)
                        errors.append(f"Console error: {short}")
                else:
                    elog("INFO", "✅ No console errors")
                    etest("pass", "No console errors")

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