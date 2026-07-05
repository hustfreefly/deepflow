#!/usr/bin/env python3
"""
Solution Pro V2 E2E Test Runner（V3 重构版）

改动（相对于 V2 legacy 版本）：
- 删除 Spawn Bridge（文件中转）
- 改为显式入口 run_e2e(spawn_fn)
- 支持 mock 和真实 spawn_fn

版本: V3.0
日期: 2026-06-29
"""
import os
import sys
import json
import argparse
from pathlib import Path
from typing import Optional, Callable

DEEPFLOW = os.path.expanduser("~/.openclaw/workspace/.deepflow")
os.chdir(DEEPFLOW)
sys.path.insert(0, ".")

from domains.solution_pro.blackboard import BlackboardManager
from domains.solution_pro.master_orchestrator import MasterOrchestrator


# === 测试配置 ===
DEFAULT_TOPIC = "OpenClaw_AI_Native_Loop_Engineering_Framework"
DEFAULT_USER_INPUT = """构建 OpenClaw AI Native Loop Engineering Framework。

核心需求：
- 全LLM控制的自主循环执行框架
- 支持8+小时无人干预运行
- Dream Loop/Meta-Loop实现持续自优化
- 解决质量漂移、死循环、状态丢失、成本失控等核心问题

详细约束：
1. 三层Loop架构（Task Loop + Dream Loop + Meta-Loop）
2. Python只做执行器，所有决策逻辑由LLM prompt驱动
3. Hermes是对等协作伙伴（非子Agent），需要双向通信协议
4. 质量门控必须由LLM根据上下文动态判断
5. 状态持久化+上下文压缩+死循环熔断三重保障

技术基础：OpenClaw现有平台能力（sessions_spawn, BlackboardManager, Skill Workshop, Feishu通知）
"""


def run_e2e(
    spawn_fn: Optional[Callable] = None,
    topic: str = DEFAULT_TOPIC,
    user_input: str = DEFAULT_USER_INPUT,
    mode: str = "standard",
) -> dict:
    """E2E 测试入口。

    Args:
        spawn_fn:
            - None: 使用 mock_spawn_fn（测试模式）
            - Callable: 使用真实 spawn_fn（生产模式）
        topic: 测试主题
        user_input: 用户输入
        mode: standard | full

    Returns:
        dict: 测试结果
    """
    # Step 1: 如果没有 spawn_fn，创建 mock
    if spawn_fn is None:
        spawn_fn = _create_mock_spawn_fn()
        print("[E2E] 使用 mock_spawn_fn（测试模式）")
    else:
        print("[E2E] 使用真实 spawn_fn（生产模式）")

    # Step 2: 初始化 Blackboard
    bm = BlackboardManager(topic, base_dir=Path(DEEPFLOW) / "domains/solution_pro/blackboard_sessions")
    bm.init_session()
    print(f"[E2E] Session ID: {bm.session_id}")
    print(f"[E2E] Session dir: {bm.session_dir}")

    # Step 3: 写入 frozen_spec
    frozen_spec = _load_or_create_frozen_spec(topic)
    bm.write("data/frozen_spec.json", frozen_spec)
    req_count = len(frozen_spec.get("requirements", []))
    print(f"[E2E] Frozen spec loaded: {req_count} requirements")

    # Step 4: 创建 MasterOrchestrator
    config = {
        "topic": topic,
        "solution_type": "architecture",
        "mode": mode,
    }

    master = MasterOrchestrator(
        blackboard=bm,
        spawn_fn=spawn_fn,
        config=config,
    )

    # Step 5: 执行 Pipeline
    print(f"[E2E] Starting V2 Pipeline: Planning → Research → ReviewQC")
    try:
        result = master.run(user_input=user_input, config=config)
        status = result.get("status", "UNKNOWN")
        print(f"[E2E] Pipeline completed: {status}")
        return {
            "status": "PASS" if status == "COMPLETE" else "DEGRADED",
            "pipeline_result": result,
            "session_id": bm.session_id,
        }
    except Exception as e:
        print(f"[E2E] Pipeline failed: {e}")
        return {
            "status": "FAIL",
            "error": str(e),
            "session_id": bm.session_id,
        }


def _create_mock_spawn_fn():
    """创建 mock spawn_fn。"""
    try:
        from domains.solution_pro.llm_recorder import LLMRecorder
        recorder = LLMRecorder()
        return recorder.create_mock_spawn_fn()
    except Exception:
        # 最简 mock：返回空 JSON
        def mock_spawn(task=None, **kwargs):
            return json.dumps({"status": "mock", "output": {}})
        return mock_spawn


def _load_or_create_frozen_spec(topic: str) -> dict:
    """加载或创建最小 frozen_spec。"""
    # 尝试从已有 session 加载
    spec_dir = Path(DEEPFLOW) / "blackboard"
    if spec_dir.exists():
        for session_dir in spec_dir.iterdir():
            if session_dir.is_dir():
                spec_file = session_dir / "data" / "frozen_spec.json"
                if spec_file.exists():
                    with open(spec_file) as f:
                        return json.load(f)

    # 创建最小 frozen_spec
    return {
        "topic": topic,
        "solution_type": "architecture",
        "mode": "standard",
        "requirements": [
            {"req_id": "REQ-P0-001", "description": "全LLM控制", "priority": "P0"},
            {"req_id": "REQ-P0-002", "description": "8+小时运行", "priority": "P0"},
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Solution Pro V2 E2E Test (V3)")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="测试主题")
    parser.add_argument("--mode", default="standard", choices=["standard", "full"], help="运行模式")
    parser.add_argument("--mock", action="store_true", help="使用 mock spawn_fn（测试模式）")
    args = parser.parse_args()

    spawn_fn = None if args.mock else None  # 生产模式需要主 Agent 注入
    result = run_e2e(spawn_fn=spawn_fn, topic=args.topic, mode=args.mode)
    print(json.dumps(result, indent=2, ensure_ascii=False))
