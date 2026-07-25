"""
Deliver Pro — 入口模块 (V2)

架构（对齐 Solution Pro / Ship Pro）:
  Main Agent (depth-0)
    → run_deliver_pro(project_name) → spawn_params
    → sessions_spawn(**spawn_params)              # 启动 Orchestrator Agent

  Orchestrator Agent (LLM, depth-1)              # prompts/deliver_orchestrator.md
    → exec: DeliverOrchestrator.drive_all()       # Python 辅助 (orchestrator.py)
    → spawn Phase Agents (并行)
    → sessions_yield()
    → loop 直到 all_done

  Phase Agents (LLM, depth-2)
    → Analyze / Workers / Validate / Package     # prompts/deliver_*.md

用法:
    from domains.deliver_pro import run_deliver_pro

    result = run_deliver_pro("my_project")
    sessions_spawn(**result["spawn_params"])      # 启动 Orchestrator Agent
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from domains.deliver_pro.contracts import WorkPackage
from domains.deliver_pro.wp_runner import DeliverWPRunner
from core.blackboard.context_injector import auto_bootstrap

logger = logging.getLogger(__name__)


# ============================================================================
# 路径常量
# ============================================================================

DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent
BLACKBOARD_ROOT = DEEPFLOW_ROOT / "blackboard"


# ============================================================================
# Ship Pro → Deliver Pro WorkPackage 适配层
# ============================================================================

def _infer_scenario(wp: dict) -> str:
    """从 WP 内容推断 scenario 类型

    推断逻辑：
    - 如果 WP 有 code_files 或 implementation 指示 → "code"
    - 如果 WP 是分析/调研/文档类 → "report"
    - 如果混合 → "mixed"
    - 默认 → "code"
    """
    description = (wp.get('description', '') or '').lower()
    deliverables = wp.get('deliverables', [])
    title = (wp.get('title', '') or '').lower()

    # 编程类信号
    code_signals = [
        '.py', '.js', '.ts', '.go', '.rs', '.java', '.c', '.cpp', '.h',
        '.rb', '.php', '.swift', '.kt', '.dart', '.sh', '.bash',
        'code', 'implementation', 'coding', 'programming', 'function',
        'class', 'module', 'api', 'endpoint', 'schema', 'database',
        'migration', 'deploy', 'docker', 'dockerfile', 'ci/cd',
        'unit test', 'unit_test', 'lint', 'refactor', 'bug fix',
    ]

    # 报告/分析类信号
    report_signals = [
        '.md', '.pdf', '.docx', '.txt', '.rst',
        'report', 'analysis', 'analyst', 'research', 'document',
        'write', 'writing', 'article', 'blog', 'summary',
        'review', 'audit', 'survey', 'evaluation', 'assessment',
        'recommendation', 'strategy', 'roadmap', 'planning',
    ]

    code_score = 0
    report_score = 0

    # 检查 title
    for sig in code_signals:
        if sig in title:
            code_score += 1
    for sig in report_signals:
        if sig in title:
            report_score += 1

    # 检查 description
    for sig in code_signals:
        if sig in description:
            code_score += 1
    for sig in report_signals:
        if sig in description:
            report_score += 1

    # 检查 deliverables
    for d in deliverables:
        d_lower = (d or '').lower()
        for sig in code_signals:
            if sig in d_lower:
                code_score += 1
        for sig in report_signals:
            if sig in d_lower:
                report_score += 1

    if code_score > 0 and report_score == 0:
        return "code"
    elif report_score > 0 and code_score == 0:
        return "report"
    elif code_score > 0 and report_score > 0:
        return "mixed"
    else:
        # 无明确信号，默认 code
        return "code"


def _adapt_ship_pro_wp(wp: dict, package_semantic_anchors: list | None = None) -> dict:
    """Ship Pro WorkPackage dict → Deliver Pro WorkPackage 适配层
    
    Ship Pro 的 WorkPackage 使用 description/acceptance_criteria List[str] 等字段，
    Deliver Pro 的 WorkPackage 使用 objective/acceptance_criteria List[AcceptanceCriterion]。
    此适配器负责字段映射，确保跨域契约兼容。

    Args:
        wp: Ship Pro 格式的单个 WP dict
        package_semantic_anchors: Ship Pro 包级 semantic_anchors（fallback）
                                  Ship Pro 将 semantic_anchors 放在 ship_package 顶层，
                                  而非每个 WP 内。若 WP 自身无 anchors，则从此参数取。
    """
    # 推断 scenario 类型
    scenario = _infer_scenario(wp)

    # 先尝试 WP-level，再 fallback 到 package-level
    # Ship Pro 将 semantic_anchors 放在 ship_package 顶层（非每个 WP），
    # 所以单个 WP dict 的 wp.get("semantic_anchors") 通常为空列表。
    semantic_anchors = wp.get("semantic_anchors", [])
    if not semantic_anchors and package_semantic_anchors:
        semantic_anchors = package_semantic_anchors

    # FixFlow R11: 字符串 anchors → 字典 anchors（ship_track.json 产出的是字符串列表）
    # WorkPackage Pydantic 模型要求 List[dict]，不是 List[str]
    if semantic_anchors and isinstance(semantic_anchors[0], str):
        semantic_anchors = [
            {"name": a, "category": "TECHNICAL", "constraint": a, "source": "ship_pro"}
            for a in semantic_anchors
        ]

    # 透传 serving_principles（含 obligation + anti_patterns）
    serving_principles = wp.get("serving_principles", [])

    adapted = {
        'wp_id': wp.get('wp_id') or wp.get('id', ''),
        'title': wp.get('title', ''),
        'objective': wp.get('description', ''),  # Ship description → Deliver objective
        'scenario': scenario,
        'acceptance_criteria': [
            {'id': f'AC-{i+1}', 'description': ac, 'priority': 'must'}
            for i, ac in enumerate(wp.get('acceptance_criteria', []))
        ],  # List[str] → List[AcceptanceCriterion]
        'constraints': {},
        'dependencies': wp.get('dependencies', []),
        'context': {
            'effort_hours': wp.get('effort_hours'),
            'covered_req_ids': wp.get('covered_req_ids', []),
            'anchored_to': wp.get('anchored_to', []),
            'deliverables': wp.get('deliverables', []),
            'source_worker': wp.get('source_worker'),
        },
        'semantic_anchors': semantic_anchors,
        'serving_principles': serving_principles,
    }
    return adapted


# ============================================================================
# 唯一入口（V2: 薄层 LLM Orchestrator + Python DeliverOrchestrator）
# ============================================================================

def run_deliver_pro(
    project_name: str,
    **kwargs,
) -> dict:
    """
    Deliver Pro 唯一入口（V2: 对齐 Solution Pro / Ship Pro 架构）。

    架构:
      Main Agent (depth-0)
        → sessions_spawn → Orchestrator Agent (LLM, depth-1)
          → exec: DeliverOrchestrator.drive_all() (Python)
          → spawn Phase Agents → yield → loop

    与 run_solution_pro() / run_ship_pro() 命名规则统一:
      - 返回 spawn_params → Main Agent 直接传给 sessions_spawn
      - Orchestrator Agent 是薄层调度器（~68 行 prompt）
      - DeliverOrchestrator (Python) 是辅助工具

    Args:
        project_name: 项目名称（blackboard 目录名）
        **kwargs: 额外参数（预留扩展）

    Returns:
        {
            "project_name": str,
            "blackboard_path": str,
            "spawn_params": dict,  # Main Agent 直接传给 sessions_spawn
        }

    Raises:
        FileNotFoundError: ship_package.json 不存在
    """
    # V2: 薄层 LLM Orchestrator + Python DeliverOrchestrator
    # 对齐 Solution Pro / Ship Pro 架构:
    #   run_solution_pro() → spawn_params (Orchestrator Agent, LLM)
    #   run_ship_pro()     → spawn_params (Dispatcher Agent, LLM)
    #   run_deliver_pro()  → spawn_params (Orchestrator Agent, LLM)  ← 这里

    # 0. Sanitize project_name: 防止路径穿越
    project_name = project_name.replace("/", "_").replace("\\", "_").replace("..", "_")

    # 1. 验证 Ship Pro 产出存在
    blackboard_path = BLACKBOARD_ROOT / project_name
    ship_pkg = blackboard_path / "ship_pro" / "ship_package.json"
    if not ship_pkg.exists():
        ship_pkg = blackboard_path / "ship_pro" / "ship_track.json"
    if not ship_pkg.exists():
        raise FileNotFoundError(
            f"Deliver Pro 无法启动: ship_package.json 不存在\n"
            f"  搜索路径: {blackboard_path}/ship_pro/\n"
            f"  请先确保 Ship Pro 已完成并产出 ship_package.json"
        )

    # 2. 读取薄层 Orchestrator prompt
    deepflow_root = str(DEEPFLOW_ROOT)
    prompt_path = DEEPFLOW_ROOT / "domains" / "deliver_pro" / "prompts" / "deliver_orchestrator.md"
    orchestrator_prompt = prompt_path.read_text(encoding="utf-8")

    # 3. 注入运行时变量
    orchestrator_prompt = orchestrator_prompt.replace("{deepflow_root}", deepflow_root)
    orchestrator_prompt = orchestrator_prompt.replace("{project_name}", project_name)

    # 4. Bootstrap（解决 sessions_spawn 8KB 截断）
    from core.blackboard.context_injector import auto_bootstrap
    deliver_pro_dir = blackboard_path / "deliver_pro"
    deliver_pro_dir.mkdir(parents=True, exist_ok=True)
    bootstrap_task = auto_bootstrap(
        deepflow_root=Path(deepflow_root),
        prompt_dir=deliver_pro_dir / "stages",
        task_content=orchestrator_prompt,
        label="deliver_orchestrator",
    )

    # 5. 返回 spawn_params（与 run_solution_pro / run_ship_pro 统一）
    result = {
        "project_name": project_name,
        "blackboard_path": str(blackboard_path),
        "deliver_pro_dir": str(deliver_pro_dir),
        "spawn_params": {
            "runtime": "subagent",
            "mode": "run",
            "label": f"deliver-orchestrator-{project_name[:20]}",
            "task": bootstrap_task,
            "cwd": deepflow_root,
            "lightContext": True,
        },
    }

    logger.info(
        f"run_deliver_pro: project={project_name}, "
        f"prompt={len(orchestrator_prompt)} chars, "
        f"spawn_params ready"
    )
    return result


# ============================================================================
# 已删除的旧函数（V2 架构不再需要）
# ============================================================================
#
# _build_orchestrator_prompt() — 旧的厚层 Orchestrator prompt（内嵌构建）
#   已替换为 prompts/deliver_orchestrator.md（薄层，~68 行）
#
# get_orchestrator() — 旧的 per-WP Orchestrator 获取函数
#   已替换为 DeliverOrchestrator (orchestrator.py) 项目级调度
#
