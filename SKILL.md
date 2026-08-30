---
name: shield-bypass
description: >-
  统一反爬与人机验证（过盾）平台：基于 Patchright + CDP Session 机制，支持动态注入调试脚本、多层跨域 iframe 与 Shadow DOM 检测、插件化识别与自动过盾（Cloudflare Turnstile、CF 5s 盾/WAF Challenge、reCAPTCHA、hCaptcha 等），并在通过后快速导出完整浏览器指纹（User-Agent, Sec-CH-UA, WebGL, Canvas 等）、全量 Cookies（含 cf_clearance / token）与认证状态。
  触发：过盾、过检测、Turnstile、cf challenge、cloudflare、人机验证、验证码、stealth、bypass、shield-bypass、cf-turnstile、Just a moment、5秒盾、导出指纹、抓取受保护页面。
---

# Shield Bypass · 统一过盾与反爬自动化

基于 Patchright（无头/有头防检测 Chromium）与 CDP Session 架构，集成插件式多验证码识别、跨域 iframe 深度探测、动态脚本注入与指纹快速导出。

```bash
BYPASS='bash scripts/bypass.sh'
```

## 核心速查

**1. 快速过盾抓取内容**

```bash
# 抓取 Cloudflare / WAF 保护页面的文本内容
$BYPASS fetch "https://example.com"

# 抓取完整渲染后的 HTML
$BYPASS fetch "https://example.com" --html

# 仅检测页面标题
$BYPASS fetch "https://example.com" --title-only
```

**2. 快速过盾并导出完整指纹与 Token（供 requests/curl_cffi 复用）**

```bash
# 导出包含 UA、Sec-CH-UA、WebGL、Canvas Hash、Cookie、cf_clearance、Turnstile Token 的 JSON
$BYPASS export "https://example.com"

# 导出为直接可执行的 curl 命令
$BYPASS export "https://example.com" --format curl

# 导出为 Python curl_cffi 代码片段
$BYPASS export "https://example.com" --format python

# 导出并保存到文件
$BYPASS export "https://example.com" -o /tmp/session_fp.json
```

**3. 长连接 Session 机制（调试与多步交互）**

```bash
# 启动后台常驻 Chrome 会话（自动管理 Xvfb 与 CDP 端口 9333）
$BYPASS session start

# 查看会话状态与 CDP 地址
$BYPASS session status

# 探测当前页面上的验证码与 iframe 层次
$BYPASS session debug detect
$BYPASS session debug iframes

# 对当前页面触发自动过盾
$BYPASS session debug solve

# 导出当前页面的全量指纹与 Cookie
$BYPASS session debug export

# 截取全屏快照查看渲染状态
$BYPASS session debug shot /tmp/shot.png

# 动态在隔离环境执行 JS（不污染主世界，防止被检测）
$BYPASS session debug iso "document.title"

# 停止会话
$BYPASS session stop
```

**4. 动态注入与 DOM 探测**

```bash
# 探测目标 URL 的 iframe 树与交互控件
$BYPASS inspect "https://example.com"

# 动态注入调试脚本
$BYPASS inject "https://example.com" --js "return document.title"
```

## 插件机制与支持类型

已内置插件体系，自动检测并分发：
- `cf_waf`: Cloudflare 5 秒盾 / "Just a moment..." / WAF 质询
- `cf_turnstile`: Cloudflare Turnstile 勾选框 / 隐式验证码
- `recaptcha`: Google reCAPTCHA v2 勾选框 / v3
- `hcaptcha`: hCaptcha 勾选框
- `generic_wait`: 通用渲染稳定等待兜底

查看当前已加载插件：
```bash
$BYPASS plugins list
```

编写新验证码插件只需继承 `BaseChallengePlugin`，实现 `detect` 和 `solve` 方法即可，详见 [examples/custom_plugin.py](examples/custom_plugin.py)。

## 架构原则与禁止事项

- **禁止使用未打补丁的标准 Playwright**：标准 Playwright 会在主世界触发 CDP `Runtime.enable`，被 Cloudflare / Turnstile 直接标黑。
- **禁止在主世界滥用 evaluate**：交互探测优先使用 isolated context (`isolated_eval`)。
- **定位原则**：Turnstile / reCAPTCHA 跨域 iframe 需等待 widget 完全绘制后再通过 frame locator 触发，避免点击 1×1 占位 shell。
- **容器显示机制**：Linux 容器无物理屏幕时，脚本会自动检测并按需拉起 Xvfb 虚拟屏幕，保证 Headed 渲染特性。

详细机制与指纹结构参考 [reference.md](reference.md)。
