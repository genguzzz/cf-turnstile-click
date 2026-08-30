(() => {
  if (globalThis.__cfTurnstileMonitor) return;
  globalThis.__cfTurnstileMonitor = 1;

  function inIframe() {
    try {
      return window.top !== window;
    } catch (_) {
      return true;
    }
  }

  function setState(state) {
    try {
      const el = document.documentElement;
      if (el.getAttribute("data-cf-ts-state") === state) return;
      el.setAttribute("data-cf-ts-state", state);
    } catch (_) {}
  }

  function tokenValue() {
    try {
      const el = document.querySelector(
        "input[name='cf-turnstile-response'], textarea[name='cf-turnstile-response']"
      );
      return el && el.value ? String(el.value) : "";
    } catch (_) {
      return "";
    }
  }

  function scanTop() {
    if (tokenValue().length > 20) {
      setState("token");
      return;
    }
    let iframe = null;
    try {
      iframe = document.querySelector(
        "iframe[src*='challenges.cloudflare.com'], iframe[src*='turnstile']"
      );
    } catch (_) {}
    if (!iframe) {
      setState("idle");
      return;
    }
    const r = iframe.getBoundingClientRect();
    if (r.width >= 20 && r.height >= 20) setState("ready");
    else setState("widget");
  }

  function scanFrame() {
    const body = document.body;
    if (body && body.innerText && /verifying/i.test(body.innerText)) {
      setState("verifying");
      return;
    }
    setState("ready");
  }

  function start() {
    const scan = inIframe() ? scanFrame : scanTop;
    try {
      scan();
    } catch (_) {}
    setInterval(function () {
      try {
        scan();
      } catch (_) {}
    }, 400);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
