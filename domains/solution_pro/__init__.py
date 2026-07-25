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
from pathlib import Path

from .blackboard import BlackboardManager




def _extract_requirements_from_input(user_input: str) -> list:
    """从 user_input 文本确定性提取需求列表（Fallback 路径）。

    适用场景: 用户未经 Spec Pro 直接调用 Solution Pro 时，
    从 Markdown 编号列表中提取需求。

    格式提取（确定性，不做语义判断）:
      - 查找 '## Requirements' 段
      - 提取编号列表（1. 2. 3. 或 - ）
      - 分配 REQ-INPUT-NNN 前缀

    Returns:
        requirement_index 列表（可能为空）
    """
    import re
    lines = user_input.split('\n')

    # 1. 尝试找 '## Requirements' 段落
    req_section_lines: list[str] = []
    in_req_section = False
    for line in lines:
        stripped = line.strip()
        if re.match(r'^##\s+[Rr]equirements?', stripped):
            in_req_section = True
            continue
        if in_req_section and stripped.startswith('## '):
            break  # 下一个 section
        if in_req_section:
            req_section_lines.append(stripped)

    # 如果没找到 Requirements section，用全文
    search_lines = req_section_lines if req_section_lines else [l.strip() for l in lines]

    # 2. 提取编号列表项
    requirements = []
    counter = 0
    for line in search_lines:
        # 匹配: 1. xxx, - xxx, * xxx
        match = re.match(r'^(?:\d+[.)\s]|[-*]\s+)(.+)', line)
        if match:
            text = match.group(1).strip()
            if len(text) >= 10:  # 过滤过短的项
                counter += 1
                requirements.append({
                    'id': f'REQ-INPUT-{counter:03d}',
                    'description': text,
                    'priority': 'MUST',
                    'source_section': 'user_input',
                    'category': 'FUNC',
                })

    return requirements


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
    """
    # 1. 初始化 Blackboard session
    topic = kwargs.get("topic", user_input[:50])
    # 契约笼子（2026-07-05）：统一 blackboard 路径，走默认 .deepflow/blackboard/
    # 确保 Ship Pro 能从统一路径读取 Solution Pro 输出
    bm = BlackboardManager(topic)  # 删掉 base_dir= → 走 PathConfig 默认路径
    bm.init_session()
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
    if not requirement_index:
        import logging
        _logger = logging.getLogger(__name__)
        _logger.warning(
            "ADR-009 Phase 3: living_spec.requirement_index 为空。"
            "尝试 fallback 生成..."
        )
        # Fallback 1: 从 living_spec 的 narrative/confirmed 提取
        try:
            from domains.solution_pro.living_spec import generate_requirement_index
            requirement_index = generate_requirement_index(living_spec or {})
        except Exception:
            requirement_index = []

        # Fallback 2 (L2): 从 user_input 文本确定性提取（Markdown 编号列表格式）
        if not requirement_index and user_input:
            requirement_index = _extract_requirements_from_input(user_input)

        # 契约铁律: 0 requirements = raise ValueError（不静默降级）
        if not requirement_index:
            raise ValueError(
                "ADR-009 契约违反: requirement_index 为空。\n"
                "根因: 以下三种路径均未产出需求:\n"
                "  1. living_spec.requirement_index 为空（Spec Pro 未生成）\n"
                "  2. generate_requirement_index(living_spec) 未提取到需求\n"
                "  3. _extract_requirements_from_input(user_input) 未提取到需求\n"
                "修复: 先运行 Spec Pro 生成 living_spec.md，或确保 user_input 包含编号需求列表。"
            )

    # 写入简化的 frozen_spec（含 requirement_index + requirements 兼容层）
    # CRITICAL #2: Ship Pro 期望 requirements 字段，同时保留 requirement_index 用于内部追踪
    # B1-FIX: semantic_anchors 从 living_spec 透传（pipeline_designer.py:169 契约笼子要求）
    _semantic_anchors = (
        living_spec.get("semantic_anchors", [])
        if isinstance(living_spec, dict) else []
    )
    frozen_spec = {
        "topic": topic,
        "requirement_index": requirement_index,
        "requirements": requirement_index,  # CRITICAL #2: Ship Pro 兼容层
        "semantic_anchors": _semantic_anchors,  # B1-FIX: Ship Pro 契约笼子要求
        "metadata": {
            "source": "spec_pro",
            "adr009_phase": 3,
            "generated_at": datetime.now().isoformat(),
        },
    }
    bm.write("data/frozen_spec.json", frozen_spec)

    # B2-FIX: Write FULL living_spec to blackboard (preserve narrative/confirmed/stakeholders/guardrails)
    # Previously only simplified frozen_spec was written, losing critical context.
    if isinstance(living_spec, dict) and living_spec:
        try:
            bm.write("data/living_spec.json", living_spec)
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                f"B2: Failed to write full living_spec.json: {e}"
            )

    # CRITICAL: Render frozen_spec.md for Ship Pro cross-domain consumption (ADR-009)
    # Ship Pro expects data/frozen_spec.md (MD source of truth), not JSON
    try:
        from domains.solution_pro.frozen_living_md import render_frozen_spec_md
        frozen_spec_md = render_frozen_spec_md(frozen_spec)
        bm.write("data/frozen_spec.md", frozen_spec_md)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"Failed to render frozen_spec.md (Ship Pro will fail): {e}"
        )

    # 3. 初始化 master_state
    bm.write("master_state.json", {
        "session_id": session_id,
        "status": "initialized",
        "current_module": None,
        "completed_modules": [],
        "failed_modules": [],
    })

    # 4. 清理旧文件（断点续跑时防止误判）
    for old_file in [".completed"]:
        old_path = bm.session_dir / old_file
        if old_path.exists():
            old_path.unlink()

    # 5. V3.1 架构：Orchestrator Agent（depth-1）直接 spawn Module Agents
    #    Orchestrator 读取 orchestrator.md，按 Planning → Research → Summary 顺序执行
    #    每个 Module Agent（depth-2）直接通过 sessions_spawn 创建 Workers（depth-3）
    deepflow_root = str(Path(__file__).resolve().parent.parent.parent)

    # 5a. 读取 orchestrator.md 模板并填充变量
    orchestrator_prompt_path = pathlib.Path(__file__).parent / "prompts" / "orchestrator.md"
    orchestrator_prompt = orchestrator_prompt_path.read_text(encoding="utf-8")
    orchestrator_prompt = (
        orchestrator_prompt
        .replace("{session_id}", session_id)
        .replace("{deepflow_root}", deepflow_root)
    )

    # 5b. 写入 blackboard（供 Orchestrator 读取）
    bm.write("orchestrator_prompt.md", orchestrator_prompt, subdir="stages")

    # 6. 返回 spawn_params
    #    主 Agent 执行：sessions_spawn(**result["spawn_params"]) → sessions_yield()
    import logging as _logging
    _logging.getLogger(__name__).info(
        f"run_solution_pro: session={session_id}, V3.1 Orchestrator path"
    )
    return {
        "session_id": session_id,
        "base_path": session_dir,
        "execution_path": "v3.1_orchestrator",
        "spawn_params": {
            "runtime": "subagent",
            "mode": "run",
            "label": "solution_orchestrator",
            "task": orchestrator_prompt,
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


# 契约笼子（2026-07-14）：显式导出
__all__ = ['run_solution_pro', 'generate_solution_track']