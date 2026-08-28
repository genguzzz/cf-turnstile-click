(() => {
  if (globalThis.__cfTurnstileClickPatch) return;
  globalThis.__cfTurnstileClickPatch = 1;

  const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
  const originX =
    typeof window.screenX === "number" && window.screenX > 50
      ? window.screenX
      : rand(240, 960);
  const originY =
    typeof window.screenY === "number" && window.screenY > 40
      ? window.screenY
      : rand(80, 420);

  function clientOf(evt, axis) {
    if (axis === "X") return Number(evt.clientX || evt.x || 0) || 0;
    return Number(evt.clientY || evt.y || 0) || 0;
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
            // CDP Input.dispatchMouseEvent inside a cross-origin iframe:
            // screenX === clientX (often < 120). Real OS clicks are hundreds.
            if (!Number.isFinite(native) || (native < 120 && Math.abs(native - client) < 2)) {
              return origin + client;
            }
            return native;
          },
        });
      } catch (_) {}
    }
  }

  patchProto(MouseEvent.prototype);
  if (typeof PointerEvent !== "undefined") patchProto(PointerEvent.prototype);
})();
