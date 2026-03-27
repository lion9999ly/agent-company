# 大文件处理 + 文档重读 — 完整任务

> 生成时间: 2026-03-24
> 执行顺序: Task 1 → 2 → 3，每个完成后跑验证

---

## Task 1: PPTX 流式处理 + 多级降级（核心改动）

**原则: 不跳过任何文件，不管多大。处理不了就换方式，换方式还不行就再换，全部失败才标记待重试。**

### 1.1 重写 doc_importer.py 的 _read_pptx 函数

把现有的 `_read_pptx` 函数完整替换为以下版本：

```python
def _read_pptx(filepath: Path) -> str:
    """读取 PPTX：流式逐页处理，多级降级，不跳过任何文件"""
    import gc
    file_size_mb = filepath.stat().st_size / 1024 / 1024
    
    # 大文件提示
    if file_size_mb > 50:
        print(f"[DocImport] 大文件处理中: {filepath.name} ({file_size_mb:.0f}MB)")
    
    # === 策略 1: python-pptx 逐页流式处理 ===
    texts = []
    try:
        from pptx import Presentation
        prs = Presentation(str(filepath))
        total_slides = len(prs.slides)
        image_count = 0
        
        for slide_idx, slide in enumerate(prs.slides):
            slide_texts = []
            
            # 提取文字
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        text = para.text.strip()
                        if text:
                            slide_texts.append(text)
                
                # 提取表格
                if shape.has_table:
                    table = shape.table
                    for row in table.rows:
                        row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                        if row_text:
                            slide_texts.append(" | ".join(row_text))
            
            if slide_texts:
                texts.append(f"[第{slide_idx+1}/{total_slides}页]\n" + "\n".join(slide_texts))
            
            # 提取图片（所有图片都处理，压缩后发 Vision）
            for shape in slide.shapes:
                if shape.shape_type == 13:  # MSO_SHAPE_TYPE.PICTURE
                    try:
                        img_bytes = shape.image.blob
                        if len(img_bytes) > 2000:  # 跳过小图标
                            # 压缩图片
                            compressed = _compress_image_bytes(img_bytes)
                            desc = _read_image_bytes(compressed, f"PPT第{slide_idx+1}页图片")
                            if desc and not desc.startswith("["):
                                texts.append(f"[第{slide_idx+1}页图片]\n{desc}")
                                image_count += 1
                    except Exception:
                        continue
            
            # 每 10 页释放一次内存
            if (slide_idx + 1) % 10 == 0:
                gc.collect()
        
        prs = None
        gc.collect()
        
        if texts:
            print(f"[DocImport] python-pptx 成功: {len(texts)} 段, {image_count} 张图片, {total_slides} 页")
            return "\n\n".join(texts)
    
    except MemoryError:
        print(f"[DocImport] python-pptx OOM ({file_size_mb:.0f}MB)，降级到 PDF 转换")
        gc.collect()
    except Exception as e:
        print(f"[DocImport] python-pptx 失败: {e}，降级到 PDF 转换")
        gc.collect()
    
    # === 策略 2: LibreOffice 转 PDF → pymupdf 逐页读 ===
    try:
        import subprocess
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            # LibreOffice 转 PDF
            cmd = [
                "soffice", "--headless", "--convert-to", "pdf",
                "--outdir", tmp_dir, str(filepath)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            # 找到生成的 PDF
            pdf_files = list(Path(tmp_dir).glob("*.pdf"))
            if pdf_files:
                pdf_path = pdf_files[0]
                print(f"[DocImport] LibreOffice 转 PDF 成功: {pdf_path.name}")
                
                # 用 pymupdf 逐页读（内存友好）
                import fitz
                doc = fitz.open(str(pdf_path))
                pdf_texts = []
                
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    page_text = page.get_text().strip()
                    
                    if page_text and len(page_text) > 20:
                        pdf_texts.append(f"[第{page_num+1}页]\n{page_text}")
                    else:
                        # 文字少的页面用 Vision OCR
                        try:
                            mat = fitz.Matrix(2, 2)
                            pix = page.get_pixmap(matrix=mat)
                            img_bytes = pix.tobytes("png")
                            if len(img_bytes) > 5000:
                                desc = _read_image_bytes(img_bytes, f"PDF第{page_num+1}页")
                                if desc and not desc.startswith("["):
                                    pdf_texts.append(f"[第{page_num+1}页OCR]\n{desc}")
                        except Exception:
                            pass
                    
                    # 每 10 页释放内存
                    if (page_num + 1) % 10 == 0:
                        gc.collect()
                
                doc.close()
                gc.collect()
                
                if pdf_texts:
                    print(f"[DocImport] PDF 读取成功: {len(pdf_texts)} 页")
                    return "\n\n".join(pdf_texts)
            else:
                print(f"[DocImport] LibreOffice 未生成 PDF, returncode={result.returncode}")
                if result.stderr:
                    print(f"  stderr: {result.stderr[:300]}")
    
    except FileNotFoundError:
        print("[DocImport] LibreOffice 未安装，跳过 PDF 降级")
    except subprocess.TimeoutExpired:
        print("[DocImport] LibreOffice 转换超时(300s)")
    except Exception as e:
        print(f"[DocImport] PDF 降级失败: {e}")
    
    gc.collect()
    
    # === 策略 3: 直接解压 pptx（它是 zip），读 XML 提取纯文本 ===
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        
        zip_texts = []
        with zipfile.ZipFile(str(filepath), 'r') as z:
            # 找所有 slide XML
            slide_files = sorted([f for f in z.namelist() if f.startswith("ppt/slides/slide") and f.endswith(".xml")])
            
            for slide_file in slide_files:
                try:
                    with z.open(slide_file) as sf:
                        tree = ET.parse(sf)
                        root = tree.getroot()
                        
                        # 提取所有文本节点
                        ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
                        page_texts = []
                        for t_elem in root.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}t'):
                            if t_elem.text and t_elem.text.strip():
                                page_texts.append(t_elem.text.strip())
                        
                        if page_texts:
                            slide_num = slide_file.split("slide")[-1].replace(".xml", "")
                            zip_texts.append(f"[第{slide_num}页]\n" + "\n".join(page_texts))
                except Exception:
                    continue
        
        gc.collect()
        
        if zip_texts:
            print(f"[DocImport] ZIP/XML 提取成功: {len(zip_texts)} 页（纯文本，无图片）")
            return "\n\n".join(zip_texts)
    
    except Exception as e:
        print(f"[DocImport] ZIP/XML 提取失败: {e}")
    
    # === 全部失败：标记待重试 ===
    pending_dir = Path(__file__).parent.parent / ".ai-state" / "pending_imports"
    pending_dir.mkdir(parents=True, exist_ok=True)
    
    # 记录失败信息
    import json
    fail_record = {
        "filename": filepath.name,
        "size_mb": round(file_size_mb, 1),
        "failed_at": datetime.now().isoformat(),
        "reason": "所有策略均失败(python-pptx/LibreOffice+PDF/ZIP+XML)",
        "original_path": str(filepath)
    }
    fail_path = pending_dir / f"{filepath.stem}_pending.json"
    fail_path.write_text(json.dumps(fail_record, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"[DocImport] 全部策略失败，已记录待重试: {fail_path}")
    return f"[处理失败，已记录待后续重试: {filepath.name} ({file_size_mb:.0f}MB)]"
```

