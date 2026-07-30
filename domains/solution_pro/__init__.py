"""
Solution Pro 模块入口

Version: 3.0.0
Date: 2026-07-14

3.0.0: 单一路径架构（Agent Orchestrator + Python 契约后置验证）
       删除双路径 + 删除降级机制。
       唯一路径：Agent Orchestrator（sessions_spawn）。
       Python 契约笼子由 Module Agent 在 exec 中调用 orchestrator.run() 触发。
       后置验证由 post_validator.py 在 Agent 完成后执行。

## 唯一入口

```python
from domains.solution_pro import run_solution_pro
result = run_solution_pro(user_input="...", topic="...", ...)
sessions_spawn(**result["spawn_params"])
```

- **run_solution_pro**: Agent Orchestrator 路径
  - 入口：run_solution_pro(user_input, **kwargs)
  - 架构：Orchestrator Agent → spawn 3 Module Agents → 各 Module 调用 Python orchestrator.run()
  - 后置验证：Agent 完成后 post_validator.py 检查输出质量
"""

import sys as _sys; _p=__import__('pathlib').Path(__file__).resolve(); _r=next((d for d in _p.parents if (d/'core'/'blackboard').is_dir()),None); _sys.path.insert(0,str(_r)) if _r and str(_r) not in _sys.path else None  # 契约笼子: 自动发现 .deepflow 根目录
import json
import os
import pathlib
from datetime import datetime, timezone
from typing import Optional  # 契约笼子：_try_load_handoff_package 返回类型
from core.blackboard.context_injector import build_bootstrap_task
from core.prompt_utils import render_prompt  # V4: 集成 PromptUtils
from pathlib import Path

from .blackboard import BlackboardManager




# Track B（2026-07-29）: _extract_requirements_from_input() 已物理删除。
# 根因：纯正则语义提取，丢失标题要素（CoWoS-L/PDK驱动型/两年路线图）。
# AI Native 铁律：语义提取禁止正则。需求必须来自 Spec Pro living_spec。


def _try_load_handoff_package(bm: BlackboardManager) -> Optional[dict]:
    """从 blackboard 加载 Spec Pro 的 handoff package（ADR-009 P1: MD 唯一版）。

    ADR-009 P1（2026-07-12）：MD 唯一架构
      必须从 living_spec.md 读取（parse_living_spec_md）。
      MD 不可用 → raise ValueError（不再 fallback 到 JSON）。

    契约笼子：
      Pydantic 验证 handoff_allowed + gate 结果。
      handoff_allowed=False → raise ValueError。
      MD 不可用 → raise ValueError（不可信的约束不是约束）。

    Returns:
        living_spec dict（仅从 MD parse）

    Raises:
        ValueError: handoff_allowed=False / 契约验证失败 / MD 不可用
    """
    import glob
    import logging as _logging
    _logger = _logging.getLogger(__name__)

    from contracts.shared.handoff_contract import HandoffPackage

    # 扫描最新的 spec_handoff_package.json
    blackboard_root = bm._base
    pattern = str(blackboard_root / "*" / "spec" / "spec_handoff_package.json")
    candidates = sorted(glob.glob(pattern), key=lambda p: Path(p).stat().st_mtime, reverse=True)

    if not candidates:
        return None

    # 读取 + Pydantic 验证
    latest_path = Path(candidates[0])
    with open(latest_path, "r", encoding="utf-8") as f:
        raw_package = json.load(f)

    try:
        package = HandoffPackage(**raw_package)
    except Exception as e:
        raise ValueError(
            f"handoff package 契约验证失败 ({latest_path}): {e}"
        ) from e

    # 契约铁律：handoff_allowed=False → 阻断
    if not package.handoff_allowed:
        raise ValueError(
            f"Spec Pro handoff 被拒绝: block_reason={package.block_reason}"
        )

    # ── ADR-009 P1: MD 唯一（不可信的约束不是约束） ──
    md_path_str = raw_package.get("living_spec_md_path")
    if not md_path_str:
        raise ValueError(
            f"ADR-009 契约违反: handoff package 缺少 living_spec_md_path。"
            f"Root cause: save_handoff_package() MD 渲染失败或未执行。"
            f"Package: {latest_path}"
        )

    md_path = Path(md_path_str)
    if not md_path.exists():
        raise ValueError(
            f"ADR-009 契约违反: living_spec.md 文件缺失 ({md_path})。"
            f"Root cause: save_handoff_package() 写入失败或文件被删除。"
        )

    from domains.spec_pro.spec_living_md import parse_living_spec_md
    md_content = md_path.read_text(encoding="utf-8")
    living_spec = parse_living_spec_md(md_content)
    _logger.info(
        f"ADR-009: living_spec loaded from MD ({len(md_content)} chars, "
        f"{len(living_spec.get('confirmed', {}))} confirmed keys)"
    )
    return living_spec


