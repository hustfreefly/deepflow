#!/usr/bin/env python3
"""
analyze_json.py — 标准化 JSON 分析工具 (FIX-5)

用法:
  python3 scripts/analyze_json.py <file> --keys      # 打印顶层 keys + 类型
  python3 scripts/analyze_json.py <file> --summary    # 打印结构摘要 (max 3 层)
  python3 scripts/analyze_json.py <file> --field NAME # 打印指定字段详情
  python3 scripts/analyze_json.py <file> --count      # 统计列表/字典元素数量

设计目的: 子 Agent 在分析 JSON 数据前先调用此工具确认结构，避免 KeyError/AttributeError。
"""

import json
import sys
from pathlib import Path


def load_file(filepath: str):
    p = Path(filepath)
    if not p.exists():
        print(f"❌ 文件不存在: {filepath}")
        sys.exit(1)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败: {e}")
        sys.exit(1)


def cmd_keys(data):
    """打印顶层 keys + 类型 + 预览"""
    if isinstance(data, dict):
        print(f"类型: dict ({len(data)} keys)")
        print()
        for k, v in data.items():
            t = type(v).__name__
            if isinstance(v, dict):
                preview = f"{{{len(v)} keys}}"
            elif isinstance(v, list):
                preview = f"[{len(v)} items]"
            elif isinstance(v, str):
                preview = f'"{v[:60]}"' if len(v) <= 60 else f'"{v[:60]}..."'
            else:
                preview = str(v)[:80]
            print(f"  {k:30s} ({t:8s}) {preview}")
    elif isinstance(data, list):
        print(f"类型: list ({len(data)} items)")
        if data:
            item = data[0]
            if isinstance(item, dict):
                print(f"\n  [0] 的 keys ({len(item)} keys):")
                for k in item.keys():
                    print(f"    - {k}")
            else:
                print(f"\n  [0] 类型: {type(item).__name__} = {str(item)[:80]}")
    else:
        print(f"类型: {type(data).__name__} = {str(data)[:200]}")


def cmd_summary(data, depth=0, max_depth=3, max_items=5):
    """递归打印结构摘要"""
    indent = "  " * depth
    if isinstance(data, dict):
        print(f"{indent}{{  ({len(data)} keys)")
        for i, (k, v) in enumerate(data.items()):
            if i >= max_items and len(data) > max_items + 2:
                print(f"{indent}  ... ({len(data) - max_items} more keys)")
                break
            if isinstance(v, dict) and depth < max_depth:
                print(f"{indent}  {k}: {{  ({len(v)} keys)")
                cmd_summary(v, depth + 2, max_depth, max_items)
                print(f"{indent}  }}")
            elif isinstance(v, list):
                print(f"{indent}  {k}: [  ({len(v)} items)", end="")
                if v and depth < max_depth and isinstance(v[0], dict):
                    print(f" — [0] keys: {list(v[0].keys())[:8]}")
                else:
                    elem_type = type(v[0]).__name__ if v else "empty"
                    print(f" — type: {elem_type}")
            else:
                val_str = str(v)[:50]
                print(f"{indent}  {k}: ({type(v).__name__}) {val_str}")
        print(f"{indent}}}")
    elif isinstance(data, list):
        print(f"{indent}[  ({len(data)} items)")
        for i, item in enumerate(data[:max_items]):
            if isinstance(item, dict):
                print(f"{indent}  [{i}] {{  keys: {list(item.keys())[:8]}")
            else:
                print(f"{indent}  [{i}] ({type(item).__name__}) {str(item)[:50]}")
        if len(data) > max_items:
            print(f"{indent}  ... ({len(data) - max_items} more items)")
        print(f"{indent}]")


def cmd_field(data, field_name):
    """打印指定字段详情"""
    if isinstance(data, dict):
        if field_name in data:
            val = data[field_name]
            print(f"字段: {field_name}")
            print(f"类型: {type(val).__name__}")
            if isinstance(val, (dict, list)):
                print(json.dumps(val, ensure_ascii=False, indent=2)[:2000])
            else:
                print(f"值: {val}")
        else:
            print(f"❌ 字段 '{field_name}' 不存在")
            print(f"可用字段: {list(data.keys())}")
    elif isinstance(data, list):
        print(f"根类型是 list，尝试在 [0] 中查找 '{field_name}'")
        if data and isinstance(data[0], dict):
            cmd_field(data[0], field_name)
        else:
            print(f"❌ list 元素类型是 {type(data[0]).__name__ if data else 'empty'}")
    else:
        print(f"❌ 根类型是 {type(data).__name__}，不支持 --field")


def cmd_count(data):
    """统计元素数量"""
    if isinstance(data, dict):
        print(f"dict: {len(data)} keys")
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                print(f"  {k}: {type(v).__name__} ({len(v)} items)")
    elif isinstance(data, list):
        print(f"list: {len(data)} items")
    else:
        print(f"{type(data).__name__}: 标量值")


def main():
    if len(sys.argv) < 3:
        print("用法: analyze_json.py <file> --keys|--summary|--field NAME|--count")
        sys.exit(1)

    filepath = sys.argv[1]
    mode = sys.argv[2]
    data = load_file(filepath)

    if mode == "--keys":
        cmd_keys(data)
    elif mode == "--summary":
        cmd_summary(data)
    elif mode == "--field":
        if len(sys.argv) < 4:
            print("❌ --field 需要指定字段名")
            sys.exit(1)
        cmd_field(data, sys.argv[3])
    elif mode == "--count":
        cmd_count(data)
    else:
        print(f"❌ 未知模式: {mode}")
        print("支持: --keys | --summary | --field NAME | --count")
        sys.exit(1)


if __name__ == "__main__":
    main()
