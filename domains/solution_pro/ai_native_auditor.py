"""
AI Native 自审工具 — 独立于 ComplianceChecker 的审计

设计理念：
- ComplianceChecker 审计"输出格式合规性"
- AINativeAuditor 审计"架构决策是否 AI Native"
- 两者独立，避免循环论证

审计维度：
1. 语义任务是否用 LLM（而非 re.match/if-elif）
2. 验证是否有 Layer 2（LLM 语义验证）
3. Prompt 是否是契约（五要素完整）
4. 错误恢复是否用 LLM 诊断（而非纯 try/except）
5. 是否有自欺信号（"这个简单不需要"等）
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class AINativeAuditor:
    """
    AI Native 审计器 — 独立于被测系统
    
    使用方法：
        auditor = AINativeAuditor()
        report = auditor.audit_pipeline(pipeline_result)
        print(report["verdict"], report["score"])
    """
    
    # AI Native 反模式检测规则
    ANTI_PATTERNS = {
        "regex_classification": {
            "pattern": r're\.(match|search|compile|findall).*classif',
            "description": "用正则做语义分类",
            "severity": "HIGH",
        },
        "elif_chains": {
            "pattern": r'elif\s+.*(?:==|in|is)\s+.*:\s*\n\s*(?:elif|else)',
            "description": "3+ elif 分支做内容判断",
            "severity": "MEDIUM",
        },
        "hardcoded_mapping": {
            "pattern": r'(?:mapping|lookup|dict)\s*=\s*\{[^}]{200,}\}',
            "description": "硬编码映射表",
            "severity": "MEDIUM",
        },
        "human_time_scale": {
            "pattern": r'(?:P[0-3]|后续|下周|以后|延后).*(?:做|实施|优化)',
            "description": "人类时间尺度思维",
            "severity": "LOW",
        },
        "self_deception": {
            "pattern": r'(?:这个比较简单|不需要|先跳过|我判断不需要)',
            "description": "自欺信号",
            "severity": "HIGH",
        },
    }
    
    def __init__(self, llm_judge_fn=None):
        self.llm_judge_fn = llm_judge_fn
    
    def audit_pipeline(self, pipeline_result: dict, code_context: str = None) -> dict:
        """
        审计 Pipeline 输出的 AI Native 合规性
        
        Args:
            pipeline_result: MasterOrchestrator.run() 的输出
            code_context: 可选的代码上下文（用于反模式检测）
        
        Returns:
            {
                "verdict": "PASS" | "WARNING" | "FAIL",
                "score": 0.75,
                "dimensions": {...},
                "anti_patterns": [...],
                "recommendations": [...],
            }
        """
        dimensions = {}
        anti_patterns = []
        recommendations = []
        
        # 维度 1: 语义任务是否用 LLM
        d1 = self._audit_semantic_tasks(pipeline_result)
        dimensions["semantic_tasks_use_llm"] = d1
        
        # 维度 2: 验证是否有 Layer 2
        d2 = self._audit_layer2_validation(pipeline_result)
        dimensions["layer2_validation"] = d2
        
        # 维度 3: Prompt 是否是契约
        d3 = self._audit_prompt_contracts(pipeline_result)
        dimensions["prompt_contracts"] = d3
        
        # 维度 4: 错误恢复
        d4 = self._audit_error_recovery(pipeline_result)
        dimensions["error_recovery"] = d4
        
        # 维度 5: 反模式检测（如果有代码上下文）
        if code_context:
            detected = self._detect_anti_patterns(code_context)
            anti_patterns = detected
            d5_score = max(0, 1.0 - len([d for d in detected if d["severity"] == "HIGH"]) * 0.3)
            dimensions["no_anti_patterns"] = {"score": d5_score, "details": detected}
        else:
            dimensions["no_anti_patterns"] = {"score": 0.5, "details": "No code context provided"}
        
        # 综合评分
        scores = [d.get("score", 0) for d in dimensions.values() if isinstance(d, dict)]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        # 三级判定
        if avg_score >= 0.8:
            verdict = "PASS"
        elif avg_score >= 0.5:
            verdict = "WARNING"
        else:
            verdict = "FAIL"
        
        # 生成建议
        recommendations = self._generate_recommendations(dimensions)
        
        return {
            "verdict": verdict,
            "score": avg_score,
            "dimensions": dimensions,
            "anti_patterns": anti_patterns,
            "recommendations": recommendations,
        }
    
    def _audit_semantic_tasks(self, pipeline_result: dict) -> dict:
        """审计语义任务是否使用 LLM"""
        score = 0.5  # 默认中等
        
        # 检查 Planning 是否使用 Expert Planners（LLM）
        planning = pipeline_result.get("planning", {})
        if isinstance(planning, dict):
            experts = planning.get("experts", [])
            if len(experts) >= 2:
                score += 0.2
            
            # 检查是否有 LLM-as-Judge
            convergence = planning.get("semantic_verification", {})
            if convergence.get("verdict") in ("PASS", "FAIL"):
                score += 0.3
        
        return {
            "score": min(1.0, score),
            "details": f"Planning has {len(planning.get('experts', []))} experts" if isinstance(planning, dict) else "N/A",
        }
    
    def _audit_layer2_validation(self, pipeline_result: dict) -> dict:
        """审计是否有 Layer 2 LLM 语义验证"""
        score = 0.3  # 默认偏低
        
        # 检查 Gate A Layer 2
        planning = pipeline_result.get("planning", {})
        if isinstance(planning, dict):
            harness = planning.get("harness", {})
            gate_a = harness.get("gate_a", {})
            if gate_a.get("layer2_calibrated"):
                score += 0.4
        
        # 检查 Convergence Planner
        if isinstance(planning, dict):
            convergence = planning.get("convergence", {})
            if convergence.get("semantic_verification"):
                score += 0.3
        
        return {
            "score": min(1.0, score),
            "details": "Layer 2 calibration present" if score >= 0.7 else "Layer 2 may be missing",
        }
    
    def _audit_prompt_contracts(self, pipeline_result: dict) -> dict:
        """审计 Prompt 是否是契约（五要素）"""
        # 五要素：角色 + 上下文 + 约束 + 示例 + 输出格式
        score = 0.5  # 默认中等（无法直接检查 prompt 文件）
        
        # 检查 Planning 输出是否有结构化 Schema
        planning = pipeline_result.get("planning", {})
        if isinstance(planning, dict):
            if planning.get("schema_version"):
                score += 0.2
            if planning.get("unified_constraints"):
                score += 0.3
        
        return {
            "score": min(1.0, score),
            "details": "Schema version present" if isinstance(planning, dict) and planning.get("schema_version") else "No schema",
        }
    
    def _audit_error_recovery(self, pipeline_result: dict) -> dict:
        """审计错误恢复是否用 LLM 诊断"""
        score = 0.4  # 默认偏低
        
        # 检查降级模块
        degraded = pipeline_result.get("degraded_modules", [])
        if not degraded:
            score += 0.3  # 没有降级 = 错误处理可能更好
        
        # 检查 Research 是否有 graceful degradation
        research = pipeline_result.get("research", {})
        if isinstance(research, dict) and research.get("degradation_info"):
            score += 0.3  # 有 degradation_info = 有意识的降级
        
        return {
            "score": min(1.0, score),
            "details": f"{len(degraded)} degraded modules",
        }
    
    def _detect_anti_patterns(self, code: str) -> list:
        """检测代码中的 AI Native 反模式"""
        detected = []
        
        for name, rule in self.ANTI_PATTERNS.items():
            matches = re.findall(rule["pattern"], code, re.IGNORECASE)
            if matches:
                detected.append({
                    "name": name,
                    "description": rule["description"],
                    "severity": rule["severity"],
                    "count": len(matches),
                })
        
        return detected
    
    def _generate_recommendations(self, dimensions: dict) -> list:
        """生成改进建议"""
        recommendations = []
        
        for dim_name, dim_data in dimensions.items():
            if isinstance(dim_data, dict) and dim_data.get("score", 1.0) < 0.7:
                if dim_name == "semantic_tasks_use_llm":
                    recommendations.append("增加 LLM-as-Judge 替代硬编码判断")
                elif dim_name == "layer2_validation":
                    recommendations.append("添加 Layer 2 LLM 语义验证层")
                elif dim_name == "prompt_contracts":
                    recommendations.append("完善 Prompt 五要素（角色+上下文+约束+示例+输出格式）")
                elif dim_name == "error_recovery":
                    recommendations.append("错误恢复使用 LLM 诊断而非纯 try/except")
                elif dim_name == "no_anti_patterns":
                    recommendations.append("消除 AI Native 反模式（正则分类/elif 链等）")
        
        return recommendations
