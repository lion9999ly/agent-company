"""
@description: 直接访问INMO官网采集数据
@dependencies: requests
@last_modified: 2026-03-16
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
from pathlib import Path

def fetch_inmo_official():
    """访问INMO官网"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }

    session = requests.Session()
    session.headers.update(headers)

    results = {
        "timestamp": datetime.now().isoformat(),
        "sources": []
    }

    # 1. 访问官网首页
    print("[1] 访问INMO官网首页...")
    try:
        resp = session.get("https://www.inmo.com", timeout=30)
        print(f"    状态码: {resp.status_code}")
        print(f"    内容长度: {len(resp.text)}")

        if resp.status_code == 200:
            # 保存原始HTML
            output_dir = Path(".ai-state/competitive_analysis")
            output_dir.mkdir(parents=True, exist_ok=True)

            with open(output_dir / "raw_inmo_official.html", 'w', encoding='utf-8') as f:
                f.write(resp.text)

            # 解析内容
            soup = BeautifulSoup(resp.text, 'html.parser')

            # 提取标题
            title = soup.find('title')
            if title:
                print(f"    页面标题: {title.get_text(strip=True)}")

            # 提取产品信息
            products = []
            # 查找产品相关元素
            product_elems = soup.find_all(['div', 'section', 'article'], class_=re.compile(r'product|item|card', re.I))
            for elem in product_elems[:10]:
                text = elem.get_text(strip=True)[:200]
                if text:
                    products.append(text)

            results["sources"].append({
                "name": "INMO官网首页",
                "url": "https://www.inmo.com",
                "status": 200,
                "products_found": len(products),
                "sample_text": products[:3] if products else []
            })

            # 提取所有链接
            links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.get_text(strip=True)
                if href and text:
                    links.append({"href": href, "text": text[:50]})

            results["sources"][0]["links"] = links[:20]

    except Exception as e:
        print(f"    错误: {e}")
        results["sources"].append({
            "name": "INMO官网首页",
            "url": "https://www.inmo.com",
            "error": str(e)
        })

    # 2. 尝试访问产品页面
    print("\n[2] 尝试访问INMO Air产品页...")
    product_urls = [
        "https://www.inmo.com/product/air",
        "https://www.inmo.com/product/air2",
        "https://www.inmo.com/product/air3",
        "https://www.inmo.com/air",
        "https://www.inmo.com/air2",
    ]

    for url in product_urls:
        try:
            resp = session.get(url, timeout=30)
            print(f"    {url}: {resp.status_code} ({len(resp.text)} bytes)")
            if resp.status_code == 200 and len(resp.text) > 1000:
                # 保存
                safe_name = url.replace("https://www.inmo.com/", "").replace("/", "_")
                with open(output_dir / f"raw_inmo_{safe_name}.html", 'w', encoding='utf-8') as f:
                    f.write(resp.text)
                results["sources"].append({
                    "name": f"INMO产品页-{safe_name}",
                    "url": url,
                    "status": 200,
                    "content_length": len(resp.text)
                })
                break
        except Exception as e:
            print(f"    {url}: 错误 - {e}")

    # 3. 尝试API接口
    print("\n[3] 尝试API接口...")
    api_urls = [
        "https://www.inmo.com/api/products",
        "https://www.inmo.com/api/v1/products",
        "https://api.inmo.com/products",
    ]

    for url in api_urls:
        try:
            resp = session.get(url, timeout=10)
            print(f"    {url}: {resp.status_code}")
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    results["sources"].append({
                        "name": f"API-{url}",
                        "url": url,
                        "status": 200,
                        "data": data
                    })
                except:
                    pass
        except Exception as e:
            print(f"    {url}: {e}")

    # 保存结果
    with open(output_dir / "inmo_official_results.json", 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n[完成] 结果已保存到 {output_dir}")
    return results

if __name__ == "__main__":
    fetch_inmo_official()