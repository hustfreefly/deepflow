#!/usr/bin/env python3
"""
FixFlow #13: 跨域 handoff 自动化 — DeepFlow 全管线入口

用法:
    # Phase 1: 初始化 Spec Pro（交互式，需要多轮对话）
    python3 scripts/run_full_pipeline.py init --topic "项目名称"

    # Phase 2: 从 Spec Pro 过渡到 Solution Pro
    python3 scripts/run_full_pipeline.py solution --session-id "spec_xxx"

    # Phase 3: 从 Solution Pro 过渡到 Ship Pro
    python3 scripts/run_full_pipeline.py ship --project-name "项目名称"

    # 一键检查全管线状态
    python3 scripts/run_full_pipeline.py status --project-name "项目名称"

设计原则:
- 每个 phase 独立调用（因为 Spec Pro 需要多轮用户交互）
- 自动发现上游输出路径（不需要手动拷贝 blackboard 文件）
- 错误时输出清晰的诊断信息
"""

import argparse
import json
import os
import sys
from pathlib import Path

DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DEEPFLOW_ROOT))


def find_blackboard_dir(session_id: str = None, project_name: str = None) -> Path:
    """自动发现 blackboard 目录"""
    bb_root = DEEPFLOW_ROOT / "blackboard"
    
    if session_id:
        # 精确匹配 session_id
        target = bb_root / session_id
        if target.exists():
            return target
    
    if project_name:
        # 按项目名搜索
        target = bb_root / project_name
        if target.exists():
            return target
        # 模糊搜索
        for d in bb_root.iterdir():
            if d.is_dir() and project_name.lower() in d.name.lower():
                return d
    
    # 搜索最新的 spec_spec_* 目录
    spec_dirs = sorted(bb_root.glob("spec_spec_*"), key=lambda d: d.stat().st_mtime, reverse=True)
    if spec_dirs:
        return spec_dirs[0]
    
    raise FileNotFoundError(f"找不到 blackboard 目录 (session_id={session_id}, project={project_name})")


def cmd_init(args):
    """Phase 1: 初始化 Spec Pro"""
    from domains.spec_pro.spec_pro_api import cmd_init as spec_init
    
    result = spec_init(args.topic)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def cmd_solution(args):
    """Phase 2: Spec Pro → Solution Pro handoff"""
    # 1. 找到 Spec Pro 的 blackboard
    bb_dir = find_blackboard_dir(session_id=args.session_id)
    print(f"📁 Spec Pro blackboard: {bb_dir}")
    
    # 2. 检查 Spec Pro 是否完成（MD-first）
    living_spec = bb_dir / "spec" / "living_spec.md"
    quality_report = bb_dir / "spec" / "quality_report.json"
    
    if not living_spec.exists():
        print(f"❌ living_spec.md 不存在: {living_spec}")
        sys.exit(1)
    
    # 3. 从 handoff package / session_id 提取项目 topic
    handoff_pkg = bb_dir / "spec" / "spec_handoff_package.json"
    topic = args.session_id or bb_dir.name
    if handoff_pkg.exists():
        try:
            package = json.loads(handoff_pkg.read_text())
            topic = (
                package.get("living_spec", {}).get("topic")
                or package.get("living_spec", {}).get("project_name")
                or topic
            )
        except Exception:
            pass
    
    # 4. 构建 Solution Pro 启动参数
    print(f"📋 Topic: {topic}")
    print(f"📊 Quality: {json.loads(quality_report.read_text()).get('weighted_score', 'N/A') if quality_report.exists() else 'N/A'}")
    
    # 5. 调用 start_solution_pro.py
    # B3-FIX: Don't force --living-spec-path; let handoff gate decide
    # If handoff package exists, Solution Pro will auto-load via _try_load_handoff_package()
    # Only fallback to --living-spec-path if handoff package doesn't exist
    cmd = [
        sys.executable,
        str(DEEPFLOW_ROOT / "scripts" / "start_solution_pro.py"),
        "--topic", topic,
        "--solution-type", args.solution_type or "architecture",
    ]
    if not handoff_pkg.exists():
        # Fallback: no handoff package, pass explicit path
        cmd.extend(["--living-spec-path", str(living_spec.relative_to(DEEPFLOW_ROOT))])
        print(f"⚠️  No handoff package found, passing --living-spec-path directly")
    else:
        print(f"✅ Handoff package found, Solution Pro will use handoff gate")
    
    if args.constraints:
        cmd.extend(["--constraints", json.dumps(args.constraints)])
    
    print(f"🚀 Solution Pro command:")
    print(f"   cd {DEEPFLOW_ROOT} && python3 {' '.join(cmd[1:])}")
    
    if not args.dry_run:
        import subprocess
        result = subprocess.run(cmd, cwd=str(DEEPFLOW_ROOT), capture_output=True, text=True)
        print(result.stdout)
        if result.returncode != 0:
            print(f"❌ Error: {result.stderr}")
            sys.exit(1)
    
    return {"status": "ready", "command": " ".join(cmd)}


