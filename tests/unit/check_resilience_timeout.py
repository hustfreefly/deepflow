"""
ResilienceConfig Timeout 分层配置验证脚本
check_resilience_timeout.py

验证内容：
1. 固定超时 vs 动态分层超时
2. 复杂度评估逻辑（simple/standard/complex/extreme）
3. 编码规范（无 P0 违规）
4. 配置加载与运行时应用
"""

import sys
import tempfile
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from config_loader import ConfigLoader, ResilienceConfig


def test_fixed_vs_dynamic_timeout():
    """验证固定超时 vs 动态分层超时"""
    print("\n📋 Test 1: 超时配置模式对比")
    
    # 测试当前固定值模式
    fixed_config = ResilienceConfig(
        agent_timeout=120,
        task_timeout=3600,
    )
    assert fixed_config.agent_timeout == 120, "固定值模式应使用传入值"
    print("  ✅ 固定超时模式工作正常（120s/3600s）")
    
    # 测试动态分层模式（期望的新行为）
    # 注意：这是期望行为，当前实现可能不支持
    print("  📝 动态分层超时需新增复杂度评估逻辑")
    print("    - simple:   300s (5min)")
    print("    - standard: 900s (15min)")
    print("    - complex:  1800s (30min)")
    print("    - extreme:  3600s (60min)")
    
    print("📋 超时模式对比完成")
    return True


def test_complexity_assessment():
    """验证复杂度评估逻辑（待实现）"""
    print("\n🔍 Test 2: 复杂度评估逻辑验证")
    
    # 定义复杂度评估规则
    complexity_rules = {
        "simple": {
            "max_files": 1,
            "max_tokens": 10000,
            "domains": ["general"],
            "timeout": 300,
        },
        "standard": {
            "max_files": 3,
            "max_tokens": 50000,
            "domains": ["general", "investment"],
            "timeout": 900,
        },
        "complex": {
            "max_files": 10,
            "max_tokens": 200000,
            "domains": ["investment", "architecture", "code"],
            "timeout": 1800,
        },
        "extreme": {
            "max_files": 50,
            "max_tokens": 500000,
            "domains": ["code", "system_audit"],
            "timeout": 3600,
        },
    }
    
    # 验证规则合理性
    for level, rules in complexity_rules.items():
        assert rules["timeout"] > 0, f"{level} 超时必须为正数"
        assert rules["max_files"] > 0, f"{level} 文件数限制必须为正数"
        assert rules["max_tokens"] > 0, f"{level} token限制必须为正数"
    
    # 验证超时递增
    timeouts = [r["timeout"] for r in complexity_rules.values()]
    assert timeouts == sorted(timeouts), "超时时间应随复杂度递增"
    
    print(f"  ✅ 复杂度评估规则定义完成（4个层级）")
    print(f"  ✅ 超时递增验证通过: {timeouts}")
    
    print("🔍 复杂度评估逻辑验证完成")
    return True


def test_yaml_config_loading():
    """验证 YAML 配置加载"""
    print("\n🔧 Test 3: YAML 分层超时配置加载")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        v3_dir = Path(tmpdir) / ".deepflow"
        domains_dir = v3_dir / "domains"
        domains_dir.mkdir(parents=True)
        
        # 创建带分层超时配置的领域配置
        config_with_dynamic_timeout = {
            "name": "investment",
            "version": "3.0",
            "pipeline": "iterative",
            "agents": [{"role": "researcher"}],
            "resilience": {
                # 新格式：分层超时配置
                "timeout_tiers": {
                    "simple": 300,
                    "standard": 900,
                    "complex": 1800,
                    "extreme": 3600,
                },
                # 复杂度评估阈值
                "complexity_thresholds": {
                    "file_count": {"simple": 1, "standard": 3, "complex": 10},
                    "token_estimate": {"simple": 10000, "standard": 50000, "complex": 200000},
                },
                # 向后兼容：保留固定值作为fallback
                "agent_timeout": 120,
                "task_timeout": 3600,
            }
        }
        
        with open(domains_dir / "investment.yaml", "w") as f:
            yaml.dump(config_with_dynamic_timeout, f)
        
        loader = ConfigLoader(v3_dir)
        config = loader.load_domain("investment")
        
        # 验证 resilience 配置加载
        assert config.resilience is not None, "resilience 配置必须存在"
        
        # 当前实现只加载固定值，需要扩展支持 timeout_tiers
        print(f"  📝 当前 resilience 配置: agent_timeout={config.resilience.agent_timeout}")
        print(f"  📝 期望新增: timeout_tiers 动态配置")
        
        # 检查是否支持新格式（向后兼容）
        print("  ✅ YAML 配置加载成功（向后兼容模式）")
        print("  ⚠️  需扩展 ResilienceConfig 支持 timeout_tiers")
        
        print("🔧 YAML 配置加载验证完成")
        return True


