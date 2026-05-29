#!/usr/bin/env python3
"""
验证 investment.yaml 精简配置
"""
import yaml
import sys

def load_investment_yaml():
    """加载 investment.yaml"""
    with open("/Users/allen/.openclaw/workspace/.deepflow/domains/investment.yaml") as f:
        return yaml.safe_load(f)

def verify_agents(config):
    """验证 agents 列表"""
    print("=" * 60)
    print("验证 Agents 列表")
    print("=" * 60)
    
    agents = config.get("agents", [])
    agent_roles = [a["role"] for a in agents]
    
    expected = [
        "data_manager",
        "planner",
        "researcher_finance",
        "researcher_tech",
        "researcher_market",
        "researcher_macro_chain",
        "researcher_management",
        "researcher_sentiment",
        "auditor_factual",
        "auditor_upside",
        "auditor_downside",
        "fixer",
        "summarizer"
    ]
    
    forbidden = ["financial", "market", "risk", "verifier"]
    
    all_pass = True
    
    # 检查数量
    if len(agents) == 13:
        print(f"  ✅ Agents 数量正确: {len(agents)}")
    else:
        print(f"  ❌ Agents 数量错误: {len(agents)} (期望: 13)")
        all_pass = False
    
    # 检查期望的 agent 都存在
    for role in expected:
        if role in agent_roles:
            print(f"  ✅ {role}")
        else:
            print(f"  ❌ {role} (缺失)")
            all_pass = False
    
    # 检查禁止的 agent 不存在
    for role in forbidden:
        if role in agent_roles:
            print(f"  ❌ {role} (不应存在)")
            all_pass = False
        else:
            print(f"  ✅ 无 {role}")
    
    return all_pass

def verify_pipeline_stages(config):
    """验证 pipeline stages"""
    print("\n" + "=" * 60)
    print("验证 Pipeline Stages")
    print("=" * 60)
    
    stages = config.get("pipeline", {}).get("stages", [])
    stage_names = [s["name"] for s in stages]
    
    expected = [
        "data_collection",
        "search",
        "planning",
        "research",
        "audit",
        "fix",
        "summarize"
    ]
    
    forbidden = ["financial_analysis", "verify"]
    
    all_pass = True
    
    # 检查数量
    if len(stages) == 7:
        print(f"  ✅ Stages 数量正确: {len(stages)}")
    else:
        print(f"  ❌ Stages 数量错误: {len(stages)} (期望: 7)")
        all_pass = False
    
    # 检查期望的 stage 都存在
    for name in expected:
        if name in stage_names:
            print(f"  ✅ {name}")
        else:
            print(f"  ❌ {name} (缺失)")
            all_pass = False
    
    # 检查禁止的 stage 不存在
    for name in forbidden:
        if name in stage_names:
            print(f"  ❌ {name} (不应存在)")
            all_pass = False
        else:
            print(f"  ✅ 无 {name}")
    
    return all_pass

def verify_convergence(config):
    """验证收敛配置"""
    print("\n" + "=" * 60)
    print("验证收敛配置")
    print("=" * 60)
    
    conv = config.get("convergence", {})
    all_pass = True
    
    # max_iterations
    if conv.get("max_iterations") == 1:
        print(f"  ✅ max_iterations = 1 (单轮模式)")
    else:
        print(f"  ❌ max_iterations = {conv.get('max_iterations')} (期望: 1)")
        all_pass = False
    
    # min_iterations
    if conv.get("min_iterations") == 1:
        print(f"  ✅ min_iterations = 1")
    else:
        print(f"  ❌ min_iterations = {conv.get('min_iterations')} (期望: 1)")
        all_pass = False
    
    # target_score
    if conv.get("target_score") == 0.0:
        print(f"  ✅ target_score = 0.0 (不触发收敛)")
    else:
        print(f"  ⚠️ target_score = {conv.get('target_score')} (期望: 0.0)")
    
    return all_pass

def main():
    print("=" * 60)
    print("Investment Domain 配置验证")
    print("=" * 60)
    
    try:
        config = load_investment_yaml()
    except Exception as e:
        print(f"❌ 加载配置失败: {e}")
        return 1
    
    results = []
    results.append(("Agents", verify_agents(config)))
    results.append(("Pipeline Stages", verify_pipeline_stages(config)))
    results.append(("收敛配置", verify_convergence(config)))
    
    # 汇总
    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status}: {name}")
    
    all_passed = all(r[1] for r in results)
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 所有验证通过！配置正确。")
    else:
        print("⚠️  有验证未通过，需要检查配置。")
    print("=" * 60)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
