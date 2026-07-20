"""
Deliver Pro — 入口模块

架构:
  Main Agent (depth-0)
    → exec: result = run_deliver_pro(wp=...)
    → sessions_spawn(**result["spawn_params"])   # 启动 Orchestrator Agent

  Orchestrator Agent (depth-1)
    → Phase 1-5 流水线（详见 orchestrator.py）

用法:
    from domains.deliver_pro import run_deliver_pro

    result = run_deliver_pro(wp=wp_dict, project_name="my_project")
    # result["spawn_params"] → 传给 sessions_spawn
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from domains.deliver_pro.contracts import WorkPackage
from domains.deliver_pro.orchestrator import DeliverProOrchestrator
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
# 唯一入口
# ============================================================================

def run_deliver_pro(
    wp: WorkPackage | dict,
    project_name: str | None = None,
    **kwargs,
) -> dict:
    """
    Deliver Pro V1 唯一入口。

    Args:
        wp: WorkPackage 对象或 dict（来自 Ship Pro）
        project_name: 项目名称（blackboard 目录名）
                      如不提供，从 wp.wp_id 生成
        **kwargs: 额外参数（预留扩展）

    Returns:
        {
            "project_name": str,
            "wp_id": str,
            "blackboard_path": str,
            "deliver_pro_dir": str,
            "spawn_params": dict,  # Main Agent 直接传给 sessions_spawn
        }

    Raises:
        ValueError: WP 验证失败
        FileNotFoundError: Blackboard 路径问题
    """
    # 1. 解析 WorkPackage（Ship Pro 格式自动适配）
    # P1-1: Extract ShipPackage top-level fields before WP adaptation
    ship_package_context = kwargs.pop('ship_package_context', None)
    if ship_package_context is None and isinstance(wp, dict):
        # Auto-extract ShipPackage fields if present in the dict
        _ship_fields = [
            'key_decisions', 'architecture', 'risk_summary',
            'implementation_phases', 'dependency_graph', 'anchor_coverage',
        ]
        _extracted = {k: wp[k] for k in _ship_fields if k in wp}
        if _extracted:
            ship_package_context = _extracted

    if isinstance(wp, dict):
        # 如果是 Ship Pro 格式的 WorkPackage，先适配
        if 'description' in wp and 'objective' not in wp:
            # 提取 package-level semantic_anchors（若传入）
            package_sa = kwargs.pop('semantic_anchors', None)
            wp = _adapt_ship_pro_wp(wp, package_semantic_anchors=package_sa)
        wp_obj = WorkPackage.model_validate(wp)
    elif isinstance(wp, WorkPackage):
        wp_obj = wp
    else:
        raise ValueError(f"wp must be WorkPackage or dict, got {type(wp).__name__}")

    # 2. 确定项目名称和路径
    if not project_name:
        project_name = f"deliver_{wp_obj.wp_id.lower().replace('-', '_')}"

    blackboard_path = BLACKBOARD_ROOT / project_name
    deliver_pro_dir = blackboard_path / "deliver_pro"

    # 3. 确保目录存在
    deliver_pro_dir.mkdir(parents=True, exist_ok=True)
    (deliver_pro_dir / "data").mkdir(exist_ok=True)
    (deliver_pro_dir / "stages").mkdir(exist_ok=True)
    (deliver_pro_dir / "stages" / "worker_outputs").mkdir(exist_ok=True)

    # 4. 写入 WP（如果尚未存在）
    wp_path = deliver_pro_dir / "data" / "wp.json"
    if not wp_path.exists():
        wp_data = wp_obj.model_dump(mode="json")
        wp_path.write_text(
            json.dumps(wp_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"WP written to {wp_path}")

    # 4b. P1-1: Write ShipPackage top-level context if available
    if ship_package_context:
        ship_context_path = deliver_pro_dir / "data" / "ship_context.json"
        ship_context_path.write_text(
            json.dumps(ship_package_context, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            f"ShipPackage context written to {ship_context_path} "
            f"(fields: {list(ship_package_context.keys())})"
        )

    # 5. 构建 Orchestrator prompt
    deepflow_root = str(DEEPFLOW_ROOT)
    orchestrator_prompt = _build_orchestrator_prompt(
        wp_id=wp_obj.wp_id,
        project_name=project_name,
        blackboard_path=str(blackboard_path),
        deliver_pro_dir=str(deliver_pro_dir),
        deepflow_root=deepflow_root,
        scenario=wp_obj.scenario,
    )

    # 6. 返回 spawn params
    result = {
        "project_name": project_name,
        "wp_id": wp_obj.wp_id,
        "blackboard_path": str(blackboard_path),
        "deliver_pro_dir": str(deliver_pro_dir),
        "input_summary": {
            "scenario": wp_obj.scenario,
            "ac_count": wp_obj.total_ac_count,
            "dependency_count": len(wp_obj.dependencies),
        },
        "spawn_params": {
            "runtime": "subagent",
            "mode": "run",
            "label": f"deliver-pro-orch-{wp_obj.wp_id.lower()}",
            "task": auto_bootstrap(
                Path(deepflow_root),
                deliver_pro_dir / "stages",
                orchestrator_prompt,
                f"deliver_orch_{wp_obj.wp_id.lower()}",
            ),
            "cwd": deepflow_root,
            "lightContext": True,
        },
    }

    logger.info(
        f"run_deliver_pro: wp={wp_obj.wp_id}, project={project_name}, "
        f"scenario={wp_obj.scenario}"
    )
    return result


# ============================================================================
# Orchestrator Prompt 构建
# ============================================================================

def _build_orchestrator_prompt(
    wp_id: str,
    project_name: str,
    blackboard_path: str,
    deliver_pro_dir: str,
    deepflow_root: str,
    scenario: str,
) -> str:
    """
    构建 Orchestrator Agent 的完整 prompt。

    Orchestrator Agent 是 depth-1，它驱动 5 Phase 流水线。
    """
    return f"""你是 Deliver Pro Orchestrator — 薄层调度器。

