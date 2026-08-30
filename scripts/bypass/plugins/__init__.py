"""Plugin registry and challenge detection/solver dispatcher."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Type

from bypass.config import debug_log
from bypass.plugins.base import BaseChallengePlugin, DetectionResult, SolveResult
from bypass.plugins.cf_turnstile import CfTurnstilePlugin
from bypass.plugins.cf_waf import CfWafPlugin
from bypass.plugins.generic_wait import GenericWaitPlugin
from bypass.plugins.hcaptcha import HcaptchaPlugin
from bypass.plugins.recaptcha import RecaptchaPlugin


class PluginRegistry:
    """Registry managing challenge solver plugins."""

    _plugins: dict[str, BaseChallengePlugin] = {}

    @classmethod
    def register(cls, plugin: BaseChallengePlugin | Type[BaseChallengePlugin]) -> None:
        instance = plugin() if isinstance(plugin, type) else plugin
        cls._plugins[instance.name] = instance
        debug_log(f"Registered plugin: {instance.name} ({instance.display_name})")

    @classmethod
    def get(cls, name: str) -> BaseChallengePlugin | None:
        return cls._plugins.get(name)

    @classmethod
    def list_plugins(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": p.name,
                "display_name": p.display_name,
                "priority": p.priority,
            }
            for p in sorted(cls._plugins.values(), key=lambda x: x.priority)
        ]

    @classmethod
    def detect_all(cls, page, ctx=None) -> list[DetectionResult]:
        """Run all registered detectors and return detected challenges sorted by confidence."""
        results: list[DetectionResult] = []
        for p in sorted(cls._plugins.values(), key=lambda x: x.priority):
            try:
                res = p.detect(page, ctx)
                if res and res.detected:
                    results.append(res)
            except Exception as e:
                debug_log(f"Plugin {p.name} detection failed: {e}")

        results.sort(key=lambda r: (r.confidence, -cls._plugins[r.challenge_type].priority), reverse=True)
        return results

    @classmethod
    def auto_solve(
        cls,
        page,
        ctx=None,
        *,
        challenge_type: str | None = None,
        timeout_s: int = 45,
        **kwargs,
    ) -> SolveResult:
        """Detect challenge on page and dispatch to the matching solver plugin."""
        if challenge_type and challenge_type in cls._plugins:
            plugin = cls._plugins[challenge_type]
            debug_log(f"Explicit challenge solver requested: {plugin.name}")
            return plugin.solve(page, ctx, timeout_s=timeout_s, **kwargs)

        detections = cls.detect_all(page, ctx)
        if not detections:
            debug_log("No challenge detected, using fallback stabilizer...")
            fallback = cls._plugins.get("generic_wait") or GenericWaitPlugin()
            return fallback.solve(page, ctx, timeout_s=min(15, timeout_s), **kwargs)

        best = detections[0]
        debug_log(f"Primary detected challenge: {best.challenge_type} (confidence={best.confidence:.2f})")
        plugin = cls._plugins.get(best.challenge_type)
        if not plugin:
            return SolveResult(success=False, error=f"No solver registered for {best.challenge_type}")

        return plugin.solve(page, ctx, timeout_s=timeout_s, **kwargs)


# Register default plugins
PluginRegistry.register(CfWafPlugin)
PluginRegistry.register(CfTurnstilePlugin)
PluginRegistry.register(RecaptchaPlugin)
PluginRegistry.register(HcaptchaPlugin)
PluginRegistry.register(GenericWaitPlugin)


def detect_challenge(page, ctx=None) -> list[DetectionResult]:
    return PluginRegistry.detect_all(page, ctx)


def auto_solve(page, ctx=None, *, challenge_type: str | None = None, timeout_s: int = 45, **kwargs) -> SolveResult:
    return PluginRegistry.auto_solve(page, ctx, challenge_type=challenge_type, timeout_s=timeout_s, **kwargs)


__all__ = [
    "BaseChallengePlugin",
    "DetectionResult",
    "SolveResult",
    "PluginRegistry",
    "detect_challenge",
    "auto_solve",
]
