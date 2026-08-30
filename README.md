# Shield Bypass

**Unified Anti-Bot Challenge Bypass, Dynamic Script Injection & Stealth Browser Automation Engine**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Patchright](https://img.shields.io/badge/engine-patchright-brightgreen.svg)](https://github.com/Kaliiiiiiiiii-tools/patchright)

`shield-bypass` 是一个针对现代反爬与人机验证（Cloudflare Turnstile、CF 5s 盾/WAF Challenge、Google reCAPTCHA、hCaptcha 等）设计的自动化过盾与浏览器指纹提取引擎。

基于 Patchright（防检测底层 Chromium）+ CDP 会话守护机制，支持跨域多层 iframe / Shadow DOM 毫秒级探测、隔离环境（Isolated Context）动态脚本注入、持久化后台长连接会话，以及通过后全量指纹（User-Agent、Sec-CH-UA、WebGL、Canvas、Cookie、`cf_clearance`、Turnstile Token）快速导出。

---

## 核心特性

- **插件化验证码求解架构**：内置 Cloudflare Turnstile、CF WAF 5秒盾、reCAPTCHA、hCaptcha 等探测与求解插件，支持按优先级自动识别或自定义编写插件。
- **极致快速探测（0ms~毫秒级）**：单次 JavaScript 原子评估获取 DOM、iframe 树与 Token 状态，避免频繁 Playwright RPC 延迟。
- **无感防检测补丁**：内置 Chromium Extension，自动修补 `MouseEvent.screenX/screenY` 坐标偏移，规避 Cloudflare / Datadome 行为指纹识别。
- **完全隔离环境执行**：所有 DOM 探测与状态监控均在 Isolated Execution Context 中执行，绝不污染页面 Main Context，不触发反爬监听。
- **全量指纹与 Token 导出**：一键导出包含 Headers、Cookies（`cf_clearance`）、Turnstile Token 的配置，可直接转换为 `curl` 命令或 Python `curl_cffi` 请求代码。
- **持久化 CDP 会话守护进程**：支持启动后台 Chrome 实例，供 Agent 或爬虫进行多步复杂交互与快速调试。
- **容器与 Linux 友好**：自动检测环境图形状态，在无头容器中自动按需分配 Display 并拉起 Xvfb 虚拟屏幕，保证完全有头环境的防指纹检测能力。

---

## 环境初始化指南

### 1. 优先推荐：直接使用系统 Python 环境（默认首选）

在没有包版本冲突的绝大多数 Linux / 容器环境下，**无需创建虚拟环境**，直接全局或用户目录安装即可：

```bash
# 进入项目目录
cd /root/shield-bypass

# 安装当前模块及命令行入口（可编辑模式）
pip install -e . --no-deps

# 若未安装 patchright，安装依赖
pip install patchright
```

### 2. 备选方案：存在版本冲突时使用虚拟环境（venv）

如果当前系统 Python 环境安装了其他冲突版本的 Playwright 或全局依赖锁定，可使用独立虚拟环境隔离：

```bash
# 创建虚拟环境
python3 -m venv .venv

# 激活环境
source .venv/bin/activate

# 安装依赖与模块
pip install -e .
```

### 3. 安装浏览器与系统依赖

在无图形界面的 Linux 机器或 Docker 容器内运行：

```bash
# 1. 安装 Patchright Chromium 浏览器内核
patchright install chromium

# 2. 安装 Linux 渲染与虚拟显示服务（Ubuntu / Debian）
apt-get update && apt-get install -y xvfb libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2
```

---

## 快速使用 (CLI)

安装后可直接使用 `shield-bypass` 或简短别名 `bypass`：

### 1. 抓取受保护页面

```bash
# 自动探测并解盾后抓取页面纯文本
bypass fetch "https://example.com"

# 抓取解盾并渲染后的完整 HTML
bypass fetch "https://example.com" --html

# 仅输出页面标题（快速验证）
bypass fetch "https://example.com" --title-only
```

### 2. 导出浏览器指纹与 Token (用于 requests / curl_cffi)

```bash
# 导出包含全量 Cookies、Tokens、Headers、Navigator、WebGL 指纹的 JSON
bypass export "https://example.com"

# 直接输出为可执行的 curl 命令（包含所有防检测请求头和 Cookie）
bypass export "https://example.com" --format curl

# 直接输出为 Python curl_cffi 代码片段
bypass export "https://example.com" --format python

# 导出并保存到本地文件
bypass export "https://example.com" -o /tmp/fingerprint.json
```

### 3. 长连接后台会话（供多步任务与调试使用）

```bash
# 1. 启动常驻后台 Chrome 会话（自动分配 Xvfb 与 CDP 端口 9333）
bypass session start

# 2. 查看会话状态与 CDP 调试端口
bypass session status

# 3. 调试当前页面：探测验证码与 iframe
bypass session debug detect
bypass session debug iframes

# 4. 触发自动解盾
bypass session debug solve

# 5. 导出当前会话的 Cookie 与指纹
bypass session debug export

# 6. 截取全屏快照查看渲染状态
bypass session debug shot /tmp/screenshot.png

# 7. 在隔离上下文中动态执行 JavaScript
bypass session debug iso "document.title"

# 8. 停止会话并释放资源
bypass session stop
```

### 4. 动态注入与 DOM 探测

```bash
# 探测目标页面的所有 iframe 与表单交互元素
bypass inspect "https://example.com"

# 动态向页面注入 JavaScript 脚本并获取返回值
bypass inject "https://example.com" --js "return { title: document.title, cookies: document.cookie }"
```

---

## Python API 使用示例

### 1. 单行快速解盾

```python
from bypass import solve_url

# 打开 URL、自动识别挑战、解盾并返回结果
result = solve_url("https://example.com/login", timeout_s=30)
if result.success:
    print(f"成功通过验证！Challenge: {result.challenge_type}")
    print("获得的 Token:", result.token)
    print("页面 Cookies:", result.cookies)
else:
    print("解盾失败:", result.error)
```

### 2. 上下文管理器 + 指纹导出并交由 `curl_cffi` 发送高速请求

```python
from bypass import chrome_context, auto_solve, extract_fingerprint, format_python_code
from curl_cffi import requests

with chrome_context(headless=False) as (page, ctx):
    page.goto("https://example.com", wait_until="commit")
    
    # 自动识别并解盾
    solve_res = auto_solve(page, ctx, timeout_s=30)
    if solve_res.success:
        # 提取完整浏览器指纹
        fp_data = extract_fingerprint(page, ctx)
        
        # 使用导出的 headers 和 cookies 进行轻量级 HTTP 请求
        headers = fp_data["headers"]
        resp = requests.get(
            "https://example.com/api/user/info",
            headers=headers,
            impersonate="chrome124"
        )
        print("API 响应内容:", resp.json())
```

---

## 插件体系 (Plugin Architecture)

已内置插件及执行优先级：
1. `cf_waf` (优先级 5): Cloudflare 5 秒盾 / WAF 质询
2. `cf_turnstile` (优先级 10): Cloudflare Turnstile 显式勾选 / 隐式验证
3. `recaptcha` (优先级 20): Google reCAPTCHA v2 / v3
4. `hcaptcha` (优先级 25): hCaptcha 验证码
5. `generic_wait` (优先级 999): 通用页面稳定等待兜底

查看当前插件列表：
```bash
bypass plugins list
```

### 编写自定义验证码插件

只需继承 `BaseChallengePlugin` 并实现 `detect` 和 `solve`：

```python
from bypass.plugins.base import BaseChallengePlugin, DetectionResult, SolveResult
from bypass.plugins import PluginRegistry

class CustomCaptchaPlugin(BaseChallengePlugin):
    name = "custom_captcha"
    display_name = "Custom Captcha Solver"
    priority = 15

    def detect(self, page, ctx=None) -> DetectionResult:
        has_widget = page.locator("#custom-captcha-box").count() > 0
        return DetectionResult(
            detected=has_widget,
            challenge_type=self.name,
            confidence=0.9 if has_widget else 0.0,
            details={"selector": "#custom-captcha-box"}
        )

    def solve(self, page, ctx=None, timeout_s=30, **kwargs) -> SolveResult:
        # 实现点击或解题逻辑...
        page.locator("#custom-captcha-box .btn-verify").click()
        return SolveResult(success=True, challenge_type=self.name)

# 注册插件
PluginRegistry.register(CustomCaptchaPlugin)
```

---

## 目录结构

```
shield-bypass/
├── bypass/                     # 核心 Python 库
│   ├── ext/                    # 防检测 Chromium Extension
│   ├── plugins/                # 插件化解盾模块 (CF, Turnstile, reCAPTCHA, hCaptcha)
│   ├── browser.py              # Patchright Chromium 启动与上下文管理
│   ├── cli.py                  # CLI 命令行实现
│   ├── config.py               # Xvfb 虚拟屏幕与运行环境配置
│   ├── daemon.py               # CDP 后台常驻守护进程
│   ├── fingerprint.py          # 全量指纹与 Token 提取器
│   ├── injector.py             # Isolated Context 动态注入器
│   ├── inspector.py            # DOM / iframe / Shadow DOM 探测器
│   └── session.py              # CDP 会话管理与挂载
├── examples/                   # 使用示例代码
├── scripts/                    # 便捷启动脚本 (bypass.sh, cf.sh)
├── tests/                      # 单元测试 (100% 覆盖关键逻辑)
├── pyproject.toml              # 项目打包配置
├── setup.py                    # setuptools 配置
├── SKILL.md                    # Cursor Agent Skill 定义
└── README.md
```

---

## 许可证

MIT License. 仅供安全研究、自动化测试与合规数据采集使用。
