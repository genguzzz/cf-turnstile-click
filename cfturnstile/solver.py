"""Wait for a Turnstile token; click the checkbox with Playwright locators.

Click the painted CF widget iframe (not a 1×1 placeholder or the host shell).
Do not use osascript / Quartz screen clicks.

Never evaluate in the page world (``isolated_context=False``). That enables
Runtime in the main world and Cloudflare refuses to load the widget.
Read the token with ``locator.input_value()``.
"""

from __future__ import annotations

import os
import sys
import time

from cfturnstile.browser import chrome_context, extension_dir, launch_extension_args, launch_kwargs
from cfturnstile.errors import TurnstileError

IFRAME_SEL = "iframe[src*='challenges.cloudflare.com']"
TOKEN_SEL = "input[name='cf-turnstile-response'], textarea[name='cf-turnstile-response']"
WIDGET_SEL = ".cf-turnstile"
HEADER_Y = 80.0
CHECKBOX_MAX_W = 240.0
CHECKBOX_MAX_H = 40.0
IFRAME_MIN_W = 200.0
IFRAME_MIN_H = 50.0
WIDGET_CLICK_X = 26.0
WIDGET_CLICK_Y = 32.0


def _dbg(msg: str) -> None:
    if os.environ.get("CF_TURNSTILE_DEBUG", "").strip().lower() in {"1", "true", "yes"}:
        print(f"[cf-turnstile] {msg}", file=sys.stderr, flush=True)


def isolated_eval(page, js: str):
    """Patchright isolated world only. Never pass isolated_context=False."""
    try:
        return page.evaluate(js, isolated_context=True)
    except TypeError:
        return page.evaluate(js)


def checkbox_point(box: dict) -> tuple[float, float]:
    """Real checkbox: its center. Wide a11y row: left square. Else iframe heuristic."""
    source = str(box.get("source") or "")
    w = float(box["width"])
    h = float(box["height"])
    x = float(box["x"])
    y = float(box["y"])
    if "checkbox" in source:
        if w >= 40:
            return x + min(14.0, h / 2.0), y + h / 2.0
        return x + w / 2.0, y + h / 2.0
    return x + min(28.0, max(12.0, w * 0.08)), y + h / 2.0


def looks_like_turnstile_checkbox(box: dict) -> bool:
    """Widget checkbox is a short row below the page header, not a 300×65 shell."""
    try:
        x = float(box["x"])
        y = float(box["y"])
        w = float(box["width"])
        h = float(box["height"])
    except (KeyError, TypeError, ValueError):
        return False
    if y < HEADER_Y:
        return False
    if h < 8 or h > CHECKBOX_MAX_H:
        return False
    if w < 8 or w > CHECKBOX_MAX_W:
        return False
    if x < 0:
        return False
    return True


def _iframe_count(page) -> int:
    try:
        return int(page.locator(IFRAME_SEL).count())
    except Exception:
        return 0


def _iframe_host_box(page, index: int) -> dict | None:
    try:
        box = page.locator(IFRAME_SEL).nth(index).bounding_box(timeout=600)
    except Exception:
        return None
    if not box:
        return None
    return {k: float(box[k]) for k in ("x", "y", "width", "height")}


def is_widget_iframe_box(box: dict) -> bool:
    """Painted managed widget, not the 1×1 placeholder or a header-sized frame."""
    w = float(box.get("width") or 0)
    h = float(box.get("height") or 0)
    y = float(box.get("y") or 0)
    return w >= IFRAME_MIN_W and h >= IFRAME_MIN_H and y >= HEADER_Y


def point_in_box(x: float, y: float, box: dict, pad: float = 0.0) -> bool:
    return (
        float(box["x"]) - pad <= x <= float(box["x"]) + float(box["width"]) + pad
        and float(box["y"]) - pad <= y <= float(box["y"]) + float(box["height"]) + pad
    )


def host_point_is_widget(page, x: float, y: float, iframe_box: dict | None = None) -> bool:
    """Abort if the intended point is in the header or outside the widget iframe."""
    if y < HEADER_Y:
        _dbg(f"abort click: y={y:.0f} is in the header")
        return False
    if iframe_box is not None and not point_in_box(x, y, iframe_box, pad=0):
        _dbg(f"abort click: ({x:.0f},{y:.0f}) outside iframe {iframe_box}")
        return False
    rec = describe_point(page, x, y)
    tag = str(rec.get("tag") or "").upper()
    blob = " ".join(
        str(rec.get(k) or "") for k in ("id", "class", "aria", "title", "text")
    ).lower()
    if tag in {"BUTTON", "A", "SVG", "PATH", "USE", "IMG", "HEADER", "INPUT"}:
        _dbg(f"abort click: host hit is {tag} {rec}")
        return False
    if tag == "IFRAME" or "cf-turnstile" in blob:
        return True
    if tag == "DIV" and y >= HEADER_Y:
        return True
    _dbg(f"abort click: unexpected host hit {rec}")
    return False