## 你的职责
按顺序执行 5 个 Phase。每个 Phase = exec 调 Driver → spawn → yield → exec 验证。
你不写业务逻辑。你只调 Driver 方法和检查输出。

## 环境
- DeepFlow root: `{deepflow_root}`
- WP ID: `{wp_id}`
- 项目: `{project_name}`

## 🔴 exec preamble（所有 exec 都用这个开头）
```python
cd {deepflow_root} && PYTHONPATH=. python3 -c "
from domains.deliver_pro.driver import DeliverProDriver
d = DeliverProDriver('{wp_id}', '{project_name}')
import json
```

## 🔴 铁律（违反任何一条 = 流水线失败）
1. spawn 后必须 sessions_yield()
2. **yield 唤醒后第一个 action 必须是 exec**（不能只输出文字）
3. 不写 import/构造对象 — 调 Driver
4. **绝不输出 NO_REPLY** — 每个 turn 必须有可见文字或 tool call。如果你认为“没事可做”，先 exec step4 查状态，再决定。
5. 每个 exec 命令执行后必须检查输出（OK/正常 → 继续，Error/Traceback → 停止报告）
6. **不要判断事件是否“重复”** — 你不知道之前处理过什么。每次 yield 唤醒后，无条件执行对应的 check 步骤（step2/step4/step6_check/step7_check），让 Driver 返回值告诉你该做什么。

## 执行算法

### Step 1: Phase 1 — Analyze
exec: `print(json.dumps(d.step1_analyze()))`
→ 拿到 spawn_params → sessions_spawn(**params) → sessions_yield()
→ **唤醒后** exec: `ok, info = d.step2_check_analyze(); print(ok, json.dumps(info))`
→ ok=True → Step 2 | ok=False → 报告错误

### Step 2: Phase 2 — Workers（循环）
exec: `print(json.dumps(d.step3_workers()))`
→ 对每个 params → sessions_spawn(**params) → sessions_yield()
→ **每次唤醒后** 无条件 exec: `done, info = d.step4_check_workers(); print(done, json.dumps(info))`
→ 根据返回值决策（不看事件内容，只看 Driver 返回值）：
  - done=True → Step 3
  - done=False + info 有 next_wave>0 → 回到 Step 2 开头（exec step3_workers）
  - done=False + next_wave=0 → sessions_yield() 继续等待

### Step 3: Phase 3 — Assembly（exec 直接执行，不 spawn）
exec: `print(json.dumps(d.step5_integrate()))`
→ status≠ASSEMBLY_ERROR → Step 4

### Step 4: Phase 4 — Validate（最多 5 轮）
round = 1
while round <= 5:
  exec: `print(json.dumps(d.step6_validate(round_num=round)))`
  → sessions_spawn → sessions_yield()
  → **唤醒后** exec: `verdict, info = d.step6_check_validate(); print(verdict, json.dumps(info))`
  → PASS → Step 5
  → CONDITIONAL → exec: `print(json.dumps(d.step6_5_fix_integrate(info["data"])))` → sessions_spawn → yield → round+=1 → 继续循环
  → FAIL → Step 5（降级交付）

### Step 5: Phase 5 — Package
exec: `print(json.dumps(d.step7_package()))`
→ sessions_spawn → sessions_yield()
→ **唤醒后** exec: `ok, info = d.step7_check_package(); print(ok, json.dumps(info))`
→ ok=True → 输出“流水线完成” → 结束

## 完成条件
只有以下条件全部满足才能结束：
- Phase 1-5 全部执行
- step7_check_package 返回 ok=True

请开始执行。从 Step 1 开始。
"""


# ============================================================================
# 便捷函数
# ============================================================================

def get_orchestrator(
    project_name: str,
    wp: WorkPackage | dict | None = None,
) -> DeliverProOrchestrator:
    """
    获取已存在的 Orchestrator（用于断点续传）。

    Args:
        project_name: 项目名称
        wp: WorkPackage（如不提供，从 Blackboard 读取）

    Returns:
        DeliverProOrchestrator 实例
    """
    blackboard_path = BLACKBOARD_ROOT / project_name
    deliver_pro_dir = blackboard_path / "deliver_pro"

    if wp is None:
        # 从 Blackboard 读取 WP
        wp_path = deliver_pro_dir / "data" / "wp.json"
        if not wp_path.exists():
            raise FileNotFoundError(f"WP not found: {wp_path}")
        wp_data = json.loads(wp_path.read_text(encoding="utf-8"))
        wp = WorkPackage.model_validate(wp_data)
    elif isinstance(wp, dict):
        wp = WorkPackage.model_validate(wp)

    return DeliverProOrchestrator(wp, blackboard_path, project_name)
