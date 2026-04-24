#!/usr/bin/env python3
"""
check_data_manager.py - DataManager 契约验证

验证项：
1. DataProvider 接口完全通用（无领域术语）
2. 原子写入机制
3. 配置驱动采集
4. 数据时效性检查
5. Provider 注册表
"""

import ast
import sys
from pathlib import Path

# Handle both __file__ and exec() contexts
try:
    DEEPFLOW_DIR = Path(__file__).parent.parent.parent
except NameError:
    DEEPFLOW_DIR = Path.cwd()


def check_provider_interface_generic():
    """P0-1: DataProvider 接口不包含领域术语"""
    with open(DEEPFLOW_DIR / "data_manager.py") as f:
        content = f.read()

    # 检查 DataProvider 类定义
    domain_terms = ["financials", "symbol", "stock", "revenue", "profit",
                    "market", "price", "quote"]

    # 找到 DataProvider 类
    class_start = content.find("class DataProvider(ABC):")
    if class_start == -1:
        print("❌ FAIL: DataProvider 类不存在")
        return False

    # 检查 abstract 方法签名
    abstract_section = content[class_start:class_start+500]

    found_issues = []
    for term in domain_terms:
        # 只检查方法名和参数名，不检查注释
        lines = abstract_section.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("#") or line.startswith('"""'):
                continue
            if f"def {term}" in line or f": {term}" in line.split("=")[0]:
                found_issues.append(f"接口包含领域术语: {term}")

    if found_issues:
        for issue in found_issues:
            print(f"❌ FAIL: {issue}")
        return False

    print("✅ PASS: DataProvider 接口完全通用")
    return True


def check_atomic_write():
    """P0-5: 原子写入机制（tmp + rename）"""
    with open(DEEPFLOW_DIR / "data_manager.py") as f:
        content = f.read()

    checks = [
        ("tempfile.mkstemp", "使用临时文件"),
        ("os.fsync", "fsync 确保落盘"),
        ("os.rename", "原子 rename 切换"),
        ("ignore_errors=True", "回滚清理"),
    ]

    all_passed = True
    for pattern, desc in checks:
        if pattern in content:
            print(f"  ✅ {desc}")
        else:
            print(f"  ❌ 缺少: {desc}")
            all_passed = False

    if all_passed:
        print("✅ PASS: 原子写入机制完整")
    else:
        print("❌ FAIL: 原子写入机制不完整")

    return all_passed


def check_config_driven():
    """验证配置驱动采集"""
    with open(DEEPFLOW_DIR / "data_manager.py") as f:
        content = f.read()

    checks = [
        ("ConfigDrivenCollector", "配置驱动采集器"),
        ("resolve_placeholders", "占位符替换"),
        ("ProviderRegistry", "Provider 注册表"),
        ("DataEvolutionLoop", "数据进化循环"),
    ]

    all_passed = True
    for pattern, desc in checks:
        if pattern in content:
            print(f"  ✅ {desc}")
        else:
            print(f"  ❌ 缺少: {desc}")
            all_passed = False

    if all_passed:
        print("✅ PASS: 配置驱动架构完整")
    else:
        print("❌ FAIL: 配置驱动架构不完整")

    return all_passed


def check_data_freshness():
    """P0-7: 数据时效性检查"""
    with open(DEEPFLOW_DIR / "data_manager.py") as f:
        content = f.read()

    checks = [
        ("def is_data_fresh", "时效检查方法"),
        ("max_age_hours", "最大年龄参数"),
        ("collected_at", "采集时间记录"),
        ("expires_at", "过期时间记录"),
    ]

    all_passed = True
    for pattern, desc in checks:
        if pattern in content:
            print(f"  ✅ {desc}")
        else:
            print(f"  ❌ 缺少: {desc}")
            all_passed = False

    if all_passed:
        print("✅ PASS: 数据时效性机制完整")
    else:
        print("❌ FAIL: 数据时效性机制不完整")

    return all_passed


def check_provider_registry():
    """P0-4: Provider 注册机制"""
    with open(DEEPFLOW_DIR / "data_manager.py") as f:
        content = f.read()

    checks = [
        ("class ProviderRegistry", "注册表类"),
        ("def register", "注册方法"),
        ("def get", "获取方法"),
        ("def list_all", "列表方法"),
    ]

    all_passed = True
    for pattern, desc in checks:
        if pattern in content:
            print(f"  ✅ {desc}")
        else:
            print(f"  ❌ 缺少: {desc}")
            all_passed = False

    if all_passed:
        print("✅ PASS: Provider 注册机制完整")
    else:
        print("❌ FAIL: Provider 注册机制不完整")

    return all_passed


def check_investment_provider():
    """验证投资领域 Provider 实现"""
    provider_file = DEEPFLOW_DIR / "data_providers/investment.py"
    if not provider_file.exists():
        print("❌ FAIL: investment.py 不存在")
        return False

    with open(provider_file) as f:
        content = f.read()

    checks = [
        ("class AKShareProvider", "AKShare Provider"),
        ("class SinaProvider", "Sina Provider"),
        ("class WebFetchProvider", "WebFetch Provider"),
        ("def register_providers", "注册函数"),
        ("def validate_finding", "数据验证"),
    ]

    all_passed = True
    for pattern, desc in checks:
        if pattern in content:
            print(f"  ✅ {desc}")
        else:
            print(f"  ❌ 缺少: {desc}")
            all_passed = False

    if all_passed:
        print("✅ PASS: 投资领域 Provider 实现完整")
    else:
        print("❌ FAIL: 投资领域 Provider 不完整")

    return all_passed


def check_yaml_config():
    """验证 YAML 配置文件"""
    yaml_file = DEEPFLOW_DIR / "data_sources/investment.yaml"
    if not yaml_file.exists():
        print("❌ FAIL: investment.yaml 不存在")
        return False

    import yaml
    with open(yaml_file) as f:
        config = yaml.safe_load(f)

    checks = [
        ("domain" in config, "领域声明"),
        ("bootstrap" in config, "bootstrap 配置"),
        ("dynamic_rules" in config, "动态规则"),
        ("extractors" in config, "Extractor 配置"),
        ("quality_rules" in config, "质量约束"),
    ]

    all_passed = True
    for passed, desc in checks:
        if passed:
            print(f"  ✅ {desc}")
        else:
            print(f"  ❌ 缺少: {desc}")
            all_passed = False

    if all_passed:
        print("✅ PASS: YAML 配置完整")
    else:
        print("❌ FAIL: YAML 配置不完整")

    return all_passed


def main():
    print("DataManager 契约验证")
    print("=" * 50)

    results = []
    results.append(("P0-1: 接口通用性", check_provider_interface_generic()))
    results.append(("P0-5: 原子写入", check_atomic_write()))
    results.append(("配置驱动", check_config_driven()))
    results.append(("P0-7: 时效性", check_data_freshness()))
    results.append(("P0-4: Provider 注册", check_provider_registry()))
    results.append(("投资 Provider", check_investment_provider()))
    results.append(("YAML 配置", check_yaml_config()))

    print()
    print("=" * 50)
    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅" if result else "❌"
        print(f"  {status} {name}")

    print()
    if passed == total:
        print(f"全部通过 ✅ ({passed}/{total})")
        return 0
    else:
        print(f"{passed}/{total} 通过，{total - passed} 项失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
