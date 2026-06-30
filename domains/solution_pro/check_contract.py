"""
契约检查脚本，验证配置完整性

Version: 2.1.0
Author: DeepFlow Solution Pro
Date: 2026-06-01
"""

"""
V1-LEGACY: This file is part of V1 pipeline (10-stage architecture).
V2 uses MasterOrchestrator + PlanningOrchestrator + ResearchOrchestrator + ReviewQCOrchestrator.
Do not import this file for new V2 workflows.
"""

# Solution Domain Contract Validation
# DeepFlow 解决方案设计领域契约笼子

import os
import sys
import yaml
import json
from pathlib import Path

import core.bootstrap

from core.config.path_config import PathConfig

def check_contract():
    """
    验证 Solution 领域的契约合规性
    """
    errors = []
    warnings = []
    
    # 1. 检查领域配置文件
    config_path = str(PathConfig.resolve().base_dir / "domains/solution_pro/config/solution.yaml")
    if not os.path.exists(config_path):
        errors.append("P0: solution.yaml 不存在")
        return {"pass": False, "errors": errors, "warnings": warnings}
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 2. 验证必需字段
    required_fields = ['domain', 'name', 'description', 'agents', 'pipeline']
    for field in required_fields:
        if field not in config:
            errors.append(f"P0: 缺少必需字段 '{field}'")
    
    # 3. 验证 agents 配置
    if 'agents' in config:
        required_roles = [
            'data_collection',
            'planning',
            'reviewer',
            'researcher',
            'consolidator',
            'auditor',
            'fixer',
            'fixer_expert',
            'harness_final',
            'summarizer',
        ]
        found_roles = [a['role'] for a in config['agents']]
        for role in required_roles:
            if role not in found_roles:
                errors.append(f"P0: 缺少必需 Agent '{role}'")
    
    # 4. 验证 pipeline stages
    if 'pipeline' in config and 'stages' in config['pipeline']:
        stages = config['pipeline']['stages']
        required_stages = [
            'data_collection',
            'planning',
            'reviewers',
            'research',
            'consolidator',
            'audit',
            'fix',
            'fixer_expert',
            'harness_final',
            'summarizer',
        ]
        found_stages = [s['name'] for s in stages]
        if found_stages != required_stages:
            errors.append(f"P0: pipeline stages 不匹配，期望 {required_stages}，实际 {found_stages}")
    
    # 5. 验证 prompts 文件
    prompt_dir = str(PathConfig.resolve().base_dir / "domains/solution_pro/prompts/")
    required_prompts = [
        'v1/data_collection.md',
        'planner_v2_harness.md',
        'reviewer_v2_harness.md',
        'researcher_v2_harness.md',
        'consolidator_v2_harness.md',
        'auditor_v2_harness.md',
        'fixer_v2_harness.md',
        'fixer_expert_v2_harness.md',
        'v1/harness_v3.md',
        'summarizer_v2_harness.md',
    ]
    for prompt in required_prompts:
        prompt_path = os.path.join(prompt_dir, prompt)
        if not os.path.exists(prompt_path):
            errors.append(f"P0: Prompt 文件缺失 '{prompt}'")
        else:
            # 检查文件内容非空
            with open(prompt_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if len(content) < 100:
                    warnings.append(f"P1: Prompt '{prompt}' 内容过少")
    
    # 6. 验证 orchestrator 可导入
    try:
        from domains.solution_pro.orchestrator_agent import _SolutionDispatcher
        orch = _SolutionDispatcher(
            topic='测试解决方案设计',
            solution_type='architecture'
        )
        if not hasattr(orch, 'get_all_tasks'):
            errors.append("P0: Orchestrator 缺少 get_all_tasks 方法")
    except Exception as e:
        errors.append(f"P0: Orchestrator 导入失败: {e}")
    
    # 7. 验证解决方案类型定义
    if 'solution_types' in config:
        required_types = ['architecture', 'business', 'technical']
        found_types = list(config['solution_types'].keys())
        for st in required_types:
            if st not in found_types:
                errors.append(f"P0: 缺少解决方案类型 '{st}'")
    
    # 8. 验证收敛配置
    if 'convergence' in config:
        conv = config['convergence']
        if conv.get('max_iterations', 0) < 1:
            errors.append("P0: max_iterations 必须 >= 1")
        if conv.get('target_score', 0) <= 0:
            errors.append("P0: target_score 必须 > 0")
    
    # 结果汇总
    return {
        "pass": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "total_errors": len(errors),
            "total_warnings": len(warnings),
            "config_valid": len(errors) == 0
        }
    }


