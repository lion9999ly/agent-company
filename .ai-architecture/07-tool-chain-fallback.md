# 🔧 工具链降级策略文档 (Tool Chain Fallback Strategy)

> **版本**: 1.0
> **创建时间**: 2026-03-16
> **用途**: 定义各类工具失败后的降级方案，确保任务不因单一工具失败而中断

---

## 一、网络搜索工具链

### 主工具: WebSearch (Claude Code 内置)

```
触发条件: 需要搜索公开信息
失败表现: 返回空结果、超时、无响应
```

### 降级策略

| 优先级 | 工具 | 适用场景 | 配置要求 |
|--------|------|----------|----------|
| P1 | WebSearch | 通用搜索 | 无 |
| P2 | WebFetch + 搜索引擎URL | 直接访问搜索引擎结果页 | 需构建搜索URL |
| P3 | browser-use (real模式) | 需登录/复杂页面 | Chrome浏览器 |
| P4 | DrissionPage | 反爬严格网站 | Python库 |
| P5 | 请求用户协助 | 所有工具失败 | 无 |

### 降级代码示例

```python
async def search_with_fallback(query: str) -> dict:
    """
    网络搜索降级策略
    """
    results = {"source": None, "data": None, "fallback_used": False}

    # P1: WebSearch
    try:
        data = await web_search(query)
        if data:
            results["source"] = "websearch"
            results["data"] = data
            return results
    except Exception as e:
        log_warning(f"WebSearch failed: {e}")

    # P2: WebFetch + 搜索引擎
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        data = await web_fetch(url)
        if data:
            results["source"] = "webfetch_google"
            results["data"] = data
            results["fallback_used"] = True
            return results
    except Exception as e:
        log_warning(f"WebFetch failed: {e}")

    # P3: browser-use
    try:
        data = await browser_use_search(query)
        if data:
            results["source"] = "browser_use"
            results["data"] = data
            results["fallback_used"] = True
            return results
    except Exception as e:
        log_warning(f"browser-use failed: {e}")

    # P4: DrissionPage
    try:
        data = await drissionpage_search(query)
        if data:
            results["source"] = "drissionpage"
            results["data"] = data
            results["fallback_used"] = True
            return results
    except Exception as e:
        log_warning(f"DrissionPage failed: {e}")

    # P5: 请求用户协助
    results["source"] = "manual_required"
    results["data"] = {"message": f"所有搜索工具失败，请手动搜索: {query}"}
    results["fallback_used"] = True
    return results
```

---

## 二、网页抓取工具链

### 主工具: WebFetch (Claude Code 内置)

```
触发条件: 需要抓取特定网页内容
失败表现: 403/404/重定向循环、超时、内容解析失败
```

### 降级策略

| 优先级 | 工具 | 适用场景 | 特点 |
|--------|------|----------|------|
| P1 | WebFetch | 静态页面 | 快速、无依赖 |
| P2 | DrissionPage | 反爬页面 | 模拟真实浏览器 |
| P3 | browser-use (chromium) | 需JS渲染 | Headless浏览器 |
| P4 | browser-use (real) | 需登录态 | 用户Chrome |
| P5 | Playwright | 复杂交互 | 强大但重 |
| P6 | 请求用户提供截图/内容 | 所有工具失败 | 最终兜底 |

### 状态码处理规则

| 状态码 | 处理策略 |
|--------|----------|
| 200 | 正常解析 |
| 301/302 | 跟随重定向（最多3次） |
| 403 | 切换DrissionPage或browser-use |
| 404 | 记录并尝试备用URL |
| 429 | 等待60秒后重试，最多3次 |
| 500/502/503 | 等待30秒后重试，最多2次 |

---

## 三、截图采集工具链

### 主工具: browser-use screenshot

```
触发条件: 需要采集UI/UX截图、产品界面、APP截图
失败表现: 启动失败、超时、截图黑屏
```

### 降级策略

| 优先级 | 工具 | 适用场景 | 输出格式 |
|--------|------|----------|----------|
| P1 | browser-use screenshot | 网页截图 | base64/PNG |
| P2 | Selenium + ChromeDriver | 需要精确控制 | PNG |
| P3 | Playwright screenshot | 复杂页面 | PNG/PDF |
| P4 | Puppeteer | Node环境 | PNG/PDF |
| P5 | 请求用户提供截图 | 所有工具失败 | 任意格式 |

### Selenium 截图脚本

