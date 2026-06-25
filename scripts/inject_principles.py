#!/usr/bin/env python3
"""
inject_principles.py — 从 Spec Pro planning.json 复制约束到 final_result.json

用途：桥接 Spec Pro → Ship Pro 的原则传递缺口
位置：.deepflow/scripts/inject_principles.py

使用方式：
    cd /Users/allen/.openclaw/workspace/.deepflow && python3 scripts/inject_principles.py \
      --planning "blackboard/<session>/stages/planning.json" \
      --final-result "blackboard/<session>/stages/final_result.json"

原理：
    Spec Pro planning 阶段正确提取了 constraints（C-001~C-010），
    但 final_result.json 的 schema 没有 constraints 字段，
    导致约束在 Spec Pro → Ship Pro 交接处丢失。
    
    此脚本读取 planning.json 的 constraints，
    原样复制到 final_result.json 中（不做任何转换）。
    
    后续由 Orchestrator 在 Phase -1 中用 LLM 提取架构原则和平台能力。

AI Native 原则：
    - 脚本只做数据复制（LLM 不擅长的格式转换）
    - 原则提取由 LLM 做（需要理解约束的含义）
"""

import argparse
import json
import os
import sys
from pathlib import Path


def copy_constraints(planning_data: dict, final_result: dict) -> dict:
    """将 planning.json 中的 constraints 原样复制到 final_result.json。"""
    constraints = planning_data.get("data", {}).get("constraints", [])
    
    # 原样复制到顶层
    final_result["constraints"] = constraints
    
    # 同时复制到 final_solution 层级（Ship Pro Architect 会读取这里）
    if "final_solution" not in final_result:
        final_result["final_solution"] = {}
    
    solution = final_result["final_solution"]
    
    if "detailed_solution" not in solution:
        solution["detailed_solution"] = {}
    
    detail = solution["detailed_solution"]
    detail["constraints"] = constraints
    
    return final_result


def main():
    parser = argparse.ArgumentParser(description='从 planning.json 复制约束到 final_result.json')
    parser.add_argument('--planning', required=True, help='planning.json 路径（相对于 .deepflow）')
    parser.add_argument('--final-result', required=True, help='final_result.json 路径（相对于 .deepflow）')
    parser.add_argument('--dry-run', action='store_true', help='只打印，不写入')
    args = parser.parse_args()
    
    deepflow_root = os.path.expanduser('~/.openclaw/workspace/.deepflow')
    
    planning_path = os.path.join(deepflow_root, args.planning)
    final_result_path = os.path.join(deepflow_root, args.final_result)
    
    # 读取文件
    with open(planning_path) as f:
        planning = json.load(f)
    
    with open(final_result_path) as f:
        final_result = json.load(f)
    
    # 复制约束
    constraints = planning.get("data", {}).get("constraints", [])
    
    print(f"📋 从 planning.json 中复制了 {len(constraints)} 条约束:")
    print()
    
    for c in constraints[:10]:
        print(f"  {c.get('id', '?')}: {c.get('description', '')[:60]} [{c.get('priority', '?')}]")
    
    if len(constraints) > 10:
        print(f"  ... 还有 {len(constraints) - 10} 条约束")
    
    if args.dry_run:
        print("\n🔍 Dry run — 不写入文件")
        return
    
    # 复制
    final_result = copy_constraints(planning, final_result)
    
    # 写回
    with open(final_result_path, 'w') as f:
        json.dump(final_result, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ 已复制到 {args.final_result}")
    print(f"   Orchestrator 将在 Phase -1 中用 LLM 提取架构原则和平台能力")


if __name__ == '__main__':
    main()
