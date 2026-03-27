"""
@description: 采集竞品数据（Xreal, Rokid, 雷鸟）
@dependencies: requests, beautifulsoup4
@last_modified: 2026-03-16
"""

import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
from pathlib import Path

def fetch_competitor_specs():
    """采集竞品规格数据"""

    output_dir = Path(".ai-state/competitive_analysis")
    output_dir.mkdir(parents=True, exist_ok=True)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }

    session = requests.Session()
    session.headers.update(headers)

    results = {
        "timestamp": datetime.now().isoformat(),
        "competitors": []
    }

    # ========== Xreal Air 2 ==========
    print("\n[1] 采集 Xreal Air 2...")
    xreal_data = {"name": "Xreal Air 2", "source": "", "specs": {}}

    urls_to_try = [
        ("Xreal Air 2 官网", "https://www.xreal.com/air2/"),
        ("Xreal Air 2 Ultra", "https://www.xreal.com/air2-ultra/"),
    ]

    for name, url in urls_to_try:
        try:
            r = session.get(url, timeout=20)
            print(f"  {name}: status={r.status_code}, length={len(r.text)}")

            if r.status_code == 200 and len(r.text) > 5000:
                xreal_data["source"] = url

                # 保存HTML
                with open(output_dir / "xreal_air2.html", 'w', encoding='utf-8') as f:
                    f.write(r.text)

                soup = BeautifulSoup(r.text, 'html.parser')
                text = soup.get_text()

                # 提取规格
                patterns = {
                    'weight': r'(\d+\.?\d*)\s*g(?:rams)?',
                    'FOV': r'(\d+°)\s*(?:FOV|Field\s*of\s*View)',
                    'brightness': r'(\d+,?\d*)\s*nits',
                    'resolution': r'(\d+\s*x\s*\d+)',
                    'refresh_rate': r'(\d+)\s*Hz',
                    'price': r'\$([\d,]+)',
                }

                for key, pattern in patterns.items():
                    match = re.search(pattern, text, re.I)
                    if match:
                        xreal_data["specs"][key] = match.group(0)

                # 提取表格数据
                for table in soup.find_all('table'):
                    for tr in table.find_all('tr'):
                        tds = tr.find_all(['td', 'th'])
                        if len(tds) >= 2:
                            key = tds[0].get_text(strip=True)
                            val = tds[1].get_text(strip=True)
                            if key and val and len(key) < 40 and len(val) < 100:
                                xreal_data["specs"][key] = val

                # 提取列表项
                for ul in soup.find_all(['ul', 'ol']):
                    items = [li.get_text(strip=True) for li in ul.find_all('li') if li.get_text(strip=True)]
                    for item in items:
                        if any(kw in item.lower() for kw in ['weight', 'fov', 'nits', 'resolution', 'battery', 'gram']):
                            if 'list_items' not in xreal_data["specs"]:
                                xreal_data["specs"]["list_items"] = []
                            xreal_data["specs"]["list_items"].append(item[:100])

                print(f"  提取规格: {len(xreal_data['specs'])}项")
                break

        except Exception as e:
            print(f"  错误: {e}")

    results["competitors"].append(xreal_data)

    # ========== Rokid Max ==========
    print("\n[2] 采集 Rokid Max...")
    rokid_data = {"name": "Rokid Max", "source": "", "specs": {}}

    urls_to_try = [
        ("Rokid官网", "https://global.rokid.com/"),
        ("Rokid Max产品页", "https://global.rokid.com/products/max/"),
    ]

    for name, url in urls_to_try:
        try:
            r = session.get(url, timeout=20)
            print(f"  {name}: status={r.status_code}, length={len(r.text)}")

            if r.status_code == 200 and len(r.text) > 5000:
                rokid_data["source"] = url

                with open(output_dir / "rokid.html", 'w', encoding='utf-8') as f:
                    f.write(r.text)

                soup = BeautifulSoup(r.text, 'html.parser')
                text = soup.get_text()

                # 提取规格
                patterns = {
                    'weight': r'(\d+\.?\d*)\s*g(?:rams)?',
                    'FOV': r'(\d+°)',
                    'brightness': r'(\d+,?\d*)\s*nits',
                    'resolution': r'(\d+\s*x\s*\d+)',
                    'refresh_rate': r'(\d+)\s*Hz',
                    'price': r'\$([\d,]+)',
                }

                for key, pattern in patterns.items():
                    match = re.search(pattern, text, re.I)
                    if match:
                        rokid_data["specs"][key] = match.group(0)

                print(f"  提取规格: {len(rokid_data['specs'])}项")
                break

        except Exception as e:
            print(f"  错误: {e}")

    results["competitors"].append(rokid_data)

    # ========== 雷鸟 Air 2 ==========
    print("\n[3] 采集 雷鸟 Air 2...")
    thunderbird_data = {"name": "雷鸟 Air 2 (TCL Thunderbird)", "source": "", "specs": {}}

    urls_to_try = [
        ("雷鸟官网", "https://www.tcl.com/global/en/products/glasses"),
        ("雷鸟Air 2", "https://www.tcl.com/global/en/products/thunderbird-air-2"),
    ]

    for name, url in urls_to_try:
        try:
            r = session.get(url, timeout=20)
            print(f"  {name}: status={r.status_code}, length={len(r.text)}")

            if r.status_code == 200 and len(r.text) > 5000:
                thunderbird_data["source"] = url

                soup = BeautifulSoup(r.text, 'html.parser')
                text = soup.get_text()

                patterns = {
                    'weight': r'(\d+\.?\d*)\s*g',
                    'FOV': r'(\d+°)',
                    'brightness': r'(\d+,?\d*)\s*nits',
                    'resolution': r'(\d+\s*x\s*\d+)',
                }

                for key, pattern in patterns.items():
                    match = re.search(pattern, text, re.I)
                    if match:
                        thunderbird_data["specs"][key] = match.group(0)

                print(f"  提取规格: {len(thunderbird_data['specs'])}项")
                break

        except Exception as e:
            print(f"  错误: {e}")

    results["competitors"].append(thunderbird_data)

    # ========== 保存结果 ==========
    with open(output_dir / "competitor_specs.json", 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n[完成] 结果保存到 {output_dir / 'competitor_specs.json'}")

    # 打印摘要
    print("\n=== 采集摘要 ===")
    for comp in results["competitors"]:
        print(f"\n{comp['name']}:")
        print(f"  来源: {comp['source'] or '未获取'}")
        for k, v in comp["specs"].items():
            print(f"  {k}: {v}")

    return results

if __name__ == "__main__":
    fetch_competitor_specs()