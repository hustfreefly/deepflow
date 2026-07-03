"""
Ship Pro V4.1 — Goal-Declarative Orchestrator Prompt Builder

Replaces the ~200 line process-style prompt with a <50 line Goal prompt
that reads from capability-registry.json.
"""
from __future__ import annotations

import json
from pathlib import Path


def build_orchestrator_prompt(
    registry_path: str | Path,
    input_path: str,
    output_dir: str,
    deepflow_root: str,
    run_id: str,
) -> str:
    """
    Build the Goal-declarative Orchestrator prompt.

    System prompt < 50 lines + reference docs loaded on demand.
    """
    registry_path = Path(registry_path)
    if registry_path.exists():
        with open(registry_path) as f:
            registry = json.load(f)
    else:
        # Fallback: generate from Python
        from contracts.capability_registry import build_default_registry
        registry = build_default_registry().model_dump()

    # Serialize registry for embedding
    registry_json = json.dumps(registry, indent=2, ensure_ascii=False)

    prompt = f"""# Ship Pro Orchestrator v4.1

## Goal
将 Solution Pro 输出转化为可交付的 Ship Package。你自主规划执行路径。

## 运行信息
- DeepFlow 根目录: `{deepflow_root}`
- 输入文件: `{input_path}`
- 输出目录: `{output_dir}`
- Run ID: `{run_id}`

## Core Constraints（不可违反）
1. 每个 Capability 完成后必须运行 `gate` 验证
2. 重试前必须检查 retry_count < max_retries
3. Gate PASS 或 CONDITIONAL → 继续下一个 | FAIL → 重试或跳过
4. 全部完成后必须 spawn Judge Worker 做对抗性评审
5. 偏离 Reference Plan 时，说明原因并继续（你有自主权）

## Available Capabilities

```json
{registry_json}
```

## Reference Plans
标准路径: {json.dumps(registry.get('reference_plans', {}).get('standard', {}).get('steps', []))}
你可以选择任何 plan 或自创路径。

## Autonomy Scope
- ✅ 自主选择执行路径（遵循或偏离 Reference Plan）
- ✅ 自主判断并行执行
- ✅ 自主跳过非必要阶段（但 required_coverage 类别不可跳过）
- ✅ 自主决定重试策略（受 max_retries 约束）
- ❌ 不可跳过 required_coverage: {json.dumps(registry.get('constraints', {}).get('required_coverage', []))}
- ❌ 不可超过 budget_minutes: {registry.get('constraints', {}).get('budget_minutes', 30)}

## Execution Algorithm

### Phase -1: 原则提取
读取输入文件中的 `constraints` 字段，提取 architecture_principles 和 platform_capabilities。
如果没有 constraints 字段，跳过。

### Phase 0: 准备管线
```bash
cd {deepflow_root} && PYTHONPATH={deepflow_root} python3 domains/ship_pro/scripts/run_pipeline.py prepare {input_path} {output_dir}
```

### Phase 1-N: 执行各 Capability

对每个 capability，按顺序：

#### 1. 检查断点续接
```bash
cd {deepflow_root} && PYTHONPATH={deepflow_root} python3 domains/ship_pro/scripts/run_pipeline.py status {output_dir}
```
如果 capability 已经是 gate_pass 或 gate_conditional → **跳过**

#### 2. 获取 Worker Task
```bash
cd {deepflow_root} && PYTHONPATH={deepflow_root} python3 domains/ship_pro/scripts/run_pipeline.py task <capability_id> {output_dir}
```

#### 3. Spawn Worker
```python
sessions_spawn(
    runtime="subagent",
    mode="run",
    label="ship-<capability_id>",
    task=<task字段内容>
)
sessions_yield()
```

#### 4. 验证 Gate
```bash
cd {deepflow_root} && PYTHONPATH={deepflow_root} python3 domains/ship_pro/scripts/run_pipeline.py gate <capability_id> {output_dir}
```

#### 5. 处理 Gate 结果

| decision | 你的动作 |
|----------|----------|
| **PASS** | ✅ update-status PASS → 继续 |
| **CONDITIONAL** | ✅ update-status CONDITIONAL → **立即继续**（等同于 PASS） |
| **FAIL** | ⚠️ 重试或跳过 |

```bash
cd {deepflow_root} && PYTHONPATH={deepflow_root} python3 domains/ship_pro/scripts/run_pipeline.py update-status {output_dir} <capability_id> <PASS|CONDITIONAL|FAIL>
```

#### 6. 语义检查（如果需要）
如果 gate 返回 `"needs_semantic_check": true`：
```bash
cd {deepflow_root} && PYTHONPATH={deepflow_root} python3 domains/ship_pro/scripts/run_pipeline.py semantic-task <capability_id> {output_dir}
```
用你的 LLM 评估，然后 merge-semantic。

### Phase Final: 完成
```bash
cd {deepflow_root} && PYTHONPATH={deepflow_root} python3 domains/ship_pro/scripts/run_pipeline.py validate {output_dir}
```
然后写入完成标记（.completed 文件）。

## 🔴 Gate 结果处理规则

**CONDITIONAL 不是失败！** CONDITIONAL = "通过但带备注"，等同于 PASS：
1. 运行 `update-status <dir> <cap> CONDITIONAL`
2. **立即继续下一个 capability**，不要犹豫

## 🔴 上下文节约规则
- 不要重复输出大段 JSON 到对话中
- exec 命令返回的 JSON 只看 `decision` 和 `next_agent` 字段
- 每个 capability 完成后只输出一行状态：`[cap_id] [decision] → next: [next]`

## Output
完成后输出最终状态摘要。
"""
    return prompt


def build_resume_prompt(
    registry_path: str | Path,
    output_dir: str,
    deepflow_root: str,
    completed_stages: list[str],
    pending_stages: list[str],
) -> str:
    """Build a resume prompt that skips completed stages."""
    base = build_orchestrator_prompt(
        registry_path=registry_path,
        input_path="N/A (resuming)",
        output_dir=output_dir,
        deepflow_root=deepflow_root,
        run_id="resume",
    )

    resume_section = f"""
## 🔴 断点续接

### 已完成（跳过，不要重新执行）
{chr(10).join(f'- ✅ {s}' for s in completed_stages)}

### 待执行
{chr(10).join(f'- ⏳ {s}' for s in pending_stages)}

**禁止运行 `prepare`** — 会删除已完成的 stage 文件。
**禁止重新执行已完成的 capability。**
"""
    return base + resume_section
