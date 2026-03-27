"""
@description: 使用DrissionPage采集京东/天猫数据（隐身模式绕过反爬）
@dependencies: DrissionPage
@last_modified: 2026-03-16
"""

from DrissionPage import ChromiumPage, ChromiumOptions
from datetime import datetime
from pathlib import Path
import json
import time
import random

def human_like_wait():
    """随机等待，模拟人类行为"""
    time.sleep(random.uniform(1.5, 3.5))

def collect_with_drissionpage():
    """使用DrissionPage采集数据 - 隐身模式"""

    output_dir = Path(".ai-state/competitive_analysis")
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "timestamp": datetime.now().isoformat(),
        "sources": []
    }

    # 配置浏览器
    co = ChromiumOptions()
    co.headless(False)  # 显示浏览器
    co.set_argument('--disable-blink-features=AutomationControlled')  # 隐藏自动化特征
    co.set_argument('--disable-infobars')
    co.set_argument('--start-maximized')
    # 随机User-Agent
    co.set_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')

    page = None
    try:
        print("[启动] 正在启动浏览器...")
        page = ChromiumPage(co)
        page.set.load_mode.eager()  # 急切加载模式

        # ========== 京东商品页 ==========
        print("\n[1/4] 访问京东商品页...")
        page.get("https://item.jd.com/100070432376.html")
        human_like_wait()

        jd_data = {
            "url": "https://item.jd.com/100070432376.html",
            "title": "",
            "price": "",
            "specs": {},
            "reviews": []
        }

        # 提取标题
        try:
            title_elem = page.ele('css:.sku-name', timeout=10)
            if title_elem:
                jd_data["title"] = title_elem.text.strip()
                print(f"  标题: {jd_data['title'][:60]}...")
        except Exception as e:
            print(f"  标题提取失败: {e}")

        # 提取价格
        try:
            price_elem = page.ele('css:.p-price .price', timeout=10)
            if not price_elem:
                price_elem = page.ele('xpath://span[contains(@class, "price")]', timeout=5)
            if price_elem:
                jd_data["price"] = price_elem.text.strip()
                print(f"  价格: {jd_data['price']}")
        except Exception as e:
            print(f"  价格提取失败: {e}")

        # 提取规格参数 - 多种选择器
        try:
            # 方式1：规格表格
            spec_items = page.eles('css:.Ptable-item')
            if not spec_items:
                spec_items = page.eles('css:.detail-list li')
            if not spec_items:
                spec_items = page.eles('xpath://ul[contains(@class,"parameter2")]/li')

            for item in spec_items:
                try:
                    text = item.text.strip()
                    if '：' in text or ':' in text:
                        parts = text.replace('：', ':').split(':')
                        if len(parts) >= 2:
                            jd_data["specs"][parts[0].strip()] = parts[1].strip()
                except:
                    pass
            print(f"  规格: {len(jd_data['specs'])}项")
        except Exception as e:
            print(f"  规格提取失败: {e}")

        # 截图
        page.get_screenshot(str(output_dir / "jd_inmo_air3.png"), full_page=True)
        print("  截图已保存")

        # 保存HTML
        html_path = output_dir / "jd_inmo_air3.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(page.html)
        print(f"  HTML已保存")

        results["sources"].append({"type": "jd", "data": jd_data})

        # ========== 评论 ==========
        print("\n[2/4] 尝试获取评论...")
        human_like_wait()

        try:
            # 滚动到评论区域
            page.scroll.down(500)
            human_like_wait()

            # 点击评论标签
            comment_tab = page.ele('text:商品评价', timeout=5)
            if not comment_tab:
                comment_tab = page.ele('xpath://a[contains(text(),"评价")]', timeout=5)
            if comment_tab:
                comment_tab.click()
                human_like_wait()

                # 获取评论
                comments = page.eles('css:.comment-item', timeout=5)
                if not comments:
                    comments = page.eles('css:.comment-content', timeout=5)

                for comment in comments[:10]:
                    try:
                        text = comment.text.strip()
                        if text and len(text) > 10:
                            jd_data["reviews"].append(text)
                    except:
                        pass
                print(f"  获取评论: {len(jd_data['reviews'])}条")
        except Exception as e:
            print(f"  评论获取失败: {e}")

        # ========== 竞品数据 ==========
        competitors = [
            ("Xreal Air 2", "https://search.jd.com/Search?keyword=Xreal%20Air%202"),
            ("Rokid Max", "https://search.jd.com/Search?keyword=Rokid%20Max%20AR"),
        ]

        print("\n[3/4] 采集竞品数据...")
        competitor_data = []

        for name, url in competitors:
            print(f"  搜索: {name}")
            try:
                page.get(url)
                human_like_wait()

                # 获取第一个商品
                first_item = page.ele('css:.gl-item', timeout=10)
                if first_item:
                    title = first_item.ele('css:.p-name a', timeout=5)
                    price = first_item.ele('css:.p-price i', timeout=5)

                    comp_info = {
                        "name": name,
                        "title": title.text.strip() if title else "",
                        "price": price.text.strip() if price else "",
                        "url": url
                    }
                    competitor_data.append(comp_info)
                    print(f"    找到: {comp_info['title'][:40]}... 价格: {comp_info['price']}")
            except Exception as e:
                print(f"    失败: {e}")

        results["sources"].append({"type": "competitors", "data": competitor_data})

        # ========== 天猫 ==========
        print("\n[4/4] 访问天猫店铺...")
        try:
            page.get("https://inmo.tmall.com")
            human_like_wait()

            page.get_screenshot(str(output_dir / "tmall_inmo.png"), full_page=True)
            print("  天猫截图已保存")

            with open(output_dir / "tmall_inmo.html", 'w', encoding='utf-8') as f:
                f.write(page.html)
            results["sources"].append({"type": "tmall", "url": "https://inmo.tmall.com"})
        except Exception as e:
            print(f"  天猫访问失败: {e}")

        print("\n[完成] 数据采集完成")

    except Exception as e:
        print(f"[错误] {e}")
        import traceback
        traceback.print_exc()
        results["error"] = str(e)
    finally:
        if page:
            try:
                page.quit()
            except:
                pass

    # 保存结果
    with open(output_dir / "drissionpage_results.json", 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n结果保存到: {output_dir / 'drissionpage_results.json'}")

    return results

if __name__ == "__main__":
    collect_with_drissionpage()