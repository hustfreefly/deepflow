"""
Master Orchestrator — Solution Pro V2 三模块串联 Pipeline

[R1-P0 采纳] 极简调度器，不做语义判断，只做：
1. 模块顺序调度（Planning → Research → ReviewQC）
2. 状态管理（master_state.json + module_state.json 双层验证）
3. 错误隔离（ModuleFailure 不影响其他模块的已完成输出）
4. 断点续跑（skip_completed 机制 + 双层 state 验证）
5. 超时保护（模块级差异化超时）
6. 降级策略（每模块有独立降级行为）
"""
import logging
import os
import time
import json
import threading
from typing import Optional, Callable
from pathlib import Path

from domains.solution_pro.pipeline_exceptions import (
    PipelineError, ModuleFailureError, ModuleTimeoutError,
    ConvergenceFailureError, DegradedPipelineError,
)
from domains.solution_pro.pipeline_watcher import PipelineWatcher
from domains.solution_pro.blackboard import STAGE_PATH_REGISTRY

logger = logging.getLogger(__name__)

# 模块级差异化超时 [R1-P1 采纳]
MODULE_TIMEOUTS = {
    "planning": 600,    # 5 min
    "research": 900,    # 15 min
    "review_qc": 600,   # 10 min
}

# 降级行为定义 [R1-P1 采纳]
DEGRADATION_STRATEGIES = {
    "planning": "default_expert_manifest",     # 使用 2 个通用 expert
    "research": "skip_with_degraded_flag",      # 跳过，标记 degraded=true
    "review_qc": "degraded_final_convergence",  # 使用 DegradedFinalConvergenceSchema
}