```python
# scripts/selenium_screenshot.py

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pathlib import Path
import time

def capture_screenshot(url: str, output_path: str, wait_seconds: int = 5) -> bool:
    """
    使用 Selenium 截取网页截图

    Args:
        url: 目标URL
        output_path: 输出文件路径
        wait_seconds: 等待页面加载的秒数

    Returns:
        bool: 是否成功
    """
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    try:
        driver = webdriver.Chrome(options=options)
        driver.get(url)

        # 等待页面加载
        time.sleep(wait_seconds)

        # 截图
        driver.save_screenshot(output_path)
        driver.quit()

        return Path(output_path).exists()
    except Exception as e:
        print(f"Selenium截图失败: {e}")
        return False

def capture_element_screenshot(url: str, selector: str, output_path: str) -> bool:
    """
    截取特定元素的截图
    """
    options = Options()
    options.add_argument("--headless")

    try:
        driver = webdriver.Chrome(options=options)
        driver.get(url)

        element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )

        element.screenshot(output_path)
        driver.quit()
        return True
    except Exception as e:
        print(f"元素截图失败: {e}")
        return False
```

---

## 四、数据采集工具链

### 主工具: WebFetch + 解析

```
触发条件: 需要从网页提取结构化数据
失败表现: 解析失败、数据不完整、格式错误
```

### 降级策略

| 优先级 | 方法 | 适用场景 |
|--------|------|----------|
| P1 | WebFetch + 正则/LXML | 简单结构化数据 |
| P2 | DrissionPage + 元素定位 | 动态内容 |
| P3 | browser-use extract | 需要LLM提取 |
| P4 | 手动记录 + 后续补充 | 所有工具失败 |

### 数据置信度标注规则

| 置信度 | 来源 | 示例 |
|--------|------|------|
| **high** | 官方数据 | 官网规格、产品包装、官方声明 |
| **medium** | 权威报道 | 科技媒体评测、行业报道 |
| **low** | 估计/推断 | 基于同类产品推断 |
| **pending** | 待采集 | 需要进一步采集的数据 |

---

## 五、API调用工具链

### 主工具: Claude Code 工具调用

```
触发条件: 需要调用外部API获取数据
失败表现: 超时、认证失败、限流
```

### 降级策略

| 场景 | 策略 |
|------|------|
| 超时 | 重试3次，每次间隔递增(5s, 15s, 30s) |
| 认证失败 | 检查API Key配置，提示用户更新 |
| 限流(429) | 等待 Retry-After 头指定时间后重试 |
| 服务不可用 | 切换到备用API或本地缓存 |

---

## 六、用户请求触发条件

当以下情况发生时，应主动请求用户协助：

1. **所有工具失败**: 明确告知用户哪些工具失败，需要什么数据
2. **需登录内容**: 需要用户登录才能访问的内容
3. **付费内容**: 需要付费订阅才能获取的报告/数据
4. **实时数据**: 需要用户实时操作才能获取的数据（如APP截图）

### 请求模板

```
📌 数据采集请求

由于以下工具均未能成功获取数据，需要您的协助：

**目标数据**: [数据描述]
**已尝试工具**: [工具列表]
**失败原因**: [原因摘要]

**建议操作**：
1. [手动操作步骤]
2. [截图/文件要求]
3. [提交方式]

感谢您的配合！
```

---

## 七、日志与监控

### 工具调用日志格式

```json
{
  "timestamp": "2026-03-16T12:00:00",
  "tool": "websearch",
  "action": "search",
  "params": {"query": "..."},
  "result": "success|failure",
  "fallback_used": false,
  "fallback_tool": null,
  "error_message": null,
  "duration_ms": 1234
}
```

### 监控指标

| 指标 | 阈值 | 触发动作 |
|------|------|----------|
| 单工具失败率 | > 50% | 告警并检查工具状态 |
| 降级触发率 | > 30% | 检查主工具可用性 |
| 用户协助请求率 | > 10% | 优化工具链或补充新工具 |

---

## 八、配置文件

### 工具优先级配置 (`tool_chain_config.json`)

```json
{
  "web_search": {
    "primary": "websearch",
    "fallback_chain": ["webfetch_google", "browser_use", "drissionpage", "manual"],
    "timeout_seconds": 30,
    "max_retries": 3
  },
  "web_fetch": {
    "primary": "webfetch",
    "fallback_chain": ["drissionpage", "browser_use", "playwright", "manual"],
    "timeout_seconds": 60,
    "max_retries": 2
  },
  "screenshot": {
    "primary": "browser_use",
    "fallback_chain": ["selenium", "playwright", "manual"],
    "timeout_seconds": 120,
    "wait_seconds": 5
  }
}
```

---

*文档版本: 1.0*
*最后更新: 2026-03-16*
*维护者: Multi-Agent 虚拟研发中心*