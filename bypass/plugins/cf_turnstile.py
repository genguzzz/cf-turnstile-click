"""Cloudflare Turnstile challenge detector and solver plugin."""

from __future__ import annotations

import time
from typing import Any

from bypass.config import debug_log
from bypass.injector import install_click_tap, isolated_eval
from bypass.inspector import describe_point
from bypass.plugins.base import BaseChallengePlugin, DetectionResult, SolveResult

IFRAME_SEL = "iframe[src*='challenges.cloudflare.com'], iframe[src*='turnstile'], iframe[id*='cf-chl-widget']"
TOKEN_SEL = "input[name='cf-turnstile-response'], textarea[name='cf-turnstile-response'], [id^='cf-chl-widget-']"
WIDGET_SEL = ".cf-turnstile, [data-sitekey], [id*='cf-chl-widget'], input[name='cf-turnstile-response']"
HEADER_Y = 80.0
IFRAME_MIN_W = 180.0
IFRAME_MIN_H = 45.0
WIDGET_CLICK_X = 26.0
WIDGET_CLICK_Y = 32.0


def _token_from_locator(page) -> str:
    """Read token directly via isolated evaluation (0ms latency)."""
    js = """() => {
      const el = document.querySelector("input[name='cf-turnstile-response'], textarea[name='cf-turnstile-response'], [id^='cf-chl-widget-']");
      return (el && el.value && el.value.length > 20) ? el.value : "";
    }"""
    try:
        val = isolated_eval(page, js)
        if val and isinstance(val, str) and len(val) > 20:
            return val
    except Exception:
        pass
    try:
        loc = page.locator(TOKEN_SEL).first
        if loc.count() > 0:
            val = loc.input_value(timeout=300)
            if val and len(val) > 20:
                return str(val)
    except Exception:
        pass
    return ""


def _iframe_count(page) -> int:
    try:
        return int(page.locator(IFRAME_SEL).count())
    except Exception:
        return 0


def _iframe_host_box(page, index: int) -> dict[str, float] | None:
    try:
        box = page.locator(IFRAME_SEL).nth(index).bounding_box(timeout=300)
        if box:
            return {k: float(box[k]) for k in ("x", "y", "width", "height")}
    except Exception:
        pass
    return None


def _is_widget_iframe_box(box: dict[str, float]) -> bool:
    w = float(box.get("width") or 0)
    h = float(box.get("height") or 0)
    y = float(box.get("y") or 0)
    return w >= IFRAME_MIN_W and h >= IFRAME_MIN_H and y >= HEADER_Y


def _frame_text_visible(fl, text: str) -> bool:
    try:
        return bool(fl.get_by_text(text, exact=True).first.is_visible(timeout=150))
    except Exception:
        return False


def click_turnstile_checkbox(page) -> bool:
    """Click the painted Turnstile iframe checkbox directly."""
    n = _iframe_count(page)
    for i in range(n):
        host = page.locator(IFRAME_SEL).nth(i)
        try:
            handle = host.element_handle(timeout=300)
        except Exception:
            handle = None
        if not handle:
            continue
        ibox = handle.bounding_box()
        if not ibox or not _is_widget_iframe_box(ibox):
            continue
        fl = page.frame_locator(IFRAME_SEL).nth(i)
        if _frame_text_visible(fl, "Verifying..."):
            continue
        loc = fl.get_by_role("checkbox")
        try:
            if not loc.first.is_visible(timeout=200):
                continue
        except Exception:
            continue

        debug_log(f"Clicking Turnstile iframe[{i}] at ({WIDGET_CLICK_X}, {WIDGET_CLICK_Y})")
        try:
            handle.click(
                position={"x": WIDGET_CLICK_X, "y": WIDGET_CLICK_Y},
                timeout=2000,
                delay=60,
                force=True,
            )
            return True
        except Exception as e:
            debug_log(f"Handle click failed ({e}), trying locator click...")
            try:
                loc.first.click(timeout=1500, force=True)
                return True
            except Exception:
                pass
    return False


class CfTurnstilePlugin(BaseChallengePlugin):
    """High-performance plugin for solving Cloudflare Turnstile widgets."""

    name = "cf_turnstile"
    display_name = "Cloudflare Turnstile"
    priority = 10

    def detect(self, page, ctx=None) -> DetectionResult:
        res = DetectionResult(challenge_type=self.name)
        existing_token = _token_from_locator(page)
        if existing_token:
            res.detected = True
            res.confidence = 1.0
            res.details = {"status": "token_present", "token_len": len(existing_token)}
            return res

        cf_frames = _iframe_count(page)
        try:
            widget_hosts = int(page.locator(WIDGET_SEL).count())
        except Exception:
            widget_hosts = 0

        if cf_frames > 0 or widget_hosts > 0:
            res.detected = True
            res.confidence = 0.95
            res.details = {"cf_frames": cf_frames, "widget_hosts": widget_hosts}
            return res

        return res

    def solve(self, page, ctx=None, *, timeout_s: int = 35, **kwargs) -> SolveResult:
        debug_log("Starting Cloudflare Turnstile solver...")
        early = _token_from_locator(page)
        if early:
            debug_log(f"Turnstile token already available (len={len(early)})")
            return SolveResult(
                success=True,
                challenge_type=self.name,
                token=early,
                data={"token_len": len(early)},
            )

        install_click_tap(page)
        deadline = time.time() + timeout_s
        clicked = False

        while time.time() < deadline:
            tok = _token_from_locator(page)
            if tok:
                debug_log(f"Turnstile solved successfully! Token len={len(tok)}")
                return SolveResult(
                    success=True,
                    challenge_type=self.name,
                    token=tok,
                    data={"token_len": len(tok)},
                )

            if not clicked:
                clicked = click_turnstile_checkbox(page)

            # High responsiveness (100ms polling)
            time.sleep(0.1)

        tok = _token_from_locator(page)
        if tok:
            return SolveResult(success=True, challenge_type=self.name, token=tok, data={"token_len": len(tok)})

        return SolveResult(
            success=False,
            challenge_type=self.name,
            error=f"Turnstile checkbox produced no token within {timeout_s}s timeout",
        )
