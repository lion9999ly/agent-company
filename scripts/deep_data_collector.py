"""
@description: 深度数据采集器 - 多策略突破采集障碍
@dependencies: requests, selenium, webdriver_manager
@last_modified: 2026-03-16
"""

import re
import json
import time
import requests
from datetime import datetime
from typing import Optional, Dict, List, Any
from pathlib import Path

# 全局配置
OUTPUT_DIR = Path(".ai-state/competitive_analysis")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

class DeepDataCollector:
    """深度数据采集器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
        })
        self.collected_data = {}
        self.sources = []

    def save_raw_page(self, filename: str, content: str):
        """保存原始页面"""
        filepath = OUTPUT_DIR / f"raw_{filename}.html"
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  [保存] {filepath}")
        return str(filepath)

    def extract_json_from_html(self, html: str) -> List[Dict]:
        """从HTML中提取JSON数据"""
        json_data_list = []

        # 匹配 <script> 标签中的 JSON
        script_pattern = r'<script[^>]*>\s*(\{[\s\S]*?\})\s*</script>'
        for match in re.finditer(script_pattern, html):
            try:
                data = json.loads(match.group(1))
                json_data_list.append(data)
            except:
                pass

        # 匹配 window.xxx = {...} 格式
        window_pattern = r'window\.\w+\s*=\s*(\{[\s\S]*?\});'
        for match in re.finditer(window_pattern, html):
            try:
                data = json.loads(match.group(1))
                json_data_list.append(data)
            except:
                pass

        return json_data_list

    def collect_jd_mobile(self, sku_id: str) -> Dict:
        """采集京东移动端页面"""
        print(f"\n[京东移动端] SKU: {sku_id}")
        url = f"https://item.m.jd.com/product/{sku_id}.html"

        result = {"success": False, "data": {}, "source": url}

        try:
            resp = self.session.get(url, timeout=30)
            print(f"  状态: {resp.status_code}, 长度: {len(resp.text)}")

            if resp.status_code == 200:
                html = resp.text
                self.save_raw_page(f"jd_{sku_id}", html)

                # 提取商品名称
                name_patterns = [
                    r'"name"\s*:\s*"([^"]+)"',
                    r'"skuName"\s*:\s*"([^"]+)"',
                    r'<title>([^<]+)</title>',
                ]
                for pattern in name_patterns:
                    match = re.search(pattern, html)
                    if match:
                        result["data"]["name"] = match.group(1).strip()
                        break

                # 提取价格
                price_patterns = [
                    r'"price"\s*:\s*"?([\d.]+)"?',
                    r'"p"\s*:\s*"?([\d.]+)"?',
                    r'¥\s*([\d.]+)',
                ]
                for pattern in price_patterns:
                    match = re.search(pattern, html)
                    if match:
                        result["data"]["price"] = match.group(1)
                        break

                # 提取规格参数
                specs = {}
                spec_patterns = [
                    r'"([^"]+)"\s*:\s*"([^"]+)"',
                ]
                # 尝试提取所有键值对
                for match in re.finditer(r'"(\w+)"\s*:\s*"([^"]{1,50})"', html):
                    key, value = match.groups()
                    if len(value) > 2 and key not in specs:
                        specs[key] = value

                if specs:
                    result["data"]["specs"] = specs

                result["success"] = True

        except Exception as e:
            result["error"] = str(e)
            print(f"  错误: {e}")

        return result

    def collect_tmall_shop(self) -> Dict:
        """采集天猫店铺"""
        print("\n[天猫店铺]")
        url = "https://inmo.tmall.com/shop/view_shop.htm"

        result = {"success": False, "data": {}, "source": url}

        try:
            resp = self.session.get(url, timeout=30)
            print(f"  状态: {resp.status_code}, 长度: {len(resp.text)}")

            if resp.status_code == 200:
                html = resp.text
                self.save_raw_page("tmall_shop", html)

                # 提取店铺名
                shop_match = re.search(r'"shopName"\s*:\s*"([^"]+)"', html)
                if shop_match:
                    result["data"]["shop_name"] = shop_match.group(1)

                # 提取商品列表
                products = []
                item_pattern = r'"itemId"\s*:\s*"(\d+)".*?"title"\s*:\s*"([^"]+)"'
                for match in re.finditer(item_pattern, html, re.DOTALL):
                    products.append({
                        "item_id": match.group(1),
                        "title": match.group(2)
                    })

                if products:
                    result["data"]["products"] = products[:10]  # 最多10个

                result["success"] = True

        except Exception as e:
            result["error"] = str(e)
            print(f"  错误: {e}")

        return result

    def collect_xiaohongshu(self, keyword: str) -> Dict:
        """采集小红书搜索结果"""
        print(f"\n[小红书] 关键词: {keyword}")
        url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"

        result = {"success": False, "data": {}, "source": url}

        try:
            resp = self.session.get(url, timeout=30)
            print(f"  状态: {resp.status_code}, 长度: {len(resp.text)}")

            if resp.status_code == 200:
                html = resp.text

                # 小红书内容通常是JS渲染的，提取初始数据
                notes = []

                # 提取笔记ID和标题
                note_pattern = r'"noteId"\s*:\s*"([^"]+)".*?"title"\s*:\s*"([^"]+)"'
                for match in re.finditer(note_pattern, html, re.DOTALL):
                    notes.append({
                        "note_id": match.group(1),
                        "title": match.group(2)[:50]
                    })

                if notes:
                    result["data"]["notes"] = notes[:10]

                # 提取用户评论内容
                content_pattern = r'"desc"\s*:\s*"([^"]{20,200})"'
                contents = []
                for match in re.finditer(content_pattern, html):
                    contents.append(match.group(1))

                if contents:
                    result["data"]["contents"] = contents[:5]

                result["success"] = len(notes) > 0 or len(contents) > 0

        except Exception as e:
            result["error"] = str(e)
            print(f"  错误: {e}")

        return result

    def collect_with_selenium(self, url: str, wait_time: int = 5) -> Dict:
        """使用Selenium采集动态页面"""
        print(f"\n[Selenium] {url}")

        result = {"success": False, "data": {}, "source": url}

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from webdriver_manager.chrome import ChromeDriverManager

            options = Options()
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(30)

            try:
                driver.get(url)
                time.sleep(wait_time)  # 等待JS渲染

                html = driver.page_source
                print(f"  页面长度: {len(html)}")

                # 保存完整页面
                filename = url.split('//')[1].split('/')[0].replace('.', '_')
                self.save_raw_page(f"selenium_{filename}", html)

                result["data"]["page_length"] = len(html)
                result["success"] = True

                # 尝试提取文本内容
                try:
                    body = driver.find_element(By.TAG_NAME, "body")
                    text = body.text
                    result["data"]["text_preview"] = text[:500]
                except:
                    pass

            finally:
                driver.quit()

        except ImportError as e:
            result["error"] = f"Selenium未正确安装: {e}"
            print(f"  警告: {e}")
        except Exception as e:
            result["error"] = str(e)
            print(f"  错误: {e}")

        return result

    def run_full_collection(self) -> Dict:
        """执行完整采集"""
        print("=" * 60)
        print("深度数据采集器 - 开始采集")
        print("=" * 60)

        all_results = {
            "start_time": datetime.now().isoformat(),
            "sources": [],
            "data": {}
        }

        # 1. 京东移动端 - INMO Air2
        jd_result = self.collect_jd_mobile("100070432376")
        if jd_result["success"]:
            all_results["sources"].append({
                "name": "京东移动端-INMO Air2",
                "url": jd_result["source"],
                "data": jd_result["data"]
            })

        # 2. 天猫店铺
        tmall_result = self.collect_tmall_shop()
        if tmall_result["success"]:
            all_results["sources"].append({
                "name": "天猫-INMO旗舰店",
                "url": tmall_result["source"],
                "data": tmall_result["data"]
            })

        # 3. 小红书
        xhs_result = self.collect_xiaohongshu("影目Air")
        if xhs_result["success"]:
            all_results["sources"].append({
                "name": "小红书-影目Air",
                "url": xhs_result["source"],
                "data": xhs_result["data"]
            })

        # 4. Selenium采集京东PC版
        selenium_result = self.collect_with_selenium(
            "https://item.jd.com/100070432376.html",
            wait_time=3
        )
        if selenium_result["success"]:
            all_results["sources"].append({
                "name": "Selenium-京东PC版",
                "url": selenium_result["source"],
                "data": selenium_result["data"]
            })

        # 5. Selenium采集天猫商品
        selenium_tmall = self.collect_with_selenium(
            "https://detail.tmall.com/item.htm?id=696226347852",
            wait_time=3
        )
        if selenium_tmall["success"]:
            all_results["sources"].append({
                "name": "Selenium-天猫商品",
                "url": selenium_tmall["source"],
                "data": selenium_tmall["data"]
            })

        all_results["end_time"] = datetime.now().isoformat()

        # 保存结果
        result_file = OUTPUT_DIR / "collection_results.json"
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"\n[完成] 结果已保存: {result_file}")

        print(f"\n[统计] 成功采集 {len(all_results['sources'])} 个数据源")

        return all_results


if __name__ == "__main__":
    collector = DeepDataCollector()
    results = collector.run_full_collection()

    # 打印采集到的数据摘要
    print("\n" + "=" * 60)
    print("采集数据摘要")
    print("=" * 60)

    for source in results.get("sources", []):
        print(f"\n[{source['name']}]")
        print(f"  URL: {source['url']}")
        data = source.get("data", {})
        for key, value in data.items():
            if isinstance(value, dict):
                print(f"  {key}: {list(value.keys())[:5]}...")
            elif isinstance(value, list):
                print(f"  {key}: {len(value)}项")
            elif isinstance(value, str) and len(value) > 50:
                print(f"  {key}: {value[:50]}...")
            else:
                print(f"  {key}: {value}")