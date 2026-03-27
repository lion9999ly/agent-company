#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from scripts.doc_importer import scan_and_import

def progress(msg):
    print(msg, flush=True)

print("=== 开始扫描 inbox ===", flush=True)
report = scan_and_import(progress_callback=progress)
if report:
    print("\n=== 导入报告 ===", flush=True)
    print(report, flush=True)
else:
    print("inbox 为空或无新文件", flush=True)
