#!/usr/bin/env python3
"""
Fix Blackboard State — Phase 0 止血

修复当前 Blackboard 的 4 个 bug：
1. stage_progress.json 未更新
2. convergence.converged 未标记 true
3. supplementary_rounds=0 但存在 supplemental 文件
4. verification_result 的 UC 覆盖验证不完整
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from domains.solution_pro.state_manager import SolutionProStateManager
from domains.solution_pro.uc_verifier import UCCoverageVerifier


def fix_blackboard_state(blackboard_path: Path) -> dict:
    """
    修复 Blackboard 状态
    
    Args:
        blackboard_path: Blackboard 目录路径
        
    Returns:
        修复报告
    """
    print(f"🔧 Fixing Blackboard state: {blackboard_path}")
    
    report = {
        "session_id": blackboard_path.name,
        "fixes_applied": [],
        "verification_results": {},
        "timestamp": datetime.now().isoformat()
    }
    
    # 1. 初始化状态管理器
    state_mgr = SolutionProStateManager(blackboard_path)
    state = state_mgr.get_state()
    
    print(f"  Loaded state: session_id={state.session_id}, status={state.status}")
    
    # 2. 从 master_state.json 恢复模块状态
    master_state_file = blackboard_path / "master_state.json"
    if master_state_file.exists():
        try:
            master_data = json.loads(master_state_file.read_text())
            completed_modules = master_data.get("completed_modules", [])
            
            for module_name in completed_modules:
                # 启动模块（如果还没启动）
                if module_name not in state.modules:
                    state_mgr.start_module(module_name)
                    report["fixes_applied"].append(f"Started module: {module_name}")
                
                # 标记为完成
                state_mgr.complete_module(module_name)
                report["fixes_applied"].append(f"Completed module: {module_name}")
            
            print(f"  ✅ Restored {len(completed_modules)} modules from master_state.json")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  ⚠️  Failed to read master_state.json: {e}")
    
    # 3. 从 stages/ 目录恢复阶段进度
    stages_dir = blackboard_path / "stages"
    if stages_dir.exists():
        stage_files = list(stages_dir.glob("*.json"))
        
        for stage_file in stage_files:
            stage_name = stage_file.stem
            
            # 推断模块名（简单规则：前缀）
            module_name = "unknown"
            if stage_name.startswith("planning_"):
                module_name = "planning"
            elif stage_name.startswith("research_"):
                module_name = "research"
            elif stage_name.startswith("review_"):
                module_name = "summary"
            elif stage_name in ["solution_document", "refined_solution", "final_solution", "verification_result"]:
                module_name = "summary"
            
            # 更新阶段状态
            if module_name != "unknown":
                state_mgr.update_stage(
                    module_name=module_name,
                    stage_name=stage_name,
                    status="completed",
                    output_file=str(stage_file.relative_to(blackboard_path))
                )
                report["fixes_applied"].append(f"Stage completed: {module_name}/{stage_name}")
        
        print(f"  ✅ Restored {len(stage_files)} stages from stages/ directory")
    
    # 4. 修复 convergence.converged 标记
    for module_name in ["planning", "research", "summary"]:
        convergence_file = stages_dir / f"{module_name}_convergence.json"
        
        if convergence_file.exists():
            try:
                conv_data = json.loads(convergence_file.read_text())
                # Handle both dict and string formats
                if isinstance(conv_data, str):
                    conv_data = json.loads(conv_data)
                
                # Extract gate results (handle different formats)
                gate_a_result = conv_data.get("gate_a", {})
                gate_b_result = conv_data.get("gate_b", {})
                
                if isinstance(gate_a_result, dict):
                    gate_a = gate_a_result.get("result", "UNKNOWN")
                else:
                    gate_a = str(gate_a_result) if gate_a_result else "UNKNOWN"
                
                if isinstance(gate_b_result, dict):
                    gate_b = gate_b_result.get("result", "UNKNOWN")
                else:
                    gate_b = str(gate_b_result) if gate_b_result else "UNKNOWN"
                
                verdict = conv_data.get("overall_verdict", "UNKNOWN")
                
                state_mgr.mark_converged(
                    module_name=module_name,
                    gate_a=gate_a,
                    gate_b=gate_b,
                    verdict=verdict,
                    convergence_file=f"stages/{module_name}_convergence.json"
                )
                report["fixes_applied"].append(f"Convergence marked: {module_name}")
                print(f"  ✅ Marked convergence: {module_name} (verdict={verdict})")
            except (json.JSONDecodeError, KeyError) as e:
                print(f"  ⚠️  Failed to read convergence for {module_name}: {e}")
    
    # 5. 修复 supplementary_rounds 计数
    supplementary_files = list(stages_dir.glob("*supplemental*.json"))
    if supplementary_files:
        for sup_file in supplementary_files:
            state_mgr.add_supplementary_round(str(sup_file.relative_to(blackboard_path)))
        report["fixes_applied"].append(f"Supplementary rounds: {len(supplementary_files)}")
        print(f"  ✅ Fixed supplementary_rounds: {len(supplementary_files)} files")
    
    # 6. UC 覆盖率验证（Bug #4）
    print("  🔍 Running UC coverage verification...")
    uc_verifier = UCCoverageVerifier(blackboard_path)
    uc_result = uc_verifier.verify()
    
    report["verification_results"]["uc_coverage"] = {
        "total_uc": uc_result.total_uc,
        "covered_uc": uc_result.covered_uc,
        "missing_uc": uc_result.missing_uc,
        "coverage_rate": uc_result.coverage_rate,
        "is_complete": uc_result.is_complete,
        "verification_method": uc_result.verification_method
    }
    
    print(f"  ✅ UC coverage: {len(uc_result.covered_uc)}/{uc_result.total_uc} ({uc_result.coverage_rate:.1%})")
    if uc_result.missing_uc:
        print(f"  ⚠️  Missing UC: {uc_result.missing_uc}")
    
    # 7. 标记 pipeline 完成（如果所有模块都完成了）
    if state.status == "running" and all(m.status == "completed" for m in state.modules.values()):
        state_mgr.mark_completed()
        report["fixes_applied"].append("Pipeline marked as completed")
        print(f"  ✅ Pipeline marked as completed")
    
    # 8. 生成修复报告
    report_file = blackboard_path / "fix_report.json"
    report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    
    print(f"\n✅ Fix complete! Report saved to: {report_file}")
    print(f"   Total fixes applied: {len(report['fixes_applied'])}")
    
    return report


def main():
    """CLI 入口"""
    if len(sys.argv) < 2:
        print("Usage: python fix_blackboard_state.py <blackboard_path>")
        print("\nExample:")
        print("  python fix_blackboard_state.py blackboard/OpenClaw\\ AI\\ Native\\ Loop\\ Engineering\\ Framework/")
        sys.exit(1)
    
    blackboard_path = Path(sys.argv[1])
    
    if not blackboard_path.exists():
        print(f"❌ Blackboard path not found: {blackboard_path}")
        sys.exit(1)
    
    report = fix_blackboard_state(blackboard_path)
    
    # 打印摘要
    print("\n" + "="*60)
    print("FIX SUMMARY")
    print("="*60)
    print(f"Session: {report['session_id']}")
    print(f"Timestamp: {report['timestamp']}")
    print(f"\nFixes Applied ({len(report['fixes_applied'])}):")
    for fix in report["fixes_applied"][:10]:  # 只显示前 10 个
        print(f"  - {fix}")
    if len(report["fixes_applied"]) > 10:
        print(f"  ... and {len(report['fixes_applied']) - 10} more")
    
    uc_cov = report["verification_results"].get("uc_coverage", {})
    if uc_cov:
        print(f"\nUC Coverage:")
        print(f"  Total: {uc_cov['total_uc']}")
        print(f"  Covered: {len(uc_cov['covered_uc'])}")
        print(f"  Rate: {uc_cov['coverage_rate']:.1%}")
        if uc_cov['missing_uc']:
            print(f"  Missing: {uc_cov['missing_uc']}")


if __name__ == "__main__":
    main()