def _frame_text_visible(fl, text: str) -> bool:
    """True only when the string is painted. Hidden template text is ignored."""
    try:
        return bool(fl.get_by_text(text, exact=True).first.is_visible(timeout=200))
    except Exception:
        return False


def turnstile_checkbox(page):
    """Checkbox in a painted CF widget iframe below the header. Never ``.first`` on a 1×1 shell."""
    n = _iframe_count(page)
    for i in range(n):
        ibox = _iframe_host_box(page, i)
        if not ibox:
            continue
        if not is_widget_iframe_box(ibox):
            _dbg(
                f"skip iframe[{i}] {ibox['width']:.0f}x{ibox['height']:.0f} "
                f"y={ibox['y']:.0f} (placeholder)"
            )
            continue
        fl = page.frame_locator(IFRAME_SEL).nth(i)
        if _frame_text_visible(fl, "Verifying..."):
            _dbg(f"iframe[{i}] still Verifying... — not clickable")
            continue
        loc = fl.get_by_role("checkbox")
        try:
            loc.first.wait_for(state="visible", timeout=400)
            box = loc.first.bounding_box(timeout=400)
        except Exception:
            continue
        if not box or not looks_like_turnstile_checkbox(box):
            if box:
                _dbg(f"reject iframe[{i}] checkbox box {box}")
            continue
        found = {k: float(box[k]) for k in ("x", "y", "width", "height")}
        found["iframe"] = float(i)
        return loc.first, found
    return None, None


def find_click_box(page, *, verbose: bool = False) -> dict | None:
    """Only the CF iframe checkbox under the header — never a host div / header icon."""
    _loc, found = turnstile_checkbox(page)
    if found and verbose:
        _dbg(f"click-target={found}")
    elif verbose:
        _dbg("click-target=None (checkbox not ready)")
    return found


def log_iframes_and_checkbox(page) -> dict | None:
    n = _iframe_count(page)
    _dbg(f"cf-iframe count={n}")
    for i in range(n):
        ibox = _iframe_host_box(page, i)
        _dbg(f"  cf-iframe[{i}] host={ibox} widget={bool(ibox and is_widget_iframe_box(ibox))}")
    try:
        all_ifr = page.locator("iframe")
        n_all = int(all_ifr.count())
    except Exception:
        n_all = 0
    _dbg(f"all iframe count={n_all}")
    for i in range(min(n_all, 8)):
        try:
            b = all_ifr.nth(i).bounding_box(timeout=400)
        except Exception:
            b = None
        _dbg(f"  iframe[{i}] box={b}")
    try:
        n_host = page.locator(WIDGET_SEL).count()
    except Exception:
        n_host = -1
    _dbg(f"host {WIDGET_SEL!r} count={n_host}")
    return find_click_box(page, verbose=True)


INSTALL_CLICK_TAP_JS = """() => {
  if (globalThis.__cfTsClickTap) return 'already';
  globalThis.__cfTsClickTap = 1;
  globalThis.__cfTsClicks = [];
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
      href: (n.getAttribute('href') || '').slice(0, 80),
      text: String(n.innerText || n.getAttribute('alt') || '').replace(/\\s+/g, ' ').slice(0, 80),
    };
  };
  document.addEventListener('click', (e) => {
    const rec = {
      clientX: e.clientX,
      clientY: e.clientY,
      button: e.button,
      target: desc(e.target),
      path: [],
    };
    let n = e.target;
    for (let i = 0; i < 8 && n; i++) {
      rec.path.push(desc(n));
      n = n.parentElement;
    }
    globalThis.__cfTsClicks.push(rec);
  }, true);
  return 'ok';
}"""

READ_CLICK_TAP_JS = """() => globalThis.__cfTsClicks || []"""


def install_click_tap(page) -> str:
    """Isolated-world click capture on the host page. Not add_init_script, not main world."""
    return str(isolated_eval(page, INSTALL_CLICK_TAP_JS) or "")


def read_click_tap(page) -> list:
    try:
        rec = isolated_eval(page, READ_CLICK_TAP_JS)
    except Exception as e:
        _dbg(f"read_click_tap fail ({e!r})")
        return []
    return rec if isinstance(rec, list) else []


