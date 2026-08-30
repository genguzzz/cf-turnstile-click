"""hCaptcha detection and solver plugin."""

from __future__ import annotations

import time
from typing import Any

from bypass.config import debug_log
from bypass.plugins.base import BaseChallengePlugin, DetectionResult, SolveResult

HCAPTCHA_IFRAME_SEL = "iframe[src*='hcaptcha.com']"
HCAPTCHA_TOKEN_SEL = "textarea[name='h-captcha-response']"


class HcaptchaPlugin(BaseChallengePlugin):
    """Plugin for hCaptcha detection and checkbox interaction."""

    name = "hcaptcha"
    display_name = "hCaptcha"
    priority = 25

    def detect(self, page, ctx=None) -> DetectionResult:
        res = DetectionResult(challenge_type=self.name)
        try:
            frames = int(page.locator(HCAPTCHA_IFRAME_SEL).count())
        except Exception:
            frames = 0

        try:
            inputs = int(page.locator(HCAPTCHA_TOKEN_SEL).count())
        except Exception:
            inputs = 0

        if frames > 0 or inputs > 0:
            res.detected = True
            res.confidence = 0.9
            res.details = {"hcaptcha_frames": frames, "token_inputs": inputs}
            return res

        return res

    def solve(self, page, ctx=None, *, timeout_s: int = 40, **kwargs) -> SolveResult:
        debug_log("Starting hCaptcha solver...")
        deadline = time.time() + timeout_s

        token = self._read_token(page)
        if token:
            return SolveResult(success=True, challenge_type=self.name, token=token, data={"token_len": len(token)})

        # Click hCaptcha checkbox inside iframe
        try:
            fl = page.frame_locator(HCAPTCHA_IFRAME_SEL).first
            checkbox = fl.locator("#checkbox, #anchor").first
            if checkbox.is_visible(timeout=2000):
                debug_log("Clicking hCaptcha checkbox...")
                checkbox.click(timeout=3000)
        except Exception as e:
            debug_log(f"hCaptcha checkbox click attempt: {e}")

        while time.time() < deadline:
            token = self._read_token(page)
            if token:
                debug_log(f"hCaptcha solved! Token len={len(token)}")
                return SolveResult(success=True, challenge_type=self.name, token=token, data={"token_len": len(token)})
            time.sleep(0.5)

        return SolveResult(
            success=False,
            challenge_type=self.name,
            error=f"hCaptcha produced no token within {timeout_s}s (may require image challenge solve)",
        )

    def _read_token(self, page) -> str:
        try:
            loc = page.locator(HCAPTCHA_TOKEN_SEL).first
            if loc.count() > 0:
                val = loc.input_value(timeout=300)
                if val and len(val) > 20:
                    return str(val)
        except Exception:
            pass
        return ""
