#!/usr/bin/env python3
"""
PipelineEngine spawn 功能验证脚本

验证清单：
1. PipelineEngine.__init__ 接受 spawn_fn 参数
2. _do_spawn_agent 优先使用注入的 spawn_fn
3. _run_single_agent 等待 Worker 完成并返回真实结果
4. orchestrator_agent.py 传入 sessions_spawn
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


def check_pipeline_engine():
    """验证 pipeline_engine.py"""
    filepath = ROOT / "pipeline_engine.py"
    violations = []

    if not filepath.exists():
        print("❌ pipeline_engine.py 不存在")
        return 1

    with open(filepath) as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"❌ 语法错误: {e}")
        return 1

    # 1. 检查 PipelineEngine 类的 __init__ 是否接受 spawn_fn 参数
    init_found = False
    spawn_fn_param = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == 'PipelineEngine':
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                    init_found = True
                    args = item.args
                    arg_names = [arg.arg for arg in args.args + args.kwonlyargs]
                    
                    if 'spawn_fn' in arg_names:
                        spawn_fn_param = True
                        print("✅ PipelineEngine.__init__ 接受 spawn_fn 参数")
                    else:
                        violations.append(Violation(
                            "P0", "spawn_fn参数缺失", item.lineno,
                            "PipelineEngine.__init__ 必须接受 spawn_fn 参数用于注入 sessions_spawn 工具"
                        ))
                    break
            break

    if not init_found:
        violations.append(Violation("P0", "__init__未找到", 0, "未找到 __init__ 方法"))

    # 2. 检查 _do_spawn_agent 是否优先使用 self._spawn_fn
    do_spawn_found = False
    uses_spawn_fn = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == '_do_spawn_agent':
            do_spawn_found = True
            # 检查函数体中是否引用 self._spawn_fn
            for child in ast.walk(node):
                if isinstance(child, ast.Attribute):
                    if child.attr == '_spawn_fn':
                        uses_spawn_fn = True
                elif isinstance(child, ast.Name):
                    if child.id == '_spawn_fn':
                        uses_spawn_fn = True
            
            if uses_spawn_fn:
                print("✅ _do_spawn_agent 使用 self._spawn_fn")
            else:
                violations.append(Violation(
                    "P0", "spawn_fn未使用", node.lineno,
                    "_do_spawn_agent 必须优先使用注入的 spawn_fn"
                ))
            break

    if not do_spawn_found:
        violations.append(Violation("P0", "_do_spawn_agent未找到", 0, "未找到 _do_spawn_agent 方法"))

    # 3. 检查 _run_single_agent 是否返回 Worker 结果（不是元数据）
    run_single_found = False
    returns_result = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == '_run_single_agent':
            run_single_found = True
            # 检查返回值是否包含真实结果
            for child in ast.walk(node):
                if isinstance(child, ast.Return):
                    # 检查返回的是否是 StageResult 且包含真实结果
                    if isinstance(child.value, ast.Call):
                        if isinstance(child.value.func, ast.Name) and child.value.func.id == 'StageResult':
                            # 检查关键字参数
                            keywords = {kw.arg for kw in child.value.keywords}
                            if 'output' in keywords:
                                # 检查 output 是否包含 agent_id（这是元数据）
                                for kw in child.value.keywords:
                                    if kw.arg == 'output':
                                        if isinstance(kw.value, ast.Dict):
                                            keys = []
                                            for k in kw.value.keys:
                                                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                                    keys.append(k.value)
                                            if 'agent_id' in keys and len(keys) <= 2:
                                                violations.append(Violation(
                                                    "P0", "返回元数据", child.lineno,
                                                    "_run_single_agent 返回的是元数据(agent_id)，不是Worker真实结果"
                                                ))
                                            else:
                                                returns_result = True
            break

    if not run_single_found:
        violations.append(Violation("P0", "_run_single_agent未找到", 0, "未找到 _run_single_agent 方法"))

    # 4. 检查 orchestrator_agent.py 是否传入 sessions_spawn
    orch_filepath = ROOT / "orchestrator_agent.py"
    if orch_filepath.exists():
        with open(orch_filepath) as f:
            orch_source = f.read()
        
        if 'spawn_fn=' in orch_source or 'spawn_fn =' in orch_source:
            print("✅ orchestrator_agent.py 传入 spawn_fn")
        else:
            violations.append(Violation(
                "P0", "spawn_fn未传入", 0,
                "orchestrator_agent.py 创建 PipelineEngine 时必须传入 spawn_fn=sessions_spawn"
            ))
    else:
        violations.append(Violation("P0", "orchestrator_agent.py不存在", 0, "文件不存在"))

    # 输出结果
    print(f"\n{'='*60}")
    print(f"验证结果: PipelineEngine spawn 功能")
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
    sys.exit(check_pipeline_engine())
