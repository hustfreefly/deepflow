"""
DeepFlow Research Pro — 通用深度研究管线

## 唯一入口

```python
from domains.research_pro import run_research_pro

result = run_research_pro(
    query="分析贵州茅台的投资价值",
    mode="standard",  # 可选: "quick" | "standard"
)

# result = {
# "session_id": str,
# "spawn_params": dict, # 直接传给 sessions_spawn
# }
```

## 主 Agent 执行流程

```
Step 1: exec 中调 run_research_pro(query) → 生成计划 + spawn_params
Step 2: sessions_spawn(**result["spawn_params"]) → 启动子 Agent 执行
Step 3: 子 Agent 自动完成 confirm → execute → report
```

与 Solution Pro 完全一致的启动模式。
"""

import json
import logging
import os
import time
from pathlib import Path

from core.blackboard.blackboard_manager import BlackboardManager
from core.blackboard.context_injector import build_bootstrap_task, auto_bootstrap

logger = logging.getLogger(__name__)

# 契约笼子：sessions_spawn task 参数安全阈值（6KB，实际限制 ~8KB）
BOOTSTRAP_SIZE_THRESHOLD = 6000  # bytes

try:
    from domains.research_pro.orchestrator import ResearchProOrchestrator
except ImportError:
    ResearchProOrchestrator = None

__all__ = ["ResearchProOrchestrator", "run_research_pro"]


# ============================================================================
# Orchestrator 子 Agent Prompt 模板
# ============================================================================

_ORCHESTRATOR_PROMPT_FILE = "research_pro/orchestrator"


def run_research_pro(
    query: str,
    mode: str = "standard",
    **kwargs,
) -> dict:
    """
    Research Pro 唯一入口。

    在主 Agent 的 exec 环境中调用，生成研究计划并初始化状态。
    返回包含 spawn_params 的字典，主 Agent 只需将 spawn_params 传给 sessions_spawn 即可启动管线。

    与 Solution Pro 的 run_solution_pro() 完全对齐。

    Args:
        query: 研究主题（必需，>=10字符）
        mode: 'quick' 或 'standard'，默认 'standard'
        **kwargs: spawn_fn, web_search_fn, base_path（可选，base_path 已废弃，改用 BlackboardManager）

    Returns:
        {
            "session_id": str,
            "spawn_params": dict,  # 直接传给 sessions_spawn 的参数
        }
    """
    if ResearchProOrchestrator is None:
        raise ImportError("ResearchProOrchestrator 导入失败，请检查依赖安装")

    spawn_fn = kwargs.get("spawn_fn")
    web_search_fn = kwargs.get("web_search_fn")

    # 生成 session_id
    import hashlib
    query_hash = hashlib.md5(query.encode()).hexdigest()[:8]
    session_id = f"research_pro_{query_hash}_{int(time.time())}"

    # 初始化 BlackboardManager（替代旧路径 API）
    bm = BlackboardManager(session_id=session_id)
    bm.init_session()

    # Step 1: 初始化 Orchestrator（传入 session_dir 以供内部使用）
    orch = ResearchProOrchestrator(
        mode=mode,
        base_path=str(bm.get_session_dir()),
        spawn_fn=spawn_fn,
        web_search_fn=web_search_fn,
    )

    # Step 2: 生成研究计划（planning 阶段）
    init_result = orch.init_session(query)

    # session_id 已在上方生成，确保 state 中也记录
    if orch.state.get("session_id") != session_id:
        orch.state["session_id"] = session_id
        orch._save_state()

    # Step 3: 清理旧状态文件
    for old_file in [".completed", ".cron_run_count", ".notified_stages.json"]:
        try:
            bm._resolve(old_file).unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"research_pro cleanup failed: {e}")

    # Step 4: 初始化通知状态文件
    bm.write(".notified_stages.json", json.dumps({"notified": [], "total_messages_sent": 0}))
    bm.write(".cron_run_count", json.dumps({"count": 0, "max_runs": 20, "run_start_at": "PENDING"}))

    # Step 5: 构建 orchestrator prompt（仅替换 {session_id}, {mode}, {query}）
    # Load orchestrator prompt from registry
    from core.prompt_registry import read_prompt
    _orchestrator_template = read_prompt(_ORCHESTRATOR_PROMPT_FILE)
    orchestrator_prompt = (
        _orchestrator_template
        .replace("{session_id}", session_id)
        .replace("{mode}", mode)
        .replace("{query}", query)
    )

    # Step 6: 根据模式决定超时时间
    timeout_seconds = 1800 if mode == "standard" else 600

    # ═══════════════════════════════════════════
    # 契约笼子：Auto-Bootstrap（解决 sessions_spawn 截断）
    # orchestrator prompt > 6KB → 自动写入 blackboard + 替换为 bootstrap 引用
    # ═══════════════════════════════════════════
    deepflow_root = Path(__file__).resolve().parent.parent.parent
    prompt_bytes = len(orchestrator_prompt.encode('utf-8'))
    
    if prompt_bytes > BOOTSTRAP_SIZE_THRESHOLD:
        prompt_filename = "orchestrator_prompt.md"
        bm.write(prompt_filename, orchestrator_prompt, subdir="stages")
        
        # 写入验证
        verify = bm.read_stage_raw(f"stages/{prompt_filename}")
        if not verify:
            raise RuntimeError(
                f"Bootstrap write-back verification failed for {prompt_filename}"
            )
        
        task = build_bootstrap_task(
            deepflow_root=deepflow_root,
            blackboard_id=session_id,
            prompt_filename=prompt_filename,
            preamble=f"cd {deepflow_root} && PYTHONPATH=.",
        )
        logger.info(
            f"Research Pro auto-bootstrap: {prompt_bytes}B → {len(task.encode('utf-8'))}B"
        )
    else:
        task = orchestrator_prompt

    return {
        "session_id": session_id,
        "analysis_plan": init_result.get("analysis_plan", {}),
        "spawn_params": {
            "runtime": "subagent",
            "mode": "run",
            "label": "research_pro_orchestrator",
            "task": auto_bootstrap(deepflow_root, session_dir / "stages", task, "research_orchestrator"),
            "cwd": str(deepflow_root),
            "lightContext": True,
            "runTimeoutSeconds": timeout_seconds,
        },
    }