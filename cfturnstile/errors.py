from __future__ import annotations


class TurnstileError(RuntimeError):
    """Widget did not load, checkbox produced no token, or browser launch failed."""
