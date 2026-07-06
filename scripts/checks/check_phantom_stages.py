"""Gate: 检查 prompt 中是否引用了 runner 不产出的 phantom stages"""
import sys
from pathlib import Path

DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent

# research_orchestrator 实际产出的 stages
RESEARCH_STAGES = {
    "knowledge_freshness", "research_experts", "research_digest",
    "research_convergence", "research_plan", "consolidation",
    "research_expert_queries", "expert_manifest",
}

# 已废弃的 stages（ReviewQC 清理遗留）
DEPRECATED_STAGES = {"gap_analysis", "devil_advocate"}

def check_file(filepath: Path) -> list[str]:
    issues = []
    content = filepath.read_text()
    for stage in DEPRECATED_STAGES:
        # 检查是否作为 stage 名引用（不是注释或示例）
        if f"`{stage}`" in content or f"'{stage}'" in content or f'"{stage}"' in content:
            issues.append(f"{filepath.name}: 引用了已废弃 stage '{stage}'")
    return issues

def main():
    prompt_dir = DEEPFLOW_ROOT / "domains" / "solution_pro" / "prompts"
    active_prompts = [f for f in prompt_dir.glob("*.md") if "_archive" not in str(f)]
    
    all_issues = []
    for f in active_prompts:
        all_issues.extend(check_file(f))
    
    if all_issues:
        print("❌ FAIL: phantom stages 仍存在")
        for i in all_issues:
            print(f"  {i}")
        sys.exit(1)
    else:
        print("✅ PASS: 无 phantom stages")
        sys.exit(0)

if __name__ == "__main__":
    main()