def describe_point(page, x: float, y: float) -> dict:
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
        return {"x": x, "y": y, "error": type(e).__name__}


def dump_page_controls(page) -> None:
    """Debug: host-page checkbox/switch locators."""
    for role in ("checkbox", "switch"):
        loc = page.get_by_role(role)
        try:
            n = loc.count()
        except Exception as e:
            _dbg(f"page role={role} count fail ({e!r})")
            continue
        _dbg(f"page role={role} count={n}")
        for i in range(min(n, 12)):
            item = loc.nth(i)
            try:
                box = item.bounding_box()
            except Exception:
                box = None
            name = title = None
            try:
                name = item.get_attribute("aria-label")
            except Exception:
                pass
            try:
                title = item.get_attribute("title")
            except Exception:
                pass
            _dbg(f"  [{i}] aria={name!r} title={title!r} box={box}")


def token_from_locator(page) -> str:
    loc = page.locator(TOKEN_SEL).first
    try:
        loc.wait_for(state="attached", timeout=1500)
        val = loc.input_value(timeout=800)
        if val and len(val) > 20:
            return str(val)
    except Exception:
        return ""
    return ""


def widget_state(page) -> str:
    """Extension monitor writes ``html[data-cf-ts-state]``. Often empty on stock Chrome."""
    try:
        return str(page.locator("html").first.get_attribute("data-cf-ts-state", timeout=400) or "")
    except Exception:
        return ""


def challenge_status(page) -> dict:
    """Detect checkbox / Success / token without relying on the extension monitor."""
    tok = token_from_locator(page)
    cb_n = 0
    success = False
    verifying = False
    n = _iframe_count(page)
    for i in range(n):
        ibox = _iframe_host_box(page, i)
        if not ibox or not is_widget_iframe_box(ibox):
            continue
        fl = page.frame_locator(IFRAME_SEL).nth(i)
        if _frame_text_visible(fl, "Verifying..."):
            verifying = True
            continue
        if _frame_text_visible(fl, "Success!"):
            success = True
            continue
        try:
            loc = fl.get_by_role("checkbox")
            loc.first.wait_for(state="visible", timeout=300)
            cb_n += loc.count()
        except Exception:
            pass
    return {
        "token": bool(tok),
        "token_len": len(tok or ""),
        "checkbox": cb_n,
        "success": success,
        "verifying": verifying,
        "ext_state": widget_state(page),
    }


def wait_widget_attached(page, timeout_ms: int) -> None:
    """Wait for a painted CF widget iframe below the header. Ignore 1×1 shells."""
    deadline = time.time() + timeout_ms / 1000.0
    last = None
    while time.time() < deadline:
        if token_from_locator(page):
            return
        n = _iframe_count(page)
        for i in range(n):
            ibox = _iframe_host_box(page, i)
            last = ibox
            if ibox and is_widget_iframe_box(ibox):
                return
        time.sleep(0.25)
    raise TurnstileError(
        "Turnstile widget did not load (challenges.cloudflare.com). "
        f"last={last}"
    )


def click_checkbox_locator(page) -> str:
    """Click the painted CF widget iframe at the checkbox square."""
    install_click_tap(page)
    n = _iframe_count(page)
    for i in range(n):
        host = page.locator(IFRAME_SEL).nth(i)
        try:
            handle = host.element_handle(timeout=600)
        except Exception:
            handle = None
        if handle is None:
            continue
        ibox = handle.bounding_box()
        if not ibox or not is_widget_iframe_box(ibox):
            if ibox:
                _dbg(
                    f"skip iframe[{i}] {ibox['width']:.0f}x{ibox['height']:.0f} "
                    f"y={ibox['y']:.0f} (placeholder)"
                )
            continue
        fl = page.frame_locator(IFRAME_SEL).nth(i)
        if _frame_text_visible(fl, "Verifying..."):
            _dbg(f"iframe[{i}] still Verifying... — not clickable")
            continue
        loc = fl.get_by_role("checkbox")
        try:
            loc.first.wait_for(state="visible", timeout=400)
        except Exception:
            continue
        ibox = handle.bounding_box()
        if not ibox or not is_widget_iframe_box(ibox):
            _dbg(f"iframe[{i}] moved/shrank before click {ibox}")
            continue
        vx = float(ibox["x"]) + WIDGET_CLICK_X
        vy = float(ibox["y"]) + WIDGET_CLICK_Y
        if not host_point_is_widget(page, vx, vy, ibox):
            continue
        _dbg(f"click iframe[{i}] ibox={ibox} at ({vx:.1f},{vy:.1f})")
        _dbg(f"elementFromPoint={describe_point(page, vx, vy)}")
        handle.click(
            position={"x": WIDGET_CLICK_X, "y": WIDGET_CLICK_Y},
            timeout=4000,
            delay=80,
            force=True,
        )
        _dbg(f"host click events: {read_click_tap(page)}")
        return "locator-iframe"
    return "locator-miss"


