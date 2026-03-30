"""
@description: 图片目录监听器：新图片出现时自动生成 OCR 文字文件
@dependencies: feishu_bridge.ocr_middleware
@last_modified: 2026-03-18

运行方式：python feishu_bridge/image_watcher.py
"""
import sys
import time
import shutil
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from feishu_bridge.ocr_middleware import process_image_to_text

WATCH_DIR = Path(r"D:\Users\uih00653\my_agent_company\pythonProject1\.cc-connect\images")

def process_new_image(img_path: Path):
    txt_path = img_path.with_suffix('.txt')
    if txt_path.exists():
        return
    print(f"[Watcher] 检测到新图片: {img_path.name}")

    # 备份原图（保持 .jpg 后缀以便 OCR 能处理）
    backup_path = img_path.parent / (img_path.stem + '_bak.jpg')
    shutil.copy2(img_path, backup_path)
    print(f"[Watcher] 已备份原图: {backup_path.name}")

    # OCR 识别（使用备份文件）
    text = process_image_to_text(str(backup_path))

    # 写 .txt 文件（保留供人工查看）
    txt_path.write_text(text, encoding='utf-8')

    # 用文字内容覆盖 .jpg（关键步骤）
    img_path.write_text(text, encoding='utf-8')

    print(f"[Watcher] OCR完成，已覆盖jpg并写入txt: {img_path.name}")

def watch():
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[Watcher] 监听目录: {WATCH_DIR}")
    seen = set()
    while True:
        for img in WATCH_DIR.glob("*.jpg"):
            if "_bak" in img.stem:
                continue
            if img not in seen:
                seen.add(img)
                process_new_image(img)
        time.sleep(1)

if __name__ == "__main__":
    watch()