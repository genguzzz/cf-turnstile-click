---
name: shield-bypass
description: >-
  统一反爬与人机验证（过盾）平台：基于 Patchright + CDP Session 机制，支持动态注入调试脚本、多层跨域 iframe 与 Shadow DOM 检测、插件化识别与自动过盾（Cloudflare Turnstile、CF 5s 盾/WAF Challenge、reCAPTCHA、hCaptcha 等），并在通过后快速导出完整浏览器指纹（User-Agent, Sec-CH-UA, WebGL, Canvas 等）、全量 Cookies（含 cf_clearance / token）与认证状态。
  触发：过盾、过检测、Turnstile、cf challenge、cloudflare、人机验证、验证码、stealth、bypass、shield-bypass、cf-turnstile、Just a moment、5秒盾、导出指纹、抓取受保护页面。
---

# Shield Bypass · 统一过盾分析指南与反爬自动化工具库

`shield-bypass` 定位为：
1. **过盾分析与调试指南（Agent Guide）**：指导 Agent 在面对各类反爬盾（CF 5s 盾、Turnstile、reCAPTCHA、hCaptcha、自定义滑块等）时，如何通过后台 CDP Session 保持长连接交互、利用 CDP / Patchright 监听网络流量与抓包、安全探测 DOM / iframe 结构、并在不污染页面的前提下开发自定义 Plugin 扩展解盾能力。
2. **可复用的 Python 工具库（`bypass` 模块）**：提供成熟的基础组件（`chrome_context`、`attach_cdp`、`isolated_eval`、`inspect_iframes`、`PluginRegistry` 等），支持从 GitHub 安装或本地引入；业务代码（如 `forum-web` NodeSeek 客户端登录）直接调用该库完成过盾。

```bash
BYPASS='bash scripts/bypass.sh'
```

---

## 一、Python 库安装与快速引入指南

### 1. 安装方式

- **GitHub 远程安装**：
  ```bash
  pip install git+https://github.com/genguzzz/shield-bypass.git
  ```
- **本地环境 Editable 安装**：
  ```bash
  pip install -e /path/to/shield-bypass
  ```

### 2. 免安装本地快速引入（编写临时探测脚本时首选）

```python
import os
import sys
from pathlib import Path

# 指定或自动探测 shield-bypass 目录
BYPASS_ROOT = os.environ.get("SHIELD_BYPASS_ROOT", str(Path(__file__).resolve().parents[2] / "shield-bypass"))
if BYPASS_ROOT not in sys.path:
    sys.path.insert(0, BYPASS_ROOT)

from bypass import (
    chrome_context,
    attach_cdp,
    start_session,
    stop_session,
    solve,
    auto_solve,
    extract_fingerprint,
    isolated_eval,
    inspect_iframes,
    PluginRegistry,
    BaseChallengePlugin,
    DetectionResult,
    SolveResult,
)
```

---

## 二、CDP 会话管理与 Agent 浏览器操控指南

`shield-bypass` 支持常驻后台的 Chrome 会话（自动处理 Linux Xvfb 虚拟屏幕与 9333 端口），允许 Agent 执行多步交互、网络流量抓取、请求拦截及逆向分析。

### 1. 命令行管理 CDP 会话

```bash
# 启动后台 Chrome 会话（返回 cdp 端口、pid、xvfb 屏幕信息）
$BYPASS session start

# 查看会话健康状态
$BYPASS session status

# 命令行直连调试会话（交互式或单命令）
$BYPASS session debug --url "https://www.nodeseek.com/signIn.html" detect
$BYPASS session debug iframes
$BYPASS session debug shot /tmp/login.png
$BYPASS session debug solve
$BYPASS session debug export

# 停止会话并释放资源
$BYPASS session stop
```

### 2. 在 Python 中操控 CDP 会话（网络请求抓取与交互）

当后台 Session 启动后，Agent 可通过 `attach_cdp()` 接入同一个浏览器实例：

