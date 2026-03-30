# 🔧 工具链降级策略文档 v2.0 (Tool Chain Fallback Strategy)

> **版本**: 2.0
> **创建时间**: 2026-03-16
> **理念**: 办法比困难多 — AI军团的武器库
> **用途**: 定义各类工具失败后的全方位降级方案，确保任务不因单一工具失败而中断

---

## 🎯 核心原则

1. **永不放弃**: 尝试所有可能方案后才请求人工协助
2. **方案矩阵**: 每个场景至少准备10+备用方案
3. **智能路由**: 根据失败原因自动选择最合适的备用方案
4. **组合拳**: 多个工具组合使用，互相补充

---

## 一、网络搜索工具链（15级降级方案）

### 降级矩阵

```
┌────────────────────────────────────────────────────────────────────────────┐
│                        网络搜索 15级降级方案                                 │
├────┬─────────────────────┬──────────────────┬─────────────────────────────┤
│ 级别│       工具/方案      │     适用场景      │          配置要求           │
├────┼─────────────────────┼──────────────────┼─────────────────────────────┤
│ P1 │ WebSearch (Claude)  │ 通用搜索          │ 无                          │
│ P2 │ WebFetch + Google   │ 直接访问搜索结果页 │ 构建搜索URL                 │
│ P3 │ WebFetch + Bing     │ Google被墙时      │ 构建搜索URL                 │
│ P4 │ WebFetch + DuckDuckGo│ 隐私搜索         │ 构建搜索URL                 │
│ P5 │ browser-use(real)   │ 需登录/复杂页面   │ Chrome浏览器                │
│ P6 │ DrissionPage        │ 反爬严格网站      │ Python库                   │
│ P7 │ Selenium + 搜索引擎  │ 需JS渲染          │ ChromeDriver               │
│ P8 │ Playwright + 搜索    │ 复杂交互          │ Playwright                 │
│ P9 │ SerpAPI/Google CSE  │ 专业搜索API       │ API Key                    │
│ P10│ Serper API          │ 快速搜索API       │ API Key                    │
│ P11│ Bing Search API     │ 微软搜索API       │ Azure Key                  │
│ P12│ Twitter/X API       │ 社交媒体搜索      │ Twitter Developer账号       │
│ P13│ Reddit API          │ 社区讨论搜索      │ Reddit Developer账号        │
│ P14│ Wayback Machine     │ 历史网页搜索      │ 无                         │
│ P15│ 用户协助            │ 最终兜底          │ 无                         │
└────┴─────────────────────┴──────────────────┴─────────────────────────────┘
```

### 搜索引擎轮换策略

| 搜索引擎 | 区域优势 | 反爬程度 | 推荐场景 |
|----------|----------|----------|----------|
| Google | 全球 | 高 | 首选，结果最全 |
| Bing | 欧美 | 中 | Google失败时 |
| DuckDuckGo | 全球 | 低 | 隐私友好，反爬弱 |
| Baidu | 中国 | 高 | 中文内容首选 |
| Sogou | 中国 | 中 | 微信内容 |
| Yandex | 俄语区 | 中 | 俄语内容 |
| Naver | 韩国 | 中 | 韩语内容 |

### 代码实现

```python
class WebSearchFallbackChain:
    """网络搜索15级降级链"""

    def __init__(self):
        self.engines = [
            ("google", "https://www.google.com/search?q={query}"),
            ("bing", "https://www.bing.com/search?q={query}"),
            ("duckduckgo", "https://duckduckgo.com/?q={query}"),
            ("baidu", "https://www.baidu.com/s?wd={query}"),
            ("sogou", "https://www.sogou.com/web?query={query}"),
        ]
        self.attempt_log = []

    async def search(self, query: str, max_attempts: int = 15) -> dict:
        """执行搜索，最多尝试15种方案"""

        # P1: WebSearch
        result = await self._try_websearch(query)
        if result["success"]:
            return result

        # P2-P4: WebFetch + 多搜索引擎
        for engine_name, url_template in self.engines:
            result = await self._try_webfetch_search(query, engine_name, url_template)
            if result["success"]:
                return result

        # P5-P8: 浏览器自动化方案
        for browser_tool in ["browser_use", "drissionpage", "selenium", "playwright"]:
            result = await self._try_browser_search(query, browser_tool)
            if result["success"]:
                return result

        # P9-P11: 搜索API
        for api in ["serpapi", "serper", "bing_api"]:
            result = await self._try_search_api(query, api)
            if result["success"]:
                return result

        # P12-P13: 社交媒体搜索
        for platform in ["twitter", "reddit"]:
            result = await self._try_social_search(query, platform)
            if result["success"]:
                return result

        # P14: Wayback Machine
        result = await self._try_wayback(query)
        if result["success"]:
            return result

        # P15: 用户协助
        return self._request_user_help(query)

    def _request_user_help(self, query: str) -> dict:
        """请求用户协助，但提供详细已尝试记录"""
        return {
            "success": False,
            "source": "manual_required",
            "data": None,
            "attempts": self.attempt_log,
            "message": f"已尝试{len(self.attempt_log)}种方案均失败，请手动搜索: {query}",
            "suggestions": [
                "1. 检查网络连接",
                "2. 尝试VPN切换地区",
                "3. 使用其他设备搜索",
                "4. 查阅图书馆/数据库资源"
            ]
        }
```

