"""Dynamic script injection and evaluation in isolated or main contexts."""

from __future__ import annotations

import json
from typing import Any

from bypass.config import debug_log


def isolated_eval(target, js: str) -> Any:
    """Execute JavaScript in Patchright isolated world.

    Never falls back to main world to prevent runtime detection.
    """
    try:
        return target.evaluate(js, isolated_context=True)
    except TypeError:
        # If the target method doesn't support isolated_context argument
        return target.evaluate(js)
    except Exception as e:
        debug_log(f"isolated_eval error: {e}")
        raise


def main_eval(target, js: str) -> Any:
    """Execute JavaScript in the main world when interacting with page globals is needed."""
    try:
        return target.evaluate(js, isolated_context=False)
    except TypeError:
        return target.evaluate(js)
    except Exception as e:
        debug_log(f"main_eval error: {e}")
        raise


def inject_script(
    page,
    script_text: str,
    *,
    world: str = "isolated",
    frame_index: int | None = None,
) -> Any:
    """Inject and evaluate a custom script in the page or specified iframe.

    world: 'isolated' (default, stealth) or 'main' (page global scope)
    """
    target = page
    if frame_index is not None and frame_index >= 0:
        all_frames = page.frames
        if frame_index < len(all_frames):
            target = all_frames[frame_index]
        else:
            raise IndexError(f"Frame index {frame_index} out of range ({len(all_frames)} frames)")

    # Normalize script into an immediately invoked function if not already
    trimmed = script_text.strip()
    if not trimmed.startswith("(") and not trimmed.startswith("function") and not trimmed.startswith("()"):
        js = f"() => {{\n{trimmed}\n}}"
    else:
        js = trimmed

    if world == "main":
        return main_eval(target, js)
    return isolated_eval(target, js)


INSTALL_CLICK_TAP_JS = """() => {
  if (globalThis.__shieldClickTap) return 'already';
  globalThis.__shieldClickTap = 1;
  globalThis.__shieldClicks = [];
  const desc = (n) => {
    if (!n || n.nodeType !== 1) return {tag: String(n && n.nodeName || '?')};
    return {
      tag: n.tagName,
      id: n.id || '',
      class: String(n.className || '').slice(0, 120),
      role: n.getAttribute('role') || '',
      aria: n.getAttribute('aria-label') || '',
      title: n.getAttribute('title') || '',
      type: n.getAttribute('type') || '',
      name: n.getAttribute('name') || '',
      href: (n.getAttribute('href') || '').slice(0, 80),
      text: String(n.innerText || n.getAttribute('alt') || '').replace(/\\s+/g, ' ').slice(0, 80),
    };
  };
  document.addEventListener('click', (e) => {
    const rec = {
      clientX: e.clientX,
      clientY: e.clientY,
      screenX: e.screenX,
      screenY: e.screenY,
      button: e.button,
      target: desc(e.target),
      path: [],
    };
    let n = e.target;
    for (let i = 0; i < 8 && n; i++) {
      rec.path.push(desc(n));
      n = n.parentElement;
    }
    globalThis.__shieldClicks.push(rec);
  }, true);
  return 'ok';
}"""

READ_CLICK_TAP_JS = """() => globalThis.__shieldClicks || []"""


def install_click_tap(page) -> str:
    """Install click event recorder in isolated context."""
    try:
        return str(isolated_eval(page, INSTALL_CLICK_TAP_JS) or "")
    except Exception:
        return ""


def read_click_tap(page) -> list[dict]:
    """Read recorded click events."""
    try:
        res = isolated_eval(page, READ_CLICK_TAP_JS)
        return res if isinstance(res, list) else []
    except Exception:
        return []
