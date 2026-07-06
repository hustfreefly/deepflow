"""
Master Orchestrator — Solution Pro 三模块串联 Pipeline

[R1-P0 采纳] 极简调度器，不做语义判断，只做：
1. 模块顺序调度（Planning → Research → Summary）
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
import hashlib
import threading
from datetime import datetime
from typing import Optional, Callable
from pathlib import Path

from domains.solution_pro.pipeline_exceptions import (
    PipelineError, ModuleFailureError, ModuleTimeoutError,
    ConvergenceFailureError, DegradedPipelineError,
)
from domains.solution_pro.pipeline_watcher import PipelineWatcher
from domains.solution_pro.blackboard import STAGE_PATH_REGISTRY
from core.trace import span, save_to_blackboard  # 全链路追踪：跨域 trace_id

logger = logging.getLogger(__name__)


# 降级策略占位（兼容旧版测试）
DEGRADATION_STRATEGIES = {
    "planning": "default_expert_manifest",
    "research": "skip_with_degraded_flag",
}

# 模块级差异化超时 [R1-P1 采纳]
MODULE_TIMEOUTS = {
    "planning": 600,    # 5 min
    "research": 900,    # 15 min
    "summary": 1200,    # 20 min (5+1 Phase，含并行 Analyzer)
}


class MasterOrchestrator:
    """
    Solution Pro Master Orchestrator
    
    职责：调度 Planning → Research → Summary 三模块串联执行。
    不做任何语义判断（AI Native 合规）。
    """
    
    def __init__(self, blackboard, spawn_fn=None, config=None):
        self.blackboard = blackboard
        self.spawn_fn = spawn_fn
        
        # prod 环境强制要求 spawn_fn（防止静默 fallback）
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
        
        # 降级模块记录（兼容旧版测试）
        self.degraded_modules = []
        
        # Pipeline Watcher — 运行时可观测性
        try:
            self.watcher = PipelineWatcher(output_dir=str(self.blackboard.session_dir))
        except Exception as e:
            logger.warning(f"Failed to initialize PipelineWatcher: {e}")
            self.watcher = None
    
    def run(self, user_input: str, config: dict = None, living_spec: dict = None) -> dict:
        """
        Pipeline 主入口
        
        Args:
            user_input: 用户输入（需求描述）
            config: 配置（topic, solution_type, mode 等）
            living_spec: Living Spec dict
        
        Returns:
            pipeline_result dict
        """
        config = config or {}
        start_time = time.time()
        
        logger.info(f"Pipeline started: topic={config.get('topic', 'N/A')}")

        # 全链路追踪：记录 Solution Pro pipeline 启动
        span("pipeline_start", domain="solution_pro", topic=config.get('topic', 'N/A'))
        
        # 准备 Living Spec 输入
        prepared_living_spec = self._prepare_input(user_input, config, living_spec)
        self.living_spec = prepared_living_spec  # 存储到 self，供 assertion 和子模块使用
        
        # 加载/恢复 state
        self._load_state()
        
        # 初始化 pipeline metrics
        metrics = {
            "pipeline_start": time.time(),
            "modules": {},
        }
        
        try:
            # Module 1: Planning
            logger.info("[Pipeline] === Module 1/3: Planning ===")
            span("module_start", domain="solution_pro", module="planning")
            planning_output = self._run_module(
                "planning",
                lambda: self._execute_planning(user_input, config, prepared_living_spec),
            )
            metrics["modules"]["planning"] = self._module_metrics("planning", planning_output)
            span("module_end", domain="solution_pro", module="planning")
            logger.info(f"[Pipeline] Planning done, completed_modules={self.state.get('completed_modules', [])}")
            
            # Module 2: Research
            logger.info("[Pipeline] === Module 2/3: Research ===")
            span("module_start", domain="solution_pro", module="research")
            research_output = self._run_module(
                "research",
                lambda: self._execute_research(planning_output, config, prepared_living_spec),
            )
            metrics["modules"]["research"] = self._module_metrics("research", research_output)
            span("module_end", domain="solution_pro", module="research")
            logger.info(f"[Pipeline] Research done, completed_modules={self.state.get('completed_modules', [])}")
            
            # Module 3: Summary（架构设计：收敛模块）
            logger.info("[Pipeline] === Module 3/3: Summary ===")
            span("module_start", domain="solution_pro", module="summary")
            summary_output = self._run_module(
                "summary",
                lambda: self._execute_summary(planning_output, research_output, config, prepared_living_spec),
            )
            metrics["modules"]["summary"] = self._module_metrics("summary", summary_output)
            span("module_end", domain="solution_pro", module="summary")
            logger.info(f"[Pipeline] Summary done, completed_modules={self.state.get('completed_modules', [])}")
            
            # 生成最终报告
            final_report = self._generate_final_report(
                planning_output, research_output, summary_output, config
            )
            
            # 记录 pipeline 指标
            metrics["pipeline_end"] = time.time()
            metrics["total_duration"] = metrics["pipeline_end"] - metrics["pipeline_start"]
            metrics["status"] = "COMPLETE"
            
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

            # 全链路追踪：记录 pipeline 完成 + 持久化到 blackboard
            span("pipeline_complete", domain="solution_pro", duration=metrics['total_duration'])
            try:
                save_to_blackboard(Path(self.blackboard.session_dir))
            except Exception:
                pass  # 追踪持久化失败不影响主流程
            
            return {
                "status": "COMPLETE",
                "planning": planning_output,
                "research": research_output,
                "summary": summary_output,
                "final_report": final_report,
                "metrics": metrics,
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
            
            # 保存输出并验证 — 失败时不标记 completed
            try:
                artifact = self._save_and_validate_module_output(module_name, result)
                self._mark_module_completed(module_name, artifact)
                logger.info(f"[Module:{module_name}] output saved and validated")
            except RuntimeError as save_err:
                logger.error(f"[Module:{module_name}] 完成失败: {save_err}")
                # 不标记 completed！模块保持 incomplete
                raise ModuleFailureError(module_name, "save_failed", save_err)
            
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
            # 超时 = 失败，不降级
            logger.error(f"[Module:{module_name}] timed out after {timeout}s — FAILING (no degradation)")
            raise ModuleTimeoutError(module_name, timeout)
            
        except Exception as e:
            # Watcher: module failed
            try:
                if self.watcher:
                    self.watcher.on_module_failed(module_name, e)
            except Exception as w_err:
                logger.warning(f"[Watcher] on_module_failed failed: {w_err}")
            # 异常 = 失败，不降级
            logger.error(f"[Module:{module_name}] failed with exception: {e}", exc_info=True)
            raise ModuleFailureError(module_name, "unknown", e)
    
    def _prepare_input(self, user_input: str, config: dict, living_spec: dict = None) -> dict:
        """
        准备 Living Spec 输入

        如果有 living_spec，直接用它（写入 blackboard 的 data/living_spec.json）
        如果没有，从 user_input + config 构造一个最小 Living Spec

        Args:
            user_input: 用户输入
            config: 配置
            living_spec: 外部传入的 Living Spec

        Returns:
            准备好的 Living Spec dict
        """
        if living_spec:
            # 有 living_spec，直接使用 + 快照机制
            logger.info
            try:
                self.blackboard.write("data/living_spec.json", living_spec)
            except Exception as e:
                logger.warning(f"Failed to write living_spec.json: {e}")
            # 快照机制：计算 hash + 写入 snapshot
            try:
                snapshot = json.loads(json.dumps(living_spec))  # deep copy
                snapshot_hash = hashlib.sha256(
                    json.dumps(living_spec, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest()[:16]
                snapshot["_snapshot_hash"] = snapshot_hash
                snapshot["_snapshot_at"] = datetime.now().isoformat()
                self.blackboard.write("data/living_spec_snapshot.json", snapshot)
                logger.info
            except Exception as e:
                logger.warning(f"Failed to create living_spec snapshot: {e}")

            # Living Spec 质量验证 (Devil's Advocate CRITICAL)
            spec_validation = self._validate_living_spec(living_spec)
            if not spec_validation["valid"]:
                logger.error(f"Living Spec validation failed: {spec_validation['issues']}")
            if spec_validation["issues"]:
                for issue in spec_validation["issues"]:
                    logger.warning(f"Living Spec issue: [{issue['severity']}] {issue['type']}: {issue['detail']}")
            if spec_validation["conflicts"]:
                for conflict in spec_validation["conflicts"]:
                    logger.warning(f"Living Spec conflict: {conflict['type']}: {conflict['detail']}")
            # 写入 blackboard 供审计
            self.blackboard.write("data/living_spec_validation.json", spec_validation)

            return living_spec

        # fallback: 从 user_input + config 构造最小 Living Spec
        logger.info
        topic = config.get("topic", user_input or "Unknown")
        minimal_living_spec = {
            "meta": {
                "engine": "spec_pro",
                "version": "2.1",
                "spec_version": 1,
                "scenario": "genesis",
                "mode": config.get("mode", "standard"),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "conversation_rounds": 0,
                "quality_score": 0,
                "quality_level": "C",
            },
            "confirmed": {
                "objective": topic,
                "pain_points": [],
                "success_metrics": [],
                "users": [],
                "key_scenarios": [],
                "capabilities": {
                    "always_do": [],
                    "should_do": [],
                    "never_do": [],
                },
                "quality_attributes": [],
                "constraints": config.get("constraints", {}),
                "integration": {},
                "risks_and_assumptions": {
                    "risks": [],
                    "assumptions": [],
                    "dependencies": [],
                },
                "terms": [],
                "user_directives": [],
            },
            "inferred": [],
            "guardrails": None,
            "solution_pro_hints": None,
            "route_recommendation": None,
            "narrative": user_input or topic,
            "requirement_index": [],
        }

        # 尝试从 living_spec 生成 requirement_index
        try:
            from domains.solution_pro.frozen_spec import generate_requirement_index
            minimal_living_spec["requirement_index"] = generate_requirement_index(minimal_living_spec)
        except Exception as e:
            logger.warning(f"Failed to generate requirement_index: {e}")

        try:
            self.blackboard.write("data/living_spec.json", minimal_living_spec)
        except Exception as e:
            logger.warning(f"Failed to write minimal living_spec.json: {e}")

        # 快照机制：同样为构造的 living_spec 创建快照
        try:
            snapshot = json.loads(json.dumps(minimal_living_spec))  # deep copy
            snapshot_hash = hashlib.sha256(
                json.dumps(minimal_living_spec, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()[:16]
            snapshot["_snapshot_hash"] = snapshot_hash
            snapshot["_snapshot_at"] = datetime.now().isoformat()
            self.blackboard.write("data/living_spec_snapshot.json", snapshot)
            logger.info
        except Exception as e:
            logger.warning(f"Failed to create minimal living_spec snapshot: {e}")

        # Living Spec 质量验证 (Devil's Advocate CRITICAL)
        spec_validation = self._validate_living_spec(minimal_living_spec)
        if not spec_validation["valid"]:
            logger.error(f"Living Spec validation failed: {spec_validation['issues']}")
        if spec_validation["issues"]:
            for issue in spec_validation["issues"]:
                logger.warning(f"Living Spec issue: [{issue['severity']}] {issue['type']}: {issue['detail']}")
        if spec_validation["conflicts"]:
            for conflict in spec_validation["conflicts"]:
                logger.warning(f"Living Spec conflict: {conflict['type']}: {conflict['detail']}")
        # 写入 blackboard 供审计
        self.blackboard.write("data/living_spec_validation.json", spec_validation)

        return minimal_living_spec

    def _validate_living_spec(self, living_spec: dict) -> dict:
        """验证 Living Spec 质量（确定性检查 + 冲突检测）

        AI Native: 代码做存在性检查，语义质量由上游 Spec Pro 保证。
        冲突解决策略：requirement_index 是权威源，narrative 是辅助理解。
        """
        issues = []
        narrative = living_spec.get("narrative", "")
        req_index = living_spec.get("requirement_index", [])

        # 1. narrative 存在性检查
        if not narrative or len(narrative.strip()) < 50:
            issues.append({
                "type": "narrative_too_short",
                "detail": f"narrative 长度 {len(narrative)} 字符，最低要求 50 字符",
                "severity": "WARNING",
            })

        # 2. requirement_index 存在性检查
        if not req_index:
            issues.append({
                "type": "requirement_index_empty",
                "detail": "requirement_index 为空，无法进行 REQ-ID 追溯",
                "severity": "WARNING",
            })

        # 3. 冲突检测：narrative 中的关键概念是否在 requirement_index 中有对应
        conflicts = []
        if narrative and req_index:
            req_titles = [r.get("title", "") for r in req_index if isinstance(r, dict)]
            mentioned = sum(1 for t in req_titles if t and t.lower() in narrative.lower())
            if req_titles and mentioned == 0:
                conflicts.append({
                    "type": "narrative_index_disconnected",
                    "detail": f"narrative 没有提到 requirement_index 中的任何标题 ({len(req_titles)} 个)",
                    "severity": "WARNING",
                })

        # 4. core_summary 检查
        core_summary = living_spec.get("core_summary", "")
        if not core_summary and narrative and len(narrative) > 5000:
            issues.append({
                "type": "missing_core_summary",
                "detail": "narrative 超过 5KB 但没有 core_summary，下游 Agent 将面临 token 开销",
                "severity": "INFO",
            })

        return {
            "valid": len([i for i in issues if i["severity"] == "ERROR"]) == 0,
            "issues": issues,
            "conflicts": conflicts,
            "conflict_resolution": {
                "authority": "requirement_index",
                "narrative_role": "auxiliary_context",
                "policy": "当 narrative 与 requirement_index 不一致时，以 requirement_index 为准",
            },
        }

    def _get_living_spec_snapshot(self) -> dict:
        """获取 living_spec 快照（优先 snapshot，fallback 到 living_spec.json）"""
        try:
            snapshot = self.blackboard.read_json("data/living_spec_snapshot.json")
            if snapshot and isinstance(snapshot, dict):
                return snapshot
        except Exception:
            pass
        try:
            return self.blackboard.read_json("data/living_spec.json")
        except Exception:
            return None

    def _execute_planning(self, user_input: str, config: dict, living_spec: dict = None) -> dict:
        """执行 Planning 模块"""
        from domains.solution_pro.planning_orchestrator import PlanningOrchestrator

        orchestrator = PlanningOrchestrator(
            session_id=self.blackboard.session_id,
            spawn_fn=self.spawn_fn,
            base_dir=str(self.blackboard.session_dir.parent),
        )

        # 使用 snapshot（保证一致性）
        snapshot = self._get_living_spec_snapshot()
        effective_living_spec = snapshot if snapshot else living_spec

        # 向后兼容 assertion (Arch-P1): living_spec 存在时禁止读取 frozen_spec 非索引字段
        if living_spec:
            assert self.living_spec is not None, "living_spec 已传入但 self.living_spec 为 None"

        # 传递 living_spec（优先）+ 兼容旧的 frozen_spec
        frozen_spec = self._build_frozen_spec(user_input, config, effective_living_spec)
        structured_requirements = self._build_structured_requirements(user_input, config)

        return orchestrator.run(
            frozen_spec=frozen_spec,
            structured_requirements=structured_requirements,
            spawn_fn=self.spawn_fn,
            living_spec=effective_living_spec,
        )

    def _execute_research(self, planning_output: dict, config: dict, living_spec: dict = None) -> dict:
        """执行 Research 模块"""
        from domains.solution_pro.research_orchestrator import ResearchOrchestrator

        orchestrator = ResearchOrchestrator(
            session_id=self.blackboard.session_id,
            spawn_fn=self.spawn_fn,
            base_dir=str(self.blackboard.session_dir.parent),
        )

        # 使用 snapshot（保证一致性）
        snapshot = self._get_living_spec_snapshot()
        effective_living_spec = snapshot if snapshot else living_spec

        # 向后兼容 assertion (Arch-P1): living_spec 存在时确保优先使用
        if living_spec:
            assert self.living_spec is not None, "living_spec 已传入但 self.living_spec 为 None"

        frozen_spec = self._build_frozen_spec("", config, effective_living_spec)

        return orchestrator.run(
            frozen_spec=frozen_spec,
            planning_output=planning_output,
            spawn_fn=self.spawn_fn,
            living_spec=effective_living_spec,
        )

    def _execute_summary(self, planning_output: dict, research_output: dict, config: dict, living_spec: dict = None) -> dict:
        """执行 Summary 模块（收敛模块，5+1 Phase）"""
        from domains.solution_pro.summary_orchestrator import SummaryOrchestrator

        orchestrator = SummaryOrchestrator(
            session_id=self.blackboard.session_id,
            spawn_fn=self.spawn_fn,
            base_dir=str(self.blackboard.session_dir.parent),
        )

        # 使用 snapshot（保证一致性）
        snapshot = self._get_living_spec_snapshot()
        effective_living_spec = snapshot if snapshot else living_spec

        frozen_spec = self._build_frozen_spec("", config, effective_living_spec)

        return orchestrator.run(
            frozen_spec=frozen_spec,
            planning_output=planning_output,
            research_output=research_output,
            spawn_fn=self.spawn_fn,
            living_spec=effective_living_spec,
        )
    
    def _generate_final_report(self, planning, research, summary, config) -> dict:
        """
        生成最终报告
        
        [R1-P0 采纳] Summarizer 归属 Master，与 ReviewQC convergence 不重叠
        """
        return {
            "topic": config.get("topic", "Unknown"),
            "solution_type": config.get("solution_type", "architecture"),
            "planning_summary": self._summarize_planning(planning),
            "research_summary": self._summarize_research(research),
            "quality_assessment": self._summarize_summary(summary),
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
        """双层验证：master state + module state + artifact integrity"""
        # Layer 1: master state
        if module_name not in self.state.get("completed_modules", []):
            return False
        
        # Layer 2: module state 文件存在且有效
        try:
            module_state_path = f"v2/{module_name}_output.json"
            output = self.blackboard.read_json(module_state_path)
            if output is None or not isinstance(output, dict):
                return False
        except Exception:
            return False
        
        # Layer 3: artifact integrity check (if artifact record exists)
        artifacts = self.state.get("module_artifacts", {})
        if module_name in artifacts:
            artifact = artifacts[module_name]
            artifact_path = artifact.get("path")
            expected_hash = artifact.get("sha256")
            if not artifact_path or not expected_hash:
                return False
            # Verify file exists and hash matches
            try:
                with open(artifact_path) as f:
                    saved_data = json.load(f)
                actual_hash = hashlib.sha256(
                    json.dumps(saved_data, sort_keys=True).encode()
                ).hexdigest()
                if actual_hash != expected_hash:
                    logger.warning(
                        f"[Module:{module_name}] artifact hash mismatch "
                        f"(expected={expected_hash[:8]}..., actual={actual_hash[:8]}...)"
                    )
                    return False
            except Exception:
                return False
        
        return True
    
    def _mark_module_completed(self, module_name: str, artifact: dict = None):
        """标记模块完成，可选记录 artifact 信息"""
        with self._state_lock:
            if "completed_modules" not in self.state:
                self.state["completed_modules"] = []
            if module_name not in self.state["completed_modules"]:
                self.state["completed_modules"].append(module_name)
            
            # Record artifact if provided
            if artifact is not None:
                if "module_artifacts" not in self.state:
                    self.state["module_artifacts"] = {}
                self.state["module_artifacts"][module_name] = artifact
            else:
                logger.warning(
                    f"[Module:{module_name}] completed without artifact record"
                )
            
            self._save_state()
    
    def _load_module_output(self, module_name: str) -> dict:
        """加载模块输出（从断点恢复）"""
        path = f"v2/{module_name}_output.json"
        return self.blackboard.read_json(path)
    
    def _save_module_output(self, module_name: str, output: dict) -> str:
        """保存模块输出（原子写入）。失败时 raise，不吞异常。
        
        Returns:
            artifact_path: 保存后的文件路径
        """
        path = f"v2/{module_name}_output.json"
        self.blackboard.write(path, output)
        # Return the full path for verification
        artifact_path = os.path.join(
            str(self.blackboard.session_dir), path
        )
        return artifact_path
    
    def _save_and_validate_module_output(self, module_name: str, output: dict) -> dict:
        """保存模块输出并验证。返回 artifact 信息。
        
        失败时 raise，不返回。
        """
        # 1. 保存
        artifact_path = self._save_module_output(module_name, output)
        if not artifact_path:
            raise RuntimeError(f"模块 {module_name} 输出保存失败")
        
        # 2. Read back 验证
        try:
            with open(artifact_path) as f:
                saved_data = json.load(f)
        except Exception as e:
            raise RuntimeError(f"模块 {module_name} 输出保存后无法读回: {e}")
        
        # 3. Hash
        content_hash = hashlib.sha256(
            json.dumps(saved_data, sort_keys=True).encode()
        ).hexdigest()
        
        # 4. 基本 schema 检查（至少是 dict 且有内容）
        if not isinstance(saved_data, dict) or len(saved_data) == 0:
            raise RuntimeError(f"模块 {module_name} 输出为空或格式错误")
        
        return {
            "path": str(artifact_path),
            "sha256": content_hash,
            "validated": True
        }
    
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
    
    # === 降级策略已移除 ===
    # 原则：降级 = 失败。任何模块超时或异常，直接 raise，不产出空壳数据。
    
    # === 辅助方法 ===
    
    def _build_frozen_spec(self, user_input: str, config: dict, living_spec: dict = None) -> dict:
        """
        构建 Frozen Spec

        DEPRECATED: 此方法保留仅为向后兼容。
        内部改为从 living_spec 提取 REQ-ID index。
        新代码应直接使用 living_spec。
        """
        if living_spec:
            # 从 living_spec 构建 frozen_spec（通过 frozen_spec.py）
            try:
                from domains.solution_pro.frozen_spec import build_frozen_spec as _build_fs
                topic = config.get("topic", user_input) or living_spec.get("confirmed", {}).get("objective", "")
                return _build_fs(topic, config.get("constraints", []), living_spec)
            except Exception as e:
                logger.warning(f"Failed to build frozen_spec from living_spec: {e}")

        # Fallback: 旧逻辑
        return {
            "topic": config.get("topic", user_input),
            "solution_type": config.get("solution_type", "architecture"),
            "mode": config.get("mode", "standard"),
            "domain": config.get("domain", "backend_api"),
            "constraints": config.get("constraints", []),
            # [Cage P1-6] 降级标记
            "_degraded": True,
            "_degradation_reason": "Failed to build frozen_spec from living_spec, fallback to hardcoded minimal spec",
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
        unified_constraints = planning_output.get("unified_constraints", {})
        if isinstance(unified_constraints, list):
            constraints = unified_constraints
        elif isinstance(unified_constraints, dict):
            constraints = unified_constraints.get("constraints", [])
        else:
            constraints = []
        verification_checklist = planning_output.get("verification_checklist", {})
        if isinstance(verification_checklist, dict):
            checklist_items = verification_checklist.get("items", []) or verification_checklist.get("checklist", [])
        elif isinstance(verification_checklist, list):
            checklist_items = verification_checklist
        else:
            checklist_items = []
        return {
            "expert_count": len(planning_output.get("experts", [])),
            "constraint_count": len(constraints),
            "checklist_count": len(checklist_items),
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
    
    def _summarize_summary(self, summary_output) -> dict:
        """摘要 Summary 输出（健壮版）"""
        if not isinstance(summary_output, dict):
            return {"verdict": "UNKNOWN", "schema_version": "?", "degraded": True}
        return {
            "schema_version": summary_output.get("schema_version", "?"),
            "constraint_coverage": summary_output.get("constraint_coverage", {}),
            "verification_status": summary_output.get("verification_status", {}),
            "document_ref": summary_output.get("document_ref", ""),
            "degraded": summary_output.get("status") == "DEGRADED",
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
        """保存 Pipeline 指标"""
        try:
            self.blackboard.write("v2/pipeline_metrics.json", metrics)
        except Exception as e:
            logger.warning(f"Failed to save pipeline metrics: {e}")


def create_pipeline(blackboard, spawn_fn=None, config=None, version=None):
    """
    工厂函数：创建 Pipeline

    已归档，仅支持 三模块架构
    version 参数保留仅用于兼容旧版测试。
    """
    return MasterOrchestrator(blackboard, spawn_fn, config)
