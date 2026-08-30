"""Configuration and environment management for shield-bypass."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_PORT = 9333
_XVFB_PROC: subprocess.Popen | None = None


def is_debug() -> bool:
    """Return True if debug mode is active."""
    for key in ("SHIELD_BYPASS_DEBUG", "CF_TURNSTILE_DEBUG"):
        val = os.environ.get(key, "").strip().lower()
        if val in {"1", "true", "yes", "on"}:
            return True
    return False


def debug_log(msg: str) -> None:
    """Log a debug message if debug mode is enabled."""
    if is_debug():
        print(f"[shield-bypass] {msg}", file=sys.stderr, flush=True)


def is_headless() -> bool:
    """Return True if headless mode is requested."""
    for key in ("SHIELD_BYPASS_HEADLESS", "CF_TURNSTILE_HEADLESS"):
        val = os.environ.get(key, "").strip().lower()
        if val in {"1", "true", "yes", "on"}:
            return True
    return False


def session_dir() -> Path:
    """Return the base directory for sessions and logs."""
    for key in ("SHIELD_BYPASS_SESSION_DIR", "CF_TURNSTILE_SESSION_DIR"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return Path(raw).expanduser()
    return Path.home() / ".shield-bypass"


def session_meta_path() -> Path:
    """Path to the session JSON metadata file."""
    return session_dir() / "session.json"


def default_profile() -> Path:
    """Path to the default persistent Chrome profile."""
    return session_dir() / "profile"


def default_port() -> int:
    """Get the CDP port from environment or default."""
    for key in ("SHIELD_BYPASS_PORT", "CF_TURNSTILE_CDP_PORT"):
        raw = os.environ.get(key, "").strip()
        if raw.isdigit():
            return int(raw)
    return DEFAULT_PORT


def cdp_url(port: int | None = None) -> str:
    """Format CDP URL."""
    return f"http://127.0.0.1:{port or default_port()}"


def _is_pid_alive(pid: int) -> bool:
    """Check if a process is alive."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _is_display_working(display: str) -> bool:
    """Test if an X11 display is currently responding."""
    disp = display if display.startswith(":") else f":{display}"
    num = disp.lstrip(":")
    sock = Path(f"/tmp/.X11-unix/X{num}")
    if sock.exists():
        # Socket exists, try a quick probe with xset or xdpyinfo if available
        xset = shutil.which("xset")
        if xset:
            r = subprocess.run([xset, "-q", "-display", disp], capture_output=True, timeout=1.0)
            if r.returncode == 0:
                return True
        else:
            return True
    return False


def _find_free_display(start: int = 99) -> str:
    """Find a display number that is not currently locked or in use."""
    for num in range(start, start + 30):
        lock = Path(f"/tmp/.X{num}-lock")
        sock = Path(f"/tmp/.X11-unix/X{num}")
        if lock.exists():
            try:
                pid_text = lock.read_text().strip()
                if pid_text.isdigit() and _is_pid_alive(int(pid_text)):
                    continue
                # Stale lock file
                lock.unlink(missing_ok=True)
            except Exception:
                pass
        if sock.exists() and not lock.exists():
            # Socket without active lock, check if working
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
    """Linux container: if DISPLAY is empty, start Xvfb so headed Chrome can run."""
    env = dict(env or os.environ)
    if not sys.platform.startswith("linux"):
        return env

    curr_disp = env.get("DISPLAY", "").strip()
    if curr_disp:
        if _is_display_working(curr_disp):
            return env
        debug_log(f"Current DISPLAY={curr_disp} is not responsive, probing fallback...")

    # Check preferred display
    pref = env.get("SHIELD_BYPASS_DISPLAY") or env.get("CF_TURNSTILE_DISPLAY") or ""
    if pref:
        display = pref if pref.startswith(":") else f":{pref}"
    else:
        display = _find_free_display(99)

    env["DISPLAY"] = display
    if _is_display_working(display):
        debug_log(f"Using existing working display {display}")
        return env

    xvfb = shutil.which("Xvfb")
    if not xvfb:
        debug_log("Xvfb binary not found in PATH")
        return env

    global _XVFB_PROC
    log_path = session_dir() / "xvfb.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_path, "ab")

    num = display.lstrip(":")
    lock = Path(f"/tmp/.X{num}-lock")
    lock.unlink(missing_ok=True)

    debug_log(f"Starting Xvfb on display {display}...")
    _XVFB_PROC = subprocess.Popen(
        [xvfb, display, "-screen", "0", "1920x1080x24", "-nolisten", "tcp", "-extension", "GLX"],
        stdout=log_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    deadline = time.time() + 6.0
    while time.time() < deadline:
        if _is_display_working(display) or lock.exists() or Path(f"/tmp/.X11-unix/X{num}").exists():
            break
        time.sleep(0.1)

    env["SHIELD_BYPASS_XVFB_PID"] = str(_XVFB_PROC.pid)
    debug_log(f"Xvfb started on display {display} (pid={_XVFB_PROC.pid})")
    return env
