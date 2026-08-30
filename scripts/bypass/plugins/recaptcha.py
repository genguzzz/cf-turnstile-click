"""Google reCAPTCHA v2/v3 detection and checkbox interaction plugin."""

from __future__ import annotations

import time
from typing import Any

from bypass.config import debug_log
from bypass.plugins.base import BaseChallengePlugin, DetectionResult, SolveResult

RECAPTCHA_IFRAME_SEL = "iframe[src*='google.com/recaptcha'], iframe[src*='recaptcha.net']"
RECAPTCHA_TOKEN_SEL = "textarea[name='g-recaptcha-response']"


class RecaptchaPlugin(BaseChallengePlugin):
    """Plugin for Google reCAPTCHA v2 / v3."""

    name = "recaptcha"
    display_name = "Google reCAPTCHA"
    priority = 20

    def detect(self, page, ctx=None) -> DetectionResult:
        res = DetectionResult(challenge_type=self.name)
        try:
            frames = int(page.locator(RECAPTCHA_IFRAME_SEL).count())
        except Exception:
            frames = 0

        try:
            inputs = int(page.locator(RECAPTCHA_TOKEN_SEL).count())
        except Exception:
            inputs = 0

        if frames > 0 or inputs > 0:
            res.detected = True
            res.confidence = 0.9
            res.details = {"recaptcha_frames": frames, "token_inputs": inputs}
            return res

        return res

    def solve(self, page, ctx=None, *, timeout_s: int = 40, **kwargs) -> SolveResult:
        debug_log("Starting Google reCAPTCHA solver...")
        deadline = time.time() + timeout_s

        # 1. Check if token already exists
        token = self._read_token(page)
        if token:
            return SolveResult(success=True, challenge_type=self.name, token=token, data={"token_len": len(token)})

        # 2. Click checkbox inside reCAPTCHA iframe
        try:
            fl = page.frame_locator(RECAPTCHA_IFRAME_SEL).first
            checkbox = fl.locator("#recaptcha-anchor, .recaptcha-checkbox-border").first
            if checkbox.is_visible(timeout=2000):
                debug_log("Clicking reCAPTCHA checkbox...")
                checkbox.click(timeout=3000)
        except Exception as e:
            debug_log(f"reCAPTCHA checkbox click attempt: {e}")

        # 3. Wait for token to appear in response textarea
        while time.time() < deadline:
            token = self._read_token(page)
            if token:
                debug_log(f"reCAPTCHA solved! Token len={len(token)}")
                return SolveResult(success=True, challenge_type=self.name, token=token, data={"token_len": len(token)})
            time.sleep(0.5)

        return SolveResult(
            success=False,
            challenge_type=self.name,
            error=f"reCAPTCHA produced no token within {timeout_s}s (may require image challenge solve)",
        )

    def _read_token(self, page) -> str:
        try:
            loc = page.locator(RECAPTCHA_TOKEN_SEL).first
            if loc.count() > 0:
                val = loc.input_value(timeout=300)
                if val and len(val) > 20:
                    return str(val)
        except Exception:
            pass
        return ""
