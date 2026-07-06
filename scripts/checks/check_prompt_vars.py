"""Gate: 检查 prompt 中的模板变量是否都被 runner 替换"""
import sys, re
from pathlib import Path

DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent

def extract_prompt_vars(content: str) -> set[str]:
    """提取 {var_name} 格式的模板变量"""
    return set(re.findall(r'\{([a-z_]+)\}', content))

def extract_runner_replacements(source: str) -> set[str]:
    """从 runner 源码中提取 .replace('{xxx}', ...) 的变量名（含多行调用）"""
    # Normalize: collapse whitespace so multi-line .replace(\n  "{var}", ...) is caught
    normalized = re.sub(r'\s+', ' ', source)
    return set(re.findall(r"\.replace\(\s*['\"]?\{([a-z_]+)\}['\"]?", normalized))

def check_prompt_runner_pair(prompt_path: Path, runner_source: str, pair_name: str) -> list[str]:
    issues = []
    prompt_content = prompt_path.read_text()
    prompt_vars = extract_prompt_vars(prompt_content)
    runner_vars = extract_runner_replacements(runner_source)
    
    # 已知由 _resolve_prompt_vars 统一替换的变量
    GLOBAL_VARS = {"deepflow_root"}
    # 已知由 _build_expert_task / _build_phase_task wrapper 注入的变量
    WRAPPER_VARS = {"session_id", "blackboard_path"}
    
    all_replaced = runner_vars | GLOBAL_VARS | WRAPPER_VARS
    unreplaced = prompt_vars - all_replaced
    
    if unreplaced:
        issues.append(f"{pair_name}: 未替换变量 {unreplaced}")
    
    return issues

def main():
    import importlib
    sys.path.insert(0, str(DEEPFLOW_ROOT))
    import inspect
    
    all_issues = []
    
    # Check research_expert_base.md → ResearchOrchestrator
    from domains.solution_pro.research_orchestrator import ResearchOrchestrator
    runner_src = inspect.getsource(ResearchOrchestrator)
    prompt_path = DEEPFLOW_ROOT / "domains/solution_pro/prompts/research_expert_base.md"
    if prompt_path.exists():
        all_issues.extend(check_prompt_runner_pair(prompt_path, runner_src, "research_expert_base"))
    
    # Check planning prompts → PlanningOrchestrator
    from domains.solution_pro.planning_orchestrator import PlanningOrchestrator
    planning_src = inspect.getsource(PlanningOrchestrator)
    for name in ["planning_expert_base.md", "expert_planner_base.md"]:
        prompt_path = DEEPFLOW_ROOT / f"domains/solution_pro/prompts/{name}"
        if prompt_path.exists():
            all_issues.extend(check_prompt_runner_pair(prompt_path, planning_src, name.replace('.md','')))
    
    if all_issues:
        print("❌ FAIL: 模板变量未替换")
        for i in all_issues:
            print(f"  {i}")
        sys.exit(1)
    else:
        print("✅ PASS: 所有模板变量有对应替换")
        sys.exit(0)

if __name__ == "__main__":
    main()
