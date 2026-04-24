#!/usr/bin/env python3
"""
验证 Task 增强和模板变量替换
"""
import sys
import os
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow')

def test_replace_template_vars():
    """测试模板变量替换"""
    print("=" * 60)
    print("测试 1: 模板变量替换")
    print("=" * 60)
    
    from orchestrator_agent import replace_template_vars
    
    prompt = "股票代码: {{code}}, 公司: {{name}}, 会话: {{session_id}}"
    variables = {
        "code": "688652.SH",
        "name": "京仪装备",
        "session_id": "test_001"
    }
    
    result = replace_template_vars(prompt, variables)
    
    checks = {
        "code替换": "688652.SH" in result,
        "name替换": "京仪装备" in result,
        "session_id替换": "test_001" in result,
        "无残留模板": "{{" not in result,
    }
    
    all_pass = True
    for name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {name}: {passed}")
        if not passed:
            all_pass = False
    
    return all_pass

def test_build_worker_task():
    """测试 Worker Task 构建"""
    print("\n" + "=" * 60)
    print("测试 2: Worker Task 构建")
    print("=" * 60)
    
    from orchestrator_agent import build_worker_task
    
    # 先创建测试用的 blackboard 目录和数据
    os.makedirs('/Users/allen/.openclaw/workspace/.deepflow/blackboard/test_build_task/data', exist_ok=True)
    os.makedirs('/Users/allen/.openclaw/workspace/.deepflow/blackboard/test_build_task/stages', exist_ok=True)
    
    # 创建测试数据
    with open('/Users/allen/.openclaw/workspace/.deepflow/blackboard/test_build_task/data/key_metrics.json', 'w') as f:
        import json
        json.dump({
            "company_name": "京仪装备",
            "company_code": "688652.SH",
            "industry": "半导体设备",
            "market_cap": "150亿",
            "pe_ratio": "108.9",
            "latest_price": "110.28"
        }, f)
    
    # 创建测试 planner 输出
    with open('/Users/allen/.openclaw/workspace/.deepflow/blackboard/test_build_task/stages/planner_output.json', 'w') as f:
        import json
        json.dump({
            "research_plan": {
                "objectives": ["分析技术壁垒", "对比竞争对手", "评估盈利能力"]
            }
        }, f)
    
    task = build_worker_task(
        agent_role="researcher_finance",
        company_code="688652.SH",
        company_name="京仪装备",
        session_id="test_build_task",
        prompt_file="prompts/investment/researcher_enhanced.md",
        output_path="blackboard/test_build_task/stages/researcher_finance_output.json",
        input_paths=["blackboard/test_build_task/data/key_metrics.json"]
    )
    
    checks = {
        "包含股票代码": "688652.SH" in task,
        "包含公司名称": "京仪装备" in task,
        "包含行业": "半导体设备" in task,
        "包含研究重点": "分析技术壁垒" in task,
        "包含输入路径": "key_metrics.json" in task,
        "包含输出路径": "researcher_finance_output.json" in task,
        "无残留模板变量": "{{code}}" not in task and "{{name}}" not in task,
        "任务上下文标记": "🎯 任务上下文" in task,
    }
    
    all_pass = True
    for name, passed in checks.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {name}: {passed}")
        if not passed:
            all_pass = False
    
    # 清理测试目录
    import shutil
    shutil.rmtree('/Users/allen/.openclaw/workspace/.deepflow/blackboard/test_build_task', ignore_errors=True)
    
    return all_pass

def test_prompt_no_outdated_instructions():
    """测试提示词不包含过时指令"""
    print("\n" + "=" * 60)
    print("测试 3: 提示词过时指令检查")
    print("=" * 60)
    
    prompt_files = [
        "prompts/investment/researcher_enhanced.md",
        "prompts/investment/researcher_tech.md",
        "prompts/investment/researcher_market.md",
    ]
    
    outdated_patterns = [
        "调用 `sessions_spawn` 工具启动子 Agent",
        "我将调用 sessions_spawn",
        "等待所有子 Agent 返回",
    ]
    
    base_dir = "/Users/allen/.openclaw/workspace/.deepflow"
    all_pass = True
    
    for prompt_file in prompt_files:
        file_path = os.path.join(base_dir, prompt_file)
        if not os.path.exists(file_path):
            print(f"  ⚠️  文件不存在: {prompt_file}")
            continue
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        has_outdated = any(pattern in content for pattern in outdated_patterns)
        status = "❌" if has_outdated else "✅"
        print(f"  {status} {prompt_file}: {'包含过时指令' if has_outdated else '干净'}")
        
        if has_outdated:
            all_pass = False
    
    return all_pass

def run_all_tests():
    print("\n" + "=" * 70)
    print("Task 增强和模板变量替换验证")
    print("=" * 70)
    
    results = []
    
    try:
        results.append(("模板变量替换", test_replace_template_vars()))
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        results.append(("模板变量替换", False))
    
    try:
        results.append(("Worker Task 构建", test_build_worker_task()))
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        results.append(("Worker Task 构建", False))
    
    try:
        results.append(("提示词过时指令检查", test_prompt_no_outdated_instructions()))
    except Exception as e:
        print(f"  ❌ 异常: {e}")
        results.append(("提示词过时指令检查", False))
    
    # 汇总
    print("\n" + "=" * 70)
    print("验证结果汇总")
    print("=" * 70)
    
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status}: {name}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "=" * 70)
    if all_passed:
        print("🎉 所有验证通过！Task 增强和模板变量替换修复完成。")
    else:
        print("⚠️  有验证未通过，需要检查。")
    print("=" * 70)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(run_all_tests())
