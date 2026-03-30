"""
@description: INMO Air系列数据采集脚本 - 严格带出处
@dependencies: requests, bs4, src.collectors.sourced_data_collector
@last_modified: 2026-03-16
"""

import re
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional, Dict, Any, List

# 添加路径
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 直接导入本地模块
sys.path.insert(0, str(PROJECT_ROOT / "src" / "collectors"))
from sourced_data_collector import (
    SourcedDataCollector, DataSourceType, SourcedReport
)


class INMODataCollector(SourcedDataCollector):
    """INMO影目数据采集器"""

    # 已知数据源URL
    SOURCES = {
        "inmo_official": "https://www.inmo.com",
        "inmo_air2_jd": "https://item.jd.com/100070432376.html",
        "inmo_air_jd": "https://item.jd.com/100043683044.html",
        "inmo_tmall": "https://inmo.tmall.com",
        "zhihu_review": "https://www.zhihu.com/search?q=影目Air",
    }

    def __init__(self):
        super().__init__()
        self.collected_data = {}

    def collect_from_jd(self, product_id: str, product_name: str) -> Dict[str, Any]:
        """从京东采集数据"""
        url = f"https://item.jd.com/{product_id}.html"
        print(f"[JD] 正在采集: {url}")

        result = {
            "success": False,
            "data": {},
            "source_url": url,
            "source_name": f"京东-{product_name}"
        }

        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code != 200:
                self.blocked_reasons.append(f"京东页面 {url} 返回 {resp.status_code}")
                return result

            html = resp.text
            soup = BeautifulSoup(html, 'html.parser')

            # 1. 提取商品标题
            title_elem = soup.select_one(".sku-name")
            if title_elem:
                result["data"]["product_title"] = title_elem.get_text(strip=True)

            # 2. 提取价格（需要特殊处理，京东价格是动态加载的）
            price_elem = soup.select_one(".p-price .price")
            if price_elem:
                result["data"]["price"] = price_elem.get_text(strip=True)

            # 3. 提取商品参数
            params = {}
            param_items = soup.select(".Ptable-item")
            for item in param_items:
                label = item.select_one("dt")
                value = item.select_one("dd")
                if label and value:
                    params[label.get_text(strip=True)] = value.get_text(strip=True)

            if params:
                result["data"]["specs"] = params

            # 4. 提取评价摘要
            comment_summary = soup.select_one(".comment-count a")
            if comment_summary:
                result["data"]["comment_count"] = comment_summary.get_text(strip=True)

            # 5. 尝试从页面脚本中提取更多数据
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and 'product' in script.string:
                    # 尝试提取JSON数据
                    match = re.search(r'product:\s*(\{[^}]+\})', script.string)
                    if match:
                        try:
                            product_json = json.loads(match.group(1))
                            result["data"].update(product_json)
                        except:
                            pass

            result["success"] = True
            print(f"[JD] 成功采集 {len(result['data'])} 个数据点")

        except Exception as e:
            self.blocked_reasons.append(f"京东采集异常: {str(e)}")

        return result

    def collect_from_official(self) -> Dict[str, Any]:
        """从官网采集数据"""
        print(f"[OFFICIAL] 正在采集: {self.SOURCES['inmo_official']}")

        result = {
            "success": False,
            "data": {},
            "source_url": self.SOURCES['inmo_official'],
            "source_name": "INMO官网"
        }

        try:
            resp = self.session.get(self.SOURCES['inmo_official'], timeout=30)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')

                # 提取产品列表
                products = []
                product_elems = soup.select(".product-item, .product-card")
                for elem in product_elems:
                    name = elem.select_one("h3, .product-name")
                    link = elem.select_one("a")
                    if name:
                        products.append({
                            "name": name.get_text(strip=True),
                            "url": link['href'] if link and link.has_attr('href') else ""
                        })

                if products:
                    result["data"]["products"] = products
                    result["success"] = True
                    print(f"[OFFICIAL] 找到 {len(products)} 个产品")

        except Exception as e:
            self.blocked_reasons.append(f"官网采集异常: {str(e)}")

        return result

    def collect_specs_from_detail(self, product_id: str) -> Dict[str, Any]:
        """从商品详情页采集规格参数"""
        url = f"https://item.jd.com/{product_id}.html"

        result = {
            "success": False,
            "specs": {},
            "source_url": url,
            "source_name": "京东商品详情"
        }

        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code != 200:
                return result

            soup = BeautifulSoup(resp.text, 'html.parser')

            # 提取规格参数表
            specs = {}

            # 方式1：标准参数表
            for li in soup.select(".detail-list li"):
                label = li.select_one(".label")
                value = li.select_one(".value")
                if label and value:
                    specs[label.get_text(strip=True).replace("：", "")] = value.get_text(strip=True)

            # 方式2：Ptable
            for tr in soup.select(".Ptable tr"):
                tds = tr.select("td")
                if len(tds) >= 2:
                    key = tds[0].get_text(strip=True)
                    val = tds[1].get_text(strip=True)
                    if key and val:
                        specs[key] = val

            result["specs"] = specs
            result["success"] = len(specs) > 0

        except Exception as e:
            self.blocked_reasons.append(f"规格采集异常: {str(e)}")

        return result

    def run_full_collection(self) -> SourcedReport:
        """执行完整采集"""
        print("=" * 60)
        print("[INMO 数据采集器] 开始采集...")
        print("=" * 60)

        # 1. 采集京东数据 - INMO Air2
        jd_result = self.collect_from_jd("100070432376", "INMO Air2")
        if jd_result["success"]:
            self.add_data_point(
                dimension="INMO Air2 京东数据",
                value=jd_result["data"],
                source_type=DataSourceType.ECOMMERCE,
                source_url=jd_result["source_url"],
                source_name=jd_result["source_name"],
                confidence="high",
                raw_text=str(jd_result["data"])[:200]
            )

        # 2. 采集规格参数
        specs_result = self.collect_specs_from_detail("100070432376")
        if specs_result["success"]:
            self.add_data_point(
                dimension="INMO Air2 规格参数",
                value=specs_result["specs"],
                source_type=DataSourceType.ECOMMERCE,
                source_url=specs_result["source_url"],
                source_name=specs_result["source_name"],
                confidence="high",
                raw_text=str(specs_result["specs"])[:200]
            )

        # 3. 标记无法自动采集的维度
        auto_unavailable = [
            "用户评价详情（需登录后查看评论区）",
            "销售增长数据（需商家后台）",
            "主要供应商（非公开信息）",
            "屏幕UI/UX截图（需截图工具）",
            "APP界面截图（需安装APP）",
            "盲操交互截图（需演示）"
        ]

        for dim in auto_unavailable:
            self.mark_missing(dim, "自动采集受限")

        # 生成报告
        report = self.generate_report("影目(INMO) Air系列 AR眼镜")

        print("\n" + "=" * 60)
        print(f"[完成] 采集数据点: {len(self.data_points)}")
        print(f"[完成] 缺失维度: {len(self.missing_dimensions)}")
        print(f"[完成] 阻断原因: {len(self.blocked_reasons)}")
        print("=" * 60)

        return report


# === 执行采集 ===
if __name__ == "__main__":
    collector = INMODataCollector()
    report = collector.run_full_collection()

    # 保存报告
    output_path = Path(".ai-state/competitive_analysis/inmo_sourced_report.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report.to_markdown())

    print(f"\n报告已保存: {output_path}")

    # 打印数据来源摘要
    print("\n[数据来源摘要]")
    for dp in collector.data_points:
        print(f"  - {dp.dimension}: [{dp.source_name}]({dp.source_url})")

    # 打印缺失维度
    if collector.missing_dimensions:
        print("\n[缺失维度 - 需人工采集]")
        for dim in collector.missing_dimensions:
            print(f"  - {dim}")