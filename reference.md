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

## 4. 插件开发规范

所有插件继承自 `bypass.plugins.base.BaseChallengePlugin`：

```python
from bypass.plugins.base import BaseChallengePlugin, DetectionResult, SolveResult

class MyChallengePlugin(BaseChallengePlugin):
    name = "my_challenge"
    display_name = "My Custom Challenge"
    priority = 30  # 1-100，越小优先级越高

    def detect(self, page, ctx=None) -> DetectionResult:
        # 检测 DOM、iframe 或标题特征
        detected = page.locator(".my-challenge-box").count() > 0
        return DetectionResult(
            detected=detected,
            challenge_type=self.name,
            confidence=0.9 if detected else 0.0,
            details={}
        )

    def solve(self, page, ctx=None, *, timeout_s: int = 40, **kwargs) -> SolveResult:
        # 执行过盾逻辑并提取 Token
        return SolveResult(
            success=True,
            challenge_type=self.name,
            token="extracted_token_here",
            clearance="cookie_here"
        )
```