```python
from bypass import attach_cdp, isolated_eval, inspect_iframes, extract_fingerprint

# 连接到已在运行的后台 CDP 实例
with attach_cdp() as (page, context):
    # 1. 监听与捕获目标网络请求（XHR / Fetch / 接口签名）
    captured_requests = []
    
    def on_request(request):
        if "/api/" in request.url:
            captured_requests.append({
                "url": request.url,
                "method": request.method,
                "headers": request.headers,
                "post_data": request.post_data,
            })
            
    def on_response(response):
        if "/api/" in response.url and response.status == 200:
            try:
                print(f"[API Response] {response.url} -> {response.json()}")
            except Exception:
                pass

    page.on("request", on_request)
    page.on("response", on_response)

    # 2. 页面导航与交互
    page.goto("https://www.nodeseek.com/signIn.html", wait_until="domcontentloaded")

    # 3. 跨域 iframe / 挑战特征深度探测
    iframes = inspect_iframes(page)
    print("Detected iframes:", iframes)

    # 4. 在安全隔离环境（Isolated World）执行 JS，严防触发反爬指纹监听
    title = isolated_eval(page, "() => document.title")
    print("Page Title:", title)

    # 5. 表单填写与点击（模拟真实用户行为）
    page.locator("input[name='username']").fill("my_username")
    page.locator("input[name='password']").fill("my_password")
```

---

## 三、Plugin 插件开发与定制指南

`shield-bypass` 采用插件化架构管理各类验证挑战。Agent 在面对新盾或特殊验证码（如滑动拼图、点选字符、自定义 WAF 等）时，可以通过继承基类轻松定制和注入插件。

### 1. 核心公共组件与工具库一览

| 模块 / 工具 | 说明 | 推荐用法 |
|---|---|---|
| `BaseChallengePlugin` | 所有挑战插件的抽象基类 | 继承并实现 `detect` 与 `solve` |
| `DetectionResult` | 探测返回容器 | `DetectionResult(detected=True, challenge_type=..., confidence=0.9)` |
| `SolveResult` | 解盾返回容器 | `SolveResult(success=True, token=..., clearance=...)` |
| `PluginRegistry` | 插件注册表与调度器 | `PluginRegistry.register(MyPlugin)` |
| `isolated_eval(page, js)` | 在独立执行上下文运行 JS | 避免主世界 `evaluate` 泄露自动化特征 |
| `inspect_iframes(page)` | 一次性探测全量 iframe 结构 | 快速定位 Cloudflare、Google、hCaptcha 的 iframe |
| `dump_page_controls(page)` | 提取页面输入框、按钮、Checkbox | 快速分析交互元素位置与选择器 |
| `extract_fingerprint(page, ctx)` | 提取完整指纹、Token 及 Cookies | 导出可复用的请求头与 Cookie Header |

### 2. 开发并注册自定义 Plugin 模版

```python
from bypass.plugins.base import BaseChallengePlugin, DetectionResult, SolveResult
from bypass.plugins import PluginRegistry, auto_solve
from bypass import chrome_context, isolated_eval


class CustomSlideCaptchaPlugin(BaseChallengePlugin):
    """自定义滑块 / 点选验证码插件示例"""

    name = "custom_slider"               # 插件唯一标识
    display_name = "Custom Slider Captcha"
    priority = 10                         # 优先级（1-100，数值越小越优先探测）

    def detect(self, page, ctx=None) -> DetectionResult:
        """分析当前页面是否存在该挑战"""
        # 推荐使用 isolated_eval 或 locator 检测 DOM
        has_slider = page.locator(".captcha-slider-track").count() > 0
        return DetectionResult(
            detected=has_slider,
            challenge_type=self.name,
            confidence=0.95 if has_slider else 0.0,
            details={"track_count": has_slider},
        )

    def solve(self, page, ctx=None, *, timeout_s: int = 40, **kwargs) -> SolveResult:
        """执行解盾 / 拖拽 / 识别操作并返回结果"""
        slider = page.locator(".captcha-slider-handle").first
        if not slider.is_visible():
            return SolveResult(success=False, challenge_type=self.name, error="Slider handle not visible")

        box = slider.bounding_box()
        if not box:
            return SolveResult(success=False, challenge_type=self.name, error="Cannot get bounding box")

        # 模拟鼠标物理拖拽
        page.mouse.move(box["x"] + 5, box["y"] + 5)
        page.mouse.down()
        page.mouse.move(box["x"] + 220, box["y"] + 5, steps=15)
        page.mouse.up()
        page.wait_for_timeout(1000)

        # 提取生成的 token 或验证状态
        token = isolated_eval(page, "() => document.querySelector('#captcha-token')?.value || ''")
        return SolveResult(
            success=bool(token),
            challenge_type=self.name,
            token=token,
            data={"drag_distance": 220},
        )


# 注册插件到全局注册表
PluginRegistry.register(CustomSlideCaptchaPlugin)
```

