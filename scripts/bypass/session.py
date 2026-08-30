"""Long-lived Patchright Chrome session manager over CDP."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from bypass.config import (
    cdp_url,
    debug_log,
    default_port,
    default_profile,
    ensure_display,
    session_dir,
    session_meta_path,
)
from bypass.errors import BypassError, SessionError


def read_meta() -> dict[str, Any] | None:
    """Read session metadata file from current or legacy path."""
    for p in (session_meta_path(), Path.home() / ".cf-turnstile" / "session.json"):
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
    return None


def write_meta(data: dict[str, Any]) -> None:
    """Write session metadata file."""
    d = session_dir()
    d.mkdir(parents=True, exist_ok=True)
    session_meta_path().write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def listening_pid(port: int) -> int | None:
    """Find process PID listening on TCP port using ss or lsof."""
    # Try ss first
    try:
        r = subprocess.run(["ss", "-tlnp", f"sport = :{port}"], capture_output=True, text=True, check=False)
        for part in (r.stdout or "").split():
            if "pid=" in part:
                p = part.split("pid=")[1].split(",")[0]
                if p.isdigit():
                    return int(p)
    except Exception:
        pass

    # Try lsof
    try:
        r = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in (r.stdout or "").split():
            if line.isdigit():
                return int(line)
    except Exception:
        pass

    return None


def wait_cdp(url: str, timeout_s: float = 25.0) -> dict[str, Any]:
    """Wait until CDP endpoint responds to /json/version."""
    deadline = time.time() + timeout_s
    last_err = None
    target = url.rstrip("/") + "/json/version"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(target, timeout=1.5) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            time.sleep(0.2)
    raise SessionError(f"CDP not ready at {url}: {last_err}")


def start_session(*, port: int | None = None, profile: Path | None = None) -> dict[str, Any]:
    """Start a long-lived Patchright Chrome instance in the background."""
    port = port or default_port()
    url = cdp_url(port)

    # Check if already running and healthy
    existing = read_meta()
    if existing:
        try:
            wait_cdp(str(existing.get("cdp") or url), timeout_s=1.5)
            debug_log(f"Session already running at {existing.get('cdp')}")
            return existing
        except SessionError:
            pass

    profile = Path(profile or default_profile())
    profile.mkdir(parents=True, exist_ok=True)

    env = ensure_display(os.environ.copy())
    env["SHIELD_BYPASS_PORT"] = str(port)
    env["CF_TURNSTILE_CDP_PORT"] = str(port)
    env["SHIELD_BYPASS_PROFILE"] = str(profile)
    env["SHIELD_BYPASS_HEADLESS"] = "0"
    env["CF_TURNSTILE_HEADLESS"] = "0"
    env.pop("SHIELD_BYPASS_CDP", None)
    env.pop("CF_TURNSTILE_CDP", None)

    log_path = session_dir() / "daemon.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_path, "ab")

    debug_log(f"Spawning session daemon on port {port}...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "bypass.daemon"],
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

    try:
        wait_cdp(url, timeout_s=35.0)
    except SessionError as e:
        try:
            proc.kill()
        except Exception:
            pass
        raise SessionError(f"Failed to start Chrome session on port {port}: {e}") from e

    chrome_pid = listening_pid(port)
    meta = {
        "pid": proc.pid,
        "chrome_pid": chrome_pid,
        "port": port,
        "cdp": url,
        "profile": str(profile),
        "display": env.get("DISPLAY", ""),
        "xvfb_pid": int(env.get("SHIELD_BYPASS_XVFB_PID") or 0),
        "started_at": time.time(),
    }
    write_meta(meta)
    debug_log(f"Session successfully started: {meta}")
    return meta


def stop_session() -> bool:
    """Stop the running background Chrome session and clean up."""
    meta = read_meta()
    if not meta:
        return False

    pid = int(meta.get("pid") or 0)
    xvfb_pid = int(meta.get("xvfb_pid") or 0)

    if pid > 0:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pid, sig)
            except Exception:
                try:
                    os.kill(pid, sig)
                except Exception:
                    pass
            time.sleep(0.3)

    if xvfb_pid > 0:
        try:
            os.kill(xvfb_pid, signal.SIGTERM)
        except Exception:
            pass

    try:
        session_meta_path().unlink(missing_ok=True)
    except Exception:
        pass

    debug_log("Session stopped.")
    return True


def session_status() -> dict[str, Any]:
    """Check current session health and return status dict."""
    meta = read_meta() or {}
    url = str(meta.get("cdp") or cdp_url())
    alive = False
    try:
        wait_cdp(url, timeout_s=1.5)
        alive = True
    except SessionError:
        alive = False

    return {
        "alive": alive,
        "cdp": url,
        "pid": meta.get("pid"),
        "chrome_pid": meta.get("chrome_pid"),
        "port": meta.get("port", default_port()),
        "display": meta.get("display"),
        "profile": meta.get("profile"),
    }


def pick_active_page(ctx, default_page=None):
    """Pick the page that has an active challenge or destination content."""
    for p in ctx.pages:
        try:
            if "about:blank" not in p.url and not p.is_closed():
                return p
        except Exception:
            continue
    return default_page or (ctx.pages[0] if ctx.pages else ctx.new_page())


@contextmanager
def attach_cdp(cdp: str | None = None):
    """Attach Patchright to a running Chrome session via CDP."""
    try:
        from patchright.sync_api import sync_playwright
    except ImportError as e:
        raise BypassError("patchright is required: pip install patchright") from e

    url = (cdp or os.environ.get("SHIELD_BYPASS_CDP") or os.environ.get("CF_TURNSTILE_CDP") or "").strip()
    if not url:
        meta = read_meta()
        url = str((meta or {}).get("cdp") or "")
    if not url:
        default_endpoint = cdp_url()
        try:
            wait_cdp(default_endpoint, timeout_s=1.0)
            url = default_endpoint
        except SessionError:
            pass
    if not url:
        raise SessionError("No active CDP URL found. Run: bypass session start")

    wait_cdp(url, timeout_s=10.0)
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(url)
        context = browser.contexts[0] if browser.contexts else None
        if context is None:
            raise SessionError(f"CDP endpoint {url} has no active browser context")
        page = pick_active_page(context, context.pages[0] if context.pages else context.new_page())
        yield page, context
