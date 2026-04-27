# Solution Domain Contract Validation
# DeepFlow 解决方案设计领域契约笼子

import os
import sys
import yaml
import json

from core.config.path_config import PathConfig

sys.path.insert(0, str(PathConfig.resolve().base_dir))

def check_contract():
    """
    验证 Solution 领域的契约合规性
    """
    errors = []
    warnings = []
    
    # 1. 检查领域配置文件
    config_path = str(PathConfig.resolve().base_dir / "domains/solution.yaml")
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
        required_roles = ['solution_planner', 'solution_researcher', 'solution_architect', 
                         'solution_auditor', 'solution_fixer', 'solution_designer']
        found_roles = [a['role'] for a in config['agents']]
        for role in required_roles:
            if role not in found_roles:
                errors.append(f"P0: 缺少必需 Agent '{role}'")
    
    # 4. 验证 pipeline stages
    if 'pipeline' in config and 'stages' in config['pipeline']:
        stages = config['pipeline']['stages']
        required_stages = ['planning', 'research', 'design', 'audit', 'fix', 'deliver']
        found_stages = [s['name'] for s in stages]
        for stage in required_stages:
            if stage not in found_stages:
                errors.append(f"P0: 缺少必需阶段 '{stage}'")
    
    # 5. 验证 prompts 文件
    prompt_dir = str(PathConfig.resolve().base_dir / "prompts/solution/")
    required_prompts = ['planner.md', 'researcher.md', 'architect.md', 
                       'auditor.md', 'fixer.md', 'designer.md']
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
        from domains.solution import SolutionOrchestrator
        orch = SolutionOrchestrator({
            'topic': '测试',
            'type': 'architecture'
        })
        if not hasattr(orch, '_execute_stage'):
            errors.append("P0: Orchestrator 缺少 _execute_stage 方法")
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