---

## 二、网页抓取工具链（20级降级方案）

### 降级矩阵

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         网页抓取 20级降级方案                                 │
├────┬──────────────────────┬────────────────────┬────────────────────────────┤
│级别 │       工具/方案       │      适用场景       │         配置要求           │
├────┼──────────────────────┼────────────────────┼────────────────────────────┤
│ P1 │ WebFetch             │ 静态页面           │ 无                         │
│ P2 │ WebFetch + headers伪装│ 基础反爬          │ 自定义User-Agent           │
│ P3 │ DrissionPage         │ 中等反爬           │ Python库                   │
│ P4 │ browser-use(chromium)│ JS渲染页面         │ browser-use                │
│ P5 │ browser-use(real)    │ 需登录态           │ Chrome浏览器               │
│ P6 │ Selenium             │ 复杂交互           │ ChromeDriver               │
│ P7 │ Playwright           │ 企业级抓取         │ Playwright                 │
│ P8 │ Puppeteer            │ Node环境           │ Puppeteer                  │
│ P9 │ requests + Session   │ 保持Cookie         │ requests                   │
│ P10│ httpx + async        │ 异步高性能         │ httpx                      │
│ P11│ curl_cffi            │ TLS指纹伪装        │ curl_cffi                  │
│ P12│ undetected_chromedriver│ 反检测浏览器     │ undetected_chromedriver    │
│ P13│ playwright-stealth    │ 隐身模式          │ playwright-stealth         │
│ P14│ 内部API调用          │ 绕过前端           │ 分析Network面板            │
│ P15│ JSON数据端点         │ 直接获取数据       │ 查找data/xxx.json          │
│ P16│ 移动端版本URL        │ 反爬较弱           │ m.xxx.com / amp页面        │
│ P17│ Google Cache         │ 获取缓存版本       │ webcache.googleusercontent │
│ P18│ Wayback Machine      │ 历史快照           │ archive.org                │
│ P19│ 代理池轮换           │ IP封禁             │ 代理服务                   │
│ P20│ 用户协助             │ 最终兜底           │ 无                         │
└────┴──────────────────────┴────────────────────┴────────────────────────────┘
```

### 失败原因 → 方案映射

| 失败原因 | 推荐方案 | 原因 |
|----------|----------|------|
| 403 Forbidden | P3 DrissionPage / P12 undetected_chromedriver | 绕过基础检测 |
| Cloudflare验证 | P13 playwright-stealth / P11 curl_cffi | TLS指纹+行为模拟 |
| JS渲染空白 | P4-P8 浏览器自动化 | 需要执行JS |
| Cookie验证 | P5 browser-use(real) / P9 requests Session | 保持登录态 |
| IP封禁 | P19 代理池轮换 | 换IP |
| 频率限制 | 延迟重试 + 分布式 | 降低频率 |
| 地域限制 | VPN + 多区域代理 | 切换地区 |
| 参数签名 | P14 内部API分析 | 绕过前端签名 |

### 内部API探测策略

```python
class InternalAPIFinder:
    """探测网站的内部API端点"""

    COMMON_API_PATTERNS = [
        "/api/v1/{resource}",
        "/api/v2/{resource}",
        "/api/{resource}",
        "/data/{resource}.json",
        "/service/{resource}",
        "/graphql",
        "/__api__/{resource}",
        "/.json",
    ]

    async def find_internal_api(self, page_url: str) -> list:
        """
        通过以下方式发现内部API:
        1. 分析Network请求
        2. 查看页面源码中的fetch/axios调用
        3. 尝试常见API路径
        """
        apis = []

        # 方法1: Network分析
        async with playwright_page() as page:
            await page.goto(page_url)
            requests = page.context.request.all()
            for req in requests:
                if any(p in req.url for p in ["/api/", "/data/", ".json"]):
                    apis.append(req.url)

        # 方法2: 源码分析
        html = await fetch_html(page_url)
        import re
        fetch_calls = re.findall(r'fetch\(["\']([^"\']+)["\']', html)
        apis.extend(fetch_calls)

        # 方法3: 路径探测
        for pattern in self.COMMON_API_PATTERNS:
            test_url = build_api_url(page_url, pattern)
            if await test_endpoint(test_url):
                apis.append(test_url)

        return list(set(apis))
