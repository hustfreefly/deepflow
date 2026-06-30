#!/usr/bin/env python3
"""
Solution Pro V2 E2E Test Runner（V3.1 增强版）

改动（相对于 V3.0）：
- 添加 verbose/debug 日志支持
- 关键节点耗时追踪
- Blackboard 写入监控
- 降级事件详细日志

版本: V3.1
日期: 2026-06-29
"""
import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import Optional, Callable

DEEPFLOW = os.path.expanduser("~/.openclaw/workspace/.deepflow")
os.chdir(DEEPFLOW)
sys.path.insert(0, ".")

from domains.solution_pro.blackboard import BlackboardManager
from domains.solution_pro.master_orchestrator import MasterOrchestrator


# === 日志级别 ===
LOG_QUIET = 0    # 只输出错误
LOG_NORMAL = 1   # 默认输出
LOG_VERBOSE = 2  # 详细日志
LOG_DEBUG = 3    # 调试日志（包含 blackboard 状态）

_log_level = LOG_NORMAL


def _log(msg: str, level: int = LOG_NORMAL):
    """按日志级别输出"""
    if _log_level >= level:
        print(msg)


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
    verbose: bool = False,
    debug: bool = False,
) -> dict:
    """E2E 测试入口。

    Args:
        spawn_fn:
            - None: 使用 mock_spawn_fn（测试模式）
            - Callable: 使用真实 spawn_fn（生产模式）
        topic: 测试主题
        user_input: 用户输入
        mode: standard | full
        verbose: 详细日志（模块耗时、blackboard 写入）
        debug: 调试日志（包含 blackboard 状态详情）

    Returns:
        dict: 测试结果
    """
    global _log_level
    if debug:
        _log_level = LOG_DEBUG
    elif verbose:
        _log_level = LOG_VERBOSE
    else:
        _log_level = LOG_NORMAL
    
    pipeline_start_time = time.time()
    module_stats = {}  # {module_name: {"status": str, "duration": float}}
    
    # Step 1: 如果没有 spawn_fn，创建 mock
    if spawn_fn is None:
        spawn_fn = _create_mock_spawn_fn()
        spawn_type = "mock spawn_fn (test mode)"
    else:
        spawn_type = f"real spawn_fn ({spawn_fn.__name__ if hasattr(spawn_fn, '__name__') else type(spawn_fn).__name__})"
    
    _log("[E2E] === Solution Pro V2 E2E Test ===")
    _log(f"[E2E] Topic: {topic}")
    _log(f"[E2E] Mode: {mode}")
    _log(f"[E2E] Spawn: {spawn_type}")
    
    if debug:
        _log(f"[E2E] User input length: {len(user_input)} chars")
    
    # Step 2: 初始化 Blackboard
    _log("[E2E] ---")
    _log(f"[E2E] [{_elapsed(pipeline_start_time)}] Initializing Blackboard...")
    bm = BlackboardManager(topic, base_dir=Path(DEEPFLOW) / "domains/solution_pro/blackboard_sessions")
    bm.init_session()
    _log(f"[E2E] Session: {bm.session_id}")
    _log(f"[E2E] Session dir: {bm.session_dir}", LOG_DEBUG)
    
    # 包装 BlackboardManager.write 以监控写入
    original_write = bm.write
    def monitored_write(path: str, data, **kwargs):
        result = original_write(path, data, **kwargs)
        if verbose:
            # 估算写入大小
            size_estimate = len(json.dumps(data)) if isinstance(data, (dict, list)) else len(str(data))
            _log(f"[E2E]   → Blackboard: {path} ({size_estimate:,}B)")
        elif debug:
            _log(f"[E2E]   → Blackboard write: {path}")
        return result
    bm.write = monitored_write

    # Step 3: 写入 frozen_spec
    frozen_spec = _load_or_create_frozen_spec(topic)
    bm.write("data/frozen_spec.json", frozen_spec)
    req_count = len(frozen_spec.get("requirements", []))
    _log(f"[E2E] Frozen spec: {req_count} requirements")

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

    # Step 5: 执行 Pipeline（带详细日志）
    _log(f"[E2E] [{_elapsed(pipeline_start_time)}] Starting V2 Pipeline: Planning → Research → ReviewQC")
    
    # 定义模块追踪顺序
    module_order = ["planning", "research", "review_qc"]
    
    try:
        result = master.run(user_input=user_input, config=config)
        status = result.get("status", "UNKNOWN")
        
        # 从结果中提取模块状态
        for mod_name in module_order:
            mod_result = result.get(mod_name)
            if mod_result is not None:
                module_stats[mod_name] = {"status": "✅", "duration": "N/A"}
            else:
                module_stats[mod_name] = {"status": "❌", "duration": "N/A"}
        
        # 检查降级模块
        degraded_modules = result.get("degraded_modules", [])
        for mod_name in degraded_modules:
            if mod_name in module_stats:
                module_stats[mod_name]["status"] = "⚠️ (degraded)"
        
        pipeline_duration = time.time() - pipeline_start_time
        
        _log("[E2E] ---")
        _log(f"[E2E] Pipeline COMPLETE in {_format_duration(pipeline_duration)}")
        
        # 打印各模块状态
        module_status_str = " | ".join([f"{m} {module_stats.get(m, {}).get('status', '?')}" for m in module_order if m in module_stats])
        _log(f"[E2E] Modules: {module_status_str}")
        
        # 打印降级信息
        if degraded_modules:
            _log(f"[E2E] Degraded: {', '.join(degraded_modules)}")
        else:
            _log("[E2E] Degraded: none")
        
        if debug:
            _log(f"[E2E] Final status: {status}")
            _log(f"[E2E] Result keys: {list(result.keys())}")
        
        return {
            "status": "PASS" if status == "COMPLETE" else "DEGRADED",
            "pipeline_result": result,
            "session_id": bm.session_id,
            "module_stats": module_stats,
            "duration_seconds": pipeline_duration,
        }
    except Exception as e:
        pipeline_duration = time.time() - pipeline_start_time
        _log("[E2E] ---")
        _log(f"[E2E] Pipeline FAILED in {_format_duration(pipeline_duration)}")
        _log(f"[E2E] Error: {e}")
        if debug:
            import traceback
            _log(f"[E2E] Traceback:\n{traceback.format_exc()}")
        return {
            "status": "FAIL",
            "error": str(e),
            "session_id": bm.session_id,
            "duration_seconds": pipeline_duration,
        }


def _elapsed(start_time: float) -> str:
    """返回从 start_time 到现在的耗时字符串 [MM:SS.s]"""
    elapsed = time.time() - start_time
    return _format_duration(elapsed)


def _format_duration(seconds: float) -> str:
    """格式化耗时：秒 → XmSS.s"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m{secs:.1f}s"


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
    parser = argparse.ArgumentParser(description="Solution Pro V2 E2E Test (V3.1)")
    parser.add_argument("--topic", default=DEFAULT_TOPIC, help="测试主题")
    parser.add_argument("--mode", default="standard", choices=["standard", "full"], help="运行模式")
    parser.add_argument("--mock", action="store_true", help="使用 mock spawn_fn（测试模式）")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志（模块耗时、blackboard 写入）")
    parser.add_argument("-d", "--debug", action="store_true", help="调试日志（包含 blackboard 状态详情）")
    args = parser.parse_args()

    spawn_fn = None if args.mock else None  # 生产模式需要主 Agent 注入
    result = run_e2e(
        spawn_fn=spawn_fn,
        topic=args.topic,
        mode=args.mode,
        verbose=args.verbose,
        debug=args.debug,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
