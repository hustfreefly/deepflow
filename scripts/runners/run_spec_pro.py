#!/usr/bin/env python3
"""
run_spec_pro.py — Spec Pro 独立运行脚本

用途：在 exec 环境中运行 Spec Pro 完整管线（init → 多轮对话 → done → 输出 LivingSpec）

使用方式：
    python3 run_spec_pro.py --mode standard --scenario genesis "我需要一个智能客服系统"
    
    或者交互式：
    python3 run_spec_pro.py --interactive

输出：
    blackboard/{session_id}/spec/living_spec.json
"""

import sys
import os
import json
import argparse
from pathlib import Path

# DeepFlow 基础路径
DEEPFLOW_BASE = str(Path(__file__).resolve().parents[2])
if DEEPFLOW_BASE not in sys.path:
    sys.path.insert(0, DEEPFLOW_BASE)
from core.config.path_config import PathConfig
DEEPFLOW_BASE = str(PathConfig.resolve().base_dir)
if DEEPFLOW_BASE not in sys.path:
    sys.path.insert(0, DEEPFLOW_BASE)

from domains.spec_pro import SpecProCoordinator, LivingSpec


def run_spec_pro(user_input: str, mode: str = "standard", scenario: str = "genesis") -> dict:
    """
    运行 Spec Pro 完整流程（模拟用户交互）。

    注意：在真实场景中，用户的每轮回答来自主 Agent 的飞书/Telegram 交互。
    本脚本用于验证端到端流程。

    Args:
        user_input: 初始需求描述
        mode: quick/standard/deep
        scenario: genesis/supplement/refine/pivot

    Returns:
        最终 Living Spec
    """
    print("=" * 70)
    print(f"Spec Pro — {mode.upper()} mode, {scenario}")
    print("=" * 70)

    # Step 1: 初始化
    coord = SpecProCoordinator(scenario=scenario, mode=mode)
    result = coord.init_session(user_input)

    session_id = result["session_id"]
    base_path = result["base_path"]
    task = result["orchestrator_task"]

    print(f"\n✅ Session: {session_id}")
    print(f"✅ Blackboard: {base_path}")
    print(f"✅ Round 1 Task: {len(task)} chars")

    # Step 2: 模拟多轮对话（真实场景由主 Agent 处理）
    # 这里仅做验证：检查 Coordinator 能正确管理轮次
    for round_num in range(2, 5):
        response = f"[模拟回答] 第{round_num}轮用户补充"
        round_result = coord.build_next_round_task(response)
        
        if "action" in round_result and round_result["action"] == "safety_stop":
            print(f"\n⏹️  Round {round_result.get('round_num', '?')}: {round_result['reason']}")
            break
        
        print(f"✅ Round {round_result['round_num']} Task: {len(round_result['orchestrator_task'])} chars")

    # Step 3: 状态检查
    status = coord.get_status()
    print(f"\n📊 Final Status:")
    print(f"   Rounds: {status['current_round']}")
    print(f"   State: {status['state']}")
    print(f"   Done: {coord.is_done()}")

    # Step 4: 输出路径
    living_spec_path = os.path.join(base_path, "spec", "living_spec.json")
    print(f"\n📁 Output files:")
    for root, dirs, files in os.walk(os.path.join(base_path, "spec")):
        for f in files:
            path = os.path.join(root, f)
            rel = os.path.relpath(path, base_path)
            size = os.path.getsize(path)
            print(f"   {rel} ({size} bytes)")

    print(f"\n✅ Spec Pro 管线验证完成")
    return {
        "session_id": session_id,
        "base_path": base_path,
        "status": status,
    }


def main():
    parser = argparse.ArgumentParser(description="Spec Pro 运行脚本")
    parser.add_argument("--mode", choices=["quick", "standard", "deep"], default="standard")
    parser.add_argument("--scenario", choices=["genesis", "supplement", "refine", "pivot"], default="genesis")
    parser.add_argument("--interactive", action="store_true", help="交互模式")
    parser.add_argument("user_input", nargs="?", help="初始需求描述")

    args = parser.parse_args()

    if args.interactive:
        print("=" * 70)
        print("Spec Pro — 交互模式")
        print("输入 'quit' 退出")
        print("=" * 70)
        
        user_input = input("\n请输入你的需求: ").strip()
        if not user_input or user_input == "quit":
            print("已取消")
            return

        coord = SpecProCoordinator(scenario=args.scenario, mode=args.mode)
        result = coord.init_session(user_input)

        print(f"\n✅ Session: {result['session_id']}")
        print(f"✅ Blackboard: {result['base_path']}")
        print(f"\n📋 Round 1 任务已生成 ({len(result['orchestrator_task'])} chars)")
        print("⚠️  注意：真实场景需要主 Agent spawn Orchestrator Worker 来执行")
        print("    本脚本仅验证 Coordinator 功能")

        # 交互循环
        round_num = 1
        while True:
            round_num += 1
            user_response = input(f"\n第 {round_num} 轮回答 (或 'done' 结束): ").strip()
            if user_response == "done":
                break
            
            result = coord.build_next_round_task(user_response)
            if "safety_stop" in str(result.get("action", "")):
                print(f"⏹️  {result.get('reason', 'max rounds')}")
                break
            
            print(f"✅ Round {result['round_num']} 任务已生成")

        status = coord.get_status()
        print(f"\n📊 Final: {status}")

    else:
        if not args.user_input:
            print("错误：请提供 user_input 或使用 --interactive")
            parser.print_help()
            return 1

        run_spec_pro(args.user_input, mode=args.mode, scenario=args.scenario)
        return 0


if __name__ == "__main__":
    sys.exit(main())  # F3: 确保错误时 exit code 非零
