#!/usr/bin/env python3
"""
Investment Orchestrator V2.0 - 统一 PipelineOrchestrator 入口

重构变更:
- 移除 from openclaw import sessions_spawn（禁止直接 spawn）
- 使用 EntryHarness + PipelineOrchestrator 统一执行引擎
- 保留迭代收敛逻辑，每轮迭代通过 PipelineOrchestrator 执行

DeepFlow 基础契约:
- spawn_fn 注入（禁止模块级 import openclaw）
- 统一执行引擎（所有领域通过 PipelineOrchestrator）
- Blackboard 数据流
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config.path_config import PathConfig
from core.blackboard.blackboard_manager import BlackboardManager
from core.quality.entry_harness import EntryHarness

_DEEPFLOW_BASE = Path(PathConfig.resolve().base_dir)


def generate_session_id(code: str, name: str) -> str:
    """生成会话 ID"""
    code_clean = code.replace(".", "_").lower()
    name_clean = name.lower().replace(" ", "_")[:10]
    uuid_short = str(uuid.uuid4())[:8]
    return f"investment_{code_clean}_{name_clean}_{uuid_short}"


def check_convergence(
    iteration: int,
    score: float,
    prev_scores: List[float],
    max_iterations: int = 10,
    target_score: float = 0.92,
    stall_threshold: float = 0.02,
) -> Dict[str, Any]:
    """检查是否应该收敛"""
    if iteration < 2:
        return {"converged": False, "reason": f"Need >=2 iterations (current: {iteration})"}
    if iteration >= max_iterations:
        return {"converged": True, "reason": f"Max iterations ({max_iterations})"}
    if score >= 0.95:
        return {"converged": True, "reason": f"High score ({score:.4f})"}
    if score >= target_score and len(prev_scores) >= 2:
        recent = prev_scores[-2:]
        if all(abs(prev_scores[i] - prev_scores[i - 1]) < stall_threshold for i in range(-1, -3, -1) if i > -len(prev_scores)):
            return {"converged": True, "reason": f"Target reached with stall"}
    if len(prev_scores) >= 3:
        recent = prev_scores[-3:]
        if max(recent) - min(recent) < stall_threshold:
            return {"converged": True, "reason": "Oscillation detected"}
    return {"converged": False, "reason": "Not converged"}


def _build_iteration_plan(
    session_id: str,
    iteration: int,
    code: str,
    name: str,
) -> str:
    """构建单轮迭代的执行计划和任务文件"""
    base_path = _DEEPFLOW_BASE / "blackboard" / session_id

    phases = [
        {"phase": 1, "stage": "data_collection", "worker": "data_manager", "parallel": False, "timeout": 300},
        {"phase": 2, "stage": "research", "workers": ["researcher_finance", "researcher_tech", "researcher_market", "researcher_macro", "researcher_management", "researcher_sentiment"], "parallel": True, "timeout": 300},
        {"phase": 3, "stage": "audit", "workers": ["auditor_correctness", "auditor_security", "auditor_performance"], "parallel": True, "timeout": 180},
        {"phase": 4, "stage": "fix", "worker": "fixer", "parallel": False, "timeout": 600},
        {"phase": 5, "stage": "verify", "worker": "verifier", "parallel": False, "timeout": 180},
    ]

    tasks = {
        "data_collection": f"Investment data collection: {name} ({code}) - iteration {iteration}",
        "research": {
            "researcher_finance": f"Financial research: {name}",
            "researcher_tech": f"Technical research: {name}",
            "researcher_market": f"Market research: {name}",
            "researcher_macro": f"Macro research: {name}",
            "researcher_management": f"Management research: {name}",
            "researcher_sentiment": f"Sentiment research: {name}",
        },
        "audit": {
            "auditor_correctness": f"Correctness audit: {name}",
            "auditor_security": f"Security audit: {name}",
            "auditor_performance": f"Performance audit: {name}",
        },
        "fix": f"Fix: {name}",
        "verify": f"Verify: {name}",
    }

    plan = {"session_id": session_id, "domain": "investment", "iteration": iteration, "phases": phases}

    plan_path = base_path / "execution_plan.json"
    tasks_path = base_path / "tasks.json"

    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    with open(tasks_path, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

    return str(plan_path)


def _extract_score(result: Dict[str, Any]) -> float:
    """从 PipelineOrchestrator 结果中提取分数"""
    workers = result.get("workers", {})
    verify = workers.get("verify", {})
    if verify and verify.get("success"):
        data = verify.get("result", {})
        if isinstance(data, dict):
            return data.get("score", 0.75)
    return 0.75


def run_investment_pipeline(
    code: str,
    name: str,
    spawn_fn: Any,
    max_iterations: int = 10,
    target_score: float = 0.92,
) -> Dict[str, Any]:
    """
    执行投资分析管线（统一 PipelineOrchestrator 入口）

    Args:
        code: 股票代码
        name: 股票名称
        spawn_fn: 注入的 spawn 函数（主Agent提供）
        max_iterations: 最大迭代次数
        target_score: 目标分数

    Returns:
        分析结果字典
    """
    print("=" * 60)
    print("DEEPFLOW V2.0 - INVESTMENT PIPELINE (Unified Engine)")
    print("=" * 60)

    session_id = generate_session_id(code, name)
    print(f"Session: {session_id} | Stock: {code} - {name}")
    print(f"Max Iterations: {max_iterations} | Target Score: {target_score}\n")

    blackboard = BlackboardManager(session_id=session_id)
    blackboard.init_session()
    blackboard.write("context.json", {"domain": "investment", "code": code, "name": name, "session_id": session_id})

    prev_scores: List[float] = []
    stage_outputs: Dict[str, Any] = {}
    convergence = {"converged": False, "reason": "Not started"}

    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*60}")
        print(f"ITERATION {iteration}/{max_iterations}")
        print(f"{'='*60}")

        # 构建本轮计划
        plan_path = _build_iteration_plan(session_id, iteration, code, name)

        # 通过 EntryHarness + PipelineOrchestrator 执行
        harness = EntryHarness()
        orchestrator = harness.validate_and_start(
            domain="investment",
            context={
                "code": code,
                "name": name,
                "session_id": session_id,
                "execution_plan_path": plan_path,
            },
            spawn_fn=spawn_fn,
        )
        result = orchestrator.run_pipeline()

        stage_outputs[f"iter{iteration}"] = result

        score = _extract_score(result)
        prev_scores.append(score)
        print(f"Iteration {iteration} Score: {score:.4f}")

        convergence = check_convergence(
            iteration=iteration,
            score=score,
            prev_scores=prev_scores,
            max_iterations=max_iterations,
            target_score=target_score,
        )

        if convergence["converged"]:
            print(f"\n✅ CONVERGED: {convergence['reason']}")
            break

    final_output = {
        "status": "completed",
        "pipeline_state": "CONVERGED" if convergence["converged"] else "MAX_ITERATIONS",
        "session_id": session_id,
        "final_score": prev_scores[-1] if prev_scores else 0,
        "convergence_reason": convergence["reason"],
        "iterations": iteration,
        "stage_outputs": stage_outputs,
    }

    print(f"\n{'='*60}")
    print("INVESTMENT PIPELINE COMPLETED")
    print(f"Status: {final_output['pipeline_state']} | Score: {final_output['final_score']:.4f}")
    print(f"{'='*60}")

    return final_output


# ============================================================================
# 向后兼容: CageOrchestrator 类
# ============================================================================

class CageOrchestrator:
    """向后兼容包装器，使用统一 PipelineOrchestrator 引擎"""

    def __init__(self):
        self.session_id = None
        self.domain = "investment"

    def run(self, context: Dict[str, Any], spawn_fn: Optional[Any] = None) -> Dict[str, Any]:
        """
        执行投资分析

        Args:
            context: 必须包含 code, name
            spawn_fn: 注入的 spawn 函数（必填）

        Returns:
            分析结果
        """
        code = context.get("code", "")
        name = context.get("name", "")
        if not code or not name:
            raise ValueError("Context must include 'code' and 'name'")
        if not spawn_fn:
            raise RuntimeError("spawn_fn required. Usage: orch.run(context, spawn_fn=sessions_spawn)")

        return run_investment_pipeline(
            code=code,
            name=name,
            spawn_fn=spawn_fn,
            max_iterations=context.get("max_iterations", 10),
            target_score=context.get("target_score", 0.92),
        )


if __name__ == "__main__":
    print("Investment Orchestrator V2.0")
    print("Usage from MainAgent: run_investment_pipeline(code, name, spawn_fn=sessions_spawn)")