def run_solution_pro(user_input: str, **kwargs):
    """
    Solution Pro 2.0.0 入口（Agent-centric 架构）

    初始化 Blackboard + frozen_spec，生成 Orchestrator prompt，
    返回 spawn_params 供主 Agent 调用 sessions_spawn 启动管线。

    架构：
      Main Agent (depth-0)
        → sessions_spawn → Orchestrator (depth-1)
          → sessions_spawn → Module Agents (depth-2)
            → sessions_spawn → Workers (depth-3)

    Args:
        user_input: 用户输入（需求描述）
        **kwargs: topic, solution_type, mode, domain, constraints, stakeholders,
                  living_spec（Spec Pro 桥接）

    Returns:
        {"session_id": str, "base_path": str, "spawn_params": dict}

    Raises:
        ValueError: user_input 为空/None/纯空白；living_spec 缺失；requirement_index 为空
    """
    # ── P0-2a: 输入校验（必须在任何副作用之前） ──
    # 用户铁律：缺输入必须 raise，禁止静默降级
    if user_input is None:
        raise ValueError(
            "user_input 为 None。Solution Pro 需要非空的需求描述作为输入。"
        )
    if not isinstance(user_input, str):
        raise ValueError(
            f"user_input 必须是 str，实际类型: {type(user_input).__name__}"
        )
    if not user_input.strip():
        raise ValueError(
            "user_input 为空字符串或纯空白。Solution Pro 需要非空的需求描述作为输入。"
        )

    # 1. 初始化 Blackboard session（仅设置路径，不创建目录）
    topic = kwargs.get("topic", user_input[:50])
    # 契约笼子（2026-07-05）：统一 blackboard 路径，走默认 .deepflow/blackboard/
    # 确保 Ship Pro 能从统一路径读取 Solution Pro 输出
    bm = BlackboardManager(topic)  # 删掉 base_dir= → 走 PathConfig 默认路径
    # P0-2b: init_session()（mkdir）延迟到所有校验完成后
    session_id = bm.session_id
    session_dir = str(bm.session_dir)

    # 2. ADR-009 Phase 3: 从 living_spec 直接读取 requirement_index
    #    frozen_spec.py 已废弃（DEPRECATED），不再生成 frozen_spec
    #    requirement_index 由 spec_pro/coordinator.py 在 _write_living_spec() 中生成
    living_spec = kwargs.get("living_spec")

    # 契约笼子（2026-07-06）：handoff package 消费逻辑
    if living_spec is None:
        living_spec = _try_load_handoff_package(bm)

    # ADR-009 Phase 3: requirement_index 已在 living_spec 中（由 spec_pro 生成）
    # 契约笼子: living_spec 必须包含 requirement_index，否则 raise
    requirement_index = living_spec.get("requirement_index", []) if isinstance(living_spec, dict) else []
    # Track B 契约铁律（2026-07-29）：living_spec 缺失或 requirement_index 为空 → raise
    # 用户铁律：需求对齐是硬性要求，不存在降级或静默方案
    if not requirement_index:
        # 尝试从 living_spec 的 narrative/confirmed 结构化提取（非正则，是结构化数据提取）
        try:
            from domains.solution_pro.living_spec import generate_requirement_index
            requirement_index = generate_requirement_index(living_spec or {})
        except Exception:
            requirement_index = []

    if not requirement_index:
        raise ValueError(
            "Track B 契约铁律: living_spec.requirement_index 为空。\n"
            "禁止静默降级 — 需求对齐是硬性要求。\n"
            "根因: living_spec 未包含 requirement_index，且 generate_requirement_index() 未提取到需求。\n"
            "修复: 先运行 Spec Pro 生成 living_spec.md（含 requirement_index），"
            "或显式传递 living_spec 参数。\n"
            "注意: _extract_requirements_from_input() 已物理删除（纯正则语义提取，"
            "丢失标题要素）。禁止用正则从原始输入提取需求。"
        )

    # ── P0-2b: 所有校验通过，现在才创建目录 ──
    # mkdir 副作用必须在决策/校验完成后（历史教训：决策被拒绝时不得留下空目录）
    bm.init_session()

    # ── ADR-009 Phase 3: MD 主写入（frozen_spec）──
    # MD 是真相源，JSON 衍生品已删除（双写 → 单写）
    # B1-FIX: semantic_anchors 从 living_spec 透传（pipeline_designer.py:169 契约笼子要求）
    _semantic_anchors = (
        living_spec.get("semantic_anchors", [])
        if isinstance(living_spec, dict) else []
    )
    # D-6-FIX: guardrails 和 solution_pro_hints 从 living_spec 透传
    _guardrails = (
        living_spec.get("guardrails", {})
        if isinstance(living_spec, dict) else {}
    )
    # Phase 3 迁移完成：删除 frozen_spec 生成，Ship Pro 直接读 living_spec.md
    # frozen_spec 是中间产物，living_spec 已包含所有必需信息
    # 契约笼子：Ship Pro 验证 living_spec 必需字段（requirement_index, semantic_anchors, guardrails）
    
    _solution_pro_hints = (
        living_spec.get("solution_pro_hints", {})
        if isinstance(living_spec, dict) else {}
    )
    
    # 确保 living_spec 包含 Ship Pro 必需的字段
    if isinstance(living_spec, dict):
        # 注入 semantic_anchors（如果缺失）
        if "semantic_anchors" not in living_spec:
            living_spec["semantic_anchors"] = _semantic_anchors
        # 注入 guardrails（如果缺失）
        if "guardrails" not in living_spec:
            living_spec["guardrails"] = _guardrails
        # 注入 solution_pro_hints（如果缺失）
        if "solution_pro_hints" not in living_spec:
            living_spec["solution_pro_hints"] = _solution_pro_hints
    
    # MD 主写入：living_spec.md 是 Ship Pro 的唯一输入
    from domains.spec_pro.spec_living_md import render_living_spec_md
    living_spec_md = render_living_spec_md(living_spec)  # raise on failure
    bm.write("data/living_spec.md", living_spec_md)

    # 3. 清理旧文件（断点续跑时防止误判）
    for old_file in [".completed"]:
        old_path = bm.session_dir / old_file
        if old_path.exists():
            old_path.unlink()

    # 5. V3.1 架构：Orchestrator Agent（depth-1）直接 spawn Module Agents
    #    Orchestrator 读取 orchestrator.md，按 Planning → Research → Summary 顺序执行
    #    每个 Module Agent（depth-2）直接通过 sessions_spawn 创建 Workers（depth-3）
    deepflow_root = str(Path(__file__).resolve().parent.parent.parent)

    # 5a. V4: 使用 PromptUtils 渲染 orchestrator.md
    orchestrator_prompt_path = pathlib.Path(__file__).parent / "prompts" / "orchestrator.md"
    render_result = render_prompt(
        orchestrator_prompt_path,
        session_id=session_id,
        deepflow_root=deepflow_root,
    )
    orchestrator_prompt = render_result.content

    # 5b. 写入 blackboard（供 Orchestrator 读取）
    bm.write("orchestrator_prompt.md", orchestrator_prompt, subdir="stages")

    # 6. 返回 spawn_params
    #    主 Agent 执行：sessions_spawn(**result["spawn_params"])
    #
    # 🔴 FixFlow V3.4（2026-07-26）：task 改为最小引用（读文件模式）
    #    根因：完整 orchestrator_prompt 约 28KB，超过 sessions_spawn task 限制后被截断，
    #    导致 Orchestrator 只收到前 2/3 指令（Planning + Research），Step 3/4/5 被截掉。
    #    修复：task 只传最小引用，让 Orchestrator 自己读 blackboard 中的文件。
    import logging as _logging
    _logging.getLogger(__name__).info(
        f"run_solution_pro: session={session_id}, V3.2 Orchestrator path"
    )
    
    # 最小引用 task（~350 chars），不塞完整 prompt
    # 根因：task 超过 ~500 chars 会被截断，导致 Orchestrator 只收到部分指令
    # 修复：task 只传最小引用（session_id + 读文件指令），完整指令在 orchestrator_prompt.md 中
    minimal_task = (
        f"## 你的任务\n"
        f"读取文件并执行其中的指令。\n\n"
        f"文件路径: `{session_dir}/stages/orchestrator_prompt.md`\n\n"
        f"用 read 工具读取这个文件，然后严格按照文件内容执行所有步骤。\n"
        f"如果文件不存在 → 用 write 工具写入 `{session_dir}/stages/.failed` 并立即结束。"
    )
    
    return {
        "session_id": session_id,
        "base_path": session_dir,
        "execution_path": "v3.2_orchestrator",
        "spawn_params": {
            "runtime": "subagent",
            "mode": "run",
            "label": "solution_orchestrator",
            "task": minimal_task,
            "cwd": deepflow_root,
            "lightContext": True,
        },
    }


