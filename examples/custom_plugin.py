#!/usr/bin/env python3
"""Example: Writing and registering a custom challenge/captcha solver plugin."""

import sys
from pathlib import Path

# Add scripts directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from bypass.plugins.base import BaseChallengePlugin, DetectionResult, SolveResult
from bypass.plugins import PluginRegistry, auto_solve
from bypass import chrome_context


class CustomSliderPlugin(BaseChallengePlugin):
    """Custom plugin for a hypothetical slider captcha."""

    name = "my_slider_captcha"
    display_name = "My Custom Slider Captcha"
    priority = 15

    def detect(self, page, ctx=None) -> DetectionResult:
        # Example detection logic
        has_slider = page.locator(".slide-captcha-track").count() > 0
        return DetectionResult(
            detected=has_slider,
            challenge_type=self.name,
            confidence=0.95 if has_slider else 0.0,
            details={"has_slider": has_slider},
        )

    def solve(self, page, ctx=None, *, timeout_s: int = 40, **kwargs) -> SolveResult:
        # Example solving logic
        slider = page.locator(".slide-captcha-handle").first
        if slider.is_visible():
            box = slider.bounding_box()
            if box:
                # Perform drag/slide operation
                page.mouse.move(box["x"] + 10, box["y"] + 10)
                page.mouse.down()
                page.mouse.move(box["x"] + 250, box["y"] + 10, steps=10)
                page.mouse.up()
                return SolveResult(success=True, challenge_type=self.name)

        return SolveResult(success=False, challenge_type=self.name, error="Slider handle not found")


def main():
    # Register the custom plugin
    PluginRegistry.register(CustomSliderPlugin)

    print("Current plugins:")
    for p in PluginRegistry.list_plugins():
        print(f"  - {p['name']}: {p['display_name']} (priority={p['priority']})")


if __name__ == "__main__":
    main()
