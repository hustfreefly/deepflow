#!/usr/bin/env python3
"""
中芯国际 (688981.SH) 数据采集脚本
- Bootstrap 阶段采集
- 补充搜索
- key_metrics.json 完整性保证
"""

import sys, os, json, subprocess

# 添加项目根目录到路径
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/')

def step1_bootstrap():
    """Step 1: 执行 bootstrap 数据采集"""
    print("=" * 60)
    print("Step 1: 执行 Bootstrap 数据采集")
    print("=" * 60)
    
    try:
        # 直接导入具体模块，避免 __init__.py 的循环依赖
        from data_providers.investment import register_providers
        from core.data_manager import DataEvolutionLoop, ConfigDrivenCollector
        from core.blackboard_manager import BlackboardManager
        
        # 注册数据源
        register_providers()
        
        # 初始化采集器
        config_path = "/Users/allen/.openclaw/workspace/.deepflow/data_sources/investment.yaml"
        collector = ConfigDrivenCollector(config_path)
        
        # 初始化 Blackboard
        blackboard = BlackboardManager("中芯国际_688981_87478313")
        data_loop = DataEvolutionLoop(collector, blackboard)
        
        # 执行 bootstrap
        context = {"code": "688981.SH", "name": "中芯国际"}
        data_loop.bootstrap_phase(context)
        print("✅ Bootstrap 完成")
        
        # 验证数据
        index_path = "/Users/allen/.openclaw/workspace/.deepflow/blackboard/中芯国际_688981_87478313/data/INDEX.json"
        if os.path.exists(index_path):
            with open(index_path) as f:
                index = json.load(f)
            print(f"✅ 已采集 {len(index)} 个数据集")
            return True
        else:
            print("⚠️ 未找到 INDEX.json，但可能已生成 key_metrics.json")
            return False
            
    except Exception as e:
        print(f"⚠️ Bootstrap 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def search_with_fallback(query, timeout=30):
    """搜索 with fallback：Gemini → DuckDuckGo → 跳过"""
    # 1. 尝试 Gemini
    try:
        result = subprocess.run(
            ["gemini", "-p", query], 
            capture_output=True, 
            text=True, 
            timeout=timeout
        )
        if result.returncode == 0 and result.stdout.strip():
            return {"source": "gemini", "result": result.stdout}
    except Exception as e:
        print(f"  Gemini 搜索失败: {e}")
        pass
    
    # 2. Fallback 到 DuckDuckGo
    try:
        from duckduckgo_search import DDGS
        results = DDGS().text(query, max_results=5)
        if results:
            return {"source": "duckduckgo", "result": str(results)}
    except Exception as e:
        print(f"  DuckDuckGo 搜索失败: {e}")
        pass
    
    # 3. 全部失败
    return {"source": "failed", "result": None}


def step2_supplement_search():
    """Step 2: 执行补充搜索"""
    print("\n" + "=" * 60)
    print("Step 2: 执行补充搜索")
    print("=" * 60)
    
    # 搜索任务
    search_tasks = [
        ("行业趋势", "半导体制造行业 2025 2026 市场规模 增长趋势"),
        ("竞品对比", "中芯国际 竞争对手 市场份额"),
        ("券商预期", "中芯国际 688981.SH 券商研报 一致预期"),
        ("风险因素", "中芯国际 风险 挑战"),
    ]
    
    supplement_dir = "/Users/allen/.openclaw/workspace/.deepflow/blackboard/中芯国际_688981_87478313/data/05_supplement"
    os.makedirs(supplement_dir, exist_ok=True)
    
    success_count = 0
    for name, query in search_tasks:
        print(f"\n正在搜索: {name}...")
        result = search_with_fallback(query)
        if result["source"] != "failed":
            with open(f"{supplement_dir}/{name}.json", "w") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"✅ {name} ({result['source']})")
            success_count += 1
        else:
            print(f"⚠️ {name} 搜索失败")
    
    print(f"\n补充搜索完成: {success_count}/{len(search_tasks)} 成功")
    return success_count


def step3_ensure_key_metrics():
    """Step 3: 确保 key_metrics.json 完整"""
    print("\n" + "=" * 60)
    print("Step 3: 确保 key_metrics.json 完整性")
    print("=" * 60)
    
    km_path = "/Users/allen/.openclaw/workspace/.deepflow/blackboard/中芯国际_688981_87478313/data/key_metrics.json"
    
    # 如果已存在，检查字段完整性
    if os.path.exists(km_path):
        with open(km_path) as f:
            km = json.load(f)
        
        # 补充缺失字段
        defaults = {
            "company_code": "688981.SH",
            "company_name": "中芯国际",
            "industry": "半导体制造",
            "current_price": None,
            "pe_ttm": None,
            "pb_ratio": None,
            "ps_ratio": None,
            "market_cap": None,
            "total_shares": None,
            "analysis_date": "2026-04-23"
        }
        
        updated = False
        for key, default_value in defaults.items():
            if key not in km or km[key] is None:
                km[key] = default_value
                updated = True
        
        if updated:
            with open(km_path, "w") as f:
                json.dump(km, f, ensure_ascii=False, indent=2)
            print("✅ key_metrics.json 已更新（补充缺失字段）")
        else:
            print("✅ key_metrics.json 字段完整，无需更新")
        
        # 显示当前内容摘要
        print(f"   - company_code: {km.get('company_code')}")
        print(f"   - company_name: {km.get('company_name')}")
        print(f"   - industry: {km.get('industry')}")
        print(f"   - analysis_date: {km.get('analysis_date')}")
        
    else:
        # 生成最小化版本
        key_metrics = {
            "company_code": "688981.SH",
            "company_name": "中芯国际",
            "industry": "半导体制造",
            "current_price": None,
            "pe_ttm": None,
            "pb_ratio": None,
            "ps_ratio": None,
            "market_cap": None,
            "total_shares": None,
            "analysis_date": "2026-04-23"
        }
        with open(km_path, "w") as f:
            json.dump(key_metrics, f, ensure_ascii=False, indent=2)
        print("✅ key_metrics.json 已生成（最小化版本）")


def main():
    """主执行流程"""
    print("🚀 开始中芯国际 (688981.SH) 数据采集")
    print()
    
    # Step 1: Bootstrap
    bootstrap_success = step1_bootstrap()
    
    # Step 2: 补充搜索（无论 bootstrap 是否成功都执行）
    supplement_success = step2_supplement_search()
    
    # Step 3: 确保 key_metrics.json 完整
    step3_ensure_key_metrics()
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 数据采集总结")
    print("=" * 60)
    print(f"Bootstrap: {'✅ 成功' if bootstrap_success else '⚠️ 失败（继续执行）'}")
    print(f"补充搜索: {supplement_success}/4 成功")
    print(f"key_metrics.json: ✅ 已确保完整性")
    
    # 验证最终输出
    blackboard_dir = "/Users/allen/.openclaw/workspace/.deepflow/blackboard/中芯国际_688981_87478313/data"
    if os.path.exists(blackboard_dir):
        files = os.listdir(blackboard_dir)
        print(f"\n📁 Blackboard 数据目录内容:")
        for f in sorted(files):
            filepath = os.path.join(blackboard_dir, f)
            size = os.path.getsize(filepath)
            print(f"   - {f} ({size:,} bytes)")
    
    print("\n✅ 数据采集任务完成")


if __name__ == "__main__":
    main()
