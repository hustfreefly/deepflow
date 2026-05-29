#!/usr/bin/env python3
"""
spec_pro_api.py — Spec Pro API for Agent Calls

用途：让主 Agent 通过 exec 调用 Spec Pro Coordinator API

支持命令：
  init <user_input> [--mode standard] [--scenario genesis]
  next_round <session_id> <user_response>
  read_output <session_id>
  status <session_id>
  confirm <session_id> <action> [revisions_json]

输出：JSON 格式结果

使用示例：
  python3 spec_pro_api.py init "我需要一个智能客服系统" --mode standard
  python3 spec_pro_api.py next_round spec_xxx "我需要支持多语言"
  python3 spec_pro_api.py read_output spec_xxx
  python3 spec_pro_api.py status spec_xxx
  python3 spec_pro_api.py confirm spec_xxx confirm
"""

import sys
import os
import json
import argparse
from pathlib import Path

# DeepFlow 基础路径
from core.config.path_config import PathConfig
DEEPFLOW_BASE = str(PathConfig.resolve().base_dir)
sys.path.insert(0, DEEPFLOW_BASE)

from core.spec_pro import SpecProCoordinator


def save_coord_state(coord: SpecProCoordinator) -> str:
    """保存 Coordinator 状态到文件"""
    state = {
        "session_id": coord.session_id,
        "base_path": coord.base_path,
        "scenario": coord.scenario,
        "mode": coord.mode,
        "current_round": coord.current_round,
        "state": coord.state.value,
    }
    state_path = os.path.join(coord.base_path, "coord_state.json")
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return state_path


def load_coord_state(session_id: str) -> dict:
    """加载 Coordinator 状态"""
    # 查找 session 目录
    blackboard_dir = os.path.join(DEEPFLOW_BASE, "blackboard")
    session_dir = None
    for d in os.listdir(blackboard_dir):
        if d == session_id:
            session_dir = os.path.join(blackboard_dir, d)
            break
    
    if not session_dir:
        raise ValueError(f"Session not found: {session_id}")
    
    state_path = os.path.join(session_dir, "coord_state.json")
    if not os.path.exists(state_path):
        raise ValueError(f"State file not found: {state_path}")
    
    with open(state_path, "r", encoding="utf-8") as f:
        return json.load(f)


def reconstruct_coord(state: dict) -> SpecProCoordinator:
    """从状态重建 Coordinator。

    修复: __init__ 会正确初始化 _config（通过 mode），
    然后恢复被序列化的状态字段。
    """
    from core.spec_pro.models import DialogState

    coord = SpecProCoordinator(
        scenario=state["scenario"],
        mode=state["mode"],  # __init__ 会正确设置 self._config = MODE_CONFIG[mode]
    )
    coord.session_id = state["session_id"]
    coord.base_path = state["base_path"]
    coord.current_round = state["current_round"]
    # 恢复 DialogState 枚举（JSON 中存的是字符串）
    state_val = state.get("state", "start")
    try:
        coord.state = DialogState(state_val)
    except ValueError:
        coord.state = DialogState.START
    return coord


def cmd_init(args):
    """初始化 session"""
    coord = SpecProCoordinator(
        scenario=args.scenario,
        mode=args.mode,
    )
    
    result = coord.init_session(args.user_input)
    save_coord_state(coord)
    
    return {
        "success": True,
        "session_id": result["session_id"],
        "base_path": result["base_path"],
        "orchestrator_task": result["orchestrator_task"],
        "message": f"Session initialized: {result['session_id']}",
    }


def cmd_next_round(args):
    """构建下一轮任务"""
    state = load_coord_state(args.session_id)
    coord = reconstruct_coord(state)
    
    result = coord.build_next_round_task(args.user_response)
    save_coord_state(coord)
    
    if "safety_stop" in str(result.get("action", "")):
        return {
            "success": True,
            "action": "safety_stop",
            "reason": result.get("reason", "max_rounds"),
            "message": result.get("message", "Max rounds reached"),
        }
    
    return {
        "success": True,
        "round_num": result["round_num"],
        "orchestrator_task": result["orchestrator_task"],
    }


def cmd_read_output(args):
    """读取本轮输出"""
    state = load_coord_state(args.session_id)
    coord = reconstruct_coord(state)
    
    result = coord.read_round_output()
    
    return {
        "success": True,
        "output": result,
    }


def cmd_status(args):
    """获取状态"""
    state = load_coord_state(args.session_id)
    coord = reconstruct_coord(state)
    
    status = coord.get_status()
    is_done = coord.is_done()
    
    return {
        "success": True,
        "status": status,
        "is_done": is_done,
    }


def cmd_confirm(args):
    """确认或修正"""
    state = load_coord_state(args.session_id)
    coord = reconstruct_coord(state)
    
    confirmation = {"action": args.action}
    if args.action == "revise" and args.revisions:
        confirmation["revisions"] = json.loads(args.revisions)
    
    task = coord.build_confirmation_task(confirmation)
    save_coord_state(coord)
    
    return {
        "success": True,
        "orchestrator_task": task,
    }


def main():
    parser = argparse.ArgumentParser(description="Spec Pro API")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # init
    p_init = subparsers.add_parser("init", help="Initialize session")
    p_init.add_argument("user_input", help="Initial user input")
    p_init.add_argument("--mode", choices=["quick", "standard", "deep"], default="standard")
    p_init.add_argument("--scenario", choices=["genesis", "supplement", "refine", "pivot"], default="genesis")
    
    # next_round
    p_next = subparsers.add_parser("next_round", help="Build next round task")
    p_next.add_argument("session_id", help="Session ID")
    p_next.add_argument("user_response", help="User response")
    
    # read_output
    p_read = subparsers.add_parser("read_output", help="Read round output")
    p_read.add_argument("session_id", help="Session ID")
    
    # status
    p_status = subparsers.add_parser("status", help="Get status")
    p_status.add_argument("session_id", help="Session ID")
    
    # confirm
    p_confirm = subparsers.add_parser("confirm", help="Confirm or revise")
    p_confirm.add_argument("session_id", help="Session ID")
    p_confirm.add_argument("action", choices=["confirm", "revise"])
    p_confirm.add_argument("revisions", nargs="?", help="Revisions JSON (for revise)")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        if args.command == "init":
            result = cmd_init(args)
        elif args.command == "next_round":
            result = cmd_next_round(args)
        elif args.command == "read_output":
            result = cmd_read_output(args)
        elif args.command == "status":
            result = cmd_status(args)
        elif args.command == "confirm":
            result = cmd_confirm(args)
        else:
            parser.print_help()
            return 1
        
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
        
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    main()
