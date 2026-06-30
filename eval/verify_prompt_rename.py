#!/usr/bin/env python3
"""
Prompt 去版本号重命名 — 契约笼子验证脚本
对应声明: eval/prompt_rename_contract.yaml
"""
import os
import sys
import re

BASE = os.path.expanduser("~/.openclaw/workspace/.deepflow")
PROMPTS_DIR = os.path.join(BASE, "domains/solution_pro/prompts")
SOLUTION_DIR = os.path.join(BASE, "domains/solution")

results = []

def check(name, passed, detail=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    results.append((name, passed, detail))
    print(f"  {status}: {name}")
    if detail:
        print(f"         {detail}")

print("=" * 60)
print("Prompt 去版本号重命名 — 契约验证")
print("=" * 60)

# === V1: 文件重命名 ===
print("\n--- V1: 文件重命名 ---")
old_files = [
    "pipeline_orchestrator_v6.md", "planner_v2_harness.md",
    "researcher_v2_harness.md", "reviewer_v2_harness.md",
    "consolidator_v2_harness.md", "auditor_v2_harness.md",
    "fixer_v2_harness.md", "fixer_expert_v2_harness.md",
    "summarizer_v2_harness.md", "harness_v3.md",
]
new_files = [
    "pipeline_orchestrator.md", "planner.md", "researcher.md",
    "reviewer.md", "consolidator.md", "auditor.md",
    "fixer.md", "fixer_expert.md", "summarizer.md", "harness_final.md",
]
old_exist = [f for f in old_files if os.path.exists(os.path.join(PROMPTS_DIR, f))]
new_missing = [f for f in new_files if not os.path.exists(os.path.join(PROMPTS_DIR, f))]
check("旧文件全部不存在", len(old_exist) == 0,
      f"残留: {old_exist}" if old_exist else "")
check("新文件全部存在", len(new_missing) == 0,
      f"缺失: {new_missing}" if new_missing else "")

# === V2: prompts/ 目录无版本号后缀文件 ===
print("\n--- V2: 目录无版本号后缀 ---")
versioned = [f for f in os.listdir(PROMPTS_DIR)
             if re.search(r'_v[0-9]', f) or '_v2_harness' in f]
check("无版本号后缀文件", len(versioned) == 0,
      f"残留: {versioned}" if versioned else "")

# === V3: .py 文件无版本号引用（注释除外） ===
print("\n--- V3: 代码无版本号引用 ---")
py_files = []
for root, dirs, files in os.walk(SOLUTION_DIR):
    if 'archive' in root or 'prompts_backup' in root or 'eval' in root:
        continue
    for f in files:
        if f.endswith('.py'):
            py_files.append(os.path.join(root, f))

version_patterns = ['_v2_harness', '_v6', 'harness_v3']
violations = []
for fpath in py_files:
    with open(fpath, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue  # 跳过注释
            for pat in version_patterns:
                if pat in stripped:
                    rel = os.path.relpath(fpath, BASE)
                    violations.append(f"{rel}:{i}: {stripped[:80]}")

check("代码文件无版本号引用", len(violations) == 0,
      f"{len(violations)} 处残留:\n" + "\n".join(f"         {v}" for v in violations[:5]) if violations else "")

# === V4: registry.yaml 无版本号 prompt_id ===
print("\n--- V4: registry.yaml 无版本号 ---")
import yaml
with open(os.path.join(BASE, "prompts/registry.yaml")) as f:
    reg = yaml.safe_load(f)

solution_ids = list(reg['domains']['solution_pro']['prompts'].keys())
versioned_ids = [pid for pid in solution_ids
                 if re.search(r'_v[0-9]', pid) or 'harness_final_v' in pid]
check("registry 无版本号 prompt_id", len(versioned_ids) == 0,
      f"残留: {versioned_ids}" if versioned_ids else "")

# === V5: registry 每个 filename 对应文件存在 ===
print("\n--- V5: registry filename 全部存在 ---")
missing_files = []
for pid, pdata in reg['domains']['solution_pro']['prompts'].items():
    fn = pdata.get('filename', '')
    fpath = os.path.join(PROMPTS_DIR, fn)
    if not os.path.exists(fpath):
        missing_files.append(f"{pid} → {fn}")
check("registry filename 全部存在", len(missing_files) == 0,
      f"缺失:\n" + "\n".join(f"         {m}" for m in missing_files) if missing_files else "")

# === V6: check_contract.py 中 required_prompts 匹配 ===
print("\n--- V6: check_contract.py 同步 ---")
cc_path = os.path.join(SOLUTION_DIR, "check_contract.py")
with open(cc_path) as f:
    cc_content = f.read()
cc_versioned = [pat for pat in version_patterns if pat in cc_content]
check("check_contract.py 无版本号引用", len(cc_versioned) == 0,
      f"残留: {cc_versioned}" if cc_versioned else "")

# === V7: 文档无残留版本号引用 ===
print("\n--- V7: 文档无残留 ---")
doc_files = [
    os.path.join(SOLUTION_DIR, "QUALITY_GUIDE.md"),
    os.path.expanduser("~/.openclaw/workspace/MEMORY.md"),
]
doc_violations = []
for fpath in doc_files:
    if not os.path.exists(fpath):
        continue
    with open(fpath) as f:
        for i, line in enumerate(f, 1):
            if 'v2_harness' in line or 'orchestrator_v6' in line or 'harness_v3' in line:
                rel = os.path.relpath(fpath, BASE)
                doc_violations.append(f"{rel}:{i}: {line.strip()[:80]}")
check("文档无残留版本号引用", len(doc_violations) == 0,
      f"{len(doc_violations)} 处残留:\n" + "\n".join(f"         {v}" for v in doc_violations[:5]) if doc_violations else "")

# === 汇总 ===
print("\n" + "=" * 60)
total = len(results)
passed = sum(1 for _, p, _ in results if p)
failed = total - passed
print(f"总计: {total} 项检查, {passed} PASS, {failed} FAIL")
if failed == 0:
    print("🎉 契约笼子验证全部通过！")
else:
    print(f"⚠️ {failed} 项未通过，需要修复")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
