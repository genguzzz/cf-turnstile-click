"""Bilibili passport login Geetest v3 word-click (文字点选) captcha plugin.

Target: https://passport.bilibili.com/login

Challenge type: Geetest v3 "文字点选" (word click) captcha — embedded in-page,
NOT an iframe. DOM layout (already analysed against the live page):
  - .geetest_holder.geetest_silver      captcha panel
  - .geetest_item_wrap                  clickable image area (bg-image in style)
  - .geetest_item_img                   image element (same area)
  - .geetest_tip_text                   prompt characters in order (after load)
  - .geetest_commit_tip / .geetest_commit  confirm button (disabled until all clicked)
  - .geetest_item_loading               loading overlay

Recognition is NOT OCR. The plugin inherits the recognition pipeline from the
open-source project MgArcher/Text_select_captcha (vendored into
`bypass.geetest`): YOLO detects the prompt chars (class=0) and the picture
chars (class=2), a Siamese network scores every prompt/picture char pair, and
greedy matching orders the click points by the prompt sequence.

Click simulation follows the upstream `bilbil.py`: wait for the image wrapper,
extract the background URL from the style attribute, download the original
image, run the model, map image coords -> page coords using the display scale,
then `page.mouse.click()` on each point (with pauses) and finally click the
"确认" button.

Known limitation: the inherited `best_v3.onnx` YOLO is trained on bilibili's
"Chinese word-click" sub-variant (汉字点选). When bilibili serves the
"icon-style" sub-variant (icon/icon-click), YOLO returns no class=2
detections because icons aren't Chinese characters, and the solver reports
`recognizer returned no points`. The plugin structure still detects the
captcha correctly (detection fires) — only recognition fails until a model
trained on the icon variant is added.
"""

from __future__ import annotations

import re
import time
from typing import Any

from bypass.config import debug_log
from bypass.injector import isolated_eval
from bypass.plugins.base import BaseChallengePlugin, DetectionResult, SolveResult

try:
    import cv2
    import numpy as np
    _CV_OK = True
except Exception:  # pragma: no cover
    _CV_OK = False

# The vendored recognizer lives inside the bypass package so no external
# checkout of Text_select_captcha is needed at runtime.
try:
    from bypass.geetest import TextSelectCaptcha
    _GEETEST_OK = True
except Exception:  # pragma: no cover
    _GEETEST_OK = False

_HOLDER_SEL = ".geetest_holder.geetest_silver"
_WRAP_SEL = ".geetest_item_wrap"
_IMG_SEL = ".geetest_item_img"
_TIP_SEL = ".geetest_tip_text"
_COMMIT_SEL = ".geetest_commit"


def _read_holder_state(page) -> dict[str, Any]:
    """Snapshot the bilibili geetest captcha state from DOM (isolated world)."""
    js = """() => {
      const q = (s) => document.querySelector(s);
      const wrap = q('.geetest_item_wrap');
      const img = q('.geetest_item_img');
      const loading = q('.geetest_item_loading');
      const tip = q('.geetest_tip_text');
      const commit = q('.geetest_commit');
      const holder = q('.geetest_holder.geetest_silver');
      let bg = '';
      if (wrap) {
        const st = wrap.getAttribute('style') || '';
        const m = st.match(/url\\(["']?(.*?)["']?\\)/);
        bg = m ? m[1] : '';
      }
      const rect = (el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {x: r.left, y: r.top, w: r.width, h: r.height};
      };
      return {
        visible: holder ? holder.offsetParent !== null : false,
        loaded: loading ? loading.offsetParent === null : true,
        bgUrl: bg,
        tip: tip ? tip.innerText : '',
        wrapRect: rect(wrap),
        imgRect: rect(img),
        commitRect: rect(commit),
        commitDisabled: commit ? /geetest_disable/.test(commit.className) : true,
        url: location.href,
      };
    }"""
    try:
        return isolated_eval(page, js) or {}
    except Exception as e:
        debug_log(f"read_holder_state failed: {e}")
        return {}


