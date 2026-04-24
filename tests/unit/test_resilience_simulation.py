#!/usr/bin/env python3
"""
ResilienceManager 容错机制模拟测试
模拟失败场景，验证各层容错是否真正能工作
"""

import asyncio
import json
import os
import sys
import tempfile
import time

# 确保能找到模块
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from resilience_manager import (
    ResilienceManager, CircuitBreaker, CircuitState,
    Task, Result, HealthLevel
)

passed = 0
failed = 0
issues = []

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        msg = f"  ❌ {name}" + (f" — {detail}" if detail else "")
        print(msg)
        issues.append(f"{name}: {detail}")


# ===================================================================
# Test 1: CircuitBreaker 基本状态机
# ===================================================================
print("\n" + "=" * 60)
print("Test 1: CircuitBreaker 基本状态机")
print("=" * 60)

cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.5)

# 初始状态
check("初始 CLOSED", cb.state == CircuitState.CLOSED,
      f"实际: {cb.state.name}")

# 允许请求
check("初始 allow_request=True", cb.allow_request() == True)

# 记录失败
cb.record_failure()
check("失败1次仍 CLOSED", cb.state == CircuitState.CLOSED,
      f"实际: {cb.state.name}")

cb.record_failure()
check("失败2次仍 CLOSED", cb.state == CircuitState.CLOSED,
      f"实际: {cb.state.name}")

cb.record_failure()
check("失败3次 → OPEN", cb.state == CircuitState.OPEN,
      f"实际: {cb.state.name}")

# 熔断后拒绝请求
check("OPEN 状态拒绝请求", cb.allow_request() == False)

# 等待恢复超时
print("  (等待 0.6s 进入 HALF_OPEN)...")
time.sleep(0.6)
check("超时后 → HALF_OPEN", cb.state == CircuitState.HALF_OPEN,
      f"实际: {cb.state.name}")

# HALF_OPEN 允许试探
check("HALF_OPEN 允许试探请求", cb.allow_request() == True)

# 试探成功 → 关闭
cb.record_success()
check("试探成功 → CLOSED", cb.state == CircuitState.CLOSED,
      f"实际: {cb.state.name}")

# HALF_OPEN 试探失败 → 重新 OPEN
cb2 = CircuitBreaker(failure_threshold=2, recovery_timeout=0.3)
cb2.record_failure()
cb2.record_failure()
assert cb2.state == CircuitState.OPEN
time.sleep(0.4)
assert cb2.state == CircuitState.HALF_OPEN
cb2.record_failure()
check("HALF_OPEN 试探失败 → 重新 OPEN", cb2.state == CircuitState.OPEN,
      f"实际: {cb2.state.name}")

# reset 功能
cb.reset()
check("reset 回到 CLOSED", cb.state == CircuitState.CLOSED)
check("reset 后 failure_count=0", cb.failure_count == 0)


# ===================================================================
# Test 2: Retry 重试逻辑
# ===================================================================
print("\n" + "=" * 60)
print("Test 2: Retry 重试逻辑")
print("=" * 60)

mgr = ResilienceManager({
    "max_retries": 2,
    "backoff_base": 0.01,  # 加速测试
    "backoff_max": 0.05,
    "circuit_failure_threshold": 3,
    "circuit_recovery_timeout": 1.0,
    "enable_degradation": False,  # 先不测试降级
})

call_count = 0

async def fail_then_succeed(task):
    """前2次失败，第3次成功"""
    global call_count
    call_count += 1
    if call_count <= 2:
        raise RuntimeError(f"Simulated failure #{call_count}")
    return Result(success=True, output="Success on attempt 3")

async def test_retry():
    task = Task(
        agent_id="test_retry_agent",
        task_prompt="test",
        model="default",
    )
    result = await mgr.execute_with_resilience(task, fail_then_succeed)
    return result

result = asyncio.run(test_retry())
check("重试最终成功", result.success == True,
      f"实际: success={result.success}, error={result.error}")
check("调用次数=3（2次失败+1次成功）", call_count == 3,
      f"实际: {call_count}")
check("重试成功未触发熔断", not mgr.is_circuit_open("test_retry_agent"))


# ===================================================================
# Test 3: 全部失败后的处理
# ===================================================================
print("\n" + "=" * 60)
print("Test 3: 全部失败 + 熔断 + 降级")
print("=" * 60)

