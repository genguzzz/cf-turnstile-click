---
name: shield-bypass
description: >-
  统一反爬与人机验证（过盾）平台：基于 Patchright + CDP Session 机制，支持动态注入调试脚本、多层跨域 iframe 与 Shadow DOM 检测、插件化识别与自动过盾（Cloudflare Turnstile、CF 5s 盾/WAF Challenge、reCAPTCHA、hCaptcha 等），并在通过后快速导出完整浏览器指纹（User-Agent, Sec-CH-UA, WebGL, Canvas 等）、全量 Cookies（含 cf_clearance / token）与认证状态。
  触发：过盾、过检测、Turnstile、cf challenge、cloudflare、人机验证、验证码、stealth、bypass、shield-bypass、cf-turnstile、Just a moment、5秒盾、导出指纹、抓取受保护页面。
---

# Shield Bypass · 统一过盾分析指南与反爬自动化工具库

`shield-bypass` 定位为：
1. **过盾分析与调试指南（Agent Guide）**：指导 Agent 在逆向与开发阶段，如何探测未知站点的反爬挑战、动态注入 JS、分析 iframe 与 DOM 结构，并快速编写临时脚本通过盾。
2. **可复用的 Python 工具库（`bypass` 模块）**：支持从 GitHub 远程安装、本地 pip editable 安装或在 Python 中通过路径直接引入；业务代码（如 `forum-web` NodeSeek 客户端登录）直接调用该库完成过盾，绝不重复编写解盾代码。

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

from bypass import chrome_context, solve, auto_solve, extract_fingerprint, isolated_eval
```

---

## 二、Agent 快速编写临时探测脚本模版

> **临时文件规范**：调试临时脚本只放在**当前工作区**或 `/tmp/`（用完即删），**严禁**在 skill 目录堆放临时文件。

### 模版 1：探测页面挑战并自动解盾提取 Token

```python
from bypass import chrome_context, solve, extract_fingerprint

url = "https://example.com/login"

with chrome_context(headless=False) as (page, ctx):
    page.goto(url, wait_until="domcontentloaded")
    
    # 自动识别挑战类型（CF WAF / Turnstile / reCAPTCHA / hCaptcha）并求解
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

## 三、CLI 常用调试命令速查

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

**3. 长连接 CDP Session 机制（多步交互与逆向调试）**
```bash
# 启动常驻后台 Chrome 会话（自动管理 Xvfb 虚拟屏幕与 9333 端口）
$BYPASS session start

# 探测当前页面的挑战与 iframe 层次
$BYPASS session debug detect
$BYPASS session debug iframes

# 触发自动过盾
$BYPASS session debug solve

# 截屏排查渲染状态
$BYPASS session debug shot /tmp/shot.png

# 在 Isolated Context 安全执行 JS（不污染主环境，防指纹检测）
$BYPASS session debug iso "document.title"

# 停止会话
$BYPASS session stop
```

---

## 四、业务代码集成原则

- **业务与过盾解耦**：业务代码（如 `forum-web` 中的 `nsclient`）只负责业务逻辑（如表单填写、登录 API 请求、会话存储）。
- **统一调用**：过盾逻辑统一委托给 `bypass` 库（如 `from bypass import solve`），不得在业务模块内部另行维护一套私有的过盾逻辑。
- **环境安全**：禁止在主世界滥用 `page.evaluate()`；必须通过 `bypass.isolated_eval()` 进行 DOM 探测，避免触发反爬指纹监听。

详细机制与指纹结构参考 [reference.md](reference.md)。
