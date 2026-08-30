(() => {
  if (globalThis.__cfTurnstileClickPatch) return;
  globalThis.__cfTurnstileClickPatch = 1;

  const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
  const framed = (() => {
    try {
      return window.top !== window;
    } catch (_) {
      return true;
    }
  })();
  // Iframe window.screenX is often the widget offset (50–90). Using that as
  // origin makes patched screenX stay < 100 and Cloudflare still rejects.
  const originX =
    !framed && typeof window.screenX === "number" && window.screenX > 50
      ? window.screenX
      : rand(240, 960);
  const originY =
    !framed && typeof window.screenY === "number" && window.screenY > 40
      ? window.screenY
      : rand(80, 420);

  function inIframe() {
    try {
      return window.top !== window;
    } catch (_) {
      return true;
    }
  }

  function clientOf(evt, axis) {
    if (axis === "X") return Number(evt.clientX || evt.x || 0) || 0;
    return Number(evt.clientY || evt.y || 0) || 0;
  }

  function needsPatch(native, client) {
    if (!Number.isFinite(native)) return true;
    // CDP Input.dispatchMouseEvent in a cross-origin iframe:
    // screenX === clientX (often < 120).
    if (native < 120 && Math.abs(native - client) < 2) return true;
    // Linux XTEST / Ozone: the iframe still gets a small screenX (widget
    // offset ~50–90), but it is NOT equal to clientX. Cloudflare's check
    // is still "screenX < 100" so the click is discarded. macOS Quartz
    // reports display coordinates (hundreds) and must not be rewritten.
    if (inIframe() && native < 120) return true;
    return false;
  }

  function patchProto(proto) {
    if (!proto) return;
    for (const name of ["screenX", "screenY"]) {
      const desc = Object.getOwnPropertyDescriptor(proto, name);
      const origGet = desc && desc.get;
      const axis = name.endsWith("X") ? "X" : "Y";
      const origin = axis === "X" ? originX : originY;
      try {
        Object.defineProperty(proto, name, {
          configurable: true,
          enumerable: !!(desc && desc.enumerable),
          get() {
            let native = 0;
            try {
              native = origGet ? origGet.call(this) : 0;
            } catch (_) {}
            const client = clientOf(this, axis);
            if (needsPatch(native, client)) return origin + client;
            return native;
          },
        });
      } catch (_) {}
    }
  }

  patchProto(MouseEvent.prototype);
  if (typeof PointerEvent !== "undefined") patchProto(PointerEvent.prototype);
  try {
    document.documentElement.setAttribute("data-cf-ts-click", "1");
  } catch (_) {}
  try {
    console.log("[cf-turnstile-click]", location.hostname, inIframe() ? "iframe" : "top");
  } catch (_) {}
})();
