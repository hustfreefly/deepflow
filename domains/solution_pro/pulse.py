"""Solution Pulse — Solution Pro 脉冲调度核心（确定性状态机）。

架构（2026-07-25，替代长驻 yield orchestrator）：
    cron 每 5min 点火 isolated session → pulse agent（depth-1）exec 跑 pulse()
    → 动作契约落盘 _solution_pulse_actions.json → agent 逐条 spawn
    → confirm 回执 → session 结束。

设计原则：
- 调度决策全部在 Python（确定性）：相位推进、stall 检测、重试预算、终态判定
- LLM（pulse agent）只做：exec pulse → 逐条 spawn → confirm → 发告警
- 不依赖 session 长寿 / 事件投递：文件系统是唯一真相
- 契约笼子：所有落盘经 Pydantic 验证（extra=forbid），原子写，单实例锁

状态文件（blackboard/{session_id}/ 下）：
- _solution_pulse_state.json   状态机（SolutionPulseState 验证）
- _solution_pulse_actions.json 本次动作+告警（SolutionPulseReport 验证）
- _solution_pulse.lock         单实例锁（fcntl，holder 死亡自动释放）
- .completed                   完成标记（快速通道）
- .failed                      终败标记
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import time
from pathlib import Path

from core.utils.atomic_io import atomic_write_json

from .contracts.pulse_report import (
    MODULE_REQUIRED_STAGES,
    PHASES,
    REVIEW_AGENTS,
    ModuleDispatch,
    SolutionPulseAction,
    SolutionPulseAlert,
    SolutionPulseReport,
    SolutionPulseState,
    SolutionPulseSummary,
)

logger = logging.getLogger(__name__)

# ── 常量（2026-07-25 V3.3：one-step 模块执行器模式）──
MODULE_RESPAWN_COOLDOWN_SECONDS = 240  # 例行重召唤冷却：模块是一步执行器，冷却到点就再召唤
MODULE_NO_PROGRESS_SECONDS = 1800      # 30min 无任何文件进展 → 计一次失败重试
MODULE_MAX_RETRIES = 3                 # 失败重试预算（仅无进展时消耗，例行重召唤免费）
REVIEW_TIMEOUT_SECONDS = 3600      # 审查 Agent 60min 无产出 → 跳过（非门控）
ORPHAN_DISPATCH_WINDOW_SECONDS = 600  # dispatch 未确认超 10min → 回滚重派（pulse agent 猝死恢复）
ZERO_PROGRESS_ALERT_THRESHOLD = 6  # 连续 6 次 pulse 零进展（30min）→ WARN 告警
PULSE_LOCK_STALE_SECONDS = 600     # 锁持有超 10min → 告警（holder 疑似挂起）
MAX_SPAWN_PER_PULSE = 2            # 单 pulse 最多 spawn 数（review 相位=2）

PULSE_STATE_FILENAME = "_solution_pulse_state.json"
PULSE_ACTIONS_FILENAME = "_solution_pulse_actions.json"
PULSE_LOCK_FILENAME = "_solution_pulse.lock"
PULSE_COMPLETED_FILENAME = ".completed"
PULSE_FAILED_FILENAME = ".failed"

# pulse 每轮 spawn 时重写的 prompt 文件（从 mtime 进展检测中排除，定义见下方文件表之后）

# 各相位模块 prompt 文件（写入 blackboard stages/ 供 Module Agent 读取）
MODULE_PROMPT_FILES = {
    "planning": "planning_module.md",
    "research": "research_module.md",
    "summary": "summary_module.md",
}
REVIEW_PROMPT_FILES = {
    "adversarial_reviewer": "adversarial_quality_reviewer.md",
    "consistency_checker": "cross_module_consistency_checker.md",
}
# 审查产出 stage
REVIEW_OUTPUT_STAGES = {
    "adversarial_reviewer": "adversarial_review_summary",
    "consistency_checker": "consistency_check",
}

# pulse 每轮 spawn 时重写的 prompt 文件（从 mtime 进展检测中排除）
_PULSE_SELF_WRITTEN_FILES: frozenset[str] = frozenset(
    set(MODULE_PROMPT_FILES.values()) | set(REVIEW_PROMPT_FILES.values())
)


class PulseLocked(Exception):
    """单实例锁冲突。"""

    def __init__(self, alert: dict | None = None):
        super().__init__("pulse locked")
        self.alert = alert


class SolutionPulse:
    """Solution Pro 脉冲调度器（每次实例化 = 一次 tick）。"""

    def __init__(self, session_id: str, blackboard_root: Path | None = None):
        self.session_id = session_id
        if blackboard_root is None:
            # 默认 .deepflow/blackboard/
            blackboard_root = Path(__file__).resolve().parent.parent.parent / "blackboard"
        self.blackboard_root = Path(blackboard_root)
        self.session_dir = self.blackboard_root / session_id
        self.stages_dir = self.session_dir / "stages"
        self.state_path = self.session_dir / PULSE_STATE_FILENAME
        self.actions_path = self.session_dir / PULSE_ACTIONS_FILENAME
        self.lock_path = self.session_dir / PULSE_LOCK_FILENAME
        self.completed_path = self.session_dir / PULSE_COMPLETED_FILENAME
        self.failed_path = self.session_dir / PULSE_FAILED_FILENAME
        self.deepflow_root = Path(__file__).resolve().parent.parent.parent

    # ── 基础设施 ──────────────────────────────────────────────

    def _acquire_lock(self):
        """单实例文件锁（fcntl.flock 非阻塞，holder 死亡自动释放）。"""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        fh = open(self.lock_path, "a+")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            alert = None
            try:
                age = time.time() - self.lock_path.stat().st_mtime
                if age > PULSE_LOCK_STALE_SECONDS:
                    alert = {
                        "severity": "WARN",
                        "code": "LOCK_STALE",
                        "message": f"pulse 锁已被持有 {int(age)}s（>{PULSE_LOCK_STALE_SECONDS}s），holder 疑似挂起",
                    }
            except Exception:
                pass
            raise PulseLocked(alert)
        # 刷新锁文件 mtime
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        return fh

    # ── 状态读写（契约笼子）──────────────────────────────────

    def _load_state(self) -> SolutionPulseState:
        """读取状态机，不存在则初始化。损坏 → raise（不静默降级）。"""
        if not self.state_path.exists():
            now = time.time()
            return SolutionPulseState(
                session_id=self.session_id,
                phase="planning",
                modules={m: ModuleDispatch() for m in ("planning", "research", "summary")},
                review={r: ModuleDispatch() for r in REVIEW_AGENTS},
                created_at=now,
                updated_at=now,
            )
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        return SolutionPulseState(**raw)  # 契约笼子：损坏/未知字段 → ValidationError

    def _save_state(self, state: SolutionPulseState) -> None:
        state.updated_at = time.time()
        atomic_write_json(self.state_path, state.model_dump(mode="json"))

    # ── 完成判定（确定性：文件系统是唯一真相）─────────────────

    def _stage_exists(self, name: str) -> bool:
        return (self.stages_dir / f"{name}.json").exists() or (
            self.stages_dir / f"{name}.md"
        ).exists()

    def _module_output_ready(self, module: str) -> bool:
        return all(self._stage_exists(s) for s in MODULE_REQUIRED_STAGES[module])

    def _latest_stage_mtime(self) -> float | None:
        """stages/ 下最新文件 mtime（含子目录）。文件系统是唯一进展信号。

        排除 pulse 自己每轮重写的 prompt 文件——否则每次例行重召唤都会刷新
        mtime，导致无进展检测被自己骗过（永远探测不到真 stall）。
        """
        latest = None
        if not self.stages_dir.exists():
            return None
        for p in self.stages_dir.rglob("*"):
            if p.is_file() and p.name not in _PULSE_SELF_WRITTEN_FILES:
                m = p.stat().st_mtime
                if latest is None or m > latest:
                    latest = m
        return latest

    def _review_output_ready(self, reviewer: str) -> bool:
        return self._stage_exists(REVIEW_OUTPUT_STAGES[reviewer])

    # ── Prompt 落盘（spawn 前置）─────────────────────────────

    def _write_module_prompt(self, module: str) -> None:
        """把模块 prompt 从 prompts/ 拷到 blackboard stages/（变量替换）。"""
        src = Path(__file__).resolve().parent / "prompts" / MODULE_PROMPT_FILES[module]
        content = src.read_text(encoding="utf-8")
        content = content.replace("{session_id}", self.session_id)
        content = content.replace("{deepflow_root}", str(self.deepflow_root))
        self.stages_dir.mkdir(parents=True, exist_ok=True)
        (self.stages_dir / MODULE_PROMPT_FILES[module]).write_text(
            content, encoding="utf-8"
        )

    def _write_review_prompt(self, reviewer: str) -> None:
        src = Path(__file__).resolve().parent / "prompts" / REVIEW_PROMPT_FILES[reviewer]
        content = src.read_text(encoding="utf-8")
        content = content.replace("{session_id}", self.session_id)
        content = content.replace("{deepflow_root}", str(self.deepflow_root))
        # DryRun B1（Agent D）：reviewer prompt 含 {module_name}/{module_output_file}
        # 模板占位符，旧 orchestrator 显式替换，pulse 路径必须补齐，
        # 否则产出 stage 名（adversarial_review_summary）与
        # REVIEW_OUTPUT_STAGES 期望不匹配，审查产出永不被消费。
        content = content.replace("{module_name}", "summary")
        content = content.replace("{module_output_file}", "final_solution")
        self.stages_dir.mkdir(parents=True, exist_ok=True)
        (self.stages_dir / REVIEW_PROMPT_FILES[reviewer]).write_text(
            content, encoding="utf-8"
        )

    def _build_module_task(self, module: str) -> str:
        prompt_file = MODULE_PROMPT_FILES[module]
        role = {
            "planning": "Planning Module Agent（V3.1 架构，depth-2）。职责：管理 Planning 模块的执行，直接通过 sessions_spawn 创建 Worker。",
            "research": "Research Module Agent（V3.1 架构，depth-2）。职责：管理 Research 模块的执行，直接通过 sessions_spawn 创建 Worker。",
            "summary": "Summary Module Agent（V3.1 架构，depth-2）。职责：管理 Summary 模块的执行（5+1 Phase），直接通过 sessions_spawn 创建 Worker。",
        }[module]
        return (
            f"cd {self.deepflow_root} && PYTHONPATH=.\n"
            f"你执行的所有 Python 命令必须以 `cd {self.deepflow_root} && PYTHONPATH=.` 开头。\n\n"
            f"## 环境\n"
            f"- session_id: `{self.session_id}`\n"
            f"- Blackboard: `{self.session_dir}`\n\n"
            f"## 你的身份\n你是 {role}\n\n"
            f"## 你的完整指令\n"
            f"用 read 工具读取: {self.stages_dir / prompt_file}\n\n"
            f"读取后严格按照其中的指令执行所有步骤。\n"
            f"如果文件缺失 → 写入 `stages/.failed` 并立即结束。"
        )

    def _build_review_task(self, reviewer: str) -> str:
        prompt_file = REVIEW_PROMPT_FILES[reviewer]
        role = {
            "adversarial_reviewer": "Adversarial Quality Reviewer（对抗质量审查 Agent）。职责：从语义层面挑战 Solution Pro 的输出质量。",
            "consistency_checker": "Cross-Module Consistency Checker（跨模块一致性检查 Agent）。职责：验证 Planning → Research → Summary 之间的数据流一致性。",
        }[reviewer]
        return (
            f"cd {self.deepflow_root} && PYTHONPATH=.\n"
            f"你执行的所有 Python 命令必须以 `cd {self.deepflow_root} && PYTHONPATH=.` 开头。\n\n"
            f"## 环境\n"
            f"- session_id: `{self.session_id}`\n"
            f"- Blackboard: `{self.session_dir}`\n\n"
            f"## 你的身份\n你是 {role}\n\n"
            f"## 你的完整指令\n"
            f"用 read 工具读取: {self.stages_dir / prompt_file}\n\n"
            f"读取后严格按照其中的指令执行。\n"
            f"如果文件缺失 → 跳过审查/检查，直接结束。"
        )

    # ── L0 后置验证（确定性，在 pulse 内直接执行）─────────────

    def _run_post_validation(self) -> tuple[bool, dict]:
        from .blackboard import BlackboardManager
        from .post_validator import validate_solution_output

        # DryRun B2（Agent A）：必须传 base_dir，否则非默认 blackboard_root
        # 部署（含测试）下读取路径错位。
        bb = BlackboardManager(self.session_id, base_dir=self.blackboard_root)
        result = validate_solution_output(bb)
        return bool(result.get("passed")), result

    # ── 主入口：单次脉冲 ─────────────────────────────────────

    def pulse(self) -> dict:
        """单次全量扫描：推进状态机 → 动作契约落盘。

        Returns:
            SolutionPulseReport dict（同时写入 _solution_pulse_actions.json）
        """
        def _report(status, actions, alerts, summary) -> dict:
            report = SolutionPulseReport(
                pulse_id=f"spulse-{int(time.time())}",
                session_id=self.session_id,
                generated_at=time.time(),
                status=status,
                actions=[SolutionPulseAction(**a) for a in actions],
                alerts=[SolutionPulseAlert(**a) for a in alerts],
                summary=SolutionPulseSummary(**summary),
            )
            data = report.model_dump(mode="json")
            atomic_write_json(self.actions_path, data)
            return data

        def _summary_of(state: SolutionPulseState) -> dict:
            in_flight = sum(
                1 for d in list(state.modules.values()) + list(state.review.values())
                if d.status == "dispatched" and d.dispatch_confirmed
            )
            completed = [m for m, d in state.modules.items() if d.status == "completed"]
            return {
                "current_phase": state.phase,
                "completed_modules": completed,
                "in_flight": in_flight,
                "retry_counts": {
                    k: d.retry_count
                    for k, d in {**state.modules, **state.review}.items()
                    if d.retry_count > 0
                },
                "zero_progress_count": state.zero_progress_count,
            }

        # 快速通道：已完成 / 已终败（零扫描退出）
        if self.completed_path.exists():
            state = self._load_state()
            return _report("completed", [], [], _summary_of(state))
        if self.failed_path.exists():
            state = self._load_state()
            return _report("failed", [], [], _summary_of(state))

        # 单实例锁
        try:
            lock_fh = self._acquire_lock()
        except PulseLocked as e:
            state = self._load_state()
            return _report(
                "locked", [], [e.alert] if e.alert else [], _summary_of(state)
            )

        try:
            state = self._load_state()
            actions: list[dict] = []
            alerts: list[dict] = []
            progress_made = False
            now = time.time()

            # ── 孤儿 dispatch 清扫（DryRun 修复：pulse agent 在 spawn 后、confirm 前
            #    猝死时，dispatch 永远 unconfirmed → 状态机卡死。超窗回滚重派。）──
            for pool in (state.modules, state.review):
                for name, d in pool.items():
                    if (
                        d.status == "dispatched"
                        and not d.dispatch_confirmed
                        and d.last_spawned_at
                        and now - d.last_spawned_at > ORPHAN_DISPATCH_WINDOW_SECONDS
                    ):
                        d.status = "pending"
                        d.retry_count += 1
                        d.dispatch_confirmed = False
                        progress_made = True
                        alerts.append({
                            "severity": "WARN",
                            "code": "SPAWN_ROLLBACK",
                            "message": f"{name} dispatch 超 {ORPHAN_DISPATCH_WINDOW_SECONDS}s 未确认（pulse agent 疑似猝死），回滚重派（第 {d.retry_count} 次）",
                        })

            # ── 相位推进循环（每轮 pulse 尽量推进，可连续推进多相位）──
            while True:
                if state.phase in ("planning", "research", "summary"):
                    module = state.phase
                    dispatch = state.modules[module]

                    # 1) 输出已就绪 → 标记完成，推进到下一相位
                    if self._module_output_ready(module):
                        dispatch.status = "completed"
                        dispatch.completed_at = now
                        next_phases = {
                            "planning": "research",
                            "research": "summary",
                            "summary": "validate",
                        }
                        state.phase = next_phases[module]
                        state.last_progress_at = now  # 新相位获得全新无进展窗口
                        progress_made = True
                        continue

                    # 2) 文件进展检测（one-step 模块模式：mtime 是唯一进展信号）
                    latest = self._latest_stage_mtime()
                    if latest and latest > (state.last_progress_at or 0):
                        state.last_progress_at = latest
                        state.zero_progress_count = 0
                        progress_made = True

                    # 3) 无进展超 30min → 消耗失败重试预算；耗尽 → 终败
                    if (now - (state.last_progress_at or state.created_at)) > MODULE_NO_PROGRESS_SECONDS:
                        if dispatch.retry_count < MODULE_MAX_RETRIES:
                            dispatch.retry_count += 1
                            state.last_progress_at = now  # 给下一个 30min 窗口
                            progress_made = True
                            alerts.append({
                                "severity": "WARN",
                                "code": "MODULE_RETRY",
                                "message": f"模块 {module} 30min 无文件进展，失败重试 {dispatch.retry_count}/{MODULE_MAX_RETRIES}",
                            })
                        else:
                            dispatch.status = "terminal_failed"
                            state.phase = "failed"
                            state.fail_reason = f"模块 {module} 连续无进展，重试 {MODULE_MAX_RETRIES} 次耗尽"
                            alerts.append({
                                "severity": "CRITICAL",
                                "code": "TERMINAL_FAILED",
                                "message": f"模块 {module} 连续 30min×{MODULE_MAX_RETRIES} 无进展，pipeline 终败",
                            })
                            atomic_write_json(self.failed_path, {
                                "session_id": self.session_id,
                                "failed_module": module,
                                "failed_at": now,
                                "reason": "MODULE_RETRY_EXHAUSTED",
                            })
                            progress_made = True
                            continue

                    # 4) dispatch 未确认 → 等待 confirm（孤儿清扫兜底）
                    if dispatch.status == "dispatched" and not dispatch.dispatch_confirmed:
                        break

                    # 5) 例行重召唤（one-step 模块核心）：pending，或已确认且冷却已过
                    #    模块每轮生命只做一步即结束，pulse 按冷却节拍反复召唤它推进。
                    #    例行重召唤不消耗失败重试预算（只有无进展才消耗）。
                    if dispatch.status == "pending" or (
                        dispatch.status == "dispatched"
                        and dispatch.dispatch_confirmed
                        and now - (dispatch.last_spawned_at or 0) > MODULE_RESPAWN_COOLDOWN_SECONDS
                    ):
                        self._write_module_prompt(module)
                        dispatch.status = "dispatched"
                        dispatch.last_spawned_at = now
                        dispatch.dispatch_confirmed = False
                        label = f"solution_{module}_module"
                        dispatch.label = label
                        if dispatch.retry_count > 0:
                            alerts.append({
                                "severity": "INFO",
                                "code": "MODULE_RETRY",
                                "message": f"模块 {module} 第 {dispatch.retry_count} 次失败重试 spawn",
                            })
                        actions.append({
                            "module": module,
                            "action": "spawn_module",
                            "task": self._build_module_task(module),
                            "label": label,
                        })
                        progress_made = True
                    break

                elif state.phase == "validate":
                    # L0 后置验证（pulse 内直接执行，不 spawn）
                    passed, detail = self._run_post_validation()
                    if passed:
                        state.phase = "review"
                        progress_made = True
                        continue
                    state.phase = "failed"
                    state.fail_reason = "POST_VALIDATION_FAILED"
                    alerts.append({
                        "severity": "CRITICAL",
                        "code": "POST_VALIDATION_FAILED",
                        "message": f"L0 后置验证失败: {json.dumps(detail.get('summary', detail), ensure_ascii=False)[:300]}",
                    })
                    atomic_write_json(self.failed_path, {
                        "session_id": self.session_id,
                        "failed_module": "validate",
                        "failed_at": now,
                        "reason": "POST_VALIDATION_FAILED",
                        "details": detail,
                    })
                    progress_made = True
                    break

                elif state.phase == "review":
                    # 审查相位：2 个 reviewer 并行（非门控）
                    all_done = True
                    for reviewer in REVIEW_AGENTS:
                        rd = state.review[reviewer]
                        if self._review_output_ready(reviewer):
                            if rd.status != "completed":
                                rd.status = "completed"
                                rd.completed_at = now
                                progress_made = True
                            continue
                        if rd.status == "dispatched" and rd.dispatch_confirmed:
                            elapsed = now - (rd.last_spawned_at or now)
                            if elapsed > REVIEW_TIMEOUT_SECONDS:
                                # 超时 → 跳过（非门控）
                                rd.status = "completed"
                                rd.completed_at = now
                                alerts.append({
                                    "severity": "WARN",
                                    "code": "REVIEW_TIMEOUT",
                                    "message": f"审查 {reviewer} 超时（{int(elapsed)}s），按 SKIPPED 处理（非门控）",
                                })
                                progress_made = True
                            else:
                                all_done = False
                        elif rd.status == "dispatched":
                            all_done = False  # 等 confirm
                        elif rd.status == "pending":
                            self._write_review_prompt(reviewer)
                            rd.status = "dispatched"
                            rd.last_spawned_at = now
                            rd.dispatch_confirmed = False
                            label = f"solution_{reviewer}"
                            rd.label = label
                            actions.append({
                                "module": reviewer,
                                "action": "spawn_reviewer",
                                "task": self._build_review_task(reviewer),
                                "label": label,
                            })
                            progress_made = True
                            all_done = False
                    if all_done and not actions:
                        state.phase = "finalize"
                        progress_made = True
                        continue
                    break

                elif state.phase == "finalize":
                    # 写 .completed + 生成 track
                    # DryRun 修复（Agent D）：保留旧 orchestrator 的 quality_notes 语义，
                    # 把审查 verdict 写入 .completed（非门控，仅记录）
                    quality_notes = {}
                    for reviewer, stage_name in REVIEW_OUTPUT_STAGES.items():
                        for ext in (".json", ".md"):
                            p = self.stages_dir / f"{stage_name}{ext}"
                            if p.exists():
                                try:
                                    data = json.loads(p.read_text(encoding="utf-8"))
                                    quality_notes[reviewer] = data.get("overall_verdict", "UNKNOWN")
                                except Exception:
                                    quality_notes[reviewer] = "UNREADABLE"
                                break
                        else:
                            quality_notes[reviewer] = "SKIPPED"
                    progress = {
                        "session_id": self.session_id,
                        "status": "completed",
                        "completed_at": now,
                        "modules_completed": [
                            m for m, d in state.modules.items() if d.status == "completed"
                        ],
                        "quality_notes": quality_notes,
                        "architecture_version": "v3.2-pulse",
                    }
                    atomic_write_json(self.completed_path, progress)
                    # P1-2: MD-first 接线 — 生成 final_solution.md + solution_document.md
                    # ADR-009 统一兜底：pipeline 完成时渲染所有 MD 产物
                    try:
                        from .solution_living_md import render_final_solution_md
                        from .blackboard import BlackboardManager
                        _bb = BlackboardManager(self.session_id, base_dir=self.blackboard_root)
                        # 1. final_solution.md
                        final_solution = _bb.read_stage("final_solution")
                        if final_solution:
                            md_content = render_final_solution_md(final_solution)
                            md_path = self.stages_dir / "final_solution.md"
                            md_path.parent.mkdir(parents=True, exist_ok=True)
                            import tempfile, os
                            fd, tmp = tempfile.mkstemp(dir=md_path.parent, suffix=".md")
                            try:
                                os.write(fd, md_content.encode("utf-8"))
                                os.close(fd)
                                os.replace(tmp, str(md_path))
                            except Exception:
                                os.close(fd)
                                raise
                            logger.info("ADR-009: final_solution.md written to %s", md_path)
                        # 2. solution_document.md
                        solution_document = _bb.read_stage("solution_document")
                        if solution_document and isinstance(solution_document, str):
                            doc_path = self.stages_dir / "solution_document.md"
                            doc_path.parent.mkdir(parents=True, exist_ok=True)
                            import tempfile as _tf, os as _os
                            fd2, tmp2 = _tf.mkstemp(dir=doc_path.parent, suffix=".md")
                            try:
                                _os.write(fd2, solution_document.encode("utf-8"))
                                _os.close(fd2)
                                _os.replace(tmp2, str(doc_path))
                            except Exception:
                                _os.close(fd2)
                                raise
                            logger.info("ADR-009: solution_document.md written to %s", doc_path)
                    except Exception as e:
                        logger.error("ADR-009: MD rendering failed (non-blocking): %s", e)
                    # FixFlow Phase 3: Track 自动生成（失败 → raise ValueError，架构违反）
                    from . import generate_solution_track
                    track_result = generate_solution_track(str(self.session_dir))
                    if track_result is None:
                        raise ValueError(
                            f"FixFlow Phase 3 契约违反: Track 自动生成失败。"
                            f"session_dir={self.session_dir}，"
                            f"final_solution.md 缺失或 extract_track_json() 返回 None。"
                            f"根因: MD 产物不完整或 track_extractor 无法解析。"
                        )
                    state.phase = "completed"
                    progress_made = True
                    break

                else:  # completed / failed
                    break

            # ── 零进展追踪 ──
            # 注意：last_progress_at 只能由 mtime 检测（文件进展）和相位推进更新，
            # 不能在这里随 progress_made 重置——否则例行重召唤会不断刷新窗口，
            # 导致 30min 无进展重试规则永远触发不了。
            if progress_made:
                state.zero_progress_count = 0
            else:
                state.zero_progress_count += 1
                if state.zero_progress_count >= ZERO_PROGRESS_ALERT_THRESHOLD:
                    alerts.append({
                        "severity": "WARN",
                        "code": "ZERO_PROGRESS",
                        "message": f"连续 {state.zero_progress_count} 次 pulse 零进展（当前相位 {state.phase}）",
                    })

            self._save_state(state)
            status = "active" if actions else (
                "completed" if state.phase == "completed" else
                "failed" if state.phase == "failed" else "idle"
            )
            return _report(status, actions, alerts, _summary_of(state))
        finally:
            try:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            lock_fh.close()

    # ── spawn 回执（两阶段 dispatch）──────────────────────────

    def confirm_dispatches(self, results: list[dict]) -> dict:
        """pulse agent spawn 后的回执。失败的 spawn 回滚为 pending（下轮重试）。"""
        state = self._load_state()
        rolled_back = []
        confirmed = []
        for r in results:
            module = r["module"]
            ok = r["ok"]
            pool = state.modules if module in state.modules else state.review
            if module not in pool:
                continue
            dispatch = pool[module]
            if ok:
                dispatch.dispatch_confirmed = True
                confirmed.append(module)
            else:
                # 回滚：下轮 pulse 重新 spawn（消耗重试预算）
                dispatch.status = "pending"
                dispatch.dispatch_confirmed = False
                dispatch.retry_count += 1
                rolled_back.append({"module": module, "error": r.get("error")})
        self._save_state(state)
        out = {"confirmed": confirmed, "rolled_back": rolled_back}
        if rolled_back:
            out["alert"] = {
                "severity": "WARN",
                "code": "SPAWN_ROLLBACK",
                "message": f"{len(rolled_back)} 个 spawn 失败已回滚: {[r['module'] for r in rolled_back]}",
            }
        return out
