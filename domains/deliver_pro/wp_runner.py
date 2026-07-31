"""
Deliver Pro Orchestrator — 5 Phase 流水线 + Validate Loop

架构:
  Main Agent (depth-0)
    → exec: result = run_deliver_pro(wp=...)
    → sessions_spawn(**result["spawn_params"])   # 启动 Orchestrator Agent

  Orchestrator Agent (depth-1, 本模块)
    → Phase 1: prepare_analyze_spawn() → spawn Analyze Agent (depth-2)
    → Phase 2: prepare_workers_spawn() → spawn Workers (depth-2, 滑动窗口)
    → Phase 3: run_integrate() → Code-First Assembly（确定性拼接，零 LLM）
    → Phase 4: prepare_validate_spawn() → spawn Validate Judge (depth-2, Loop ≤5)
    → Phase 5: prepare_package_spawn() → spawn Package Agent (depth-2)

核心原则:
  1. Orchestrator 不直接调用 sessions_spawn（Python 不能调 Agent tool）
  2. 每个 prepare_* 方法返回 spawn_params dict
  3. Phase 间数据通过 Blackboard 文件传递
  4. Worker 故障恢复：LLM 诊断（不查表），最多 3 轮/WP
  5. Validate Loop：最多 5 轮，LLM 判断 should_continue

参考:
  - Ship Pro: domains/ship_pro/orchestrator/ship_orchestrator.py
  - Solution Pro: domains/solution_pro/master_orchestrator.py
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import os
import tempfile

from domains.deliver_pro.contracts import (
    WorkPackage,
    ExecutionPlan,
    TaskNode,
    WorkerOutputMeta,
    ValidationVerdict,
    ScoreDimension,
    FixDirective,
    PipelineState,
    PipelinePhase,
    DeliveryManifest,
    ComponentStatus,
    DeliveryStatus,
    RecoveryAction,
    WorkerError,
    RecoveryStrategy,
    IntegrationReport,
)
from core.blackboard.context_injector import auto_bootstrap
from core.utils.atomic_io import atomic_write_json
from domains.deliver_pro.prompt_registry import load_prompt
from domains.deliver_pro.failure_recovery import WorkerFailureRecovery

# ADR-009: MD Track Extractor (optional — graceful fallback if core/ not in path)
try:
    from core.md_track_extractor import validate_md_structure, extract_track_json
    _HAS_TRACK_EXTRACTOR = True
except ImportError:
    _HAS_TRACK_EXTRACTOR = False

logger = logging.getLogger(__name__)


# ============================================================================
# 常量
# ============================================================================

MAX_VALIDATE_ROUNDS = 5
MAX_WORKER_RECOVERY_ATTEMPTS = 3
VALIDATE_PASS_THRESHOLD = 3.5
VALIDATE_MIN_DIMENSION = 3
VALIDATE_CONDITIONAL_THRESHOLD = 3.0
VALIDATE_FAIL_MIN_DIMENSION = 2


class DeliverWPRunner:
    """
    Deliver Pro 核心编排器 — 5 Phase 流水线 + Validate Loop.

    纯工具库模式（对标 Ship Pro 的 ShipOrchestrator）：
    - 提供 prepare_* 方法返回 spawn_params dict
    - 提供 verify_* 方法进行 Gate 验证
    - 不直接调用 sessions_spawn（那是 Agent 层的职责）
    """

    # B-3 fix: shared rules file path (inject into all prompts)
    _SHARED_RULES_PATH = Path(__file__).parent / "prompts" / "_shared_subagent_rules.md"

    def _load_shared_rules(self) -> str:
        """Load shared subagent rules for prompt injection (B-3 fix)."""
        if self._SHARED_RULES_PATH.exists():
            return self._SHARED_RULES_PATH.read_text(encoding="utf-8")
        return ""

    def __init__(
        self,
        wp: WorkPackage,
        blackboard_path: Path,
        project_name: str = "default",
    ):
        """
        初始化 Orchestrator。

        Args:
            wp: Work Package（来自 Ship Pro）
            blackboard_path: Blackboard 根路径
                            (.deepflow/blackboard/{project_name}/)
            project_name: 项目名称
        """
        self.wp = wp
        self.blackboard_path = Path(blackboard_path)
        self.project_name = project_name

        # Deliver Pro 专属目录（按 wp_id 分子目录）
        # Fix(commit 3489118): wp_subdir 必须保存为实例属性，供 prompt 模板使用
        self.wp_subdir = wp.wp_id.lower().replace('-', '_') if wp.wp_id else ""
        self.deliver_pro_dir = self.blackboard_path / "deliver_pro" / self.wp_subdir
        self.data_dir = self.deliver_pro_dir / "data"
        self.stages_dir = self.deliver_pro_dir / "stages"
        self.worker_outputs_dir = self.stages_dir / "worker_outputs"
        self.integrated_draft_dir = self.stages_dir / "integrated_draft"
        self.final_deliverable_dir = self.stages_dir / "final_deliverable"

        # 确保目录存在
        self._ensure_directories()

        # 初始化状态：优先从磁盘加载，否则创建新状态
        state_path = self.deliver_pro_dir / "delivery_state.json"
        if state_path.exists():
            try:
                from domains.deliver_pro.utils.safe_json_loader import SafeJsonLoader
                result = SafeJsonLoader.load(state_path, PipelineState, mtime_window=0)
                if result.state == "ok":
                    state_data = result.data
                else:
                    # delivery_state.json 损坏，备份后重建
                    logger.warning(f"delivery_state.json corrupted ({result.state}), backing up and rebuilding")
                    backup_path = state_path.with_suffix(".corrupted")
                    state_path.rename(backup_path)
                    state_data = {}
                # B2 fix: Phase field recovery — map unknown phase to valid enum
                raw_phase = state_data.get("phase", "")
                if raw_phase and raw_phase not in {p.value for p in PipelinePhase}:
                    _PHASE_ALIASES = {"ASSEMBLING": "INTEGRATING", "ASSEMBLE": "INTEGRATING"}
                    if raw_phase in _PHASE_ALIASES:
                        logger.warning(f"B2: Phase alias '{raw_phase}' → '{_PHASE_ALIASES[raw_phase]}'")
                        state_data["phase"] = _PHASE_ALIASES[raw_phase]
                    elif state_data.get("completed_tasks") or state_data.get("running_tasks"):
                        logger.warning(f"B2: Unknown phase '{raw_phase}', salvaging to GENERATING")
                        state_data["phase"] = "GENERATING"
                    else:
                        logger.warning(f"B2: Unknown phase '{raw_phase}', resetting to INIT")
                        state_data["phase"] = "INIT"
                self.state = PipelineState.model_validate(state_data)
                logger.info(f"State loaded from disk: phase={self.state.phase}")
            except Exception:
                # P2-3: preserve exception context + backup corrupted file
                logger.warning(
                    f"Failed to load state from {state_path}, starting fresh",
                    exc_info=True,
                )
                try:
                    backup_path = state_path.with_suffix(".json.corrupted")
                    state_path.rename(backup_path)
                    logger.warning(f"Corrupted state backed up to {backup_path}")
                except OSError as backup_err:
                    logger.error(f"Failed to backup corrupted state: {backup_err}")
                self.state = PipelineState(wp_id=wp.wp_id)
        else:
            self.state = PipelineState(wp_id=wp.wp_id)

        # 写入 WP 到 Blackboard（只读输入）
        self._write_wp()

        logger.info(
            f"DeliverWPRunner initialized: wp={wp.wp_id}, "
            f"scenario={wp.scenario}, blackboard={self.blackboard_path}"
        )

    def _ensure_directories(self) -> None:
        """确保所有必要目录存在。"""
        for d in [
            self.data_dir,
            self.stages_dir,
            self.worker_outputs_dir,
            self.stages_dir / "integrated_draft",
            self.stages_dir / "final_deliverable",
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def _write_wp(self) -> None:
        """写入 WP 到 Blackboard（data/wp.json）。"""
        wp_path = self.data_dir / "wp.json"
        if not wp_path.exists():
            wp_data = self.wp.model_dump(mode="json")
            wp_path.write_text(
                json.dumps(wp_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(f"WP written to {wp_path}")

    def _save_state(self) -> None:
        """保存流水线状态到 delivery_state.json。

        P1-polish: 添加 deprecation 标记，指明 phase 显示以 batch_progress.json / derive_phase 为准。
        V3 架构不读 delivery_state.json 做决策（文件系统即真相），但直接读者会被滞留 phase 误导。
        """
        state_path = self.deliver_pro_dir / "delivery_state.json"
        state_data = self.state.model_dump()
        state_data["_deprecation_note"] = (
            "DEPRECATED: phase 显示以 batch_progress.json / derive_phase 为准。"
            "本文件仅作 append-only 日志，不作为决策门禁。"
        )
        atomic_write_json(state_path, state_data)

    # ========================================================================
    # Phase 1: Analyze
    # ========================================================================

    def prepare_analyze_spawn(self) -> dict[str, Any]:
        """
        Phase 1: 准备 Analyze Agent 的 spawn 参数。

        Analyze Agent 解析 WP → 生成 execution_plan.json（任务图 + 并发计划）。

        Returns:
            sessions_spawn 参数 dict
        """
        self.state.transition_to(PipelinePhase.ANALYZING)
        self._save_state()

        # 尝试加载 prompt 模板，fallback 到内嵌 prompt
        try:
            prompt = load_prompt(
                "deliver_analyze",
                wp_id=self.wp.wp_id,
                wp_summary=self.wp.objective,
                workspace=str(self.blackboard_path),
                lib_path=str(self.blackboard_path.parent.parent / "domains"),
                deepflow_root=str(self.blackboard_path.parent.parent),
                wp_data_path=str(self.data_dir / "wp.json"),
                output_path=str(self.stages_dir / "execution_plan.json"),
                stages_dir=str(self.stages_dir),
            )
        except FileNotFoundError:
            prompt = self._build_analyze_prompt()

        _root = self.blackboard_path.parent.parent
        _label = f"deliver_analyze_{self.wp.wp_id}"
        return {
            "runtime": "subagent",
            "mode": "run",
            "label": _label,
            "task": auto_bootstrap(_root, self.stages_dir, prompt, _label),
            "thinking": "high",
        }

    # 第一行动提示（供 Orchestrator 在 spawn 时使用，非必选）
    ANALYZE_FIRST_ACTION_HINT = (
        f"读取 bootstrap 后，你的下一个 action 必须是 exec: cat <wp_data_path>"
    )

    def verify_analyze_output(self, plan_data: dict) -> tuple[bool, str]:
        """
        验证 Analyze Agent 输出。

        Args:
            plan_data: execution_plan.json 的内容

        Returns:
            (passed, error_message)
        """
        try:
            # Pydantic 验证（DAG 无环检查在 model_validator 中）
            plan = ExecutionPlan.model_validate(plan_data)

            # 额外检查
            if plan.wp_id != self.wp.wp_id:
                return False, f"wp_id mismatch: expected {self.wp.wp_id}, got {plan.wp_id}"

            # P1-5 fix: Allow zero-worker plans — mark as COMPLETED directly.
            # A valid plan with 0 tasks means "nothing to do" (e.g., no-op WP).
            if plan.task_count == 0:
                plan_path = self.stages_dir / "execution_plan.json"
                plan_path.write_text(
                    json.dumps(plan_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self.state.transition_to(PipelinePhase.GENERATING)
                self.state.transition_to(PipelinePhase.INTEGRATING)
                self.state.transition_to(PipelinePhase.VALIDATING)
                self.state.transition_to(PipelinePhase.PACKAGING)
                self.state.transition_to(PipelinePhase.COMPLETED)
                self._save_state()
                logger.info("P1-5: Zero-worker plan → auto-COMPLETED")
                return True, "zero_worker_plan"

            # 写入验证后的 plan
            plan_path = self.stages_dir / "execution_plan.json"
            plan_path.write_text(
                json.dumps(plan_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            self.state.transition_to(PipelinePhase.GENERATING)
            self.state.pending_tasks = [t.task_id for t in plan.task_graph]
            self._save_state()

            logger.info(
                f"Phase 1 verified: {plan.task_count} tasks, "
                f"scenario={plan.scenario}, waves={len(plan.concurrency_plan.waves)}"
            )
            return True, ""

        except Exception as e:
            return False, f"ExecutionPlan validation failed: {e}"

    def _build_analyze_prompt(self) -> str:
        """内嵌 Analyze Agent prompt（fallback）。"""
        shared_rules = self._load_shared_rules()
        rules_section = f"\n\n## 共享规则（必须遵守）\n{shared_rules}" if shared_rules else ""
        return f"""你是 Deliver Pro 的 Analyze Agent。
{rules_section}