```

### 移动端/AMP页面探测

```python
MOBILE_PATTERNS = {
    "mobile_subdomain": ["m.{domain}", "mobile.{domain}"],
    "amp_path": ["/amp/", "/amp.html", "?amp=1"],
    "responsive_param": ["?mobile=1", "?view=mobile"],
}

async def try_mobile_version(url: str) -> dict:
    """尝试访问移动端版本，通常反爬更弱"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc

    mobile_urls = []

    # 子域名方式
    for pattern in MOBILE_PATTERNS["mobile_subdomain"]:
        mobile_domain = pattern.format(domain=domain)
        mobile_urls.append(f"{parsed.scheme}://{mobile_domain}{parsed.path}")

    # 路径方式
    for pattern in MOBILE_PATTERNS["amp_path"]:
        mobile_urls.append(f"{url.rstrip('/')}{pattern}")

    for mobile_url in mobile_urls:
        result = await try_fetch(mobile_url)
        if result["success"]:
            return result

    return {"success": False}
```

---

## 三、截图采集工具链（15级降级方案）

### 降级矩阵

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         截图采集 15级降级方案                                 │
├────┬──────────────────────┬────────────────────┬────────────────────────────┤
│级别 │       工具/方案       │      适用场景       │         输出格式           │
├────┼──────────────────────┼────────────────────┼────────────────────────────┤
│ P1 │ browser-use screenshot│ 网页截图          │ base64/PNG                 │
│ P2 │ Selenium screenshot  │ 精确控制           │ PNG                        │
│ P3 │ Playwright screenshot│ 企业级             │ PNG/PDF                    │
│ P4 │ Puppeteer screenshot │ Node环境           │ PNG/PDF                    │
│ P5 │ wkhtmltoimage        │ 命令行工具         │ PNG                        │
│ P6 │ CutyCapt             │ Windows工具        │ PNG/PDF/SVG                │
│ P7 │ ScreenshotAPI.com    │ 云服务             │ PNG/JPG                    │
│ P8 │ UrlBox.io            │ 云服务             │ PNG                        │
│ P9 │ ScreenshotOne        │ 云服务             │ PNG                        │
│ P10│ Apiflash             │ 云服务             │ PNG                        │
│ P11│ 评测视频截图          │ 无法访问官网时     │ PNG                        │
│ P12│ YouTube关键帧提取    │ 视频内容           │ PNG                        │
│ P13│ PDF转换+图像提取     │ PDF文档            │ PNG                        │
│ P14│ OCR屏幕识别         │ 无法保存截图时     │ 文字数据                   │
│ P15│ 用户协助            │ 最终兜底           │ 任意格式                   │
└────┴──────────────────────┴────────────────────┴────────────────────────────┘
```

### 云服务截图API

```python
SCREENSHOT_APIS = {
    "screenshotapi": {
        "url": "https://api.screenshotapi.net/screenshot",
        "params": {"token": "API_KEY", "url": "{target_url}", "output": "image"},
        "free_limit": "100/month"
    },
    "urlbox": {
        "url": "https://api.urlbox.io/v1/{api_key}",
        "params": {"url": "{target_url}"},
        "free_limit": "500/month"
    },
    "apiflash": {
        "url": "https://api.apiflash.com/v1/urltoimage",
        "params": {"access_key": "API_KEY", "url": "{target_url}"},
        "free_limit": "100/month"
    },
    "screenshotone": {
        "url": "https://api.screenshotone.com/take",
        "params": {"access_key": "API_KEY", "url": "{target_url}"},
        "free_limit": "100/month"
    }
}

async def cloud_screenshot(url: str, output_path: str) -> bool:
    """使用云服务截图"""
    for service, config in SCREENSHOT_APIS.items():
        try:
            api_url = config["url"].format(api_key=os.getenv(f"{service.upper()}_KEY", ""))
            params = {k: v.format(target_url=url) for k, v in config["params"].items()}

            response = await async_get(api_url, params=params)
            if response.status == 200:
                with open(output_path, "wb") as f:
                    f.write(response.content)
                return True
        except Exception as e:
            log(f"{service} failed: {e}")
            continue
    return False
```

### 视频/评测内容截图策略

```python
async def screenshot_from_video(video_url: str, timestamps: list, output_dir: str) -> list:
    """
    从视频内容提取关键帧截图
    适用于无法直接访问产品官网的情况
    """
    import subprocess
    from pathlib import Path

    screenshots = []

    # YouTube视频
    if "youtube.com" in video_url or "youtu.be" in video_url:
        # 使用yt-dlp获取视频信息
        for ts in timestamps:
            # 直接获取YouTube缩略图或特定时间帧
            thumb_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            screenshot_path = f"{output_dir}/frame_{ts}.png"
            await download_image(thumb_url, screenshot_path)
            screenshots.append(screenshot_path)

    # 其他视频源
    else:
        # 使用ffmpeg提取帧
        for ts in timestamps:
            cmd = f'ffmpeg -ss {ts} -i "{video_url}" -frames:v 1 {output_dir}/frame_{ts}.png'
            subprocess.run(cmd, shell=True)
            screenshots.append(f"{output_dir}/frame_{ts}.png")

    return screenshots
```

---

## 四、数据采集工具链（18级降级方案）

### 降级矩阵

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         数据采集 18级降级方案                                 │
├────┬──────────────────────┬────────────────────┬────────────────────────────┤
│级别 │       工具/方案       │      适用场景       │         配置要求           │
├────┼──────────────────────┼────────────────────┼────────────────────────────┤
│ P1 │ WebFetch + 正则解析  │ 简单结构化数据     │ 正则表达式                  │
│ P2 │ WebFetch + BeautifulSoup│ HTML解析        │ beautifulsoup4             │
│ P3 │ WebFetch + lxml/XPath│ 精确定位          │ lxml                       │
│ P4 │ WebFetch + parsel   │ CSS选择器          │ parsel                     │
│ P5 │ DrissionPage + 元素定位│ 动态内容         │ DrissionPage               │
│ P6 │ browser-use extract │ LLM智能提取        │ browser-use + API Key      │
│ P7 │ 内部JSON API        │ 绕过前端           │ Network分析                │
│ P8 │ GraphQL查询         │ GraphQL接口        │ 分析GraphQL Schema         │
│ P9 │ RSS/Atom订阅        │ 内容订阅源         │ RSS阅读器                  │
│ P10│ sitemap.xml解析     │ 网站结构           │ XML解析                    │
│ P11│ 结构化数据(JSON-LD) │ SEO数据            │ JSON-LD解析                │
│ P12│ Open Graph标签      │ 社交元数据         │ OG标签解析                 │
│ P13│ 第三方数据API       │ 专业数据源         │ SimilarWeb/Semrush等       │
│ P14│ Diffbot/Import.io   │ AI提取服务         │ API Key                    │
│ P15│ OCR图像识别         │ 图片内文字         │ Tesseract/PaddleOCR        │
│ P16│ LLM文本提取        │ 非结构化文本       │ GPT-4/Claude API           │
│ P17│ 本地知识库检索      │ 已有资料           │ 向量数据库                 │
│ P18│ 用户协助           │ 最终兜底           │ 无                         │
└────┴──────────────────────┴────────────────────┴────────────────────────────┘
```

### 结构化数据提取策略

```python
STRUCTURED_DATA_SOURCES = {
    "json_ld": {
        "selector": 'script[type="application/ld+json"]',
        "parse": "json.loads",
        "schemas": ["Product", "Offer", "AggregateRating", "Organization"]
    },
    "open_graph": {
        "selectors": ['meta[property="og:{key}"]', 'meta[name="twitter:{key}"]'],
        "keys": ["title", "description", "image", "price", "availability"]
    },
    "microdata": {
        "selector": '[itemscope][itemtype]',
        "parse": "microdata.extract"
    },
    "schema_org": {
        "selector": '[itemtype*="schema.org"]',
        "types": ["Product", "Offer", "Brand"]
    }
}

async def extract_structured_data(html: str) -> dict:
    """从页面提取所有结构化数据"""
    from bs4 import BeautifulSoup
    import json

    soup = BeautifulSoup(html, 'html.parser')
    data = {}

    # JSON-LD
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            ld_data = json.loads(script.string)
            for schema in STRUCTURED_DATA_SOURCES["json_ld"]["schemas"]:
                if ld_data.get("@type") == schema:
                    data[f"json_ld_{schema.lower()}"] = ld_data
        except:
            pass

    # Open Graph
    og_data = {}
    for key in STRUCTURED_DATA_SOURCES["open_graph"]["keys"]:
        meta = soup.find('meta', property=f'og:{key}')
        if meta:
            og_data[key] = meta.get('content')
    if og_data:
        data["open_graph"] = og_data

    # Schema.org Microdata
    for item in soup.find_all(itemtype=True):
        item_type = item.get('itemtype', '').split('/')[-1]
        item_data = {}
        for prop in item.find_all(itemprop=True):
            item_data[prop.get('itemprop')] = prop.get('content') or prop.text.strip()
        data[f"microdata_{item_type.lower()}"] = item_data

    return data
```

### 第三方数据API

```python
THIRD_PARTY_DATA_APIS = {
    "similarweb": {
        "endpoint": "https://api.similarweb.com/v1/website/{domain}/total-traffic-and-engagement/visits",
        "data": ["访问量", "排名", "跳出率", "停留时间"],
        "free_limit": "有限"
    },
    "semrush": {
        "endpoint": "https://api.semrush.com/",
        "data": ["关键词排名", "流量估算", "竞争对手分析"],
        "free_limit": "10次/天"
    },
    "builtwith": {
        "endpoint": "https://api.builtwith.com/v21/api.json",
        "data": ["技术栈", "服务器", "CDN", "分析工具"],
        "free_limit": "有限"
    },
    "crunchbase": {
        "endpoint": "https://api.crunchbase.com/api/v4/searches/entities",
        "data": ["公司信息", "融资", "团队", "竞争对手"],
        "free_limit": "需要申请"
    },
    "rapidapi_aggregators": {
        "endpoint": "https://rapidapi.com/",
        "data": ["各种数据聚合API"],
        "note": "一站式API市场"
    }
}
```

---

## 五、组合拳策略

### 5.1 搜索+抓取组合

```python
async def search_then_scrape(query: str, target_data: list) -> dict:
    """
    先搜索找到相关页面，再抓取提取数据
    """
    # Step 1: 多引擎搜索
    search_results = await multi_engine_search(query)

    # Step 2: 对每个结果尝试抓取
    for result in search_results:
        url = result["url"]

        # Step 3: 尝试多种抓取方式
        html = await try_all_fetch_methods(url)

        if html:
            # Step 4: 尝试多种解析方式
            data = await try_all_parse_methods(html, target_data)

            if data:
                return {
                    "success": True,
                    "source_url": url,
                    "data": data,
                    "attempts_log": []
                }

    return {"success": False}
```

### 5.2 缓存+实时组合

```python
async def cached_then_live(url: str, max_age_hours: int = 24) -> dict:
    """
    优先使用缓存，过期则实时获取
    """
    # Step 1: 检查本地缓存
    cached = check_local_cache(url)
    if cached and not is_expired(cached, max_age_hours):
        return cached

    # Step 2: 检查Wayback Machine
    wayback = await check_wayback(url)
    if wayback:
        save_to_cache(url, wayback)
        return wayback

    # Step 3: 检查Google Cache
    google_cache = await check_google_cache(url)
    if google_cache:
        save_to_cache(url, google_cache)
        return google_cache

    # Step 4: 实时获取
    live_data = await try_all_fetch_methods(url)
    if live_data:
        save_to_cache(url, live_data)
        return live_data

    # Step 5: 使用过期缓存（聊胜于无）
    if cached:
        return {**cached, "warning": "使用过期缓存数据"}

    return {"success": False}
```

### 5.3 官网+第三方交叉验证

```python
async def cross_validate_data(product_name: str, data_type: str) -> dict:
    """
    多来源交叉验证数据准确性
    """
    sources = []

    # 官网数据
    official = await scrape_official_site(product_name)
    if official:
        sources.append(("official", official))

    # 电商数据
    ecommerce = await scrape_ecommerce(product_name)
    if ecommerce:
        sources.append(("ecommerce", ecommerce))

    # 媒体评测
    reviews = await scrape_reviews(product_name)
    if reviews:
        sources.append(("reviews", reviews))

    # 第三方API
    third_party = await query_third_party_api(product_name)
    if third_party:
        sources.append(("third_party", third_party))

    # 交叉验证
    return validate_and_merge(sources)
```

---

## 六、智能失败诊断

### 失败原因自动识别

```python
FAILURE_PATTERNS = {
    "cloudflare": {
        "indicators": ["cf-browser-verification", "cf-ray:", "challenge-platform"],
        "solution": "playwright-stealth / curl_cffi / 云服务API"
    },
    "recaptcha": {
        "indicators": ["recaptcha", "g-recaptcha", "hcaptcha"],
        "solution": "2Captcha / Anti-Captcha服务"
    },
    "rate_limit": {
        "indicators": ["429", "rate limit", "too many requests"],
        "solution": "延迟重试 / 代理轮换 / 分布式请求"
    },
    "geo_block": {
        "indicators": ["not available in your region", "country blocked"],
        "solution": "VPN切换 / 代理 / 云服务API"
    },
    "js_required": {
        "indicators": ["<noscript>", "javascript required", "enable javascript"],
        "solution": "浏览器自动化 / browser-use"
    },
    "login_required": {
        "indicators": ["sign in", "log in", "authentication required"],
        "solution": "browser-use(real) / 用户协助"
    }
}

def diagnose_failure(response) -> dict:
    """自动诊断失败原因并推荐解决方案"""
    for failure_type, config in FAILURE_PATTERNS.items():
        for indicator in config["indicators"]:
            if indicator.lower() in response.text.lower() or indicator in str(response.status):
                return {
                    "failure_type": failure_type,
                    "solution": config["solution"],
                    "confidence": "high"
                }

    return {
        "failure_type": "unknown",
        "solution": "尝试所有降级方案",
        "confidence": "low"
    }
```

---

## 七、完整降级流程图

```
                    ┌─────────────────┐
                    │    任务开始      │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   主工具尝试     │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
       ┌──────▼──────┐              ┌───────▼──────┐
       │   成功？    │              │   失败诊断   │
       └──────┬──────┘              └───────┬──────┘
              │                             │
              │                    ┌────────▼────────┐
              │                    │ 识别失败类型    │
              │                    └────────┬────────┘
              │                             │
              │                    ┌────────▼────────┐
              │                    │ 选择对应策略    │
              │                    └────────┬────────┘
              │                             │
       ┌──────▼──────┐              ┌───────▼──────┐
       │   返回结果   │◄─────────────│   备用方案1  │
       └─────────────┘              └───────┬──────┘
                                            │
                                   ┌────────▼────────┐
                                   │   成功？        │
                                   └────────┬────────┘
                                            │
                              ┌─────────────┴─────────────┐
                              │                           │
                       ┌──────▼──────┐            ┌───────▼──────┐
                       │   返回结果   │            │   备用方案2  │
                       └─────────────┘            └───────┬──────┘
                                                          │
                                                         ...
                                                          │
                                                  ┌───────▼──────┐
                                                  │ 备用方案N    │
                                                  └───────┬──────┘
                                                          │
                                                  ┌───────▼──────┐
                                                  │ 用户协助     │
                                                  └──────────────┘
```

---

## 八、配置与阈值

```json
{
  "fallback_config": {
    "max_attempts": 15,
    "timeout_per_attempt": 30,
    "delay_between_attempts": [1, 2, 5, 10, 30],
    "success_threshold": "any_data_returned",
    "quality_threshold": {
      "min_data_points": 5,
      "required_fields": []
    }
  },
  "tool_priorities": {
    "search": ["websearch", "webfetch", "browser_use", "api", "social", "cache", "manual"],
    "fetch": ["webfetch", "drissionpage", "browser_use", "selenium", "playwright", "api", "cache", "manual"],
    "screenshot": ["browser_use", "selenium", "playwright", "cloud_api", "video", "manual"],
    "parse": ["regex", "beautifulsoup", "lxml", "llm", "ocr", "manual"]
  },
  "api_keys_required": {
    "serpapi": "SERPAPI_KEY",
    "serper": "SERPER_KEY",
    "screenshotapi": "SCREENSHOTAPI_KEY",
    "similarweb": "SIMILARWEB_KEY"
  }
}
```

---

*文档版本: 2.0*
*最后更新: 2026-03-16*
*理念: 办法比困难多 — AI军团永不放弃*