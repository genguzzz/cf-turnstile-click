# cf-turnstile-click

Drop-in **Cloudflare Turnstile checkbox** helper for [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python) / Playwright.

给已有脚本加上「自动点 Turnstile 勾选框、取出 token」：系统级点击 + Chrome 扩展修补 CDP 跨域 iframe 的 `screenX/Y` 泄漏。不伪造 token，不改 Cloudflare 脚本。

## Why Patchright `mouse.click` is not enough

`turnstile/v0/api.js` only creates the iframe / hidden `cf-turnstile-response`. The bot check lives **inside** the cross-origin iframe:

1. **`Runtime.enable`** — stock Playwright is detected; the widget fires `error-callback` (“人机验证服务加载失败”). Use Patchright. Never `page.evaluate(..., isolated_context=False)`.
2. **CDP click in the iframe** — `MouseEvent.screenX` is relative to the iframe (&lt; 100). A real click is relative to the display (hundreds). `page.mouse.click` fails on Patchright, Selenium, nodriver, etc. ([write-up](https://webscraper.io/blog/google-patches-100-precise-cloudflare-turnstile-bot-check)).
3. Token is a **hidden** input — wait `state="attached"`, read `locator.input_value()`, do not `wait_for(visible)`.

This repo:

- launches **system Chrome** via Patchright (`channel=chrome`, `no_viewport`, no `--enable-automation`)
- loads `cfturnstile/ext/` (`world: MAIN`, `all_frames`) to rewrite iframe `screenX/Y` when they look like the CDP leak (`screenX ≈ clientX` and `&lt; 120`)
- clicks the checkbox with **OS mouse** (macOS Quartz, Linux `xdotool`, Windows `mouse_event`), CDP click as fallback

Inspired by [Theyka/Turnstile-Solver](https://github.com/Theyka/Turnstile-Solver), [ObjectAscended screenX patcher](https://github.com/ObjectAscended/CDP-bug-MouseEvent-.screenX-.screenY-patcher), and [cdp-patches](https://github.com/Kaliiiiiiiiii-Vinyzu/CDP-Patches) (Windows/Linux only; we add macOS).

## Install

```bash
pip install "git+https://github.com/genguzzz/cf-turnstile-click.git"
python -m patchright install chrome   # or use the Chrome already on the machine
```

macOS: grant **Accessibility** to the app that launches Chrome (Terminal / iTerm / Cursor). Keep the Chrome window visible. Headless usually fails.

## Integrate (copy-paste)

**Already have a Patchright page:**

```python
from cfturnstile import solve

token = solve(page)   # clicks checkbox if needed, returns cf-turnstile-response
```

**You launch the browser:**

```python
from patchright.sync_api import sync_playwright
from cfturnstile import launch_kwargs, solve

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context("/tmp/cf-profile", **launch_kwargs())
    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://example.com/login")
    token = solve(page)
    context.close()
```

**One-shot URL:**

```python
from cfturnstile import solve_url

token = solve_url("https://example.com/login")
```

**Context manager:**

```python
from cfturnstile import chrome_context, solve

with chrome_context() as (page, context):
    page.goto("https://example.com/login")
    page.fill("#email", "you@example.com")
    token = solve(page)
    page.click("button[type=submit]")
    cookies = context.cookies()
```

**CLI:**

```bash
cf-turnstile --url 'https://example.com/login' -v
# token on stdout
```

Do **not**:

- `page.evaluate(..., isolated_context=False)`
- `add_init_script` / custom User-Agent (Patchright detection)
- click the Turnstile iframe with `page.mouse` only (use `solve()`)

## Env

| var | meaning |
|-----|---------|
| `CF_TURNSTILE_DEBUG=1` | stderr progress |
| `CF_TURNSTILE_HEADLESS=1` | force headless (usually worse) |

## API

| symbol | role |
|--------|------|
| `solve(page, timeout_s=25) -> str` | widget on current page → token |
| `solve_url(url, ...) -> str` | open URL → token |
| `chrome_context()` | `(page, context)` |
| `launch_kwargs()` | for your own `launch_persistent_context` |
| `TurnstileError` | load / click / token failure |

## License

MIT. Use on sites you are allowed to automate. This does not bypass Cloudflare by forging tokens.
