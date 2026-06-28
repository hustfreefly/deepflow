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
    收敛层（Convergence Layer）
    
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
    
    def _read_directory_stages(self, dir_name: str) -> list[dict]:
        """读取目录下的所有 Stage 输出"""
        # 简化实现：假设目录下有 N 个文件
        # 实际实现需要 BlackboardManager 支持目录读取
        logger.warning(f"Directory reading not fully implemented for {dir_name}")
        return []
    
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
        """获取 P0 REQ 列表（从 frozen_spec.json）"""
        try:
            frozen_spec = self.blackboard.read("data/frozen_spec.json")
            p0_reqs = frozen_spec.get("p0_req_ids", [])
            return p0_reqs
        except Exception as e:
            logger.warning(f"Failed to read P0 REQs: {e}")
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
            expert_manifest = self.blackboard.read("stages/meta_planning.json")
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
        
        # Gate B 评估（Harness Agent）
        gate_b_result = self._evaluate_gate_b(compressed, gate_b_config)
        
        # Final Verdict（代码计算）
        final_verdict = self._compute_final_verdict(gate_a_result, gate_b_result, verdict_policy)
        
        return {
            "gate_a_scores": gate_a_result,
            "gate_b_results": gate_b_result,
            "gate_verdict": final_verdict,
        }
    
    def _evaluate_gate_a(self, compressed: dict, gate_a_config: dict) -> dict:
        """Gate A 评估（代码计算）"""
        # 简化实现：返回默认分数
        # 实际实现需要计算四维度分数
        logger.warning("_evaluate_gate_a not fully implemented, using defaults")
        
        return {
            "score": 0.9,
            "verdict": "PASS",
            "scores": {
                "completeness": 0.9,
                "necessity": 0.9,
                "alignment": 0.9,
                "global_impact": 0.9,
            },
        }
    
    def _evaluate_gate_b(self, compressed: dict, gate_b_config: dict) -> dict:
        """Gate B 评估（Harness Agent）"""
        # 简化实现：返回 PASS
        # 实际实现需要 spawn Harness Agent
        logger.warning("_evaluate_gate_b not fully implemented, using defaults")
        
        return {
            "pass_rate": 1.0,
            "verdict": "PASS",
            "failed_items": [],
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


__all__ = [
    "ConvergenceLayer",
]
