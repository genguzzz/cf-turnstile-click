# Shield Bypass 技术架构与机制参考

## 1. 反检测核心机制 (Patchright + CDP)

现代防爬系统（Cloudflare Turnstile, Cloudflare Managed Challenge, Datadome, Kasada 等）主要针对以下特征进行检测：
1. **CDP Runtime 检测**：标准 Playwright / Puppeteer 在 `page.evaluate()` 时会发送 `Runtime.enable` 到主世界，注入 `__puppeteer_evaluation_script__`。Patchright 通过将评估代码注入独立执行上下文（Isolated Execution Context）绕过该检测。
2. **Navigator 特征覆盖检测**：修改 `navigator.webdriver` 常常留下原型链污染痕迹。Patchright 直接在 C++ 内部剔除了自动化标志。
3. **跨域 iframe 鼠标坐标欺骗 (ScreenX / ScreenY)**：
   - 跨域 iframe 内的 `MouseEvent.screenX/Y` 在 CDP dispatch 时常常被置为相对 iframe 的坐标（<100px），而真实鼠标点击相对显示器屏幕通常在数百像素。
   - 内置扩展通过 `Object.defineProperty` 拦截 `MouseEvent.prototype.screenX/Y` 读取，动态补齐屏幕偏移量。

## 2. 容器环境下的 Display 与 Xvfb 机制

在 Docker / 无显卡 Linux 容器中：
- 很多反爬脚本（如 Turnstile 的 WebGL / Canvas / 动画渲染管线）在无头（Headless）模式下会有明显特征差异或直接加载失败。
- `shield-bypass` 的 `ensure_display()` 会检测当前 `DISPLAY` 是否有效。若无可用显示服务，自动扫描并分配空闲 Display（如 `:99`、`:98` 等），清理死锁文件并启动 `Xvfb` 后台虚拟屏幕，使 Chrome 可以以完整的有头图形模式运行。

## 3. 指纹导出结构

通过 `export` 命令导出的 JSON 包含以下完整字段：

- `fingerprint`:
  - `navigator`: `userAgent`, `platform`, `languages`, `hardwareConcurrency`, `deviceMemory`, `webdriver` 等
  - `screen`: `width`, `height`, `availWidth`, `availHeight`, `colorDepth`, `devicePixelRatio`
  - `clientHints`: `brands`, `mobile`, `platform`
  - `webgl`: `vendor`, `renderer`, `unmaskedVendor`, `unmaskedRenderer`
  - `canvasHash`: Canvas 渲染哈希签名
  - `timezone`: 时区名称及偏移
- `tokens`:
  - `cf_clearance`: Cloudflare WAF 放行 Cookie
  - `__cf_bm`: Cloudflare Bot Management 标识
  - `cf-turnstile-response`: Turnstile 响应令牌
  - `g-recaptcha-response` / `h-captcha-response`
- `cookies`: 包含 name, value, domain, path, expires, httpOnly, secure, sameSite 的全量 Cookie 数组
- `cookie_header`: 格式化好的单行 Cookie 字符串（用于 HTTP Request Header）
- `headers`: 包含精确 User-Agent、Sec-CH-UA、Sec-Fetch-* 的完整请求头，可直接在 `curl_cffi` / Python `requests` / Golang 中复用。

## 4. 插件开发与高级定制规范

所有插件继承自 `bypass.plugins.base.BaseChallengePlugin`，支持自定义优先级、置信度判定与解盾逻辑：

```python
from bypass.plugins.base import BaseChallengePlugin, DetectionResult, SolveResult
from bypass.plugins import PluginRegistry
from bypass import isolated_eval

class MyCustomPlugin(BaseChallengePlugin):
    name = "my_custom_challenge"        # 唯一标识符
    display_name = "My Custom Challenge"
    priority = 30                        # 1-100，越小优先级越高，优先执行 detect

    def detect(self, page, ctx=None) -> DetectionResult:
        """快速探测页面特征，建议使用 isolated_eval 或 locator 避免污染全局 JS 环境"""
        # 1. 检查特定 iframe 或元素
        count = page.locator(".my-challenge-box").count()
        if count > 0:
            return DetectionResult(
                detected=True,
                challenge_type=self.name,
                confidence=0.9,
                details={"element_count": count}
            )
        return DetectionResult(detected=False)

    def solve(self, page, ctx=None, *, timeout_s: int = 40, **kwargs) -> SolveResult:
        """执行具体的过盾逻辑，模拟点击/拖拽/求解，并提取 token / cookies"""
        try:
            # 执行点击或与 CDP 交互
            page.locator("#challenge-checkbox").click(timeout=5000)
            
            # 等待结果并提取 Token / Cookie
            token = isolated_eval(page, "() => document.querySelector('#challenge-result')?.value || ''")
            return SolveResult(
                success=bool(token),
                challenge_type=self.name,
                token=token,
                data={"custom_meta": 123}
            )
        except Exception as e:
            return SolveResult(success=False, challenge_type=self.name, error=str(e))

# 注册到系统全局调度器
PluginRegistry.register(MyCustomPlugin)
```

## 5. CDP 会话调试与网络拦截实战

在多步复杂反爬逆向中，结合 CDP 监听与 Playwright 事件可以轻松抓取签名参数：

```python
from bypass import attach_cdp

with attach_cdp() as (page, ctx):
    # 启用 CDP 级别的网络监听（可选直接使用 Playwright 封装）
    def handle_request(req):
        if "api/v1/auth" in req.url:
            print("Captured Auth Request:", req.url)
            print("Headers:", req.headers)
            print("Payload:", req.post_data)

    def handle_response(res):
        if "api/v1/auth" in res.url:
            print("Auth Response:", res.status, res.text()[:200])

    page.on("request", handle_request)
    page.on("response", handle_response)
    
    # 执行后续交互
    page.goto("https://target-site.com")
```