### 1.2 添加图片压缩辅助函数

在 doc_importer.py 中，`_read_image_bytes` 函数附近添加（如果项目中已有 compress_image 可直接复用）：

```python
def _compress_image_bytes(img_bytes: bytes, max_size: int = 1024) -> bytes:
    """压缩图片字节：限制最大边 max_size 像素，JPEG 质量 85"""
    try:
        from PIL import Image
        from io import BytesIO
        img = Image.open(BytesIO(img_bytes))
        img.thumbnail((max_size, max_size))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return img_bytes  # 压缩失败就用原图
```

### 1.3 修改 scan_and_import：大文件处理前通知 + 处理后释放内存

在 `scan_and_import` 函数的文件遍历循环中（`for f in files:` 内部），在 `content = _read_file(f)` 之前添加：

```python
            # 大文件预通知
            file_size_mb = f.stat().st_size / 1024 / 1024
            if file_size_mb > 50 and progress_callback:
                progress_callback(f"📦 正在处理大文件: {short_name} ({file_size_mb:.0f}MB)，请稍候...")
```

在 `f.rename(PROCESSED_DIR / f.name)` 之后添加：

```python
            # 每个文件处理完强制释放内存
            import gc
            gc.collect()
```

### 1.4 安装依赖（如果缺失）

