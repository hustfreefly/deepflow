#!/usr/bin/env python3
"""
契约笼子验证脚本

用法：
  python cage/validate.py [module]        # 验证单个模块
  python cage/validate.py --all           # 验证所有模块
  python cage/validate.py --list          # 列出所有契约文件
  python cage/validate.py --discover      # 自动发现契约文件
"""

import argparse
import sys
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).parent.parent
CAGE_DIR = ROOT / "cage"
SCHEMA_FILE = CAGE_DIR / "schema.yaml"

# 契约文件大小限制（分级：简单/中等/复杂）
# 估算：方法数 × 150 字符，预留余量给详细契约
SIZE_LIMITS = {
    "simple": 2000,    # ≤10 方法，约200行代码
    "medium": 6000,    # 10-20 方法，约350行代码（预留1KB余量）
    "complex": 10000,  # >20 方法，约500行代码
}
DEFAULT_MAX_CHARS = SIZE_LIMITS["simple"]

# 必需字段
REQUIRED_FIELDS = ["module", "version", "interface", "behavior", "boundaries"]


def discover_modules() -> list[str]:
    """从 cage/ 目录自动发现契约文件（排除 schema.yaml）"""
    return sorted(
        f.stem for f in CAGE_DIR.glob("*.yaml")
        if f.stem != "schema"
    )


def discover_module_files() -> dict[str, str]:
    """从项目根目录自动发现 Python 模块"""
    return {
        f.stem: f.name
        for f in ROOT.glob("*.py")
        if f.stem not in ("__init__", "protocols")
    }


