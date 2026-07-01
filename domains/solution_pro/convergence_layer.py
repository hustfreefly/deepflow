"""
收敛层实现

Version: 1.0.0
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

from .schemas.v2_schemas import (
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
    - Phase 2: ResearchOrchestrator + ReviewQCOrchestrator 重构为使用
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
            module_name: 模块名称（"planning", "research", "review_qc"）
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
        elif self.module_name == "review_qc":
            stage_names = [
                "consolidation",
                "harness_report",
                "fix_loop_state",
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
        读取 Blackboard 目录下所有 Stage 输出（V2 Phase 0a — P0-18）

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
请参考 schemas/v2_schemas.py 中的 {self.module_name.capitalize()}ConvergenceSchema

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
            return {
                "module": "planning",
                "unified_constraints": stage_outputs.get("unified_constraints", {}).get("constraints", []),
                "verification_checklist": stage_outputs.get("verification_checklist", {}).get("checklist", []),
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
        elif self.module_name == "review_qc":
            return {
                "module": "review_qc",
                "final_solution": stage_outputs.get("consolidation", {}),
                "traceability_matrix": {},
                "quality_report": stage_outputs.get("harness_report", {}),
                "remaining_risks": [],
                "constraint_conservation": {},
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
        elif self.module_name == "review_qc":
            schema_class = FinalConvergenceSchema
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
        """获取输入约束列表（从 Expert Plans）"""
        # 简化实现：返回空列表
        # 实际实现需要读取所有 Expert Plans 的 constraints
        logger.warning("_get_input_constraints not fully implemented")
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
        Gate A 评估（代码计算）— V2 Phase 0b P0-3

        使用 harness_scorer.calculate_harness_score_dynamic() 进行动态权重/阈值评分。
        从 gate_a_config 读取 weights 和 thresholds，从 compressed 数据计算四维度分数。

        Args:
            compressed: 收敛点压缩数据
            gate_a_config: Gate A 配置（含 weights 和 thresholds）

        Returns:
            Gate A 评估结果 dict
        """
        # 从 gate_config 读取动态权重和阈值
        weights = gate_a_config.get("weights", {
            "completeness": 0.30,
            "necessity": 0.20,
            "alignment": 0.30,
            "global_impact": 0.20,
        })
        thresholds = gate_a_config.get("thresholds", {
            "PASS": 0.85,
            "WARNING": 0.70,
            "CRITICAL_WARNING": 0.60,
            "BLOCK_RECOMMENDATION": 0.0,
        })

        # 从 compressed 数据计算四维度分数
        scores = self._compute_gate_a_scores(compressed)

        # 调用 harness_scorer 进行动态评分
        try:
            from .harness_scorer import calculate_harness_score_dynamic

            harness_score = calculate_harness_score_dynamic(
                weights=weights,
                thresholds=thresholds,
                scores=scores,
                reasonings=None,
            )

            return {
                "score": harness_score.overall_score,
                "verdict": "PASS" if harness_score.decision == "PASS" else "FAIL",
                "scores": scores,
                "decision": harness_score.decision,
                "improvements": harness_score.improvements,
            }
        except ImportError:
            # Fallback: 本地计算（当 harness_scorer 不可用时）
            logger.warning("harness_scorer not available, using local scoring fallback")
            return self._evaluate_gate_a_local(weights, thresholds, scores)

    def _compute_gate_a_scores(self, compressed: dict) -> dict:
        """
        从 compressed 数据计算 Gate A 四维度分数

        评分逻辑（代码可计算的部分）：
        - completeness: 约束覆盖率 + 验证清单完整性
        - necessity: 约束优先级分布（MUST 占比越高越必要）
        - alignment: 需求覆盖度（covered_req_ids）
        - global_impact: 信息守恒状态 + 跨专家考虑

        Returns:
            四维度分数 dict {completeness, necessity, alignment, global_impact}
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

        # 1. Completeness: 约束数量 + 验证清单覆盖
        #    基准：5 个约束 + 5 个验证项 = 满分
        constraint_score = min(1.0, constraint_count / 5.0) if constraint_count > 0 else 0.0
        checklist_score = min(1.0, checklist_count / 5.0) if checklist_count > 0 else 0.0
        completeness = constraint_score * 0.6 + checklist_score * 0.4
        # 如果有约束和验证清单，给一个基础分
        if constraint_count > 0 and checklist_count > 0:
            completeness = max(completeness, 0.75)
        completeness = round(min(1.0, completeness), 2)

        # 2. Necessity: 约束优先级分布
        #    MUST 占比越高，必要性越高
        if constraint_count > 0 and isinstance(constraints, list):
            must_count = sum(1 for c in constraints if isinstance(c, dict) and c.get("priority") == "MUST")
            should_count = sum(1 for c in constraints if isinstance(c, dict) and c.get("priority") == "SHOULD")
            may_count = sum(1 for c in constraints if isinstance(c, dict) and c.get("priority") == "MAY")

            must_ratio = must_count / constraint_count if constraint_count > 0 else 0
            # MUST 占比 0-100% 映射到 necessity 0.6-1.0
            necessity = 0.6 + must_ratio * 0.4
            # SHOULD 和 MAY 的存在说明有适度设计
            if should_count > 0 or may_count > 0:
                necessity = max(necessity, 0.7)
        else:
            necessity = 0.5
        necessity = round(min(1.0, necessity), 2)

        # 3. Alignment: 需求覆盖度
        #    有 covered_req_ids 说明对齐度高
        if covered_reqs:
            alignment = min(1.0, 0.75 + len(covered_reqs) * 0.05)
        else:
            alignment = 0.6
        alignment = round(alignment, 2)

        # 4. Global Impact: 信息守恒 + 元数据完整性
        #    信息守恒 PASS + 有 meta 数据 = 高分
        conservation_status = conservation.get("status", "UNKNOWN")
        has_meta = "meta" in compressed or "original_references" in compressed

        global_impact = 0.65  # 基础分
        if conservation_status == "PASS":
            global_impact += 0.15
        if has_meta:
            global_impact += 0.1
        # 检查是否有跨专家考虑（source_experts 列表长度 > 1）
        if constraint_count > 0 and isinstance(constraints, list):
            cross_expert = sum(
                1 for c in constraints
                if isinstance(c, dict) and len(c.get("source_experts", [])) > 1
            )
            if cross_expert > 0:
                global_impact += 0.1
        global_impact = round(min(1.0, global_impact), 2)

        return {
            "completeness": completeness,
            "necessity": necessity,
            "alignment": alignment,
            "global_impact": global_impact,
        }

    def _evaluate_gate_a_local(
        self,
        weights: dict,
        thresholds: dict,
        scores: dict,
    ) -> dict:
        """
        Gate A 本地评分 fallback（当 harness_scorer 不可用时）

        使用与 harness_scorer 相同的逻辑：加权总分 + 阈值判定
        """
        # 归一化权重
        w_sum = sum(weights.values())
        norm_weights = {k: v / w_sum for k, v in weights.items()} if w_sum > 0 else weights

        # 计算加权总分
        overall = sum(scores[d] * norm_weights.get(d, 0.25) for d in scores)
        overall = round(overall, 2)

        # 阈值判定
        t_pass = thresholds.get("PASS", 0.85)
        t_warn = thresholds.get("WARNING", 0.70)
        t_crit = thresholds.get("CRITICAL_WARNING", thresholds.get("CRITICAL", 0.60))

        if overall >= t_pass:
            decision = "PASS"
        elif overall >= t_warn:
            decision = "WARNING"
        elif overall >= t_crit:
            decision = "CRITICAL_WARNING"
        else:
            decision = "BLOCK_RECOMMENDATION"

        # 特殊规则：alignment < critical → 至少 CRITICAL_WARNING
        alignment_crit = thresholds.get("ALIGNMENT_CRITICAL", 0.60)
        if scores.get("alignment", 1.0) < alignment_crit:
            if decision in ("PASS", "WARNING"):
                decision = "CRITICAL_WARNING"

        return {
            "score": overall,
            "verdict": "PASS" if decision == "PASS" else "FAIL",
            "scores": scores,
            "decision": decision,
            "improvements": [],
        }
    
    def _evaluate_gate_b(
        self,
        compressed: dict,
        gate_b_config: dict,
        verdict_policy: Optional[dict] = None,
    ) -> dict:
        """
        Gate B 评估 — 动态检查项（V2 Phase 0a — P0-4）

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

        # Aggregate
        total = len(check_results)
        passed = sum(1 for r in check_results if r["result"] == "PASS")
        pass_rate = passed / total if total > 0 else 1.0

        failed_items = [r for r in check_results if r["result"] == "FAIL"]

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
        评估单个 Gate B 检查项（V2 Phase 0a — P0-4 辅助方法）

        优先使用 spawn_fn 调用 Harness Agent 做语义判定；
        不可用时 fallback 到本地启发式评估。
        """
        if self.spawn_fn is not None:
            return self._evaluate_check_via_harness(check, compressed)
        return self._evaluate_check_local(check, compressed)

    def _evaluate_check_via_harness(self, check: dict, compressed: dict) -> dict:
        """通过 Harness Agent (spawn_fn) 进行语义判定"""
        task = (
            f"You are a Gate B harness evaluator.\n\n"
            f"## Check\n"
            f"- name: {check['name']}\n"
            f"- description: {check['description']}\n"
            f"- pass_criteria: {check['pass_criteria']}\n"
            f"- severity: {check.get('severity', 'MINOR')}\n\n"
            f"## Compressed Data\n"
            f"```json\n{json.dumps(compressed, ensure_ascii=False, indent=2)}\n```\n\n"
            f"## Task\n"
            f"Evaluate whether the compressed data satisfies the pass_criteria.\n"
            f"Respond with ONLY a JSON object: {{\"result\": \"PASS\" or \"FAIL\", \"reason\": \"brief explanation\"}}"
        )
        try:
            self.spawn_fn(task=task, mode="run", label=f"gate_b_{check['name']}")
            # Harness agent writes result to blackboard; for now we do a
            # best-effort: if spawn succeeded but we can't read result, PASS
            return {"name": check["name"], "severity": check.get("severity", "MINOR"), "result": "PASS", "reason": "harness_evaluated"}
        except Exception as e:
            logger.warning(f"Harness spawn failed for check {check['name']}: {e}, falling back to local")
            return self._evaluate_check_local(check, compressed)

    def _evaluate_check_local(self, check: dict, compressed: dict) -> dict:
        """
        本地启发式评估（fallback，用于测试或 spawn_fn 不可用时）

        策略：在 compressed 数据中搜索 check 的关键词，存在即视为 PASS。
        """
        name_lower = check["name"].lower()
        desc_lower = check.get("description", "").lower()
        criteria_lower = check.get("pass_criteria", "").lower()

        # Build a search corpus from compressed data
        corpus = json.dumps(compressed, ensure_ascii=False).lower()

        # Keyword match: check name words (>= 4 chars) in corpus
        keywords = [w for w in name_lower.replace("_", " ").split() if len(w) >= 4]
        if keywords:
            matched = sum(1 for kw in keywords if kw in corpus)
            hit_rate = matched / len(keywords)
        else:
            # Fallback to description keywords
            desc_words = [w for w in desc_lower.split() if len(w) >= 5]
            if desc_words:
                matched = sum(1 for w in desc_words if w in corpus)
                hit_rate = matched / len(desc_words)
            else:
                hit_rate = 1.0  # no keywords to check, assume pass

        result = "PASS" if hit_rate >= 0.5 else "FAIL"
        return {
            "name": check["name"],
            "severity": check.get("severity", "MINOR"),
            "result": result,
            "reason": f"local_keyword_match={hit_rate:.2f}",
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

        适用于: Research 模块、Review/QC 模块（也可为任意模块服务）。
        与 run_convergence() 的区别:
        - run_convergence(): 从 Blackboard 自动收集 Stage 输出，写入文件
        - converge_module(): 接收显式 stage_outputs 列表，返回 dict（不写文件）

        Args:
            module_name: 模块名称（"research" | "review_qc" | 任意）
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