class MasterOrchestrator:
    """
    Solution Pro V2 Master Orchestrator
    
    职责：调度 Planning → Research → ReviewQC 三模块串联执行。
    不做任何语义判断（AI Native 合规）。
    """
    
    def __init__(self, blackboard, spawn_fn=None, config=None):
        self.blackboard = blackboard
        self.spawn_fn = spawn_fn
        
        # V3: prod 环境强制要求 spawn_fn（防止静默 fallback）
        if spawn_fn is None and os.environ.get("DEEPFLOW_ENV") == "prod":
            raise ValueError(
                "spawn_fn is required in production mode. "
                "Set DEEPFLOW_ENV=test for mock mode, or pass spawn_fn explicitly."
            )
        
        self.config = config or {}
        self.state = {}
        self._state_lock = threading.Lock()
        
        # 模块超时配置（可覆盖默认值）
        self.module_timeouts = {**MODULE_TIMEOUTS, **self.config.get("module_timeouts", {})}
        
        # 降级模块记录
        self.degraded_modules = []
        
        # Pipeline Watcher — 运行时可观测性
        try:
            self.watcher = PipelineWatcher(output_dir=str(self.blackboard.session_dir))
        except Exception as e:
            logger.warning(f"Failed to initialize PipelineWatcher: {e}")
            self.watcher = None
    
    def run(self, user_input: str, config: dict = None) -> dict:
        """
        Pipeline 主入口
        
        Args:
            user_input: 用户输入（需求描述）
            config: 配置（topic, solution_type, mode 等）
        
        Returns:
            pipeline_result dict
        """
        config = config or {}
        start_time = time.time()
        
        logger.info(f"Pipeline started: topic={config.get('topic', 'N/A')}")
        
        # 加载/恢复 state
        self._load_state()
        
        # 初始化 pipeline metrics
        metrics = {
            "pipeline_start": time.time(),
            "modules": {},
            "degraded_modules": [],
        }
        
        try:
            # Module 1: Planning
            logger.info("[Pipeline] === Module 1/3: Planning ===")
            planning_output = self._run_module(
                "planning",
                lambda: self._execute_planning(user_input, config),
            )
            metrics["modules"]["planning"] = self._module_metrics("planning", planning_output)
            logger.info(f"[Pipeline] Planning done, completed_modules={self.state.get('completed_modules', [])}")
            
            # Module 2: Research
            logger.info("[Pipeline] === Module 2/3: Research ===")
            research_output = self._run_module(
                "research",
                lambda: self._execute_research(planning_output, config),
            )
            metrics["modules"]["research"] = self._module_metrics("research", research_output)
            logger.info(f"[Pipeline] Research done, completed_modules={self.state.get('completed_modules', [])}")
            
            # Module 3: ReviewQC
            logger.info("[Pipeline] === Module 3/3: ReviewQC ===")
            review_qc_output = self._run_module(
                "review_qc",
                lambda: self._execute_review_qc(planning_output, research_output, config),
            )
            metrics["modules"]["review_qc"] = self._module_metrics("review_qc", review_qc_output)
            logger.info(f"[Pipeline] ReviewQC done, completed_modules={self.state.get('completed_modules', [])}")
            
            # 生成最终报告
            final_report = self._generate_final_report(
                planning_output, research_output, review_qc_output, config
            )
            
            # 记录 pipeline 指标
            metrics["pipeline_end"] = time.time()
            metrics["total_duration"] = metrics["pipeline_end"] - metrics["pipeline_start"]
            metrics["status"] = "COMPLETE"
            metrics["degraded_modules"] = self.degraded_modules
            
            self._save_pipeline_metrics(metrics)
            
            # Watcher: pipeline completed — write report to blackboard
            try:
                if self.watcher:
                    watcher_report = self.watcher.generate_report()
                    watcher_path = STAGE_PATH_REGISTRY.get(
                        "pipeline_watcher_report", "v2/pipeline_watcher_report.json"
                    )
                    self.blackboard.write(watcher_path, watcher_report)
                    logger.info(f"[Watcher] Pipeline report written to blackboard: {watcher_path}")
            except Exception as e:
                logger.warning(f"[Watcher] Failed to write pipeline report: {e}")
            
            logger.info(f"Pipeline completed in {metrics['total_duration']:.1f}s")
            
            return {
                "status": "COMPLETE",
                "planning": planning_output,
                "research": research_output,
                "review_qc": review_qc_output,
                "final_report": final_report,
                "metrics": metrics,
                "degraded_modules": self.degraded_modules,
            }
            
        except PipelineError as e:
            logger.error(f"Pipeline failed: {e}")
            metrics["status"] = "FAILED"
            metrics["error"] = str(e)
            metrics["pipeline_end"] = time.time()
            self._save_pipeline_metrics(metrics)
            
            # Watcher: pipeline failed — still save partial report
            try:
                if self.watcher:
                    watcher_report = self.watcher.generate_report()
                    watcher_path = STAGE_PATH_REGISTRY.get(
                        "pipeline_watcher_report", "v2/pipeline_watcher_report.json"
                    )
                    self.blackboard.write(watcher_path, watcher_report)
            except Exception as e:
                logger.warning(f"[Watcher] Failed to write pipeline report on failure: {e}")
            
            raise
    
    def _run_module(self, module_name: str, execute_fn: Callable) -> dict:
        """
        运行单个模块（含断点续跑 + 超时 + 降级）
        
        双层 State 验证 [R1-P0 + R2-P0 采纳]:
        - master_state.json: 模块级完成状态
        - module_{name}_state.json: stage 级状态
        - 断点续跑需双重确认
        """
        # 检查断点续跑（双层验证）
        if self._is_module_completed(module_name):
            logger.info(f"[Module:{module_name}] already completed (from checkpoint), skipping")
            return self._load_module_output(module_name)
        
        timeout = self.module_timeouts.get(module_name, 600)
        logger.info(f"[Module:{module_name}] starting (timeout={timeout}s)")
        
        # Watcher: module started
        try:
            if self.watcher:
                self.watcher.on_module_start(module_name)
        except Exception as e:
            logger.warning(f"[Watcher] on_module_start failed: {e}")
        
        try:
            # 超时保护
            result = self._execute_with_timeout(execute_fn, timeout, module_name)
            logger.info(f"[Module:{module_name}] execution returned (type={type(result).__name__})")
            
            # 保存输出（原子写入）— 保存失败不应阻塞状态更新
            try:
                self._save_module_output(module_name, result)
                logger.info(f"[Module:{module_name}] output saved")
            except Exception as save_err:
                logger.error(f"[Module:{module_name}] failed to save output: {save_err}")
                # 输出保存失败但模块已执行完成，仍标记为 completed
            
            # 更新 state — 无论输出保存是否成功，执行成功即标记完成
            self._mark_module_completed(module_name)
            logger.info(f"[Module:{module_name}] marked as completed")
            
            # Watcher: module completed
            try:
                if self.watcher:
                    self.watcher.on_module_complete(module_name, result)
            except Exception as e:
                logger.warning(f"[Watcher] on_module_complete failed: {e}")
            
            return result
            
        except ModuleTimeoutError:
            # Watcher: module timeout
            try:
                if self.watcher:
                    self.watcher.on_module_timeout(module_name, timeout)
            except Exception as e:
                logger.warning(f"[Watcher] on_module_timeout failed: {e}")
            # 超时 → 降级
            logger.warning(f"[Module:{module_name}] timed out after {timeout}s, applying degradation")
            degraded = self._apply_degradation(module_name)
            # Watcher: module degraded
            try:
                if self.watcher:
                    self.watcher.on_module_degraded(module_name, f"timeout after {timeout}s")
            except Exception as e:
                logger.warning(f"[Watcher] on_module_degraded failed: {e}")
            self._mark_module_completed(module_name)
            logger.info(f"[Module:{module_name}] degradation applied and marked completed")
            return degraded
            
        except Exception as e:
            # Watcher: module failed
            try:
                if self.watcher:
                    self.watcher.on_module_failed(module_name, e)
            except Exception as w_err:
                logger.warning(f"[Watcher] on_module_failed failed: {w_err}")
            # 其他错误 → 尝试降级
            logger.error(f"[Module:{module_name}] failed with exception: {e}", exc_info=True)
            degradation = DEGRADATION_STRATEGIES.get(module_name)
            if degradation:
                logger.warning(f"[Module:{module_name}] applying degradation '{degradation}'")
                degraded = self._apply_degradation(module_name)
                # Watcher: module degraded (after exception)
                try:
                    if self.watcher:
                        self.watcher.on_module_degraded(module_name, str(e))
                except Exception as w_err:
                    logger.warning(f"[Watcher] on_module_degraded failed: {w_err}")
                self._mark_module_completed(module_name)
                logger.info(f"[Module:{module_name}] degradation applied and marked completed")
                return degraded
            logger.error(f"[Module:{module_name}] no degradation strategy, raising ModuleFailureError")
            raise ModuleFailureError(module_name, "unknown", e)
    
    def _execute_planning(self, user_input: str, config: dict) -> dict:
        """执行 Planning 模块"""
        from domains.solution_pro.planning_orchestrator import PlanningOrchestrator
        
        orchestrator = PlanningOrchestrator(
            session_id=self.blackboard.session_id,
            spawn_fn=self.spawn_fn,
            base_dir=str(self.blackboard.session_dir.parent),
        )
        
        # 构造 frozen_spec 和 structured_requirements
        frozen_spec = self._build_frozen_spec(user_input, config)
        structured_requirements = self._build_structured_requirements(user_input, config)
        
        return orchestrator.run(
            frozen_spec=frozen_spec,
            structured_requirements=structured_requirements,
            spawn_fn=self.spawn_fn,
        )
    
    def _execute_research(self, planning_output: dict, config: dict) -> dict:
        """执行 Research 模块"""
        from domains.solution_pro.research_orchestrator import ResearchOrchestrator
        
        orchestrator = ResearchOrchestrator(
            session_id=self.blackboard.session_id,
            spawn_fn=self.spawn_fn,
            base_dir=str(self.blackboard.session_dir.parent),
        )
        
        frozen_spec = self._build_frozen_spec("", config)
        
        return orchestrator.run(
            frozen_spec=frozen_spec,
            planning_output=planning_output,
            spawn_fn=self.spawn_fn,
        )
    
    def _execute_review_qc(self, planning_output: dict, research_output: dict, config: dict) -> dict:
        """执行 ReviewQC 模块"""
        from domains.solution_pro.review_qc_orchestrator import ReviewQCOrchestrator
        
        orchestrator = ReviewQCOrchestrator(
            session_id=self.blackboard.session_id,
            spawn_fn=self.spawn_fn,
            base_dir=str(self.blackboard.session_dir.parent),
        )
        
        frozen_spec = self._build_frozen_spec("", config)
        
        return orchestrator.run(
            frozen_spec=frozen_spec,
            planning_output=planning_output,
            research_output=research_output,
            spawn_fn=self.spawn_fn,
        )
    
    def _generate_final_report(self, planning, research, review_qc, config) -> dict:
        """
        生成最终报告
        
        [R1-P0 采纳] Summarizer 归属 Master，与 ReviewQC convergence 不重叠
        """
        return {
            "topic": config.get("topic", "Unknown"),
            "solution_type": config.get("solution_type", "architecture"),
            "planning_summary": self._summarize_planning(planning),
            "research_summary": self._summarize_research(research),
            "quality_assessment": self._summarize_review_qc(review_qc),
            "degraded_modules": self.degraded_modules,
            "generated_at": time.time(),
        }
    
    # === State 管理（双层验证）===
    
    def _load_state(self):
        """加载 master state"""
        try:
            path = "v2/master_state.json"
            self.state = self.blackboard.read_json(path)
            logger.info(f"Loaded master state: {len(self.state.get('completed_modules', []))} modules completed")
        except Exception:
            self.state = {"completed_modules": [], "module_outputs": {}}
    
    def _save_state(self):
        """保存 master state（原子写入）"""
        path = "v2/master_state.json"
        self.blackboard.write(path, self.state)
    
    def _is_module_completed(self, module_name: str) -> bool:
        """双层验证：master state + module state"""
        # Layer 1: master state
        if module_name not in self.state.get("completed_modules", []):
            return False
        
        # Layer 2: module state 文件存在且有效
        try:
            module_state_path = f"v2/{module_name}_output.json"
            output = self.blackboard.read_json(module_state_path)
            return output is not None and isinstance(output, dict)
        except Exception:
            return False
    
    def _mark_module_completed(self, module_name: str):
        """标记模块完成"""
        with self._state_lock:
            if "completed_modules" not in self.state:
                self.state["completed_modules"] = []
            if module_name not in self.state["completed_modules"]:
                self.state["completed_modules"].append(module_name)
            self._save_state()
    
    def _load_module_output(self, module_name: str) -> dict:
        """加载模块输出（从断点恢复）"""
        path = f"v2/{module_name}_output.json"
        return self.blackboard.read_json(path)
    
    def _save_module_output(self, module_name: str, output: dict):
        """保存模块输出（原子写入）"""
        path = f"v2/{module_name}_output.json"
        self.blackboard.write(path, output)
    
    # === 超时保护 ===
    
    def _execute_with_timeout(self, fn: Callable, timeout: int, module_name: str) -> dict:
        """带超时保护的执行"""
        result = [None]
        error = [None]
        
        def target():
            try:
                result[0] = fn()
            except Exception as e:
                error[0] = e
        
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            raise ModuleTimeoutError(module_name, timeout)
        
        if error[0]:
            raise error[0]
        
        return result[0]
    
    # === 降级策略 ===
    
    def _apply_degradation(self, module_name: str) -> dict:
        """应用模块降级策略"""
        strategy = DEGRADATION_STRATEGIES.get(module_name, "skip")
        self.degraded_modules.append(module_name)
        
        logger.warning(f"Applying degradation '{strategy}' for module '{module_name}'")
        
        if module_name == "planning":
            # 默认 ExpertManifest（2 个通用 expert）
            return {
                "schema_version": "degraded_planning_v1",
                "status": "DEGRADED",
                "experts": [
                    {"expert_name": "general_architect", "domain": "general"},
                    {"expert_name": "security_reviewer", "domain": "security"},
                ],
                "unified_constraints": {"constraints": []},
                "verification_checklist": {"items": []},
            }
        elif module_name == "research":
            return {
                "schema_version": "degraded_research_v1",
                "status": "DEGRADED",
                "degradation_flag": True,
                "findings": [],
                "sources": [],
            }
        elif module_name == "review_qc":
            return {
                "schema_version": "degraded_final_v1",
                "status": "DEGRADED",
                "degradation_flag": True,
                "degradation_reason": f"Module '{module_name}' failed or timed out",
                "partial_results": [],
                "quality_scores": {"degraded": True, "score": 0.0},
                "fix_loop_summary": {"abort_round": 0, "failure_diagnosis": "timeout or error"},
            }
        
        return {"status": "DEGRADED", "module": module_name}
    
    # === 辅助方法 ===
    
    def _build_frozen_spec(self, user_input: str, config: dict) -> dict:
        """构建 Frozen Spec"""
        return {
            "topic": config.get("topic", user_input),
            "solution_type": config.get("solution_type", "architecture"),
            "mode": config.get("mode", "standard"),
            "domain": config.get("domain", "backend_api"),
            "constraints": config.get("constraints", []),
        }
    
    def _build_structured_requirements(self, user_input: str, config: dict) -> dict:
        """构建 Structured Requirements"""
        return {
            "schema_version": "2.0",
            "requirements": [
                {
                    "req_id": "REQ-P0-001",
                    "description": user_input or config.get("topic", "Main requirement"),
                    "priority": "P0",
                }
            ],
        }
    
    def _summarize_planning(self, planning_output) -> dict:
        """摘要 Planning 输出（健壮版）"""
        if not isinstance(planning_output, dict):
            return {"expert_count": 0, "constraint_count": 0, "checklist_count": 0, "degraded": True}
        return {
            "expert_count": len(planning_output.get("experts", [])),
            "constraint_count": len(planning_output.get("unified_constraints", {}).get("constraints", [])),
            "checklist_count": len(planning_output.get("verification_checklist", {}).get("items", [])),
        }
    
    def _summarize_research(self, research_output) -> dict:
        """摘要 Research 输出（健壮版）"""
        if not isinstance(research_output, dict):
            return {"finding_count": 0, "source_count": 0, "degraded": True}
        return {
            "finding_count": len(research_output.get("findings", [])),
            "source_count": len(research_output.get("sources", [])),
            "degraded": research_output.get("degradation_flag", False),
        }
    
    def _summarize_review_qc(self, review_qc_output) -> dict:
        """摘要 ReviewQC 输出（健壮版）"""
        if not isinstance(review_qc_output, dict):
            return {"verdict": "UNKNOWN", "quality_score": 0.0, "fix_rounds": 0, "degraded": True}
        return {
            "verdict": review_qc_output.get("final_verdict", "UNKNOWN"),
            "quality_score": review_qc_output.get("quality_score", 0.0),
            "fix_rounds": review_qc_output.get("fix_loop_summary", {}).get("rounds", 0),
            "degraded": review_qc_output.get("degradation_flag", False),
        }
    
    def _module_metrics(self, module_name: str, output) -> dict:
        """记录模块指标（健壮版：处理 None/str/dict）"""
        if not isinstance(output, dict):
            return {
                "status": "UNKNOWN",
                "degraded": True,
                "timestamp": time.time(),
                "output_type": type(output).__name__ if output else "None",
            }
        return {
            "status": output.get("status", "COMPLETE"),
            "degraded": output.get("degradation_flag", False) or output.get("status") == "DEGRADED",
            "timestamp": time.time(),
        }
    
    def _save_pipeline_metrics(self, metrics: dict):
        """保存 Pipeline 指标（V2 子目录隔离）"""
        try:
            self.blackboard.write("v2/pipeline_metrics.json", metrics)
        except Exception as e:
            logger.warning(f"Failed to save pipeline metrics: {e}")


def create_pipeline(blackboard, spawn_fn=None, config=None, version="v2"):
    """
    工厂函数：创建 V1 或 V2 Pipeline
    
    [R2-P0 采纳] V1/V2 共存策略
    """
    if version == "v2":
        return MasterOrchestrator(blackboard, spawn_fn, config)
    else:
        # V1 入口（保持向后兼容）
        from domains.solution_pro.orchestrator_agent import OrchestratorAgent
        return OrchestratorAgent(
            session_id=blackboard.session_id,
            blackboard=blackboard,
            spawn_fn=spawn_fn,
        )
