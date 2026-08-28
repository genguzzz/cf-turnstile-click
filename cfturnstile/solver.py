"""Wait for a Turnstile token; click the checkbox with OS input when needed.

Never evaluate in the page world (``isolated_context=False``). That enables
Runtime in the main world and Cloudflare refuses to load the widget.
Read the token with ``locator.input_value()``.
"""

from __future__ import annotations

import os
import sys
import time

from cfturnstile.browser import chrome_context, extension_dir, launch_extension_args, launch_kwargs
from cfturnstile.errors import TurnstileError
from cfturnstile.os_click import os_click, viewport_point_to_screen

IFRAME_SEL = "iframe[src*='challenges.cloudflare.com'], iframe[src*='turnstile']"
TOKEN_SEL = "input[name='cf-turnstile-response'], textarea[name='cf-turnstile-response']"
WIDGET_SEL = ".cf-turnstile, [data-turnstile-widget-id], [data-sitekey]"
GEO_JS = """() => ({
  screenX: window.screenX,
  screenY: window.screenY,
  outerW: window.outerWidth,
  outerH: window.outerHeight,
  innerW: window.innerWidth,
  innerH: window.innerHeight,
  dpr: window.devicePixelRatio || 1
})"""


def _dbg(msg: str) -> None:
    if os.environ.get("CF_TURNSTILE_DEBUG", "").strip().lower() in {"1", "true", "yes"}:
        print(f"[cf-turnstile] {msg}", file=sys.stderr, flush=True)


def isolated_eval(page, js: str):
    """Patchright isolated world only. Never pass isolated_context=False."""
    try:
        return page.evaluate(js, isolated_context=True)
    except TypeError:
        return page.evaluate(js)


def checkbox_point(box: dict) -> tuple[float, float]:
    """Left checkbox of the managed widget (Theyka / playwright-captcha)."""
    x = box["x"] + min(28.0, max(12.0, float(box["width"]) * 0.08))
    y = box["y"] + float(box["height"]) / 2.0
    return x, y


def token_from_locator(page) -> str:
    loc = page.locator(TOKEN_SEL).first
    try:
        loc.wait_for(state="attached", timeout=1500)
        val = loc.input_value(timeout=800)
        if val and len(val) > 20:
            return str(val)
    except Exception:
        return ""
    return ""


def wait_widget_attached(page, timeout_ms: int) -> None:
    deadline = time.time() + timeout_ms / 1000.0
    last_err = None
    while time.time() < deadline:
        for sel in (IFRAME_SEL, WIDGET_SEL, TOKEN_SEL):
            try:
                page.locator(sel).first.wait_for(state="attached", timeout=800)
                return
            except Exception as e:
                last_err = e
        time.sleep(0.25)
    raise TurnstileError(
        "Turnstile widget did not load (challenges.cloudflare.com). "
        f"last={last_err}"
    )


def widget_box(page) -> dict | None:
    for sel in (IFRAME_SEL, WIDGET_SEL):
        loc = page.locator(sel).first
        try:
            if loc.count() == 0:
                continue
            box = loc.bounding_box()
            if box and box.get("width", 0) >= 20 and box.get("height", 0) >= 20:
                return box
        except Exception:
            continue
    loc = page.locator(TOKEN_SEL).first
    try:
        if loc.count() == 0:
            return None
        parent = loc.locator("xpath=..")
        box = parent.bounding_box()
        if box and box.get("height", 0) >= 20:
            return box
    except Exception:
        return None
    return None


def _page_geo(page) -> dict:
    try:
        geo = isolated_eval(page, GEO_JS) or {}
        if isinstance(geo, dict) and "screenX" in geo:
            return geo
    except Exception:
        pass
    return {
        "screenX": 0,
        "screenY": 0,
        "outerW": 0,
        "outerH": 0,
        "innerW": 0,
        "innerH": 0,
    }


def click_checkbox_os(page, box: dict) -> str:
    vx, vy = checkbox_point(box)
    geo = _page_geo(page)
    sx, sy = viewport_point_to_screen(geo, vx, vy)
    try:
        page.bring_to_front()
    except Exception:
        pass
    _dbg(f"click viewport=({vx:.1f},{vy:.1f}) screen=({sx:.1f},{sy:.1f}) geo={geo}")
    return os_click(sx, sy, viewport=(vx, vy))


