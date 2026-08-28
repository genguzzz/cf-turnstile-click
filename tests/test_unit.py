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
    native, client = 26, 26
    assert native < 120 and abs(native - client) < 2
    native_os, client_os = 412, 26
    assert not (native_os < 120 and abs(native_os - client_os) < 2)


def test_launch_kwargs_keep_extensions():
    from cfturnstile import launch_kwargs
    from cfturnstile.browser import find_chrome

    kw = launch_kwargs()
    assert kw["no_viewport"] is True
    assert "--disable-extensions" in kw["ignore_default_args"]
    joined = " ".join(kw["args"])
    assert "--load-extension=" in joined
    assert "--no-sandbox" in joined
    chrome = find_chrome()
    if chrome:
        assert kw.get("executable_path") == chrome
        assert "channel" not in kw
    else:
        assert kw.get("channel") == "chrome"