def solve(page, timeout_s: int = 40) -> str:
    """Click the Turnstile checkbox on an already-open page and return the token.

    ``page`` is a Patchright/Playwright page that already shows the widget.
    """
    early = token_from_locator(page)
    if early:
        return early
    wait_widget_attached(page, min(20_000, timeout_s * 1000))
    _dbg("widget attached")
    if os.environ.get("CF_TURNSTILE_DEBUG", "").strip().lower() in {"1", "true", "yes"}:

        def _con(msg) -> None:
            text = ""
            try:
                text = str(msg.text)
            except Exception:
                return
            if "cf-turnstile-click" in text or "challenges.cloudflare" in text:
                _dbg(f"console {text[:180]}")

        try:
            page.on("console", _con)
        except Exception:
            pass
    # Wait for an idle checkbox (not Verifying..., not a 1×1 shell). Empty 300×65 is not ready.
    ready_deadline = time.time() + min(15.0, timeout_s)
    while time.time() < ready_deadline:
        if token_from_locator(page):
            break
        st = challenge_status(page)
        if st.get("verifying"):
            time.sleep(0.25)
            continue
        _cb, box = turnstile_checkbox(page)
        if box:
            break
        time.sleep(0.25)
    deadline = time.time() + timeout_s
    clicked = False
    last_tick = 0.0
    last_status = None
    stable = 0
    last_box = None
    while time.time() < deadline:
        st = challenge_status(page)
        tok = token_from_locator(page)
        if tok:
            _dbg(f"token len={len(tok)} status={st}")
            return tok
        now = time.time()
        if st != last_status or now - last_tick >= 5:
            _dbg(f"waiting status={st} clicked={clicked} stable={stable}")
            last_tick = now
            last_status = st
        if st.get("verifying"):
            stable = 0
            last_box = None
            time.sleep(0.4)
            continue
        if not clicked and not tok:
            box = find_click_box(page, verbose=True)
            if not box:
                stable = 0
                last_box = None
                time.sleep(0.4)
                continue
            same = (
                last_box is not None
                and abs(box["x"] - last_box["x"]) < 2
                and abs(box["y"] - last_box["y"]) < 2
            )
            last_box = box
            if not same:
                stable = 1
                time.sleep(0.4)
                continue
            stable += 1
            if stable < 2:
                time.sleep(0.4)
                continue
            kind = click_checkbox_locator(page)
            _dbg(f"clicked kind={kind} box={box}")
            clicked = kind != "locator-miss"
            if not clicked:
                stable = 0
                last_box = None
            elif os.environ.get("CF_TURNSTILE_DEBUG", "").strip().lower() in {"1", "true", "yes"}:
                try:
                    page.screenshot(path="/tmp/cf-turnstile-after-click.png", full_page=True)
                    _dbg("screenshot /tmp/cf-turnstile-after-click.png")
                except Exception:
                    pass
        time.sleep(0.4)
    try:
        page.screenshot(path="/tmp/cf-turnstile-fail.png", full_page=True)
    except Exception:
        pass
    raise TurnstileError(
        "Turnstile checkbox produced no token. "
        "Use headed Chrome and iframe locator click. "
        "screenshot=/tmp/cf-turnstile-fail.png"
    )


def solve_url(url: str, *, timeout_s: int = 45, headless: bool = False, wait_until: str = "domcontentloaded") -> str:
    """Open ``url`` in patched Chrome, solve Turnstile, return the token."""
    with chrome_context(headless=headless) as (page, _ctx):
        page.goto(url, wait_until=wait_until, timeout=timeout_s * 1000)
        return solve(page, timeout_s=timeout_s)


__all__ = [
    "IFRAME_SEL",
    "TOKEN_SEL",
    "WIDGET_SEL",
    "challenge_status",
    "checkbox_point",
    "describe_point",
    "dump_page_controls",
    "install_click_tap",
    "read_click_tap",
    "chrome_context",
    "click_checkbox_locator",
    "extension_dir",
    "isolated_eval",
    "log_iframes_and_checkbox",
    "launch_extension_args",
    "launch_kwargs",
    "is_widget_iframe_box",
    "point_in_box",
    "looks_like_turnstile_checkbox",
    "solve",
    "solve_url",
    "token_from_locator",
    "turnstile_checkbox",
    "wait_widget_attached",
    "widget_state",
]
