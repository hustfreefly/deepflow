#!/usr/bin/env python3
"""
编码规范检查脚本

用法：
  python cage/check_standards.py [file.py]        # 检查单个文件
  python cage/check_standards.py --all             # 检查所有模块
  python cage/check_standards.py --list            # 列出所有检查项
"""

import argparse
import ast
import sys
from pathlib import Path
from dataclasses import dataclass

# 项目根目录
ROOT = Path(__file__).parent.parent

# 单文件行数限制
MAX_LINES = 500


@dataclass
class Violation:
    """违规记录"""
    level: str  # P0 / P1 / P2
    rule: str
    line: int
    message: str
    file: str


def discover_module_files() -> dict[str, str]:
    """从项目根目录自动发现 Python 模块"""
    return {
        f.stem: f.name
        for f in ROOT.glob("*.py")
        if f.stem not in ("__init__", "protocols")
    }


def check_bare_except(tree: ast.AST, filepath: str) -> list[Violation]:
    """P0: 检查 bare except"""
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                violations.append(Violation(
                    level="P0",
                    rule="bare_except",
                    line=node.lineno,
                    message="禁止使用 bare except",
                    file=filepath,
                ))
    return violations


def check_unused_imports(tree: ast.AST, source: str, filepath: str) -> list[Violation]:
    """P0: 检查未使用的导入（改进版：处理 TYPE_CHECKING 和条件导入）"""
    violations = []

    # 收集所有导入
    imports: dict[str, tuple[str, int]] = {}  # name -> (full_import, line)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name] = (alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module == "TYPE_CHECKING":
                continue  # 跳过 TYPE_CHECKING 块
            for alias in node.names:
                imports[alias.asname or alias.name] = (
                    f"{node.module}.{alias.name}" if node.module else alias.name,
                    node.lineno,
                )

    # 收集所有名称（排除导入行）
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            # 处理 os.path 等情况：检查顶级名称
            if isinstance(node.value, ast.Name):
                names.add(node.value.id)

    # 检查未使用的导入
    for name, (full_import, line) in imports.items():
        if name not in names:
            violations.append(Violation(
                level="P0",
                rule="unused_import",
                line=line,
                message=f"未使用的导入: {full_import}（别名: {name}）",
                file=filepath,
            ))
    return violations


def check_type_annotations(tree: ast.AST, filepath: str) -> list[Violation]:
    """P1: 检查公开方法的类型注解"""
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # 公开方法（不以 _ 开头）
            if not node.name.startswith('_'):
                # 检查返回值注解
                if node.returns is None:
                    violations.append(Violation(
                        level="P1",
                        rule="missing_return_annotation",
                        line=node.lineno,
                        message=f"公开方法 {node.name} 缺少返回值类型注解",
                        file=filepath,
                    ))
                # 检查参数注解
                for arg in node.args.args:
                    if arg.arg == 'self':
                        continue
                    if arg.annotation is None:
                        violations.append(Violation(
                            level="P1",
                            rule="missing_param_annotation",
                            line=node.lineno,
                            message=f"公开方法 {node.name} 的参数 {arg.arg} 缺少类型注解",
                            file=filepath,
                        ))
    return violations


def check_docstrings(tree: ast.AST, filepath: str) -> list[Violation]:
    """P1: 检查公开方法的 docstring（>10行方法才强制）"""
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if not node.name.startswith('_'):
                # 计算方法行数（end_lineno - lineno + 1）
                method_lines = (node.end_lineno or node.lineno) - node.lineno + 1
                # 超过10行的方法才强制docstring
                if method_lines > 10:
                    docstring = ast.get_docstring(node)
                    if not docstring:
                        violations.append(Violation(
                            level="P1",
                            rule="missing_docstring",
                            line=node.lineno,
                            message=f"公开方法 {node.name}（{method_lines}行）缺少 docstring",
                            file=filepath,
                        ))
    return violations


