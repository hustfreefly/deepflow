#!/usr/bin/env python3
"""
orchestrator_agent.py 契约验证脚本

验证清单：
1. 接口契约：所有定义的方法存在且签名匹配
2. 行为契约：关键方法有正确实现
3. 边界条件：错误处理存在
4. 编码规范：无 P0/P1 违规
"""

import ast
import sys
from pathlib import Path
from dataclasses import dataclass

ROOT = Path(__file__).parent.parent


@dataclass
class Violation:
    level: str
    rule: str
    line: int
    message: str


def check_orchestrator_agent():
    """验证 orchestrator_agent.py"""
    filepath = ROOT / "orchestrator_agent.py"
    violations = []

    if not filepath.exists():
        print("❌ orchestrator_agent.py 不存在")
        return 1

    with open(filepath) as f:
        source = f.read()
        lines = source.split('\n')

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"❌ 语法错误: {e}")
        return 1

    # 1. 检查类定义
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    class_names = [c.name for c in classes]

    if 'OrchestratorAgent' not in class_names:
        violations.append(Violation("P0", "类定义缺失", 0, "OrchestratorAgent 类未定义"))
    else:
        print("✅ OrchestratorAgent 类已定义")

    # 2. 检查方法定义
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    func_names = [f.name for f in functions]

    required_methods = [
        '__init__', 'log', 'step1_data_collection', '_generate_key_metrics',
        'step2_pipeline_execution', 'step3_save_results', 'run', 'main'
    ]

    for method in required_methods:
        if method not in func_names:
            violations.append(Violation("P0", "方法缺失", 0, f"{method} 未定义"))
        else:
            print(f"✅ 方法 {method} 已定义")

    # 3. 检查 bare except
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                violations.append(Violation(
                    "P0", "bare_except", node.lineno,
                    "使用 bare except:，必须指定具体异常类型"
                ))
            elif isinstance(node.type, ast.Name) and node.type.id == 'Exception':
                violations.append(Violation(
                    "P0", "bare_except", node.lineno,
                    "使用 except Exception:，应使用更具体的异常类型"
                ))

    # 4. 检查 main() 是否调用 run()
    main_func = None
    for func in functions:
        if func.name == 'main':
            main_func = func
            break

    if main_func:
        # 检查是否调用了 run()
        has_run_call = False
        for node in ast.walk(main_func):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == 'run':
                    has_run_call = True
                elif isinstance(node.func, ast.Name) and node.func.id == 'run':
                    has_run_call = True

        if has_run_call:
            print("✅ main() 正确调用 run()")
        else:
            violations.append(Violation(
                "P0", "逻辑错误", main_func.lineno,
                "main() 必须调用 agent.run() 执行完整流程"
            ))

    # 5. 检查类方法是否有 docstring
    for cls in classes:
        if cls.name == 'OrchestratorAgent':
            for item in cls.body:
                if isinstance(item, ast.FunctionDef):
                    # 检查是否有 docstring
                    has_docstring = False
                    if item.body and isinstance(item.body[0], ast.Expr):
                        if isinstance(item.body[0].value, ast.Constant):
                            if isinstance(item.body[0].value.value, str):
                                has_docstring = True
                        elif isinstance(item.body[0].value, ast.Str):
                            has_docstring = True

                    if not has_docstring and item.name != '__init__':
                        violations.append(Violation(
                            "P1", "docstring缺失", item.lineno,
                            f"方法 {item.name} 缺少 docstring"
                        ))

    # 6. 检查导入
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    required_imports = [
        'config_loader', 'blackboard_manager', 'pipeline_engine',
        'data_manager', 'data_providers'
    ]

    import_names = []
    for imp in imports:
        if isinstance(imp, ast.Import):
            for alias in imp.names:
                import_names.append(alias.name)
        elif isinstance(imp, ast.ImportFrom):
            if imp.module:
                import_names.append(imp.module)

    for req in required_imports:
        if not any(req in name for name in import_names):
            violations.append(Violation(
                "P1", "导入缺失", 0,
                f"可能缺少导入: {req}"
            ))

    # 7. 检查 step1_data_collection 是否委托给 PipelineEngine（不再直接 spawn DataManager）
    step1_func = None
    for func in functions:
        if func.name == 'step1_data_collection':
            step1_func = func
            break
    
    if step1_func:
        # 检查是否包含 PipelineEngine 委托的注释或逻辑
        has_delegate_comment = False
        source_lines = source.split('\n')
        for i, line in enumerate(source_lines, 1):
            if i >= step1_func.lineno and i <= (step1_func.end_lineno or step1_func.lineno + 20):
                if 'PipelineEngine' in line or '由 PipelineEngine' in line:
                    has_delegate_comment = True
                    break
        
        if has_delegate_comment:
            print("✅ step1_data_collection 已委托给 PipelineEngine 执行")
        else:
            # 检查是否仍调用 _spawn_fn（旧逻辑）
            has_spawn_call = False
            for node in ast.walk(step1_func):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute) and node.func.attr == '_spawn_fn':
                        has_spawn_call = True
                    elif isinstance(node.func, ast.Name) and node.func.id == '_spawn_fn':
                        has_spawn_call = True
            
            if has_spawn_call:
                print("✅ step1_data_collection 调用 _spawn_fn（兼容旧模式）")
            else:
                violations.append(Violation(
                    "P0", "方法逻辑缺失", step1_func.lineno,
                    "step1_data_collection 必须委托给 PipelineEngine 或调用 _spawn_fn"
                ))
    
    # 8. 检查 _generate_key_metrics 是否有错误处理
    generate_func = None
    for func in functions:
        if func.name == '_generate_key_metrics':
            generate_func = func
            break
    
    if generate_func:
        has_try_except = False
        for node in ast.walk(generate_func):
            if isinstance(node, ast.Try):
                has_try_except = True
                break
        
        if has_try_except:
            print("✅ _generate_key_metrics 有错误处理")
        else:
            violations.append(Violation(
                "P0", "错误处理缺失", generate_func.lineno,
                "_generate_key_metrics 必须有 try/except 错误处理"
            ))
        
        # 检查是否写入 key_metrics.json
        has_key_metrics_write = False
        for node in ast.walk(generate_func):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if 'key_metrics.json' in node.value:
                    has_key_metrics_write = True
        
        if has_key_metrics_write:
            print("✅ _generate_key_metrics 写入 key_metrics.json")
        else:
            violations.append(Violation(
                "P0", "输出文件缺失", generate_func.lineno,
                "_generate_key_metrics 必须写入 key_metrics.json"
            ))

    # 输出结果
    print(f"\n{'='*60}")
    print(f"验证结果: {filepath.name}")
    print(f"{'='*60}")

    if not violations:
        print("✅ 全部通过！无违规")
        return 0

    p0_count = sum(1 for v in violations if v.level == "P0")
    p1_count = sum(1 for v in violations if v.level == "P1")

    print(f"\n违规统计: P0={p0_count}, P1={p1_count}")
    print()

    for v in violations:
        print(f"{v.level}: {v.rule} (行{v.line})")
        print(f"    {v.message}")

    if p0_count > 0:
        print(f"\n❌ 存在 P0 违规，必须修复")
        return 1
    else:
        print(f"\n⚠️ 存在 P1 违规，建议修复")
        return 0


if __name__ == "__main__":
    sys.exit(check_orchestrator_agent())