def _download(url: str, referer: str) -> bytes:
    """Download the captcha background image (direct connection, no browser)."""
    import urllib.request
    req = urllib.request.Request(
        url,
        headers={
            "Referer": referer,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


class BilibiliGeetestPlugin(BaseChallengePlugin):
    """Solver for the bilibili passport login Geetest v3 word-click captcha."""

    name = "bilibili_geetest"
    display_name = "Bilibili Passport Geetest Word-Click"
    priority = 8

    # ---- detection ----------------------------------------------------------

    def detect(self, page, ctx=None) -> DetectionResult:
        res = DetectionResult(challenge_type=self.name)
        if not page or not getattr(page, "url", ""):
            return res
        if "bilibili.com" not in page.url:
            return res
        st = _read_holder_state(page)
        if not st.get("visible"):
            return res
        if st.get("bgUrl"):
            res.detected = True
            res.confidence = 0.95
            res.details = {"reason": "holder_visible_with_bg", "wrapRect": st.get("wrapRect")}
            return res
        res.detected = True
        res.confidence = 0.5
        res.details = {"reason": "holder_visible"}
        return res

    # ---- solve --------------------------------------------------------------

    def solve(self, page, ctx=None, *, timeout_s: int = 90, **kwargs) -> SolveResult:
        debug_log("starting bilibili geetest word-click solver")

        if not _GEETEST_OK or not _CV_OK:
            return SolveResult(
                success=False,
                challenge_type=self.name,
                error="recognizer unavailable: need opencv/numpy + vendored Text_select_captcha code",
            )

        # 1. Wait for the captcha wrapper with a background image (same as
        #    upstream bilbil.py: it only needs the wrapper + img element; the
        #    "loading" state in headless/attach sessions is ignored because the
        #    bg URL in style is already present).
        deadline = time.time() + min(20, timeout_s)
        st: dict[str, Any] = {}
        while time.time() < deadline:
            st = _read_holder_state(page)
            if st.get("bgUrl") and st.get("wrapRect") and st["wrapRect"]["w"] > 50:
                break
            time.sleep(0.4)
        if not st.get("bgUrl"):
            return SolveResult(
                success=False,
                challenge_type=self.name,
                error="captcha background image never appeared",
            )

        bg_url = st["bgUrl"]
        wrap = st["wrapRect"]
        img_rect = st.get("imgRect") or wrap
        debug_log(f"bg url={bg_url[:120]} wrap=({wrap['w']}x{wrap['h']})")

        # 2. Download the original image and run YOLO + Siamese recognition
        try:
            img_bytes = _download(bg_url, page.url)
        except Exception as e:
            return SolveResult(success=False, challenge_type=self.name, error=f"image download failed: {e}")

        try:
            cap = TextSelectCaptcha()
            plan = cap.run_dict(img_bytes)
        except Exception as e:
            return SolveResult(success=False, challenge_type=self.name, error=f"recognition failed: {e}")

        points = plan.get("point") or []
        if not points:
            return SolveResult(success=False, challenge_type=self.name, error="recognizer returned no points")

        orig_w = plan.get("imgW")
        orig_h = plan.get("imgH")
        debug_log(f"recognized {len(points)} points on {orig_w}x{orig_h} image")

        # 3. Map original-image coords -> page coords (upstream bilbil.py logic:
        #    scale_x = display_w / orig_w, scale_y = display_h / orig_h)
        display_w = img_rect["w"] or wrap["w"]
        display_h = img_rect["h"] or wrap["h"]
        scale_x = display_w / orig_w if orig_w else 1.0
        scale_y = display_h / orig_h if orig_h else 1.0
        page_points = []
        for pt in points:
            click_x = wrap["x"] + pt["x_rel"] * scale_x
            click_y = wrap["y"] + pt["y_rel"] * scale_y
            page_points.append((click_x, click_y))
        debug_log(f"display {display_w}x{display_h} scale=({scale_x:.3f},{scale_y:.3f})")
        debug_log(f"page click points: {page_points}")

        # 4. Click each target (human-like pauses between clicks, like upstream)
        for i, (cx, cy) in enumerate(page_points):
            page.mouse.move(cx, cy)
            page.mouse.down()
            time.sleep(0.05 + 0.02 * (i % 3))
            page.mouse.up()
            time.sleep(0.6 + 0.15 * (i % 3))  # avoid anti-bot on rapid clicks

        # 5. Click 确认 (commit). Upstream clicks `.geetest_commit_tip`; we try
        #    the commit button rect first, then fall back to JS click.
        page.wait_for_timeout(500)
        commit = st.get("commitRect")
        clicked_commit = False
        if commit and commit.get("w", 0) > 0:
            cx = commit["x"] + commit["w"] / 2
            cy = commit["y"] + commit["h"] / 2
            page.mouse.move(cx, cy)
            page.mouse.click(cx, cy)
            clicked_commit = True
        if not clicked_commit:
            isolated_eval(page, "() => { const b = document.querySelector('.geetest_commit'); if (b) b.click(); }")

        # 6. Wait for outcome: panel closes (success) or failure tip appears
        deadline = time.time() + max(10, timeout_s - 30)
        while time.time() < deadline:
            st2 = _read_holder_state(page)
            if not st2.get("visible"):
                debug_log("captcha panel closed -> success")
                return SolveResult(
                    success=True,
                    challenge_type=self.name,
                    data={"points": page_points, "bg": bg_url[:120]},
                )
            tip2 = st2.get("tip") or ""
            if "再试一次" in tip2 or "失败" in tip2 or "错误" in tip2:
                debug_log(f"captcha failure: {tip2}")
                return SolveResult(
                    success=False,
                    challenge_type=self.name,
                    error=f"geetest: {tip2}",
                    data={"points": page_points},
                )
            time.sleep(0.5)

        return SolveResult(
            success=False,
            challenge_type=self.name,
            error="timeout waiting for captcha outcome",
            data={"points": page_points},
        )