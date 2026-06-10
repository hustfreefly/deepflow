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
#     "session_id": str,
#     "base_path": str,
#     "plan_path": str,
#     "spawn_params": dict,  # 直接传给 sessions_spawn
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
import os
import time
from pathlib import Path

try:
    from domains.research_pro.orchestrator import ResearchProOrchestrator
except ImportError:
    ResearchProOrchestrator = None

__all__ = ["ResearchProOrchestrator", "run_research_pro"]


# ============================================================================
# Orchestrator 子 Agent Prompt 模板
# ============================================================================

_ORCHESTRATOR_PROMPT_TEMPLATE = """\
# Research Pro Orchestrator

你是 Research Pro 的编排器子 Agent。你的任务是驱动 Research Pro 的完整流程。

## 当前状态

- **session_id**: __SESSION_ID__
- **base_path**: __BASE_PATH__
- **mode**: __MODE__
- **query**: __QUERY__

## 你的执行步骤

### Step 1: 加载已有计划
```bash
cat __BASE_PATH__/state.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d.get('analysis_plan',dict()), ensure_ascii=False, indent=2))"
```
查看分析计划，确认子任务和关键词组。

### Step 2: 自动确认计划
调用 Python 确认计划（auto-approve，无需等待用户）:
```bash
cd __BASE_PATH__/../../.. && python3 -c "
import sys; sys.path.insert(0, '.')
from domains.research_pro.orchestrator import ResearchProOrchestrator
orch = ResearchProOrchestrator(mode='__MODE__', base_path='__BASE_PATH__')
result = orch.confirm_plan(dict(action='approve'))
print('Plan confirmed:', result.get('stage_status'))
"
```

### Step 3: 执行研究
```bash
cd __BASE_PATH__/../../.. && python3 -c "
import sys; sys.path.insert(0, '.')
from domains.research_pro.orchestrator import ResearchProOrchestrator
orch = ResearchProOrchestrator(mode='__MODE__', base_path='__BASE_PATH__')
result = orch.execute_research()
print('Sources:', result.get('sources_count'))
print('Batches:', len(result.get('batches', list())))
"
```

### Step 4: 生成报告
```bash
cd __BASE_PATH__/../../.. && python3 -c "
import sys; sys.path.insert(0, '.')
from domains.research_pro.orchestrator import ResearchProOrchestrator
orch = ResearchProOrchestrator(mode='__MODE__', base_path='__BASE_PATH__')
result = orch.generate_report()
print('Report path:', result.get('report_path'))
print('Citations:', result.get('citations_verified'))
"
```

### Step 5: 写入完成标记
```bash
echo '{"completed_at": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'", "status": "done"}' > __BASE_PATH__/.completed
```

## 重要约束

- ❌ 不要在中途停止，必须跑完所有 4 步
- ❌ 不要修改 state.json 手动，通过 Python API 操作
- ✅ 每步完成后打印结果供主 Agent 监控
- ✅ 遇到错误时打印详细错误信息并继续尝试下一步
- ✅ 最终写入 .completed 文件后才算完成
"""


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
        **kwargs: spawn_fn, web_search_fn, base_path（可选）

    Returns:
        {
            "session_id": str,
            "base_path": str,
            "plan_path": str,
            "spawn_params": dict,  # 直接传给 sessions_spawn 的参数
        }
    """
    if ResearchProOrchestrator is None:
        raise ImportError("ResearchProOrchestrator 导入失败，请检查依赖安装")

    spawn_fn = kwargs.get("spawn_fn")
    web_search_fn = kwargs.get("web_search_fn")

    # 生成 session_id 和 base_path（与 Solution Pro 对齐）
    import hashlib
    query_hash = hashlib.md5(query.encode()).hexdigest()[:8]
    session_id = f"research_pro_{query_hash}_{int(time.time())}"
    
    from core.config.path_config import PathConfig
    _path_config = PathConfig.resolve()
    base_path_input = str(_path_config.base_dir / "blackboard" / session_id)

    # Step 1: 初始化 Orchestrator
    orch = ResearchProOrchestrator(
        mode=mode,
        base_path=base_path_input,
        spawn_fn=spawn_fn,
        web_search_fn=web_search_fn,
    )

    # Step 2: 生成研究计划（planning 阶段）
    init_result = orch.init_session(query)

    # session_id 已在上方生成，确保 state 中也记录
    if orch.state.get("session_id") != session_id:
        orch.state["session_id"] = session_id
        orch._save_state()
    base_path = str(orch.base_path)
    plan_path = f"{base_path}/state.json"

    # Step 3: 清理旧状态文件（与 Solution Pro 一致）
    for old_file in [".completed", ".cron_run_count", ".notified_stages.json"]:
        path = os.path.join(base_path, old_file)
        if os.path.exists(path):
            os.remove(path)

    # Step 4: 初始化通知状态文件
    os.makedirs(base_path, exist_ok=True)
    with open(os.path.join(base_path, ".notified_stages.json"), "w") as f:
        json.dump({"notified": [], "total_messages_sent": 0}, f)
    with open(os.path.join(base_path, ".cron_run_count"), "w") as f:
        json.dump({"count": 0, "max_runs": 20, "run_start_at": "PENDING"}, f)

    # Step 5: 构建 orchestrator prompt（替换占位符）
    orchestrator_prompt = (
        _ORCHESTRATOR_PROMPT_TEMPLATE
        .replace("__SESSION_ID__", session_id)
        .replace("__BASE_PATH__", base_path)
        .replace("__MODE__", mode)
        .replace("__QUERY__", query)
    )

    # Step 6: 根据模式决定超时时间
    timeout_seconds = 1800 if mode == "standard" else 600

    return {
        "session_id": session_id,
        "base_path": base_path,
        "plan_path": plan_path,
        "analysis_plan": init_result.get("analysis_plan", {}),
        "spawn_params": {
            "runtime": "subagent",
            "mode": "run",
            "label": "research_pro_orchestrator",
            "task": orchestrator_prompt,
            "runTimeoutSeconds": timeout_seconds,
        },
    }
