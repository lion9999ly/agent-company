"""
@description: 图片目录监听器：新图片出现时自动生成 OCR 文字文件
@dependencies: feishu_bridge.ocr_middleware
@last_modified: 2026-03-18

运行方式：python feishu_bridge/image_watcher.py
"""
import time
from pathlib import Path
from feishu_bridge.ocr_middleware import process_image_to_text

WATCH_DIR = Path(r"D:\Users\uih00653\my_agent_company\pythonProject1\.cc-connect\images")

def process_new_image(img_path: Path):
    txt_path = img_path.with_suffix('.txt')
    if txt_path.exists():
        return
    print(f"[Watcher] 检测到新图片: {img_path.name}")
    text = process_image_to_text(str(img_path))
    txt_path.write_text(text, encoding='utf-8')
    print(f"[Watcher] OCR完成，写入: {txt_path.name}")

def watch():
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[Watcher] 监听目录: {WATCH_DIR}")
    seen = set()
    while True:
        for img in WATCH_DIR.glob("*.jpg"):
            if img not in seen:
                seen.add(img)
                process_new_image(img)
        time.sleep(1)

if __name__ == "__main__":
    watch()