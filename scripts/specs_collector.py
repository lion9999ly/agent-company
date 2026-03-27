"""
@description: 竞品规格数据采集器 - 多源降级采集
@dependencies: selenium, webdriver-manager
@last_modified: 2026-03-16
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
from pathlib import Path
import json
import time
import re

# 输出目录
OUTPUT_DIR = Path(".ai-state/competitive_analysis/specs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def create_driver(headless=True):
    """创建Chrome WebDriver"""
    options = Options()
    if headless:
        options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
    options.add_argument('--lang=en-US')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(30)
    return driver

def extract_text_safe(driver, selector, by=By.CSS_SELECTOR, default=""):
    """安全提取文本"""
    try:
        elem = driver.find_element(by, selector)
        return elem.text.strip()
    except:
        return default

def extract_all_texts(driver, selector, by=By.CSS_SELECTOR):
    """提取所有匹配元素的文本"""
    try:
        elems = driver.find_elements(by, selector)
        return [e.text.strip() for e in elems if e.text.strip()]
    except:
        return []

def collect_inmo_air3_specs():
    """采集INMO Air3规格数据 - 多源尝试"""
    print("=" * 60)
    print("采集 INMO Air3 规格")
    print("=" * 60)

    specs = {
        "product": "INMO Air3",
        "timestamp": datetime.now().isoformat(),
        "sources_tried": [],
        "data": {}
    }

    driver = None

    # 来源列表（按优先级）
    sources = [
        {
            "name": "INMO官网",
            "url": "https://www.inmo.com/en/air3",
            "type": "official"
        },
        {
            "name": "京东商品页",
            "url": "https://item.jd.com/100070432376.html",
            "type": "ecommerce"
        },
        {
            "name": "天猫旗舰店",
            "url": "https://detail.tmall.com/item.htm?id=742435265118",
            "type": "ecommerce"
        },
        {
            "name": "Amazon",
            "url": "https://www.amazon.com/s?k=INMO+Air3",
            "type": "ecommerce"
        }
    ]

    try:
        driver = create_driver(headless=True)

        for source in sources:
            print(f"\n[尝试] {source['name']}: {source['url']}")
            specs["sources_tried"].append(source["name"])

            try:
                driver.get(source["url"])
                time.sleep(3)

                # 检查是否成功加载
                page_source = driver.page_source

                if "404" in driver.title or "Not Found" in driver.title:
                    print(f"  [失败] 页面不存在")
                    continue

                if len(page_source) < 5000:
                    print(f"  [失败] 页面内容过少")
                    continue

                # 根据来源类型提取数据
                if source["type"] == "official":
                    data = extract_official_specs(driver, page_source)
                else:
                    data = extract_ecommerce_specs(driver, page_source)

                if data:
                    specs["data"].update(data)
                    specs["primary_source"] = source["name"]
                    print(f"  [成功] 获取 {len(data)} 项数据")

                    # 截图保存
                    screenshot_path = OUTPUT_DIR / f"inmo_air3_{source['name'].replace(' ', '_')}.png"
                    driver.save_screenshot(str(screenshot_path))
                    print(f"  [截图] {screenshot_path}")

                    # 成功获取后退出
                    break
                else:
                    print(f"  [失败] 未提取到有效数据")

            except Exception as e:
                print(f"  [错误] {str(e)[:100]}")
                continue

    except Exception as e:
        print(f"[全局错误] {e}")
        specs["error"] = str(e)
    finally:
        if driver:
            driver.quit()

    # 保存结果
    output_path = OUTPUT_DIR / "inmo_air3_specs.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(specs, f, ensure_ascii=False, indent=2)
    print(f"\n[保存] {output_path}")

    return specs

def extract_official_specs(driver, page_source):
    """从官网提取规格"""
    data = {}

    # 查找规格表格或列表
    spec_selectors = [
        ".spec-list li", ".specs li", ".product-specs li",
        ".parameters li", ".params li", "table.specs td",
        ".spec-item", ".param-item", "dl.specs dt, dl.specs dd"
    ]

    for selector in spec_selectors:
        items = extract_all_texts(driver, selector)
        if items:
            for item in items:
                # 解析键值对
                if ':' in item or '：' in item:
                    parts = re.split(r'[:：]', item, 1)
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = parts[1].strip()
                        data[key] = value

    # 查找价格
    price_selectors = [".price", ".product-price", "[class*='price']"]
    for sel in price_selectors:
        price = extract_text_safe(driver, sel)
        if price and re.search(r'\d', price):
            data["price"] = price
            break

    # 查找标题/产品名
    title = driver.title
    if title:
        data["page_title"] = title

    return data

def extract_ecommerce_specs(driver, page_source):
    """从电商页面提取规格"""
    data = {}

    # 京东规格表
    if "jd.com" in driver.current_url:
        # 规格参数
        spec_items = extract_all_texts(driver, ".Ptable-item")
        for item in spec_items:
            if ':' in item or '：' in item:
                parts = re.split(r'[:：]', item, 1)
                if len(parts) == 2:
                    data[parts[0].strip()] = parts[1].strip()

        # 标题
        title = extract_text_safe(driver, ".sku-name")
        if title:
            data["product_title"] = title

        # 价格
        price = extract_text_safe(driver, ".p-price .price")
        if price:
            data["price"] = price

    # 天猫
    elif "tmall.com" in driver.current_url:
        # 规格参数
        spec_items = extract_all_texts(driver, ".tm-clear")
        for item in spec_items:
            if ':' in item or '：' in item:
                parts = re.split(r'[:：]', item, 1)
                if len(parts) == 2:
                    data[parts[0].strip()] = parts[1].strip()

        # 标题
        title = extract_text_safe(driver, ".tb-detail-hd h1")
        if title:
            data["product_title"] = title

    # Amazon
    elif "amazon.com" in driver.current_url:
        # 产品特性
        features = extract_all_texts(driver, "#feature-bullets li")
        if features:
            data["features"] = features

        # 规格表
        spec_rows = driver.find_elements(By.CSS_SELECTOR, "#productDetails_techSpec_section_1 tr")
        for row in spec_rows:
            try:
                th = row.find_element(By.TAG_NAME, "th").text.strip()
                td = row.find_element(By.TAG_NAME, "td").text.strip()
                data[th] = td
            except:
                pass

    return data

def collect_meta_rayban_specs():
    """采集Meta Ray-Ban Display规格数据"""
    print("\n" + "=" * 60)
    print("采集 Meta Ray-Ban Display 规格")
    print("=" * 60)

    specs = {
        "product": "Meta Ray-Ban Display",
        "timestamp": datetime.now().isoformat(),
        "sources_tried": [],
        "data": {}
    }

    driver = None

    sources = [
        {
            "name": "Ray-Ban官网",
            "url": "https://www.ray-ban.com/usa/l/discover-meta-ray-ban-display",
            "type": "official"
        },
        {
            "name": "Meta官网",
            "url": "https://www.meta.com/smart-glasses/",
            "type": "official"
        },
        {
            "name": "Amazon",
            "url": "https://www.amazon.com/s?k=Meta+Ray-Ban+smart+glasses",
            "type": "ecommerce"
        }
    ]

    try:
        driver = create_driver(headless=True)

        for source in sources:
            print(f"\n[尝试] {source['name']}: {source['url']}")
            specs["sources_tried"].append(source["name"])

            try:
                driver.get(source["url"])
                time.sleep(4)

                page_source = driver.page_source

                if len(page_source) < 5000:
                    print(f"  [失败] 页面内容过少")
                    continue

                data = {}

                if "ray-ban.com" in driver.current_url:
                    # Ray-Ban官网
                    data = extract_rayban_official(driver, page_source)
                elif "meta.com" in driver.current_url:
                    data = extract_meta_official(driver, page_source)
                else:
                    data = extract_ecommerce_specs(driver, page_source)

                if data:
                    specs["data"].update(data)
                    specs["primary_source"] = source["name"]
                    print(f"  [成功] 获取 {len(data)} 项数据")

                    screenshot_path = OUTPUT_DIR / f"meta_rayban_{source['name'].replace(' ', '_')}.png"
                    driver.save_screenshot(str(screenshot_path))
                    print(f"  [截图] {screenshot_path}")
                    break
                else:
                    print(f"  [失败] 未提取到有效数据")

            except Exception as e:
                print(f"  [错误] {str(e)[:100]}")
                continue

    except Exception as e:
        print(f"[全局错误] {e}")
        specs["error"] = str(e)
    finally:
        if driver:
            driver.quit()

    output_path = OUTPUT_DIR / "meta_rayban_specs.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(specs, f, ensure_ascii=False, indent=2)
    print(f"\n[保存] {output_path}")

    return specs

def extract_rayban_official(driver, page_source):
    """从Ray-Ban官网提取规格"""
    data = {}

    # 查找规格信息
    spec_text_selectors = [
        ".product-specs", ".specs-list", ".tech-specs",
        "[class*='spec']", "[class*='detail']"
    ]

    for selector in spec_text_selectors:
        texts = extract_all_texts(driver, selector)
        for text in texts:
            if ':' in text or '：' in text:
                parts = re.split(r'[:：]', text, 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    if len(key) < 50 and len(value) < 200:
                        data[key] = value

    # 价格
    price = extract_text_safe(driver, "[class*='price']")
    if price:
        data["price"] = price

    # 标题
    data["page_title"] = driver.title

    # 关键规格搜索
    page_lower = page_source.lower()

    # 处理器
    processor_patterns = ["snapdragon", "ar1", "processor", "chip"]
    for pattern in processor_patterns:
        if pattern in page_lower:
            # 尝试提取完整型号
            match = re.search(r'(Snapdragon\s*AR1[^\s<]*)', page_source, re.IGNORECASE)
            if match:
                data["processor"] = match.group(1)
            break

    # 显示
    display_patterns = ["display", "micro-led", "oled"]
    for pattern in display_patterns:
        if pattern in page_lower:
            data["display_type"] = "Micro-LED" if "micro-led" in page_lower else "Display equipped"
            break

    return data

def extract_meta_official(driver, page_source):
    """从Meta官网提取规格"""
    data = {}

    # 产品特性
    features = extract_all_texts(driver, "[class*='feature']")
    if features:
        data["features"] = features[:10]

    # 规格数据
    specs = extract_all_texts(driver, "[class*='spec']")
    for spec in specs:
        if ':' in spec:
            parts = spec.split(':', 1)
            if len(parts) == 2:
                data[parts[0].strip()] = parts[1].strip()

    data["page_title"] = driver.title

    return data

def main():
    """执行全量规格采集"""
    print("=" * 60)
    print("竞品规格数据采集器 v1.0")
    print(f"开始时间: {datetime.now().isoformat()}")
    print("=" * 60)

    results = {
        "collection_time": datetime.now().isoformat(),
        "products": []
    }

    # 采集INMO Air3
    inmo_specs = collect_inmo_air3_specs()
    results["products"].append(inmo_specs)

    # 采集Meta Ray-Ban
    meta_specs = collect_meta_rayban_specs()
    results["products"].append(meta_specs)

    # 保存汇总结果
    summary_path = OUTPUT_DIR / "specs_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("采集完成汇总")
    print("=" * 60)
    for product in results["products"]:
        print(f"\n{product['product']}:")
        print(f"  数据来源: {product.get('primary_source', '未获取')}")
        print(f"  数据项数: {len(product.get('data', {}))}")
        if product.get('data'):
            for key, value in list(product['data'].items())[:5]:
                print(f"    {key}: {value[:50] if isinstance(value, str) else value}")

    print(f"\n汇总保存到: {summary_path}")

    return results

if __name__ == "__main__":
    main()