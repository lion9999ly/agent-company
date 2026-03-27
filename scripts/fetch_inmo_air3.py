"""
@description: 采集INMO Air3产品详细规格
@dependencies: requests
@last_modified: 2026-03-16
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
from pathlib import Path

def fetch_inmo_air3_specs():
    """采集INMO Air3详细规格"""

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8',
    }

    session = requests.Session()
    session.headers.update(headers)

    output_dir = Path(".ai-state/competitive_analysis")
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "timestamp": datetime.now().isoformat(),
        "products": []
    }

    # INMO Air3产品页面
    product_urls = [
        ("INMO Air3", "https://www.inmoxr.com/products/inmo-air3-ar-glasses-all-in-one-full-color-waveguide"),
        ("INMO Air3 Collection", "https://www.inmoxr.com/collections/air"),
        ("INMO Go", "https://www.inmoxr.com/collections/go"),
    ]

    for name, url in product_urls:
        print(f"[采集] {name}: {url}")
        try:
            resp = session.get(url, timeout=30)
            print(f"  状态: {resp.status_code}, 长度: {len(resp.text)}")

            if resp.status_code == 200 and len(resp.text) > 1000:
                # 保存HTML
                safe_name = name.lower().replace(" ", "_")
                html_path = output_dir / f"raw_inmo_{safe_name}.html"
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(resp.text)
                print(f"  保存: {html_path}")

                # 解析内容
                soup = BeautifulSoup(resp.text, 'html.parser')

                # 提取标题
                title = soup.find('h1') or soup.find('title')
                title_text = title.get_text(strip=True) if title else "无标题"

                # 提取价格
                price_elems = soup.find_all(['span', 'div'], class_=re.compile(r'price|money', re.I))
                prices = [p.get_text(strip=True) for p in price_elems if p.get_text(strip=True)]

                # 提取规格参数 - 查找表格或列表
                specs = {}
                # 方式1: 查找description或features区域
                for elem in soup.find_all(['div', 'section'], class_=re.compile(r'spec|feature|detail|description', re.I)):
                    text = elem.get_text(strip=True)
                    if len(text) > 50:
                        specs[f"section_{len(specs)}"] = text[:500]

                # 方式2: 查找表格
                for table in soup.find_all('table'):
                    for tr in table.find_all('tr'):
                        tds = tr.find_all(['td', 'th'])
                        if len(tds) >= 2:
                            key = tds[0].get_text(strip=True)
                            value = tds[1].get_text(strip=True)
                            if key and value:
                                specs[key] = value

                # 方式3: 查找列表
                for ul in soup.find_all(['ul', 'ol'], class_=re.compile(r'spec|feature|detail', re.I)):
                    items = [li.get_text(strip=True) for li in ul.find_all('li')]
                    specs["list_items"] = items

                # 方式4: 提取所有包含关键词的文本
                keywords = ['weight', 'battery', 'display', 'FOV', 'nits', 'resolution', 'gram', 'hour', 'mAh', 'inch', 'mm']
                keyword_content = {}
                for kw in keywords:
                    pattern = re.compile(rf'.{{0,50}}{kw}.{{0,50}}', re.I)
                    matches = pattern.findall(resp.text)
                    if matches:
                        keyword_content[kw] = matches[:5]

                results["products"].append({
                    "name": name,
                    "url": url,
                    "status": resp.status_code,
                    "title": title_text,
                    "prices": prices[:5] if prices else [],
                    "specs": specs,
                    "keyword_matches": keyword_content
                })

        except Exception as e:
            print(f"  错误: {e}")
            results["products"].append({
                "name": name,
                "url": url,
                "error": str(e)
            })

    # 保存结果
    with open(output_dir / "inmo_air3_specs.json", 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n[完成] 结果保存到 {output_dir / 'inmo_air3_specs.json'}")
    return results

if __name__ == "__main__":
    fetch_inmo_air3_specs()