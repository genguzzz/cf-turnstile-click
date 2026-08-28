from cfturnstile.os_click import viewport_point_to_screen
from cfturnstile.solver import checkbox_point, extension_dir


def test_checkbox_point_and_screen_map():
    box = {"x": 100.0, "y": 200.0, "width": 300.0, "height": 65.0}
    x, y = checkbox_point(box)
    assert 112 <= x <= 128
    assert y == 232.5
    sx, sy = viewport_point_to_screen(
        {"screenX": 40, "screenY": 80, "outerW": 1280, "outerH": 800, "innerW": 1280, "innerH": 720},
        x,
        y,
    )
    assert sx == 40 + x
    assert sy == 80 + 80 + y


def test_extension_files():
    ext = extension_dir()
    assert (ext / "manifest.json").is_file()
    js = (ext / "script.js").read_text(encoding="utf-8")
    assert "PointerEvent" in js
    assert "screenX" in js
    assert "__cfTurnstileClickPatch" in js


def test_cdp_iframe_screen_leak_heuristic():
    # CDP: screenX == clientX < 120
    native, client = 26, 26
    assert native < 120 and abs(native - client) < 2
    # Linux XTEST inside the Turnstile iframe: screenX is the widget offset
    # (~50–90), not clientX. Old heuristic missed this and CF discarded the click.
    native_xtest, client_xtest = 74, 26
    assert native_xtest < 120 and abs(native_xtest - client_xtest) >= 2
    # Real macOS OS click (display coordinates) must stay untouched.
    native_os, client_os = 412, 26
    assert native_os >= 120


def test_extension_patches_iframe_xtest_offset():
    js = (extension_dir() / "script.js").read_text(encoding="utf-8")
    assert "inIframe" in js
    assert "needsPatch" in js
    assert "framed" in js
    manifest = (extension_dir() / "manifest.json").read_text(encoding="utf-8")
    assert "match_origin_as_fallback" in manifest


def test_launch_kwargs_keep_extensions():
    from cfturnstile import launch_kwargs
    from cfturnstile.browser import find_chrome

    kw = launch_kwargs()
    assert kw["no_viewport"] is True
    assert "--disable-extensions" in kw["ignore_default_args"]
    joined = " ".join(kw["args"])
    assert "--load-extension=" in joined
    assert "--ozone-platform=x11" in joined
    assert "ExtensionsMenuAccessControl" in joined
    assert "--no-sandbox" in joined
    chrome = find_chrome()
    if chrome:
        assert kw.get("executable_path") == chrome
        assert "channel" not in kw
    else:
        assert kw.get("channel") == "chrome"