def click_checkbox_cdp(page, box: dict) -> str:
    vx, vy = checkbox_point(box)
    try:
        page.mouse.move(vx, vy)
        time.sleep(0.12)
        page.mouse.click(vx, vy, delay=80)
        return "cdp-mouse"
    except Exception as e:
        _dbg(f"cdp-mouse failed ({e!r})")
    iframe = page.locator(IFRAME_SEL).first
    try:
        if iframe.count() > 0:
            iframe.click(position={"x": 26, "y": 32}, timeout=2000)
            return "cdp-iframe"
    except Exception as e:
        _dbg(f"cdp-iframe click failed ({e!r})")
    return "cdp-miss"


def solve(page, timeout_s: int = 40) -> str:
    """Click the Turnstile checkbox on an already-open page and return the token.

    ``page`` is a Patchright/Playwright page that already shows the widget.
    """
    wait_widget_attached(page, min(20_000, timeout_s * 1000))
    _dbg("widget attached")
    if os.environ.get("CF_TURNSTILE_DEBUG", "").strip().lower() in {"1", "true", "yes"}:

        def _con(msg) -> None:
            text = ""
            try:
                text = str(msg.text)
            except Exception:
                return
            if "cf-turnstile-click" in text or "challenges.cloudflare" in text:
                _dbg(f"console {text[:180]}")

        try:
            page.on("console", _con)
        except Exception:
            pass
    time.sleep(1.0)
    deadline = time.time() + timeout_s
    clicked = False
    while time.time() < deadline:
        tok = token_from_locator(page)
        if tok:
            _dbg(f"token len={len(tok)}")
            return tok
        box = widget_box(page)
        if box and not clicked:
            # Linux XTEST does not reach Chrome OOPIF (Turnstile iframe).
            # Extra clicks while the widget says "Verifying..." abort the challenge.
            linux = sys.platform.startswith("linux")
            if linux:
                kind = click_checkbox_cdp(page, box)
                _dbg(f"{kind} box={box}")
            else:
                try:
                    backend = click_checkbox_os(page, box)
                    _dbg(f"os click {backend} box={box}")
                except Exception as e:
                    _dbg(f"os click failed ({e!r}), cdp fallback")
                    click_checkbox_cdp(page, box)
            clicked = True
            if os.environ.get("CF_TURNSTILE_DEBUG", "").strip().lower() in {"1", "true", "yes"}:
                try:
                    page.screenshot(path="/tmp/cf-turnstile-after-click.png", full_page=True)
                    _dbg("screenshot /tmp/cf-turnstile-after-click.png")
                except Exception:
                    pass
        time.sleep(0.4)
    try:
        page.screenshot(path="/tmp/cf-turnstile-fail.png", full_page=True)
    except Exception:
        pass
    raise TurnstileError(
        "Turnstile checkbox produced no token. "
        "Use headed Chrome, grant Accessibility (macOS) to the process that "
        "launches Chrome, and keep the window visible. "
        "screenshot=/tmp/cf-turnstile-fail.png"
    )


def solve_url(url: str, *, timeout_s: int = 45, headless: bool = False, wait_until: str = "domcontentloaded") -> str:
    """Open ``url`` in patched Chrome, solve Turnstile, return the token."""
    with chrome_context(headless=headless) as (page, _ctx):
        page.goto(url, wait_until=wait_until, timeout=timeout_s * 1000)
        return solve(page, timeout_s=timeout_s)


__all__ = [
    "IFRAME_SEL",
    "TOKEN_SEL",
    "WIDGET_SEL",
    "checkbox_point",
    "chrome_context",
    "click_checkbox_cdp",
    "click_checkbox_os",
    "extension_dir",
    "isolated_eval",
    "launch_extension_args",
    "launch_kwargs",
    "solve",
    "solve_url",
    "token_from_locator",
    "wait_widget_attached",
    "widget_box",
]