# ============================================================================
# ADR-009: Track Generation
# ============================================================================

def generate_solution_track(base_path: str) -> dict | None:
    """
    ADR-009: 从 final_solution.md 生成 solution_track.json。

    在 Solution Pro Orchestrator 完成后调用（通过 exec 或 post-completion hook）。
    非阻断：任何步骤失败 → log warning，返回 None。

    Args:
        base_path: Solution Pro session 目录（blackboard/{session_id}/）

    Returns:
        track_data dict if successful, None if failed
    """
    import logging
    from pathlib import Path as _Path

    logger = logging.getLogger(__name__)
    try:
        from core.track_generator import generate_track_from_md
    except ImportError:
        logger.info("ADR-009: track_generator not available, skipping")
        return None

    base = _Path(base_path)
    # Try stages/final_solution.md first (sidecar), then root final_solution.md
    md_path = base / "stages" / "final_solution.md"
    if not md_path.exists():
        md_path = base / "final_solution.md"
    if not md_path.exists():
        logger.warning(f"ADR-009: final_solution.md not found in {base_path}")
        return None

    return generate_track_from_md(
        md_path=md_path,
        domain="solution_pro",
        output_path=base / "solution_track.json",
    )


# ============================================================================
# ADR-009: MD-First Rendering (Unified Fallback)
# ============================================================================

