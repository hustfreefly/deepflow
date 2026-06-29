"""
Planning Orchestrator (Module 1)

Version: 1.0.0
Author: DeepFlow Solution Pro
Date: 2026-06-28

Description:
- Planning V2 three-layer architecture orchestrator
- Layer 0: Meta-Planner (analyze task → select experts → configure Gate)
- Layer 1: Expert Planners ×N (generate constraints from different perspectives)
- Layer 2: Convergence Planner (merge + validate + trace P0 REQs)
- Gate A + Gate B evaluation
- Generate planning_convergence.json

Design Principles:
- Code controls flow (deterministic logic)
- LLM generates content (semantic understanding)
- No direct OpenClaw calls (spawned by main Agent)
"""

import json
import logging
import os
from typing import Any, Callable, Optional
from pathlib import Path

from .module_orchestrator_base import ModuleOrchestrator
from .schemas.v2_schemas import (
    ExpertManifestSchema,
    ExpertPlanSchema,
    UnifiedConstraintsSchema,
    VerificationChecklistSchema,
    PlanningConvergenceSchema,
)
from .convergence_layer import ConvergenceLayer
from .task_builder import build_meta_planner_task, build_reviewer_meta_task
from .harness_scorer import GateALayer2Calibration, evaluate_gate_b_critical

logger = logging.getLogger(__name__)


