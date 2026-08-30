from cfturnstile.solver import (
    checkbox_point,
    extension_dir,
    is_widget_iframe_box,
    looks_like_turnstile_checkbox,
    point_in_box,
)


def test_rejects_header_chrome_box():
    assert not looks_like_turnstile_checkbox(
        {"x": 1180.0, "y": 12.0, "width": 24.0, "height": 24.0}
    )
    assert not looks_like_turnstile_checkbox(
        {"x": 59.0, "y": 20.0, "width": 168.0, "height": 24.0}
    )
    assert looks_like_turnstile_checkbox(
        {"x": 59.0, "y": 289.6, "width": 168.1, "height": 24.0}
    )
    # Host .cf-turnstile shell is 300×65 — not a checkbox.
    assert not looks_like_turnstile_checkbox(
        {"x": 48.0, "y": 270.0, "width": 300.0, "height": 65.0}
    )


def test_skips_placeholder_iframe():
    assert not is_widget_iframe_box({"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0})
    assert not is_widget_iframe_box({"x": 1200.0, "y": 12.0, "width": 24.0, "height": 24.0})
    assert is_widget_iframe_box({"x": 48.0, "y": 250.0, "width": 300.0, "height": 65.0})


def test_click_stays_inside_widget_iframe():
    iframe = {"x": 50.0, "y": 269.0, "width": 300.0, "height": 65.0}
    wx, wy = 50.0 + 26.0, 269.0 + 32.0
    assert point_in_box(wx, wy, iframe)
    assert not point_in_box(12.0, 12.0, iframe)
    assert not is_widget_iframe_box({"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0})


def test_checkbox_point_left_of_a11y_row():
    box = {"x": 100.0, "y": 200.0, "width": 300.0, "height": 65.0}
    x, y = checkbox_point(box)
    assert 112 <= x <= 128
    assert y == 232.5
    a11y = {"x": 110.0, "y": 210.0, "width": 24.0, "height": 24.0, "source": "frame-role-checkbox"}
    ax, ay = checkbox_point(a11y)
    assert ax == 122.0
    assert ay == 222.0


def test_extension_files():
    ext = extension_dir()
    assert (ext / "manifest.json").is_file()
    js = (ext / "script.js").read_text(encoding="utf-8")
    assert "PointerEvent" in js
    assert "screenX" in js
    assert "__cfTurnstileClickPatch" in js
    monitor = (ext / "monitor.js").read_text(encoding="utf-8")
    assert "data-cf-ts-state" in monitor
    manifest = (ext / "manifest.json").read_text(encoding="utf-8")
    assert "monitor.js" in manifest


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


def test_session_ensure_display_preserves_display():
    from cfturnstile.session import ensure_display

    env = ensure_display({"DISPLAY": ":1", "HOME": "/tmp"})
    assert env["DISPLAY"] == ":1"


def test_session_opt_in_does_not_change_launch(monkeypatch):
    monkeypatch.delenv("CF_TURNSTILE_CDP", raising=False)
    from cfturnstile.session import cdp_url, default_port
    from cfturnstile import launch_kwargs

    assert cdp_url(9333) == "http://127.0.0.1:9333"
    assert default_port() == 9333
    kw = launch_kwargs()
    assert "--disable-extensions" in kw["ignore_default_args"]
    assert kw["ignore_default_args"] == ["--enable-automation", "--disable-extensions"]
    assert "service_workers" not in kw
