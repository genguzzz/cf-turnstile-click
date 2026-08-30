"""Custom exceptions for shield-bypass."""

from __future__ import annotations


class BypassError(Exception):
    """Base error for shield-bypass operations."""


class ChallengeTimeoutError(BypassError):
    """Raised when a challenge does not complete within the timeout."""


class TurnstileError(ChallengeTimeoutError):
    """Raised when Cloudflare Turnstile verification fails or times out."""


class DetectionFailedError(BypassError):
    """Raised when challenge detection fails or no solver is found."""


class SessionError(BypassError):
    """Raised when session creation, CDP connection, or management fails."""
