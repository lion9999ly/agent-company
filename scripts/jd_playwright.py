"""
@description: 使用Playwright爬取京东商品评价（无需登录，通过公开API）
@dependencies: playwright
@last_modified: 2026-03-16
"""

from playwright.sync_api import sync_playwright
import json
import time
from pathlib import Path

def scrape_jd_reviews(product_id="100070432376"):
    """爬取京东商品评价（通过公开API）"""

    output_dir = Path(".ai-state/competitive_analysis")
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "product_id": product_id,
        "summary": None,
        "reviews": []
    }

    with sync_playwright() as p:
        # 启动浏览器（headless模式）
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = context.new_page()

        try:
            # 访问商品页面
            url = f"https://item.jd.com/{product_id}.html"
            print(f"访问: {url}")
            page.goto(url, wait_until='networkidle', timeout=30000)

            # 等待页面加载
            time.sleep(2)

            # 获取页面标题
            title = page.title()
            print(f"页面标题: {title}")

            # 截图
            page.screenshot(path=str(output_dir / "jd_playwright_screenshot.png"))
            print("截图已保存")

            # 尝试获取评价摘要（公开API）
            api_url = f"https://club.jd.com/comment/productCommentSummaries.action?referenceIds={product_id}"

            # 在页面中执行请求
            response = page.evaluate(f'''
                async () => {{
                    const response = await fetch("{api_url}");
                    return await response.text();
                }}
            ''')

            if response:
                try:
                    data = json.loads(response)
                    results["summary"] = data
                    print("评价摘要获取成功")
                except:
                    pass

            # 保存页面HTML
            html = page.content()
            with open(output_dir / "jd_playwright.html", 'w', encoding='utf-8') as f:
                f.write(html)
            print("HTML已保存")

        except Exception as e:
            print(f"错误: {e}")
            results["error"] = str(e)

        finally:
            browser.close()

    # 保存结果
    with open(output_dir / "jd_playwright_results.json", 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return results

if __name__ == "__main__":
    print("=== Playwright 京东爬虫 ===\n")
    scrape_jd_reviews()