```bash
pip install Pillow --break-system-packages
```

LibreOffice 如果没装，策略 2 会自动跳过走策略 3，不影响。

### 1.5 验证

```bash
python -c "
from scripts.doc_importer import _read_pptx, _compress_image_bytes
from pathlib import Path

# 验证压缩函数
test_bytes = b'\x89PNG' + b'\x00' * 100  # 假数据
result = _compress_image_bytes(test_bytes)
print(f'压缩函数: OK (输入 {len(test_bytes)} → 输出 {len(result)} bytes)')

# 验证 _read_pptx 能被导入
print(f'_read_pptx: 可导入')

# 验证 pending 目录创建
pending = Path('.ai-state/pending_imports')
pending.mkdir(parents=True, exist_ok=True)
print(f'pending 目录: {pending.exists()}')

print('✅ Task 1 完成')
"
```

---

## Task 2: 重读 processed 文档

**需求**: 之前导入过的文档可能提炼不够深，需要支持重新导入。

### 2.1 添加飞书指令

在 feishu_sdk_client.py 的文本指令处理中添加：

```python
elif text.strip() in ("重读文档", "reread", "重新导入"):
    import shutil
    from pathlib import Path
    processed = Path(".ai-state/inbox/processed")
    inbox = Path(".ai-state/inbox")
    
    if not processed.exists():
        send_reply(open_id, "📂 processed 目录为空，没有需要重读的文档")
        return
    
    count = 0
    total_size_mb = 0
    for f in processed.iterdir():
        if f.is_file() and f.suffix.lower() in ('.pptx', '.pdf', '.docx', '.xlsx', '.txt', '.md', '.csv',
                                                   '.png', '.jpg', '.jpeg', '.gif', '.webp',
                                                   '.mp3', '.wav', '.ogg', '.m4a',
                                                   '.mp4', '.mov'):
            shutil.move(str(f), str(inbox / f.name))
            total_size_mb += f.stat().st_size / 1024 / 1024 if (inbox / f.name).exists() else 0
            count += 1
    
    if count == 0:
        send_reply(open_id, "📂 processed 中没有可重读的文件")
        return
    
    send_reply(open_id, f"📂 已将 {count} 个文件移回 inbox ({total_size_mb:.0f}MB)，开始重新导入...\n这些文件会用更深入的视角重新提炼。")
    
    # 在后台线程执行，避免阻塞
    import threading
    def _reread():
        try:
            from scripts.doc_importer import scan_and_import
            report = scan_and_import(progress_callback=lambda msg: send_reply(open_id, msg))
            if report:
                send_reply(open_id, report)
            else:
                send_reply(open_id, "✅ 重读完成，无新知识产出")
        except Exception as e:
            send_reply(open_id, f"❌ 重读失败: {e}")
    
    threading.Thread(target=_reread, daemon=True).start()
```

### 2.2 添加待重试文件的查询和重试指令

