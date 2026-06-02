"""
Harness 专家检查器

Version: 2.1.0
Author: DeepFlow Solution Pro
Date: 2026-06-01
"""

#!/usr/bin/env python3
"""
Stage 7 专家修复后的Harness检查
PragmaticGuard - 实用性和防发散检查
"""

import json
import sys
from pathlib import Path

from domains.solution.blackboard import STAGE_PATH_REGISTRY

def check_expert_fix(session_id: str, blackboard_path: Path) -> dict:
    """
    检查专家修复质量
    
    Returns:
        {
            "passed": bool,
            "score": int,  # 0-100
            "issues": [],
            "recommendation": "pass|retry|flag_risk"
        }
    """
    # 读取输入
    audit_path = blackboard_path / session_id / STAGE_PATH_REGISTRY["audit"]
    fix_path = blackboard_path / session_id / STAGE_PATH_REGISTRY["fixer_expert"]
    
    if not audit_path.exists() or not fix_path.exists():
        return {
            "passed": False,
            "score": 0,
            "issues": ["输入文件缺失"],
            "recommendation": "retry"
        }
    
    with open(audit_path) as f:
        audit = json.load(f)
    with open(fix_path) as f:
        fix = json.load(f)
    
    issues = []
    score = 100
    
    # === 质量检查 ===
    # 汇总所有审计问题
    all_issues = audit.get("data", {}).get("audit_findings") or audit.get("data", {}).get("issues") or []
    if not all_issues:
        for auditor_output in audit.get("auditors", []):
            all_issues.extend(auditor_output.get("issues", []))
    
    p0_total = len([i for i in all_issues if i.get("level") == "P0" or i.get("severity") == "critical"])
    p1_total = len([i for i in all_issues if i.get("level") == "P1" or i.get("severity") == "major"])
    
    summary = fix.get("data", {}).get("summary", {})
    p0_fixed = fix.get("harness_check", {}).get("P0_resolved", summary.get("critical_fixed", 0))
    p1_fixed = fix.get("harness_check", {}).get("P1_resolved", summary.get("major_fixed", 0))
    
    # P0必须100%修复
    if p0_total > 0 and p0_fixed < p0_total:
        issues.append(f"P0未全部修复: {p0_fixed}/{p0_total}")
        score -= 40
    
    # P1建议80%修复
    if p1_total > 0 and p1_fixed < p1_total * 0.8:
        issues.append(f"P1修复率不足: {p1_fixed}/{p1_total}")
        score -= 15
    
    # 修复方案可执行性检查
    fixes = fix.get("data", {}).get("deep_fixes") or fix.get("data", {}).get("fixes_applied") or fix.get("fixes", [])
    for f in fixes:
        fix_text = f.get("fix") or f.get("fix_strategy") or f.get("fix_description") or f.get("implementation")
        if not fix_text or fix_text == "TODO":
            issues.append(f"修复方案不够具体: {f.get('issue_id') or f.get('audit_id')}")
            score -= 10
    
    # === 发散检查（PragmaticGuard）===
    # 技术债务检查
    tech_debt = fix.get("harness_check", {}).get("tech_debt_introduced", 0)
    if tech_debt > 2:
        issues.append(f"引入过多技术债务: {tech_debt}处")
        score -= 15
    
    # 架构一致性检查
    if not fix.get("harness_check", {}).get("architecture_consistency", True):
        issues.append("修复与整体架构不一致")
        score -= 20
    
    # 推荐决策
    if score >= 85:
        recommendation = "pass"
    elif score >= 70:
        recommendation = "pass_with_warning"
    elif score >= 50:
        recommendation = "flag_risk"
    else:
        recommendation = "retry"
    
    return {
        "passed": score >= 70,
        "score": score,
        "issues": issues,
        "recommendation": recommendation,
        "details": {
            "P0_total": p0_total,
            "P0_fixed": p0_fixed,
            "P1_total": p1_total,
            "P1_fixed": p1_fixed,
            "tech_debt": tech_debt
        }
    }

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 harness_check_expert.py <session_id> <blackboard_path>")
        sys.exit(1)
    
    session_id = sys.argv[1]
    blackboard_path = Path(sys.argv[2])
    
    result = check_expert_fix(session_id, blackboard_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    sys.exit(0 if result["passed"] else 1)
