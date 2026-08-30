"""Unified anti-bot challenge bypass and stealth browser automation engine."""

from __future__ import annotations

import os
from typing import Any

from bypass.browser import chrome_context, find_chrome, launch_kwargs
from bypass.errors import (
    BypassError,
    ChallengeTimeoutError,
    DetectionFailedError,
    SessionError,
    TurnstileError,
)
from bypass.fingerprint import extract_fingerprint, format_curl_cmd, format_python_code
from bypass.injector import (
    inject_script,
    install_click_tap,
    isolated_eval,
    main_eval,
    read_click_tap,
)
from bypass.inspector import (
    describe_point,
    detect_page_state,
    dump_page_controls,
    inspect_iframes,
)
from bypass.plugins import (
    BaseChallengePlugin,
    DetectionResult,
    PluginRegistry,
    SolveResult,
    auto_solve,
    detect_challenge,
)
from bypass.session import (
    attach_cdp,
    cdp_url,
    session_status,
    start_session,
    stop_session,
)


def solve(page, ctx=None, *, timeout_s: int = 45, challenge_type: str | None = None) -> SolveResult:
    """Auto-detect and solve challenges on the page."""
    return auto_solve(page, ctx, timeout_s=timeout_s, challenge_type=challenge_type)


def solve_url(
    url: str,
    *,
    timeout_s: int = 45,
    headless: bool = False,
    challenge_type: str | None = None,
    cdp: str | None = None,
) -> SolveResult:
    """Open a URL, detect and solve any challenge present, and return SolveResult."""
    with chrome_context(headless=headless, cdp=cdp) as (page, ctx):
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
        return solve(page, ctx, timeout_s=timeout_s, challenge_type=challenge_type)


def fetch_url(
    url: str,
    *,
    timeout_s: int = 45,
    headless: bool = False,
    wait_after_s: float = 2.0,
    cdp: str | None = None,
) -> dict[str, Any]:
    """Open a URL through anti-bot shields and return title, body text, HTML, and status."""
    with chrome_context(headless=headless, cdp=cdp) as (page, ctx):
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_s * 1000)
        res = solve(page, ctx, timeout_s=timeout_s)

        import time

        if wait_after_s > 0:
            time.sleep(wait_after_s)

        title = ""
        try:
            title = page.title()
        except Exception:
            pass

        text = ""
        try:
            text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            pass

        html = ""
        try:
            html = page.content()
        except Exception:
            pass

        return {
            "url": page.url,
            "title": title,
            "text": text,
            "html": html,
            "solve_result": {
                "success": res.success,
                "challenge_type": res.challenge_type,
                "token": res.token,
                "clearance": res.clearance,
            },
        }


__all__ = [
    "BypassError",
    "ChallengeTimeoutError",
    "DetectionFailedError",
    "SessionError",
    "TurnstileError",
    "chrome_context",
    "find_chrome",
    "launch_kwargs",
    "attach_cdp",
    "start_session",
    "stop_session",
    "session_status",
    "cdp_url",
    "isolated_eval",
    "main_eval",
    "inject_script",
    "install_click_tap",
    "read_click_tap",
    "inspect_iframes",
    "describe_point",
    "dump_page_controls",
    "detect_page_state",
    "extract_fingerprint",
    "format_curl_cmd",
    "format_python_code",
    "PluginRegistry",
    "BaseChallengePlugin",
    "DetectionResult",
    "SolveResult",
    "detect_challenge",
    "auto_solve",
    "solve",
    "solve_url",
    "fetch_url",
]