## 任务
解析 Work Package，生成执行计划（任务图 + 并发计划）。

## 输入
- WP 文件: {self.data_dir / "wp.json"}
## 输出
写入: {self.stages_dir / "execution_plan.json"}

## 输出格式
```json
{{
  "schema_version": "1.0.0",
  "wp_id": "{self.wp.wp_id}",
  "scenario": "{self.wp.scenario}",
  "task_graph": [
    {{
      "task_id": "T-001",
      "title": "任务标题",
      "depends_on": [],
      "estimated_complexity": "low|medium|high",
      "expected_outputs": [{{"path": "...", "type": "code|report"}}],
      "acceptance_criteria": ["AC 描述"]
    }}
  ],
  "concurrency_plan": {{
    "suggested_parallelism": 3,
    "safety_cap": 8,
    "waves": [{{"wave": 1, "task_ids": ["T-001", "T-002"]}}]
  }},
  "quality_gates": {{
    "code": ["lint_pass", "test_pass"],
    "report": ["data_verified", "source_cited"]
  }}
}}
```

## 约束
1. 任务图必须是无环 DAG
2. 每个任务必须有明确的 expected_outputs
3. 并发计划要合理（依赖关系决定执行顺序）
4. 任务数量建议 2-8 个

请直接输出 JSON。
"""

    # ========================================================================
    # Phase 2: Generate (Workers)
    # ========================================================================

    def _derive_worker_progress(self, plan: ExecutionPlan):
        """V3: 从文件系统推导 worker 进度（completed/failed/running/pending）。"""
        from domains.deliver_pro.phase_deriver import derive_worker_progress
        plan_task_ids = {t.task_id for t in plan.task_graph}
        task_deps = {t.task_id: t.depends_on for t in plan.task_graph}
        return derive_worker_progress(self.deliver_pro_dir, plan_task_ids, task_deps)

    def peek_next_wave_count(self, plan: ExecutionPlan) -> int:
        """纯只读：计算下一波可执行任务数量（不修改 state）。

        V3: completed/failed/running 全部从文件系统推导。
        """
        progress = self._derive_worker_progress(plan)
        completed = progress["completed"]
        ready_tasks = plan.get_ready_tasks(completed)

        # 排除 running / failed / blocked
        excluded = progress["running"] | progress["failed"] | progress["blocked"]
        ready_tasks = [t for t in ready_tasks if t.task_id not in excluded]

        max_parallel = plan.concurrency_plan.suggested_parallelism
        return min(len(ready_tasks), max_parallel)

    def prepare_workers_spawn(
        self,
        plan: ExecutionPlan,
        completed_tasks: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Phase 2: 准备 Worker spawn 参数（滑动窗口 + 依赖图）。

        根据 execution_plan 的依赖关系，返回当前可以执行的任务的 spawn 参数。

        Args:
            plan: 执行计划
            completed_tasks: 已完成的任务 ID 集合

        Returns:
            spawn_params 列表（每个元素对应一个 Worker）
        """
        # 契约笼子：幂等前置状态记录（V3: 日志语义，不再 raise）
        if self.state.phase == PipelinePhase.ANALYZING:
            self.state.transition_to(PipelinePhase.GENERATING)
            self._save_state()

        # V3: 从文件系统推导进度（derive, don't sync）
        progress = self._derive_worker_progress(plan)
        completed = completed_tasks if completed_tasks is not None else progress["completed"]
        ready_tasks = plan.get_ready_tasks(completed)

        # V3: 排除 running / failed / blocked（全部从文件推导）
        excluded = progress["running"] | progress["failed"] | progress["blocked"]
        ready_tasks = [t for t in ready_tasks if t.task_id not in excluded]

        if not ready_tasks:
            logger.info("No ready tasks (all dependencies not met or all completed)")
            return []

        # 限制并发数
        max_parallel = plan.concurrency_plan.suggested_parallelism
        ready_tasks = ready_tasks[:max_parallel]

        spawn_params_list = []
        for task in ready_tasks:
            params = self._prepare_single_worker_spawn(task, plan)
            spawn_params_list.append(params)

            # 标记为 running
            if task.task_id not in self.state.running_tasks:
                self.state.running_tasks.append(task.task_id)

        self._save_state()
        logger.info(
            f"Phase 2: prepared {len(spawn_params_list)} workers "
            f"(completed={len(completed)}, pending={len(self.state.pending_tasks)})"
        )
        return spawn_params_list

    def _prepare_single_worker_spawn(
        self,
        task: TaskNode,
        plan: ExecutionPlan,
    ) -> dict[str, Any]:
        """准备单个 Worker 的 spawn 参数。"""
        # 构建 Worker prompt
        prompt = self._build_worker_prompt(task, plan)

        _root = self.blackboard_path.parent.parent
        # F5 fix: label 加 WP ID——不同 WP 的同名 task（如各自的 T-002）在后台可区分
        # （本次事故：CHP-001/T-002 与 DFM-001/T-002 撞名被误判为重复 spawn）
        _label = f"deliver-worker-{self.wp.wp_id.lower()}-{task.task_id.lower()}"
        return {
            "runtime": "subagent",
            "mode": "run",
            "label": _label,
            # Pulse V1: task_id 用于 orchestrator 的 dedup_key / task_attempts 账本 /
            # 孤儿目录清理。非 sessions_spawn 合法参数，Agent 层 spawn 前需剥离。
            "task_id": task.task_id,
            "task": auto_bootstrap(_root, self.stages_dir, prompt, _label),
            "thinking": "high",
            # N5: Inject timeout from TaskNode contract
            "timeoutSeconds": task.timeout_seconds * 1000,  # Convert to ms
        }

    def _build_worker_prompt(self, task: TaskNode, plan: ExecutionPlan) -> str:
        """构建 Worker prompt。"""
        shared_rules = self._load_shared_rules()
        rules_section = f"\n\n## 共享规则（必须遵守）\n{shared_rules}" if shared_rules else ""
        # 依赖路径
        dep_paths = []
        for dep_id in task.depends_on:
            dep_dir = self.worker_outputs_dir / dep_id
            dep_paths.append(str(dep_dir))

        # 输出目录
        output_dir = self.worker_outputs_dir / task.task_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # N1: 格式化任务详细内容
        ac_text = "\n".join(f"- {ac}" for ac in task.acceptance_criteria) if task.acceptance_criteria else "（无）"
        outputs_text = "\n".join(
            f"- {o.get('path', '?')} ({o.get('type', '?')})"
            for o in task.expected_outputs
        ) if task.expected_outputs else "（无）"

        # B3 fix (DryRun 2026-07-30): 透传 semantic_anchors 和 serving_principles
        # Ship Pro 的语义锚点和服务原则通过 _adapt_ship_pro_wp() 存入 WP.context，
        # 必须注入到 Worker prompt 中，否则信息守恒在 WP→Worker 环节断裂。
        if self.wp.semantic_anchors:
            anchors_text = "\n".join(
                f"- {a.get('name', a.get('constraint', str(a)))}"
                for a in self.wp.semantic_anchors
            )
        else:
            anchors_text = "（无）"
        if self.wp.serving_principles:
            principles_text = "\n".join(
                f"- {p.get('obligation', str(p))}"
                for p in self.wp.serving_principles
            )
        else:
            principles_text = "（无）"
        semantic_context_section = (
            f"\n\n## 语义锚点（必须遵守的约束）\n{anchors_text}"
            f"\n\n## 服务原则（必须满足的义务）\n{principles_text}"
        )

        # P0-1 fix: use project_name (not wp_id_lower) for absolute path construction
        project_name = self.project_name
        # Fix(commit 3489118): 必须传递 wp_subdir 给 prompt 模板，
        # 否则 Worker 看到的输出路径中 {wp_subdir} 不会被替换，
        # 导致 Worker 写入 deliver_pro/stages/ 而非 deliver_pro/{wp_subdir}/stages/
        try:
            prompt = load_prompt(
                "deliver_worker_base",
                task_id=task.task_id,
                wp_id=self.wp.wp_id,
                project_name=project_name,
                wp_subdir=self.wp_subdir,
                scenario=task.scenario_type,
                dependencies=", ".join(dep_paths) if dep_paths else "无",
                forced_actions=", ".join(task.forced_actions) if task.forced_actions else "无",
                title=task.title,
                description=task.description or task.title,
                acceptance_criteria=ac_text,
                expected_outputs=outputs_text,
                deepflow_root=str(self.blackboard_path.parent.parent),
            )
            # B3 fix: 追加语义上下文到 template prompt
            return prompt + semantic_context_section
        except FileNotFoundError:
            pass

        # Fallback: 内嵌 prompt
        scenario = task.scenario_type or plan.scenario
        forced_actions = self._get_forced_actions(scenario)

        return f"""你是 Deliver Pro 的 Worker。

## 你的任务
- Task ID: {task.task_id}
- 标题: {task.title}
- 描述: {task.description or task.title}
- 场景: {scenario}

## 验收标准
{ac_text}

## 期望输出（附加产物，不替代 DELIVERABLE.md）
{outputs_text}

> ⚠️ 期望输出是附加产物（写入对应子目录作为补充），不能替代 DELIVERABLE.md（缺失 = FAILED）。

## WP 上下文
- WP ID: {self.wp.wp_id}
- 目标: {self.wp.objective}
- 文件: {self.data_dir / "wp.json"}

## 语义锚点（必须遵守的约束）
{anchors_text}

## 服务原则（必须满足的义务）
{principles_text}

## 依赖（上游 Worker 输出）
{chr(10).join(f'- {p}' for p in dep_paths) if dep_paths else '无依赖'}

## 输出目录
{output_dir}

必须产出 4 个文件:
1. DELIVERABLE.md — 主产物
2. EVIDENCE.md — 验证证据
3. ISSUES.md — 问题记录（没有则写"无"）
4. MANIFEST.json — 元数据

## 强制动作（{scenario} 场景）
{forced_actions}

## 铁律
1. 无证据不交付
2. 不完整必须声明（写入 ISSUES.md）
3. 自检是交付前提
4. 不修改他人产出

## Preamble
cd {self.blackboard_path.parent.parent}

请直接开始工作。
"""

    def _get_forced_actions(self, scenario: str) -> str:
        """获取场景对应的强制动作。"""
        if scenario == "code":
            return """- web_search ≥ 2 次（技术方案/API 文档）
- write 代码 + 测试
- exec 安装依赖 + 运行测试 + lint（≥ 2 次，所有 exec 必须带 timeout ≤300s）
- exec smoke test：每个可执行脚本/程序真实执行 ≥ 1 次（必须带 timeout，如 exec timeout 参数或 gtimeout 300）
- EVIDENCE.md 必须包含每个脚本的真实执行输出（含脚本名）
- write MANIFEST.json"""
        elif scenario == "report":
            return """- web_search ≥ 3 次（行业数据/验证数据点）
- write 分析报告
- 事实性陈述逐条验证
- write EVIDENCE.md + MANIFEST.json"""
        else:
            return "- 根据任务需求合理使用工具"

    def _detect_substance(self, output_dir: Path) -> bool:
        """检测 output_dir 是否存在实质产出文件。

        实质产出 = 存在任一文件，满足：
        - 文件名不属于契约元数据集合 {MANIFEST.json, EVIDENCE.md, ISSUES.md}
        - 文件名不是 DELIVERABLE.md（始终排除，避免 missing_blocking/too short 误判）
        - 文件大小 > 100 字节
        """
        metadata_files = {"MANIFEST.json", "EVIDENCE.md", "ISSUES.md"}
        try:
            for path in output_dir.rglob("*"):
                if not path.is_file():
                    continue
                if path.name in metadata_files:
                    continue
                if path.name == "DELIVERABLE.md":
                    continue
                try:
                    if path.stat().st_size > 100:
                        return True
                except OSError:
                    continue
        except OSError:
            return False
        return False

    def verify_worker_output(
        self,
        task_id: str,
        output_dir: Path,
    ) -> tuple[bool, str, WorkerOutputMeta | None]:
        """
        验证 Worker 输出。

        Args:
            task_id: 任务 ID
            output_dir: Worker 输出目录

        Returns:
            (passed, error_message, output_meta)
        """
        # 检查必需文件 (P1-2: 4-file contract)
        # Blocking: DELIVERABLE.md + MANIFEST.json required
        blocking_files = ["DELIVERABLE.md", "MANIFEST.json"]
        missing_blocking = [f for f in blocking_files if not (output_dir / f).exists()]
        if missing_blocking:
            # F-B: 区分“有实质产出但缺契约文件” vs “实质失败”
            substance = self._detect_substance(output_dir)
            failure_class = "contract_violation" if substance else "substance_failure"
            # V3: 验证失败事实写入 MANIFEST（若 MANIFEST 本身缺失则创建）
            self.mark_worker_failed(
                task_id,
                f"Missing required files: {missing_blocking}",
                failure_class=failure_class,
            )
            return False, f"Missing required files: {missing_blocking}", None

        # Non-blocking: EVIDENCE.md + ISSUES.md (PARTIAL if missing, not FAILED)
        optional_files = ["EVIDENCE.md", "ISSUES.md"]
        missing_optional = [f for f in optional_files if not (output_dir / f).exists()]
        if missing_optional:
            logger.warning(
                f"Worker {task_id} missing optional files: {missing_optional}. "
                f"Status will be PARTIAL."
            )

        # Guard: 检查 DELIVERABLE.md 内容不为空（Doctor #4 修复）
        deliverable_path = output_dir / "DELIVERABLE.md"
        content = deliverable_path.read_text(encoding="utf-8").strip()
        MIN_DELIVERABLE_LENGTH = 50  # 至少 50 字符
        if len(content) < MIN_DELIVERABLE_LENGTH:
            logger.warning(
                f"Worker {task_id} DELIVERABLE.md too short: "
                f"{len(content)} chars (min {MIN_DELIVERABLE_LENGTH})"
            )
            # F-B: DELIVERABLE.md 过短也区分“有实质产出” vs “实质失败”
            # （_detect_substance 默认已排除 DELIVERABLE.md 自身）
            substance = self._detect_substance(output_dir)
            failure_class = "contract_violation" if substance else "substance_failure"
            # V3: 验证失败事实写入 MANIFEST（文件系统即真相）
            self.mark_worker_failed(
                task_id,
                f"DELIVERABLE.md content too short ({len(content)} chars, "
                f"minimum {MIN_DELIVERABLE_LENGTH})",
                failure_class=failure_class,
            )
            return (
                False,
                f"DELIVERABLE.md content too short ({len(content)} chars, "
                f"minimum {MIN_DELIVERABLE_LENGTH}). Worker likely produced empty output.",
                None,
            )

        # 读取 MANIFEST.json
        try:
            manifest_path = output_dir / "MANIFEST.json"
            from domains.deliver_pro.utils.safe_json_loader import SafeJsonLoader
            from domains.deliver_pro.contracts.worker_task import WorkerOutputMeta
            result = SafeJsonLoader.load(manifest_path, WorkerOutputMeta, mtime_window=0)
            if result.state != "ok":
                self.mark_worker_failed(task_id, f"MANIFEST.json corrupted: {result.state}")
                return False, f"MANIFEST.json corrupted: {result.state}", None
            meta = result.parsed
        except Exception as e:
            self.mark_worker_failed(task_id, f"MANIFEST.json validation failed: {e}")
            return False, f"MANIFEST.json validation failed: {e}", None

        # P1-2: Override status to PARTIAL if optional files missing
        if missing_optional:
            meta.status = "PARTIAL"
            logger.info(f"Worker {task_id} status overridden to PARTIAL (missing: {missing_optional})")

        # Smoke-test Gate (L1, 2026-07-31 git_init.sh 事故):
        # code 场景交付可执行脚本时，EVIDENCE.md 必须包含每个脚本名的执行证据，
        # 防止“脚本带 bug 但自评通过”（如参数解析死循环烧 15 小时 CPU）。
        # 注: 这是 L1 快速过滤（文件名出现在证据中），语义真实性由 L2 Validate 判断。
        if meta.scenario == "code":
            script_names = [
                Path(str(o.get("path", ""))).name
                for o in (meta.outputs or [])
                if isinstance(o, dict) and o.get("type") == "script" and o.get("path")
            ]
            if script_names:
                evidence_path = output_dir / "EVIDENCE.md"
                evidence_text = (
                    evidence_path.read_text(encoding="utf-8", errors="replace")
                    if evidence_path.exists()
                    else ""
                )
                missing_smoke = [n for n in script_names if n not in evidence_text]
                if missing_smoke:
                    msg = (
                        f"Smoke test evidence missing for script deliverables: "
                        f"{missing_smoke}. EVIDENCE.md must contain actual execution "
                        f"output (with timeout) for each script."
                    )
                    self.mark_worker_failed(
                        task_id, msg, failure_class="contract_violation"
                    )
                    return False, msg, None

        # 更新状态
        self.state.mark_task_completed(task_id)
        if task_id in self.state.running_tasks:
            self.state.running_tasks.remove(task_id)
        self._save_state()

        logger.info(f"Worker {task_id} verified: status={meta.status}")
        return True, "", meta

    # ========================================================================
    # Phase 3: Integrate
    # ========================================================================

    def run_integrate(self, plan: ExecutionPlan) -> Any:
        """Phase 3: Code-First Assembly（确定性拼接，零 LLM 压缩）。

        使用 SmartAssembler 拼接 Worker 产出，保留率 ≥95%。
        这是生产主链的 Phase 3 入口（替代 LLM Integrate Agent）。

        Args:
            plan: 执行计划

        Returns:
            AssemblyResult 包含保留率、文件路径等
        """
        from domains.deliver_pro.smart_assembler import SmartAssembler

        # Idempotent transition: skip if already INTEGRATING (e.g., prepare_integrate_spawn called first)
        if self.state.phase != PipelinePhase.INTEGRATING:
            self.state.transition_to(PipelinePhase.INTEGRATING)
            self._save_state()

        assembler = SmartAssembler(
            worker_outputs_dir=self.worker_outputs_dir,
            plan_data=plan.model_dump(mode="json"),
            output_dir=self.integrated_draft_dir,
        )
        result = assembler.run()

        self.state.transition_to(PipelinePhase.VALIDATING)
        self._save_state()

        logger.info(
            f"Phase 3 Integrate (Code-First): {result.workers_integrated} workers, "
            f"retention={result.retention_ratio:.1%}"
        )
        return result

    def prepare_integrate_spawn(
        self,
        plan: ExecutionPlan,
        fix_directives: list[FixDirective] | None = None,
    ) -> dict[str, Any]:
        """
        Phase 3 (legacy): 准备 Integrate Agent 的 spawn 参数。
        建议改用 run_integrate() 进行确定性拼接。

        Integrate Agent 组装所有 Worker 输出为统一交付物草稿。

        Args:
            plan: 执行计划
            fix_directives: 修复指令（Validate Loop 修复轮次时传入）

        Returns:
            sessions_spawn 参数 dict
        """
        self.state.transition_to(PipelinePhase.INTEGRATING)
        self._save_state()

        # 收集 Worker 输出路径
        worker_dirs = []
        failed_workers = []
        for task in plan.task_graph:
            task_dir = self.worker_outputs_dir / task.task_id
            if task_dir.exists():
                worker_dirs.append(str(task_dir))
            else:
                failed_workers.append(task.task_id)

        # 尝试加载 prompt 模板
        try:
            prompt = load_prompt(
                "deliver_integrate",
                wp_id=self.wp.wp_id,
                project_name=self.project_name,
                wp_subdir=self.wp_subdir,
                worker_count=str(len(worker_dirs)),
                failed_workers=", ".join(failed_workers) if failed_workers else "无",
                fix_directives=json.dumps([d.model_dump() for d in fix_directives], ensure_ascii=False) if fix_directives else "无",
                deepflow_root=str(self.blackboard_path.parent.parent),
            )
        except FileNotFoundError:
            prompt = self._build_integrate_prompt(plan, worker_dirs, fix_directives)

        _root = self.blackboard_path.parent.parent
        _label = f"deliver_integrate_{self.wp.wp_id}"
        return {
            "runtime": "subagent",
            "mode": "run",
            "label": _label,
            "task": auto_bootstrap(_root, self.stages_dir, prompt, _label),
            "thinking": "high",
        }

    def _build_integrate_prompt(
        self,
        plan: ExecutionPlan,
        worker_dirs: list[str],
        fix_directives: list[FixDirective] | None = None,
    ) -> str:
        """构建 Integrate Agent prompt。"""
        shared_rules = self._load_shared_rules()
        rules_section = f"\n\n## 共享规则（必须遵守）\n{shared_rules}" if shared_rules else ""
        output_dir = self.stages_dir / "integrated_draft"

        fix_section = ""
        if fix_directives:
            fix_items = "\n".join(
                f"- [{d.priority}] {d.target}: {d.issue} → {d.fix_instruction}"
                for d in fix_directives
            )
            fix_section = f"""
## 修复指令（来自 Validate Judge）
{fix_items}

请根据以上修复指令进行定向修复。
"""

        return f"""你是 Deliver Pro 的 Integrate Agent。

## 任务
组装所有 Worker 输出为统一交付物草稿。

## 输入
- 执行计划: {self.stages_dir / "execution_plan.json"}
- Worker 输出目录:
{chr(10).join(f'  - {d}' for d in worker_dirs)}

## 输出目录
{output_dir}

必须产出:
1. DELIVERABLE.md — 组装后的主产物
2. integration_report.json — 组装报告

## 组装前检查
1. 所有 Worker 输出文件存在且格式合规
2. 编程场景: MANIFEST 接口对齐（provides vs requires）
3. 报告场景: 术语一致性、数据交叉引用一致

## 组装后验证
- 编程场景: exec 运行集成测试 + lint
- 报告场景: 术语扫描 + 数据一致性检查
{fix_section}

## 铁律
1. 不修改 Worker 原始输出（只组装 + 格式调整）
2. 生成者 ≠ 验证者（你是组装者，不是验证者）

请直接开始工作。
"""

    def verify_integrate_output(
        self,
        output_dir: Path,
        plan: ExecutionPlan | None = None,
    ) -> tuple[bool, str]:
        """
        验证 Integrate Agent 输出。

        P1-3: Added completeness verification — workers count, retention,
        coverage gaps consistency. If plan is not provided, loads from blackboard.

        Returns:
            (passed, error_message)
        """
        # P1-3: Auto-load plan from blackboard if not provided
        if plan is None:
            try:
                plan = self.load_execution_plan()
                logger.info("P1-3: Auto-loaded execution plan from blackboard for verification")
            except Exception as e:
                logger.warning(f"P1-3: Could not load execution plan from blackboard: {e}")
                logger.warning("P1-3: Skipping completeness verification (plan unavailable)")

        # 检查必需文件
        deliverable = output_dir / "DELIVERABLE.md"
        report = output_dir / "integration_report.json"

        if not deliverable.exists():
            return False, "integrated_draft/DELIVERABLE.md not found"

        if not report.exists():
            return False, "integrated_draft/integration_report.json not found"

        # 读取并验证 integration_report.json
        try:
            from domains.deliver_pro.utils.safe_json_loader import SafeJsonLoader
            from domains.deliver_pro.contracts.integration_report import IntegrationReport
            result = SafeJsonLoader.load(report, IntegrationReport, mtime_window=0)
            if result.state != "ok":
                return False, f"integration_report.json corrupted: {result.state}"
            report_obj = result.parsed

            if report_obj.status not in ("READY_FOR_VALIDATE", "PARTIAL"):
                return False, (
                    f"Integration status is {report_obj.status}, "
                    f"not READY_FOR_VALIDATE or PARTIAL"
                )

        except Exception as e:
            return False, f"integration_report.json validation failed: {e}"

        # P1-3: Completeness verification (when plan available)
        if plan is not None:
            expected = plan.task_count
            actual = report_obj.workers_integrated + report_obj.workers_failed
            if actual != expected:
                return False, (
                    f"Worker count mismatch: integrated({report_obj.workers_integrated}) "
                    f"+ failed({report_obj.workers_failed}) = {actual}, "
                    f"expected {expected}"
                )

            # Retention check (Code-First Assembly requires >= 0.95)
            retention = report_data.get("assembly_stats", {}).get(
                "body_retention_ratio", 1.0
            )
            if retention < 0.95:
                return False, (
                    f"Body retention ratio {retention:.3f} < 0.95 "
                    f"(Code-First Assembly invariant violated)"
                )

            # Coverage gaps should only reference failed workers
            failed_ids = set(
                t.task_id
                for t in plan.task_graph
                if t.task_id not in [
                    # integrated workers are those with successful output
                    tid
                    for tid in self.state.completed_tasks
                ]
            )
            gaps = report_obj.coverage.get("gaps", [])
            for gap in gaps:
                if gap not in failed_ids:
                    return False, (
                        f"Coverage gap '{gap}' references a non-failed worker"
                    )

        self.state.transition_to(PipelinePhase.VALIDATING)
        self.state.round_count = 1
        self._save_state()

        logger.info(
            f"Phase 3 verified: integrated {report_obj.workers_integrated} workers, "
            f"failed={report_obj.workers_failed}, coverage={report_obj.coverage_ratio:.1%}"
        )
        return True, ""

    # ========================================================================
    # Phase 4: Validate (Loop ≤5 轮)
    # ========================================================================

    def prepare_validate_spawn(
        self,
        plan: ExecutionPlan,
        round_num: int = 1,
    ) -> dict[str, Any]:
        """
        Phase 4: 准备 Validate Judge 的 spawn 参数。

        Validate Judge 独立评估交付物质量，输出 PASS/CONDITIONAL/FAIL + fix_directives。

        Args:
            plan: 执行计划
            round_num: 当前轮次

        Returns:
            sessions_spawn 参数 dict
        """
        # 契约笼子：幂等前置状态转换（LLM 跳步不崩）
        if self.state.phase == PipelinePhase.INTEGRATING:
            self.state.transition_to(PipelinePhase.VALIDATING)
            self._save_state()

        # 尝试加载 prompt 模板
        try:
            prompt = load_prompt(
                "deliver_validate",
                wp_id=self.wp.wp_id,
                round_count=str(round_num),
                max_rounds=str(MAX_VALIDATE_ROUNDS),
                deepflow_root=str(self.blackboard_path.parent.parent),
            )
        except FileNotFoundError:
            prompt = self._build_validate_prompt(plan, round_num)

        _root = self.blackboard_path.parent.parent
        _label = f"deliver_validate_{self.wp.wp_id}_r{round_num}"
        return {
            "runtime": "subagent",
            "mode": "run",
            "label": _label,
            "task": auto_bootstrap(_root, self.stages_dir, prompt, _label),
            "thinking": "high",
        }

    def _build_validate_prompt(self, plan: ExecutionPlan, round_num: int) -> str:
        """构建 Validate Judge prompt（fallback）。"""
        shared_rules = self._load_shared_rules()
        rules_section = f"\n\n## 共享规则（必须遵守）\n{shared_rules}" if shared_rules else ""
        # 收集 AC 列表
        ac_list = []
        for task in plan.task_graph:
            for ac in task.acceptance_criteria:
                ac_list.append(f"- [{task.task_id}] {ac}")

        return f"""你是 Deliver Pro 的 Validate Judge（独立质量裁判）。

## 任务
独立评估交付物质量，输出判定结果。

## 输入
- WP 文件: {self.data_dir / "wp.json"}
- 执行计划: {self.stages_dir / "execution_plan.json"}
- 交付物草稿: {self.stages_dir / "integrated_draft"}

## 输出
写入: {self.stages_dir / "validation_result.json"}

## 评分维度（6 维度，每维度 1-5 分）
1. completeness（完整性，权重 0.25）
2. correctness（正确性，权重 0.25）
3. credibility（可信度，权重 0.20）
4. actionability（可操作性，权重 0.15）
5. consistency（一致性，权重 0.10）
6. professionalism（专业性，权重 0.05）

## 验收标准（来自 ExecutionPlan）
{chr(10).join(ac_list) if ac_list else "（无具体 AC）"}

## 门禁规则
- PASS: weighted_score ≥ 3.5 且无维度 < 3
- CONDITIONAL: weighted_score ≥ 3.0 且无维度 < 2
- FAIL: weighted_score < 3.0 或任意维度 < 2

## should_continue 判断
- true: 有可修复项 + 有进展 + 修复成本合理
- false: 无可修复项 / 无进展 / 已达边际收益上限

## 当前轮次
Round {round_num}/{MAX_VALIDATE_ROUNDS}

## 输出格式
```json
{{
  "round": {round_num},
  "verdict": "PASS|CONDITIONAL|FAIL",
  "scores": {{
    "completeness": {{"score": 4, "max": 5, "weight": 0.25, "notes": "..."}},
    "correctness": {{"score": 4, "max": 5, "weight": 0.25, "notes": "..."}},
    "credibility": {{"score": 4, "max": 5, "weight": 0.20, "notes": "..."}},
    "actionability": {{"score": 4, "max": 5, "weight": 0.15, "notes": "..."}},
    "consistency": {{"score": 3, "max": 5, "weight": 0.10, "notes": "..."}},
    "professionalism": {{"score": 3, "max": 5, "weight": 0.05, "notes": "..."}}
  }},
  "weighted_score": 3.8,
  "fix_directives": [
    {{"target": "T-001", "issue": "...", "fix_instruction": "...", "priority": "high"}}
  ],
  "has_fixable": true,
  "should_continue": true,
  "should_continue_reason": "..."
}}
```

## 铁律
1. 你是独立裁判，不参与生成
2. 数值门禁是硬约束，不可被 LLM 判断覆盖
3. 无证据不交付（编程要有测试输出，报告要有数据源）

请直接输出 JSON。
"""

    def verify_validate_output(self, verdict_data: dict) -> tuple[bool, str, ValidationVerdict | None]:
        """
        验证 Validate Judge 输出。

        Returns:
            (passed, error_message, verdict)
        """
        try:
            verdict = ValidationVerdict.model_validate(verdict_data)

            # 独立门禁验证：用代码计算 weighted_score 和 verdict，与 LLM 输出交叉验证
            computed_score = ValidationVerdict.compute_weighted_score(verdict.scores)
            computed_verdict = ValidationVerdict.compute_verdict(computed_score, verdict.scores)
            if computed_verdict != verdict.verdict:
                logger.warning(
                    f"Gate mismatch: LLM says {verdict.verdict}, "
                    f"code computes {computed_verdict} (score={computed_score:.2f}). "
                    f"Using code verdict (hard constraint)."
                )
                verdict.verdict = computed_verdict
                verdict.weighted_score = computed_score

            # N6: Information Conservation Gate
            # Check AC coverage from integration report
            integration_report_path = self.stages_dir / "integrated_draft" / "integration_report.json"
            if integration_report_path.exists():
                try:
                    from domains.deliver_pro.utils.safe_json_loader import SafeJsonLoader
                    from domains.deliver_pro.contracts.integration_report import IntegrationReport
                    result = SafeJsonLoader.load(integration_report_path, IntegrationReport, mtime_window=0)
                    if result.state == "ok":
                        report_data = result.data
                    else:
                        logger.warning(f"integration_report.json corrupted: {result.state}, skipping AC coverage check")
                        report_data = {}
                    coverage = report_data.get("coverage", {})
                    # Fix B-1: compute ratio from actual fields (covered/acceptance_criteria_total)
                    ac_total = coverage.get("acceptance_criteria_total", 0)
                    ac_covered = coverage.get("covered", 0)
                    ac_coverage_ratio = ac_covered / ac_total if ac_total > 0 else 0.0
                    # AC coverage < 80% → auto FAIL
                    if ac_coverage_ratio < 0.8:
                        logger.error(
                            f"N6: AC coverage {ac_coverage_ratio:.2%} < 80%, auto FAIL"
                        )
                        verdict.verdict = "FAIL"
                        verdict.should_continue = False
                except Exception as e:
                    logger.warning(f"N6: Could not read integration report for AC check: {e}")

            # 写入修正后的验证结果（不是原始 verdict_data）
            verdict_path = self.stages_dir / "validation_result.json"
            verdict_path.write_text(
                verdict.model_dump_json(indent=2),
                encoding="utf-8",
            )

            # 状态转换：INTEGRATING → VALIDATING
            # （如果是 FIX_LOOP 回来的，状态已经在 INTEGRATING）
            if self.state.phase == PipelinePhase.INTEGRATING:
                self.state.transition_to(PipelinePhase.VALIDATING)

            # 更新状态
            self.state.validation_score = verdict.weighted_score
            self.state.last_verdict = verdict.verdict
            self._save_state()

            logger.info(
                f"Phase 4 (round {verdict.round}): verdict={verdict.verdict}, "
                f"score={verdict.weighted_score:.2f}, continue={verdict.should_continue}"
            )
            return True, "", verdict

        except Exception as e:
            return False, f"ValidationVerdict validation failed: {e}", None

    def decide_validate_loop(self, verdict: ValidationVerdict) -> str:
        """
        决定 Validate Loop 的下一步。

        Returns:
            "pass" — 进入 Phase 5
            "fix" — 进入修复轮次（spawn Integrate with fix_directives）
            "stop" — 停止循环，进入 Phase 5（标记 unvalidated）
        """
        # Guard: null verdict
        if verdict is None:
            logger.error("decide_validate_loop called with None verdict")
            return "stop"

        # 硬约束检查
        if verdict.is_pass:
            return "pass"

        # Guard: round_count may be None (first run)
        current_round = self.state.round_count or 0
        if current_round >= MAX_VALIDATE_ROUNDS:
            logger.warning(f"Max validate rounds ({MAX_VALIDATE_ROUNDS}) reached")
            return "stop"

        # Guard: should_continue may be None
        if verdict.should_continue is False:
            logger.info(f"Validate Judge decided to stop: {verdict.should_continue_reason}")
            return "stop"

        # Guard: has_fixable may be None
        if not verdict.has_fixable:
            logger.info("No fixable issues, but verdict is not PASS")
            return "stop"

        # 进入修复轮次（带状态转换保护）
        try:
            if self.state.phase != PipelinePhase.FIX_LOOP:
                self.state.transition_to(PipelinePhase.FIX_LOOP)
        except (ValueError, AttributeError) as e:
            logger.warning(f"State transition to FIX_LOOP failed: {e}, forcing state")
            self.state.phase = PipelinePhase.FIX_LOOP

        self.state.round_count = current_round + 1
        self._save_state()

        logger.info(f"Entering fix loop round {self.state.round_count}")
        return "fix"

    def prepare_fix_integrate_spawn(
        self,
        plan: ExecutionPlan,
        verdict: ValidationVerdict,
    ) -> dict[str, Any]:
        """
        准备修复轮次的 Integrate Agent spawn 参数。

        状态机: FIX_LOOP → (spawn Integrate) → FIX_LOOP → VALIDATING
        注意：修复轮次不改变状态为 INTEGRATING，保持在 FIX_LOOP，
        等 Integrate 完成后由 verify_fix_integrate_output 转换到 VALIDATING。
        """
        # Guard: null verdict
        if verdict is None:
            raise ValueError("prepare_fix_integrate_spawn requires a valid verdict")

        # 收集 Worker 输出路径
        worker_dirs = []
        for task in plan.task_graph:
            task_dir = self.worker_outputs_dir / task.task_id
            if task_dir.exists():
                worker_dirs.append(str(task_dir))

        # Guard: empty worker_dirs
        if not worker_dirs:
            raise ValueError(f"No worker output directories found in {self.worker_outputs_dir}")

        # 构建 prompt（带 fix_directives）
        fix_directives = verdict.fix_directives or []
        prompt = self._build_integrate_prompt(plan, worker_dirs, fix_directives=fix_directives)

        # V3: 重入 INTEGRATING 前失效下游 artifact
        # （否则旧 validation_result.json 会让推导跳到 PACKAGING，带着旧 verdict 打包）
        # DryRun D-P2-3: 失效前备份旧 verdict，防止 fix-integrate 失败后丢失修复依据
        from domains.deliver_pro.phase_deriver import invalidate_downstream
        _vr_path = self.stages_dir / "validation_result.json"
        if _vr_path.exists():
            try:
                import shutil
                shutil.copy2(str(_vr_path), str(self.stages_dir / "validation_result.json.bak"))
            except Exception as e:
                logger.warning(f"Failed to backup validation_result.json: {e}")
        invalidate_downstream(self.deliver_pro_dir, from_phase="INTEGRATING")

        # Guard: round_count may be None
        round_num = self.state.round_count or 1

        # 不改变状态（保持在 FIX_LOOP）
        self._save_state()

        _deepflow_root = self.blackboard_path.parent.parent
        _label = f"deliver_fix_integrate_{self.wp.wp_id}_r{round_num}"
        return {
            "runtime": "subagent",
            "mode": "run",
            "label": _label,
            "task": auto_bootstrap(_deepflow_root, self.stages_dir, prompt, _label),
            "thinking": "high",
        }

    def verify_fix_integrate_output(self, output_dir: Path) -> tuple[bool, str]:
        """
        验证修复轮次的 Integrate Agent 输出。

        状态转换: FIX_LOOP → VALIDATING
        """
        # 检查必需文件
        deliverable = output_dir / "DELIVERABLE.md"
        if not deliverable.exists():
            return False, "integrated_draft/DELIVERABLE.md not found after fix"

        # 状态转换: FIX_LOOP → VALIDATING
        if self.state.phase == PipelinePhase.FIX_LOOP:
            self.state.transition_to(PipelinePhase.VALIDATING)
            self._save_state()

        logger.info(f"Fix integrate verified, transitioning to VALIDATING (round {self.state.round_count})")
        return True, ""

    # ========================================================================
    # Phase 5: Package
    # ========================================================================

    def prepare_package_spawn(
        self,
        plan: ExecutionPlan,
        verdict: ValidationVerdict | None = None,
    ) -> dict[str, Any]:
        """
        Phase 5: 准备 Package Agent 的 spawn 参数。

        Package Agent 最终打包 + 组件级诚实交付。

        Returns:
            sessions_spawn 参数 dict
        """
        self.state.transition_to(PipelinePhase.PACKAGING)
        self._save_state()

        # V3: 从文件系统推导 worker 进度（fail_count 用于 prompt 渲染）
        progress = self._derive_worker_progress(plan)
        derived_fail_count = len(progress["failed"]) + len(progress["blocked"])

        # 尝试加载 prompt 模板
        try:
            prompt = load_prompt(
                "deliver_package",
                wp_id=self.wp.wp_id,
                delivery_status="COMPLETE" if (verdict and verdict.is_pass) else "PARTIAL",
                final_score=f"{verdict.weighted_score:.1f}" if verdict else "N/A",
                pass_count=str(len(progress["completed"])),
                fail_count=str(derived_fail_count),
                total=str(plan.task_count),
                deepflow_root=str(self.blackboard_path.parent.parent),
            )
        except FileNotFoundError:
            prompt = self._build_package_prompt(plan, verdict)

        _deepflow_root = self.blackboard_path.parent.parent
        _label = f"deliver_package_{self.wp.wp_id}"
        return {
            "runtime": "subagent",
            "mode": "run",
            "label": _label,
            "task": auto_bootstrap(_deepflow_root, self.stages_dir, prompt, _label),
            "thinking": "medium",
        }

    def _build_package_prompt(
        self,
        plan: ExecutionPlan,
        verdict: ValidationVerdict | None = None,
    ) -> str:
        """构建 Package Agent prompt（fallback）。"""
        shared_rules = self._load_shared_rules()
        rules_section = f"\n\n## 共享规则（必须遵守）\n{shared_rules}" if shared_rules else ""
        verdict_info = ""
        if verdict:
            verdict_info = f"""
## 质量评估
- 轮次: {verdict.round}
- 判定: {verdict.verdict}
- 分数: {verdict.weighted_score:.2f}
"""

        # 收集任务状态（V3: 从文件系统推导）
        progress = self._derive_worker_progress(plan)
        task_status = []
        for task in plan.task_graph:
            if task.task_id in progress["completed"]:
                status = "PASS"
            elif task.task_id in progress["blocked"]:
                status = "BLOCKED"
            else:
                status = "FAILED"
            task_status.append(f"- {task.task_id}: {status}")

        return f"""你是 Deliver Pro 的 Package Agent。

## 任务
最终打包 + 组件级诚实交付。

## 输入
- WP 文件: {self.data_dir / "wp.json"}
- 交付物草稿: {self.stages_dir / "integrated_draft"}
- Worker 输出: {self.worker_outputs_dir}
{verdict_info}

## 输出
1. 最终交付物: {self.stages_dir / "final_deliverable"}
2. 交付清单: {self.stages_dir / "delivery_manifest.json"}

## 任务状态
{chr(10).join(task_status)}

## 交付逻辑
- 全部 PASS → 完整交付
- 部分 FAIL + 组件独立 → 交付成功部分 + 失败报告
- 部分 FAIL + 核心依赖缺失 → 不交付 + 失败报告 + 行动选项

## delivery_manifest.json 格式
```json
{{
  "wp_id": "{self.wp.wp_id}",
  "delivery_status": "COMPLETE|PARTIAL|FAILED",
  "components": [
    {{"task_id": "T-001", "title": "...", "status": "PASS|FAILED", "artifacts": ["..."]}}
  ],
  "validation_summary": {{
    "rounds_run": {verdict.round if verdict else 0},
    "final_score": {verdict.weighted_score if verdict else 0},
    "verdict": "{verdict.verdict if verdict else 'N/A'}"
  }}
}}
```

## 铁律
1. 诚实优于完美 — 宁可承认不足，不编造数据
2. 组件级独立评估 — 每个组件单独判定状态

请直接开始工作。
"""

    # ========================================================================
    # ADR-009: Track JSON Generation (Post-Phase 5)
    # ========================================================================

    def generate_track_json(self) -> None:
        """
        ADR-009: 从 DELIVERABLE.md 提取 track.json。

        在 Phase 5 (Package) 验证通过后、写入 .completed 之前调用。
        提取失败 → log warning，不阻断交付。
        """
        if not _HAS_TRACK_EXTRACTOR:
            logger.info("ADR-009: md_track_extractor not available, skipping track.json generation")
            return

        deliverable_path = self.stages_dir / "final_deliverable" / "DELIVERABLE.md"
        if not deliverable_path.exists():
            logger.warning("ADR-009: DELIVERABLE.md not found, skipping track.json")
            return

        try:
            md_content = deliverable_path.read_text(encoding="utf-8")

            # L1: Validate structure
            passed, msg, warnings = validate_md_structure(md_content, "deliver_pro")
            if not passed:
                logger.warning(f"ADR-009: MD validation failed: {msg}")
                return
            if warnings:
                logger.info(f"ADR-009: MD validation warnings: {warnings}")

            # L2: Extract track.json
            track_data = extract_track_json(md_content, "deliver_pro")

            # Write via direct file I/O (extractor is pure function)
            track_path = self.stages_dir / "deliver_track.json"
            track_path.write_text(
                json.dumps(track_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            logger.info(
                f"ADR-009: track.json generated — "
                f"req_count={track_data['metrics']['req_count']}, "
                f"sections={track_data['metrics']['section_count']}, "
                f"gate={track_data['gate_summary']}"
            )

        except ValueError as e:
            logger.warning(f"ADR-009: track extraction failed (ValueError): {e}")
        except Exception as e:
            logger.warning(f"ADR-009: unexpected error during track generation: {e}")

    # ========================================================================
    # Worker 故障恢复
    # ========================================================================

    def prepare_diagnosis_spawn(
        self,
        error: WorkerError,
        task: TaskNode,
    ) -> dict[str, Any]:
        """
        Worker 失败时，准备 LLM 诊断的 spawn 参数。

        LLM 端到端诊断，不预定义故障类型（废除 F1-F8）。

        Args:
            error: Worker 错误信息
            task: 失败的任务定义

        Returns:
            sessions_spawn 参数 dict
        """
        recovery_history_str = ""
        if error.recovery_history:
            recovery_history_str = "\n".join(
                f"- Round {r.get('round', '?')}: {r.get('action', '?')} → {r.get('result', '?')}"
                for r in error.recovery_history
            )

        prompt = f"""你是 Deliver Pro 的故障诊断专家。

## 任务
诊断 Worker 失败原因，生成恢复方案。

## 失败信息
- Task ID: {error.task_id}
- 错误类型: {error.error_type}
- 错误消息: {error.message}
- 上下文: {json.dumps(error.context, ensure_ascii=False)}

## 任务定义
- 标题: {task.title}
- 场景: {task.scenario_type}
- 依赖: {task.depends_on}

## 已尝试的恢复策略
{recovery_history_str or "（首次失败）"}

## 输出格式
```json
{{
  "task_id": "{error.task_id}",
  "diagnosis": "LLM 的诊断结果",
  "recovery_action": "retry|switch_model|split_wp|simplify|add_context|skip",
  "specific_changes": "具体的修改建议",
  "confidence": 0.7,
  "suggested_model": "qwen3.7-plus"
}}
```

## 恢复策略说明
- retry: 原样重试（适用于临时错误）
- switch_model: 换模型（适用于模型能力不足）
- split_wp: 拆分任务（适用于任务过复杂）
- simplify: 简化任务（适用于范围过大）
- add_context: 补充上下文（适用于信息不足）
- skip: 跳过（标记 FAILED，适用于不可恢复）

请直接输出 JSON。
"""

        _deepflow_root = self.blackboard_path.parent.parent
        _label = f"deliver_diagnosis_{self.wp.wp_id}_{error.task_id}"
        return {
            "runtime": "subagent",
            "mode": "run",
            "label": _label,
            "task": auto_bootstrap(_deepflow_root, self.stages_dir, prompt, _label),
            "thinking": "medium",
        }

    def verify_diagnosis_output(
        self,
        diagnosis_data: dict,
    ) -> tuple[bool, str, RecoveryAction | None]:
        """
        验证 LLM 诊断输出。

        Returns:
            (passed, error_message, recovery_action)
        """
        try:
            action = RecoveryAction.model_validate(diagnosis_data)
            logger.info(
                f"Diagnosis for {action.task_id}: action={action.recovery_action.value}, "
                f"confidence={action.confidence:.2f}"
            )
            return True, "", action
        except Exception as e:
            return False, f"RecoveryAction validation failed: {e}", None

    def verify_package_output(self, manifest_path: Path) -> tuple[bool, str, DeliveryManifest | None]:
        """
        B-4 fix: 验证 Package 阶段的 delivery_manifest.json。

        Returns:
            (passed, error_message, manifest)
        """
        if not manifest_path.exists():
            return False, f"delivery_manifest.json not found at {manifest_path}", None
        try:
            from domains.deliver_pro.utils.safe_json_loader import SafeJsonLoader
            from domains.deliver_pro.contracts.delivery_manifest import DeliveryManifest
            result = SafeJsonLoader.load(manifest_path, DeliveryManifest, mtime_window=0)
            if result.state != "ok":
                return False, f"delivery_manifest.json corrupted: {result.state}", None
            manifest = result.parsed
            logger.info(
                f"Package validated: status={manifest.delivery_status}, "
                f"files={len(manifest.deliverables)}"
            )
            return True, "", manifest
        except Exception as e:
            return False, f"DeliveryManifest validation failed: {e}", None

    def should_retry_worker(self, task_id: str, attempts: int) -> bool:
        """判断是否应该重试 Worker。"""
        return attempts < MAX_WORKER_RECOVERY_ATTEMPTS

    def mark_worker_failed(
        self,
        task_id: str,
        reason: str,
        failure_class: str | None = None,
    ) -> None:
        """标记 Worker 为失败状态。

        V3: 失败事实写入 MANIFEST.json（文件系统即真相），
        state 仅作日志记录。

        Args:
            task_id: 任务 ID
            reason: 失败原因
            failure_class: 可选失败分类（如 "contract_violation" / "substance_failure"）。
                未提供时不写入该字段（向后兼容：无该字段 = 未分类 = 不可重试）。
        """
        # 写入 MANIFEST（推导层的数据源）
        manifest_path = self.worker_outputs_dir / task_id / "MANIFEST.json"
        try:
            if manifest_path.exists():
                from domains.deliver_pro.utils.safe_json_loader import SafeJsonLoader
                from domains.deliver_pro.contracts.worker_task import WorkerOutputMeta
                result = SafeJsonLoader.load(manifest_path, WorkerOutputMeta, mtime_window=0)
                if result.state == "ok":
                    data = result.data
                else:
                    # MANIFEST 损坏，备份后重新创建
                    # 注意：SafeJsonLoader 可能已经备份了文件，所以先检查是否还存在
                    logger.warning(f"MANIFEST corrupted for {task_id} ({result.state}), backing up and recreating")
                    if manifest_path.exists():
                        backup_path = manifest_path.with_suffix(".corrupted")
                        manifest_path.rename(backup_path)
                    data = {"task_id": task_id}
            else:
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                data = {"task_id": task_id}
            data["status"] = "FAILED"
            data["failure_reason"] = reason
            if failure_class is not None:
                data["failure_class"] = failure_class
            atomic_write_json(manifest_path, data)
        except Exception as e:
            logger.error(f"Failed to write FAILED MANIFEST for {task_id}: {e}")

        # 日志记录（不作决策依据）
        self.state.mark_task_failed(task_id)
        if task_id in self.state.running_tasks:
            self.state.running_tasks.remove(task_id)
        self._save_state()
        logger.warning(f"Worker {task_id} marked as FAILED: {reason}")

    # ========================================================================
    # 状态查询
    # ========================================================================

    def get_pipeline_summary(self) -> dict[str, Any]:
        """获取流水线摘要。"""
        return {
            "wp_id": self.wp.wp_id,
            "phase": self.state.phase.value,
            "completed_tasks": self.state.completed_tasks,
            "failed_tasks": self.state.failed_tasks,
            "pending_tasks": self.state.pending_tasks,
            "running_tasks": self.state.running_tasks,
            "round_count": self.state.round_count,
            "validation_score": self.state.validation_score,
            "last_verdict": self.state.last_verdict,
            "is_terminal": self.state.is_terminal,
        }

    def load_execution_plan(self) -> ExecutionPlan | None:
        """从 Blackboard 加载执行计划。"""
        plan_path = self.stages_dir / "execution_plan.json"
        if not plan_path.exists():
            return None
        try:
            from domains.deliver_pro.utils.safe_json_loader import SafeJsonLoader
            from domains.deliver_pro.contracts.execution_plan import ExecutionPlan
            result = SafeJsonLoader.load(plan_path, ExecutionPlan, mtime_window=0)
            if result.state == "ok":
                return result.parsed
            logger.error(f"execution_plan.json corrupted: {result.state}")
            return None
        except Exception as e:
            logger.error(f"Failed to load execution_plan: {e}")
            return None

    def load_validation_verdict(self) -> ValidationVerdict | None:
        """从 Blackboard 加载验证结果。"""
        verdict_path = self.stages_dir / "validation_result.json"
        if not verdict_path.exists():
            return None
        try:
            from domains.deliver_pro.utils.safe_json_loader import SafeJsonLoader
            from domains.deliver_pro.contracts.validation_verdict import ValidationVerdict
            result = SafeJsonLoader.load(verdict_path, ValidationVerdict, mtime_window=0)
            if result.state == "ok":
                return result.parsed
            logger.error(f"validation_result.json corrupted: {result.state}")
            return None
        except Exception as e:
            logger.error(f"Failed to load validation_result: {e}")
            return None
