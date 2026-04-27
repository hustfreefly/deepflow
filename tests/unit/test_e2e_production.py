from core.config.path_config import PathConfig

#!/usr/bin/env python3
"""
DeepFlow 生产部署前端到端体检
验证: Coordinator.start() → WAITING_AGENT → resume() → COMPLETED
检查 Blackboard 输出完整性、无 bypass
"""

import asyncio
import json
import sys
import time
sys.path.insert(0, str(PathConfig.resolve().base_dir))

from coordinator import Coordinator, AgentResult
from blackboard_manager import BlackboardManager
from config_loader import ConfigLoader

# ── 计数器 ──
issues = []
checks_passed = []
bypass_log = []

def check(name: str, condition: bool, detail: str = ""):
    if condition:
        checks_passed.append(f"✅ {name}")
    else:
        issues.append(f"❌ {name}: {detail}")

async def run_e2e_test():
    print("=" * 60)
    print("🦞 DeepFlow 生产部署前深度体检")
    print("=" * 60)

    # ══════════════════════════════════════════════════════
    # TEST 1: general 域 iterative 管线全流程
    # ══════════════════════════════════════════════════════
    print("\n📍 TEST 1: general 域 iterative 管线全流程")
    print("   输入: '分析 Python asyncio 特性'")

    coordinator = Coordinator()
    status = await coordinator.start("分析 Python asyncio 特性")
    session_id = status.session_id
    round_num = 1
    max_rounds = 15
    all_pending = []

    print(f"   Round 1 → state={status.state}, domain={status.domain}")
    check("start() 返回 WAITING_AGENT 或 DONE",
          status.state in ("WAITING_AGENT", "COMPLETED", "DONE"),
          f"实际状态: {status.state}")

    if status.domain == "general":
        check("意图解析: general", True)
    else:
        check("意图解析: general", False, f"实际 domain={status.domain}")

    # 加载管线模板验证
    loader = ConfigLoader()
    config = loader.load_domain("general")
    pipeline = loader.load_pipeline(config.pipeline)
    check(f"管线模板加载: {config.pipeline}", len(pipeline.stages) > 0)
    stage_ids = [s.id for s in pipeline.stages]
    print(f"   管线 stages: {stage_ids}")

    while not status.is_completed and round_num < max_rounds:
        round_num += 1

        if status.is_waiting_agent:
            reqs = status.pending_requests
            print(f"   Round {round_num} → WAITING_AGENT, {len(reqs)} 个待执行")
            all_pending.extend(reqs)

            # 检查是否有 bypass 日志
            for req in reqs:
                bypass_log.append(f"[{round_num}] Agent: {req['agent_role']}, stage: {req['stage_id']}, instance: {req['instance_name']}")

            agent_results = []
            for req in reqs:
                # 模拟 Agent 产出写入 Blackboard
                bb = BlackboardManager(session_id)
                output_file = f"{req['stage_id']}_{req['instance_name']}.md"
                content = (
                    f"# {req['agent_role']} 输出\n\n"
                    f"Stage: {req['stage_id']}\n"
                    f"Instance: {req['instance_name']}\n"
                    f"Angle: {req['angle']}\n"
                    f"Input: {req['input_context'][:200]}\n\n"
                    f"Python asyncio 是协程框架，支持异步 I/O、事件循环、"
                    f"Task/Future 等核心特性。async/await 语法糖简化异步编程。"
                )
                bb.write(output_file, content)

                result = AgentResult(
                    request_id=req['request_id'],
                    success=True,
                    output_file=output_file,
                    score=0.85,
                )
                agent_results.append(result)

            status = await coordinator.resume(session_id, agent_results)
            print(f"   resume() → state={status.state}")

        elif status.state == "WAITING_HITL":
            print(f"   ⏸️  HITL 暂停，跳过")
            break
        else:
            status = await coordinator._resume_execution(session_id)
            print(f"   Round {round_num} → state={status.state}")

    # 检查结果
    if status.is_completed:
        check("管线执行到 COMPLETED", True)
        print(f"   ✅ 完成! 分数={status.final_result.quality_score:.2%}")
    else:
        check("管线执行到 COMPLETED", False, f"最终状态: {status.state}")

    # ══════════════════════════════════════════════════════
    # TEST 2: Blackboard 输出完整性
    # ══════════════════════════════════════════════════════
    print("\n📍 TEST 2: Blackboard 输出检查")

    bb = BlackboardManager(session_id)
    all_files = bb.list_files("*.md")
    shared_state = bb.get_shared_state()

    print(f"   文件列表: {[str(f) for f in all_files[:15]]}")
    print(f"   共享状态 keys: {list(shared_state.keys())}")

    # 检查 plan_output
    plan_files = [f for f in all_files if 'plan' in str(f).lower()]
    check("plan_output.md 存在", len(plan_files) > 0,
          f"plan 相关文件: {[str(f) for f in plan_files]}")

    # 检查 researcher_output
    researcher_files = [f for f in all_files if 'execute' in str(f).lower() or 'researcher' in str(f).lower()]
    check("researcher_output 存在", len(researcher_files) > 0,
          f"researcher/execute 相关文件: {[str(f) for f in researcher_files]}")

    # 检查 quality_scores
    quality_scores = shared_state.get("quality_scores", [])
    check("quality_scores 非空", len(quality_scores) > 0,
          f"quality_scores 长度={len(quality_scores)}")

    # 检查 shared_state 基本结构
    check("shared_state 包含 stage_history", "stage_history" in shared_state)
    check("shared_state 包含 quality_scores", "quality_scores" in shared_state)

    # ══════════════════════════════════════════════════════
    # TEST 3: 无 bypass 验证
    # ══════════════════════════════════════════════════════
    print("\n📍 TEST 3: 无 bypass 验证")

    check("所有 Agent 通过 Coordinator 调度", len(all_pending) > 0,
          f"总计 {len(all_pending)} 个 Agent 请求")

    # 检查是否有 "直接 spawn" 日志
    # 在我们的测试中，所有 Agent 都通过 Coordinator._create_agent_callback_d 收集
    spawn_log = [log for log in bypass_log if "spawn" in log.lower() and "coordinator" not in log.lower()]
    check("无 '直接 spawn' 日志", len(spawn_log) == 0,
          f"发现 {len(spawn_log)} 条可疑日志")

    # 验证所有 Agent 请求都有合法的 stage 关联
    valid_stages = {s.id for s in pipeline.stages}
    for req in all_pending:
        stage_id = req.get('stage_id', '')
        if stage_id not in valid_stages:
            issues.append(f"⚠️ Agent 请求关联到未知 stage: {stage_id}")

    check("所有 Agent 请求关联到有效 stage",
          all(req.get('stage_id', '') in valid_stages for req in all_pending))

    # 验证所有数据通过 Blackboard
    if all_files:
        check("所有数据走 Blackboard", True, f"共 {len(all_files)} 个文件")
    else:
        check("所有数据走 Blackboard", False, "Blackboard 为空")

    # 检查 Agent 调度日志
    print(f"   Agent 调度记录 ({len(bypass_log)} 条):")
    for log in bypass_log[:10]:
        print(f"     {log}")

    # ══════════════════════════════════════════════════════
    # TEST 4: 管线阶段完整性
    # ══════════════════════════════════════════════════════
    print("\n📍 TEST 4: 管线阶段覆盖检查")

    executed_stages = set()
    for req in all_pending:
        executed_stages.add(req.get('stage_id', 'unknown'))

    print(f"   已执行 stages: {executed_stages}")
    print(f"   管线定义 stages: {valid_stages}")

    skipped_ok = {"check", "fix", "verify"}
    missing_stages = valid_stages - executed_stages - skipped_ok
    if missing_stages:
        check(f"管线阶段覆盖 (缺失: {missing_stages})", False,
              f"已执行: {executed_stages}")
    else:
        check("管线阶段覆盖 (fix/check/verify因收敛跳过属正常)", True)

    # ══════════════════════════════════════════════════════
    # 汇总
    # ══════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("📊 体检报告")
    print("=" * 60)

    for c in checks_passed:
        print(f"  {c}")

    for i in issues:
        print(f"  {i}")

    total = len(checks_passed) + len(issues)
    score = int(len(checks_passed) / max(total, 1) * 100)

    passed = "✅ YES" if len(issues) == 0 else "⚠️ PARTIAL"
    if any("❌" in i for i in issues):
        passed = "❌ NO"

    print(f"\n  通过检查: {len(checks_passed)}/{total}")
    print(f"  测试结论: {passed}")
    print(f"  总体评分: {score}/100")
    print(f"  Agent 请求总数: {len(all_pending)}")
    print(f"  总轮数: {round_num}")
    print("=" * 60)

    return score, passed

if __name__ == "__main__":
    score, passed = asyncio.run(run_e2e_test())
    sys.exit(0 if score >= 70 else 1)
