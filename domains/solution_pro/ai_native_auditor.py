"""
AINativeAuditor — 最小 AI Native 审计器（兼容 Phase 3 验收）
"""

from typing import Literal


class AINativeAuditor:
    """评估 pipeline 输出是否符合 AI Native 原则。"""

    def audit_pipeline(self, pipeline_result: dict) -> dict:
        degraded = pipeline_result.get("degraded_modules", []) or []
        planning = pipeline_result.get("planning", {}) or {}

        dimensions = {
            "schema_compliance": 1.0 if planning.get("schema_version") else 0.0,
            "expert_coverage": 1.0 if planning.get("experts") else 0.0,
            "semantic_verification": 1.0 if planning.get("semantic_verification", {}).get("verdict") == "PASS" else 0.0,
            "degradation_risk": 0.0 if degraded else 1.0,
        }

        score = sum(dimensions.values()) / len(dimensions)
        if degraded:
            score = max(0.0, score - 0.3)
        verdict = "PASS" if score >= 0.8 else ("WARNING" if score >= 0.5 else "FAIL")

        recommendations = []
        if degraded:
            recommendations.append(f"degraded modules detected: {', '.join(degraded)}")
        if not planning.get("experts"):
            recommendations.append("add experts to planning output")
        if not planning.get("semantic_verification"):
            recommendations.append("add semantic verification to planning output")

        return {
            "verdict": verdict,
            "score": round(score, 2),
            "dimensions": dimensions,
            "recommendations": recommendations,
        }