def load_yaml(filepath: str) -> dict:
    """加载 YAML 文件"""
    try:
        import yaml
        with open(filepath, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return None
    except yaml.YAMLError as e:
        print(f"  ❌ YAML 解析错误: {e}")
        return None


def get_size_limit(data: dict) -> int:
    """根据契约复杂度返回大小限制"""
    complexity = data.get("complexity", "simple")
    return SIZE_LIMITS.get(complexity, DEFAULT_MAX_CHARS)


def validate_dependencies(module: str, data: dict) -> bool:
    """验证声明的依赖是否在代码中实际调用"""
    dependencies = data.get("dependencies", [])
    if not dependencies:
        return True

    # 读取对应 Python 文件
    code_file = ROOT / f"{module}.py"
    if not code_file.exists():
        print(f"  ⚠️ 代码文件不存在: {code_file.name}（跳过依赖验证）")
        return True

    code = code_file.read_text(encoding='utf-8')

    for dep in dependencies:
        # dep 格式: "module.method"
        parts = dep.split(".")
        if len(parts) != 2:
            print(f"  ❌ 依赖格式错误: {dep}（应为 module.method）")
            return False

        dep_module, dep_method = parts

        # 检查代码中是否包含依赖的方法名
        if dep_method not in code:
            print(f"  ❌ 依赖未在实际代码中调用: {dep}")
            return False

    return True


def validate_contract(module: str) -> bool:
    """验证单个模块契约"""
    contract_file = CAGE_DIR / f"{module}.yaml"

    print(f"\n{'='*60}")
    print(f"验证模块: {module}")
    print(f"契约文件: {contract_file}")

    # 检查 1: 文件存在
    if not contract_file.exists():
        print(f"  ❌ 契约文件不存在")
        return False
    print(f"  ✅ 契约文件存在")

    # 检查 2: 文件大小（分级限制）
    file_size = contract_file.stat().st_size
    data = load_yaml(str(contract_file))

    if data is None:
        print(f"  ❌ YAML 解析失败")
        return False

    size_limit = get_size_limit(data)
    if file_size > size_limit:
        print(f"  ❌ 契约文件过大: {file_size} 字符（限制 {size_limit}，复杂度: {data.get('complexity', 'simple')}）")
        return False
    print(f"  ✅ 契约文件大小: {file_size} 字符（≤ {size_limit}）")

    # 检查 3: YAML 解析（已在检查 2 中完成）
    print(f"  ✅ YAML 解析成功")

    # 检查 4: 必需字段
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        print(f"  ❌ 缺少必需字段: {missing}")
        return False
    print(f"  ✅ 所有必需字段存在: {REQUIRED_FIELDS}")

    # 检查 5: 接口与行为对齐
    interface = data.get("interface", {})
    behavior = data.get("behavior", {})

    interface_methods = set(interface.keys()) if isinstance(interface, dict) else set()
    behavior_methods = set(behavior.keys()) if isinstance(behavior, dict) else set()

    if interface_methods != behavior_methods:
        print(f"  ❌ 接口与行为方法不对齐")
        print(f"     接口有: {interface_methods}")
        print(f"     行为有: {behavior_methods}")
        return False
    print(f"  ✅ 接口与行为对齐: {interface_methods}")

    # 检查 6: 边界条件至少 1 条
    boundaries = data.get("boundaries", [])
    if not isinstance(boundaries, list) or len(boundaries) < 1:
        print(f"  ❌ 边界条件至少需要 1 条")
        return False
    print(f"  ✅ 边界条件: {len(boundaries)} 条")

    # 检查 7: 行为契约必须有 success 和 failure
    for method, spec in behavior.items():
        if not isinstance(spec, dict):
            print(f"  ❌ {method} 的行为契约格式错误")
            return False
        if "success" not in spec or "failure" not in spec:
            print(f"  ❌ {method} 缺少 success/failure 定义")
            return False
    print(f"  ✅ 所有方法定义了 success/failure 路径")

    # 检查 8: 依赖验证
    if not validate_dependencies(module, data):
        return False
    print(f"  ✅ 依赖验证通过")

    print(f"  ✅ 验证通过")
    return True


def list_contracts() -> None:
    """列出所有契约文件"""
    modules = discover_modules()
    print("契约文件清单:")
    for module in modules:
        contract_file = CAGE_DIR / f"{module}.yaml"
        if contract_file.exists():
            size = contract_file.stat().st_size
            data = load_yaml(str(contract_file))
            complexity = data.get("complexity", "simple") if data else "?"
            limit = get_size_limit(data) if data else "?"
            print(f"  ✅ {module}.yaml ({size}/{limit} 字符, {complexity})")
        else:
            print(f"  ❌ {module}.yaml (不存在)")


def main() -> None:
    """契约笼子验证脚本入口"""
    parser = argparse.ArgumentParser(description="契约笼子验证脚本")
    parser.add_argument("module", nargs="?", help="模块名")
    parser.add_argument("--all", action="store_true", help="验证所有模块")
    parser.add_argument("--list", action="store_true", help="列出所有契约文件")
    parser.add_argument("--discover", action="store_true", help="自动发现契约文件")
    args = parser.parse_args()

    if args.list:
        list_contracts()
        return

    if args.discover:
        modules = discover_modules()
        print(f"发现 {len(modules)} 个契约文件: {modules}")
        return

    if args.all:
        modules = discover_modules()
        if not modules:
            print("⚠️ 未发现契约文件，请先创建 cage/[module].yaml")
            sys.exit(1)

        print("=" * 60)
        print("验证所有模块契约")
        print("=" * 60)

        results = {}
        for module in modules:
            results[module] = validate_contract(module)

        print(f"\n{'='*60}")
        print("汇总结果")
        print(f"{'='*60}")
        for module, passed in results.items():
            status = "✅ 通过" if passed else "❌ 失败"
            print(f"  {module}: {status}")

        passed_count = sum(1 for v in results.values() if v)
        print(f"\n总计: {passed_count}/{len(modules)} 通过")

        if passed_count < len(modules):
            sys.exit(1)

    elif args.module:
        if validate_contract(args.module):
            print(f"\n✅ {args.module} 契约验证通过")
        else:
            print(f"\n❌ {args.module} 契约验证失败")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
