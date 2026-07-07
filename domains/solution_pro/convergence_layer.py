"""
收敛层实现

Version: 2.0.0
Author: DeepFlow Solution Pro
Date: 2026-06-28

描述:
- 语义压缩（LLM）
- 契约验证（Pydantic）
- 信息守恒检查（代码）
- Gate A + Gate B 评估
- 生成收敛点文件

设计原则:
- 代码做格式转换和验证
- LLM 做语义压缩
- 不直接调用 OpenClaw（由主 Agent spawn）
"""

import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional
from datetime import datetime

from .schemas.schemas import (
    PlanningConvergenceSchema,
    ResearchConvergenceSchema,
    FinalConvergenceSchema,
    SemanticVerification,
)

logger = logging.getLogger(__name__)


class ConvergenceLayer:
    """
    ConvergenceLayer — 共享收敛层基础设施

    Phase 归属：
    - Phase 1: PlanningOrchestrator 使用内置 _generate_planning_convergence() 逻辑
      （不经过 ConvergenceLayer.run_convergence()）
    - Phase 2: ResearchOrchestrator + SummaryOrchestrator 重构为使用
      ConvergenceLayer.run_convergence() 作为共享收敛入口
    - Gate A/B 评估逻辑：Phase 1 在 ConvergenceLayer._evaluate_gates() 中已实现，
      Phase 2 扩展到所有模块复用

    当前状态：Gate A/B 真实逻辑已实现（Phase 0），可供所有模块调用。

    职责：
    1. 读取模块内所有 Stage 输出
    2. 语义压缩（LLM）
    3. 契约验证（Pydantic）
    4. 信息守恒检查（代码）
    5. Gate A + Gate B 评估
    6. 生成收敛点文件
    
    使用方法：
        layer = ConvergenceLayer(module_name="planning", blackboard=bb)
        convergence = layer.run_convergence()
    """
    
    def __init__(
        self,
        module_name: str,
        blackboard: Any,
        spawn_fn: Optional[Callable] = None,
    ):
        """
        初始化收敛层
        
        Args:
            module_name: 模块名称（"planning", "research", "summary"）
            blackboard: BlackboardManager 实例
            spawn_fn: spawn 函数（用于 spawn LLM 做语义压缩）
        """
        self.module_name = module_name
        self.blackboard = blackboard
        self.spawn_fn = spawn_fn
        
        logger.info(f"ConvergenceLayer initialized: {module_name}")
    
    def run_convergence(self) -> dict:
        """
        运行收敛层（主入口）
        
        Returns:
            收敛点数据（dict）
        """
        logger.info(f"Running convergence for module: {self.module_name}")
        
        # 1. 读取模块内所有 Stage 输出
        stage_outputs = self._collect_stage_outputs()
        
        # 2. 语义压缩（LLM）
        compressed = self._compress_semantically(stage_outputs)
        
        # 2.5 字段归一化（代码做确定性工作）
        if self.module_name == "planning":
            compressed = self._normalize_planning_constraints(compressed)
        
        # 3. 契约验证（Pydantic）
        self._validate_contract(compressed)
        
        # 4. 信息守恒检查（代码）
        conservation = self._check_information_conservation(compressed)
        compressed["information_conservation"] = conservation
        
        # 5. Gate A + Gate B 评估
        gate_results = self._evaluate_gates(compressed)
        compressed.update(gate_results)
        
        # 6. 添加元数据
        compressed["schema_version"] = "1.0.0"
        compressed["timestamp"] = datetime.now().isoformat()
        compressed["module"] = self.module_name
        
        # 7. 写入收敛点文件
        convergence_path = f"{self.module_name}_convergence.json"
        self.blackboard.write(convergence_path, compressed)
        
        logger.info(f"Convergence completed: {convergence_path}")
        return compressed
    
    def _normalize_planning_constraints(self, compressed: dict) -> dict:
        """
        归一化 Planning 约束字段名。
        
        LLM 可能输出 id/constraint_id、content/description 等不同字段名。
        代码做归一化（确定性工作），不依赖 LLM 精确遵守字段名。
        这是 AI Native 的容错设计：接受 LLM 的自然输出，代码处理格式差异。
        """
        constraints = compressed.get("unified_constraints", [])
        normalized = []
        
        for c in constraints:
            if not isinstance(c, dict):
                normalized.append(c)
                continue
            
            nc = dict(c)  # copy
            
            # 归一化 ID 字段
            if "constraint_id" not in nc and "id" in nc:
                nc["constraint_id"] = nc.pop("id")
            
            # 归一化描述字段
            if "description" not in nc and "content" in nc:
                nc["description"] = nc.pop("content")
            
            # 确保 relevant_experts 存在
            if "relevant_experts" not in nc:
                nc["relevant_experts"] = []
            
            # 确保 covered_req_ids 存在
            if "covered_req_ids" not in nc:
                nc["covered_req_ids"] = []
            
            normalized.append(nc)
        
        compressed["unified_constraints"] = normalized
        return compressed
    
    def _collect_stage_outputs(self) -> dict:
        """收集模块内所有 Stage 输出"""
        stage_outputs = {}
        
        # 根据模块名确定需要收集的 Stage
        if self.module_name == "planning":
            stage_names = [
                "meta_planning",
                "expert_plans",  # 目录，需要特殊处理
                "convergence_planning",
                "unified_constraints",
                "verification_checklist",
            ]
        elif self.module_name == "research":
            stage_names = [
                "research_experts",  # 目录
                "research_consolidator",
                "architecture",
                "detailed_design",
            ]
        else:
            raise ValueError(f"Unknown module: {self.module_name}")
        
        # 收集每个 Stage 的输出
        for stage_name in stage_names:
            try:
                if stage_name in ["expert_plans", "research_experts"]:
                    # 目录 Stage：读取目录下所有文件
                    outputs = self._read_directory_stages(stage_name)
                    stage_outputs[stage_name] = outputs
                else:
                    # 单个文件 Stage
                    path = f"stages/{stage_name}.json"
                    output = self.blackboard.read(path)
                    stage_outputs[stage_name] = output
            except Exception as e:
                logger.warning(f"Failed to read stage {stage_name}: {e}")
                stage_outputs[stage_name] = None
        
        logger.info(f"Collected {len(stage_outputs)} stage outputs")
        return stage_outputs
    
    def _read_directory_stages(self, dir_name: str) -> dict[str, dict]:
        """
        读取 Blackboard 目录下所有 Stage 输出

        遍历 stages/{dir_name}/ 下所有 .json 文件，使用 BlackboardManager API
        （read_json）读取文件内容，返回 {stage_name: stage_output} dict。

        Args:
            dir_name: 目录名（如 "expert_plans", "research_experts"）

        Returns:
            {stage_name: stage_output} 字典。文件不存在或解析错误时记录警告并跳过。
        
        Note:
            使用 blackboard.read_json() 读取文件（BlackboardManager API），
            仅使用文件系统 API 列出目录内容（list_dir / Path.glob），
            因为 BlackboardManager 不提供子目录列表功能。
        """
        results: dict[str, dict] = {}

        # 获取 session 目录路径（使用 BlackboardManager API）
        try:
            session_dir = self.blackboard.get_session_dir()
        except AttributeError:
            # Fallback: blackboard 没有 get_session_dir() 时尝试 _session_dir
            session_dir = getattr(self.blackboard, "_session_dir", None)
            if session_dir is None:
                logger.warning(f"Cannot resolve session dir for directory read: {dir_name}")
                return results

        stage_dir = Path(session_dir) / "stages" / dir_name
        if not stage_dir.is_dir():
            logger.warning(f"Directory does not exist: {stage_dir}")
            return results

        # 遍历目录中的 JSON 文件，使用 BlackboardManager API 读取
        for json_file in sorted(stage_dir.glob("*.json")):
            stage_name = json_file.stem  # e.g. "security" from "security.json"
            try:
                # 构建相对于 session_dir 的路径，使用 BlackboardManager.read_json()
                relative_path = f"stages/{dir_name}/{json_file.name}"
                data = self.blackboard.read_json(relative_path)
                if data is not None:
                    results[stage_name] = data
                else:
                    logger.warning(f"read_json returned None for {relative_path}")
            except Exception as e:
                logger.warning(f"Failed to read {json_file} via BlackboardManager: {e}")
                continue

        logger.info(f"Read {len(results)} stage files from {dir_name}/")
        return results
    
    def _compress_semantically(self, stage_outputs: dict) -> dict:
        """
        语义压缩（LLM）
        
        Args:
            stage_outputs: 所有 Stage 输出
        
        Returns:
            压缩后的数据（dict）
        """
        logger.info("Compressing semantically (LLM)")
        
        # 构建 LLM task
        task = self._build_compression_task(stage_outputs)
        
        # Spawn LLM（如果提供了 spawn_fn）
        if self.spawn_fn:
            result = self.spawn_fn(
                task=task,
                mode="run",
                label=f"convergence_{self.module_name}",
            )
            
            # 读取 LLM 输出
            output_path = f"stages/convergence_{self.module_name}.json"
            compressed = self.blackboard.read(output_path)
        else:
            # 本地压缩（简化实现，用于测试）
            compressed = self._compress_local(stage_outputs)
        
        return compressed
    
    def _build_compression_task(self, stage_outputs: dict) -> str:
        """构建语义压缩 task"""
        task = f"""
你是一个收敛层压缩器。你的任务是将模块内的多个 Stage 输出压缩为一个收敛点文件。

## 模块名称
{self.module_name}

## Stage 输出
```json
{json.dumps(stage_outputs, indent=2, ensure_ascii=False)}
```

## 压缩原则
1. 保留关键信息（P0 REQ、约束、决策、风险）
2. 合并重复内容（语义去重）
3. 解决冲突（记录 conflicts_resolved）
4. 添加 original_references（引用原始文件路径）

## 输出 Schema
请参考 schemas/schemas.py 中的 {self.module_name.capitalize()}ConvergenceSchema

## 输出路径
stages/convergence_{self.module_name}.json

请完成压缩并将输出写入指定路径。
"""
        return task
    
    def _compress_local(self, stage_outputs: dict) -> dict:
        """本地压缩（简化实现，用于测试）"""
        logger.warning("Running local compression (test mode)")
        
        # 根据模块名返回简化结构
        if self.module_name == "planning":
            unified_constraints = stage_outputs.get("unified_constraints", {})
            if isinstance(unified_constraints, list):
                constraints = unified_constraints
            elif isinstance(unified_constraints, dict):
                constraints = unified_constraints.get("constraints", [])
            else:
                constraints = []
            verification_checklist = stage_outputs.get("verification_checklist", {})
            if isinstance(verification_checklist, dict):
                checklist = verification_checklist.get("checklist", [])
            elif isinstance(verification_checklist, list):
                checklist = verification_checklist
            else:
                checklist = []
            return {
                "module": "planning",
                "unified_constraints": constraints,
                "verification_checklist": checklist,
                "planning_summary": "本地压缩摘要（测试模式）",
                "expert_divergence": [],
                "original_references": {},
                "semantic_verification": {
                    "verdict": "EQUIVALENT",
                    "confidence": 1.0,
                    "divergences": [],
                },
            }
        elif self.module_name == "research":
            return {
                "module": "research",
                "research_summary": "本地压缩摘要（测试模式）",
                "key_findings": [],
                "design_decisions": [],
                "open_questions": [],
                "architecture": stage_outputs.get("architecture", {}),
                "detailed_design": stage_outputs.get("detailed_design", {}),
                "original_references": {},
                "semantic_verification": {
                    "verdict": "EQUIVALENT",
                    "confidence": 1.0,
                    "divergences": [],
                },
            }
        else:
            raise ValueError(f"Unknown module: {self.module_name}")
    
    def _validate_contract(self, compressed: dict):
        """契约验证（Pydantic）"""
        logger.info("Validating contract (Pydantic)")
        
        # 根据模块名选择 Schema
        if self.module_name == "planning":
            schema_class = PlanningConvergenceSchema
        elif self.module_name == "research":
            schema_class = ResearchConvergenceSchema
        else:
            raise ValueError(f"Unknown module: {self.module_name}")
        
        # 验证
        try:
            schema_class(**compressed)
            logger.info("Contract validation passed")
        except Exception as e:
            logger.error(f"Contract validation failed: {e}")
            raise ValueError(f"Contract validation failed: {e}")
    
    def _check_information_conservation(self, compressed: dict) -> dict:
        """
        信息守恒检查（代码）
        
        Returns:
            信息守恒检查结果（dict）
        """
        logger.info("Checking information conservation")
        
        conservation = {
            "status": "PASS",
            "checks": [],
        }
        
        # 检查 1: P0 REQ 覆盖
        p0_reqs = self._get_p0_reqs()
        covered_reqs = compressed.get("covered_req_ids", [])
        
        if p0_reqs:
            missing_reqs = [req for req in p0_reqs if req not in covered_reqs]
            if missing_reqs:
                conservation["status"] = "FAIL"
                conservation["checks"].append({
                    "check": "p0_req_coverage",
                    "status": "FAIL",
                    "message": f"Missing P0 REQs: {missing_reqs}",
                })
            else:
                conservation["checks"].append({
                    "check": "p0_req_coverage",
                    "status": "PASS",
                    "message": f"All {len(p0_reqs)} P0 REQs covered",
                })
        
        # 检查 2: 约束覆盖率
        input_constraints = self._get_input_constraints()
        output_constraints = compressed.get("unified_constraints", [])
        
        if input_constraints:
            coverage_rate = len(output_constraints) / len(input_constraints)
            if coverage_rate < 0.8:
                conservation["status"] = "FAIL"
                conservation["checks"].append({
                    "check": "constraint_coverage",
                    "status": "FAIL",
                    "message": f"Constraint coverage {coverage_rate:.2%} < 80%",
                })
            else:
                conservation["checks"].append({
                    "check": "constraint_coverage",
                    "status": "PASS",
                    "message": f"Constraint coverage {coverage_rate:.2%}",
                })
        
        logger.info(f"Information conservation: {conservation['status']}")
        return conservation
    
    def _get_p0_reqs(self) -> list[str]:
        """获取 P0 REQ 列表（优先 living_spec，fallback frozen_spec）"""
        # 优先从 living_spec 的 requirement_index 获取
        try:
            living_spec = self.blackboard.read_json("data/living_spec.json")
            if living_spec and isinstance(living_spec, dict):
                req_index = living_spec.get("requirement_index", [])
                if req_index:
                    return [r["id"] for r in req_index if isinstance(r, dict) and r.get("priority") == "P0"]
        except Exception:
            pass
        # Fallback: frozen_spec
        try:
            frozen_spec = self.blackboard.read_json("data/frozen_spec.json")
            if frozen_spec:
                return frozen_spec.get("p0_req_ids", [])
        except Exception:
            pass
        return []
    
    def _get_input_constraints(self) -> list[str]:
        """获取输入约束列表（从 Expert Plans 目录提取所有 constraints 描述）"""
        try:
            import os
            expert_plans_dir = self.blackboard.session_dir / "stages" / "expert_plans"
            if not expert_plans_dir.exists():
                logger.info(f"No expert_plans directory found at {expert_plans_dir}")
                return []
            
            constraints = []
            for f in sorted(expert_plans_dir.glob("*.json")):
                try:
                    plan = self.blackboard.read_json(f"stages/expert_plans/{f.name}")
                    if not isinstance(plan, dict):
                        continue
                    plan_constraints = plan.get("constraints", [])
                    if isinstance(plan_constraints, list):
                        for c in plan_constraints:
                            if isinstance(c, dict):
                                desc = c.get("description", "")
                                if desc:
                                    constraints.append(desc)
                except Exception as e:
                    logger.warning(f"Failed to read expert plan {f.name}: {e}")
            
            logger.info(f"Loaded {len(constraints)} constraints from {len(list(expert_plans_dir.glob('*.json')))} expert plans")
            return constraints
        except Exception as e:
            logger.warning(f"Failed to read expert_plans directory: {e}")
            return []
    
    def _evaluate_gates(self, compressed: dict) -> dict:
        """
        Gate A + Gate B 评估
        
        Returns:
            Gate 评估结果（dict）
        """
        logger.info("Evaluating gates")
        
        # 读取 Gate 配置（从 meta_planning 输出）
        try:
            expert_manifest = self.blackboard.read_json("stages/meta_planning.json")
            gate_a_config = expert_manifest.get("gate_a", {})
            gate_b_config = expert_manifest.get("gate_b", {})
            verdict_policy = expert_manifest.get("verdict_policy", {})
        except Exception as e:
            logger.warning(f"Failed to load Gate config: {e}, using defaults")
            gate_a_config = {}
            gate_b_config = {}
            verdict_policy = {}
        
        # Gate A 评估（代码计算）
        gate_a_result = self._evaluate_gate_a(compressed, gate_a_config)
        
        # Gate B 评估（Harness Agent / local fallback）
        gate_b_result = self._evaluate_gate_b(compressed, gate_b_config, verdict_policy)
        
        # Final Verdict（代码计算）
        final_verdict = self._compute_final_verdict(gate_a_result, gate_b_result, verdict_policy)
        
        return {
            "gate_a_scores": gate_a_result,
            "gate_b_results": gate_b_result,
            "gate_verdict": final_verdict,
        }
    
    def _evaluate_gate_a(self, compressed: dict, gate_a_config: dict) -> dict:
        """
        Gate A 评估（确定性部分）。

        AI Native 原则：代码只计算原始指标 + 结构性检查。
        语义评分由 Layer 2 LLM Judge 完成。

        Args:
            compressed: 收敛点压缩数据
            gate_a_config: Gate A 配置（保留用于向后兼容）

        Returns:
            Gate A 评估结果 dict（含 raw_metrics，无语义分数）
        """
        # 从 compressed 数据计算原始指标
        scores = self._compute_gate_a_scores(compressed)

        # 结构性判定：有约束 + 有验证清单 = structural_pass
        structural_pass = scores.get("structural_pass", False)
        raw_metrics = scores.get("raw_metrics", {})

        return {
            "score": 0.0,  # 无语义分数
            "verdict": "PASS" if structural_pass else "FAIL",
            "raw_metrics": raw_metrics,
            "structural_pass": structural_pass,
            "decision": "STRUCTURAL_PASS" if structural_pass else "STRUCTURAL_FAIL",
            "semantic_scoring": "SKIPPED — requires LLM Judge (Layer 2)",
            "improvements": [],
        }

    def _compute_gate_a_scores(self, compressed: dict) -> dict:
        """
        计算 Gate A 原始指标（确定性部分）。

        AI Native 原则：代码只输出原始指标，不做语义评分。
        语义评分由 Layer 2 LLM Judge 完成。

        Returns:
            {
                "raw_metrics": {原始指标 dict},
                "structural_pass": bool,
            }
        """
        # 提取关键数据
        constraints = compressed.get("unified_constraints", [])
        checklist = compressed.get("verification_checklist", [])
        covered_reqs = compressed.get("covered_req_ids", [])
        conservation = compressed.get("information_conservation", {})

        # 处理 constraints 可能的嵌套结构
        if isinstance(constraints, dict):
            constraints = constraints.get("constraints", [])
        if isinstance(checklist, dict):
            checklist = checklist.get("checklist", [])

        constraint_count = len(constraints) if isinstance(constraints, list) else 0
        checklist_count = len(checklist) if isinstance(checklist, list) else 0

        # MUST 计数
        must_count = 0
        if constraint_count > 0 and isinstance(constraints, list):
            must_count = sum(
                1 for c in constraints
                if isinstance(c, dict) and c.get("priority") == "MUST"
            )

        # 跨专家约束计数
        cross_expert_count = 0
        if constraint_count > 0 and isinstance(constraints, list):
            cross_expert_count = sum(
                1 for c in constraints
                if isinstance(c, dict) and len(c.get("source_experts", [])) > 1
            )

        return {
            "raw_metrics": {
                "constraint_count": constraint_count,
                "must_count": must_count,
                "checklist_count": checklist_count,
                "covered_req_count": len(covered_reqs or []),
                "total_req_count": len(compressed.get("all_req_ids", []) or []),
                "conservation_status": conservation.get("status", "UNKNOWN"),
                "has_meta": "meta" in compressed or "original_references" in compressed,
                "cross_expert_count": cross_expert_count,
            },
            "structural_pass": constraint_count > 0 and checklist_count > 0,
        }

    def _evaluate_gate_a_local(
        self,
        weights: dict,
        thresholds: dict,
        scores: dict,
    ) -> dict:
        """
        Gate A 本地评估 fallback（当 harness_scorer 不可用时）。

        AI Native 原则：代码不做语义评分。只基于 raw_metrics 做结构性检查，
        语义评分留给 Layer 2 LLM Judge。
        """
        raw = scores.get("raw_metrics", {})
        structural_pass = scores.get("structural_pass", False)

        # 结构性检查：有约束 + 有验证清单 = structural_pass
        # 不做语义评分，只报告原始指标 + 结构性判定
        return {
            "score": 0.0,  # 无语义分数
            "verdict": "PASS" if structural_pass else "FAIL",
            "raw_metrics": raw,
            "decision": "STRUCTURAL_PASS" if structural_pass else "STRUCTURAL_FAIL",
            "semantic_scoring": "SKIPPED — requires LLM Judge (Layer 2)",
            "improvements": [],
        }
    
    def _evaluate_gate_b(
        self,
        compressed: dict,
        gate_b_config: dict,
        verdict_policy: Optional[dict] = None,
    ) -> dict:
        """
        Gate B 评估 — 动态检查项

        对 gate_b_config 中的每项 dynamic_check 进行语义判定：
        - 优先通过 spawn_fn 调用 Harness Agent 进行 LLM 语义判定
        - spawn_fn 不可用时 fallback 到本地启发式评估
        - CRITICAL 项全部必须通过 + 整体通过率 ≥ min_gate_b_pass_rate

        Args:
            compressed: 收敛点压缩数据
            gate_b_config: Gate B 配置（含 dynamic_checks 列表）
            verdict_policy: 判定策略（含 min_gate_b_pass_rate，默认 0.8）

        Returns:
            {pass_rate: float, verdict: str, failed_items: list[dict]}
        """
        dynamic_checks = gate_b_config.get("dynamic_checks", [])
        if not dynamic_checks:
            logger.info("Gate B: no dynamic_checks configured, auto-PASS")
            return {"pass_rate": 1.0, "verdict": "PASS", "failed_items": []}

        min_pass_rate = (verdict_policy or {}).get("min_gate_b_pass_rate", 0.8)

        # Evaluate each check
        check_results: list[dict] = []
        for check in dynamic_checks:
            result = self._evaluate_single_gate_b_check(check, compressed)
            check_results.append(result)

        # Aggregate — SKIPPED items excluded from total (no semantic judgment made)
        evaluated = [r for r in check_results if r["result"] != "SKIPPED"]
        total = len(evaluated)
        passed = sum(1 for r in evaluated if r["result"] == "PASS")
        pass_rate = passed / total if total > 0 else 1.0

        failed_items = [r for r in evaluated if r["result"] == "FAIL"]

        # CRITICAL 项必须全部通过
        critical_failed = [
            r for r in failed_items if r.get("severity") == "CRITICAL"
        ]

        # Verdict 判定
        if critical_failed:
            verdict = "FAIL"
        elif pass_rate < min_pass_rate:
            verdict = "FAIL"
        else:
            verdict = "PASS"

        logger.info(
            f"Gate B: {passed}/{total} passed (rate={pass_rate:.2f}, "
            f"min={min_pass_rate:.2f}), verdict={verdict}, "
            f"critical_failures={len(critical_failed)}"
        )

        return {
            "pass_rate": round(pass_rate, 4),
            "verdict": verdict,
            "failed_items": [
                {"name": r["name"], "severity": r.get("severity", "MINOR"), "reason": r.get("reason", "")}
                for r in failed_items
            ],
        }

    def _evaluate_single_gate_b_check(self, check: dict, compressed: dict) -> dict:
        """
        评估单个 Gate B 检查项

        优先使用 spawn_fn 调用 Harness Agent 做语义判定。
        - spawn_fn 不存在（测试环境）→ SKIP
        - spawn_fn 存在但调用失败 → hard raise（生产零容忍）
        """
        if self.spawn_fn is not None:
            return self._evaluate_check_via_harness(check, compressed)
        # 测试环境：无 spawn_fn，明确标记 SKIP（不做关键词匹配假阳性）
        check_name = check["name"]
        logger.info(f"Gate B check '{check_name}': SKIP (no spawn_fn in test environment)")
        return {"name": check_name, "severity": check.get("severity", "MINOR"), "result": "SKIP", "reason": "no_spawn_fn"}

    def _evaluate_check_via_harness(self, check: dict, compressed: dict) -> dict:
        """通过 Harness Agent (spawn_fn) 进行语义判定。

        spawn 后等待结果文件写入 blackboard，读取并解析 verdict。
        文件不存在或 verdict 非 PASS → 返回 FAIL。
        """
        check_name = check["name"]
        output_path = f"stages/gate_b/{check_name}.json"

        task = (
            f"You are a Gate B harness evaluator.\n\n"
            f"## Check\n"
            f"- name: {check_name}\n"
            f"- description: {check['description']}\n"
            f"- pass_criteria: {check['pass_criteria']}\n"
            f"- severity: {check.get('severity', 'MINOR')}\n\n"
            f"## Compressed Data\n"
            f"```json\n{json.dumps(compressed, ensure_ascii=False, indent=2)}\n```\n\n"
            f"## Task\n"
            f"Evaluate whether the compressed data satisfies the pass_criteria.\n"
            f"Write your result as a JSON object to the blackboard path: {output_path}\n"
            f"The JSON must have format: {{\"result\": \"PASS\" or \"FAIL\", \"reason\": \"brief explanation\"}}"
        )
        try:
            self.spawn_fn(task=task, mode="run", label=f"gate_b_{check_name}")
        except Exception as e:
            # 生产环境：spawn_fn 存在但调用失败 → hard raise（与 "No silent fallback" 哲学一致）
            raise RuntimeError(
                f"Gate B harness spawn failed for check '{check_name}': {e}. "
                f"Production requires LLM semantic judgment — keyword matching fallback is disabled."
            ) from e

        # 等待并读取结果
        result_data = self._wait_for_gate_b_result(output_path, check_name)
        if result_data is None:
            logger.warning(f"Gate B harness did not produce result for '{check_name}' at {output_path}, marking FAIL")
            return {"name": check_name, "severity": check.get("severity", "MINOR"), "result": "FAIL", "reason": "harness_no_output"}

        verdict = result_data.get("result", "FAIL")
        return {
            "name": check_name,
            "severity": check.get("severity", "MINOR"),
            "result": verdict if verdict in ("PASS", "FAIL") else "FAIL",
            "reason": result_data.get("reason", "harness_evaluated"),
        }

    def _wait_for_gate_b_result(self, output_path: str, check_name: str, timeout: float = 120.0) -> Optional[dict]:
        """轮询等待 Gate B harness 结果文件出现，解析并返回。超时返回 None。"""
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data = self.blackboard.read_json(output_path)
                if data and isinstance(data, dict):
                    return data
            except Exception:
                pass
            time.sleep(2.0)
        return None

    def _evaluate_check_local(self, check: dict, compressed: dict) -> dict:
        """
        本地评估 fallback（当 spawn_fn 不可用时）。

        AI Native 原则：代码不做语义判断。无 LLM Judge 时输出 SKIPPED，
        不伪造 PASS/FAIL。结构性检查（字段存在性等）仍可执行。
        """
        check_name = check["name"]
        # 结构性检查：验证 compressed 中存在相关字段（确定性检查）
        structural_ok = check_name in json.dumps(compressed, ensure_ascii=False)
        return {
            "name": check_name,
            "severity": check.get("severity", "MINOR"),
            "result": "SKIPPED",
            "reason": "No LLM judge available — semantic evaluation requires LLM",
            "structural_check": structural_ok,
        }
    
    def _compute_final_verdict(
        self,
        gate_a_result: dict,
        gate_b_result: dict,
        verdict_policy: dict,
    ) -> dict:
        """计算 Final Verdict（代码）"""
        gate_a_verdict = gate_a_result.get("verdict", "FAIL")
        gate_b_verdict = gate_b_result.get("verdict", "FAIL")
        
        # Final Verdict = Gate A PASS ∧ Gate B PASS
        if gate_a_verdict == "PASS" and gate_b_verdict == "PASS":
            final_verdict = "PASS"
        else:
            final_verdict = "FAIL"
        
        return {
            "final_verdict": final_verdict,
            "gate_a": gate_a_verdict,
            "gate_b": gate_b_verdict,
        }

    # ─────────────────────────────────────────────────────────────
    # Phase 2 新增: converge_module() 通用模块收敛方法
    # ─────────────────────────────────────────────────────────────

    def converge_module(
        self,
        module_name: str,
        stage_outputs: list[dict],
        contract: Optional[dict] = None,
    ) -> dict:
        """
        通用模块收敛方法 — Phase 2 新增

        适用于: Research 模块、Summary 模块（也可为任意模块服务）。
        与 run_convergence() 的区别:
        - run_convergence(): 从 Blackboard 自动收集 Stage 输出，写入文件
        - converge_module(): 接收显式 stage_outputs 列表，返回 dict（不写文件）

        Args:
            module_name: 模块名称（"research" | "summary" | 任意）
            stage_outputs: 该模块的所有 stage 输出列表
            contract: 可选的契约约束（影响 Gate A/B 评估）

        Returns:
            convergence dict，包含 gate_a、gate_b、overall_verdict

        流程:
        1. 收集所有 stage 输出
        2. 压缩信息（规则压缩 / LLM 总结）
        3. Gate A 评估（动态权重）
        4. Gate B 评估（动态检查项）
        5. 生成 convergence dict
        """
        logger.info(f"converge_module: module={module_name}, stages={len(stage_outputs)}")

        # 1. 收集 stage 输出
        collected = self._collect_provided_stage_outputs(stage_outputs)

        # 2. 压缩信息
        compressed = self._compress_outputs(collected, module_name)

        # 3. Gate A 评估（复用已有方法，contract 作为 gate_a_config）
        gate_a_result = self._evaluate_gate_a(compressed, contract or {})

        # 4. Gate B 评估（复用已有方法，contract 作为 gate_b_config）
        gate_b_result = self._evaluate_gate_b(compressed, contract or {})

        # 5. 生成 convergence
        convergence = self._generate_module_convergence(
            module_name, collected, gate_a_result, gate_b_result
        )

        logger.info(
            f"converge_module done: module={module_name}, "
            f"verdict={convergence.get('overall_verdict', 'UNKNOWN')}"
        )
        return convergence

    def _collect_provided_stage_outputs(self, stage_outputs: list[dict]) -> dict:
        """收集并整理显式提供的 stage 输出列表（Phase 2 新增）"""
        collected = {
            "total_stages": len(stage_outputs),
            "stages": [],
        }

        for i, output in enumerate(stage_outputs):
            collected["stages"].append({
                "stage_index": i,
                "output": output,
            })

        return collected

    def _compress_outputs(self, collected: dict, module_name: str) -> dict:
        """
        压缩 stage 输出为结构化摘要（Phase 2 新增）

        规则压缩：提取 findings / constraints / risks 等关键字段。
        若需 LLM 语义压缩，应使用 run_convergence() 路径。
        """
        compressed = {
            "module": module_name,
            "total_stages": collected["total_stages"],
            "key_findings": [],
            "constraints": [],
            "risks": [],
        }

        for stage in collected["stages"]:
            output = stage["output"]
            if not isinstance(output, dict):
                continue

            # 提取 findings（取前 5 个避免膨胀）
            if "findings" in output and isinstance(output["findings"], list):
                compressed["key_findings"].extend(output["findings"][:5])

            # 提取 constraints
            if "constraints" in output and isinstance(output["constraints"], list):
                compressed["constraints"].extend(output["constraints"])

            # 提取 risks
            if "risks" in output and isinstance(output["risks"], list):
                compressed["risks"].extend(output["risks"])

        return compressed

    def _generate_module_convergence(
        self,
        module_name: str,
        collected: dict,
        gate_a_result: dict,
        gate_b_result: dict,
    ) -> dict:
        """生成模块收敛结果 dict（Phase 2 新增）"""
        convergence = {
            "schema_version": f"{module_name}_v2.0",
            "module": module_name,
            "status": "COMPLETE",
            "stage_count": collected["total_stages"],
            "gate_a": gate_a_result,
            "gate_b": gate_b_result,
            "overall_verdict": self._combine_gate_verdicts(gate_a_result, gate_b_result),
        }

        return convergence

    def _combine_gate_verdicts(self, gate_a: dict, gate_b: dict) -> str:
        """组合 Gate A 和 Gate B 的判定（Phase 2 新增）"""
        gate_a_verdict = gate_a.get("verdict", "FAIL")
        gate_b_verdict = gate_b.get("verdict", "FAIL")

        if gate_a_verdict == "PASS" and gate_b_verdict == "PASS":
            return "PASS"
        else:
            return "FAIL"


__all__ = [
    "ConvergenceLayer",
]