def cmd_ship(args):
    """Phase 3: Solution Pro → Ship Pro handoff"""
    from domains.ship_pro import run_ship_pro
    
    project_name = args.project_name
    
    # 1. 检查 Solution Pro 输出（MD-first）
    bb_dir = find_blackboard_dir(project_name=project_name)
    final_solution = bb_dir / "stages" / "final_solution.md"
    
    if not final_solution.exists():
        print(f"❌ Solution Pro 未完成: {final_solution} 不存在")
        sys.exit(1)
    
    print(f"✅ Solution Pro 输出已就绪: {final_solution}")
    
    # 2. 调用 run_ship_pro
    result = run_ship_pro(project_name)
    
    print(f"🚀 Ship Pro spawn params ready:")
    print(f"   project: {result['project_name']}")
    print(f"   blackboard: {result['project_blackboard']}")
    print(f"   input: {json.dumps(result['input_summary'], ensure_ascii=False)}")
    
    # 3. 输出 spawn 命令（Main Agent 需要 sessions_spawn）
    spawn = result['spawn_params']
    print(f"\n📦 Main Agent 执行:")
    print(f"   sessions_spawn(")
    print(f"     task='<见 spawn_params>',")
    print(f"     runtime='subagent',")
    print(f"     mode='run',")
    print(f"     label='ship_pro_orchestrator',")
    print(f"     cwd='{DEEPFLOW_ROOT}',")
    print(f"     lightContext=True")
    print(f"   )")
    
    return result


def cmd_deliver(args):
    """Phase 4: Ship Pro → Deliver Pro handoff"""
    from domains.deliver_pro import run_deliver_pro

    bb_dir = find_blackboard_dir(project_name=args.project_name)
    project_name = bb_dir.name

    try:
        result = run_deliver_pro(project_name)
    except Exception as e:
        print(f"❌ Deliver Pro 无法启动: {e}")
        sys.exit(1)

    print(f"🚀 Deliver Pro Pulse ready:")
    print(f"   project: {result['project_name']}")
    print(f"   blackboard: {result['blackboard_path']}")
    print(f"   ship_package: {result['ship_package_path']}")
    print(f"\n📦 执行一次 Pulse:")
    print(f"   {result['launch_command']}")
    print(f"\n🕒 注册 cron:")
    print(f"   {result['cron_hint']}")

    return result


