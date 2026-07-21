"""
Deliver Pro Driver — Python 驱动 5 Phase 流水线

替代 Agent Orchestrator 的确定性驱动方案。
Main Agent 逐步调 exec 驱动流水线，每步都是简单的 Python 调用。

架构:
  Main Agent
    → exec: driver = DeliverRunner(wp_id, project_name)
    → exec: params = driver.step1_analyze()  → sessions_spawn + yield
    → exec: driver.step2_check_analyze()     → 验证
    → exec: params = driver.step3_workers()  → sessions_spawn (多个) + yield
    → exec: driver.step4_check_workers()     → 验证 + 循环
    → exec: driver.step5_integrate()         → Python 直接跑
    → exec: params = driver.step6_validate() → sessions_spawn + yield
    → exec: params = driver.step7_package()  → sessions_spawn + yield
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from domains.deliver_pro.contracts import WorkPackage
from domains.deliver_pro.wp_runner import DeliverWPRunner

logger = logging.getLogger(__name__)


class DeliverRunner:
    """Python 驱动的 Deliver Pro 5 Phase 流水线。

    用法（Main Agent 逐步调 exec）:
        # Step 0: 初始化
        driver = DeliverRunner("CORE-001", "skill-health-cli_core_001")

        # Step 1: Analyze
        spawn_params = driver.step1_analyze()
        # → sessions_spawn(**spawn_params) + sessions_yield()

        # Step 2: 检查 Analyze 完成
        ok, info = driver.step2_check_analyze()
        # → if ok, 继续 Step 3

        # Step 3: Workers
        spawn_params_list = driver.step3_workers()
        # → 对每个 params 调用 sessions_spawn + sessions_yield

        # Step 4: 检查 Workers
        all_done, info = driver.step4_check_workers()
        # → if not all_done, 可能有 next_wave → 回到 Step 3
        # → if all_done, 继续 Step 5

        # Step 5: Assembly（Python 直接跑）
        result = driver.step5_integrate()

        # Step 6: Validate
        spawn_params = driver.step6_validate(round_num=1)
        # → sessions_spawn + yield

        # Step 7: Package
        spawn_params = driver.step7_package(verdict_str="PASS")
        # → sessions_spawn + yield
    """

    def __init__(self, wp_id: str, project_name: str):
        from domains.deliver_pro import BLACKBOARD_ROOT

        self.project_name = project_name
        self.blackboard_path = BLACKBOARD_ROOT / project_name
        wp_subdir = wp_id.lower().replace('-', '_')
        self.deliver_pro_dir = self.blackboard_path / "deliver_pro" / wp_subdir
        self.stages_dir = self.deliver_pro_dir / "stages"
        self.worker_outputs_dir = self.stages_dir / "worker_outputs"

        # 加载 WP
        wp_path = self.deliver_pro_dir / "data" / "wp.json"
        if not wp_path.exists():
            raise FileNotFoundError(f"WP not found: {wp_path}")

        self.wp = WorkPackage.model_validate(json.loads(wp_path.read_text()))
        self.orch = DeliverWPRunner(
            self.wp, self.blackboard_path, project_name
        )
        self.wp_id = wp_id
        self._validate_round = 0

        # P1-1: Stuck detection
        self._last_completed_count = 0
        self._stuck_checks = 0

        logger.info(f"Driver init: wp={wp_id}, project={project_name}")

    def step1_analyze(self) -> dict[str, Any]:
        """Phase 1: 准备 Analyze Agent spawn 参数。"""
        params = self.orch.prepare_analyze_spawn()
        logger.info(f"Step 1: Analyze spawn ready")
        return params

    def step2_check_analyze(self) -> tuple[bool, dict]:
        """Phase 1 验证: 检查 execution_plan.json 是否存在。"""
        plan_path = self.stages_dir / "execution_plan.json"
        if not plan_path.exists():
            return False, {"error": "execution_plan.json not found"}

        try:
            plan_data = json.loads(plan_path.read_text())
            # Verify analyze output quality
            valid, msg = self.orch.verify_analyze_output(plan_data)
            if not valid:
                return False, {"error": f"verify_analyze_output failed: {msg}"}
            # NEW-01 fix: task_count is @property, not JSON field
            task_count = len(plan_data.get("task_graph", []))
            return True, {"task_count": task_count, "plan_path": str(plan_path)}
        except Exception as e:
            return False, {"error": str(e)}

    def step3_workers(self) -> list[dict[str, Any]]:
        """Phase 2: 准备当前可执行的 Workers spawn 参数。"""
        from domains.deliver_pro.contracts import PipelinePhase

        plan = self.orch.load_execution_plan()

        # Ensure state is GENERATING before spawning workers
        if self.orch.state.phase == PipelinePhase.ANALYZING:
            self.orch.state.transition_to(PipelinePhase.GENERATING)
            self.orch._save_state()

        params_list = self.orch.prepare_workers_spawn(plan)
        logger.info(f"Step 3: {len(params_list)} workers ready to spawn")
        return params_list

    def step4_check_workers(self) -> tuple[bool, dict]:
        """Phase 2 验证: 检查 Workers 完成情况。

        Returns:
            (all_done, info)
            all_done=True → 可以进入 Phase 3
            all_done=False → 需要继续等待或 spawn 更多 workers
        """
        import glob

        manifests = glob.glob(str(self.worker_outputs_dir / "*/MANIFEST.json"))
        plan = self.orch.load_execution_plan()
        total = plan.task_count
        completed = len(manifests)

        # B3 fix: Verify BEFORE marking completed.
        # Only verified workers count as completed; invalid → failed.
        newly_detected = []
        for manifest_path in manifests:
            try:
                manifest = json.loads(Path(manifest_path).read_text())
                task_id = manifest.get("task_id", "")
                if task_id and task_id not in self.orch.state.completed_tasks \
                        and task_id not in self.orch.state.failed_tasks:
                    newly_detected.append(task_id)
            except Exception:
                pass

        # Verify each newly detected worker output
        verified_count = 0
        for task_id in newly_detected:
            output_dir = self.worker_outputs_dir / task_id
            valid, msg, _ = self.orch.verify_worker_output(task_id, output_dir)
            if valid:
                verified_count += 1
            else:
                logger.warning(f"Worker {task_id} verify failed: {msg}")
                self.orch.mark_worker_failed(task_id, msg)

        # Recount completed from verified state (not MANIFEST count)
        completed = len(self.orch.state.completed_tasks)

        self.orch._save_state()

        info = {
            "completed": completed,
            "total": total,
            "manifests": [str(m) for m in manifests],
        }

        if completed >= total:
            logger.info(f"Step 4: All {completed}/{total} workers done")
            # Reset stuck detection on completion
            self._last_completed_count = 0
            self._stuck_checks = 0
            return True, info
        else:
            # P1-1: Stuck detection
            if completed == self._last_completed_count:
                self._stuck_checks += 1
                if self._stuck_checks >= 3:
                    logger.warning(
                        f"⚠️ P1-1 STUCK: {self.wp_id} no progress for "
                        f"{self._stuck_checks} checks. "
                        f"Completed: {completed}/{total}"
                    )
                    info["stuck"] = True
                    info["stuck_checks"] = self._stuck_checks
            else:
                self._last_completed_count = completed
                self._stuck_checks = 0

            # BLOCKER-A fix: Use read-only peek (no side effects)
            next_wave = self.orch.peek_next_wave_count(plan)
            info["next_wave"] = next_wave
            # BLOCKER-B fix: Account for failed tasks in terminal check
            failed = len(self.orch.state.failed_tasks)
            processed = completed + failed
            if processed >= total and next_wave == 0:
                logger.info(
                    f"Step 4: Terminal — {completed}/{total} done, "
                    f"{failed} failed, no more runnable work"
                )
                info["failed"] = failed
                info["terminal"] = True
                return True, info
            logger.info(
                f"Step 4: {completed}/{total} done, "
                f"{failed} failed, next_wave={next_wave}"
            )
            return False, info

    def step5_integrate(self) -> dict:
        """Phase 3: Code-First Assembly（Python 直接执行，不需要 Agent）。"""
        plan = self.orch.load_execution_plan()
        result = self.orch.run_integrate(plan)

        info = {
            "workers_integrated": result.workers_integrated,
            "workers_failed": result.workers_failed,
            "retention_ratio": result.retention_ratio,
            "status": result.status,
        }

        # Verify integrate output (non-blocking)
        if result.status != "ASSEMBLY_ERROR":
            valid, msg = self.orch.verify_integrate_output(self.orch.integrated_draft_dir)
            if not valid:
                info["verify_warning"] = msg

        logger.info(f"Step 5: Assembly done — {info}")
        return info

    def step6_validate(self, round_num: int | None = None) -> dict[str, Any]:
        """Phase 4: 准备 Validate Agent spawn 参数。"""
        if round_num is None:
            self._validate_round += 1
            round_num = self._validate_round

        plan = self.orch.load_execution_plan()
        params = self.orch.prepare_validate_spawn(plan, round_num=round_num)
        logger.info(f"Step 6: Validate round {round_num} spawn ready")
        return params

    def step6_check_validate(self) -> tuple[str, dict]:
        """Phase 4 验证: 读取 verdict。

        Returns:
            (verdict, details)
            verdict: "PASS" | "CONDITIONAL" | "FAIL" | "NOT_FOUND"
        """
        # BLK-03 fix: Validate Agent writes validation_result.json, not validate_verdict.json
        verdict_path = self.stages_dir / "validation_result.json"
        if not verdict_path.exists():
            return "NOT_FOUND", {}

        try:
            data = json.loads(verdict_path.read_text())
            # Verify validate output (blocking — schema + cross-check)
            valid, msg, verdict_obj = self.orch.verify_validate_output(data)
            if not valid:
                return "FAIL", {"error": f"verify_validate_output failed: {msg}"}
            # Use Schema-validated verdict (enum: PASS/CONDITIONAL/FAIL)
            verdict_str = verdict_obj.verdict if verdict_obj else data.get("verdict", "FAIL")
            # BLK-03 fix: field is weighted_score, not overall_score
            score = data.get("weighted_score", 0)
            return verdict_str, {"score": score, "data": data}
        except Exception as e:
            return "ERROR", {"error": str(e)}

    def step7_package(self, verdict_str: str | None = None) -> dict[str, Any]:
        """Phase 5: 准备 Package Agent spawn 参数。
        
        P1-3 fix: Auto-read verdict from validation_result.json.
        verdict_str parameter is only used as fallback when file doesn't exist
        (e.g., assembly error path).
        """
        from domains.deliver_pro.contracts.validation_verdict import ValidationVerdict, ScoreDimension

        plan = self.orch.load_execution_plan()

        # Read validation_result.json using Pydantic model_validate
        validation_path = self.stages_dir / "validation_result.json"
        verdict_obj = None
        if validation_path.exists():
            try:
                vdata = json.loads(validation_path.read_text())
                verdict_obj = ValidationVerdict.model_validate(vdata)
            except Exception as e:
                logger.warning(f"Failed to parse validation_result.json: {e}")

        # B2 fix: Fallback — never default to PASS when file is missing/corrupt.
        # Only use verdict_str if explicitly provided (e.g., ASSEMBLY_ERROR path).
        # Otherwise, default to CONDITIONAL (safe middle ground: package runs but flags it).
        if verdict_obj is None:
            fallback_verdict = verdict_str or "CONDITIONAL"
            fallback_score = 3.0 if fallback_verdict == "CONDITIONAL" else (
                1.5 if fallback_verdict == "FAIL" else 4.4
            )
            verdict_obj = ValidationVerdict.model_validate({
                "weighted_score": fallback_score,
                "scores": {},
                "verdict": fallback_verdict,
                "round": 1,
            })
            logger.warning(
                f"B2: validation_result.json unavailable, using fallback "
                f"verdict={fallback_verdict} (explicit={verdict_str is not None})"
            )

        params = self.orch.prepare_package_spawn(plan, verdict=verdict_obj)
        actual_verdict = verdict_obj.verdict if hasattr(verdict_obj, 'verdict') else 'UNKNOWN'
        logger.info(f"Step 7: Package spawn ready (verdict={actual_verdict})")
        return params

    def step7_check_package(self) -> tuple[bool, dict]:
        """Phase 5 验证: 检查 final_deliverable 目录 + delivery_manifest。"""
        final_dir = self.stages_dir / "final_deliverable"
        if not final_dir.exists():
            return False, {"error": "final_deliverable dir not found"}

        files = [f for f in final_dir.rglob("*") if f.is_file()]
        if not files:
            return False, {"error": "final_deliverable is empty"}

        # Verify package output via delivery_manifest.json (blocking)
        manifest_path = self.stages_dir / "delivery_manifest.json"
        if manifest_path.exists():
            valid, msg, _ = self.orch.verify_package_output(manifest_path)
            if not valid:
                return False, {"error": f"verify_package_output failed: {msg}"}
            # Mark pipeline COMPLETED (guard: skip if already terminal)
            from domains.deliver_pro.contracts import PipelinePhase
            if not self.orch.state.is_terminal:
                self.orch.state.transition_to(PipelinePhase.COMPLETED)
                self.orch._save_state()

        return True, {"file_count": len(files), "files": [str(f) for f in files]}

    def step6_5_fix_integrate(self, verdict_data: dict) -> dict[str, Any]:
        """Phase 4.5: 准备 FIX 轮次的 Integrate Agent spawn 参数。

        Args:
            verdict_data: validation_result.json 的内容（dict 格式）

        Returns:
            spawn_params dict，供 Orchestrator 调 sessions_spawn
        """
        plan = self.orch.load_execution_plan()
        from domains.deliver_pro.contracts.validation_verdict import ValidationVerdict
        verdict_obj = ValidationVerdict.model_validate(verdict_data)
        return self.orch.prepare_fix_integrate_spawn(plan, verdict_obj)

    def get_status(self) -> dict:
        """获取当前流水线状态。"""
        import glob

        state_path = self.deliver_pro_dir / "delivery_state.json"
        phase = "UNKNOWN"
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text())
                phase = state.get("phase", "UNKNOWN")
            except Exception:
                pass

        manifests = glob.glob(str(self.worker_outputs_dir / "*/MANIFEST.json"))
        integrated = (self.stages_dir / "integrated_draft" / "DELIVERABLE.md").exists()
        final_files = list((self.stages_dir / "final_deliverable").rglob("*")) if (self.stages_dir / "final_deliverable").exists() else []

        return {
            "wp_id": self.wp_id,
            "project": self.project_name,
            "phase": phase,
            "workers_completed": len(manifests),
            "assembly_done": integrated,
            "package_done": len([f for f in final_files if f.is_file()]) > 0,
        }
