"""
DeliverOrchestrator — 批量驱动多个 WP 的 Deliver Pro 5 Phase 流水线。

按 dependency_graph.execution_layers 分层执行：
  Layer 0: 无依赖的 WP 并行
  Layer 1: 依赖 Layer 0 的 WP 并行
  ...

每个 WP 独立驱动，通过 blackboard 文件系统检查实际 phase。
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from core.utils.atomic_io import atomic_write_json

logger = logging.getLogger(__name__)

# === Pulse Scheduling V1 常量（2026-07-24 评审裁决 A1-A8 落地） ===
MAX_IN_FLIGHT = 8  # A5: 全局在途 agent 硬上限（防 429 风暴）
MAX_SPAWN_PER_PULSE = 5  # 单次 pulse spawn 上限（对齐平台 maxChildrenPerAgent 默认值）
ORPHAN_DISPATCH_WINDOW_SECONDS = 600  # A4: 未确认 dispatch 的孤儿窗口（2 个 pulse 周期）
RECORDLESS_ORPHAN_GRACE_SECONDS = 300  # F1b: 无记录孤儿空目录宽限期（正常 spawn→首文件写入 <70s 的 4x 余量）
RETRY_BUDGET = 3  # A2: task/WP 级重试预算上限
PULSE_LOCK_STALE_SECONDS = 600  # A1: 锁持有超 10min → 告警（holder 疑似挂起）
STALLED_ALERT_THRESHOLD = 3  # A7: 连续 N 次零进展 → 告警
STALLED_ALERT_COOLDOWN_SECONDS = 1800  # A7: 告警冷却 30min
PULSE_ACTIONS_FILENAME = "_pulse_actions.json"
PULSE_COMPLETED_FILENAME = ".deliver_completed.json"
PULSE_STATE_FILENAME = "_pulse_state.json"
PULSE_LOCK_FILENAME = "_pulse.lock"

# === Final Synthesis 常量（2026-07-29 架构更新） ===
DELIVERABLE_CONTRACT_FILENAME = "_deliverable_contract.json"
FINAL_GATE_REPORT_FILENAME = "_final_gate_report.json"
FINAL_DELIVERABLE_DONE_FILENAME = "_final_deliverable_done.json"
FINAL_SYNTHESIS_DIRNAME = "final_synthesis"
FINAL_GATE_SPAWNED_FILENAME = "_gate_action_spawned.json"  # Flag: gate action已spawn

# 孤儿分发恢复：分发记录超过超时仍未产出 artifact，允许重新分发。
# 防 session 死亡/中断导致 dedup 记录永久阻塞流水线（2026-07-23 smk_001 停摆事故）。
# A3: 仅适用于「已确认」的 dispatch；未确认的记录走 ORPHAN_DISPATCH_WINDOW_SECONDS。
_STALE_DISPATCH_TIMEOUTS = {
    "analyze": 1800,         # 30 min
    "spawn_workers": 5400,   # 90 min（Worker 跑大任务耗时长）
    "validate": 1800,        # 30 min
    "package": 1800,         # 30 min
}
_DEFAULT_STALE_TIMEOUT = 1800

# F2: 非 worker dispatch 的完成证据映射（与 wp_runner.py 各 step 实现保持双向引用）
# analyze ← wp_runner step1/step2_check_analyze 读写同一文件
# validate ← wp_runner verify_validate_output 写入同一文件
# package  ← wp_runner step7_package 写入同一文件
_ACTION_COMPLETION_EVIDENCE = {
    "analyze": "stages/execution_plan.json",
    "validate": "stages/validation_result.json",
    "package": "stages/delivery_manifest.json",
    "package_failed": "stages/delivery_manifest.json",
}


def _check_drive_mode_allowed(method_name: str) -> None:
    """契约笼子：drive_all/drive_once 已禁用（2026-07-28），仅紧急回退可用。

    根因：LLM 调度模式绕过并发控制（17 children 突破 MAX_IN_FLIGHT）
          + 上下文遗忘导致已完成 worker 重复 spawn。
    唯一生产路径：Pulse（pulse_cli.py pulse --project X，26/26 WP 零干预验证）。

    紧急回退（仅测试/审计）：DEEPFLOW_ALLOW_DRIVE_ALL=1
    """
    if os.environ.get("DEEPFLOW_ALLOW_DRIVE_ALL") != "1":
        raise RuntimeError(
            f"{method_name} 已禁用（契约违例）：LLM 调度模式于 2026-07-28 废弃。\n"
            f"  根因：LLM 调度绕过并发控制（17 并发）+ 已完成 worker 重复 spawn\n"
            f"  唯一生产路径：Pulse\n"
            f"    python3 -m domains.deliver_pro.pulse_cli pulse --project <name>\n"
            f"  紧急回退（仅测试/审计）：DEEPFLOW_ALLOW_DRIVE_ALL=1"
        )


class PulseLocked(Exception):
    """另一个 pulse 进程持有锁。携带可选的 stale-lock 告警。"""

    def __init__(self, alert: dict | None = None):
        super().__init__("pulse lock held by another process")
        self.alert = alert


class DeliverOrchestrator:
    """批量驱动多个 WP 的 Deliver Pro 流水线。"""

    def __init__(self, project_name: str):
        from domains.deliver_pro import BLACKBOARD_ROOT

        # Sanitize project_name: 防止路径穿越
        self.project_name = project_name.replace("/", "_").replace("\\", "_").replace("..", "_")
        self.blackboard_root = BLACKBOARD_ROOT
        # F1 fix (W3): ship_package 缺失 → raise（禁止静默降级）
        # 与 run_deliver_pro 行为一致——缺失即 raise，不允许空包运行。
        ship_pkg_path = self._find_ship_package()
        self.ship_package = json.loads(ship_pkg_path.read_text())
        # 能力正交：Ship Pro 输出 "id" → 兼容为 "wp_id"
        for wp in self.ship_package.get("work_packages", []):
            if "wp_id" not in wp and "id" in wp:
                wp["wp_id"] = wp["id"]
        self.layers = self._compute_layers()
        self.progress_path = self.blackboard_root / project_name / "batch_progress.json"
        self.progress = self._load_progress()
        self._last_tick_truncated = False  # A5: 上次 tick 是否因预算截断

    # ------------------------------------------------------------------
    # 初始化辅助
    # ------------------------------------------------------------------

    def _find_ship_package(self) -> Path:
        """搜索 blackboard/{project}/ship_pro/ 下的 ship package。

        查找顺序（ADR-009 MD-first）：
        1. ship_pro/ship_track.json（Track 衍生，跨域元数据）
        2. ship_pro/ship_package.json（JSON 衍生，向后兼容）
        3. ship_pro/stages/ship_package.json（旧路径）
        """
        candidates = [
            self.blackboard_root / self.project_name / "ship_pro" / "ship_track.json",
            self.blackboard_root / self.project_name / "ship_pro" / "ship_package.json",
            self.blackboard_root / self.project_name / "ship_pro" / "stages" / "ship_package.json",
        ]
        for path in candidates:
            if path.exists():
                logger.info(f"Ship package found: {path}")
                return path
        raise FileNotFoundError(
            f"ship_package.json or ship_track.json not found. Searched: {[str(p) for p in candidates]}"
        )

    def _compute_layers(self) -> list[list[str]]:
        """优先用 dependency_graph.execution_layers，fallback 拓扑排序。"""
        dep_graph = self.ship_package.get("dependency_graph", {})
        execution_layers = dep_graph.get("execution_layers")
        if execution_layers:
            return execution_layers

        # Fallback: 从 WP dependencies 做拓扑排序
        wp_deps = {}
        for wp in self.ship_package.get("work_packages", []):
            wp_deps[wp["wp_id"]] = wp.get("dependencies", [])
        return self._topo_layers(wp_deps)

    @staticmethod
    def _topo_layers(wp_deps: dict[str, list[str]]) -> list[list[str]]:
        """从 dependencies 计算分层（Kahn's algorithm variant）。

        Args:
            wp_deps: {wp_id: [dependency_wp_ids]}

        Returns:
            [[layer0_wps], [layer1_wps], ...]
        """
        # Build in-degree map
        in_degree: dict[str, int] = {wp: 0 for wp in wp_deps}
        dependents: dict[str, list[str]] = {wp: [] for wp in wp_deps}

        for wp, deps in wp_deps.items():
            for dep in deps:
                if dep in dependents:
                    dependents[dep].append(wp)
                    in_degree[wp] = in_degree.get(wp, 0) + 1

        layers: list[list[str]] = []
        remaining = dict(in_degree)

        while remaining:
            # Find all nodes with in-degree 0
            layer = sorted([wp for wp, deg in remaining.items() if deg == 0])
            if not layer:
                # Circular dependency — break by picking the first remaining
                layer = [sorted(remaining.keys())[0]]
                logger.warning(f"Circular dependency detected, forcing layer: {layer}")

            layers.append(layer)

            # Remove layer nodes and update in-degrees
            for wp in layer:
                del remaining[wp]
                for dependent in dependents.get(wp, []):
                    if dependent in remaining:
                        remaining[dependent] -= 1

        return layers

    # ------------------------------------------------------------------
    # Progress persistence
    # ------------------------------------------------------------------

    def _load_progress(self) -> dict:
        """从 JSON 文件加载进度（剥离 _meta 版本字段，内存只存 WP 进度）。"""
        if self.progress_path.exists():
            try:
                data = json.loads(self.progress_path.read_text())
                data.pop("_meta", None)
                return data
            except Exception as e:
                logger.warning(f"Failed to load progress: {e}")
        return {}

    def _save_progress(self) -> None:
        """保存进度到 JSON 文件（A1: 原子写 + schema version）。"""
        # _meta 只存在于文件（schema 演进标记，P2-4），不污染内存 dict
        data = {**self.progress, "_meta": {"version": 1}}
        atomic_write_json(self.progress_path, data)

    # ------------------------------------------------------------------
    # WP 数据访问
    # ------------------------------------------------------------------

    def _get_wp_data(self, wp_id: str) -> dict:
        """从 ship_package 获取 WP 原始数据。"""
        for wp in self.ship_package.get("work_packages", []):
            if wp["wp_id"] == wp_id:
                return wp
        raise KeyError(f"WP not found: {wp_id}")

    def _get_wp_project_name(self, wp_id: str) -> str:
        """WP ID → project_name 映射。

        V3: 所有 WP 输出统一写到项目自己的 blackboard（self.project_name），
        与 run_deliver_pro 设置的 blackboard 目录保持一致。

        历史设计曾映射到独立项目目录（deliver_{wp_id}），导致：
        - WP 输出与 ship_package / orchestrator blackboard 分离
        - 跨项目目录的旧残留（deliver_smk_001 等）被 derive_phase 误判为 DONE
        """
        return self.project_name

    def _get_driver(self, wp_id: str):
        """创建 DeliverRunner(wp_id, project_name)。"""
        from domains.deliver_pro.driver import DeliverRunner

        project_name = self._get_wp_project_name(wp_id)
        return DeliverRunner(wp_id, project_name)

    # ------------------------------------------------------------------
    # Phase 检测（V3: 纯文件推导，不再交叉校验 state 文件）
    # ------------------------------------------------------------------

    def _check_wp_phase(self, wp_id: str) -> str:
        """V3: 从文件系统推导 WP phase（derive, don't sync）。

        不再读取 delivery_state.json 做交叉校验——文件系统即真相。
        旧 artifact 失效由 invalidate_downstream 在重入阶段时处理。

        Returns:
            "DONE" | "PACKAGING" | "VALIDATING" | "ASSEMBLING" |
            "GENERATING" | "PENDING"
        """
        from domains.deliver_pro.phase_deriver import derive_phase, migrate_legacy_worker_outputs

        wp_project = self._get_wp_project_name(wp_id)
        wp_subdir = wp_id.lower().replace('-', '_')
        wp_dir = self.blackboard_root / wp_project / "deliver_pro" / wp_subdir

        # 幂等搬迁 legacy 路径（无操作若已是标准路径）
        # P2-2: 传入 blackboard_root 避免 .parent 在 slash 路径下出错
        migrate_legacy_worker_outputs(wp_dir, blackboard_root=self.blackboard_root)

        return derive_phase(wp_dir)

    # ------------------------------------------------------------------
    # 核心 API
    # ------------------------------------------------------------------

    def get_next_actions(self) -> dict:
        """返回当前层所有 WP 的下一步动作。

        Returns:
            {
                "layer": int,
                "actions": [
                    {"wp_id": str, "action": str, "spawn_params": dict|None, "error": str|None},
                    ...
                ]
            }
        """
        for layer_idx, layer_wps in enumerate(self.layers):
            # 检查该层是否有未完成的 WP
            unfinished = []
            for wp_id in layer_wps:
                phase = self._get_wp_phase(wp_id)
                if phase != "DONE":
                    # A2/P1-4: terminal_failed 视为已解决（不再调度）
                    if not self.progress.get(wp_id, {}).get("terminal_failed"):
                        unfinished.append(wp_id)

            if not unfinished:
                continue  # 该层全部完成，检查下一层

            # 该层有未完成 WP → 返回它们的 next actions
            actions = []
            for wp_id in unfinished:
                try:
                    action = self._get_wp_next_action(wp_id)
                    actions.append(action)
                except Exception as e:
                    actions.append({
                        "wp_id": wp_id,
                        "action": "error",
                        "spawn_params": None,
                        "error": str(e),
                    })

            return {"layer": layer_idx, "actions": actions}

        # 所有层都完成
        return {"layer": -1, "actions": []}

    def _ensure_wp_initialized(self, wp_id: str) -> None:
        """确保 WP 的 blackboard 目录和 wp.json 存在。"""
        from domains.deliver_pro import _adapt_ship_pro_wp
        from domains.deliver_pro.contracts import WorkPackage

        project_name = self._get_wp_project_name(wp_id)
        wp_subdir = wp_id.lower().replace('-', '_')
        deliver_pro_dir = self.blackboard_root / project_name / "deliver_pro" / wp_subdir
        wp_path = deliver_pro_dir / "data" / "wp.json"

        if wp_path.exists():
            return  # 已初始化

        # 从 ship_package 获取 WP 数据并适配
        wp_data = self._get_wp_data(wp_id)
        package_sa = self.ship_package.get("semantic_anchors", [])
        # W4-F4: 包级 serving_principles fallback（与 semantic_anchors 同款模式）
        package_sp = self.ship_package.get("serving_principles", [])
        adapted = _adapt_ship_pro_wp(
            wp_data,
            package_semantic_anchors=package_sa,
            package_serving_principles=package_sp,
        )
        wp_obj = WorkPackage.model_validate(adapted)

        # 创建目录结构
        deliver_pro_dir.mkdir(parents=True, exist_ok=True)
        (deliver_pro_dir / "data").mkdir(exist_ok=True)
        (deliver_pro_dir / "stages").mkdir(exist_ok=True)
        (deliver_pro_dir / "stages" / "worker_outputs").mkdir(exist_ok=True)

        # 写入 wp.json
        wp_path.write_text(
            json.dumps(wp_obj.model_dump(mode="json"), ensure_ascii=False, indent=2)
        )
        logger.info(f"Initialized WP {wp_id} at {wp_path}")

    def _has_retriable_timed_out(self, wp_id: str, driver) -> list[str]:
        """F3: 检测"超时但重试预算未耗尽"的任务（防 blocked 级联冤案）。

        只查 timed_out 子集：MANIFEST-FAILED 的任务不归 retry 管，
        若把它们也算进来会死锁（WP 永远卡在 GENERATING 不进 ASSEMBLING）。
        attempts 默认值 1（与 _prepare_worker_retries 语义对齐：目录存在≈spawn 过 1 次）。

        Returns:
            可重试的 timed_out task_id 列表（空 = 无冤案，可安全推进终态）
        """
        try:
            plan = driver.orch.load_execution_plan()
            if plan is None:
                return []
            progress = driver.orch._derive_worker_progress(plan)
            timed_out = progress.get("timed_out", set())
            if not timed_out:
                return []
            attempts_map = self.progress.get(wp_id, {}).get("task_attempts", {})
            return sorted(
                t for t in timed_out
                if attempts_map.get(t, 1) < RETRY_BUDGET
            )
        except Exception as e:
            logger.warning("%s: retriable-timed_out check failed (fail-open): %s", wp_id, e)
            return []  # 检查失败 → fail-open，不阻塞正常流程

    def _has_unexecuted_tasks(self, wp_id: str, driver) -> list[str]:
        """F3c: 检测“从未真正执行”的任务（终态写入前的最后防线）。

        触发条件（三类）：
        - 类 1：timed_out 且 attempts < RETRY_BUDGET（同 F3a/b，可能还有救）
        - 类 2：ready 或即将 ready（deps ⊆ COMPLETE ∪ RUNNING）且 attempts == 0 且无 MANIFEST。
          RUNNING 也算：防止打包抢跑在途 worker 波次（2026-07-29 SPI-003 实证：
          T-003 完成前 1 分钟打包决策放行 T-004，终态写入 "never executed"）。
        - 类 3（F-B）：failed 且 failure_class in ("contract_violation", "quality_failure")
          且 attempts < RETRY_BUDGET（契约违规或质量验证 FAIL，还有救）

        blocked 任务不触发守卫：若其依赖是真失败（attempts>=1 后 MANIFEST FAILED），
        FAIL 打包是诚实结果，不该拦截。

        Returns:
            需要重跑机会的 task_id 列表（空 = 可以安全写终态文件）
        """
        try:
            plan = driver.orch.load_execution_plan()
            if plan is None:
                return []
            progress = driver.orch._derive_worker_progress(plan)
            attempts_map = self.progress.get(wp_id, {}).get("task_attempts", {})
            result: list[str] = []
            # 类 1：timed_out 且预算未耗尽
            for t in progress.get("timed_out", set()):
                if attempts_map.get(t, 1) < RETRY_BUDGET:
                    result.append(t)
            # 类 3（F-B）：failed + contract_violation + 预算未耗尽
            wo = driver.worker_outputs_dir
            for t in progress.get("failed", set()):
                if attempts_map.get(t, 1) >= RETRY_BUDGET:
                    continue
                manifest_path = wo / t / "MANIFEST.json"
                if not manifest_path.exists():
                    continue
                try:
                    mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if mdata.get("failure_class") in ("contract_violation", "quality_failure"):
                    result.append(t)
            # 类 2：ready 但从未派发
            completed = progress.get("completed", set())
            running = progress.get("running", set())
            failed = progress.get("failed", set())
            blocked = progress.get("blocked", set())
            for task_node in plan.task_graph:
                tid = task_node.task_id
                if tid in completed or tid in running or tid in failed or tid in blocked:
                    continue
                deps = set(getattr(task_node, "depends_on", None) or [])
                if deps and not deps.issubset(completed | running):
                    continue  # 依赖未完成且不在途 → 不算可跑，不守卫；依赖在途 → 守卫（防打包抢跑）
                if attempts_map.get(tid, 0) == 0 and not (wo / tid / "MANIFEST.json").exists():
                    result.append(tid)
            return sorted(result)
        except Exception as e:
            logger.warning("%s: unexecuted-tasks check failed (fail-open): %s", wp_id, e)
            return []

    def _get_wp_next_action(self, wp_id: str) -> dict:
        """获取单个 WP 的下一步动作（含 spawn params）。"""
        phase = self._check_wp_phase(wp_id)
        progress_entry = self.progress.get(wp_id, {})
        progress_entry["phase"] = phase
        self.progress[wp_id] = progress_entry

        # DONE / PACKAGING → 无需 spawn
        if phase == "DONE":
            return {"wp_id": wp_id, "action": "done", "spawn_params": None, "error": None}

        if phase == "PACKAGING":
            # BLK-02 fix: PACKAGING should spawn Package agent, not return done
            try:
                self._ensure_wp_initialized(wp_id)
                driver = self._get_driver(wp_id)
                # F3c fix: 终态写入前的最后防线——存在从未真正执行的任务时拒绝打包，
                # 回退给它们真正的执行机会（防 Class E：状态污染后的不可逆写入）
                unexecuted = self._has_unexecuted_tasks(wp_id, driver)
                if unexecuted:
                    logger.warning(
                        "%s: PACKAGING 被 F3c 拦截——%s 从未真正执行，回退重跑",
                        wp_id, unexecuted,
                    )
                    retry_params, retry_alerts = self._prepare_worker_retries(wp_id, driver)
                    params_list = driver.step3_workers()
                    merged_params = retry_params + params_list
                    item = {"wp_id": wp_id, "action": "spawn_workers", "spawn_params": merged_params, "error": None}
                    if retry_alerts:
                        item["alerts"] = retry_alerts
                    return item
                params = driver.step7_package(verdict_str="PASS")
                return {"wp_id": wp_id, "action": "package", "spawn_params": params, "error": None}
            except Exception as e:
                return {"wp_id": wp_id, "action": "package_failed", "spawn_params": None, "error": str(e)}

        # 需要 driver → 确保已初始化
        try:
            self._ensure_wp_initialized(wp_id)
            driver = self._get_driver(wp_id)
        except Exception as e:
            return {"wp_id": wp_id, "action": "init_failed", "spawn_params": None, "error": str(e)}

        if phase == "PENDING":
            try:
                params = driver.step1_analyze()
                return {"wp_id": wp_id, "action": "analyze", "spawn_params": params, "error": None}
            except Exception as e:
                return {"wp_id": wp_id, "action": "analyze_failed", "spawn_params": None, "error": str(e)}

        if phase == "GENERATING":
            ok, info = driver.step2_check_analyze()
            if not ok:
                # A2 契约修复：plan 损坏 → 删除坏 plan + 清除 analyze dispatch 记录，
                # 下一 pulse 从 PENDING 重新 analyze（WP 级重试预算在 tick stale-clear 守卫）
                try:
                    wp_subdir = wp_id.lower().replace('-', '_')
                    plan_path = (
                        self.blackboard_root / self._get_wp_project_name(wp_id)
                        / "deliver_pro" / wp_subdir / "stages" / "execution_plan.json"
                    )
                    plan_path.unlink(missing_ok=True)
                    for k in ("last_spawned_action", "last_spawned_at", "dispatch_confirmed"):
                        progress_entry.pop(k, None)
                    progress_entry["action_retries"] = progress_entry.get("action_retries", 0) + 1
                    self.progress[wp_id] = progress_entry
                    self._save_progress()
                    logger.warning("%s: corrupt execution_plan invalidated, will re-analyze", wp_id)
                except Exception as inv_e:
                    logger.warning("%s: failed to invalidate corrupt plan: %s", wp_id, inv_e)
                return {"wp_id": wp_id, "action": "analyze_check_failed", "spawn_params": None, "error": str(info)}
            try:
                # BLK-05 fix: Check if workers are already done before spawning new ones
                all_done, check_info = driver.step4_check_workers()
                if all_done:
                    # F3a fix: blocked 级联防护——存在"超时但重试预算未耗尽"的任务时，
                    # 不推进 assemble（那些任务从未真正运行就被判死，属于冤案），
                    # 回落到重试路径给它们真正的执行机会
                    retriable = self._has_retriable_timed_out(wp_id, driver)
                    if not retriable:
                        # Workers already completed → trigger assembly
                        return {"wp_id": wp_id, "action": "assemble", "spawn_params": None, "error": None}
                    logger.warning(
                        "%s: all_done 但被 F3a 拦截——%s 超时且重试预算未耗尽，转重试路径",
                        wp_id, retriable,
                    )
                # A2/A3: derive 判 timed_out 的 task 走重试路径（无视 stale dedup 直接重派）
                retry_params, retry_alerts = self._prepare_worker_retries(wp_id, driver)
                params_list = driver.step3_workers()
                merged_params = retry_params + params_list
                item = {"wp_id": wp_id, "action": "spawn_workers", "spawn_params": merged_params, "error": None}
                if retry_alerts:
                    item["alerts"] = retry_alerts
                return item
            except Exception as e:
                return {"wp_id": wp_id, "action": "workers_failed", "spawn_params": None, "error": str(e)}

        if phase == "ASSEMBLING":
            try:
                # F3b fix: ASSEMBLING 分支同样需要级联防护——
                # phase 一旦被 derive 为 ASSEMBLING，若绕过 GENERATING 分支的 F3a 守卫，
                # 伪 failed 仍会污染拼装。此处做最后拦截：回退按 GENERATING 重试处理
                retriable = self._has_retriable_timed_out(wp_id, driver)
                if retriable:
                    logger.warning(
                        "%s: ASSEMBLING 被 F3b 拦截——%s 超时且重试预算未耗尽，回退重试",
                        wp_id, retriable,
                    )
                    retry_params, retry_alerts = self._prepare_worker_retries(wp_id, driver)
                    params_list = driver.step3_workers()
                    merged_params = retry_params + params_list
                    item = {"wp_id": wp_id, "action": "spawn_workers", "spawn_params": merged_params, "error": None}
                    if retry_alerts:
                        item["alerts"] = retry_alerts
                    return item
                result = driver.step5_integrate()
                # K5-B: 零产出 → terminal_failed（不烧 validate/package 两轮 LLM）
                if result.get("status") == "ASSEMBLY_EMPTY":
                    return {"wp_id": wp_id, "action": "terminal_failed", "spawn_params": None, "error": result.get("error", "零 worker 产出")}
                if result.get("status") == "ASSEMBLY_ERROR":
                    params = driver.step7_package(verdict_str="FAIL")
                    return {"wp_id": wp_id, "action": "package_failed", "spawn_params": params, "error": "Assembly failed"}
                params = driver.step6_validate(round_num=1)
                return {"wp_id": wp_id, "action": "validate", "spawn_params": params, "error": None}
            except Exception as e:
                return {"wp_id": wp_id, "action": "assembly_failed", "spawn_params": None, "error": str(e)}

        if phase == "VALIDATING":
            verdict, details = driver.step6_check_validate()
            # P1-1 fix: NOT_FOUND = validate agent still running → skip, don't trigger package_failed
            if verdict == "NOT_FOUND":
                # 孤儿 validate 恢复（2026-07-23 E2E 停摆事故）：
                # validate agent 死亡或从未被分发时，validation_result.json 永远缺失，
                # 无条件 skip 会永久停摆（Layer 0 不 DONE → 后续所有 layer 锁死）。
                # 分发记录过期或从未分发 validate → 重新分发 validate agent。
                progress_entry = self.progress.get(wp_id, {})
                last_spawned = progress_entry.get("last_spawned_action", "")
                validate_dispatched = last_spawned == "validate" or last_spawned.startswith("validate:")
                if not validate_dispatched or self._is_stale_dispatch(progress_entry, "validate"):
                    try:
                        round_num = progress_entry.get("validate_round", 1)
                        params = driver.step6_validate(round_num=round_num)
                        logger.warning("%s: re-dispatching orphan validate (round=%s)", wp_id, round_num)
                        return {"wp_id": wp_id, "action": "validate", "spawn_params": params, "error": None}
                    except Exception as e:
                        return {"wp_id": wp_id, "action": "validate_failed", "spawn_params": None, "error": str(e)}
                return {"wp_id": wp_id, "action": "skip", "spawn_params": None, "error": "validate_pending"}
            try:
                # F3c fix: 同 PACKAGING 分支——VALIDATING→package 派发前做最后防线
                unexecuted = self._has_unexecuted_tasks(wp_id, driver)
                if unexecuted:
                    logger.warning(
                        "%s: VALIDATING→package 被 F3c 拦截——%s 从未真正执行，回退重跑",
                        wp_id, unexecuted,
                    )
                    retry_params, retry_alerts = self._prepare_worker_retries(wp_id, driver)
                    params_list = driver.step3_workers()
                    merged_params = retry_params + params_list
                    item = {"wp_id": wp_id, "action": "spawn_workers", "spawn_params": merged_params, "error": None}
                    if retry_alerts:
                        item["alerts"] = retry_alerts
                    return item
                params = driver.step7_package()  # P1-3 fix: auto-read verdict from validation_result.json
                action = "package" if verdict == "PASS" else "package_failed"
                return {"wp_id": wp_id, "action": action, "spawn_params": params, "error": None}
            except Exception as e:
                return {"wp_id": wp_id, "action": "package_failed", "spawn_params": None, "error": str(e)}

        return {"wp_id": wp_id, "action": "unknown", "spawn_params": None, "error": f"Unknown phase: {phase}"}

    def _get_wp_phase(self, wp_id: str) -> str:
        """获取 WP 的逻辑 phase（优先用 progress 记录，fallback 到文件系统检测）。"""
        # 先用文件系统检测实际 phase
        return self._check_wp_phase(wp_id)

    def report_done(self, wp_id: str, action: str, success: bool = True, error: str = None) -> None:
        """报告动作完成，更新 progress。"""
        if wp_id not in self.progress:
            self.progress[wp_id] = {}

        entry = self.progress[wp_id]
        entry["last_action"] = action
        entry["last_success"] = success
        entry["last_error"] = error

        if success:
            entry["action_count"] = entry.get("action_count", 0) + 1
        else:
            entry["error_count"] = entry.get("error_count", 0) + 1

        # 更新 phase
        entry["phase"] = self._check_wp_phase(wp_id)

        self._save_progress()

    def get_status(self) -> dict:
        """整体进度概览。"""
        total_wps = sum(len(layer) for layer in self.layers)
        completed = 0
        failed = 0
        in_progress = 0
        terminal_failed = 0

        for layer in self.layers:
            for wp_id in layer:
                if self.progress.get(wp_id, {}).get("terminal_failed"):
                    terminal_failed += 1
                    continue
                phase = self._check_wp_phase(wp_id)
                if phase == "DONE":
                    completed += 1
                elif self.progress.get(wp_id, {}).get("last_error"):
                    failed += 1
                else:
                    in_progress += 1

        # 找当前层（第一个有未完成 WP 的层）
        current_layer = -1
        for i, layer in enumerate(self.layers):
            if any(self._check_wp_phase(wp_id) != "DONE" for wp_id in layer):
                current_layer = i
                break

        all_done = completed == total_wps

        return {
            "total_wps": total_wps,
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "terminal_failed": terminal_failed,
            "current_layer": current_layer,
            "all_done": all_done,
            # A2/P1-4: 流水线终态 = 全部 WP 已解决（含永久失败）
            "all_resolved": (completed + terminal_failed) == total_wps,
        }

    def tick(self, max_spawn_budget: int | None = None) -> list[dict]:
        """AI Native 统一推进接口：一次调用完成 scan → reconcile → dedup → 返回 spawn list。

        主 Agent 只需：
        1. 调用 tick()
        2. 对返回的每个 spawn_params 调用 sessions_spawn
        3. yield 等待完成
        4. 再次调用 tick()

        Args:
            max_spawn_budget: A5 spawn 预算硬上限（pulse 模式传入）。
                预算耗尽后跳过后续 spawn 动作（不记录 dispatch、不返回），
                并置 self._last_tick_truncated = True。
                None = 不限（向后兼容 drive_once/drive_all 调用方）。

        内部自动处理：
        - MANIFEST 路径修正（worker_outputs/ → stages/worker_outputs/）
        - State reconcile（completed_tasks 从 MANIFEST 计算）
        - 去重（已 spawn 的 agent 不重复返回）
        - Assembly 自动执行（确定性代码，不需要 agent）

        Returns:
            list of {"wp_id": str, "action": str, "spawn_params": dict|None}
            action: "analyze" | "spawn_workers" | "validate" | "package" | "done"
        """
        import shutil

        self._last_tick_truncated = False
        results = []
        next_actions = self.get_next_actions()
        _reconciled_wps: set[str] = set()  # F3: 每 WP 每 tick 只对账一次

        for action_item in next_actions.get("actions", []):
            wp_id = action_item["wp_id"]
            action = action_item["action"]

            # F3: 僵尸 running_tasks 对账（每 WP 每 tick 一次，在 L1 过滤之前）
            if wp_id not in _reconciled_wps:
                try:
                    driver = self._get_driver(wp_id)
                    n_cleared = self._reconcile_running_tasks(wp_id, driver)
                    if n_cleared:
                        logger.info("%s: reconciled %d zombie running_tasks", wp_id, n_cleared)
                except Exception as e:
                    logger.warning("%s: reconcile running_tasks failed: %s", wp_id, e)
                _reconciled_wps.add(wp_id)

            # V3: legacy 路径搬迁已在 _check_wp_phase 中幂等处理（derive, don't sync）

            # L1 fix: spawn_workers 走 per-task 最终过滤（替代 Wave 级 dedup）
            progress_entry = self.progress.get(wp_id, {})
            current_params = action_item.get("spawn_params")
            has_real_params = bool(current_params) and (
                not isinstance(current_params, list) or len(current_params) > 0
            )
            if action == "spawn_workers" and isinstance(current_params, list):
                current_params = self._filter_spawnable_tasks(wp_id, current_params)
                action_item = dict(action_item, spawn_params=current_params)
                has_real_params = len(current_params) > 0
                # 更新 task_ids 用于 dedup_key 记录（L1 过滤后的准确列表）
                current_task_ids = ",".join(sorted(
                    p.get("task_id", p.get("label", "")) for p in current_params
                    if isinstance(p, dict)
                ))
                dedup_key = f"{action}:{current_task_ids}" if current_task_ids else action

            # 去重：检查 progress 中是否已 spawn 同 action（含具体 task IDs）
            # spawn_workers 已通过 L1 per-task 过滤，不再走 Wave 级 dedup 短路
            # 非 worker action（analyze/validate/package）仍走原有 dedup 逻辑
            last_spawned = progress_entry.get("last_spawned_action")
            if action != "spawn_workers":
                # P0-3 fix: dedup key 包含具体 task IDs，不同 wave 的 spawn_workers 不互相阻塞
                current_task_ids = ""
                if isinstance(current_params, list):
                    current_task_ids = ",".join(sorted(
                        p.get("task_id", p.get("label", "")) for p in current_params
                        if isinstance(p, dict)
                    ))
                dedup_key = f"{action}:{current_task_ids}" if current_task_ids else action
            if last_spawned == dedup_key and has_real_params:
                # 孤儿分发恢复：dedup 记录可能来自已死 session（agent 从未真正运行）。
                # 过期则清除记录并继续分发；未过期才真正跳过。
                if self._is_stale_dispatch(progress_entry, action):
                    # A2: 非 worker 动作（analyze/validate/package）的 WP 级重试预算
                    if action != "spawn_workers":
                        retries = progress_entry.get("action_retries", 0) + 1
                        progress_entry["action_retries"] = retries
                        if retries > RETRY_BUDGET:
                            progress_entry["terminal_failed"] = True
                            self.progress[wp_id] = progress_entry
                            self._save_progress()
                            logger.error(
                                "%s: action '%s' exceeded retry budget (%d) → terminal_failed",
                                wp_id, action, RETRY_BUDGET,
                            )
                            results.append({
                                "wp_id": wp_id,
                                "action": "terminal_failed",
                                "spawn_params": None,
                                "error": f"action '{action}' 重试 {RETRY_BUDGET} 次仍失败",
                            })
                            continue
                    # A4: 未确认的 spawn_workers 孤儿 → 删除空 task 目录（下次 pulse 可重派）
                    if action == "spawn_workers" and not progress_entry.get(
                        "dispatch_confirmed", False
                    ):
                        self._cleanup_orphan_worker_dirs(wp_id)
                    logger.warning(
                        "%s: clearing stale dispatch '%s' (spawned_at=%s)",
                        wp_id, dedup_key, progress_entry.get("last_spawned_at"),
                    )
                    progress_entry.pop("last_spawned_action", None)
                    progress_entry.pop("last_spawned_at", None)
                    progress_entry.pop("dispatch_confirmed", None)
                    self.progress[wp_id] = progress_entry
                else:
                    continue  # 同一批 worker 已在进行中，跳过
            if last_spawned == dedup_key and not has_real_params:
                progress_entry.pop("last_spawned_action", None)
                progress_entry.pop("last_spawned_at", None)
                progress_entry.pop("dispatch_confirmed", None)
                self.progress[wp_id] = progress_entry

            # A5: spawn 预算硬上限（在记录 dispatch 之前拦截）
            if has_real_params and max_spawn_budget is not None:
                n_params = len(current_params) if isinstance(current_params, list) else 1
                if max_spawn_budget <= 0:
                    self._last_tick_truncated = True
                    # F1a fix: budget=0 时 params 已构建（mkdir 副作用已发生），
                    # 必须清理空目录，否则孤儿目录被 derive 误判 running 占坑 30min
                    # （与下方截断分支行为对齐）
                    if isinstance(current_params, list) and current_params:
                        self._drop_worker_param_dirs(wp_id, current_params)
                    continue  # 预算耗尽：不记录、不返回、不派生
                if isinstance(current_params, list) and n_params > max_spawn_budget:
                    dropped = current_params[max_spawn_budget:]
                    action_item = dict(action_item)
                    action_item["spawn_params"] = current_params[:max_spawn_budget]
                    current_params = action_item["spawn_params"]
                    has_real_params = len(current_params) > 0
                    current_task_ids = ",".join(sorted(
                        p.get("task_id", p.get("label", "")) for p in current_params
                        if isinstance(p, dict)
                    ))
                    dedup_key = f"{action}:{current_task_ids}" if current_task_ids else action
                    self._last_tick_truncated = True
                    # 被截断的 task：删除空目录 → 下次 pulse 立即可重派（不等 30min 超时）
                    self._drop_worker_param_dirs(wp_id, dropped)
                max_spawn_budget -= min(n_params, max_spawn_budget)

            # 3. Assembly 自动执行（确定性代码，不需要 agent）
            if action == "assemble":
                try:
                    driver = self._get_driver(wp_id)
                    result = driver.step5_integrate()
                    # K5-B: 零产出 → terminal_failed（不烧 package agent 写失败报告）
                    if result.get("status") == "ASSEMBLY_EMPTY":
                        logger.error(f"{wp_id}: ASSEMBLY_EMPTY — terminal")
                        self.report_done(wp_id, "assemble", False, error="ASSEMBLY_EMPTY")
                        results.append({"wp_id": wp_id, "action": "terminal_failed", "spawn_params": None, "error": result.get("error", "零 worker 产出")})
                    # P1-6 fix: Check assembly status — don't discard ASSEMBLY_ERROR
                    elif result.get("status") == "ASSEMBLY_ERROR":
                        logger.error(f"{wp_id}: ASSEMBLY_ERROR — routing to failure packaging")
                        self.report_done(wp_id, "assemble", False, error="ASSEMBLY_ERROR")
                        try:
                            params = driver.step7_package(verdict_str="FAIL")
                            results.append({"wp_id": wp_id, "action": "package_failed", "spawn_params": params, "error": "Assembly failed"})
                        except Exception as pkg_e:
                            results.append({"wp_id": wp_id, "action": "terminal_failed", "spawn_params": None, "error": f"Assembly+Package both failed: {pkg_e}"})
                    else:
                        self.report_done(wp_id, "assemble", True)
                        # 立即获取下一个动作（validate）
                        new_action = self._get_wp_next_action(wp_id)
                        # 链式 action 也必须记录分发状态（2026-07-23 STORE-003 孤儿事故）：
                        # 否则 validate agent 死亡后，VALIDATING 分支的 stale 检查
                        # 只能看到旧的 spawn_workers 时间戳，可能误杀正常运行的 validate。
                        new_params = new_action.get("spawn_params")
                        if new_params and new_action.get("action") not in ("done", "skip"):
                            pe = self.progress.get(wp_id, {})
                            pe["last_spawned_action"] = new_action["action"]
                            pe["last_spawned_at"] = time.time()
                            self.progress[wp_id] = pe
                            self._save_progress()
                        results.append(new_action)
                except Exception as e:
                    # P1-7 fix: assembly exception → terminal_failed (not retryable)
                    logger.error(f"{wp_id}: assembly exception — {e}")
                    results.append({"wp_id": wp_id, "action": "terminal_failed", "spawn_params": None, "error": str(e)})
                continue

            # 4. 记录 spawn 状态（P0-3 fix: 用 dedup_key 而非 action，区分不同 wave）
            if has_real_params:
                progress_entry["last_spawned_action"] = dedup_key
                progress_entry["last_spawned_at"] = time.time()
                progress_entry["dispatch_confirmed"] = False  # A4: 两阶段 dispatch（待 spawn 回执）
                # A2: task 级 spawn 次数账本（重试预算的数据源）
                if action == "spawn_workers" and isinstance(current_params, list):
                    attempts_map = progress_entry.setdefault("task_attempts", {})
                    spawned_map = progress_entry.setdefault("task_spawned_at", {})  # L2: per-task 冷却窗口账本
                    for p in current_params:
                        tid = p.get("task_id") if isinstance(p, dict) else None
                        if tid:
                            attempts_map[tid] = attempts_map.get(tid, 0) + 1
                            spawned_map[tid] = time.time()  # L2: 记录 spawn 时间戳
                self.progress[wp_id] = progress_entry
                self._save_progress()

            results.append(action_item)

        return results

    def _filter_spawnable_tasks(self, wp_id: str, params: list[dict]) -> list[dict]:
        """L1 最终防线：派发前 per-task 过滤。

        无论上层逻辑如何出错，有 MANIFEST / 冷却期内 / attempts 耗尽的 task
        物理上无法进入 spawn 列表。在 flock 锁内、派发前执行。

        三道检查（全部通过才保留）：
        1. MANIFEST 存在 → 终态（完成/失败），绝不重派
        2. attempts >= RETRY_BUDGET → 硬上限，防无限重试
        3. task_spawned_at 在冷却窗口内 → 防重复 spawn（替代 Wave 级 dedup）
        """
        from domains.deliver_pro.phase_deriver import WORKER_TIMEOUT_SECONDS

        kept = []
        entry = self.progress.get(wp_id, {})
        attempts_map = entry.get("task_attempts", {})
        spawned_at_map = entry.get("task_spawned_at", {})
        wo = self._wp_dir(wp_id) / "stages" / "worker_outputs"
        now = time.time()
        for p in params:
            tid = p.get("task_id") if isinstance(p, dict) else None
            if not tid:
                continue
            tdir = wo / tid
            manifest_file = tdir / "MANIFEST.json"
            if manifest_file.exists():
                # F-B Round 2 + quality_failure 豁免——
                # MANIFEST 存在但 failure_class in (contract_violation, quality_failure) 且预算未耗尽 → 放行
                exempt = False
                try:
                    mdata = json.loads(manifest_file.read_text(encoding="utf-8"))
                    if (
                        mdata.get("failure_class") in ("contract_violation", "quality_failure")
                        and attempts_map.get(tid, 1) < RETRY_BUDGET
                    ):
                        exempt = True
                except (OSError, json.JSONDecodeError, ValueError):
                    pass  # MANIFEST 读不到/解析失败 → 保持原过滤行为
                if not exempt:
                    continue  # 终态（COMPLETE/失败/预算耗尽/非 contract_violation）
            if attempts_map.get(tid, 0) >= RETRY_BUDGET:  # 硬上限
                continue
            last = spawned_at_map.get(tid, 0)
            if last and now - last < WORKER_TIMEOUT_SECONDS:  # 冷却窗口
                continue
            kept.append(p)
        return kept

    @staticmethod
    def _is_stale_dispatch(progress_entry: dict, action: str) -> bool:
        """判断分发记录是否为孤儿分发（agent 从未运行或所在 session 已死亡）。

        规则：
        - 无 last_spawned_at（旧版本代码写入的记录）→ 视为过期，自动恢复
        - A4 两阶段 dispatch（2026-07-24）：
          - 未确认（dispatch_confirmed=False，pulse 记录了但 spawn 未回执）
            → 超过 ORPHAN_DISPATCH_WINDOW_SECONDS（10min）即过期
          - 已确认（spawn 成功回执）→ 超过该 action 类型的超时阈值才过期

        已确认的超时阈值取保守上限（30/90min 两个常数，A3），避免误杀仍在正常运行的 agent。
        """
        spawned_at = progress_entry.get("last_spawned_at")
        if spawned_at is None:
            return True
        if not progress_entry.get("dispatch_confirmed", False):
            return (time.time() - spawned_at) > ORPHAN_DISPATCH_WINDOW_SECONDS
        timeout = _STALE_DISPATCH_TIMEOUTS.get(action, _DEFAULT_STALE_TIMEOUT)
        return (time.time() - spawned_at) > timeout

    # ------------------------------------------------------------------
    # Pulse Scheduling V1（2026-07-24 评审裁决 A1-A8）
    # ------------------------------------------------------------------

    def _wp_dir(self, wp_id: str) -> Path:
        wp_subdir = wp_id.lower().replace('-', '_')
        return (
            self.blackboard_root / self._get_wp_project_name(wp_id)
            / "deliver_pro" / wp_subdir
        )

    def _drop_task_dir_if_empty(self, wp_id: str, task_id: str) -> bool:
        """删除空 task 目录（无 MANIFEST 且无任何文件）。

        用于 A4 孤儿清理 / A5 截断回滚：params 生成时 mkdir 的目录是空的，
        删除后 derive 视为 pending → 下次 pulse 可立即重派（不等 30min 超时）。
        worker 已开始写文件的目录（非空）保留。
        """
        import shutil

        task_dir = self._wp_dir(wp_id) / "stages" / "worker_outputs" / task_id
        if not task_dir.is_dir():
            return False
        if (task_dir / "MANIFEST.json").exists():
            return False
        try:
            if any(task_dir.iterdir()):  # 非空（worker 已开写）→ 保留
                return False
            shutil.rmtree(task_dir)
            logger.info("%s/%s: dropped empty orphan task dir", wp_id, task_id)
            return True
        except OSError as e:
            logger.warning("%s/%s: failed to drop orphan dir: %s", wp_id, task_id, e)
            return False

    def _drop_worker_param_dirs(self, wp_id: str, dropped_params: list[dict]) -> None:
        """A5 截断回滚：删除被预算截掉的 task 的空目录。"""
        for p in dropped_params:
            tid = p.get("task_id") if isinstance(p, dict) else None
            if tid:
                self._drop_task_dir_if_empty(wp_id, tid)

    def _cleanup_orphan_worker_dirs(self, wp_id: str) -> int:
        """A4 孤儿清理：未确认 spawn_workers 过期时，删除所有空 task 目录。"""
        worker_outputs = self._wp_dir(wp_id) / "stages" / "worker_outputs"
        if not worker_outputs.is_dir():
            return 0
        removed = 0
        for task_dir in worker_outputs.iterdir():
            if task_dir.is_dir() and self._drop_task_dir_if_empty(wp_id, task_dir.name):
                removed += 1
        return removed

    def _reconcile_running_tasks(self, wp_id: str, driver) -> int:
        """F3: 僵尸 running_tasks 对账清理。

        对比 running_tasks 与实际文件证据 + task_spawned_at 超时：
        - 有 MANIFEST.json → 终态（完成/失败），running 条目为僵尸 → 清除
        - task_spawned_at 超 WORKER_TIMEOUT_SECONDS 且无 MANIFEST → 僵尸 → 清除
        - 无 MANIFEST 且 spawn 时间未超 stale 窗口 → 保留（可能仍在运行）
        - 无 task_spawned_at 记录但目录非空 → 保留（保守原则）

        Returns:
            清除的僵尸条目数
        """
        from domains.deliver_pro.phase_deriver import WORKER_TIMEOUT_SECONDS

        try:
            state = driver.orch.state
        except AttributeError:
            return 0

        running = list(state.running_tasks)
        if not running:
            return 0

        entry = self.progress.get(wp_id, {})
        spawned_at_map = entry.get("task_spawned_at", {})
        wo = self._wp_dir(wp_id) / "stages" / "worker_outputs"
        now = time.time()
        cleared = 0

        for task_id in running:
            manifest_path = wo / task_id / "MANIFEST.json"
            if manifest_path.exists():
                # 有 MANIFEST = 终态，running 条目是僵尸
                state.running_tasks.remove(task_id)
                cleared += 1
                logger.warning(
                    "%s/%s: zombie running_task cleared (MANIFEST exists)",
                    wp_id, task_id,
                )
                continue
            spawn_time = spawned_at_map.get(task_id, 0)
            if spawn_time and now - spawn_time > WORKER_TIMEOUT_SECONDS:
                # 超 stale 窗口且无 MANIFEST = 僵尸（worker 被杀但从未写 MANIFEST）
                state.running_tasks.remove(task_id)
                cleared += 1
                logger.warning(
                    "%s/%s: zombie running_task cleared (stale >%ds, no MANIFEST)",
                    wp_id, task_id, WORKER_TIMEOUT_SECONDS,
                )
                continue
            # 保守保留：无 MANIFEST 且未超时（或无 spawn 时间记录）

        if cleared > 0:
            driver.orch._save_state()
        return cleared

    def _prepare_worker_retries(self, wp_id: str, driver) -> tuple[list[dict], list[dict]]:
        """A2/A3: derive 判 timed_out 的 task 走重试路径（无视 stale dedup 直接重派）。

        契约笼子：
        - attempts >= RETRY_BUDGET → 写合成 MANIFEST FAILED（derive 永久判 failed，
          级联 blocked），不再重派 + CRITICAL 告警
        - attempts < RETRY_BUDGET → 重派 + touch 目录（derive 视为 running，
          防下一 pulse 重复重派）

        Returns:
            (retry_spawn_params, alerts)
        """
        params: list[dict] = []
        alerts: list[dict] = []
        try:
            plan = driver.orch.load_execution_plan()
        except Exception as e:
            logger.warning("%s: retry pre-pass failed to load plan: %s", wp_id, e)
            return params, alerts
        if plan is None:
            return params, alerts

        progress = driver.orch._derive_worker_progress(plan)
        timed_out = sorted(progress.get("timed_out", set()))

        entry = self.progress.setdefault(wp_id, {})
        attempts_map = entry.setdefault("task_attempts", {})
        task_nodes = {t.task_id: t for t in plan.task_graph}

        if timed_out:
            for task_id in timed_out:
                attempts = attempts_map.get(task_id, 1)  # 目录存在 = 至少 spawn 过 1 次
                if attempts >= RETRY_BUDGET:
                    # 终态：合成 MANIFEST（契约笼子：失败必须显式落盘，不允许无限重试）
                    manifest_path = driver.worker_outputs_dir / task_id / "MANIFEST.json"
                    if not manifest_path.exists():
                        atomic_write_json(manifest_path, {
                            "task_id": task_id,
                            "status": "FAILED",
                            "failure_reason": f"retry_budget_exceeded ({attempts} attempts, no MANIFEST)",
                            "completed_at": time.time(),
                            "synthetic": True,
                        })
                    alerts.append({
                        "severity": "CRITICAL",
                        "code": "TASK_RETRY_EXHAUSTED",
                        "message": f"{wp_id}/{task_id}: 重试 {attempts} 次仍无产出，已标记终态失败",
                    })
                    continue
                task_node = task_nodes.get(task_id)
                if task_node is None:
                    continue
                try:
                    new_params = driver.orch._prepare_single_worker_spawn(task_node, plan)
                except Exception as e:
                    logger.warning("%s/%s: retry spawn prep failed: %s", wp_id, task_id, e)
                    continue
                # L3 fix: 删除 os.utime（不再需要刷 mtime 欺骗 derive）
                # 防下一 pulse 重复重派由 L2 task_spawned_at 冷却窗口承担
                # 职责分离：derive 报事实，账本管节奏
                params.append(new_params)
                alerts.append({
                    "severity": "INFO",
                    "code": "TASK_RETRY",
                    "message": f"{wp_id}/{task_id}: 第 {attempts + 1} 次重派（超时未产出）",
                })

        # F-B + quality_failure: 可救失败重试循环（与 timed_out 同等地位）
        # contract_violation: 实质产出合格但缺契约文件
        # quality_failure: 实质产出存在但验证判质量 FAIL（人工 backfill 标记）
        failed = sorted(progress.get("failed", set()))
        completed_set = progress.get("completed", set())
        wo_dir = driver.worker_outputs_dir
        for task_id in failed:
            manifest_path = wo_dir / task_id / "MANIFEST.json"
            if not manifest_path.exists():
                continue
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            failure_class = manifest_data.get("failure_class")
            if failure_class not in ("contract_violation", "quality_failure"):
                continue
            # quality_failure 依赖排序约束：只派发 deps 全 COMPLETE 的任务
            task_node = task_nodes.get(task_id)
            if task_node is None:
                continue
            if failure_class == "quality_failure":
                deps = set(getattr(task_node, "depends_on", None) or [])
                if deps and not deps.issubset(completed_set):
                    # deps 中含 failed/running 的任务留给后续 pulse
                    continue
            # quality_failure: quality_feedback 字段缺失时跳过（不编造反馈）
            if failure_class == "quality_failure":
                quality_feedback = manifest_data.get("quality_feedback")
                if not quality_feedback:
                    logger.warning(
                        "%s/%s: quality_failure but no quality_feedback in MANIFEST, skipping",
                        wp_id, task_id,
                    )
                    continue
            attempts = attempts_map.get(task_id, 1)
            if attempts >= RETRY_BUDGET:
                exhausted_code = (
                    "TASK_RETRY_CONTRACT_EXHAUSTED" if failure_class == "contract_violation"
                    else "TASK_RETRY_QUALITY_EXHAUSTED"
                )
                class_desc = "契约违规" if failure_class == "contract_violation" else "质量验证"
                alerts.append({
                    "severity": "INFO",
                    "code": exhausted_code,
                    "message": (
                        f"{wp_id}/{task_id}: {class_desc}重试预算耗尽 "
                        f"({attempts} attempts)，保持终态 FAILED"
                    ),
                })
                continue
            try:
                new_params = driver.orch._prepare_single_worker_spawn(task_node, plan)
            except Exception as e:
                retry_kind = "contract" if failure_class == "contract_violation" else "quality"
                logger.warning("%s/%s: %s retry spawn prep failed: %s", wp_id, task_id, retry_kind, e)
                continue
            # 在 prompt 末尾追加反馈段（检查 params 结构找 prompt 字段）
            prompt_key = "task" if "task" in new_params else None
            if prompt_key is None:
                logger.warning(
                    "%s/%s: %s retry params has no 'task' field, skipping feedback append",
                    wp_id, task_id, failure_class,
                )
            else:
                # auto_bootstrap 返回的 task 是引用字符串，实际 prompt 在文件中
                # 格式：用 `read` 工具读取: `{filepath}`
                bootstrap_text = new_params[prompt_key]
                path_match = re.search(r"读取:\s*`([^`]+)`", bootstrap_text)
                if path_match:
                    prompt_file = Path(path_match.group(1))
                    if prompt_file.exists():
                        # 列出 output_dir 实际文件（相对路径）
                        task_output_dir = wo_dir / task_id
                        existing_files: list[str] = []
                        try:
                            for p in task_output_dir.rglob("*"):
                                if p.is_file():
                                    try:
                                        existing_files.append(
                                            str(p.relative_to(task_output_dir))
                                        )
                                    except ValueError:
                                        existing_files.append(str(p))
                        except OSError:
                            pass
                        existing_files.sort()
                        files_list = (
                            "\n".join(f"- {f}" for f in existing_files)
                            if existing_files
                            else "（无）"
                        )
                        if failure_class == "quality_failure":
                            # quality_failure: 从 MANIFEST quality_feedback 读取失败原因
                            feedback = (
                                "\n\n## 上次失败反馈（质量验证 FAIL）\n"
                                f"前次交付验证 FAIL，失败原因：{quality_feedback}。"
                                "请针对性修正后重新交付完整契约文件。\n"
                            )
                        else:
                            # contract_violation: 按 failure_reason 区分反馈文案
                            failure_reason = manifest_data.get("failure_reason", "")
                            if "too short" in failure_reason:
                                problem_desc = "你的 DELIVERABLE.md 内容过短（<50字符），请基于已有产出充实它。"
                                action_desc = "基于已有产出充实 DELIVERABLE.md（主产物，≥50字符，整合已有报告内容）"
                            else:
                                problem_desc = "你缺少强制契约文件 DELIVERABLE.md，请基于已有产出补写。"
                                action_desc = "基于已有产出补写 DELIVERABLE.md（主产物，≥50字符，整合已有报告内容）"
                            feedback = (
                                "\n\n## 上次失败反馈（契约违规重试）\n"
                                f"你上次的实质产出已存在于输出目录（如下），但{problem_desc}\n"
                                f"已有文件：\n{files_list}\n"
                                f"本次任务：{action_desc}，"
                                "并更新 MANIFEST.json（status/outputs/completed_at）。不要重复已完成的实质工作。\n"
                            )
                        try:
                            with prompt_file.open("a", encoding="utf-8") as f:
                                f.write(feedback)
                        except OSError as e:
                            logger.warning(
                                "%s/%s: failed to append feedback to prompt file: %s",
                                wp_id, task_id, e,
                            )
                    else:
                        logger.warning(
                            "%s/%s: prompt file %s does not exist, skipping feedback append",
                            wp_id, task_id, prompt_file,
                        )
                else:
                    logger.warning(
                        "%s/%s: could not parse prompt file path from bootstrap string",
                        wp_id, task_id,
                    )
            params.append(new_params)
            if failure_class == "quality_failure":
                retry_code = "TASK_RETRY_QUALITY"
                retry_desc = "质量验证 FAIL 修正"
            else:
                retry_code = "TASK_RETRY_CONTRACT"
                retry_desc = "契约违规补写"
            alerts.append({
                "severity": "INFO",
                "code": retry_code,
                "message": f"{wp_id}/{task_id}: 第 {attempts + 1} 次重派（{retry_desc}）",
            })
        return params, alerts

    def _acquire_pulse_lock(self):
        """A1: 单实例文件锁（fcntl.flock 非阻塞）。

        flock 在 holder 进程死亡时自动释放，无 stale lock 残留问题。
        锁持有超 PULSE_LOCK_STALE_SECONDS 说明 holder 疑似挂起 → PulseLocked(alert)。
        """
        import fcntl

        lock_path = self.blackboard_root / self.project_name / PULSE_LOCK_FILENAME
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(lock_path, "a+", encoding="utf-8")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            alert = None
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > PULSE_LOCK_STALE_SECONDS:
                    alert = {
                        "severity": "CRITICAL",
                        "code": "LOCK_STALE",
                        "message": f"pulse 锁已被持有 {int(age)}s（>{PULSE_LOCK_STALE_SECONDS}s），holder 疑似挂起",
                    }
            except OSError:
                pass
            fh.close()
            raise PulseLocked(alert)
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        os.utime(lock_path, None)  # mtime 作为持有起始时间
        return fh

    def _count_in_flight(self) -> int:
        """A5: 当前在途 agent 数（文件系统真相 + 已确认未过期的非 worker dispatch）。"""
        from domains.deliver_pro.phase_deriver import derive_worker_progress

        n = 0
        now = time.time()
        for layer in self.layers:
            for wp_id in layer:
                if self.progress.get(wp_id, {}).get("terminal_failed"):
                    continue
                # worker running 计数（文件系统真相）
                wp_dir = self._wp_dir(wp_id)
                plan_path = wp_dir / "stages" / "execution_plan.json"
                if plan_path.exists():
                    try:
                        plan_data = json.loads(plan_path.read_text())
                        task_graph = plan_data.get("task_graph", [])
                        if task_graph:
                            plan_task_ids = {
                                t.get("task_id", "") if isinstance(t, dict) else str(t)
                                for t in task_graph
                            }
                            task_deps = {
                                (t.get("task_id", "") if isinstance(t, dict) else str(t)):
                                    (t.get("depends_on", []) if isinstance(t, dict) else [])
                                for t in task_graph
                            }
                            wp = derive_worker_progress(wp_dir, plan_task_ids, task_deps)
                            n += len(wp["running"])
                    except Exception as e:
                        logger.warning("%s: in-flight worker count failed: %s", wp_id, e)
                # 非 worker 的已确认未过期 dispatch（analyze/validate/package）
                entry = self.progress.get(wp_id, {})
                spawned_at = entry.get("last_spawned_at")
                last_action = entry.get("last_spawned_action", "")
                if (
                    spawned_at
                    and entry.get("dispatch_confirmed")
                    and not last_action.startswith("spawn_workers")
                ):
                    base_action = last_action.split(":")[0]
                    # F2 fix: 文件系统证据优先——产出已落盘 = 阶段已完成，立即释放名额
                    # （不再纯按 30min 超时等待。证据不存在才回退到时间推断）
                    evidence_rel = _ACTION_COMPLETION_EVIDENCE.get(base_action)
                    evidence_done = bool(
                        evidence_rel and (wp_dir / evidence_rel).exists()
                    )
                    if not evidence_done:
                        timeout = _STALE_DISPATCH_TIMEOUTS.get(base_action, _DEFAULT_STALE_TIMEOUT)
                        if now - spawned_at <= timeout:
                            n += 1
        return n

    def _update_pulse_state(self, n_spawn_actions: int, status: dict) -> tuple[dict, dict | None]:
        """A7: 零进展检测（连续 N 次无 spawn 且完成数未变 → STALLED 告警，30min 冷却）。"""
        state_path = self.blackboard_root / self.project_name / PULSE_STATE_FILENAME
        state: dict = {}
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text())
            except Exception:
                state = {}

        signature = f"{status['completed']}+{status.get('terminal_failed', 0)}/{status['total_wps']}"
        alert = None
        last_sig = state.get("last_signature")
        if n_spawn_actions == 0 and signature == last_sig:
            state["zero_progress_count"] = state.get("zero_progress_count", 0) + 1
        elif n_spawn_actions == 0 and last_sig is None:
            # 首次 pulse 即零动作 = 第一次零进展观察（计入阈值）
            state["zero_progress_count"] = 1
        else:
            # 签名变化（有进展）或有 spawn 动作（在派活）→ 归零
            state["zero_progress_count"] = 0
        state["last_signature"] = signature

        now = time.time()
        if (
            state["zero_progress_count"] >= STALLED_ALERT_THRESHOLD
            and now - state.get("last_alert_at", 0) > STALLED_ALERT_COOLDOWN_SECONDS
        ):
            state["last_alert_at"] = now
            alert = {
                "severity": "CRITICAL",
                "code": "STALLED",
                "message": (
                    f"连续 {state['zero_progress_count']} 次 pulse 零进展"
                    f"（{signature}），流水线疑似卡死，请人工检查"
                ),
            }
        atomic_write_json(state_path, state)
        return state, alert

    def confirm_dispatches(self, results: list[dict]) -> dict:
        """A4/P1-1: pulse agent spawn 后的两阶段确认/回滚。

        Args:
            results: [{"wp_id": str, "label": str, "ok": bool, "error": str|None}, ...]
                - ok=True → dispatch_confirmed=True（进入正常 30/90min stale 窗口）
                - ok=False → 回滚该 label 对应的 dispatch 记录（下次 pulse 立即重派）
                  + 删除空 task 目录 + spawn_failures 计数

        Returns:
            {"confirmed": int, "rolled_back": int, "failures": [...]}
        """
        confirmed = 0
        rolled_back = 0
        failures: list[dict] = []
        for r in results:
            wp_id = r.get("wp_id", "")
            label = r.get("label", "")
            ok = bool(r.get("ok"))
            entry = self.progress.get(wp_id)
            if not isinstance(entry, dict) or not entry.get("last_spawned_action"):
                continue
            if ok:
                entry["dispatch_confirmed"] = True
                confirmed += 1
                continue
            # 回滚：从 dedup_key 中移除失败的 task（部分确认其余）
            last = entry["last_spawned_action"]
            base, _, ids = last.partition(":")
            if ids:
                # F5 fix: label 已带 WP 前缀（deliver-worker-{wp_id}-{task_id}），
                # 必须先 strip 前缀再匹配 dedup_key 中的裸 task_id（如 T-001）；
                # 否则 matched 永远为空 → 回滚静默失效 + 失败目录不清理
                wp_prefix = f"deliver-worker-{wp_id.lower()}-"
                if label.lower().startswith(wp_prefix):
                    tid = label[len(wp_prefix):]
                else:  # 向后兼容旧格式（deliver-worker-{task_id}）
                    tid = label.replace("deliver-worker-", "")
                # F2: strip 冲突 fallback 追加的时间戳后缀（_{10+ digits}）
                # 必须在匹配 dedup_key 之前 strip，否则 tid 带后缀永远匹配不上
                tid = re.sub(r"_\d{10,}$", "", tid)
                id_list = ids.split(",")
                matched = [x for x in id_list if x.lower() == tid.lower()]
                remaining = [x for x in id_list if x not in matched]
                if remaining:
                    entry["last_spawned_action"] = f"{base}:{','.join(sorted(remaining))}"
                    entry["dispatch_confirmed"] = True  # 其余 spawn 成功 → 部分确认
                else:
                    for k in ("last_spawned_action", "last_spawned_at", "dispatch_confirmed"):
                        entry.pop(k, None)
                for t in matched:
                    self._drop_task_dir_if_empty(wp_id, t)
            else:
                for k in ("last_spawned_action", "last_spawned_at", "dispatch_confirmed"):
                    entry.pop(k, None)
            entry["spawn_failures"] = entry.get("spawn_failures", 0) + 1
            # L2/L4 fix: 回滚时清理 per-task 账本（解禁冷却窗口 + 递减 attempts）
            if ids and matched:
                spawned_at_map = entry.get("task_spawned_at", {})
                attempts_map = entry.get("task_attempts", {})
                for t in matched:
                    spawned_at_map.pop(t, None)  # L2: 解禁冷却窗口，下次 pulse 可立即重派
                    if t in attempts_map and attempts_map[t] > 0:
                        attempts_map[t] -= 1  # L4: spawn 失败不算执行，递减计数
            rolled_back += 1
            failures.append({"wp_id": wp_id, "label": label, "error": r.get("error")})
            logger.warning("%s/%s: spawn rolled back — %s", wp_id, label, r.get("error"))
        self._save_progress()
        return {"confirmed": confirmed, "rolled_back": rolled_back, "failures": failures}

    def _orphan_sweep(self) -> None:
        """A4: 未确认的 spawn_workers 记录超孤儿窗口 → 清除记录 + 删除空 task 目录。

        为什么需要独立清扫：worker 目录在 params 生成时即创建（driver 行为），
        孤儿 task 目录是"新鲜"的 → derive 视为 running → 正常 dedup 路径永远
        匹配不到旧 dedup_key（ready 集合已变）。若不清扫，孤儿 worker 要等
        30min WORKER_TIMEOUT 才走重试路径；清扫后下次 tick 即可重派（~10min）。
        """
        now = time.time()
        swept = False
        for wp_id, entry in self.progress.items():
            if not isinstance(entry, dict):
                continue
            last = entry.get("last_spawned_action") or ""
            if not last.startswith("spawn_workers"):
                continue
            if entry.get("dispatch_confirmed"):
                continue
            spawned_at = entry.get("last_spawned_at")
            if spawned_at and now - spawned_at > ORPHAN_DISPATCH_WINDOW_SECONDS:
                removed = self._cleanup_orphan_worker_dirs(wp_id)
                for k in ("last_spawned_action", "last_spawned_at", "dispatch_confirmed"):
                    entry.pop(k, None)
                swept = True
                logger.warning(
                    "%s: orphan spawn_workers sweep (unconfirmed >%ds, %d dirs dropped)",
                    wp_id, ORPHAN_DISPATCH_WINDOW_SECONDS, removed,
                )
        # F1b: 无记录孤儿空目录清扫（budget=0 分支若清理遗漏的兜底）
        if self._sweep_recordless_orphan_dirs():
            swept = True
        if swept:
            self._save_progress()

    def _sweep_recordless_orphan_dirs(self) -> bool:
        """F1b: 清扫"无 task_spawned_at 记录 + 空 + 超宽限期"的孤儿目录。

        结构性兜底：budget=0 分支（F1a）若清理遗漏，或未来新增否决路径忘记清理，
        此处 5min 内自愈，防孤儿目录被 derive 误判 running 占坑 30min。

        豁免规则（场景穷举已验证不会误删）：
        - 非空目录（worker 已写产出）→ _drop_task_dir_if_empty 物理跳过
        - 有 task_spawned_at 记录（真 spawn 过，worker 可能慢启动）→ 豁免
        - 目录年龄 <= 5min（可能是刚创建的合法目录）→ 豁免
        """
        now = time.time()
        any_swept = False
        # 遍历所有已知 WP（不能只遍历 progress.keys()——无 progress 条目的 WP 也会有孤儿目录）
        all_wp_ids = {wp_id for layer in self.layers for wp_id in layer}
        for wp_id in all_wp_ids:
            entry = self.progress.get(wp_id, {})
            if not isinstance(entry, dict):
                continue
            spawned_at_map = entry.get("task_spawned_at", {})
            worker_outputs = self._wp_dir(wp_id) / "stages" / "worker_outputs"
            if not worker_outputs.is_dir():
                continue
            for task_dir in worker_outputs.iterdir():
                if not task_dir.is_dir():
                    continue
                tid = task_dir.name
                if tid in spawned_at_map:
                    continue  # 有 spawn 记录 → 真 worker，豁免
                try:
                    age = now - task_dir.stat().st_mtime
                except OSError:
                    continue
                if age <= RECORDLESS_ORPHAN_GRACE_SECONDS:
                    continue  # 宽限期内 → 豁免
                if self._drop_task_dir_if_empty(wp_id, tid):
                    any_swept = True
                    logger.warning(
                        "%s/%s: recordless orphan dir swept (empty, no spawn record, age=%ds)",
                        wp_id, tid, int(age),
                    )
        return any_swept

    # ------------------------------------------------------------------
    # Final Synthesis 架构（2026-07-29）
    # ------------------------------------------------------------------

    def _batch_dir(self) -> Path:
        """批次根目录（blackboard/{project}/）。"""
        return self.blackboard_root / self.project_name

    def _living_spec_path(self) -> Path:
        """living_spec.json 路径（与 solution_pro 路径约定一致）。"""
        return self._batch_dir() / "data" / "living_spec.json"

    def _read_living_spec(self) -> dict:
        """读取 living_spec.json。

        Raises:
            ValueError: living_spec 缺失或不可读（禁止 fallback 到 frozen_spec，禁止静默）
        """
        path = self._living_spec_path()
        if not path.exists():
            raise ValueError(
                f"living_spec.json not found at {path}. "
                f"Final Synthesis requires living_spec to exist. "
                f"Please run Spec Pro first to generate living_spec before running Final Synthesis."
            )
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            raise ValueError(
                f"living_spec.json at {path} is unreadable: {e}. "
                f"Please ensure the file is valid JSON and re-run Spec Pro if needed."
            ) from e

    def _contract_path(self) -> Path:
        """_deliverable_contract.json 路径（批次根）。"""
        return self._batch_dir() / DELIVERABLE_CONTRACT_FILENAME

    def _final_gate_report_path(self) -> Path:
        """_final_gate_report.json 路径（批次根）。"""
        return self._batch_dir() / FINAL_GATE_REPORT_FILENAME

    def _final_deliverable_done_path(self) -> Path:
        """_final_deliverable_done.json 路径（批次根）。"""
        return self._batch_dir() / FINAL_DELIVERABLE_DONE_FILENAME

    def _final_synthesis_dir(self) -> Path:
        """final_synthesis/ 目录（批次根）。"""
        return self._batch_dir() / FINAL_SYNTHESIS_DIRNAME

    def _gate_spawned_path(self) -> Path:
        """Gate action spawned flag 文件路径。"""
        return self._batch_dir() / FINAL_GATE_SPAWNED_FILENAME

    def _should_infer_contract(self) -> bool:
        """是否应推断交付物契约（批次启动阶段，无 contract 文件时）。
        
        仅在批次启动阶段（无 WP 活动）时返回 True。
        如果 WP 已经在运行或完成，说明已过启动阶段，不再推断 contract（兼容旧批次）。
        """
        if self._contract_path().exists():
            return False
        # 检查是否有 WP 活动（任何 WP 有 progress 记录或 stages 目录）
        for layer in self.layers:
            for wp_id in layer:
                # 检查 progress 记录
                if self.progress.get(wp_id):
                    return False
                # 检查 stages 目录是否存在
                wp_dir = self._wp_dir(wp_id)
                if (wp_dir / "stages").exists():
                    return False
        return True

    def _all_wps_derive_done(self) -> bool:
        """检查全部 WP 的 derive phase 是否均为 DONE。"""
        for layer in self.layers:
            for wp_id in layer:
                phase = self._check_wp_phase(wp_id)
                if phase != "DONE":
                    return False
        return True

    def _no_inflight_actions(self) -> bool:
        """检查当前无 in-flight 动作（简化版：无 last_spawned_action 未完成的 WP）。"""
        for layer in self.layers:
            for wp_id in layer:
                entry = self.progress.get(wp_id, {})
                if entry.get("last_spawned_action") and not entry.get("terminal_failed"):
                    # 有未确认的分发记录 → 可能有 in-flight
                    if not self._is_stale_dispatch(entry, entry["last_spawned_action"]):
                        return False
        return True

    def _should_trigger_final_synthesis(self) -> bool:
        """Final Synthesis 触发条件检查。"""
        # 条件 1: 全部 WP derive DONE
        if not self._all_wps_derive_done():
            return False
        # 条件 2: 无 in-flight 动作
        if not self._no_inflight_actions():
            return False
        # 条件 3: contract 存在
        if not self._contract_path().exists():
            return False
        # 条件 4: 无 _final_deliverable_done.json
        if self._final_deliverable_done_path().exists():
            return False
        return True

    def _build_infer_contract_action(self) -> dict:
        """构建 infer_deliverable_contract 动作。"""
        living_spec = self._read_living_spec()  # 缺失直接 raise
        spec_summary = json.dumps(living_spec, ensure_ascii=False)[:3000]
        task = (
            f"You are a Deliverable Contract Inferencer.\n"
            f"Read the following living_spec and output a JSON contract to:\n"
            f"{self._contract_path()}\n\n"
            f"Output format:\n"
            f"{{\n"
            f'  "deliverable_type": "software|report|framework|files",\n'
            f'  "req_elements": [\n'
            f'    {{"element": "<requirement element>", "criticality": "MUST|SHOULD"}}\n'
            f"  ],\n"
            f'  "required_structure": ["<section/artifact name>", ...]\n'
            f"}}\n\n"
            f"living_spec (truncated):\n{spec_summary}\n\n"
            f"Rules:\n"
            f"- Extract requirement elements from living_spec\n"
            f"- MUST = core requirement, SHOULD = nice-to-have\n"
            f"- required_structure = sections/artifacts the deliverable must contain\n"
            f"- Write the JSON to the specified path using atomic_write_json\n"
        )
        return {
            "wp_id": "BATCH",
            "action": "infer_deliverable_contract",
            "task": task,
            "label": f"infer-contract-{self.project_name.lower()}",
            "mode": "run",
            "thinking": "medium",
        }

    def _build_final_synthesis_action(self) -> dict:
        """构建 final_synthesis 动作。"""
        contract = json.loads(self._contract_path().read_text(encoding="utf-8"))
        living_spec = self._read_living_spec()
        spec_summary = json.dumps(living_spec, ensure_ascii=False)[:3000]
        contract_summary = json.dumps(contract, ensure_ascii=False)[:2000]
        synthesis_dir = self._final_synthesis_dir()
        synthesis_dir.mkdir(parents=True, exist_ok=True)
        task = (
            f"You are a Final Synthesis Agent.\n"
            f"Read the living_spec, deliverable contract, and each WP's final_deliverable.\n"
            f"Generate the final deliverable according to contract.deliverable_type:\n"
            f"- report → comprehensive report document\n"
            f"- framework → framework doc + index\n"
            f"- software → runnable package + README\n"
            f"- files → organized file collection\n\n"
            f"Output to: {synthesis_dir}/\n\n"
            f"living_spec (truncated):\n{spec_summary}\n\n"
            f"contract (truncated):\n{contract_summary}\n\n"
            f"Rules:\n"
            f"- Do NOT overwrite individual WP final_deliverables\n"
            f"- Synthesize across all WPs into a cohesive deliverable\n"
            f"- Ensure all MUST req_elements are addressed\n"
        )
        return {
            "wp_id": "BATCH",
            "action": "final_synthesis",
            "task": task,
            "label": f"final-synthesis-{self.project_name.lower()}",
            "mode": "run",
            "thinking": "medium",
        }

    def _build_run_final_gate_action(self) -> dict:
        """构建 run_final_gate 动作（LLM-as-Judge 语义回溯 Gate）。
        
        Returns:
            Spawn action dict for LLM to judge each req_element as COVERED/PARTIAL/MISSING
        """
        contract = json.loads(self._contract_path().read_text(encoding="utf-8"))
        req_elements = contract.get("req_elements", [])
        synthesis_dir = self._final_synthesis_dir()
        
        # Collect synthesis output for LLM context
        synthesis_text = ""
        if synthesis_dir.exists():
            for f in synthesis_dir.rglob("*"):
                if f.is_file() and f.stat().st_size > 0:
                    try:
                        synthesis_text += f.read_text(encoding="utf-8", errors="ignore")[:5000]
                    except Exception:
                        pass
        
        contract_summary = json.dumps(contract, ensure_ascii=False)[:2000]
        
        task = (
            f"You are a Semantic Gate Judge (LLM-as-Judge).\n"
            f"Read the deliverable contract and final synthesis output.\n"
            f"For each requirement element in contract.req_elements, judge its coverage:\n"
            f"- COVERED: Fully addressed in synthesis\n"
            f"- PARTIAL: Partially addressed (mention but incomplete)\n"
            f"- MISSING: Not addressed at all\n\n"
            f"Contract (truncated):\n{contract_summary}\n\n"
            f"Final Synthesis Output:\n{synthesis_text[:10000]}\n\n"
            f"Output Format (write to {self._final_gate_report_path()}):\n"
            f"{{\n"
            f'  "gaps": [\n'
            f'    {{"element": "<req element>", "criticality": "MUST|SHOULD", "status": "COVERED|PARTIAL|MISSING", "reason": "<brief explanation>"}}\n'
            f"  ]\n"
            f"}}\n\n"
            f"Rules:\n"
            f"- Judge SEMANTICALLY, not by keyword matching\n"
            f"- MUST elements are critical; MISSING = HARD_BLOCK\n"
            f"- SHOULD elements are nice-to-have; MISSING = recorded but not blocking\n"
            f"- Write the JSON to the specified path using atomic_write_json\n"
            f"- If you cannot determine coverage, mark as MISSING (fail-closed)\n"
        )
        return {
            "wp_id": "BATCH",
            "action": "run_final_gate",
            "task": task,
            "label": f"final-gate-{self.project_name.lower()}",
            "mode": "run",
            "thinking": "medium",
        }
    
    def _process_gate_report(self) -> dict:
        """Process the gate report written by LLM judge.
        
        Returns:
            {"passed": bool, "gaps": [...], "report_path": str}
        
        Raises:
            ValueError: MUST 要素 MISSING → HARD_BLOCK, or report invalid/missing (fail-closed)
        """
        report_path = self._final_gate_report_path()
        
        # Fail-closed: report must exist
        if not report_path.exists():
            raise ValueError(
                f"Gate report not found at {report_path}. "
                f"LLM judge failed to write judgment. Fail-closed: cannot proceed."
            )
        
        # Fail-closed: report must be valid JSON
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise ValueError(
                f"Gate report at {report_path} is invalid JSON: {e}. "
                f"Fail-closed: cannot proceed."
            ) from e
        
        # Fail-closed: report must have expected structure
        gaps = report.get("gaps")
        if not isinstance(gaps, list):
            raise ValueError(
                f"Gate report at {report_path} missing 'gaps' array. "
                f"Fail-closed: cannot proceed."
            )
        
        # Check MUST elements
        must_missing = [g for g in gaps if g.get("criticality") == "MUST" and g.get("status") == "MISSING"]
        report["passed"] = len(must_missing) == 0
        report["must_missing"] = must_missing
        report["report_path"] = str(report_path)
        
        # Re-write with computed fields
        atomic_write_json(report_path, report)
        
        if must_missing:
            raise ValueError(
                f"HARD_BLOCK: MUST elements missing: {[m['element'] for m in must_missing]}. "
                f"Final deliverable cannot be declared complete."
            )
        return report

    def _mark_final_deliverable_done(self, gate_report: dict) -> None:
        """标记 Final Synthesis 完成。"""
        done_data = {
            "completed_at": time.time(),
            "gate_passed": gate_report.get("passed", False),
            "gaps": gate_report.get("gaps", []),
            "synthesis_dir": str(self._final_synthesis_dir()),
        }
        atomic_write_json(self._final_deliverable_done_path(), done_data)

    def pulse(self) -> dict:
        """脉冲式调度单次 tick（V1, 2026-07-24 评审裁决 A1-A8 落地）。

        形态：cron 每 5min 触发 isolated session → exec 跑本方法 →
        动作落盘 _pulse_actions.json → agent 逐条 spawn → 回执 confirm。

        契约笼子：
        - 产出必须通过 PulseReport Pydantic 验证（extra=forbid，写时校验）
        - 所有落盘原子写（temp + os.replace）
        - 单实例文件锁（fcntl.flock 非阻塞，holder 死亡自动释放）
        - 不依赖任何 session 长寿 / 事件投递（文件系统是唯一真相）

        Returns:
            PulseReport dict（同时写入 blackboard/{project}/_pulse_actions.json）
        """
        from domains.deliver_pro.contracts.pulse_report import (
            PulseAction,
            PulseAlert,
            PulseReport,
            PulseSummary,
        )

        project_dir = self.blackboard_root / self.project_name
        completed_path = project_dir / PULSE_COMPLETED_FILENAME
        actions_path = project_dir / PULSE_ACTIONS_FILENAME

        def _build_report(
            status: str,
            actions: list[dict],
            alerts: list[dict],
            summary: dict,
        ) -> dict:
            report = PulseReport(
                pulse_id=f"pulse-{int(time.time())}",
                project_name=self.project_name,
                generated_at=time.time(),
                status=status,  # type: ignore[arg-type]
                actions=[PulseAction(**a) for a in actions],
                alerts=[PulseAlert(**a) for a in alerts],
                summary=PulseSummary(**summary),
            )
            data = report.model_dump(mode="json")
            atomic_write_json(actions_path, data)
            return data

        # A8: 完成标记快速通道（零扫描退出，不烧 token 之外的任何资源）
        if completed_path.exists():
            try:
                completed_data = json.loads(completed_path.read_text())
            except Exception:
                completed_data = {}
            return _build_report(
                status="completed",
                actions=[],
                alerts=[],
                summary={
                    "total_wps": completed_data.get("total_wps", 0),
                    "completed": completed_data.get("completed", 0),
                    "terminal_failed": completed_data.get("terminal_failed", 0),
                    "in_progress": 0,
                    "in_flight": 0,
                    "zero_progress_count": 0,
                    "truncated": False,
                },
            )

        # A1: 单实例锁
        try:
            lock_fh = self._acquire_pulse_lock()
        except PulseLocked as e:
            status = self.get_status()
            return _build_report(
                status="locked",
                actions=[],
                alerts=[e.alert] if e.alert else [],
                summary={
                    "total_wps": status["total_wps"],
                    "completed": status["completed"],
                    "terminal_failed": status["terminal_failed"],
                    "in_progress": status["in_progress"],
                    "in_flight": 0,
                    "zero_progress_count": 0,
                    "truncated": False,
                },
            )

        try:
            alerts: list[dict] = []

            # A4: 孤儿 spawn_workers 清扫（记录 + 空目录）
            self._orphan_sweep()

            # === Final Synthesis 前置检查（2026-07-29） ===
            # 阶段 1: 批次启动时推断交付物契约
            # 铁律：需求对齐是硬性要求，living_spec 缺失直接 raise，禁止静默跳过
            if self._should_infer_contract():
                # _build_infer_contract_action 内部调用 _read_living_spec()
                # 若 living_spec 缺失/不可读 → ValueError 直接 propagate（不 catch）
                contract_action = self._build_infer_contract_action()
                # 契约推断优先于正常 tick，直接返回
                return _build_report(
                    status="active",
                    actions=[contract_action],
                    alerts=[],
                    summary={
                        "total_wps": sum(len(l) for l in self.layers),
                        "completed": 0,
                        "terminal_failed": 0,
                        "in_progress": sum(len(l) for l in self.layers),
                        "in_flight": 0,
                        "zero_progress_count": 0,
                        "truncated": False,
                    },
                )

            # A5: 并发上限 → spawn 预算（在 tick 记录 dispatch 之前拦截）
            in_flight = self._count_in_flight()
            budget = max(0, min(MAX_IN_FLIGHT - in_flight, MAX_SPAWN_PER_PULSE))

            # 单次全量扫描（内含 dedup / stale / 重试 / 终态处理）
            tick_results = self.tick(max_spawn_budget=budget)

            # 收集 spawn 候选 + 传播 tick 内告警 + 处理终态动作
            candidates: list[dict] = []
            for item in tick_results:
                wp_id = item["wp_id"]
                action = item["action"]
                for a in item.get("alerts", []):
                    alerts.append(a)
                if action in ("done", "skip"):
                    continue
                if action == "terminal_failed":
                    self.progress.setdefault(wp_id, {})["terminal_failed"] = True
                    alerts.append({
                        "severity": "CRITICAL",
                        "code": "TERMINAL_FAILED",
                        "message": f"{wp_id}: {item.get('error', 'terminal failed')}",
                    })
                    continue
                if action.startswith("assemble"):
                    continue  # 确定性代码已在 tick 内执行
                params = item.get("spawn_params")
                if not params:
                    # A#1(DryRun R1): 错误 action 不静默丢弃 — 转 WARN alert（可观测性）
                    if item.get("error"):
                        alerts.append({
                            "severity": "WARN",
                            "code": "ACTION_ERROR",
                            "message": f"{wp_id}/{action}: {item['error']}",
                        })
                    continue
                param_list = params if isinstance(params, list) else [params]
                # F2: label 冲突 fallback — 若该 WP 有 spawn 失败记录（含 label already in use），
                # 追加 _{timestamp} 后缀避免与旧 session 撞名循环。
                # 首次 spawn 保持确定性格式（不改变 label），仅冲突后加后缀。
                # P1-polish: 扩展到 validate/package action（生产事故 00:16:18 label 冲突）
                _entry = self.progress.get(wp_id, {})
                _should_add_suffix = (
                    action in ("spawn_workers", "validate", "package")
                    and _entry.get("spawn_failures", 0) > 0
                )
                for p in param_list:
                    if not isinstance(p, dict) or not p.get("task"):
                        continue
                    _label = p.get("label", f"{action}-{wp_id.lower()}")
                    if _should_add_suffix and not re.search(r"_\d{10,}$", _label):
                        _label = f"{_label}_{int(time.time())}"
                    candidates.append({
                        "wp_id": wp_id,
                        "action": action if action != "spawn_workers" else "spawn_workers",
                        "task": p["task"],
                        "label": _label,
                        "model": p.get("model"),
                        "mode": p.get("mode", "run"),
                        "thinking": p.get("thinking", "medium"),
                    })
                # P1-polish: 重置计数器移出循环，确保多 param wave 都获后缀
                if _should_add_suffix:
                    _entry["spawn_failures"] = 0
                    self.progress[wp_id] = _entry

            if self._last_tick_truncated:
                alerts.append({
                    # INFO 而非 WARN：预算截断是正常节流行为，不值得飞书告警
                    # （2026-07-24 首轮运行刷屏 15 条教训）
                    "severity": "INFO",
                    "code": "IN_FLIGHT_CAP",
                    "message": (
                        f"并发上限截断：in_flight={in_flight}，本次预算 {budget}，"
                        f"部分动作延迟到下一 pulse"
                    ),
                })

            # === Final Synthesis 触发检查（2026-07-29） ===
            # 阶段 2: 全部 WP DONE 后触发 final_synthesis
            if self._should_trigger_final_synthesis():
                try:
                    synthesis_action = self._build_final_synthesis_action()
                    candidates.append(synthesis_action)
                except Exception as e:
                    alerts.append({
                        "severity": "WARN",
                        "code": "FINAL_SYNTHESIS_BUILD_FAILED",
                        "message": str(e),
                    })

            # 阶段 3: final_synthesis 产出落盘后执行语义回溯 Gate（LLM-as-Judge）
            # 铁律：语义判断必须用 LLM，禁止关键词检查
            if (
                self._final_synthesis_dir().exists()
                and self._contract_path().exists()
            ):
                # 检查 synthesis 是否有实质产出
                synthesis_has_content = any(
                    f.is_file() and f.stat().st_size > 0
                    for f in self._final_synthesis_dir().rglob("*")
                )
                if synthesis_has_content:
                    gate_report_exists = self._final_gate_report_path().exists()
                    gate_spawned = self._gate_spawned_path().exists()
                    
                    if gate_report_exists:
                        # LLM 已写完 judgment → Python 侧处理
                        try:
                            gate_report = self._process_gate_report()
                            if gate_report.get("passed"):
                                self._mark_final_deliverable_done(gate_report)
                        except ValueError as e:
                            # MUST 要素 MISSING 或 report 非法 → HARD_BLOCK
                            alerts.append({
                                "severity": "CRITICAL",
                                "code": "SEMANTIC_GATE_HARD_BLOCK",
                                "message": str(e),
                            })
                    elif gate_spawned:
                        # Gate action 已 spawn 但无 report → LLM 失败 → fail-closed
                        alerts.append({
                            "severity": "CRITICAL",
                            "code": "SEMANTIC_GATE_LLM_FAILED",
                            "message": (
                                "Gate action was spawned but LLM judge failed to write report. "
                                "Fail-closed: cannot proceed. Please check LLM session and re-run."
                            ),
                        })
                    else:
                        # 首次触发：spawn gate action + 写 flag
                        try:
                            gate_action = self._build_run_final_gate_action()
                            candidates.append(gate_action)
                            # 写 flag 标记已 spawn
                            atomic_write_json(self._gate_spawned_path(), {
                                "spawned_at": time.time(),
                                "action": "run_final_gate",
                            })
                        except Exception as e:
                            # 构建 action 失败（如 contract 不可读）→ fail-closed
                            alerts.append({
                                "severity": "CRITICAL",
                                "code": "SEMANTIC_GATE_BUILD_FAILED",
                                "message": f"Failed to build gate action: {e}. Fail-closed.",
                            })

            # A7: 零进展检测
            status = self.get_status()
            pulse_state, stalled_alert = self._update_pulse_state(len(candidates), status)
            if stalled_alert:
                alerts.append(stalled_alert)

            # A2/P1-4: 终态判定（2026-07-29 更新：需 final_synthesis 完成）
            # 完成条件：all_resolved + _final_deliverable_done.json 存在
            final_done = self._final_deliverable_done_path().exists()
            if status["all_resolved"] and final_done:
                terminal_wps = [
                    wp for layer in self.layers for wp in layer
                    if self.progress.get(wp, {}).get("terminal_failed")
                ]
                atomic_write_json(completed_path, {
                    "completed_at": time.time(),
                    "total_wps": status["total_wps"],
                    "completed": status["completed"],
                    "terminal_failed": status["terminal_failed"],
                    "terminal_failed_wps": terminal_wps,
                    "final_synthesis_done": True,
                })
                pulse_status = "completed"
            elif status["all_resolved"] and not final_done:
                # 全部 WP DONE 但 final_synthesis 未完成 → 保持 active
                pulse_status = "active"
            else:
                pulse_status = "active" if candidates else "idle"

            # F1: 刷新 batch_progress 中每个 WP 的 phase（与 derive_phase 对齐）
            # V3 Pulse 路径写完 PACKAGING 后再无代码更新 phase，导致监控说谎。
            # delivery_state.json 由 wp_runner 管理（orchestrator 不写入），且
            # _check_wp_phase 注释明确 "文件系统即真相"，故只刷新 batch_progress。
            for layer in self.layers:
                for wp_id in layer:
                    entry = self.progress.get(wp_id)
                    if not isinstance(entry, dict):
                        continue
                    derived = self._check_wp_phase(wp_id)
                    if entry.get("phase") != derived:
                        entry["phase"] = derived
                        self.progress[wp_id] = entry

            self._save_progress()
            return _build_report(
                status=pulse_status,
                actions=candidates,
                alerts=alerts,
                summary={
                    "total_wps": status["total_wps"],
                    "completed": status["completed"],
                    "terminal_failed": status["terminal_failed"],
                    "in_progress": status["in_progress"],
                    # B#3(DryRun R1): 终态报告中在途数归零（all_resolved 后残留计数只是采样时序差）
                    "in_flight": 0 if pulse_status == "completed" else in_flight,
                    "zero_progress_count": pulse_state.get("zero_progress_count", 0),
                    "truncated": self._last_tick_truncated,
                },
            )
        finally:
            import fcntl

            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
            lock_fh.close()

    def drive_once(self) -> dict:
        """Auto-loop 接口：一次调用返回当前所有可执行的 spawn 动作。

        Pulse 模式（deliver_pulse.md）：
            result = driver.drive_once()
            for action in result["spawn_actions"]:
                sessions_spawn(task=action["task"], label=action["label"], ...)
            # 🔴 绝不 sessions_yield — spawn 后立即结束，状态由下次 pulse 推导

        自动处理（无需 Agent 干预）：
        - State reconcile（completed/running tasks 从 MANIFEST 同步）
        - Assembly（确定性代码，自动执行）
        - Dedup（已 spawn 的不重复返回）
        - Stale running_tasks 清理

        Returns:
            {
                "all_done": bool,
                "spawn_actions": [
                    {"wp_id": str, "action": str, "task": str, "label": str, ...},
                ],
                "status": dict,  # get_status() output
                "auto_completed": [str],  # actions auto-executed (e.g., assemble)
            }
        """
        _check_drive_mode_allowed("drive_once()")
        status = self.get_status()
        if status["all_done"]:
            return {"all_done": True, "spawn_actions": [], "status": status, "auto_completed": []}

        tick_results = self.tick()
        spawn_actions = []
        auto_completed = []
        for item in tick_results:
            wp_id = item["wp_id"]
            action = item["action"]
            params = item.get("spawn_params")

            if action == "done":
                auto_completed.append(f"{wp_id}:{action}")
                continue

            # P1-4 fix: skip ≠ progress. Track separately so drive_all can detect waiting.
            if action == "skip":
                # Don't add to auto_completed — it's not real progress
                continue

            # P1-7 fix: terminal_failed is a final state, not retryable
            if action == "terminal_failed":
                auto_completed.append(f"{wp_id}:{action}")
                continue

            if action.startswith("assemble"):
                # Assembly is auto-executed by tick(), record it
                auto_completed.append(f"{wp_id}:{action}")
                continue

            if params:
                # Extract spawn-relevant fields
                if isinstance(params, list):
                    for p in params:
                        spawn_actions.append({
                            "wp_id": wp_id,
                            "action": action,
                            "task": p.get("task", ""),
                            "label": p.get("label", ""),
                            "model": p.get("model"),
                            "mode": p.get("mode", "run"),
                            "thinking": p.get("thinking", "medium"),
                        })
                else:
                    spawn_actions.append({
                        "wp_id": wp_id,
                        "action": action,
                        "task": params.get("task", ""),
                        "label": params.get("label", ""),
                        "model": params.get("model"),
                        "mode": params.get("mode", "run"),
                        "thinking": params.get("thinking", "medium"),
                    })
            elif item.get("error"):
                logger.warning(f"{wp_id}: {action} failed — {item['error']}")

        # Refresh status after tick
        status = self.get_status()
        return {
            "all_done": status["all_done"],
            "spawn_actions": spawn_actions,
            "status": status,
            "auto_completed": auto_completed,
        }

    def drive_all(self, max_iterations: int = 50) -> dict:
        """Blocking auto-loop: keep driving until agents need to spawn or pipeline is done.

        Pulse 模式（deliver_pulse.md）：
            result = driver.drive_all()
            for action in result["spawn_actions"]:
                sessions_spawn(task=action["task"], label=action["label"], ...)
            # 🔴 绝不 sessions_yield — spawn 后立即结束，状态由下次 pulse 推导

        内部自动处理（无需 Agent 干预）:
        - 所有确定性转换（Assembly, state reconcile, dedup）
        - NOT_FOUND verdict → skip（等 validate agent 完成）
        - 多轮 tick() 直到需要 agent 干预

        Args:
            max_iterations: 安全上限，防止无限循环

        Returns:
            {
                "all_done": bool,
                "spawn_actions": [...],  # 需要 agent spawn 的动作
                "auto_completed": [...],  # 自动完成的动作
                "iterations": int,  # tick() 调用次数
            }
        """
        _check_drive_mode_allowed("drive_all()")
        all_auto_completed = []
        iterations = 0

        for i in range(max_iterations):
            iterations += 1
            result = self.drive_once()

            if result["all_done"]:
                return {
                    "all_done": True,
                    "spawn_actions": [],
                    "auto_completed": all_auto_completed + result.get("auto_completed", []),
                    "iterations": iterations,
                }

            # Collect auto-completed actions
            all_auto_completed.extend(result.get("auto_completed", []))

            # If there are spawn actions, return them to the agent
            if result["spawn_actions"]:
                return {
                    "all_done": False,
                    "spawn_actions": result["spawn_actions"],
                    "auto_completed": all_auto_completed,
                    "iterations": iterations,
                    "status": result.get("status", {}),
                }

            # No spawn actions but not done — keep driving (deterministic transitions)
            # This handles cases where tick() returns only skip/done/assemble actions

            # P1-1 fix: Early exit on consecutive empty iterations (agents still running)
            # If only "skip" actions (e.g., NOT_FOUND verdict), return "waiting" instead
            # of burning through max_iterations scanning the filesystem.
            if not result.get("auto_completed") and not result.get("spawn_actions"):
                # Truly empty iteration — nothing happened, agents still running
                return {
                    "all_done": False,
                    "spawn_actions": [],
                    "auto_completed": all_auto_completed,
                    "iterations": iterations,
                    "waiting": True,
                }

        # Safety limit reached
        return {
            "all_done": False,
            "spawn_actions": [],
            "auto_completed": all_auto_completed,
            "iterations": iterations,
            "error": f"max_iterations ({max_iterations}) reached without spawning or completing",
        }

    def get_progress_report(self) -> str:
        """生成人类可读的 pipeline 进度报告。"""
        status = self.get_status()
        lines = [
            f"## Deliver Pro Pipeline Status",
            f"Total: {status['total_wps']} | Done: {status['completed']} | Failed: {status['failed']} | In Progress: {status['in_progress']}",
            f"All Done: {status['all_done']}",
            "",
        ]

        for layer_idx, layer in enumerate(self.layers):
            lines.append(f"### Layer {layer_idx}")
            for wp_id in layer:
                phase = self._check_wp_phase(wp_id)
                # Check validation score if available
                proj = f"deliver_{wp_id.lower().replace('-', '_')}"
                wp_subdir = wp_id.lower().replace('-', '_')
                vr = self.blackboard_root / proj / "deliver_pro" / wp_subdir / "stages" / "validation_result.json"
                score_str = ""
                if vr.exists():
                    try:
                        vdata = json.loads(vr.read_text())
                        score = vdata.get("weighted_score", "?")
                        verdict = vdata.get("verdict", "?")
                        score_str = f" ({score}/5.0 {verdict})"
                    except Exception:
                        pass
                lines.append(f"  {wp_id}: {phase}{score_str}")
            lines.append("")

        return "\n".join(lines)

    def reset_wp(self, wp_id: str) -> None:
        """重置单个 WP 的进度。"""
        if wp_id in self.progress:
            del self.progress[wp_id]
        self._save_progress()

    def reset_all(self) -> None:
        """重置所有进度。"""
        self.progress = {}
        self._save_progress()
