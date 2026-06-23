#!/usr/bin/env python3
"""
DocUpdate 影响分析器

给定改动文件，查询依赖索引，输出受影响文档。

用法:
    python3 scripts/docupdate/analyze.py                     # git diff 未提交
    python3 scripts/docupdate/analyze.py --since HEAD~3      # 指定 commit 范围
    python3 scripts/docupdate/analyze.py gates.py reviewer.py  # 手动指定
"""

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

DEEPFLOW_ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = DEEPFLOW_ROOT / ".doc_index.json"

# 常见词过滤（这些符号太通用，引用不代表依赖）
NOISE_SYMBOLS = {
    "main", "init", "check", "run", "reset", "scan", "parse", "process",
    "setup", "cleanup", "validate", "handle", "execute", "load", "save",
    "read", "write", "get", "set", "update", "delete", "create", "remove",
    "start", "stop", "open", "close", "send", "receive", "format",
    "completed", "failed", "pending", "running", "timeout", "progress",
    "error", "warning", "info", "debug", "test", "assert",
    "parse_timestamp", "generate", "build", "compile", "transform",
    "dfs", "bfs", "sort", "filter", "map", "reduce", "merge",
}


def _get_changed_files(since: str = None) -> list[str]:
    """从 git diff 获取改动文件列表。"""
    cmd = ["git", "diff", "--name-only"]
    if since:
        cmd.append(since)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=DEEPFLOW_ROOT)
    return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]


def analyze(changed_files: list[str] = None, since: str = None):
    """分析改动的影响范围。"""

    # Step 1: 获取改动文件
    if not changed_files:
        changed_files = _get_changed_files(since)
    if not changed_files:
        print("没有检测到改动。")
        return {"red": [], "yellow": [], "green_count": 0}

    # Step 2: 加载索引
    if not INDEX_PATH.exists():
        print("⚠️ 索引不存在，正在构建...")
        sys.path.insert(0, str(DEEPFLOW_ROOT))
        from scripts.docupdate.build_index import build_index
        index = build_index()
    else:
        index = json.loads(INDEX_PATH.read_text())

    # Step 3: 查询影响
    affected_docs = defaultdict(lambda: {"reasons": [], "level": "green"})

    for changed_file in changed_files:
        changed_path = Path(changed_file)

        # 3a: 文件删除/重命名检查
        if not (DEEPFLOW_ROOT / changed_file).exists():
            for md_file in DEEPFLOW_ROOT.rglob("*.md"):
                if any(d in str(md_file) for d in ["ARCHIVED", "docs/archive", "blackboard", "__pycache__"]):
                    continue
                content = md_file.read_text(errors="ignore")
                if changed_file in content:
                    rel = str(md_file.relative_to(DEEPFLOW_ROOT))
                    affected_docs[rel]["reasons"].append(f"引用了已删除/重命名的文件: {changed_file}")
                    affected_docs[rel]["level"] = "red"

        # 3b: 符号级查询（过滤噪音符号）
        for sym_name, sym_info in index.items():
            if sym_info["defined_in"] == changed_file:
                # 跳过噪音符号（太通用，不代表真实依赖）
                if sym_name in NOISE_SYMBOLS:
                    continue
                # 跳过太短的符号名
                if len(sym_name) < 5:
                    continue
                for ref in sym_info.get("referenced_by_docs", []):
                    doc_file = ref["file"]
                    confidence = ref.get("confidence", "medium")
                    affected_docs[doc_file]["reasons"].append(
                        f"引用了 {sym_name} ({ref['context']})"
                    )
                    current = affected_docs[doc_file]["level"]
                    if confidence == "high":
                        if current != "red":
                            affected_docs[doc_file]["level"] = "yellow"
                    elif current == "green":
                        affected_docs[doc_file]["level"] = "yellow"

    # Step 4: 分类
    red, yellow = [], []
    for doc_file, info in affected_docs.items():
        entry = {"file": doc_file, "reasons": info["reasons"]}
        if info["level"] == "red":
            red.append(entry)
        elif info["level"] == "yellow":
            yellow.append(entry)

    # 统计 🟢 数量
    all_referenced_docs = set()
    for sym_info in index.values():
        for ref in sym_info.get("referenced_by_docs", []):
            all_referenced_docs.add(ref["file"])
    green_count = max(0, len(all_referenced_docs) - len(affected_docs))

    report = {
        "changed_files": changed_files,
        "red": sorted(red, key=lambda x: x["file"]),
        "yellow": sorted(yellow, key=lambda x: x["file"]),
        "green_count": green_count,
    }

    # Step 5: 输出报告
    _print_report(report)
    return report


def _print_report(report):
    print(f"\n{'='*60}")
    print(f"  DeepFlow DocUpdate 影响报告")
    print(f"{'='*60}\n")

    print(f"📁 改动文件 ({len(report['changed_files'])} 个):")
    for f in report["changed_files"][:15]:
        print(f"  - {f}")
    if len(report["changed_files"]) > 15:
        print(f"  ... 还有 {len(report['changed_files'])-15} 个")

    print(f"\n🔴 必须更新 ({len(report['red'])} 个):")
    if report["red"]:
        for item in report["red"]:
            print(f"  📄 {item['file']}")
            for r in item["reasons"][:3]:
                print(f"     → {r}")
            if len(item["reasons"]) > 3:
                print(f"     ... 还有 {len(item['reasons'])-3} 个原因")
    else:
        print("  无")

    print(f"\n🟡 建议更新 ({len(report['yellow'])} 个):")
    if report["yellow"]:
        for item in report["yellow"]:
            print(f"  📄 {item['file']}")
            for r in item["reasons"][:2]:
                print(f"     → {r}")
            if len(item["reasons"]) > 2:
                print(f"     ... 还有 {len(item['reasons'])-2} 个原因")
    else:
        print("  无")

    print(f"\n🟢 无需更新: {report['green_count']} 个文档不受影响")
    print(f"\n{'='*60}")


def auto_fix_red(report: dict) -> int:
    """自动修复 🔴 级别问题（路径重命名/删除）。"""
    import re as _re
    fixed_count = 0

    for item in report.get("red", []):
        doc_file = DEEPFLOW_ROOT / item["file"]
        if not doc_file.exists():
            continue
        content = doc_file.read_text(errors="ignore")
        new_content = content

        for reason in item["reasons"]:
            # 提取旧路径 → 新路径映射
            match = _re.search(r'已删除/重命名的文件: (.+)', reason)
            if match:
                old_path = match.group(1)
                # 尝试推断新路径（从 git diff 的改动文件中找同名文件）
                for changed in report.get("changed_files", []):
                    if Path(changed).name == Path(old_path).name and changed != old_path:
                        new_content = new_content.replace(old_path, changed)
                        fixed_count += 1
                        print(f"  ✅ {item['file']}: {old_path} → {changed}")
                        break

        if new_content != content:
            doc_file.write_text(new_content)

    return fixed_count


if __name__ == "__main__":
    since = None
    files = []
    auto = False
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--since" and i + 1 < len(args):
            since = args[i + 1]
            i += 2
        elif args[i].startswith("--since="):
            since = args[i].split("=", 1)[1]
            i += 1
        elif args[i] == "--auto-fix":
            auto = True
            i += 1
        else:
            files.append(args[i])
            i += 1

    report = analyze(changed_files=files if files else None, since=since)

    # 自动修复 🔴
    if auto and report.get("red"):
        print(f"\n⚙️  自动修复 🔴 级别问题...")
        fixed = auto_fix_red(report)
        print(f"  修复了 {fixed} 个文件")