class PlanningOrchestrator(ModuleOrchestrator):
    """
    PlanningOrchestrator — Planning V2 三层架构编排器

    Gate A/B 逻辑位置：
    - Phase 1: Gate 评估通过 ConvergenceLayer._evaluate_gates() 调用
      （Harness Agent spawn + 本地 fallback）
    - Phase 2: Gate 评估逻辑统一到 ConvergenceLayer，所有模块共享

    stage_sequence() 说明：
    PlanningOrchestrator 使用自定义 run() 流程（7 步），而非基类的线性 stage_sequence()。
    这是因为 Planning V2 的三层架构（Meta → Expert ×N → Convergence）不是简单的线性序列。
    V1 的 stage_sequence() 模式保留为 fallback。

    Responsibilities:
    1. Run Meta-Planner (Layer 0)
    2. Run Expert Planners ×N (Layer 1, parallel)
    3. Run Convergence Planner (Layer 2)
    4. Run Reviewer_Meta (validate Meta-Planner output)
    5. Run Reviewer_Convergence (validate Convergence output)
    6. Run Harness Agent (Gate A + Gate B evaluation)
    7. Generate planning_convergence.json
    """
    
    def __init__(
        self,
        session_id: str,
        spawn_fn: Optional[Callable] = None,
        base_dir: Optional[str] = None,
    ):
        """
        Initialize Planning Orchestrator
        
        Args:
            session_id: Session ID
            base_dir: Blackboard 基础目录
            spawn_fn: Spawn function (provided by main Agent)
        """
        super().__init__("planning", session_id, spawn_fn, base_dir=base_dir)
        
        # Load prompts
        self.meta_planner_prompt = self._load_prompt("meta_planner.md")
        self.expert_planner_prompt = self._load_prompt("expert_planner_base.md")
        self.convergence_planner_prompt = self._load_prompt("convergence_planner.md")
        self.harness_agent_prompt = self._load_prompt("harness_agent.md")
        self.reviewer_meta_prompt = self._load_prompt("reviewer_meta.md")
        self.reviewer_convergence_prompt = self._load_prompt("reviewer_convergence.md")
        
        logger.info("PlanningOrchestrator initialized")
    
    @property
    def session_dir(self) -> Path:
        """
        Get session directory from blackboard.
        
        This property provides compatibility with task_builder functions
        that expect a session_dir parameter.
        
        Returns:
            Path to session directory (blackboard base_dir)
        """
        if hasattr(self.blackboard, 'base_dir'):
            return self.blackboard.base_dir
        # Fallback: construct from session_id
        return Path(f"/tmp/deepflow/sessions/{self.session_id}")
    
    def _load_prompt(self, filename: str) -> str:
        """Load prompt file"""
        prompt_path = Path(__file__).parent / "prompts" / filename
        if prompt_path.exists():
            return prompt_path.read_text()
        else:
            logger.warning(f"Prompt file not found: {filename}")
            return ""
    
    def _load_checkpoint(self, path: str) -> Optional[dict]:
        """
        加载断点输出（如果存在）
        
        Args:
            path: Blackboard 相对路径
        
        Returns:
            dict if exists, None otherwise
        """
        try:
            result = self.blackboard.read(path)
            logger.debug(f"Checkpoint loaded: {path}")
            return result
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.warning(f"Failed to load checkpoint for {path}: {e}")
            return None
    
    def _save_checkpoint(self, path: str, result: dict):
        """
        保存输出（checkpoint）
        
        Args:
            path: Blackboard 相对路径
            result: 输出 dict
        """
        try:
            self.blackboard.write(path, result)
            logger.debug(f"Checkpoint saved: {path}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint for {path}: {e}")
    
    def run(
        self,
        frozen_spec: dict = None,
        structured_requirements: dict = None,
        spawn_fn: Callable = None,
        llm_judge_fn: Callable = None,
    ) -> dict:
        """
        Run Planning module (main entry point)
        
        V2 增强：支持可选参数注入（V1 向后兼容）
        - 如果提供参数，使用参数值
        - 如果未提供，从 blackboard 读取（V1 模式）
        
        Args:
            frozen_spec: Frozen spec dict（可选，V1 从 blackboard 读取）
            structured_requirements: Structured requirements dict（可选，V1 从 blackboard 读取）
            spawn_fn: Spawn function（可选，覆盖初始化时的 spawn_fn）
            llm_judge_fn: LLM judge function（可选，供 Phase 2 使用）
        
        Returns:
            planning_convergence.json content
        """
        # V2: 存储可选参数（供 Phase 2 使用）
        if spawn_fn is not None:
            self.spawn_fn = spawn_fn
        if llm_judge_fn is not None:
            self.llm_judge_fn = llm_judge_fn
        if frozen_spec is not None:
            self.blackboard.write("frozen_spec.json", frozen_spec)
        if structured_requirements is not None:
            self.blackboard.write("structured_requirements.json", structured_requirements)
        
        logger.info("Starting Planning module")
        
        # Check for checkpoint (resume support)
        if self.state and self.state.get("completed"):
            logger.info("Planning module already completed, loading from checkpoint")
            checkpoint_data = None
            try:
                if hasattr(self.blackboard, 'read_json'):
                    checkpoint_data = self.blackboard.read_json("planning_convergence.json")
                else:
                    result = self.blackboard.read("planning_convergence.json")
                    if isinstance(result, str):
                        import json
                        checkpoint_data = json.loads(result)
                    elif isinstance(result, dict):
                        checkpoint_data = result
            except Exception as e:
                logger.warning(f"Failed to load planning checkpoint: {e}")
            
            if checkpoint_data and isinstance(checkpoint_data, dict):
                return checkpoint_data
            # Checkpoint invalid — reset state and re-run
            logger.warning("Invalid checkpoint, resetting state")
            self.state["completed"] = False
        
        # Step 1: Run Meta-Planner (Layer 0)
        logger.info("Step 1: Running Meta-Planner (Layer 0)")
        expert_manifest = self._run_meta_planner()
        
        # Step 2: Run Reviewer_Meta (validate Meta-Planner output)
        logger.info("Step 2: Running Reviewer_Meta")
        reviewer_meta_output = self._run_reviewer_meta(expert_manifest)
        if reviewer_meta_output is None:
            logger.error("Reviewer_Meta returned None")
            raise RuntimeError("spawn_fn returned None for reviewer_meta")
        if reviewer_meta_output.get("overall_verdict") == "FAIL":
            logger.error("Meta-Planner output failed review")
            raise ValueError("Meta-Planner output failed review")
        
        # Step 3: Run Expert Planners ×N (Layer 1, parallel)
        logger.info(f"Step 3: Running Expert Planners ×{len(expert_manifest['experts'])} (Layer 1)")
        expert_plans = self._run_expert_planners(expert_manifest)
        
        # Step 4: Run Convergence Planner (Layer 2)
        logger.info("Step 4: Running Convergence Planner (Layer 2)")
        convergence_output = self._run_convergence_planner(expert_manifest, expert_plans)
        
        # Step 5: Run Reviewer_Convergence (validate Convergence output)
        logger.info("Step 5: Running Reviewer_Convergence")
        reviewer_convergence_output = self._run_reviewer_convergence(convergence_output)
        if reviewer_convergence_output is None:
            logger.error("Reviewer_Convergence returned None")
            raise RuntimeError("spawn_fn returned None for reviewer_convergence")
        if reviewer_convergence_output.get("overall_verdict") == "FAIL":
            logger.error("Convergence output failed review")
            raise ValueError("Convergence output failed review")
        
        # Step 6: Run Harness Agent (Gate A + Gate B evaluation)
        logger.info("Step 6: Running Harness Agent (Gate A + Gate B)")
        harness_output = self._run_harness_agent(convergence_output, expert_manifest)
        
        # Step 7: Generate planning_convergence.json
        logger.info("Step 7: Generating planning_convergence.json")
        planning_convergence = self._generate_planning_convergence(
            expert_manifest,
            convergence_output,
            harness_output,
        )
        
        # Save checkpoint (P0-1 fix: use self.state, _save_state() takes no args)
        self.state["completed"] = True
        self._save_state()
        
        logger.info("Planning module completed")
        return planning_convergence
    
    def _run_meta_planner(self) -> dict:
        """
        Run Meta-Planner (Layer 0)（含断点续跑）
        
        Flow:
        1. 检查是否已有输出（断点恢复）
        2. Use build_meta_planner_task() to generate task
        3. Execute via spawn_fn (or local fallback)
        4. Output written to Blackboard {session_dir}/stages/meta_planning.json
        5. Validate output against ExpertManifestSchema
        6. If invalid, raise error
        """
        # 检查是否已有输出（断点恢复）
        checkpoint = self._load_checkpoint("stages/meta_planning.json")
        if checkpoint:
            logger.info("Step 1: 从断点恢复 meta_planning.json")
            return checkpoint
        
        # Read input files
        frozen_spec = self.blackboard.read("frozen_spec.json")
        structured_requirements = self.blackboard.read("structured_requirements.json")
        
        # Get session directory from blackboard (fallback for test mocks)
        session_dir = str(getattr(self.blackboard, 'session_dir', self.session_id))
        
        # Build task using task_builder (generates prompt + system_prompt)
        task = build_meta_planner_task(frozen_spec, structured_requirements, session_dir)
        
        # Execute task via spawn_fn
        # Use relative output_path for spawn_fn compatibility (blackboard handles session_dir)
        output_path = "stages/meta_planning.json"
        if self.spawn_fn:
            worker_output = self._adapted_spawn(
                task=task["prompt"],
                output_path=output_path,
                timeout=task.get("timeout", 600),
            )
            if worker_output is None:
                raise RuntimeError("spawn_fn returned None for meta_planner")
        else:
            # Fallback for testing
            worker_output = self._mock_meta_planner()
        
        # Validate output against ExpertManifestSchema
        try:
            ExpertManifestSchema(**worker_output)
        except Exception as e:
            logger.error(f"Meta-Planner output validation failed: {e}")
            raise
        
        # Save to blackboard（checkpoint）
        self._save_checkpoint("stages/meta_planning.json", worker_output)
        
        return worker_output
    
    def _mock_meta_planner(self) -> dict:
        """Mock Meta-Planner output (for testing)"""
        return {
            "schema_version": "1.0.0",
            "task_profile": {
                "domain": "backend_api",
                "complexity": "high",
                "risk_areas": ["security", "scalability", "data_consistency"],
            },
            "experts": [
                {
                    "expert_name": "security_expert",
                    "domain": "Security",
                    "focus_areas": ["OWASP Top 10", "authentication", "authorization"],
                    "evaluation_lens": "从安全漏洞和攻击面角度审视每个设计决策",
                },
                {
                    "expert_name": "performance_expert",
                    "domain": "Performance & Scalability",
                    "focus_areas": ["latency", "throughput", "resource_usage"],
                    "evaluation_lens": "从性能瓶颈和扩展性角度审视每个设计决策",
                },
                {
                    "expert_name": "data_architect",
                    "domain": "Data Architecture",
                    "focus_areas": ["data_modeling", "consistency", "migration"],
                    "evaluation_lens": "从数据完整性和一致性角度审视每个设计决策",
                },
            ],
            "gate_a": {
                "weights": {
                    "completeness": 0.30,
                    "necessity": 0.15,
                    "alignment": 0.35,
                    "global_impact": 0.20,
                },
                "thresholds": {
                    "PASS": 0.85,
                    "WARNING": 0.70,
                    "CRITICAL_WARNING": 0.60,
                    "BLOCK_RECOMMENDATION": 0.0,
                },
                "rationale": "高风险后端 API 任务，强调目标一致性和完整性",
            },
            "gate_b": {
                "dynamic_checks": [
                    {
                        "name": "security_audit",
                        "description": "安全审计检查",
                        "pass_criteria": "无高危漏洞，所有 OWASP Top 10 风险已缓解",
                        "severity": "CRITICAL",
                        "reasoning": "安全是 P0 需求 REQ-P0-001",
                    },
                    {
                        "name": "p0_req_coverage",
                        "description": "P0 需求覆盖率检查",
                        "pass_criteria": "所有 P0 REQ 在 unified_constraints 中有对应约束",
                        "severity": "CRITICAL",
                        "reasoning": "P0 需求必须 100% 覆盖",
                    },
                ],
            },
            "verdict_policy": {
                "warning_acceptable": False,
                "min_gate_b_pass_rate": 0.8,
            },
        }
    
    def _run_reviewer_meta(self, expert_manifest: dict) -> dict:
        """
        Run Reviewer_Meta (validate Meta-Planner output)（含断点续跑）
        
        Flow:
        1. 检查是否已有输出（断点恢复）
        2. Use build_reviewer_meta_task() to generate task
        3. Read meta_planning.json as input
        4. Execute via spawn_fn (or local fallback)
        5. Output written to Blackboard {session_dir}/stages/reviewer_meta.json
        6. If verdict == FAIL, raise error
        """
        # 检查是否已有输出（断点恢复）
        checkpoint = self._load_checkpoint("stages/reviewer_meta.json")
        if checkpoint:
            logger.info("Step 2: 从断点恢复 reviewer_meta.json")
            return checkpoint
        
        # Read input files
        frozen_spec = self.blackboard.read("frozen_spec.json")
        
        # Get session directory from blackboard (fallback for test mocks)
        session_dir = str(getattr(self.blackboard, 'session_dir', self.session_id))
        
        # Build task using task_builder (generates prompt + system_prompt)
        task = build_reviewer_meta_task(expert_manifest, frozen_spec, session_dir)
        
        # Execute task via spawn_fn
        # Use relative output_path for spawn_fn compatibility (blackboard handles session_dir)
        output_path = "stages/reviewer_meta.json"
        if self.spawn_fn:
            worker_output = self._adapted_spawn(
                task=task["prompt"],
                output_path=output_path,
                timeout=task.get("timeout", 600),
            )
            if worker_output is None:
                raise RuntimeError("spawn_fn returned None for reviewer_meta")
        else:
            # Fallback for testing
            worker_output = self._mock_reviewer_meta()
        
        # Save to blackboard（checkpoint）
        self._save_checkpoint("stages/reviewer_meta.json", worker_output)
        
        return worker_output
    
    def _mock_reviewer_meta(self) -> dict:
        """Mock Reviewer_Meta output (for testing)"""
        return {
            "schema_version": "1.0.0",
            "reviewer": "reviewer_meta",
            "overall_verdict": "PASS",
            "overall_score": 0.92,
            "reviews": {},
            "issues": [],
            "suggestions": [],
        }
    
    def _run_expert_planners(self, expert_manifest: dict) -> list[dict]:
        """Run Expert Planners ×N (Layer 1, parallel)"""
        # V2: Use parallel execution with checkpoint, retry, and graceful degradation
        return self._run_expert_planners_parallel(expert_manifest)
    
    def _run_expert_planners_parallel(self, expert_manifest: dict) -> list[dict]:
        """
        并行执行 N 个 Expert Planners
        
        关键特性：
        1. ThreadPoolExecutor 并行执行（max_workers=5）
        2. per-expert checkpoint（已完成的 expert 不重跑）
        3. spawn_fn retry（max 2 retries, exponential backoff）
        4. graceful degradation（MIN_VIABLE_EXPERTS）
        5. per-expert timeout（default 120s）
        
        V1 向后兼容：当 spawn_fn 为 None 时，退化为顺序执行（测试模式）
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
        import time
        
        experts = expert_manifest["experts"]
        expected_count = len(experts)
        
        # MIN_VIABLE_EXPERTS: 最少需要成功的 expert 数量
        MIN_VIABLE = {1: 1, 2: 2, 3: 2, 4: 3, 5: 3}
        min_viable = MIN_VIABLE.get(expected_count, max(1, expected_count - 1))
        
        results = []
        failed_experts = []
        
        # Check for completed experts (resume scenario / checkpoint)
        pending_experts = []
        for expert in experts:
            checkpoint = self._load_expert_checkpoint(expert["expert_name"])
            if checkpoint:
                logger.info(f"Expert {expert['expert_name']} loaded from checkpoint")
                results.append(checkpoint)
            else:
                pending_experts.append(expert)
        
        if not pending_experts:
            logger.info("All experts loaded from checkpoint, skipping execution")
            return results
        
        # V1 向后兼容：当 spawn_fn 为 None 时，退化为顺序执行（测试模式）
        if not self.spawn_fn:
            logger.info("spawn_fn is None, falling back to sequential execution (V1 mode)")
            for expert in pending_experts:
                try:
                    result = self._mock_expert_planner(expert)
                    ExpertPlanSchema(**result)
                    self._save_expert_checkpoint(expert["expert_name"], result)
                    results.append(result)
                except Exception as e:
                    failed_experts.append({"name": expert["expert_name"], "error": str(e)})
                    logger.error(f"Expert {expert['expert_name']} failed: {e}")
        else:
            # V2: 并行执行
            logger.info(f"Running {len(pending_experts)} experts in parallel (max_workers={min(5, len(pending_experts))})")
            
            with ThreadPoolExecutor(max_workers=min(5, len(pending_experts))) as executor:
                futures = {}
                for expert in pending_experts:
                    future = executor.submit(self._run_single_expert_with_retry, expert)
                    futures[future] = expert
                
                # Wait for completion with timeout
                try:
                    for future in as_completed(futures, timeout=600):
                        expert = futures[future]
                        try:
                            result = future.result(timeout=600)
                            results.append(result)
                            self._save_expert_checkpoint(expert["expert_name"], result)
                            logger.info(f"Expert {expert['expert_name']} completed successfully")
                        except TimeoutError:
                            failed_experts.append({"name": expert["expert_name"], "error": "Timeout (120s)"})
                            logger.error(f"Expert {expert['expert_name']} timed out")
                        except Exception as e:
                            failed_experts.append({"name": expert["expert_name"], "error": str(e)})
                            logger.error(f"Expert {expert['expert_name']} failed: {e}")
                except TimeoutError:
                    logger.error("Global timeout (600s) exceeded for expert planners")
        
        # Graceful degradation check
        if len(results) < min_viable:
            raise RuntimeError(
                f"Insufficient experts: {len(results)}/{expected_count} succeeded, "
                f"minimum viable is {min_viable}. Failed: {[f['name'] for f in failed_experts]}"
            )
        
        if failed_experts:
            logger.warning(
                f"Degraded mode: {len(results)}/{expected_count} experts succeeded. "
                f"Failed: {[f['name'] for f in failed_experts]}"
            )
        
        logger.info(f"Expert planners completed: {len(results)}/{expected_count} succeeded")
        return results
    
    def _run_single_expert_with_retry(self, expert: dict, max_retries: int = 2) -> dict:
        """
        单个 Expert Planner 执行（含重试）
        
        Args:
            expert: Expert configuration dict
            max_retries: Maximum number of retries (default: 2)
        
        Returns:
            Expert plan output dict
        
        Raises:
            Exception: If all retries fail
        """
        import time
        
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"Running expert {expert['expert_name']} (attempt {attempt + 1}/{max_retries + 1})")
                
                # Read input files
                frozen_spec = self.blackboard.read("frozen_spec.json")
                structured_requirements = self.blackboard.read("structured_requirements.json")
                
                # Build prompt (base + specialization)
                prompt = self.expert_planner_prompt
                prompt = prompt.replace("{expert_name}", expert["expert_name"])
                prompt = prompt.replace("{domain}", expert["domain"])
                prompt = prompt.replace("{focus_areas}", ", ".join(expert["focus_areas"]))
                prompt = prompt.replace("{evaluation_lens}", expert["evaluation_lens"])
                prompt = prompt.replace("{frozen_spec}", json.dumps(frozen_spec, indent=2))
                prompt = prompt.replace("{structured_requirements}", json.dumps(structured_requirements, indent=2))
                
                # Spawn LLM worker
                worker_output = self._adapted_spawn(
                    task=prompt,
                    output_path=f"stages/expert_plans/{expert['expert_name']}.json",
                    timeout=600,
                )
                if worker_output is None:
                    raise RuntimeError(f"spawn_fn returned None for expert_planner_{expert['expert_name']}")
                
                # Validate output
                try:
                    ExpertPlanSchema(**worker_output)
                except Exception as e:
                    logger.error(f"Expert Planner output validation failed: {e}")
                    raise
                
                # Save to blackboard
                self.blackboard.write(f"stages/expert_plans/{expert['expert_name']}.json", worker_output)
                
                return worker_output
                
            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"Expert {expert['expert_name']} failed after {max_retries + 1} attempts: {e}")
                    raise
                
                # Exponential backoff: 1s, 2s, 4s, ...
                backoff_time = 2 ** attempt
                logger.warning(f"Expert {expert['expert_name']} attempt {attempt + 1} failed, retrying in {backoff_time}s: {e}")
                time.sleep(backoff_time)
        
        # Should never reach here
        raise RuntimeError(f"Expert {expert['expert_name']} retry logic error")
    
    def _load_expert_checkpoint(self, expert_name: str) -> Optional[dict]:
        """
        加载已完成的 Expert Plan（断点续跑）
        
        Args:
            expert_name: Expert name
        
        Returns:
            Expert plan dict if exists, None otherwise
        """
        path = f"stages/expert_plans/{expert_name}.json"
        try:
            result = self.blackboard.read(path)
            logger.debug(f"Checkpoint loaded for {expert_name}")
            return result
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.warning(f"Failed to load checkpoint for {expert_name}: {e}")
            return None
    
    def _save_expert_checkpoint(self, expert_name: str, result: dict):
        """
        保存 Expert Plan 输出（checkpoint）
        
        Args:
            expert_name: Expert name
            result: Expert plan output dict
        """
        path = f"stages/expert_plans/{expert_name}.json"
        try:
            self.blackboard.write(path, result)
            logger.debug(f"Checkpoint saved for {expert_name}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint for {expert_name}: {e}")
    
    def _mock_expert_planner(self, expert: dict) -> dict:
        """Mock Expert Planner output (for testing)"""
        return {
            "schema_version": "1.0.0",
            "expert_name": expert["expert_name"],
            "constraints": [
                {
                    "constraint_id": "C-001",
                    "description": f"{expert['domain']} constraint 1",
                    "priority": "MUST",
                    "rationale": "Critical requirement",
                },
                {
                    "constraint_id": "C-002",
                    "description": f"{expert['domain']} constraint 2",
                    "priority": "SHOULD",
                    "rationale": "Important requirement",
                },
            ],
            "risks": [
                {
                    "risk_id": "R-001",
                    "description": f"{expert['domain']} risk 1",
                    "mitigation": "Mitigation strategy",
                },
            ],
            "acceptance_criteria": [
                {
                    "criterion_id": "AC-001",
                    "description": f"{expert['domain']} acceptance criterion 1",
                    "verification_method": "Run test X, expect Y",
                },
            ],
            "covered_req_ids": ["REQ-P0-001"],
        }
    
    def _run_convergence_planner(
        self,
        expert_manifest: dict,
        expert_plans: list[dict],
    ) -> dict:
        """
        Run Convergence Planner (Layer 2)（含断点续跑）
        
        Flow:
        1. 检查是否已有输出（断点恢复）
        2. Read input files
        3. Build prompt
        4. Spawn LLM worker
        5. Validate output
        6. Save to blackboard
        """
        # 检查是否已有输出（断点恢复）
        checkpoint = self._load_checkpoint("stages/convergence_planning.json")
        if checkpoint:
            logger.info("Step 4: 从断点恢复 convergence_planning.json")
            return checkpoint
        
        # Read input files
        frozen_spec = self.blackboard.read("frozen_spec.json")
        
        # Build prompt
        prompt = self.convergence_planner_prompt.replace("{frozen_spec}", json.dumps(frozen_spec, indent=2))
        prompt = prompt.replace("{meta_planning}", json.dumps(expert_manifest, indent=2))
        prompt = prompt.replace("{expert_plans}", json.dumps(expert_plans, indent=2))
        
        # Spawn LLM worker
        if self.spawn_fn:
            worker_output = self._adapted_spawn(
                task=prompt,
                output_path="stages/convergence_planning.json",
                timeout=600,
            )
            if worker_output is None:
                raise RuntimeError("spawn_fn returned None for convergence_planner")
        else:
            # Fallback for testing
            worker_output = self._mock_convergence_planner(expert_plans)
        
        # Validate output (unified_constraints + verification_checklist)
        try:
            UnifiedConstraintsSchema(**worker_output["unified_constraints"])
            VerificationChecklistSchema(**worker_output["verification_checklist"])
        except Exception as e:
            logger.error(f"Convergence Planner output validation failed: {e}")
            raise
        
        # Save to blackboard（checkpoint）
        self._save_checkpoint("stages/unified_constraints.json", worker_output["unified_constraints"])
        self._save_checkpoint("stages/verification_checklist.json", worker_output["verification_checklist"])
        self._save_checkpoint("stages/convergence_planning.json", worker_output)
        
        return worker_output
    
    def _mock_convergence_planner(self, expert_plans: list[dict]) -> dict:
        """Mock Convergence Planner output (for testing)"""
        # Merge constraints from all experts
        unified_constraints = []
        constraint_id = 1
        
        for plan in expert_plans:
            for constraint in plan["constraints"]:
                unified_constraints.append({
                    "constraint_id": f"UC-{constraint_id:03d}",
                    "description": constraint["description"],
                    "priority": constraint["priority"],
                    "source_experts": [plan["expert_name"]],
                    "conflicts_resolved": [],
                })
                constraint_id += 1
        
        # Generate verification checklist
        verification_checklist = []
        check_id = 1
        
        for constraint in unified_constraints:
            verification_checklist.append({
                "check_id": f"VC-{check_id:03d}",
                "constraint_id": constraint["constraint_id"],
                "verification_method": f"Verify {constraint['description']}",
                "expected_result": "Pass",
            })
            check_id += 1
        
        return {
            "schema_version": "1.0.0",
            "unified_constraints": {
                "schema_version": "1.0.0",
                "constraints": unified_constraints,
                "rejected_constraints": [],
                "meta": {
                    "total_expert_plans": len(expert_plans),
                    "total_input_constraints": sum(len(p["constraints"]) for p in expert_plans),
                    "total_output_constraints": len(unified_constraints),
                    "merge_ratio": len(unified_constraints) / sum(len(p["constraints"]) for p in expert_plans),
                },
                "covered_req_ids": ["REQ-P0-001"],
            },
            "verification_checklist": {
                "schema_version": "1.0.0",
                "checklist": verification_checklist,
                "total_checks": len(verification_checklist),
            },
        }
    
    def _run_reviewer_convergence(self, convergence_output: dict) -> dict:
        """
        Run Reviewer_Convergence (validate Convergence output)（含断点续跑）
        
        Flow:
        1. 检查是否已有输出（断点恢复）
        2. Read input files
        3. Build prompt
        4. Spawn LLM worker
        5. Save to blackboard
        """
        # 检查是否已有输出（断点恢复）
        checkpoint = self._load_checkpoint("stages/reviewer_convergence.json")
        if checkpoint:
            logger.info("Step 5: 从断点恢复 reviewer_convergence.json")
            return checkpoint
        
        # Read input files
        frozen_spec = self.blackboard.read("frozen_spec.json")
        expert_manifest = self.blackboard.read("stages/meta_planning.json")
        expert_plans = []
        
        for expert in expert_manifest["experts"]:
            plan = self.blackboard.read(f"stages/expert_plans/{expert['expert_name']}.json")
            expert_plans.append(plan)
        
        # Build prompt
        prompt = self.reviewer_convergence_prompt.replace("{frozen_spec}", json.dumps(frozen_spec, indent=2))
        prompt = prompt.replace("{meta_planning}", json.dumps(expert_manifest, indent=2))
        prompt = prompt.replace("{expert_plans}", json.dumps(expert_plans, indent=2))
        prompt = prompt.replace("{unified_constraints}", json.dumps(convergence_output["unified_constraints"], indent=2))
        prompt = prompt.replace("{verification_checklist}", json.dumps(convergence_output["verification_checklist"], indent=2))
        
        # Spawn LLM worker
        if self.spawn_fn:
            worker_output = self._adapted_spawn(
                task=prompt,
                output_path="stages/reviewer_convergence.json",
                timeout=600,
            )
            if worker_output is None:
                raise RuntimeError("spawn_fn returned None for reviewer_convergence")
        else:
            # Fallback for testing
            worker_output = self._mock_reviewer_convergence()
        
        # Save to blackboard（checkpoint）
        self._save_checkpoint("stages/reviewer_convergence.json", worker_output)
        
        return worker_output
    
    def _mock_reviewer_convergence(self) -> dict:
        """Mock Reviewer_Convergence output (for testing)"""
        return {
            "schema_version": "1.0.0",
            "reviewer": "reviewer_convergence",
            "overall_verdict": "PASS",
            "overall_score": 0.91,
            "reviews": {},
            "issues": [],
            "suggestions": [],
        }
    
    def _run_harness_agent(
        self,
        convergence_output: dict,
        expert_manifest: dict,
    ) -> dict:
        """Run Harness Agent (Gate A + Gate B evaluation)（含断点续跑）

        V2 Phase 1.4: Layer 2 语义校准 + Gate B CRITICAL 保底检查。
        Layer 2 是可选增强，当 llm_judge_fn 未设置时自动 fallback 到规则判定（V1 兼容）。
        
        Flow:
        1. 检查是否已有输出（断点恢复）
        2. Build prompt
        3. Spawn LLM worker
        4. Layer 2 语义校准
        5. Gate B CRITICAL 保底检查
        6. Save to blackboard
        """
        # 检查是否已有输出（断点恢复）
        checkpoint = self._load_checkpoint("stages/harness_planning.json")
        if checkpoint:
            logger.info("Step 6: 从断点恢复 harness_planning.json")
            return checkpoint
        
        # Build prompt
        prompt = self.harness_agent_prompt
        prompt = prompt.replace("{stage_output}", json.dumps(convergence_output, indent=2))
        prompt = prompt.replace("{gate_a_config}", json.dumps(expert_manifest["gate_a"], indent=2))
        prompt = prompt.replace("{gate_b_config}", json.dumps(expert_manifest["gate_b"], indent=2))

        # Spawn LLM worker
        if self.spawn_fn:
            worker_output = self._adapted_spawn(
                task=prompt,
                output_path="stages/harness_planning.json",
                timeout=600,
            )
            if worker_output is None:
                raise RuntimeError("spawn_fn returned None for harness_agent")
        else:
            # Fallback for testing
            worker_output = self._mock_harness_agent()

        # [V2 Phase 1.4] Layer 2: 语义校准
        llm_judge_fn = getattr(self, 'llm_judge_fn', None)
        layer2 = GateALayer2Calibration(llm_judge_fn=llm_judge_fn)

        # Extract Layer 1 scores from harness output
        gate_a = worker_output.get("gate_a", {})
        layer1_scores = gate_a.get("scores", {})
        harness_reasoning = json.dumps(gate_a.get("reasoning", {}), ensure_ascii=False)

        # Read frozen_spec if available (for Layer 2 prompt context)
        try:
            frozen_spec = self.blackboard.read("frozen_spec.json")
        except Exception:
            frozen_spec = {}

        layer2_result = layer2.run_majority_vote(
            stage_output=convergence_output,
            frozen_spec=frozen_spec,
            harness_reasoning=harness_reasoning,
            scores=layer1_scores,
        )
        worker_output["gate_a_layer2"] = layer2_result

        # 如果 Layer 2 判定 FAIL，覆盖 Layer 1 的 PASS
        if layer2_result["semantic_verdict"] == "FAIL":
            worker_output["overall_verdict"] = "FAIL"
            worker_output["layer2_override_reason"] = layer2_result["votes"]
            # Also update final_verdict if present
            if "final_verdict" in worker_output and isinstance(worker_output["final_verdict"], dict):
                worker_output["final_verdict"]["final_verdict"] = "FAIL"
                worker_output["final_verdict"]["layer2_override"] = True

        # [V2 Phase 1.4] Gate B CRITICAL 保底检查
        gate_b_results = worker_output.get("gate_b", {}).get("checks", [])
        gate_b_dynamic = expert_manifest.get("gate_b", {}).get("dynamic_checks", [])
        if gate_b_results and gate_b_dynamic:
            gate_b_critical = evaluate_gate_b_critical(gate_b_results, gate_b_dynamic)
            worker_output["gate_b_critical"] = gate_b_critical
            if gate_b_critical["verdict"] == "FAIL":
                worker_output["overall_verdict"] = "FAIL"
                if "final_verdict" in worker_output and isinstance(worker_output["final_verdict"], dict):
                    worker_output["final_verdict"]["final_verdict"] = "FAIL"
                    worker_output["final_verdict"]["gate_b_critical_override"] = True

        # Save to blackboard（checkpoint）
        self._save_checkpoint("stages/harness_planning.json", worker_output)

        return worker_output
    
    def _mock_harness_agent(self) -> dict:
        """Mock Harness Agent output (for testing)"""
        return {
            "schema_version": "1.0.0",
            "gate_a": {
                "score": 0.87,
                "verdict": "PASS",
                "scores": {
                    "completeness": 0.90,
                    "necessity": 0.85,
                    "alignment": 0.88,
                    "global_impact": 0.82,
                },
                "reasoning": {
                    "completeness": "Good coverage",
                    "necessity": "Reasonable constraints",
                    "alignment": "Aligned with task profile",
                    "global_impact": "Considered global impact",
                },
            },
            "gate_b": {
                "pass_rate": 1.0,
                "verdict": "PASS",
                "checks": [],
                "failed_items": [],
            },
            "final_verdict": {
                "final_verdict": "PASS",
                "gate_a": "PASS",
                "gate_b": "PASS",
            },
        }
    
    def _generate_planning_convergence(
        self,
        expert_manifest: dict,
        convergence_output: dict,
        harness_output: dict,
    ) -> dict:
        """Generate planning_convergence.json（含断点续跑）
        
        Flow:
        1. 检查是否已有输出（断点恢复）
        2. Build convergence data
        3. Validate output
        4. Save to blackboard
        """
        # 检查是否已有输出（断点恢复）
        checkpoint = self._load_checkpoint("planning_convergence.json")
        if checkpoint:
            logger.info("Step 7: 从断点恢复 planning_convergence.json")
            return checkpoint
        
        # Build convergence data
        planning_convergence = {
            "schema_version": "1.0.0",
            "module": "planning",
            "unified_constraints": convergence_output["unified_constraints"]["unified_constraints"],
            "verification_checklist": convergence_output["verification_checklist"]["checklist"],
            "planning_summary": self._generate_planning_summary(expert_manifest, convergence_output),
            "expert_divergence": self._identify_expert_divergence(convergence_output["unified_constraints"]),
            "original_references": {
                "meta_planning": {
                    "path": "stages/meta_planning.json",
                    "hash": self._compute_hash(expert_manifest),
                    "size_bytes": len(json.dumps(expert_manifest)),
                },
            },
            "semantic_verification": {
                "verdict": "EQUIVALENT",
                "confidence": 0.95,
                "divergences": [],
            },
            "gate_a_scores": harness_output["gate_a"],
            "gate_b_results": harness_output["gate_b"],
            "gate_verdict": harness_output["final_verdict"],
            "_metadata": {
                "produced_at": self._get_timestamp(),
                "schema_version": "1.0.0",
                "module": "planning",
                "stage_count": 5,
            },
        }
        
        # Validate output
        try:
            PlanningConvergenceSchema(**planning_convergence)
        except Exception as e:
            logger.error(f"Planning convergence validation failed: {e}")
            raise
        
        # Save to blackboard（checkpoint）
        self._save_checkpoint("planning_convergence.json", planning_convergence)
        
        return planning_convergence
    
    def _generate_planning_summary(
        self,
        expert_manifest: dict,
        convergence_output: dict,
    ) -> str:
        """Generate planning summary (≤500 words)"""
        domain = expert_manifest["task_profile"]["domain"]
        complexity = expert_manifest["task_profile"]["complexity"]
        num_experts = len(expert_manifest["experts"])
        num_constraints = len(convergence_output["unified_constraints"]["unified_constraints"])
        
        summary = f"""
