"""
Deliver Pro — 入口模块 (V3: Pulse 脉冲调度，唯一生产路径)

架构（Pulse V1.2，2026-07-24 验证 26/26 WP 零干预）:
  cron 每 5min 点火 isolated session
    → pulse_cli.py pulse --project X
    → DeliverOrchestrator.pulse() 单次全量扫描
    → 动作契约落盘 _pulse_actions.json → spawn + confirm 回执
    → session 结束（不依赖 session 长寿 / 事件投递）

⚠️ V2 LLM Orchestrator 模式（drive_all）已于 2026-07-28 禁用：
  - 根因: LLM 调度绕过并发控制（17 children）+ 上下文遗忘导致重复 spawn
  - 详见 blackboard/2.5D封装设计团队组建/GLOBAL_ANALYSIS.md
  - 紧急回退: DEEPFLOW_ALLOW_DRIVE_ALL=1（仅测试/审计用）

用法:
    # 生产路径（唯一允许）
    python3 -m domains.deliver_pro.pulse_cli pulse --project "my_project"

    # 入口函数（返回 Pulse 启动信息，不再返回 LLM spawn_params）
    from domains.deliver_pro import run_deliver_pro
    result = run_deliver_pro("my_project")  # mode="pulse" 默认
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from domains.deliver_pro.contracts import WorkPackage
from domains.deliver_pro.wp_runner import DeliverWPRunner

logger = logging.getLogger(__name__)


# ============================================================================
# 路径常量
# ============================================================================

DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent
BLACKBOARD_ROOT = DEEPFLOW_ROOT / "blackboard"


def find_ship_package_path(project_name: str) -> Path:
    """查找 Ship Pro 产出的可执行 WorkPackage 包。

    只接受 ship_package.md/json（包含 work_packages），不接受 ship_track.json：
    track 是跨域元数据，不包含可调度 WP 列表。

    查找顺序：
      1. ship_pro/ship_package.{md,json}（canonical）
      2. ship_pro/stages/ship_package.{md,json}（旧 canonical）
      3. ship_pro_<run_id>/stages/ship_package.{md,json}（run_id 隔离目录）
    """
    safe_project = project_name.replace("/", "_").replace("\\", "_").replace("..", "_")
    project_dir = BLACKBOARD_ROOT / safe_project

    candidates = [
        project_dir / "ship_pro" / "ship_package.md",
        project_dir / "ship_pro" / "ship_package.json",
        project_dir / "ship_pro" / "stages" / "ship_package.md",
        project_dir / "ship_pro" / "stages" / "ship_package.json",
    ]
    for path in candidates:
        if path.exists():
            return path

    run_candidates = sorted(
        list(project_dir.glob("ship_pro_*/stages/ship_package.md"))
        + list(project_dir.glob("ship_pro_*/stages/ship_package.json")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in run_candidates:
        if path.exists():
            return path

    searched = [str(p) for p in candidates] + [str(project_dir / "ship_pro_*/stages/ship_package.{md,json}")]
    raise FileNotFoundError(
        "Ship Pro package 不存在（需要包含 work_packages 的 ship_package.md/json）。\n"
        f"  搜索路径: {searched}"
    )


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


def _adapt_ship_pro_wp(wp: dict, package_semantic_anchors: list | None = None,
                       package_serving_principles: list | None = None) -> dict:
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
    # W4-F4: WP-level 优先，包级 fallback（与 semantic_anchors 同款模式）
    serving_principles = wp.get("serving_principles", [])
    if not serving_principles and package_serving_principles:
        serving_principles = package_serving_principles

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
# 唯一入口（V3: Pulse 脉冲调度，契约笼子强制）
# ============================================================================

def run_deliver_pro(
    project_name: str,
    mode: str = "pulse",
    **kwargs,
) -> dict:
    """
    Deliver Pro 唯一入口（V3: Pulse 脉冲调度）。

    架构（Pulse V1.2，26/26 WP 零干预验证）:
      cron 每 5min 点火 → pulse_cli.py pulse --project X
        → DeliverOrchestrator.pulse() 单次扫描 → 契约落盘 → spawn+confirm

    ⚠️ V2 LLM Orchestrator（drive_all）已于 2026-07-28 禁用。
       根因: 17 并发失控 + 重复 spawn（详见 GLOBAL_ANALYSIS.md）。

    Args:
        project_name: 项目名称（blackboard 目录名）
        mode: 调度模式。唯一允许 "pulse"。契约笼子：非 pulse → ValueError。
        **kwargs: 预留扩展

    Returns:
        {
            "project_name": str,
            "blackboard_path": str,
            "mode": "pulse",
            "launch_command": str,   # Pulse CLI 启动命令
            "cron_hint": str,        # cron 注册提示
        }

    Raises:
        ValueError: mode != "pulse"（契约违例）
        FileNotFoundError: ship_package.json 不存在
    """
    # 契约笼子：project_name 入口校验（P0-7）
    if not project_name or not str(project_name).strip():
        raise ValueError(
            f"project_name 不能为空（收到: {project_name!r}）。"
            f" 要求: 非空字符串，纯空白也不行。"
        )

    # 契约笼子 Step 1: mode 硬约束（raise ValueError，不是建议性 warning）
    if mode != "pulse":
        raise ValueError(
            f"mode='{mode}' 已禁用（契约违例）。唯一允许模式: 'pulse'\n"
            f"  Pulse 调用: python3 -m domains.deliver_pro.pulse_cli pulse --project \"{project_name}\"\n"
            f"  背景: V2 LLM Orchestrator（drive_all）于 2026-07-28 禁用\n"
            f"        （17 并发失控 + 已完成 worker 重复 spawn）\n"
            f"  紧急回退（仅测试）: DEEPFLOW_ALLOW_DRIVE_ALL=1"
        )

    # 0. Sanitize project_name: 防止路径穿越
    project_name = project_name.replace("/", "_").replace("\\", "_").replace("..", "_")

    # 1. 验证 Ship Pro 产出存在（契约笼子：缺前置产出 → 硬报错，不静默降级）
    blackboard_path = BLACKBOARD_ROOT / project_name
    ship_pkg = find_ship_package_path(project_name)

    # 2. 返回 Pulse 启动信息（不再返回 LLM spawn_params —— 物理上消除误用可能）
    deepflow_root = str(DEEPFLOW_ROOT)
    result = {
        "project_name": project_name,
        "blackboard_path": str(blackboard_path),
        "ship_package_path": str(ship_pkg),
        "mode": "pulse",
        "launch_command": (
            f"cd {deepflow_root} && PYTHONPATH=. "
            f"python3 -m domains.deliver_pro.pulse_cli pulse --project \"{project_name}\""
        ),
        "cron_hint": (
            f"注册 cron 每 5min 点火: openclaw cron add "
            f"--schedule '*/5 * * * *' "
            f"--task 'cd {deepflow_root} && PYTHONPATH=. python3 -m domains.deliver_pro.pulse_cli pulse --project \"{project_name}\"'"
        ),
    }

    logger.info(
        f"run_deliver_pro: project={project_name}, mode=pulse, "
        f"launch_command ready"
    )
    return result


# ============================================================================
# 已删除的旧函数（V3 Pulse 架构不再需要）
# ============================================================================
#
# _build_orchestrator_prompt() — 旧的厚层 Orchestrator prompt（内嵌构建）
#   已随 V2 LLM Orchestrator 模式一并废弃（2026-07-28）
#
# get_orchestrator() — 旧的 per-WP Orchestrator 获取函数
#   已替换为 DeliverOrchestrator (orchestrator.py) 项目级调度
#
# V2 LLM Orchestrator spawn_params 返回 — 已废弃（2026-07-28）
#   根因: 17 并发失控 + 已完成 worker 重复 spawn
#   替代: Pulse 脉冲调度（pulse_cli.py pulse --project X）
#   prompts/deliver_orchestrator.md 已移至 prompts/_archive/
#