mgr2 = ResilienceManager({
    "max_retries": 1,  # 最多重试1次（总共2次尝试）
    "backoff_base": 0.01,
    "backoff_max": 0.05,
    "circuit_failure_threshold": 2,  # 2次失败就熔断
    "circuit_recovery_timeout": 10.0,  # 长超时，不会很快恢复
    "enable_degradation": True,
})

call_count_2 = 0
fallback_called = False

async def always_fail(task):
    global call_count_2, fallback_called
    call_count_2 += 1
    if "degraded_from" in task.metadata:
        fallback_called = True
        # 降级模型成功
        return Result(success=True, output="Fallback succeeded", degraded=True)
    raise RuntimeError("Primary always fails")

async def test_all_fail():
    task = Task(
        agent_id="test_fail_agent",
        task_prompt="test",
        model="default",
        fallback_model="lightweight",
    )
    result = await mgr2.execute_with_resilience(task, always_fail)
    return result

result2 = asyncio.run(test_all_fail())
check("降级成功", result2.success == True,
      f"实际: success={result2.success}")
check("降级标记为 True", result2.degraded == True)
check("降级模型被调用", fallback_called == True,
      f"fallback_called={fallback_called}")
check("总调用次数=3（2次主模型+1次降级）", call_count_2 == 3,
      f"实际: {call_count_2}")


# ===================================================================
# Test 4: 熔断器阻止请求
# ===================================================================
print("\n" + "=" * 60)
print("Test 4: 熔断器阻止后续请求")
print("=" * 60)

mgr3 = ResilienceManager({
    "max_retries": 0,  # 不重试，直接失败
    "circuit_failure_threshold": 2,
    "circuit_recovery_timeout": 10.0,
    "enable_degradation": False,
})

call_count_3 = 0

async def always_fail_3(task):
    global call_count_3
    call_count_3 += 1
    raise RuntimeError("fail")

async def test_circuit_blocking():
    task = Task(
        agent_id="test_circuit_agent",
        task_prompt="test",
        model="default",
    )
    # 第一次：失败
    r1 = await mgr3.execute_with_resilience(task, always_fail_3)
    # 第二次：失败 → 熔断
    r2 = await mgr3.execute_with_resilience(task, always_fail_3)
    # 第三次：应该被熔断器阻止
    r3 = await mgr3.execute_with_resilience(task, always_fail_3)
    return r1, r2, r3

r1, r2, r3 = asyncio.run(test_circuit_blocking())
check("第1次失败", r1.success == False)
check("第2次失败并触发熔断", r2.success == False)
check("第3次被熔断阻止（无额外调用）", r3.success == False)
check("熔断阻止没有调用 executor", call_count_3 == 2,
      f"实际调用: {call_count_3}")
check("熔断错误信息包含 'OPEN'", "Circuit breaker OPEN" in r3.error,
      f"实际错误: {r3.error}")


# ===================================================================
# Test 5: Checkpoint 保存和加载
# ===================================================================
print("\n" + "=" * 60)
print("Test 5: Checkpoint 保存和加载")
print("=" * 60)

# 内存模式
mgr4 = ResilienceManager()
mgr4.save_checkpoint("stage_1", {"result": "partial_output", "score": 0.85})
loaded = mgr4.load_checkpoint("stage_1")
check("内存模式保存+加载", loaded is not None and loaded["result"] == "partial_output",
      f"实际: {loaded}")

# 不存在的检查点
check("不存在的检查点返回 None", mgr4.load_checkpoint("nonexistent") is None)

# 磁盘模式
with tempfile.TemporaryDirectory() as tmpdir:
    mgr5 = ResilienceManager({"checkpoint_dir": tmpdir})
    mgr5.save_checkpoint("stage_2", {"data": [1, 2, 3], "meta": "test"})
    
    # 验证文件存在
    cp_file = os.path.join(tmpdir, "stage_2.json")
    check("磁盘检查点文件存在", os.path.exists(cp_file))
    
    # 验证文件内容
    with open(cp_file) as f:
        content = json.load(f)
    check("磁盘内容正确", content["data"] == [1, 2, 3],
          f"实际: {content.get('data')}")
    
    # 从磁盘加载
    loaded2 = mgr5.load_checkpoint("stage_2")
    check("从磁盘加载成功", loaded2 is not None and loaded2["data"] == [1, 2, 3],
          f"实际: {loaded2}")

