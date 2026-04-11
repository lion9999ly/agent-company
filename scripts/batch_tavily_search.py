"""
批量 Tavily 搜索脚本
"""
import requests
import os
import json
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

TAVILY_API_KEY = os.environ['TAVILY_API_KEY']

SEARCH_TASKS = [
    {"id": 1, "query": "SeeYA SY049 OLED microdisplay specifications FOV brightness resolution 2024 2025", "focus": "SeeYA OLED微显示器规格"},
    {"id": 2, "query": "视涯科技 0.49寸 OLED 微显示器 SY049 参数 亮度 分辨率 功耗", "focus": "SeeYA中文规格"},
    {"id": 3, "query": "JBD Hummingbird MicroLED microdisplay 0.13 inch specifications brightness nits power consumption 2024", "focus": "JBD MicroLED规格"},
    {"id": 4, "query": "JBD 上海显耀 MicroLED 640x480 VGA 单色 微显示 面板亮度 功耗 寿命", "focus": "JBD中文规格"},
    {"id": 5, "query": "freeform prism AR HUD optical specifications FOV eyebox brightness helmet motorcycle 2024", "focus": "Freeform棱镜HUD参数"},
    {"id": 6, "query": "freeform combiner film motorcycle helmet HUD optical reflection efficiency brightness", "focus": "Freeform反射膜方案"},
    {"id": 7, "query": "resin diffractive waveguide full color AR display FOV brightness transparency eyebox 2024 2025", "focus": "树脂衍射光波导全彩"},
    {"id": 8, "query": "树脂衍射光波导 单色 绿光 MicroLED FOV 亮度 透过率 眼盒", "focus": "树脂波导单色绿光"},
    {"id": 9, "query": "珑璟光电 Lochn resin waveguide SRG specifications FOV brightness transparency 30 40 50 degree", "focus": "珑璟光电参数"},
    {"id": 10, "query": "Goolton 古镜科技 nano imprint high refractive index resin waveguide 1.8 FOV", "focus": "古镜高折射率树脂"},
    {"id": 11, "query": "EyeLights EyeRide HUD motorcycle helmet specifications FOV brightness eyebox combiner", "focus": "EyeLights实测参数"},
    {"id": 12, "query": "Shoei GT-Air 3 Smart HUD optical display specifications brightness FOV", "focus": "Shoei HUD参数"},
]

def tavily_search(query, max_results=5):
    """执行 Tavily 搜索"""
    try:
        resp = requests.post(
            'https://api.tavily.com/search',
            json={
                'api_key': TAVILY_API_KEY,
                'query': query,
                'max_results': max_results,
                'search_depth': 'advanced'
            },
            timeout=30
        )
        if resp.status_code == 200:
            return resp.json()
        else:
            return {'error': f'HTTP {resp.status_code}', 'results': []}
    except Exception as e:
        return {'error': str(e), 'results': []}

def fetch_url(url, timeout=15):
    """抓取网页内容"""
    try:
        resp = requests.get(url, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code == 200:
            # 提取关键内容（简单处理）
            text = resp.text
            # 清理 HTML 标签
            import re
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text)
            return text[:3000]  # 截取前3000字符
        return f'HTTP {resp.status_code}'
    except Exception as e:
        return f'Error: {str(e)}'

def main():
    results = []

    for task in SEARCH_TASKS:
        print(f"搜索 #{task['id']}: {task['query']}")

        search_result = tavily_search(task['query'])

        task_data = {
            'id': task['id'],
            'focus': task['focus'],
            'query': task['query'],
            'timestamp': datetime.now().isoformat(),
            'results': []
        }

        if 'error' in search_result and search_result.get('results') == []:
            task_data['error'] = search_result['error']
        else:
            for r in search_result.get('results', [])[:3]:  # 只取前3个结果
                url = r.get('url', '')
                title = r.get('title', '')
                content = r.get('content', '')

                # 尝试抓取详情
                detail = fetch_url(url) if url else ''

                task_data['results'].append({
                    'title': title,
                    'url': url,
                    'snippet': content[:500],
                    'detail': detail[:1000]  # 截取详情前1000字符
                })

        results.append(task_data)
        print(f"  完成: {len(task_data['results'])} 个结果")

    # 保存结果
    output_path = '.ai-state/research_raw_data.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_path}")

    # 生成 Markdown 报告
    md_content = generate_markdown(results)
    md_path = '.ai-state/research_raw.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"Markdown 报告已保存到: {md_path}")

def generate_markdown(results):
    """生成 Markdown 格式报告"""
    md = """# Deep Research 原始数据收集

> 收集时间: 2026-04-11
> 工具链: Tavily API + requests
> 搜索任务: 12 个

---

"""

    for task in results:
        md += f"\n## 搜索 #{task['id']}: {task['focus']}\n\n"
        md += f"**查询**: `{task['query']}`\n\n"
        md += f"**时间**: {task['timestamp']}\n\n"

        if 'error' in task:
            md += f"**错误**: {task['error']}\n\n"

        for i, r in enumerate(task['results'], 1):
            md += f"### 结果 {i}\n\n"
            md += f"**标题**: {r['title']}\n\n"
            md += f"**URL**: [{r['url']}]({r['url']})\n\n"
            md += f"**摘要**: {r['snippet']}\n\n"
            if r['detail']:
                md += f"**详情**:\n```\n{r['detail'][:500]}...\n```\n\n"

        md += "---\n\n"

    return md

if __name__ == '__main__':
    main()