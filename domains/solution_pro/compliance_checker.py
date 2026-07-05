"""
ComplianceChecker — 最小合规检查器（兼容 Phase 3 验收）
"""

from typing import Literal
from pydantic import BaseModel, Field

class ComplianceReport(BaseModel):
    verdict: Literal["PASS", "WARNING", "FAIL"] = Field(default="PASS")
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    findings: list[str] = Field(default_factory=list)


class ComplianceChecker:
    """检查 stage 输出是否包含关键字段。"""

    def check(self, output: dict) -> ComplianceReport:
        if not isinstance(output, dict):
            return ComplianceReport(verdict="FAIL", score=0.0, findings=["output is not a dict"])

        score = 1.0
        findings = []
        if "schema_version" not in output:
            score -= 0.4
            findings.append("missing schema_version")
        if "constraints" not in output and "unified_constraints" not in output:
            score -= 0.3
            findings.append("missing constraints/unified_constraints")
        if "unified_constraints" in output:
            uc = output["unified_constraints"]
            if not isinstance(uc, dict) or "constraints" not in uc or not uc["constraints"]:
                score -= 0.3
                findings.append("unified_constraints empty or malformed")

        score = max(0.0, score)
        verdict = "PASS" if score >= 0.9 else ("WARNING" if score >= 0.5 else "FAIL")
        return ComplianceReport(verdict=verdict, score=score, findings=findings)