if __name__ == "__main__":
    result = check_contract()
    
    print("=" * 60)
    print("SOLUTION DOMAIN CONTRACT VALIDATION")
    print("=" * 60)
    
    if result["pass"]:
        print("✅ ALL CONTRACTS PASSED")
    else:
        print(f"❌ {result['summary']['total_errors']} ERRORS FOUND")
    
    if result["warnings"]:
        print(f"⚠️ {result['summary']['total_warnings']} WARNINGS")
    
    print("\nErrors:")
    for e in result["errors"]:
        print(f"  ❌ {e}")
    
    print("\nWarnings:")
    for w in result["warnings"]:
        print(f"  ⚠️ {w}")
    
    print(f"\n{'='*60}")
    print(json.dumps(result["summary"], indent=2))


# ============================================================================
# V2 Schema Validation Entry Point
# ============================================================================

# V2 schema mapping: (module_name, stage_name) → Schema class
_V2_SCHEMA_MAP = {
    ("planning", "meta_planning"): "ExpertManifestSchema",
    ("planning", "expert_plans"): "ExpertPlanSchema",
    ("planning", "unified_constraints"): "UnifiedConstraintsSchema",
    ("planning", "verification_checklist"): "VerificationChecklistSchema",
    ("planning", "planning_convergence"): "PlanningConvergenceSchema",
    ("research", "research_experts"): "ResearchExpertSchema",
    ("research", "research_consolidator"): "ResearchConsolidatorSchema",
    ("research", "research_convergence"): "ResearchConvergenceSchema",
}


def check_v2_contract(module_name: str, stage_name: str, output: dict) -> dict:
    """V2 schema validation entry point.

    Args:
        module_name: "planning" | "research" | "review_qc"
        stage_name: stage identifier (e.g., "meta_planning", "knowledge_freshness")
        output: stage output dict to validate

    Returns:
        {"valid": bool, "errors": list[str], "stage": str}
    """
    from domains.solution_pro.schemas.v2_schemas import (
        ExpertManifestSchema,
        ExpertPlanSchema,
        UnifiedConstraintsSchema,
        VerificationChecklistSchema,
        PlanningConvergenceSchema,
        ResearchExpertSchema,
        ResearchConsolidatorSchema,
        ResearchConvergenceSchema,
    )

    # Resolve schema class from mapping
    schema_name = _V2_SCHEMA_MAP.get((module_name, stage_name))
    if schema_name is None:
        return {
            "valid": False,
            "errors": [f"Unknown V2 stage: module={module_name}, stage={stage_name}"],
            "stage": stage_name,
        }

    # Map name → actual class
    _class_map = {
        "ExpertManifestSchema": ExpertManifestSchema,
        "ExpertPlanSchema": ExpertPlanSchema,
        "UnifiedConstraintsSchema": UnifiedConstraintsSchema,
        "VerificationChecklistSchema": VerificationChecklistSchema,
        "PlanningConvergenceSchema": PlanningConvergenceSchema,
        "ResearchExpertSchema": ResearchExpertSchema,
        "ResearchConsolidatorSchema": ResearchConsolidatorSchema,
        "ResearchConvergenceSchema": ResearchConvergenceSchema,
    }
    schema_class = _class_map.get(schema_name)
    if schema_class is None:
        return {
            "valid": False,
            "errors": [f"Schema class not found: {schema_name}"],
            "stage": stage_name,
        }

    # Validate
    errors = []
    try:
        schema_class(**output)
    except Exception as exc:
        errors.append(str(exc))

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "stage": stage_name,
    }
