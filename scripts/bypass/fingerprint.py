"""Fingerprint extraction and session export utilities."""

from __future__ import annotations

import json
from typing import Any

from bypass.config import debug_log
from bypass.injector import isolated_eval

FP_COLLECTOR_JS = """() => {
  const getWebGL = () => {
    try {
      const canvas = document.createElement('canvas');
      const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      if (!gl) return null;
      const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
      return {
        vendor: gl.getParameter(gl.VENDOR),
        renderer: gl.getParameter(gl.RENDERER),
        unmaskedVendor: debugInfo ? gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) : null,
        unmaskedRenderer: debugInfo ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : null,
        glVersion: gl.getParameter(gl.VERSION),
        shadingLanguageVersion: gl.getParameter(gl.SHADING_LANGUAGE_VERSION)
      };
    } catch (_) {
      return null;
    }
  };

  const getCanvasHash = () => {
    try {
      const canvas = document.createElement('canvas');
      canvas.width = 200;
      canvas.height = 50;
      const ctx = canvas.getContext('2d');
      if (!ctx) return null;
      ctx.textBaseline = 'top';
      ctx.font = '14px Arial';
      ctx.textBaseline = 'alphabetic';
      ctx.fillStyle = '#f60';
      ctx.fillRect(125, 1, 62, 20);
      ctx.fillStyle = '#069';
      ctx.fillText('ShieldBypass,123 <canvas>', 2, 15);
      ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
      ctx.fillText('ShieldBypass,123 <canvas>', 4, 17);
      const dataUrl = canvas.toDataURL();
      let hash = 0;
      for (let i = 0; i < dataUrl.length; i++) {
        hash = ((hash << 5) - hash) + dataUrl.charCodeAt(i);
        hash |= 0;
      }
      return 'cv_' + Math.abs(hash).toString(16);
    } catch (_) {
      return null;
    }
  };

  const getClientHints = () => {
    try {
      if (!navigator.userAgentData) return null;
      return {
        brands: navigator.userAgentData.brands || [],
        mobile: navigator.userAgentData.mobile || false,
        platform: navigator.userAgentData.platform || ''
      };
    } catch (_) {
      return null;
    }
  };

  const getTimezone = () => {
    try {
      return {
        name: Intl.DateTimeFormat().resolvedOptions().timeZone,
        offset: new Date().getTimezoneOffset()
      };
    } catch (_) {
      return null;
    }
  };

  return {
    navigator: {
      userAgent: navigator.userAgent,
      platform: navigator.platform,
      language: navigator.language,
      languages: Array.from(navigator.languages || []),
      hardwareConcurrency: navigator.hardwareConcurrency || 4,
      deviceMemory: navigator.deviceMemory || 8,
      maxTouchPoints: navigator.maxTouchPoints || 0,
      vendor: navigator.vendor || '',
      webdriver: navigator.webdriver || false
    },
    screen: {
      width: screen.width,
      height: screen.height,
      availWidth: screen.availWidth,
      availHeight: screen.availHeight,
      colorDepth: screen.colorDepth,
      pixelDepth: screen.pixelDepth,
      devicePixelRatio: window.devicePixelRatio || 1
    },
    clientHints: getClientHints(),
    webgl: getWebGL(),
    canvasHash: getCanvasHash(),
    timezone: getTimezone()
  };
}"""


def extract_fingerprint(page, context) -> dict[str, Any]:
    """Extract complete browser fingerprint, cookies, tokens, and storage."""
    # 1. JS-evaluated fingerprint properties
    try:
        fp_data = isolated_eval(page, FP_COLLECTOR_JS)
        if not isinstance(fp_data, dict):
            fp_data = {}
    except Exception as e:
        debug_log(f"Fingerprint JS extraction error: {e}")
        fp_data = {}

    # 2. Cookies extraction
    cookies: list[dict[str, Any]] = []
    try:
        cookies = context.cookies()
    except Exception as e:
        debug_log(f"Cookies extraction error: {e}")

    cookie_header_parts = [f"{c['name']}={c['value']}" for c in cookies if c.get("name") and c.get("value")]
    cookie_header = "; ".join(cookie_header_parts)

    # 3. Target challenge tokens identification
    tokens: dict[str, str] = {}
    for c in cookies:
        name = c.get("name", "")
        if name in ("cf_clearance", "__cf_bm", "cf_chl_2", "cf_chl_prog", "cf_chl_rc_m", "cto_bundle"):
            tokens[name] = c.get("value", "")

    # Check DOM inputs for response tokens
    for token_name, sel in (
        ("cf-turnstile-response", "input[name='cf-turnstile-response'], textarea[name='cf-turnstile-response']"),
        ("g-recaptcha-response", "textarea[name='g-recaptcha-response']"),
        ("h-captcha-response", "textarea[name='h-captcha-response']"),
    ):
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                val = loc.input_value(timeout=300)
                if val:
                    tokens[token_name] = val
        except Exception:
            pass

    # 4. Storage extraction
    local_storage: dict[str, str] = {}
    session_storage: dict[str, str] = {}
    try:
        local_storage = isolated_eval(page, "() => ({ ...localStorage })") or {}
    except Exception:
        pass
    try:
        session_storage = isolated_eval(page, "() => ({ ...sessionStorage })") or {}
    except Exception:
        pass

    # 5. Suggested HTTP Headers
    ua = (fp_data.get("navigator") or {}).get("userAgent", "")
    ch = fp_data.get("clientHints") or {}
    brands = ch.get("brands") or []
    sec_ch_ua = ", ".join([f'"{b.get("brand", "")}";v="{b.get("version", "")}"' for b in brands if b.get("brand")])
    if not sec_ch_ua and "Chrome/" in ua:
        # Default Chrome 148+ brand string
        sec_ch_ua = '"Chromium";v="148", "Not A(Brand";v="24", "Google Chrome";v="148"'

    headers: dict[str, str] = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-CH-UA": sec_ch_ua,
        "Sec-CH-UA-Mobile": "?0" if not ch.get("mobile") else "?1",
        "Sec-CH-UA-Platform": f'"{ch.get("platform") or "Linux"}"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header

    return {
        "url": page.url,
        "title": page.title() if hasattr(page, "title") else "",
        "fingerprint": fp_data,
        "tokens": tokens,
        "cookies": cookies,
        "cookie_header": cookie_header,
        "headers": headers,
        "storage": {
            "localStorage": local_storage,
            "sessionStorage": session_storage,
        },
    }


def format_curl_cmd(url: str, exported: dict[str, Any]) -> str:
    """Format an executable curl command matching the exported fingerprint."""
    headers = exported.get("headers", {})
    parts = ["curl -sSL", f"'{url}'"]
    for k, v in headers.items():
        if k.lower() == "cookie":
            parts.append(f"-b '{v}'")
        else:
            parts.append(f"-H '{k}: {v}'")
    return " \\\n  ".join(parts)


def format_python_code(url: str, exported: dict[str, Any]) -> str:
    """Format Python code using curl_cffi / requests."""
    headers = exported.get("headers", {})
    ua = headers.get("User-Agent", "")
    cookie_str = exported.get("cookie_header", "")

    return f'''# Python curl_cffi snippet
from curl_cffi import requests

headers = {json.dumps(headers, indent=4)}

response = requests.get(
    "{url}",
    headers=headers,
    impersonate="chrome124",
    timeout=30
)
print("Status:", response.status_code)
print("Content length:", len(response.text))
'''
