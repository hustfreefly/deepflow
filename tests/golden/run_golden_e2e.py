#!/usr/bin/env python3
"""
Solution Pro E2E Golden Case 启动器

用法:
    cd ~/.openclaw/workspace/.deepflow
    python3 tests/golden/run_golden_e2e.py

功能:
    1. 调用 run_solution_pro() 生成执行计划
    2. 打印 session_id 和路径信息
    3. 输出后续步骤指令（主Agent spawn + cron）

注意: 此脚本只生成计划，不执行管线。
管线执行需要主Agent通过 sessions_spawn 启动 orchestrator。
"""

import json
import sys
import os

DEEPFLOW_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, DEEPFLOW_ROOT)

from domains.solution import run_solution_pro


def main():
    # 加载 golden case
    golden_path = os.path.join(os.path.dirname(__file__), "golden_case_001.json")
    with open(golden_path, "r", encoding="utf-8") as f:
        golden = json.load(f)

    input_params = golden["input"]

    print("=" * 60)
    print("🧪 Solution Pro E2E Golden Case Launcher")
    print("=" * 60)
    print(f"  Topic:    {input_params['topic']}")
    print(f"  Type:     {input_params['solution_type']}")
    print(f"  Mode:     {input_params['mode']}")
    print(f"  约束数:   {len(input_params['constraints'])}")
    print(f"  利益方:   {len(input_params['stakeholders'])}")
    print("=" * 60)

    # 调用 run_solution_pro
    print("\n⏳ 正在生成执行计划...")
    plan = run_solution_pro(
        topic=input_params["topic"],
        solution_type=input_params["solution_type"],
        mode=input_params["mode"],
        constraints=input_params["constraints"],
        stakeholders=input_params["stakeholders"],
    )

    print("\n✅ 执行计划生成成功!")
    print(f"  Session ID:  {plan['session_id']}")
    print(f"  Base Path:   {plan['base_path']}")
    print(f"  Plan Path:   {plan['plan_path']}")

    # 验证生成物
    print("\n📋 生成物检查:")
    for fname in ["execution_plan.json", "tasks.json", "data/frozen_spec.json"]:
        fpath = os.path.join(plan["base_path"], fname)
        exists = os.path.exists(fpath)
        print(f"  {'✅' if exists else '❌'} {fname}")

    # 输出 frozen spec 摘要
    frozen_path = os.path.join(plan["base_path"], "data", "frozen_spec.json")
    if os.path.exists(frozen_path):
        with open(frozen_path, "r", encoding="utf-8") as f:
            spec = json.load(f)
        reqs = spec.get("requirements", [])
        print(f"\n🔒 Frozen Spec: {len(reqs)} 条需求")
        for r in reqs:
            print(f"    {r['id']} [{r['priority']}] {r['description'][:60]}...")

    # 输出后续步骤
    print(f"""
{'=' * 60}
📌 后续步骤（在主Agent中执行）:

1. 清理旧状态文件:
   python3 -c "
   import os
   base = '{plan['base_path']}'
   for f in ['.completed', '.cron_job_id', '.cron_run_count', '.notified_stages.json', '.run_start_at']:
       p = os.path.join(base, f)
       os.path.exists(p) and os.remove(p)
   "

2. spawn orchestrator:
   sessions_spawn(
       runtime="subagent",
       mode="run",
       label="golden_orchestrator",
       task="<pipeline_orchestrator_v4.md 内容，替换变量>",
       runTimeoutSeconds=3600
   )

3. 创建 cron watcher（每3分钟巡检）

4. sessions_yield() 等待完成

5. 完成后运行验证:
   python3 tests/golden/verify_golden_case.py {plan['session_id']}
{'=' * 60}
""")

    # 输出 session_id 供外部脚本使用
    with open(os.path.join(os.path.dirname(__file__), ".last_session_id"), "w") as f:
        f.write(plan["session_id"])

    return plan


if __name__ == "__main__":
    main()