---

## 四、Agent 快速编写临时探测脚本模版

> **临时文件规范**：调试临时脚本只放在**当前工作区**或 `/tmp/`（用完即删），**严禁**在 skill 目录堆放临时文件。

### 模版 1：探测页面挑战并自动解盾提取 Token

```python
from bypass import chrome_context, solve, extract_fingerprint

url = "https://example.com/login"

with chrome_context(headless=False) as (page, ctx):
    page.goto(url, wait_until="domcontentloaded")
    
    # 自动识别挑战类型（CF WAF / Turnstile / reCAPTCHA / hCaptcha / 自定义插件）并求解
    res = solve(page, ctx, timeout_s=30)
    print(f"解盾状态: {res.success}, 类型: {res.challenge_type}, Token: {res.token}")
    
    # 提取全量指纹与 cookies（含 cf_clearance）
    fp = extract_fingerprint(page, ctx)
    print("Cookies:", fp["cookies"])
    print("UA / Headers:", fp["headers"])
```

### 模版 2：解盾后导出指纹并由 `curl_cffi` 发送高速请求

```python
from bypass import chrome_context, solve, extract_fingerprint
from curl_cffi import requests

with chrome_context(headless=False) as (page, ctx):
    page.goto("https://www.nodeseek.com/signIn.html", wait_until="domcontentloaded")
    res = solve(page, ctx, timeout_s=30)
    fp = extract_fingerprint(page, ctx)

# 将导出的指纹和 Cookie 注入 curl_cffi 进行后续轻量 API 调用
headers = fp["headers"]
resp = requests.get("https://www.nodeseek.com/api/user/info", headers=headers, impersonate="chrome124")
print("API Response:", resp.text)
```

---

## 五、CLI 常用调试命令速查

**1. 快速抓取受保护页面**
```bash
# 抓取纯文本
$BYPASS fetch "https://example.com"

# 抓取完整渲染后的 HTML
$BYPASS fetch "https://example.com" --html

# 仅探测页面标题
$BYPASS fetch "https://example.com" --title-only
```

**2. 快速过盾并导出完整指纹与 Token**
```bash
# 导出为 JSON 指纹字典
$BYPASS export "https://example.com"

# 直接导出为可执行 curl 命令
$BYPASS export "https://example.com" --format curl

# 导出为 Python 代码
$BYPASS export "https://example.com" --format python -o /tmp/fetch_example.py
```

---

## 六、业务代码集成原则

- **业务与过盾解耦**：业务代码（如 `forum-web` 中的 `nsclient`）只负责业务逻辑（如表单填写、登录 API 请求、会话存储）。
- **统一调用**：过盾逻辑统一委托给 `bypass` 库（如 `from bypass import solve`），不得在业务模块内部另行维护一套私有的过盾逻辑。
- **环境安全**：禁止在主世界滥用 `page.evaluate()`；必须通过 `bypass.isolated_eval()` 进行 DOM 探测，避免触发反爬指纹监听。

详细机制与指纹结构参考 [reference.md](reference.md)。
