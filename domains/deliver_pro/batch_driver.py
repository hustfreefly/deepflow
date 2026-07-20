"""
BatchDriver — 批量驱动多个 WP 的 Deliver Pro 5 Phase 流水线。

按 dependency_graph.execution_layers 分层执行：
  Layer 0: 无依赖的 WP 并行
  Layer 1: 依赖 Layer 0 的 WP 并行
  ...

每个 WP 独立驱动，通过 blackboard 文件系统检查实际 phase。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BatchDriver:
    """批量驱动多个 WP 的 Deliver Pro 流水线。"""

    def __init__(self, project_name: str):
        from domains.deliver_pro import BLACKBOARD_ROOT

        self.project_name = project_name
        self.blackboard_root = BLACKBOARD_ROOT
        ship_pkg_path = self._find_ship_package()
        self.ship_package = json.loads(ship_pkg_path.read_text())
        self.layers = self._compute_layers()
        self.progress_path = self.blackboard_root / project_name / "batch_progress.json"
        self.progress = self._load_progress()

    # ------------------------------------------------------------------
    # 初始化辅助
    # ------------------------------------------------------------------

    def _find_ship_package(self) -> Path:
        """搜索 blackboard/{project}/ship_pro/stages/ship_package.json"""
        path = self.blackboard_root / self.project_name / "ship_pro" / "stages" / "ship_package.json"
        if not path.exists():
            raise FileNotFoundError(f"ship_package.json not found: {path}")
        return path

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
        """从 JSON 文件加载进度。"""
        if self.progress_path.exists():
            try:
                return json.loads(self.progress_path.read_text())
            except Exception as e:
                logger.warning(f"Failed to load progress: {e}")
        return {}

    def _save_progress(self) -> None:
        """保存进度到 JSON 文件。"""
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        self.progress_path.write_text(
            json.dumps(self.progress, ensure_ascii=False, indent=2)
        )

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

        e.g., CORE-001 → deliver_core_001
        """
        return f"deliver_{wp_id.lower().replace('-', '_')}"

    def _get_driver(self, wp_id: str):
        """创建 DeliverProDriver(wp_id, project_name)。"""
        from domains.deliver_pro.driver import DeliverProDriver

        project_name = self._get_wp_project_name(wp_id)
        return DeliverProDriver(wp_id, project_name)

    # ------------------------------------------------------------------
    # Phase 检测（从 blackboard 文件系统）
    # ------------------------------------------------------------------

    def _check_wp_phase(self, wp_id: str) -> str:
        """从 blackboard 文件系统检查 WP 实际 phase。

        Returns:
            "DONE" | "PACKAGING" | "VALIDATING" | "ASSEMBLING" |
            "GENERATING" | "PENDING"
        """
        wp_project = self._get_wp_project_name(wp_id)
        stages_dir = self.blackboard_root / wp_project / "deliver_pro" / "stages"

        if not stages_dir.exists():
            return "PENDING"

        # P1-8 fix: DONE requires delivery_manifest.json OR terminal state.
        # File existence alone ≠ verified completion.
        final_dir = stages_dir / "final_deliverable"
        manifest_file = stages_dir / "delivery_manifest.json"
        if final_dir.exists() and manifest_file.exists():
            final_files = [f for f in final_dir.rglob("*") if f.is_file()]
            if final_files:
                return "DONE"
        # Also DONE if state is terminal (DELIVERED/COMPLETED/FAILED)
        state_file = stages_dir.parent / "delivery_state.json"
        if state_file.exists():
            try:
                state_data = json.loads(state_file.read_text())
                if state_data.get("phase") in ("DELIVERED", "COMPLETED", "FAILED"):
                    return "DONE"
            except Exception:
                pass

        # PACKAGING: validation_result.json 存在
        if (stages_dir / "validation_result.json").exists():
            return "PACKAGING"

        # VALIDATING: integrated_draft/DELIVERABLE.md 存在
        # But only if state agrees (not stale artifacts from a previous run).
        if (stages_dir / "integrated_draft" / "DELIVERABLE.md").exists():
            # Cross-check with state file to avoid stale artifact false positive
            if state_file.exists():
                try:
                    _sf_data = json.loads(state_file.read_text())
                    _sf_phase = _sf_data.get("phase", "")
                    # If state is GENERATING or earlier, the draft is stale
                    if _sf_phase in ("INIT", "ANALYZING", "GENERATING"):
                        pass  # Fall through to ASSEMBLING/GENERATING check
                    else:
                        return "VALIDATING"
                except Exception:
                    return "VALIDATING"
            else:
                return "VALIDATING"

        # ASSEMBLING: 所有 worker MANIFEST 完成
        # (检查 execution_plan.json 中的 task_count vs MANIFEST 数量)
        plan_path = stages_dir / "execution_plan.json"
        if plan_path.exists():
            try:
                import glob
                plan_data = json.loads(plan_path.read_text())
                # BLK-01 fix: task_count is a @property, not serialized to JSON
                task_count = len(plan_data.get("task_graph", []))
                manifests = glob.glob(str(stages_dir / "worker_outputs" / "*/MANIFEST.json"))
                if task_count > 0 and len(manifests) >= task_count:
                    return "ASSEMBLING"
            except Exception:
                pass

        # GENERATING: execution_plan.json 有 task_graph
        if plan_path.exists():
            try:
                plan_data = json.loads(plan_path.read_text())
                # BLK-01 fix: use len(task_graph) instead of task_count property
                if plan_data.get("task_graph") or len(plan_data.get("task_graph", [])) > 0:
                    return "GENERATING"
            except Exception:
                pass

        return "PENDING"

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
        deliver_pro_dir = self.blackboard_root / project_name / "deliver_pro"
        wp_path = deliver_pro_dir / "data" / "wp.json"

        if wp_path.exists():
            return  # 已初始化

        # 从 ship_package 获取 WP 数据并适配
        wp_data = self._get_wp_data(wp_id)
        package_sa = self.ship_package.get("semantic_anchors", [])
        adapted = _adapt_ship_pro_wp(wp_data, package_semantic_anchors=package_sa)
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
                return {"wp_id": wp_id, "action": "analyze_check_failed", "spawn_params": None, "error": str(info)}
            try:
                # BLK-05 fix: Check if workers are already done before spawning new ones
                all_done, check_info = driver.step4_check_workers()
                if all_done:
                    # Workers already completed → trigger assembly
                    return {"wp_id": wp_id, "action": "assemble", "spawn_params": None, "error": None}
                params_list = driver.step3_workers()
                return {"wp_id": wp_id, "action": "spawn_workers", "spawn_params": params_list, "error": None}
            except Exception as e:
                return {"wp_id": wp_id, "action": "workers_failed", "spawn_params": None, "error": str(e)}

        if phase == "ASSEMBLING":
            try:
                result = driver.step5_integrate()
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
                return {"wp_id": wp_id, "action": "skip", "spawn_params": None, "error": "validate_pending"}
            try:
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

        for layer in self.layers:
            for wp_id in layer:
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
            "current_layer": current_layer,
            "all_done": all_done,
        }

    def tick(self) -> list[dict]:
        """AI Native 统一推进接口：一次调用完成 scan → reconcile → dedup → 返回 spawn list。

        主 Agent 只需：
        1. 调用 tick()
        2. 对返回的每个 spawn_params 调用 sessions_spawn
        3. yield 等待完成
        4. 再次调用 tick()

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

        results = []
        next_actions = self.get_next_actions()

        for action_item in next_actions.get("actions", []):
            wp_id = action_item["wp_id"]
            action = action_item["action"]

            # 1. MANIFEST 路径修正
            self._reconcile_manifests(wp_id)

            # 2. 去重：检查 progress 中是否已 spawn 同 action（含具体 task IDs）
            progress_entry = self.progress.get(wp_id, {})
            last_spawned = progress_entry.get("last_spawned_action")
            current_params = action_item.get("spawn_params")
            has_real_params = bool(current_params) and (
                not isinstance(current_params, list) or len(current_params) > 0
            )
            # P0-3 fix: dedup key 包含具体 task IDs，不同 wave 的 spawn_workers 不互相阻塞
            current_task_ids = ""
            if isinstance(current_params, list):
                current_task_ids = ",".join(sorted(
                    p.get("label", p.get("task_id", "")) for p in current_params
                    if isinstance(p, dict)
                ))
            dedup_key = f"{action}:{current_task_ids}" if current_task_ids else action
            if last_spawned == dedup_key and has_real_params:
                continue  # 同一批 worker 已在进行中，跳过
            if last_spawned == dedup_key and not has_real_params:
                progress_entry.pop("last_spawned_action", None)
                self.progress[wp_id] = progress_entry

            # 3. Assembly 自动执行（确定性代码，不需要 agent）
            if action == "assemble":
                try:
                    driver = self._get_driver(wp_id)
                    result = driver.step5_integrate()
                    # P1-6 fix: Check assembly status — don't discard ASSEMBLY_ERROR
                    if result.get("status") == "ASSEMBLY_ERROR":
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
                        results.append(new_action)
                except Exception as e:
                    # P1-7 fix: assembly exception → terminal_failed (not retryable)
                    logger.error(f"{wp_id}: assembly exception — {e}")
                    results.append({"wp_id": wp_id, "action": "terminal_failed", "spawn_params": None, "error": str(e)})
                continue

            # 4. 记录 spawn 状态（P0-3 fix: 用 dedup_key 而非 action，区分不同 wave）
            if has_real_params:
                progress_entry["last_spawned_action"] = dedup_key
                self.progress[wp_id] = progress_entry
                self._save_progress()

            results.append(action_item)

        return results

    def drive_once(self) -> dict:
        """Auto-loop 接口：一次调用返回当前所有可执行的 spawn 动作。

        Agent 层使用模式：
            while True:
                result = driver.drive_once()
                if result["all_done"]:
                    break
                for action in result["spawn_actions"]:
                    sessions_spawn(task=action["task"], label=action["label"], ...)
                sessions_yield()  # 等待所有 worker 完成

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

        Agent 层使用模式（极简）:
            while True:
                result = driver.drive_all()
                if result["all_done"]:
                    break  # Pipeline 完成！
                # spawn agents
                for action in result["spawn_actions"]:
                    sessions_spawn(task=action["task"], label=action["label"], ...)
                sessions_yield()  # 等待所有 worker 完成
                # loop back to drive_all()

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
                vr = self.blackboard_root / proj / "deliver_pro" / "stages" / "validation_result.json"
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

    def _reconcile_manifests(self, wp_id: str) -> None:
        """自动修正 MANIFEST 路径 + 同步 state 文件。

        三层修复：
        1. 移动旧路径 worker_outputs/ → stages/worker_outputs/（legacy fix）
        2. 扫描正确路径 stages/worker_outputs/，更新 completed_tasks
        3. 清理 stale running_tasks（running 但无 MANIFEST = 从未实际 spawn）
        """
        import shutil
        import glob

        wp_project = self._get_wp_project_name(wp_id)
        project_dir = self.blackboard_root / wp_project / "deliver_pro"
        wrong_dir = project_dir / "worker_outputs"
        correct_dir = project_dir / "stages" / "worker_outputs"

        # Step 1: Legacy path migration (only if old path exists)
        if wrong_dir.exists():
            for task_dir in wrong_dir.iterdir():
                if not task_dir.is_dir():
                    continue
                dst = correct_dir / task_dir.name
                if not (dst / "MANIFEST.json").exists():
                    correct_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(str(task_dir), str(dst), dirs_exist_ok=True)

        # Step 2+3: ALWAYS reconcile state from correct path
        state_path = project_dir / "delivery_state.json"
        if not state_path.exists():
            return

        state = json.loads(state_path.read_text())
        manifests = sorted(glob.glob(str(correct_dir / "*/MANIFEST.json")))

        # Build completed set from actual MANIFESTs on disk
        completed_from_disk = set()
        for m in manifests:
            try:
                d = json.loads(open(m).read())
                tid = d.get("task_id", "")
                if tid and d.get("status") in ("COMPLETE", "PASS"):
                    completed_from_disk.add(tid)
            except Exception:
                pass

        # Clean stale running_tasks: if task is in running but has no MANIFEST → stale
        old_running = set(state.get("running_tasks", []))
        # A task is truly running if it's in running AND has a MANIFEST that's not COMPLETE
        # OR has no MANIFEST yet (still in progress)
        manifest_task_ids = set()
        for m in manifests:
            try:
                d = json.loads(open(m).read())
                manifest_task_ids.add(d.get("task_id", ""))
            except Exception:
                pass

        # Stale = in running_tasks but has COMPLETE MANIFEST (should be in completed)
        stale_running = old_running & completed_from_disk
        clean_running = old_running - stale_running

        # B1 fix: Timeout stale running_tasks.
        # Tasks in running_tasks but WITHOUT a MANIFEST and running for too long
        # are dead workers (spawned but never produced output).
        # Mark them as failed so the pipeline doesn't hang forever.
        WORKER_TIMEOUT_SECONDS = 600  # 10 minutes
        timed_out = set()
        for task_id in clean_running:
            if task_id in manifest_task_ids:
                continue  # Has MANIFEST, will be handled by completed_from_disk
            # No MANIFEST → check if task has been running too long
            task_dir = correct_dir / task_id
            if task_dir.exists():
                # Directory exists but no MANIFEST → partial write or crashed
                mtime = task_dir.stat().st_mtime
                import time
                if time.time() - mtime > WORKER_TIMEOUT_SECONDS:
                    timed_out.add(task_id)
            else:
                # No directory at all → worker never started or was cleaned
                # Check state file updated_at for how long it's been running
                state_updated = state.get("updated_at", "")
                if state_updated:
                    try:
                        from datetime import datetime
                        updated_dt = datetime.fromisoformat(state_updated)
                        import time
                        if time.time() - updated_dt.timestamp() > WORKER_TIMEOUT_SECONDS * 2:
                            timed_out.add(task_id)
                    except (ValueError, TypeError):
                        pass

        if timed_out:
            failed_tasks = set(state.get("failed_tasks", []))
            failed_tasks.update(timed_out)
            clean_running -= timed_out
            state["failed_tasks"] = sorted(failed_tasks)
            logger.warning(
                f"{wp_id}: B1 timeout — {len(timed_out)} workers timed out: "
                f"{sorted(timed_out)}"
            )

        # Only update if something changed
        old_completed = set(state.get("completed_tasks", []))
        old_failed = set(state.get("failed_tasks", []))
        if (completed_from_disk != old_completed or clean_running != old_running
                or timed_out):
            state["completed_tasks"] = sorted(completed_from_disk)
            state["running_tasks"] = sorted(clean_running)
            if state.get("phase") not in ("COMPLETED", "DELIVERED", "PACKAGING", "VALIDATING", "ASSEMBLING"):
                state["phase"] = "GENERATING"
            state_path.write_text(json.dumps(state, indent=2))
            if stale_running:
                logger.info(f"{wp_id}: cleaned stale running_tasks={stale_running}, "
                           f"completed={sorted(completed_from_disk)}")

    def reset_wp(self, wp_id: str) -> None:
        """重置单个 WP 的进度。"""
        if wp_id in self.progress:
            del self.progress[wp_id]
        self._save_progress()

    def reset_all(self) -> None:
        """重置所有进度。"""
        self.progress = {}
        self._save_progress()
