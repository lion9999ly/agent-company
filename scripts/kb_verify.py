"""验证知识条目质量"""
import json
from pathlib import Path
from datetime import datetime

KB_ROOT = Path(".ai-state/knowledge")
today = datetime.now().strftime("%Y%m%d")

# 找今天最新的 competitors 条目
latest = None
competitors_dir = KB_ROOT / "competitors"
if competitors_dir.exists():
    for f in sorted(competitors_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if today in f.name:
            latest = f
            break

if latest:
    data = json.loads(latest.read_text(encoding="utf-8"))
    content = data.get('content', '')

    with open('_kb_verify_output.txt', 'w', encoding='utf-8') as out:
        out.write(f"文件: {latest.name}\n")
        out.write(f"标题: {data.get('title', '')}\n")
        out.write(f"Domain: {data.get('domain', '')}\n")
        out.write(f"Tags: {data.get('tags', [])}\n")
        out.write(f"Source: {data.get('source', '')}\n")
        out.write(f"内容长度: {len(content)} 字\n")
        out.write(f"\n--- 内容前 800 字 ---\n")
        out.write(content[:800])
        out.write(f"\n\n--- 内容后 300 字 ---\n")
        out.write(content[-300:])

        # 检查关键数据点
        checks = {
            'VR销量497万台': '497' in content,
            'AR销量110万台': '110' in content,
            'Meta Quest': 'Meta' in content or 'Quest' in content,
            'Wellsenn XR': 'wellsenn' in content.lower() or 'XR' in content,
            '图片内容': '图片' in content or '图表' in content or '产品形态' in content,
        }
        out.write(f"\n\n--- 关键数据保留检查 ---\n")
        for k, v in checks.items():
            status = 'PASS' if v else 'FAIL'
            out.write(f"  [{status}] {k}\n")

    print("结果已写入 _kb_verify_output.txt")
    # 打印关键信息
    print(f"标题: {data.get('title', '')[:60]}")
    print(f"内容长度: {len(content)} 字")
    print(f"关键数据检查:")
    checks = {
        'VR销量497万台': '497' in content,
        'AR销量110万台': '110' in content,
        'Meta Quest': 'Meta' in content or 'Quest' in content,
        'Wellsenn XR': 'wellsenn' in content.lower() or 'XR' in content,
        '图片内容': '图片' in content or '图表' in content or '产品形态' in content,
    }
    for k, v in checks.items():
        status = 'PASS' if v else 'FAIL'
        print(f"  [{status}] {k}")
else:
    print("未找到今天的 competitors 条目")