"""
@description: 尝试多个可能的INMO官网域名
@dependencies: requests
@last_modified: 2026-03-16
"""

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
from pathlib import Path

def try_inmo_domains():
    """尝试访问可能的INMO域名"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    }

    session = requests.Session()
    session.headers.update(headers)

    # 可能的INMO AR眼镜域名
    domains = [
        "https://inmo.cn",
        "https://www.inmo.cn",
        "https://inmo.com.cn",
        "https://www.inmo.com.cn",
        "https://inmoar.com",
        "https://www.inmoar.com",
        "https://inmoglass.com",
        "https://www.inmoglass.com",
        "https://myinmo.com",
        "https://www.myinmo.com",
        # 京东商品页
        "https://item.jd.com/100070432376.html",
        "https://item.jd.com/100043683044.html",
        # 天猫
        "https://inmo.tmall.com",
        # 百度搜索
        "https://www.baidu.com/s?wd=影目Air3",
    ]

    results = {"timestamp": datetime.now().isoformat(), "domains": []}
    output_dir = Path(".ai-state/competitive_analysis")
    output_dir.mkdir(parents=True, exist_ok=True)

    for url in domains:
        print(f"尝试: {url}")
        try:
            resp = session.get(url, timeout=15, allow_redirects=True)
            print(f"  状态: {resp.status_code}, 长度: {len(resp.text)}, 最终URL: {resp.url}")

            if resp.status_code == 200 and len(resp.text) > 500:
                # 保存HTML
                safe_name = url.replace("https://", "").replace("http://", "").replace("/", "_")[:50]
                html_path = output_dir / f"raw_{safe_name}.html"

                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(resp.text)

                # 解析
                soup = BeautifulSoup(resp.text, 'html.parser')
                title = soup.find('title')
                title_text = title.get_text(strip=True) if title else "无标题"

                # 提取可能的AR眼镜相关内容
                ar_keywords = ['AR', '眼镜', 'Air', '智能', '影目', 'INMO', '显示', '续航', '重量']
                content_preview = soup.get_text()[:2000]
                found_keywords = [kw for kw in ar_keywords if kw in content_preview]

                results["domains"].append({
                    "url": url,
                    "final_url": resp.url,
                    "status": resp.status_code,
                    "content_length": len(resp.text),
                    "title": title_text,
                    "found_keywords": found_keywords,
                    "saved_to": str(html_path)
                })

                print(f"  标题: {title_text}")
                print(f"  关键词: {found_keywords}")

        except Exception as e:
            print(f"  错误: {e}")
            results["domains"].append({
                "url": url,
                "error": str(e)
            })

    # 保存结果
    with open(output_dir / "domain_search_results.json", 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到 {output_dir / 'domain_search_results.json'}")
    return results

if __name__ == "__main__":
    try_inmo_domains()