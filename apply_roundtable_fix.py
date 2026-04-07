"""
圆桌系统飞书适配补丁
直接替换 scripts/roundtable/__init__.py 中的 run_task 函数

CC 执行方式：
1. 复制本文件到项目根目录
2. python apply_roundtable_fix.py
3. 飞书发送 圆桌:hud_demo 验证
4. 验证通过后删除本文件
"""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
INIT_FILE = PROJECT_ROOT / "scripts" / "roundtable" / "__init__.py"
ROUTER_FILE = PROJECT_ROOT / "scripts" / "feishu_handlers" / "text_router.py"

def fix_init_file():
    """修复 __init__.py: 所有 await feishu.notify() 改为安全调用"""
    content = INIT_FILE.read_text(encoding='utf-8')
    
    # 在文件顶部 import 区域后插入 _safe_notify 函数
    safe_notify_code = '''
import asyncio as _asyncio

async def _safe_notify(feishu, msg):
    """安全通知：兼容同步/异步/None"""
    if feishu is None:
        print(f"[Roundtable] {msg}")
        return
    try:
        if hasattr(feishu, 'notify'):
            result = feishu.notify(msg)
        elif callable(feishu):
            result = feishu(msg)
        else:
            print(f"[Roundtable] {msg}")
            return
        if _asyncio.iscoroutine(result):
            await result
    except Exception as e:
        print(f"[Roundtable] 通知失败({type(e).__name__}): {e}")
        print(f"[Roundtable] 原始消息: {msg}")
'''
    
    if '_safe_notify' not in content:
        # 找到第一个 def 或 class 之前插入
        match = re.search(r'^(async\s+)?def\s+|^class\s+', content, re.MULTILINE)
        if match:
            insert_pos = match.start()
            content = content[:insert_pos] + safe_notify_code + '\n' + content[insert_pos:]
        else:
            content = safe_notify_code + '\n' + content
    
    # 替换所有 await feishu.notify(...) 为 await _safe_notify(feishu, ...)
    content = re.sub(
        r'await\s+feishu\.notify\(([^)]+)\)',
        r'await _safe_notify(feishu, \1)',
        content
    )
    
    # 替换所有 await feishu(...)（如果有直接调用的情况）
    content = re.sub(
        r'await\s+feishu\(([^)]+)\)',
        r'await _safe_notify(feishu, \1)',
        content
    )
    
    INIT_FILE.write_text(content, encoding='utf-8')
    print(f"[OK] {INIT_FILE} 已修复")

def fix_router_file():
    """修复 text_router.py: 构造 FeishuAdapter + 传入 kb"""
    content = ROUTER_FILE.read_text(encoding='utf-8')
    
    # 查找 _run_roundtable 函数
    if '_run_roundtable' not in content:
        print(f"[SKIP] {ROUTER_FILE} 中未找到 _run_roundtable")
        return
    
    # 添加 FeishuAdapter 类（如果不存在）
    adapter_code = '''
class _FeishuAdapter:
    """将 send_reply 函数包装为圆桌系统期望的 feishu 对象"""
    def __init__(self, send_reply_func, reply_target):
        self._send = send_reply_func
        self._target = reply_target
    
    def notify(self, msg):
        self._send(self._target, msg)
'''
    
    if '_FeishuAdapter' not in content:
        # 在 _run_roundtable 函数之前插入
        match = re.search(r'def\s+_run_roundtable', content)
        if match:
            content = content[:match.start()] + adapter_code + '\n' + content[match.start():]
    
    # 修复 run_task 调用：替换 None 为 kb，替换 feishu 为 adapter
    # 找到 run_task(spec, gw, None, feishu) 并替换
    content = re.sub(
        r'run_task\(spec,\s*gw,\s*None,\s*feishu\)',
        'run_task(spec, gw, _kb_instance, _feishu_adapter)',
        content
    )
    
    # 在 _run_roundtable 函数内部，确保有 adapter 和 kb 的构造
    # 查找函数体
    match = re.search(r'def\s+_run_roundtable\([^)]*\):', content)
    if match:
        func_start = match.end()
        # 找到函数体的第一行非空非注释代码
        lines = content[func_start:func_start+2000].split('\n')
        insert_after = func_start
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith('#') and not stripped.startswith('"""') and not stripped.startswith("'''"):
                insert_after = func_start + sum(len(l) + 1 for l in lines[:i])
                break
        
        setup_code = '''
    # === 圆桌适配 ===
    _feishu_adapter = _FeishuAdapter(send_reply, reply_target)
    try:
        from src.tools.knowledge_base import search_knowledge
        class _KBWrapper:
            def search(self, query, top_k=5):
                return search_knowledge(query, limit=top_k)
        _kb_instance = _KBWrapper()
    except Exception as _kb_err:
        print(f"[Roundtable] KB 加载失败: {_kb_err}")
        _kb_instance = None
'''
        
        if '_feishu_adapter' not in content:
            content = content[:insert_after] + setup_code + '\n' + content[insert_after:]
    
    ROUTER_FILE.write_text(content, encoding='utf-8')
    print(f"[OK] {ROUTER_FILE} 已修复")

def fix_roundtable_modules():
    """修复 roundtable.py, generator.py, verifier.py 中的 await feishu.notify"""
    for filename in ['roundtable.py', 'generator.py', 'verifier.py', 'crystallizer.py']:
        filepath = PROJECT_ROOT / "scripts" / "roundtable" / filename
        if not filepath.exists():
            continue
        content = filepath.read_text(encoding='utf-8')
        
        changed = False
        
        # 添加 _safe_notify import（如果有 await feishu 调用）
        if 'await' in content and 'feishu' in content and '_safe_notify' not in content:
            # 添加 import
            import_line = "from scripts.roundtable import _safe_notify\n"
            if import_line not in content:
                # 找到第一个 import 之后插入
                match = re.search(r'^(from|import)\s+', content, re.MULTILINE)
                if match:
                    # 找到这个 import 块的末尾
                    pos = match.start()
                    content = content[:pos] + import_line + content[pos:]
                    changed = True
            
            # 替换 await feishu.notify(...)
            new_content = re.sub(
                r'await\s+self\.feishu\.notify\(([^)]+)\)',
                r'await _safe_notify(self.feishu, \1)',
                content
            )
            if new_content != content:
                content = new_content
                changed = True
            
            new_content = re.sub(
                r'await\s+feishu\.notify\(([^)]+)\)',
                r'await _safe_notify(feishu, \1)',
                content
            )
            if new_content != content:
                content = new_content
                changed = True
        
        if changed:
            filepath.write_text(content, encoding='utf-8')
            print(f"[OK] {filepath} 已修复")
        else:
            print(f"[SKIP] {filepath} 无需修改")

if __name__ == "__main__":
    print("=" * 50)
    print("圆桌系统飞书适配补丁")
    print("=" * 50)
    
    if not INIT_FILE.exists():
        print(f"[ERROR] 文件不存在: {INIT_FILE}")
        exit(1)
    if not ROUTER_FILE.exists():
        print(f"[ERROR] 文件不存在: {ROUTER_FILE}")
        exit(1)
    
    fix_init_file()
    fix_router_file()
    fix_roundtable_modules()
    
    print("\n" + "=" * 50)
    print("补丁完成。请：")
    print("1. 重启飞书服务")
    print("2. 飞书发送: 圆桌:hud_demo")
    print("3. 验证通过后删除本文件")
    print("=" * 50)