```python
elif text.strip() in ("待处理", "pending", "失败文件"):
    from pathlib import Path
    import json
    pending_dir = Path(".ai-state/pending_imports")
    if not pending_dir.exists() or not list(pending_dir.glob("*.json")):
        send_reply(open_id, "📂 没有待处理的失败文件")
        return
    
    lines = ["📂 待重试文件："]
    for f in pending_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            lines.append(f"  - {data.get('filename', '?')} ({data.get('size_mb', '?')}MB)")
            lines.append(f"    失败时间: {data.get('failed_at', '?')}")
            lines.append(f"    原因: {data.get('reason', '?')[:80]}")
        except:
            continue
    send_reply(open_id, "\n".join(lines))
```

### 2.3 验证

```bash
python -c "
from pathlib import Path
# 检查 processed 目录中有多少文件可重读
processed = Path('.ai-state/inbox/processed')
if processed.exists():
    files = [f for f in processed.iterdir() if f.is_file()]
    total_mb = sum(f.stat().st_size / 1024 / 1024 for f in files)
    print(f'可重读文件: {len(files)} 个, 总大小: {total_mb:.0f}MB')
    for f in files[:5]:
        print(f'  - {f.name} ({f.stat().st_size / 1024 / 1024:.1f}MB)')
    if len(files) > 5:
        print(f'  ... 及其他 {len(files)-5} 个')
else:
    print('processed 目录不存在')
print('✅ Task 2 完成')
"
```

---

## Task 3: 立即处理 inbox 中的新 PPT 文件

**需求**: 用户已经把一批智驾大陆 Astra/Luna 相关 PPT 放进了 inbox。

### 3.1 重启服务让 DocImporter 自动扫描

重启主服务后，DocImporter 会自动扫描 inbox 并开始处理。观察日志确认：

1. 小文件（< 50MB）直接用 python-pptx 处理
2. 中等文件（50-200MB）python-pptx 处理 + 大文件提示
3. 大文件（> 200MB）如果 python-pptx OOM，自动降级到 PDF 或 ZIP/XML
4. 每个文件都有产出（不跳过）

### 3.2 如果自动扫描没触发，手动触发

在飞书发送：`导入` 或在命令行执行：

```bash
python -c "
from scripts.doc_importer import scan_and_import
report = scan_and_import(progress_callback=lambda msg: print(msg))
print(report)
"
```

### 3.3 处理完成后验证知识库增量

```bash
python -c "
from src.tools.knowledge_base import get_knowledge_stats
from scripts.daily_learning import audit_knowledge_base

stats = get_knowledge_stats()
total = sum(stats.values())
print(f'知识库总量: {total} 条')
print(f'分布: {stats}')

audit = audit_knowledge_base()
print(f'质量: 浅{audit[\"shallow\"]}({audit[\"shallow_pct\"]}%) 无数据{audit[\"no_data\"]} 重复{audit[\"duplicates\"]}')
"
```

---

## 执行完成后的检查清单

```bash
# 1. 确认改动可导入
python -c "from scripts.doc_importer import scan_and_import, _read_pptx, _compress_image_bytes; print('OK')"

# 2. 确认 inbox 中的文件
dir .ai-state\inbox\*.pptx

# 3. 重启服务，观察 DocImporter 日志
# 预期看到：
#   [DocImporter] 收件箱扫描已启动
#   [DocImport] 大文件处理中: xxx.pptx (435MB)
#   [DocImport] python-pptx 成功: N 段, M 张图片
#   或
#   [DocImport] python-pptx OOM，降级到 PDF 转换
#   [DocImport] PDF 读取成功: N 页
```

---

## 新增飞书指令汇总

| 指令 | 功能 |
|------|------|
| 重读文档 / reread | 把 processed 下的文件移回 inbox 重新导入 |
| 待处理 / pending | 查看处理失败待重试的文件列表 |
| 审计 / audit | 知识库质量审计（Day 8 已加） |
| 重置学习 / reset learning | 清空固定主题覆盖记录（Day 8 已加） |
| 自动研究 / auto research | 手动触发基于对齐报告的自动研究（Day 9 已加） |
