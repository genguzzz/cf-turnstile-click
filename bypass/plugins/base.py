"""Base class and result containers for challenge detection and solver plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DetectionResult:
    """Outcome of challenge detection on a page."""

    detected: bool = False
    challenge_type: str = ""
    confidence: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SolveResult:
    """Outcome of a solver execution."""

    success: bool = False
    challenge_type: str = ""
    token: str = ""
    clearance: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class BaseChallengePlugin:
    """Abstract base class for all challenge detector and solver plugins."""

    name: str = "base"
    display_name: str = "Base Challenge Plugin"
    priority: int = 100  # Lower number = higher priority during auto-detection

    def detect(self, page, ctx=None) -> DetectionResult:
        """Analyze page/context and determine if this challenge type is present."""
        raise NotImplementedError

    def solve(self, page, ctx=None, *, timeout_s: int = 40, **kwargs) -> SolveResult:
        """Solve or bypass the challenge on the page and extract tokens/cookies."""
        raise NotImplementedError
