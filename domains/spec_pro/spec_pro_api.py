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
import json
import argparse
from pathlib import Path

import core.bootstrap
from core.config.path_config import PathConfig

DEEPFLOW_BASE = str(PathConfig.resolve().base_dir)

from domains.spec_pro import SpecProCoordinator
from domains.spec_pro.blackboard import BlackboardManager


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
    coord.bb.write("coord_state.json", state)
    return str(coord.bb.session_dir / "coord_state.json")


def load_coord_state(session_id: str) -> dict:
    """加载 Coordinator 状态"""
    bb = BlackboardManager(session_id)
    state = bb.read_json("coord_state.json")
    if state is None:
        raise ValueError(f"State file not found for session: {session_id}")
    return state


def reconstruct_coord(state: dict) -> SpecProCoordinator:
    """从状态重建 Coordinator。

    修复: __init__ 会正确初始化 _config（通过 mode），
    然后恢复被序列化的状态字段。

    Fix 3: 增强健壮性 — base_path 缺失时 fallback 到默认 base_dir，
    始终确保 _bb 可用，避免 next_round 因 NoneType 崩溃。
    """
    from domains.spec_pro.models import DialogState
    from pathlib import Path as _Path

    coord = SpecProCoordinator(
        scenario=state["scenario"],
        mode=state["mode"],  # __init__ 会正确设置 self._config = MODE_CONFIG[mode]
    )
    coord.session_id = state["session_id"]
    # Reconstruct BlackboardManager with correct base_dir from persisted base_path
    persisted_base = state.get("base_path")
    if persisted_base:
        base_dir = _Path(persisted_base).parent  # session_dir's parent is blackboard_dir
        coord._bb = BlackboardManager(coord.session_id, base_dir=str(base_dir))
    else:
        # Fix 3: base_path 缺失时 fallback — 用默认 PathConfig 创建 BlackboardManager
        # 而非留 None 导致后续 build_next_round_task 崩溃
        import logging
        logging.getLogger(__name__).warning(
            f"base_path not in state for session {coord.session_id}, using default base_dir"
        )
        coord._bb = BlackboardManager(coord.session_id)
    coord.current_round = state.get("current_round", 0)
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
        "coordinator_task": result["coordinator_task"],
        "v3_parse_worker_prompt": result.get("v3_parse_worker_prompt"),
        "v3_main_eval_prompt": result.get("v3_main_eval_prompt"),
        "message": f"Session initialized: {result['session_id']}",
    }


def cmd_next_round(args):
    """构建下一轮任务"""
    # Fix 3: 增加错误处理，避免 state 损坏时直接崩溃
    try:
        state = load_coord_state(args.session_id)
    except (ValueError, OSError) as e:
        return {
            "success": False,
            "error": f"Failed to load session state: {e}",
            "hint": "Session may not exist or state file is corrupted. Try re-initializing.",
        }

    try:
        coord = reconstruct_coord(state)
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to reconstruct coordinator: {e}",
            "state_keys": list(state.keys()) if isinstance(state, dict) else "invalid",
        }

    try:
        result = coord.build_next_round_task(args.user_response)
    except RuntimeError as e:
        return {
            "success": False,
            "error": str(e),
            "hint": "BlackboardManager may not be initialized. Check session directory exists.",
            "current_round": coord.current_round,
            "session_id": coord.session_id,
        }

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
        "coordinator_task": result["coordinator_task"],
        "v3_parse_worker_prompt": result.get("v3_parse_worker_prompt"),
        "v3_main_eval_prompt": result.get("v3_main_eval_prompt"),
    }


def cmd_read_output(args):
    """读取本轮输出"""
    state = load_coord_state(args.session_id)
    coord = reconstruct_coord(state)
    
    result = coord.read_round_output()
    save_coord_state(coord)
    
    return {
        "success": True,
        "output": result,
    }


def generate_spec_track(session_dir: Path) -> dict | None:
    """
    ADR-009: 从 living_spec.md 生成 spec_track.json。

    非阻断：任何步骤失败 → log warning，返回 None。
    """
    md_path = session_dir / "spec" / "living_spec.md"
    json_path = session_dir / "spec" / "living_spec.json"

    # Try MD first (native MD output)
    if md_path.exists():
        try:
            from core.track_generator import generate_track_from_md
            return generate_track_from_md(
                md_path=md_path,
                domain="spec_pro",
                output_dir=session_dir / "spec",
            )
        except ImportError:
            pass

    # Fallback to JSON
    if json_path.exists():
        try:
            from core.track_generator import generate_track_from_json
            return generate_track_from_json(
                json_path=json_path,
                domain="spec_pro",
                output_dir=session_dir / "spec",
            )
        except ImportError:
            return None

    return None


def cmd_status(args):
    """获取状态"""
    state = load_coord_state(args.session_id)
    coord = reconstruct_coord(state)
    
    status = coord.get_status()
    is_done = coord.is_done()
    
    # 当 Spec Pro 完成时，写 .completed 标记文件（触发 auto_chain）
    if is_done and hasattr(coord, '_bb') and coord._bb:
        from datetime import datetime
        completed_path = Path(coord._bb.session_dir) / ".completed"
        if not completed_path.exists():
            import json as _json

            # ADR-009: 生成 track.json（在 .completed 之前，非阻断）
            generate_spec_track(Path(coord._bb.session_dir))

            marker = {
                "status": "completed",
                "completed_at": datetime.now().isoformat(),
                "session_id": args.session_id,
            }
            completed_path.write_text(_json.dumps(marker, ensure_ascii=False))
    
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
        try:
            confirmation["revisions"] = json.loads(args.revisions)
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid revisions JSON: {e}"}
    
    task = coord.build_confirmation_task(confirmation)
    save_coord_state(coord)
    
    return {
        "success": True,
        "coordinator_task": task,
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
    sys.exit(main())  # F3: 确保错误时 exit code 非零
