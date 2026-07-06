"""检查 HandoffPackage 契约笼子实施完整性

检查项：
  1. contracts/shared/handoff_contract.py 存在且包含 HandoffPackage 模型
  2. domains/spec_pro/handoff.py 中有 HandoffPackage 引用（产出端验证）
  3. domains/solution_pro/__init__.py 中有 handoff 消费逻辑（消费端验证）

设计意图：
  契约笼子的自检脚本，确保 Spec Pro → Solution Pro 的跨域交接
  有 Pydantic 强类型契约保护，而非裸 dict 传递。

Usage:
  python scripts/checks/check_handoff_contract.py
"""

import sys
from pathlib import Path


def resolve_deepflow_root() -> Path:
    """解析 .deepflow 根目录"""
    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        if (parent / "core" / "blackboard").is_dir():
            return parent
    # fallback: 向上找 .deepflow
    for parent in script_path.parents:
        if parent.name == ".deepflow":
            return parent
    raise RuntimeError("无法定位 .deepflow 根目录")


def check_contract_file_exists(root: Path) -> bool:
    """检查 1: 契约模型文件存在"""
    contract_path = root / "contracts" / "shared" / "handoff_contract.py"
    if not contract_path.exists():
        print(f"  ❌ FAIL: 契约文件不存在: {contract_path}")
        return False
    print(f"  ✅ PASS: 契约文件存在: {contract_path.relative_to(root)}")
    return True


def check_contract_model_defined(root: Path) -> bool:
    """检查 1b: 契约文件中定义了 HandoffPackage 和 DensityGateResult"""
    contract_path = root / "contracts" / "shared" / "handoff_contract.py"
    if not contract_path.exists():
        print(f"  ❌ FAIL: 契约文件不存在，无法检查模型定义")
        return False

    content = contract_path.read_text(encoding="utf-8")
    checks = {
        "HandoffPackage": "class HandoffPackage" in content,
        "DensityGateResult": "class DensityGateResult" in content,
        "field_validator": "field_validator" in content,
        "living_spec_not_empty": "living_spec_not_empty" in content,
        "model_post_init": "model_post_init" in content,
    }

    all_pass = True
    for name, found in checks.items():
        if found:
            print(f"  ✅ PASS: HandoffPackage 包含 {name}")
        else:
            print(f"  ❌ FAIL: HandoffPackage 缺少 {name}")
            all_pass = False
    return all_pass


def check_spec_pro_handoff_integration(root: Path) -> bool:
    """检查 2: spec_pro/handoff.py 中有 HandoffPackage 引用（产出端验证）"""
    handoff_path = root / "domains" / "spec_pro" / "handoff.py"
    if not handoff_path.exists():
        print(f"  ❌ FAIL: handoff.py 不存在: {handoff_path}")
        return False

    content = handoff_path.read_text(encoding="utf-8")
    checks = {
        "HandoffPackage import": "HandoffPackage" in content,
        "handoff_contract import": "handoff_contract" in content,
        "save_handoff_package 验证": "HandoffPackage(**package)" in content or "HandoffPackage(" in content,
    }

    all_pass = True
    for name, found in checks.items():
        if found:
            print(f"  ✅ PASS: spec_pro/handoff.py {name}")
        else:
            print(f"  ❌ FAIL: spec_pro/handoff.py 缺少 {name}")
            all_pass = False
    return all_pass


def check_solution_pro_handoff_integration(root: Path) -> bool:
    """检查 3: solution_pro/__init__.py 中有 handoff 消费逻辑（消费端验证）"""
    init_path = root / "domains" / "solution_pro" / "__init__.py"
    if not init_path.exists():
        print(f"  ❌ FAIL: solution_pro/__init__.py 不存在: {init_path}")
        return False

    content = init_path.read_text(encoding="utf-8")
    checks = {
        "HandoffPackage import": "HandoffPackage" in content,
        "_try_load_handoff_package": "_try_load_handoff_package" in content,
        "handoff_allowed 检查": "handoff_allowed" in content,
        "block_reason 检查": "block_reason" in content,
        "blackboard 扫描": "spec_handoff_package.json" in content,
    }

    all_pass = True
    for name, found in checks.items():
        if found:
            print(f"  ✅ PASS: solution_pro/__init__.py {name}")
        else:
            print(f"  ❌ FAIL: solution_pro/__init__.py 缺少 {name}")
            all_pass = False
    return all_pass


def main() -> int:
    """主检查入口"""
    print("=" * 60)
    print("HandoffPackage 契约笼子检查")
    print("=" * 60)

    try:
        root = resolve_deepflow_root()
    except RuntimeError as e:
        print(f"  ❌ FAIL: {e}")
        return 1

    print(f"\n📁 DeepFlow 根目录: {root}\n")

    results = []

    # 检查 1: 契约模型文件
    print("── 检查 1: 契约模型文件 ──")
    results.append(check_contract_file_exists(root))
    results.append(check_contract_model_defined(root))
    print()

    # 检查 2: Spec Pro 产出端集成
    print("── 检查 2: Spec Pro 产出端集成 ──")
    results.append(check_spec_pro_handoff_integration(root))
    print()

    # 检查 3: Solution Pro 消费端集成
    print("── 检查 3: Solution Pro 消费端集成 ──")
    results.append(check_solution_pro_handoff_integration(root))
    print()

    # 汇总
    passed = sum(results)
    total = len(results)
    print("=" * 60)
    if all(results):
        print(f"✅ 全部通过 ({passed}/{total})")
        return 0
    else:
        print(f"❌ 部分失败 ({passed}/{total})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