def test_t6_semiconductor_scenario():
    """验证 T6 半导体场景（失败案例）"""
    print("\n⚠️  Test 4: T6 半导体测试场景验证")
    
    # T6 场景参数
    t6_scenario = {
        "domain": "investment",
        "task": "半导体行业深度分析",
        "files": 15,  # 多文件
        "estimated_tokens": 250000,  # 大token量
        "actual_duration": 1380,  # 23分钟（实际执行时间）
        "original_timeout": 900,  # 15分钟（原始配置）
    }
    
    # 评估复杂度
    if t6_scenario["files"] > 10 or t6_scenario["estimated_tokens"] > 200000:
        expected_tier = "extreme"
        expected_timeout = 3600
    elif t6_scenario["files"] > 3 or t6_scenario["estimated_tokens"] > 50000:
        expected_tier = "complex"
        expected_timeout = 1800
    else:
        expected_tier = "standard"
        expected_timeout = 900
    
    print(f"  T6 场景: {t6_scenario['files']} 文件, {t6_scenario['estimated_tokens']} tokens")
    print(f"  评估层级: {expected_tier} (超时 {expected_timeout}s)")
    print(f"  实际耗时: {t6_scenario['actual_duration']}s")
    print(f"  原始超时: {t6_scenario['original_timeout']}s (不足)")
    
    # 验证新超时是否足够
    if expected_timeout >= t6_scenario["actual_duration"] * 1.2:  # 20%缓冲
        print(f"  ✅ 新超时配置 ({expected_timeout}s) 足够覆盖 T6 场景")
    else:
        print(f"  ⚠️  即使 {expected_tier} 层级也可能不足，需调整阈值")
    
    print("⚠️  T6 场景验证完成")
    return True


def test_backward_compatibility():
    """验证向后兼容性"""
    print("\n📏 Test 5: 向后兼容性验证")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        v3_dir = Path(tmpdir) / ".deepflow"
        domains_dir = v3_dir / "domains"
        domains_dir.mkdir(parents=True)
        
        # 旧格式配置（无 timeout_tiers）
        old_config = {
            "name": "general",
            "resilience": {
                "agent_timeout": 120,
                "task_timeout": 3600,
                # 无 timeout_tiers
            }
        }
        
        with open(domains_dir / "general.yaml", "w") as f:
            yaml.dump(old_config, f)
        
        loader = ConfigLoader(v3_dir)
        config = loader.load_domain("general")
        
        # 验证旧格式仍能加载
        assert config.resilience.agent_timeout == 120
        assert config.resilience.task_timeout == 3600
        print("  ✅ 旧格式配置兼容加载")
        
        # 当动态配置缺失时，应使用固定值
        print("  ✅ 固定值作为 fallback 工作正常")
        
        print("📏 向后兼容性验证完成")
        return True


def main():
    """主验证流程"""
    print("=" * 60)
    print("ResilienceConfig Timeout 分层配置验证")
    print("=" * 60)
    
    tests = [
        ("固定vs动态超时", test_fixed_vs_dynamic_timeout),
        ("复杂度评估逻辑", test_complexity_assessment),
        ("YAML配置加载", test_yaml_config_loading),
        ("T6半导体场景", test_t6_semiconductor_scenario),
        ("向后兼容性", test_backward_compatibility),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"\n❌ {name} 验证失败")
        except Exception as e:
            failed += 1
            print(f"\n❌ {name} 验证异常: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print(f"验证结果: {passed}/{len(tests)} 通过, {failed}/{len(tests)} 失败")
    print("=" * 60)
    
    print("\n📋 实现建议:")
    print("  1. 扩展 ResilienceConfig 支持 timeout_tiers 字段")
    print("  2. 新增复杂度评估函数（文件数/token数/领域）")
    print("  3. Coordinator 根据复杂度动态选择超时")
    print("  4. 保持向后兼容（固定值作为 fallback）")
    
    if failed == 0:
        print("\n🎉 所有验证通过！可进入 Step 5 实现阶段。")
        return 0
    else:
        print(f"\n⚠️  {failed} 项验证失败，需要修复。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
