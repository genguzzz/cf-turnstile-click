"""Fallback page stabilization and generic challenge resolution plugin."""

from __future__ import annotations

import time
from typing import Any

from bypass.config import debug_log
from bypass.plugins.base import BaseChallengePlugin, DetectionResult, SolveResult


class GenericWaitPlugin(BaseChallengePlugin):
    """Fallback plugin when no specific challenge signature is identified."""

    name = "generic_wait"
    display_name = "Generic Page Stabilization"
    priority = 999  # Lowest priority (fallback)

    def detect(self, page, ctx=None) -> DetectionResult:
        # Always detected with low confidence as fallback
        return DetectionResult(
            detected=True,
            challenge_type=self.name,
            confidence=0.1,
            details={"fallback": True},
        )

    def solve(self, page, ctx=None, *, timeout_s: int = 15, **kwargs) -> SolveResult:
        debug_log("Running generic page stabilization...")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout_s * 1000)
        except Exception:
            pass

        try:
            page.wait_for_load_state("networkidle", timeout=min(8000, timeout_s * 1000))
        except Exception:
            pass

        title = ""
        try:
            title = page.title()
        except Exception:
            pass

        return SolveResult(
            success=True,
            challenge_type=self.name,
            data={"title": title, "url": page.url},
        )