def check_file_length(source: str, filepath: str) -> list[Violation]:
    """P1: 检查文件行数"""
    lines = source.count('\n') + 1
    if lines > MAX_LINES:
        return [Violation(
            level="P1",
            rule="file_too_long",
            line=lines,
            message=f"文件过长: {lines} 行（限制 {MAX_LINES} 行）",
            file=filepath,
        )]
    return []


def check_file(filepath: str) -> list[Violation]:
    """检查单个文件"""
    violations: list[Violation] = []
    filepath = Path(filepath)

    if not filepath.exists():
        print(f"  ❌ 文件不存在: {filepath}")
        return violations

    source = filepath.read_text(encoding='utf-8')

    # 处理空文件
    if not source.strip():
        violations.append(Violation(
            level="P1",
            rule="empty_file",
            line=0,
            message="文件为空",
            file=str(filepath),
        ))
        return violations

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        violations.append(Violation(
            level="P0",
            rule="syntax_error",
            line=e.lineno or 0,
            message=f"语法错误: {e.msg}",
            file=str(filepath),
        ))
        return violations

    # 运行所有检查
    violations.extend(check_bare_except(tree, str(filepath)))
    violations.extend(check_unused_imports(tree, source, str(filepath)))
    violations.extend(check_type_annotations(tree, str(filepath)))
    violations.extend(check_docstrings(tree, str(filepath)))
    violations.extend(check_file_length(source, str(filepath)))

    return violations


def main() -> None:
    """编码规范检查脚本入口"""
    parser = argparse.ArgumentParser(description="编码规范检查脚本")
    parser.add_argument("file", nargs="?", help="Python 文件路径")
    parser.add_argument("--all", action="store_true", help="检查所有模块")
    parser.add_argument("--list", action="store_true", help="列出所有检查项")
    args = parser.parse_args()

    if args.list:
        print("编码规范检查项:")
        print("  P0: bare_except, unused_import, syntax_error")
        print("  P1: missing_return_annotation, missing_param_annotation,")
        print("      missing_docstring, file_too_long, empty_file")
        return

    if args.all:
        module_files = discover_module_files()
        print("=" * 60)
        print("检查所有模块编码规范")
        print("=" * 60)

        all_violations: dict[str, list[Violation]] = {}
        total_p0 = 0

        for module, filename in sorted(module_files.items()):
            filepath = ROOT / filename
            print(f"\n检查: {filename}")
            violations = check_file(filepath)
            all_violations[module] = violations

            p0_count = sum(1 for v in violations if v.level == "P0")
            p1_count = sum(1 for v in violations if v.level == "P1")
            p2_count = sum(1 for v in violations if v.level == "P2")
            total_p0 += p0_count

            if violations:
                for v in violations:
                    print(f"  [{v.level}] 行 {v.line}: {v.message}")
            else:
                print(f"  ✅ 无违规")

        print(f"\n{'='*60}")
        print("汇总结果")
        print(f"{'='*60}")
        for module, violations in sorted(all_violations.items()):
            p0 = sum(1 for v in violations if v.level == "P0")
            p1 = sum(1 for v in violations if v.level == "P1")
            p2 = sum(1 for v in violations if v.level == "P2")
            status = "✅" if p0 == 0 else "❌"
            print(f"  {status} {module}: P0={p0}, P1={p1}, P2={p2}")

        print(f"\n总计: P0={total_p0}")
        if total_p0 > 0:
            print("❌ 存在 P0 违规，不得进入下一阶段")
            sys.exit(1)
        else:
            print("✅ 所有模块 P0=0，编码规范通过")

    elif args.file:
        filepath = Path(args.file)
        print(f"检查: {filepath}")
        violations = check_file(filepath)

        if violations:
            for v in violations:
                print(f"  [{v.level}] 行 {v.line}: {v.message}")

            p0_count = sum(1 for v in violations if v.level == "P0")
            print(f"\nP0={p0_count}")
            if p0_count > 0:
                sys.exit(1)
        else:
            print("  ✅ 无违规")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
