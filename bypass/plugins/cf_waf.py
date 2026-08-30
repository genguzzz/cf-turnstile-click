"""Cloudflare 5s / Managed WAF Challenge detector and solver plugin."""

from __future__ import annotations

import time
from typing import Any

from bypass.config import debug_log
from bypass.plugins.base import BaseChallengePlugin, DetectionResult, SolveResult
from bypass.plugins.cf_turnstile import CfTurnstilePlugin


class CfWafPlugin(BaseChallengePlugin):
    """Plugin for passing Cloudflare 5s challenge, 'Just a moment...', and Managed WAF challenges."""

    name = "cf_waf"
    display_name = "Cloudflare WAF / 5s Challenge"
    priority = 5  # Higher priority than standalone turnstile when whole page is blocked

    def detect(self, page, ctx=None) -> DetectionResult:
        res = DetectionResult(challenge_type=self.name)
        title = ""
        try:
            title = page.title()
        except Exception:
            pass

        body_snippet = ""
        try:
            body_snippet = page.locator("body").inner_text(timeout=500)[:500]
        except Exception:
            pass

        indicators = [
            "Just a moment..." in title,
            "Attention Required! | Cloudflare" in title,
            "cf-chl-widget" in body_snippet,
            "cf-chl-opt" in body_snippet,
            "Cloudflare Ray ID" in body_snippet and "challenge" in body_snippet.lower(),
        ]

        if any(indicators):
            res.detected = True
            res.confidence = 0.98
            res.details = {"title": title, "indicators": indicators}
            return res

        return res

    def solve(self, page, ctx=None, *, timeout_s: int = 45, **kwargs) -> SolveResult:
        debug_log("Starting Cloudflare WAF / 5s Challenge solver...")
        deadline = time.time() + timeout_s

        # 1. Check if an interactive Turnstile widget is embedded inside the WAF page
        turnstile_plugin = CfTurnstilePlugin()
        ts_detection = turnstile_plugin.detect(page, ctx)
        if ts_detection.detected:
            debug_log("Embedded Turnstile detected inside Cloudflare WAF challenge page")
            ts_res = turnstile_plugin.solve(page, ctx, timeout_s=min(25, timeout_s))
            debug_log(f"Turnstile solve result inside WAF: success={ts_res.success}")

        # 2. Wait for challenge page transition and cf_clearance cookie
        last_title = ""
        while time.time() < deadline:
            title = ""
            try:
                title = page.title()
            except Exception:
                pass

            # Check if title moved away from Cloudflare challenge
            if title and "Just a moment" not in title and "Attention Required" not in title and "Cloudflare" not in title:
                debug_log(f"WAF challenge cleared! Destination page title: {title}")
                clearance = self._extract_clearance(ctx)
                return SolveResult(
                    success=True,
                    challenge_type=self.name,
                    clearance=clearance,
                    data={"title": title, "cf_clearance": clearance},
                )

            # Check if cf_clearance cookie appeared
            clearance = self._extract_clearance(ctx)
            if clearance:
                debug_log(f"cf_clearance cookie obtained: {clearance[:15]}...")
                # Allow page a moment to redirect
                time.sleep(1.0)
                try:
                    title = page.title()
                except Exception:
                    pass
                return SolveResult(
                    success=True,
                    challenge_type=self.name,
                    clearance=clearance,
                    data={"title": title, "cf_clearance": clearance},
                )

            # If still stuck and has turnstile, retry clicking
            if ts_detection.detected:
                turnstile_plugin.solve(page, ctx, timeout_s=3)

            time.sleep(0.5)

        # Final check
        clearance = self._extract_clearance(ctx)
        try:
            title = page.title()
        except Exception:
            pass

        if clearance or ("Just a moment" not in title and "Cloudflare" not in title):
            return SolveResult(
                success=True,
                challenge_type=self.name,
                clearance=clearance,
                data={"title": title, "cf_clearance": clearance},
            )

        return SolveResult(
            success=False,
            challenge_type=self.name,
            error=f"Cloudflare WAF challenge did not resolve within {timeout_s}s timeout",
        )

    def _extract_clearance(self, ctx) -> str:
        if not ctx:
            return ""
        try:
            for c in ctx.cookies():
                if c.get("name") == "cf_clearance" and c.get("value"):
                    return str(c["value"])
        except Exception:
            pass
        return ""
