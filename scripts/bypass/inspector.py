"""DOM and iframe inspection utilities for challenge detection and debugging."""

from __future__ import annotations

from typing import Any

from bypass.config import debug_log
from bypass.injector import isolated_eval

FAST_INSPECT_JS = """() => {
  const iframes = Array.from(document.querySelectorAll('iframe')).map((f, i) => {
    const r = f.getBoundingClientRect();
    const src = f.src || f.getAttribute('src') || '';
    const srcL = src.toLowerCase();
    let challengeType = null;
    if (srcL.includes('challenges.cloudflare.com') || srcL.includes('turnstile') || (f.id && f.id.includes('cf-chl'))) {
      challengeType = 'cf_turnstile';
    } else if (srcL.includes('recaptcha')) {
      challengeType = 'recaptcha';
    } else if (srcL.includes('hcaptcha')) {
      challengeType = 'hcaptcha';
    }
    let text = '';
    try {
      if (f.contentDocument && f.contentDocument.body) {
        text = f.contentDocument.body.innerText.replace(/\\s+/g, ' ').slice(0, 100);
      }
    } catch (_) {}

    return {
      index: i,
      src: src,
      name: f.name || '',
      id: f.id || '',
      box: { x: Math.round(r.left), y: Math.round(r.top), width: Math.round(r.width), height: Math.round(r.height) },
      visible: r.width > 1 && r.height > 1,
      challenge_type: challengeType,
      text: text
    };
  });

  const tokens = {};
  const cfTok = document.querySelector("input[name='cf-turnstile-response'], textarea[name='cf-turnstile-response'], [id^='cf-chl-widget-']");
  if (cfTok && cfTok.value && cfTok.value.length > 20) tokens['cf_turnstile'] = cfTok.value;

  const gTok = document.querySelector("textarea[name='g-recaptcha-response']");
  if (gTok && gTok.value && gTok.value.length > 20) tokens['g_recaptcha'] = gTok.value;

  const hTok = document.querySelector("textarea[name='h-captcha-response']");
  if (hTok && hTok.value && hTok.value.length > 20) tokens['h_captcha'] = hTok.value;

  return {
    url: window.location.href,
    title: document.title,
    iframes: iframes,
    tokens: tokens
  };
}"""


def inspect_iframes(page) -> list[dict[str, Any]]:
    """Fast deep inspect all iframes on the page in a single evaluate call."""
    try:
        data = isolated_eval(page, FAST_INSPECT_JS)
        if isinstance(data, dict) and "iframes" in data:
            return data["iframes"]
    except Exception as e:
        debug_log(f"inspect_iframes fast path failed: {e}")

    # Fallback to locator
    results: list[dict[str, Any]] = []
    try:
        frames_locator = page.locator("iframe")
        count = int(frames_locator.count())
        for i in range(count):
            loc = frames_locator.nth(i)
            box = None
            try:
                b = loc.bounding_box(timeout=200)
                if b:
                    box = {k: round(float(b[k]), 1) for k in ("x", "y", "width", "height")}
            except Exception:
                pass
            src = loc.get_attribute("src", timeout=200) or ""
            src_lower = src.lower()
            ch_type = None
            if "challenges.cloudflare.com" in src_lower or "turnstile" in src_lower:
                ch_type = "cf_turnstile"
            elif "recaptcha" in src_lower:
                ch_type = "recaptcha"
            elif "hcaptcha" in src_lower:
                ch_type = "hcaptcha"
            results.append({
                "index": i,
                "src": src,
                "name": loc.get_attribute("name", timeout=200) or "",
                "id": loc.get_attribute("id", timeout=200) or "",
                "box": box,
                "visible": bool(box and box["width"] > 1 and box["height"] > 1),
                "challenge_type": ch_type,
                "text": "",
            })
    except Exception:
        pass
    return results


def describe_point(page, x: float, y: float) -> dict[str, Any]:
    """Describe the DOM element located at (x, y) coordinates."""
    js = f"""() => {{
      const x = {float(x)}, y = {float(y)};
      const n = document.elementFromPoint(x, y);
      if (!n || n.nodeType !== 1) return {{x, y, tag: n ? n.nodeName : null}};
      return {{
        x, y,
        tag: n.tagName,
        id: n.id || '',
        class: String(n.className || '').slice(0, 120),
        role: n.getAttribute('role') || '',
        aria: n.getAttribute('aria-label') || '',
        title: n.getAttribute('title') || '',
        type: n.getAttribute('type') || '',
        text: String(n.innerText || '').replace(/\\s+/g, ' ').slice(0, 80),
      }};
    }}"""
    try:
        rec = isolated_eval(page, js)
        return rec if isinstance(rec, dict) else {"x": x, "y": y}
    except Exception as e:
        return {"x": x, "y": y, "error": str(e)}


FAST_CONTROLS_JS = """() => {
  const selectors = ['input', 'button', 'textarea', '[role="checkbox"]', '[role="button"]', '.cf-turnstile'];
  const res = [];
  selectors.forEach(sel => {
    const els = Array.from(document.querySelectorAll(sel)).slice(0, 15);
    els.forEach((el, idx) => {
      const r = el.getBoundingClientRect();
      res.push({
        selector: sel,
        index: idx,
        tag: el.tagName.toLowerCase(),
        id: el.id || '',
        name: el.name || el.getAttribute('name') || '',
        type: el.type || el.getAttribute('type') || '',
        role: el.getAttribute('role') || '',
        box: { x: Math.round(r.left), y: Math.round(r.top), width: Math.round(r.width), height: Math.round(r.height) }
      });
    });
  });
  return res;
}"""


def dump_page_controls(page) -> list[dict[str, Any]]:
    """List interactive controls and inputs on the page in a single pass."""
    try:
        data = isolated_eval(page, FAST_CONTROLS_JS)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def detect_page_state(page) -> dict[str, Any]:
    """Capture a fast snapshot of page title, URL, challenge tokens, and state."""
    try:
        data = isolated_eval(page, FAST_INSPECT_JS)
        if isinstance(data, dict):
            title = data.get("title", "")
            url = data.get("url", "")
            iframes = data.get("iframes", [])
            tokens = data.get("tokens", {})
            challenge_iframes = [f for f in iframes if f.get("challenge_type")]
            is_cf_5s = "Just a moment" in title or "Attention Required" in title or "Cloudflare" in title

            return {
                "url": url,
                "title": title,
                "is_cloudflare_waf": is_cf_5s,
                "tokens": tokens,
                "has_tokens": bool(tokens),
                "total_iframes": len(iframes),
                "challenge_iframes": challenge_iframes,
            }
    except Exception:
        pass

    title = page.title() if hasattr(page, "title") else ""
    return {
        "url": page.url if hasattr(page, "url") else "",
        "title": title,
        "is_cloudflare_waf": "Just a moment" in title or "Cloudflare" in title,
        "tokens": {},
        "has_tokens": False,
        "total_iframes": 0,
        "challenge_iframes": [],
    }
