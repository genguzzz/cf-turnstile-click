"""Long-lived Chrome session over CDP for cfturnstile."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from cfturnstile.errors import TurnstileError

DEFAULT_PORT = 9333
_XVFB_PROC = None


def session_dir() -> Path:
    raw = os.environ.get("CF_TURNSTILE_SESSION_DIR", "").strip() or os.environ.get("SHIELD_BYPASS_SESSION_DIR", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".cf-turnstile"


def session_meta_path() -> Path:
    return session_dir() / "session.json"


def default_profile() -> Path:
    return session_dir() / "profile"


def default_port() -> int:
    raw = os.environ.get("CF_TURNSTILE_CDP_PORT", "").strip() or os.environ.get("SHIELD_BYPASS_PORT", "").strip()
    return int(raw) if raw.isdigit() else DEFAULT_PORT


def cdp_url(port: int | None = None) -> str:
    return f"http://127.0.0.1:{port or default_port()}"


def listening_pid(port: int = 9333) -> int | None:
    try:
        r = subprocess.run(["ss", "-tlnp", f"sport = :{port}"], capture_output=True, text=True, check=False)
        for part in (r.stdout or "").split():
            if "pid=" in part:
                p = part.split("pid=")[1].split(",")[0]
                if p.isdigit():
                    return int(p)
    except Exception:
        pass
    try:
        r = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            check=False,
            capture_output=True,
            text=True,
        )
        for line in (r.stdout or "").split():
            if line.isdigit():
                return int(line)
    except Exception:
        pass
    return None


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _is_display_working(display: str) -> bool:
    disp = display if display.startswith(":") else f":{display}"
    num = disp.lstrip(":")
    sock = Path(f"/tmp/.X11-unix/X{num}")
    return sock.exists()


def _find_free_display(start: int = 99) -> str:
    for num in range(start, start + 30):
        lock = Path(f"/tmp/.X{num}-lock")
        sock = Path(f"/tmp/.X11-unix/X{num}")
        if lock.exists():
            try:
                pid_text = lock.read_text().strip()
                if pid_text.isdigit() and _is_pid_alive(int(pid_text)):
                    continue
                lock.unlink(missing_ok=True)
            except Exception:
                pass
        if sock.exists() and not lock.exists():
            if not _is_display_working(f":{num}"):
                try:
                    sock.unlink(missing_ok=True)
                except Exception:
                    pass
            else:
                continue
        return f":{num}"
    return ":99"


def ensure_display(env: dict | None = None) -> dict:
    """Linux: ensure an active Xvfb display is available."""
    env = dict(env or os.environ)
    if not sys.platform.startswith("linux"):
        return env
    curr_disp = env.get("DISPLAY", "").strip()
    if curr_disp and _is_display_working(curr_disp):
        return env

    pref = curr_disp or env.get("CF_TURNSTILE_DISPLAY") or env.get("SHIELD_BYPASS_DISPLAY") or ""
    display = (pref if pref.startswith(":") else f":{pref}") if pref else _find_free_display(99)
    env["DISPLAY"] = display

    if _is_display_working(display):
        return env

    xvfb = shutil.which("Xvfb")
    if not xvfb:
        return env

    global _XVFB_PROC
    log_path = session_dir() / "xvfb.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_path, "ab")
    num = display.lstrip(":")
    Path(f"/tmp/.X{num}-lock").unlink(missing_ok=True)

    _XVFB_PROC = subprocess.Popen(
        [xvfb, display, "-screen", "0", "1920x1080x24", "-nolisten", "tcp", "-extension", "GLX"],
        stdout=log_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.time() + 5
    while time.time() < deadline:
        if _is_display_working(display):
            break
        time.sleep(0.1)
    env["CF_TURNSTILE_XVFB_PID"] = str(_XVFB_PROC.pid)
    return env


def read_meta() -> dict | None:
    for p in (session_meta_path(), Path.home() / ".shield-bypass" / "session.json"):
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    return None


def write_meta(data: dict) -> None:
    d = session_dir()
    d.mkdir(parents=True, exist_ok=True)
    session_meta_path().write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def wait_cdp(url: str, timeout_s: float = 20.0) -> dict:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/json/version", timeout=1.5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(0.2)
    raise TurnstileError(f"CDP not ready at {url}: {last}")


def start_session(*, port: int | None = None, profile: Path | None = None) -> dict:
    existing = read_meta()
    port = port or default_port()
    url = cdp_url(port)
    if existing:
        try:
            wait_cdp(str(existing.get("cdp") or url), timeout_s=2)
            return existing
        except TurnstileError:
            pass
    profile = Path(profile or os.environ.get("CF_TURNSTILE_PROFILE") or default_profile())
    profile.mkdir(parents=True, exist_ok=True)
    env = ensure_display(os.environ.copy())
    env["CF_TURNSTILE_CDP_PORT"] = str(port)
    env["CF_TURNSTILE_PROFILE"] = str(profile)
    env["CF_TURNSTILE_HEADLESS"] = "0"
    env.pop("CF_TURNSTILE_CDP", None)
    log_path = session_dir() / "daemon.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_path, "ab")
    proc = subprocess.Popen(
        [sys.executable, "-m", "cfturnstile.session_daemon"],
        stdout=log_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=env,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    try:
        log_f.close()
    except Exception:
        pass
    wait_cdp(url, timeout_s=35)
    chrome_pid = listening_pid(port)
    meta = read_meta() or {
        "pid": proc.pid,
        "port": port,
        "cdp": url,
        "profile": str(profile),
        "mode": "patchright",
    }
    meta["pid"] = proc.pid
    if chrome_pid:
        meta["chrome_pid"] = chrome_pid
    if env.get("DISPLAY"):
        meta["display"] = env["DISPLAY"]
    if env.get("CF_TURNSTILE_XVFB_PID"):
        meta["xvfb_pid"] = int(env["CF_TURNSTILE_XVFB_PID"])
    write_meta(meta)
    return meta


def stop_session() -> bool:
    meta = read_meta()
    if not meta:
        return False
    pid = int(meta.get("pid") or 0)
    xvfb_pid = int(meta.get("xvfb_pid") or 0)
    if pid:
        try:
            os.killpg(pid, signal.SIGTERM)
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
    if xvfb_pid:
        try:
            os.kill(xvfb_pid, signal.SIGTERM)
        except Exception:
            pass
    try:
        session_meta_path().unlink(missing_ok=True)
    except Exception:
        pass
    return True


def session_status() -> dict:
    meta = read_meta() or {}
    url = str(meta.get("cdp") or cdp_url())
    alive = False
    try:
        wait_cdp(url, timeout_s=1.5)
        alive = True
    except TurnstileError:
        alive = False
    return {"alive": alive, **meta, "cdp": url}


@contextmanager
def attach_cdp(cdp: str | None = None):
    """Connect Patchright to a running Chrome. Does not close Chrome on exit."""
    try:
        from patchright.sync_api import sync_playwright
    except ImportError as e:
        raise TurnstileError("pip install 'cfturnstile' (needs patchright)") from e

    url = (cdp or os.environ.get("CF_TURNSTILE_CDP") or os.environ.get("SHIELD_BYPASS_CDP") or "").strip()
    if not url:
        meta = read_meta()
        url = str((meta or {}).get("cdp") or "")
    if not url:
        default_endpoint = cdp_url()
        try:
            wait_cdp(default_endpoint, timeout_s=1.0)
            url = default_endpoint
        except TurnstileError:
            pass
    if not url:
        raise TurnstileError("no CDP url; run: cf-turnstile session start")
    wait_cdp(url, timeout_s=8)
    os.environ.setdefault("CF_TURNSTILE_CDP", url)
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(url)
        context = browser.contexts[0] if browser.contexts else None
        if context is None:
            raise TurnstileError(f"CDP {url} has no browser context")
        page = context.pages[0] if context.pages else context.new_page()
        yield page, context