def cmd_status(args):
    """全管线状态检查（MD-first + run_id 目录兼容）"""
    project_name = args.project_name
    
    try:
        bb_dir = find_blackboard_dir(project_name=project_name)
    except FileNotFoundError:
        print(f"❌ 找不到项目: {project_name}")
        sys.exit(1)
    
    print(f"📁 Blackboard: {bb_dir}")
    
    # Spec Pro
    living_spec = bb_dir / "spec" / "living_spec.md"
    handoff_pkg = bb_dir / "spec" / "spec_handoff_package.json"
    quality_report = bb_dir / "spec" / "quality_report.json"
    spec_done = living_spec.exists() and handoff_pkg.exists()
    
    print(f"\n{'✅' if spec_done else '⏳' if living_spec.exists() else '❌'} Spec Pro: ", end="")
    if living_spec.exists():
        score = "N/A"
        if quality_report.exists():
            try:
                qr = json.loads(quality_report.read_text())
                score = qr.get("weighted_score", "N/A")
            except Exception:
                pass
        print(f"score={score}, handoff={'yes' if handoff_pkg.exists() else 'no'}")
    else:
        print("未初始化")
    
    # Solution Pro
    living_spec_out = bb_dir / "data" / "living_spec.md"
    final_solution = bb_dir / "stages" / "final_solution.md"
    sol_done = living_spec_out.exists() and final_solution.exists()
    
    print(f"{'✅' if sol_done else '⏳' if living_spec_out.exists() else '❌'} Solution Pro: ", end="")
    if sol_done:
        size_kb = final_solution.stat().st_size / 1024
        print(f"{size_kb:.0f}KB, done=True")
    elif living_spec_out.exists():
        print("已启动，等待 final_solution.md")
    else:
        print("未启动")
    
    # Ship Pro
    from domains.deliver_pro import find_ship_package_path
    try:
        ship_pkg = find_ship_package_path(bb_dir.name)
        ship_done = True
    except FileNotFoundError:
        ship_pkg = None
        ship_done = False
    
    print(f"{'✅' if ship_done else '❌'} Ship Pro: ", end="")
    if ship_done:
        try:
            if ship_pkg.suffix == ".json":
                pkg = json.loads(ship_pkg.read_text())
            else:
                from domains.ship_pro.ship_living_md import parse_ship_package_md
                pkg = parse_ship_package_md(ship_pkg.read_text())
            wps = len(pkg.get("work_packages", []))
            print(f"{wps} WPs ({ship_pkg.relative_to(bb_dir)})")
        except Exception:
            print(f"package found ({ship_pkg.relative_to(bb_dir)})")
    else:
        print("未启动")

    # Deliver Pro
    deliver_done = (bb_dir / ".deliver_completed.json").exists()
    deliver_outputs = list((bb_dir / "deliver_pro").rglob("DELIVERABLE.md")) if (bb_dir / "deliver_pro").exists() else []
    print(f"{'✅' if deliver_done else '⏳' if deliver_outputs else '❌'} Deliver Pro: ", end="")
    if deliver_done:
        print("completed")
    elif deliver_outputs:
        print(f"{len(deliver_outputs)} deliverable drafts")
    else:
        print("未启动")


def main():
    parser = argparse.ArgumentParser(description="DeepFlow 全管线入口")
    sub = parser.add_subparsers(dest="command")
    
    # init
    p_init = sub.add_parser("init", help="Phase 1: 初始化 Spec Pro")
    p_init.add_argument("--topic", required=True, help="项目主题")
    
    # solution
    p_sol = sub.add_parser("solution", help="Phase 2: Spec Pro → Solution Pro")
    p_sol.add_argument("--session-id", help="Spec Pro session ID")
    p_sol.add_argument("--solution-type", default="architecture")
    p_sol.add_argument("--constraints", type=json.loads)
    p_sol.add_argument("--dry-run", action="store_true")
    
    # ship
    p_ship = sub.add_parser("ship", help="Phase 3: Solution Pro → Ship Pro")
    p_ship.add_argument("--project-name", required=True, help="项目名称")

    # deliver
    p_deliver = sub.add_parser("deliver", help="Phase 4: Ship Pro → Deliver Pro")
    p_deliver.add_argument("--project-name", required=True, help="项目名称")
    
    # status
    p_status = sub.add_parser("status", help="全管线状态检查")
    p_status.add_argument("--project-name", required=True)
    
    args = parser.parse_args()
    
    if args.command == "init":
        cmd_init(args)
    elif args.command == "solution":
        cmd_solution(args)
    elif args.command == "ship":
        cmd_ship(args)
    elif args.command == "deliver":
        cmd_deliver(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