# 删除检查点
mgr4.delete_checkpoint("stage_1")
check("删除后加载返回 None", mgr4.load_checkpoint("stage_1") is None)
check("删除不存在的返回 False", mgr4.delete_checkpoint("nonexistent") == False)


# ===================================================================
# Test 6: Rollback 回滚
# ===================================================================
print("\n" + "=" * 60)
print("Test 6: Rollback 回滚")
print("=" * 60)

mgr6 = ResilienceManager({"enable_rollback": True})

# 保存多个状态
state1 = {"iteration": 1, "score": 0.5}
state2 = {"iteration": 2, "score": 0.7}
state3 = {"iteration": 3, "score": 0.85}

mgr6.save_safe_state(state1)
mgr6.save_safe_state(state2)
mgr6.save_safe_state(state3)

# 回滚到最近
rolled = mgr6.rollback_to_safe_state()
check("回滚到最近状态 (iter=3)", rolled is not None and rolled["iteration"] == 3,
      f"实际: {rolled}")

# 再次回滚
rolled2 = mgr6.rollback_to_safe_state()
check("再次回滚 (iter=2)", rolled2 is not None and rolled2["iteration"] == 2,
      f"实际: {rolled2}")

# 空栈回滚
mgr6.rollback_to_safe_state()  # pop iter=1
rolled3 = mgr6.rollback_to_safe_state()
check("空栈回滚返回 None", rolled3 is None)

# 禁用回滚
mgr7 = ResilienceManager({"enable_rollback": False})
mgr7.save_safe_state({"data": "test"})
check("禁用回滚时不保存", len(mgr7._rollback_stack) == 0)


# ===================================================================
# Test 7: 统计与可观测性
# ===================================================================
print("\n" + "=" * 60)
print("Test 7: 统计与可观测性")
print("=" * 60)

stats = mgr2.get_resilience_stats()
check("统计包含 executions", "total_executions" in stats)
check("统计包含 circuit_breakers", "circuit_breakers" in stats)
check("统计包含 success_rate", "success_rate" in stats)
check("success_rate 在 0-1 之间", 0 <= stats["success_rate"] <= 1,
      f"实际: {stats['success_rate']}")


# ===================================================================
# Test 8: PipelineEngine 集成检查
# ===================================================================
print("\n" + "=" * 60)
print("Test 8: PipelineEngine 集成检查")
print("=" * 60)

# 检查 pipeline_engine.py 中 resilience_manager 的调用
with open(os.path.join(os.path.dirname(__file__), "pipeline_engine.py")) as f:
    pe_code = f.read()

checks = {
    "导入 ResilienceManager": "from resilience_manager import ResilienceManager" in pe_code,
    "__init__ 接受 resilience_manager 参数": "resilience_manager" in pe_code,
    "agent stage 使用 execute_with_resilience": "execute_with_resilience" in pe_code,
}

for name, result in checks.items():
    check(name, result)

# 检查缺失的集成点
missing_integrations = []
if "save_safe_state" not in pe_code:
    missing_integrations.append("save_safe_state — 管线执行前未保存安全状态")
if "rollback_to_safe_state" not in pe_code:
    missing_integrations.append("rollback_to_safe_state — 阶段失败后未触发回滚")
if "save_checkpoint" not in pe_code or "self._resilience_manager.save_checkpoint" not in pe_code:
    missing_integrations.append("resilience_manager.save_checkpoint — 未使用韧性管理器保存检查点")
if "get_stage_retry_info" not in pe_code:
    missing_integrations.append("get_stage_retry_info — 未使用检查点重试 Stage")
if "reset_pipeline_state" not in pe_code:
    missing_integrations.append("reset_pipeline_state — 管线完成后未重置状态")

if missing_integrations:
    print(f"\n  ⚠️  PipelineEngine 缺失的集成点 ({len(missing_integrations)} 个):")
    for item in missing_integrations:
        print(f"    ❌ {item}")
else:
    print("\n  ✅ 所有集成点已覆盖")


# ===================================================================
# 汇总
# ===================================================================
print("\n" + "=" * 60)
print(f"汇总: {passed} passed, {failed} failed")
print("=" * 60)

if issues:
    print("\n❌ 失败详情:")
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")

sys.exit(0 if failed == 0 else 1)