def render_solution_md(session_id: str, base_dir: str = None) -> dict:
    """
    ADR-009 Phase 3: MD 主写入 — 渲染 Solution Pro 的所有 MD 产物。

    在 pipeline 完成后调用（pulse.py 自动调用，也可手动调用）。
    Phase 3 翻转：MD render 失败 → raise ValueError（不再静默跳过）。

    Args:
        session_id: Solution Pro session ID
        base_dir: Blackboard 根目录（可选）

    Returns:
        {"final_solution_md": bool, "solution_document_md": bool} 渲染结果

    Raises:
        ValueError: MD 渲染失败（ADR-009 契约违反）
    """
    from domains.solution_pro.solution_living_md import render_final_solution_md
    from domains.solution_pro.blackboard import BlackboardManager

    bm = BlackboardManager(session_id, base_dir=base_dir)
    results = {"final_solution_md": False, "solution_document_md": False}

    # 1. final_solution.md — MD 主写入
    final_solution_data = bm.read_stage('final_solution')
    if final_solution_data:
        if isinstance(final_solution_data, str):
            # 已经是 MD（Phase 4+ Agent 直接写 MD）
            final_solution_md = final_solution_data
        else:
            # dict → MD 渲染（render 失败 → raise，不捕获）
            final_solution_md = render_final_solution_md(final_solution_data)
        bm.write_stage('final_solution', final_solution_md)  # MD 真相源
        results['final_solution_md'] = True

    # 2. solution_document.md — MD 主写入
    solution_document_data = bm.read_stage('solution_document')
    if solution_document_data:
        if isinstance(solution_document_data, str):
            # 已经是 MD（Agent 直接写 MD）
            solution_document_md = solution_document_data
        else:
            # dict → 不静默降级，raise 明确错误
            raise ValueError(
                "ADR-009 契约违反: solution_document 是 dict，缺少 MD renderer。"
                "Phase 4+ Agent 应直接写 MD（str），不应写 dict。"
            )
        bm.write_stage('solution_document', solution_document_md)  # MD 真相源
        results['solution_document_md'] = True

    return results


# 契约笼子（2026-07-14）：显式导出
__all__ = ['run_solution_pro', 'generate_solution_track', 'render_solution_md']