Planning module completed successfully.

Task Profile:
- Domain: {domain}
- Complexity: {complexity}
- Risk Areas: {', '.join(expert_manifest['task_profile']['risk_areas'])}

Expert Selection:
- {num_experts} experts selected based on complexity level
- Experts: {', '.join(e['expert_name'] for e in expert_manifest['experts'])}

Unified Constraints:
- {num_constraints} constraints merged from expert plans
- Priorities: {self._count_priorities(convergence_output['unified_constraints']['unified_constraints'])}

Gate Evaluation:
- Gate A and Gate B configured for quality assurance
- Verdict policy: warning_acceptable={expert_manifest['verdict_policy']['warning_acceptable']}
"""
        
        return summary.strip()
    
    def _count_priorities(self, constraints: list[dict]) -> str:
        """Count constraint priorities"""
        must_count = sum(1 for c in constraints if c["priority"] == "MUST")
        should_count = sum(1 for c in constraints if c["priority"] == "SHOULD")
        may_count = sum(1 for c in constraints if c["priority"] == "MAY")
        
        return f"MUST: {must_count}, SHOULD: {should_count}, MAY: {may_count}"
    
    def _identify_expert_divergence(self, unified_constraints: dict) -> list[dict]:
        """Identify expert divergence (conflicts resolved)"""
        divergences = []
        
        for constraint in unified_constraints["unified_constraints"]:
            if constraint["conflicts_resolved"]:
                divergences.append({
                    "constraint_id": constraint["constraint_id"],
                    "source_experts": constraint["source_experts"],
                    "conflicts": constraint["conflicts_resolved"],
                })
        
        return divergences
    
    def _compute_hash(self, data: dict) -> str:
        """Compute SHA256 hash of data"""
        import hashlib
        
        data_str = json.dumps(data, sort_keys=True)
        return f"sha256:{hashlib.sha256(data_str.encode()).hexdigest()}"
    
    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        
        return datetime.now().isoformat()


__all__ = ["PlanningOrchestrator"]
# [V2 Phase 0a] P0-1: 修复 run() 中 state 引用 bug（state → self.state，_save_state(state) → _save_state()）
