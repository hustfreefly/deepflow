#!/usr/bin/env python3
"""Go-Live 验证脚本"""
import sys, os, re

DEEPFLOW = os.path.expanduser("~/.openclaw/workspace/.deepflow")
os.chdir(DEEPFLOW)
sys.path.insert(0, ".")

results = []

# 1. 测试通过（用 os.popen 避免 subprocess 环境问题）
try:
    output = os.popen(f"cd {DEEPFLOW} && PYTHONPATH=. python3 -m pytest domains/solution_pro/tests/ --tb=no -q 2>&1").read()
    match = re.search(r"(\d+) passed", output)
    test_count = int(match.group(1)) if match else 0
    passed = test_count >= 100
    results.append((f"Tests pass ({test_count} passed, expect ≥100)", passed))
except Exception as e:
    results.append((f"Tests pass (error: {e})", False))

# 2. SKILL.md with open("domains/solution_pro/SKILL.md") as f:
    content = f.read()
results.append)
results.append(("No '10 阶段' in SKILL.md", "10 阶段" not in content))

# 3. MEMORY.md 无 引用
with open(os.path.expanduser("~/.openclaw/workspace/MEMORY.md")) as f:
    mem = f.read()
results.append(("MEMORY.md no '10阶段'", "10阶段" not in mem))

# 4. 入口可导入
try:
    from domains.solution_pro import run_solution_pro_v2
    results.append)
except ImportError:
    results.append)

# 5. ROLLBACK.md 存在
results.append(("ROLLBACK.md exists", 
    os.path.exists("domains/solution_pro/ROLLBACK.md")))

# Print results
all_pass = True
for name, ok in results:
    status = "✅" if ok else "❌"
    print(f"  {status} {name}")
    if not ok:
        all_pass = False

print(f"\n{'ALL PASS ✅' if all_pass else 'SOME FAILED ❌'}")
sys.exit(0 if all_pass else 1)
