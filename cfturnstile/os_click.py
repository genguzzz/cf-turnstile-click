"""OS-level mouse click (not CDP Input.dispatchMouseEvent).

A CDP click inside Cloudflare's cross-origin Turnstile iframe reports
MouseEvent.screenX/Y relative to that iframe (< 100). A real OS click is
relative to the display (hundreds).
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import time
from typing import Literal

Button = Literal["left", "right", "middle"]


def viewport_point_to_screen(geo: dict, x: float, y: float) -> tuple[float, float]:
    """Map CSS viewport coords to global screen coords using window chrome sizes."""
    outer_w = float(geo.get("outerW") or geo.get("outerWidth") or 0)
    outer_h = float(geo.get("outerH") or geo.get("outerHeight") or 0)
    inner_w = float(geo.get("innerW") or geo.get("innerWidth") or 0)
    inner_h = float(geo.get("innerH") or geo.get("innerHeight") or 0)
    screen_x = float(geo.get("screenX") or 0)
    screen_y = float(geo.get("screenY") or 0)
    chrome_x = max(0.0, (outer_w - inner_w) / 2.0)
    chrome_y = max(0.0, outer_h - inner_h)
    return screen_x + chrome_x + x, screen_y + chrome_y + y


def _quartz_click(x: float, y: float, button: Button = "left") -> None:
    import ctypes
    import ctypes.util

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    kCGEventMouseMoved = 5
    kCGHIDEventTap = 0
    button_map = {
        "left": (1, 2, 0),
        "right": (3, 4, 1),
        "middle": (25, 26, 2),
    }
    down_t, up_t, btn = button_map[button]
    path = ctypes.util.find_library("CoreGraphics") or (
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
    )
    cf_path = ctypes.util.find_library("CoreFoundation") or (
        "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
    )
    cg = ctypes.CDLL(path)
    cf = ctypes.CDLL(cf_path)
    cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    cg.CGEventCreateMouseEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        CGPoint,
        ctypes.c_uint32,
    ]
    cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    cf.CFRelease.argtypes = [ctypes.c_void_p]

    pt = CGPoint(float(x), float(y))

    def post(etype: int) -> None:
        ev = cg.CGEventCreateMouseEvent(None, etype, pt, btn)
        if not ev:
            raise OSError("CGEventCreateMouseEvent returned NULL")
        cg.CGEventPost(kCGHIDEventTap, ev)
        cf.CFRelease(ev)

    post(kCGEventMouseMoved)
    time.sleep(0.04)
    post(down_t)
    time.sleep(0.05)
    post(up_t)


def _osascript_click(x: float, y: float) -> None:
    script = (
        "tell application \"System Events\" to click at "
        f"{{{int(round(x))}, {int(round(y))}}}"
    )
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True)


def _activate_chrome() -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.run(
            ["osascript", "-e", 'tell application "Google Chrome" to activate'],
            check=False,
            capture_output=True,
        )
        time.sleep(0.25)
        return
    if system == "Linux" and shutil.which("xdotool"):
        for needle in ("Chromium", "Google Chrome", "Chrome", "chromium"):
            r = subprocess.run(
                ["xdotool", "search", "--name", needle, "windowactivate"],
                check=False,
                capture_output=True,
            )
            if r.returncode == 0:
                break
        time.sleep(0.15)


def _windows_click(x: float, y: float, button: Button = "left") -> None:
    import ctypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    user32.SetCursorPos(int(round(x)), int(round(y)))
    down_up = {
        "left": (0x0002, 0x0004),
        "right": (0x0008, 0x0010),
        "middle": (0x0020, 0x0040),
    }[button]
    user32.mouse_event(down_up[0], 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(down_up[1], 0, 0, 0, 0)


def _xdotool_window_id() -> str | None:
    queries = (
        ["--onlyvisible", "--class", "Chromium"],
        ["--onlyvisible", "--class", "chromium"],
        ["--onlyvisible", "--class", "Google-chrome"],
        ["--onlyvisible", "--name", "NodeSeek"],
        ["--onlyvisible", "--name", "Chromium"],
        ["--onlyvisible", "--name", "Chrome"],
    )
    for extra in queries:
        r = subprocess.run(
            ["xdotool", "search", *extra],
            check=False,
            capture_output=True,
            text=True,
        )
        ids = [i for i in (r.stdout or "").split() if i.isdigit()]
        if ids:
            return ids[-1]
    return None


def _linux_click(
    x: float,
    y: float,
    button: Button = "left",
    viewport: tuple[float, float] | None = None,
) -> None:
    if not shutil.which("xdotool"):
        raise RuntimeError("Linux OS click needs xdotool on PATH")
    btn = {"left": "1", "middle": "2", "right": "3"}[button]
    wid = _xdotool_window_id()
    if wid:
        subprocess.run(
            ["xdotool", "windowactivate", "--sync", wid],
            check=False,
            capture_output=True,
        )
        time.sleep(0.1)
    subprocess.run(
        [
            "xdotool",
            "mousemove",
            "--sync",
            str(int(round(x))),
            str(int(round(y))),
            "click",
            btn,
        ],
        check=True,
        capture_output=True,
    )


def os_click(
    x: float,
    y: float,
    button: Button = "left",
    viewport: tuple[float, float] | None = None,
) -> str:
    """Click at global screen coordinates. Returns the backend used."""
    system = platform.system()
    _activate_chrome()
    if system == "Darwin":
        try:
            _quartz_click(x, y, button=button)
            return "quartz"
        except Exception:
            _osascript_click(x, y)
            return "osascript"
    if system == "Windows":
        _windows_click(x, y, button=button)
        return "win32"
    if system == "Linux":
        _linux_click(x, y, button=button, viewport=viewport)
        return "xdotool"
    raise RuntimeError(f"OS click unsupported on {system}")
