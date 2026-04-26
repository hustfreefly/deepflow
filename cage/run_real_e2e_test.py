#!/usr/bin/env python3
"""
Real End-to-End Test for Solution Domain
使用真实模型调用运行完整的 Solution pipeline
"""

import sys
import os
import time
import json
import asyncio
from datetime import datetime

# 添加 .deepflow 到路径
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')

from domains.solution import SolutionOrchestrator

async def run_test():
    """运行真实端到端测试"""
    
    print("=" * 80)
    print("Solution Domain - Real End-to-End Test")
    print("=" * 80)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 测试用例
    test_case = {
        "topic": "设计一个支持百万日订单的电商订单系统",
        "type": "architecture",
        "mode": "standard",
        "constraints": ["日均百万订单", "99.99%可用性", "<200ms响应时间"],
        "stakeholders": ["技术团队", "产品团队", "运维团队"]
    }
    
    print("测试用例:")
    print(json.dumps(test_case, indent=2, ensure_ascii=False))
    print()
    
    # 记录开始时间
    start_time = time.time()
    
    try:
        # 运行 SolutionOrchestrator
        print("启动 SolutionOrchestrator...")
        orchestrator = SolutionOrchestrator(test_case)
        
        result = await orchestrator.run()
        
        # 记录结束时间
        end_time = time.time()
        total_duration = end_time - start_time
        
        print()
        print("=" * 80)
        print("测试结果汇总")
        print("=" * 80)
        print(f"总执行时间: {total_duration:.2f} 秒 ({total_duration/60:.2f} 分钟)")
        print()
        
        # Pipeline 状态
        print(f"Pipeline 状态: {result.get('state', 'UNKNOWN')}")
        print(f"最终分数: {result.get('final_score', 'N/A')}")
        print(f"收敛原因: {result.get('convergence_reason', 'N/A')}")
        print()
        
        # 阶段耗时
        if 'stage_durations' in result:
            print("各阶段耗时:")
            for stage_name, duration in result['stage_durations'].items():
                print(f"  {stage_name}: {duration:.2f} 秒")
            print()
        
        # 产出文件路径
        blackboard_path = result.get('blackboard_path', 'N/A')
        print(f"Blackboard 路径: {blackboard_path}")
        
        # 检查产出文件
        if blackboard_path and blackboard_path != 'N/A':
            deliverables = []
            final_solution_path = os.path.join(blackboard_path, 'final_solution.md')
            final_result_path = os.path.join(blackboard_path, 'final_result.json')
            
            if os.path.exists(final_solution_path):
                deliverables.append(final_solution_path)
                size = os.path.getsize(final_solution_path)
                print(f"✓ final_solution.md 存在 ({size} bytes)")
            else:
                print(f"✗ final_solution.md 不存在")
            
            if os.path.exists(final_result_path):
                deliverables.append(final_result_path)
                size = os.path.getsize(final_result_path)
                print(f"✓ final_result.json 存在 ({size} bytes)")
            else:
                print(f"✗ final_result.json 不存在")
            
            # 列出 stages 目录
            stages_dir = os.path.join(blackboard_path, 'stages')
            if os.path.exists(stages_dir):
                stage_files = os.listdir(stages_dir)
                print(f"✓ stages/ 目录包含 {len(stage_files)} 个文件")
                for f in sorted(stage_files):
                    size = os.path.getsize(os.path.join(stages_dir, f))
                    print(f"    - {f} ({size} bytes)")
        
        print()
        
        # 质量评估
        print("=" * 80)
        print("产出质量评估")
        print("=" * 80)
        
        quality_checks = {
            "RC-001": {"desc": "是否包含技术架构描述？", "passed": False},
            "RC-002": {"desc": "是否提到具体技术选型（如数据库、缓存）？", "passed": False},
            "RC-003": {"desc": "是否回应了约束条件（百万订单、99.99%可用性）？", "passed": False},
            "RC-004": {"desc": "产出是否结构化、可读？", "passed": False},
        }
        
        # 读取 final_solution.md 进行质量检查
        final_solution_path = os.path.join(blackboard_path, 'final_solution.md') if blackboard_path != 'N/A' else None
        if final_solution_path and os.path.exists(final_solution_path):
            with open(final_solution_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # RC-001: 技术架构描述
                architecture_keywords = ['架构', '架构设计', '系统设计', '整体架构', 'architecture']
                quality_checks["RC-001"]["passed"] = any(kw in content for kw in architecture_keywords)
                
                # RC-002: 技术选型
                tech_keywords = ['数据库', '缓存', 'Redis', 'MySQL', 'MongoDB', 'Kafka', '微服务']
                quality_checks["RC-002"]["passed"] = any(kw in content for kw in tech_keywords)
                
                # RC-003: 约束条件回应
                constraint_keywords = ['百万', '99.99', '可用性', '200ms', '响应时间', '高并发']
                quality_checks["RC-003"]["passed"] = any(kw in content for kw in constraint_keywords)
                
                # RC-004: 结构化
                structure_indicators = ['# ', '## ', '- ', '1. ', '* ']
                quality_checks["RC-004"]["passed"] = sum(1 for ind in structure_indicators if ind in content) >= 2
        
        passed_count = sum(1 for check in quality_checks.values() if check["passed"])
        
        for check_id, check in quality_checks.items():
            status = "✓" if check["passed"] else "✗"
            print(f"{status} {check_id}: {check['desc']} {'通过' if check['passed'] else '未通过'}")
        
        print()
        print(f"质量检查通过率: {passed_count}/{len(quality_checks)} ({passed_count/len(quality_checks)*100:.0f}%)")
        
        # 成功标准
        print()
        print("=" * 80)
        print("验收标准检查")
        print("=" * 80)
        
        success_criteria = [
            ("至少 3 项质量检查通过", passed_count >= 3),
            ("Pipeline 状态为 CONVERGED 或 STALLED", result.get('state') in ['CONVERGED', 'STALLED']),
            ("最终分数 >= 0.70", result.get('final_score', 0) >= 0.70),
        ]
        
        all_passed = True
        for criterion, passed in success_criteria:
            status = "✓" if passed else "✗"
            print(f"{status} {criterion}")
            if not passed:
                all_passed = False
        
        print()
        if all_passed:
            print("🎉 测试通过！所有验收标准均满足。")
        else:
            print("⚠️  测试部分失败，请检查上述未通过的验收标准。")
        
        # 遇到的问题和建议
        print()
        print("=" * 80)
        print("问题和改进建议")
        print("=" * 80)
        
        issues = []
        
        # 检查是否有异常
        if result.get('state') == 'FAILED':
            issues.append("Pipeline 执行失败，需要检查错误日志")
        
        if result.get('final_score', 0) < 0.70:
            issues.append(f"最终分数 {result.get('final_score')} 低于 0.70，可能需要优化审计和修复流程")
        
        if total_duration > 600:
            issues.append(f"执行时间 {total_duration:.0f} 秒超过 10 分钟，可能需要优化性能")
        
        if not issues:
            print("✓ 未发现明显问题")
        else:
            for issue in issues:
                print(f"⚠️  {issue}")
        
        # 保存测试报告
        report = {
            "test_name": "solution_real_e2e_test",
            "timestamp": datetime.now().isoformat(),
            "test_case": test_case,
            "execution_time_seconds": total_duration,
            "pipeline_state": result.get('state'),
            "final_score": result.get('final_score'),
            "convergence_reason": result.get('convergence_reason'),
            "stage_durations": result.get('stage_durations', {}),
            "blackboard_path": blackboard_path,
            "quality_checks": {k: v["passed"] for k, v in quality_checks.items()},
            "quality_pass_rate": f"{passed_count}/{len(quality_checks)}",
            "success_criteria_met": all_passed,
            "issues": issues,
        }
        
        report_path = os.path.join(
            '/Users/allen/.openclaw/workspace/.deepflow/cage',
            'real_e2e_test_report.json'
        )
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print()
        print(f"测试报告已保存到: {report_path}")
        
        return result
        
    except Exception as e:
        end_time = time.time()
        total_duration = end_time - start_time
        
        print()
        print("=" * 80)
        print("❌ 测试执行出错")
        print("=" * 80)
        print(f"执行时间: {total_duration:.2f} 秒")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        
        import traceback
        traceback.print_exc()
        
        # 保存错误报告
        error_report = {
            "test_name": "solution_real_e2e_test",
            "timestamp": datetime.now().isoformat(),
            "test_case": test_case,
            "execution_time_seconds": total_duration,
            "error_type": type(e).__name__,
            "error_message": str(e),
            "traceback": traceback.format_exc(),
        }
        
        report_path = os.path.join(
            '/Users/allen/.openclaw/workspace/.deepflow/cage',
            'real_e2e_test_error.json'
        )
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(error_report, f, indent=2, ensure_ascii=False)
        
        print(f"\n错误报告已保存到: {report_path}")
        
        raise


if __name__ == "__main__":
    asyncio.run(run_test())
