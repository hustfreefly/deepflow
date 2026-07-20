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
    
    # 2. 检查 Spec Pro 是否完成
    living_spec = bb_dir / "spec" / "living_spec.json"
    quality_report = bb_dir / "spec" / "quality_report.json"
    
    if not living_spec.exists():
        print(f"❌ living_spec.json 不存在: {living_spec}")
        sys.exit(1)
    
    # 3. 读取 living_spec 提取关键信息
    spec = json.loads(living_spec.read_text())
    topic = spec.get("topic", spec.get("project_name", args.session_id))
    
    # 4. 构建 Solution Pro 启动参数
    print(f"📋 Topic: {topic}")
    print(f"📊 Quality: {json.loads(quality_report.read_text()).get('weighted_score', 'N/A') if quality_report.exists() else 'N/A'}")
    
    # 5. 调用 start_solution_pro.py
    # B3-FIX: Don't force --living-spec-path; let handoff gate decide
    # If handoff package exists, Solution Pro will auto-load via _try_load_handoff_package()
    # Only fallback to --living-spec-path if handoff package doesn't exist
    handoff_pkg = bb_dir / "spec" / "handoff_package.json"
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
    
    # 1. 检查 Solution Pro 输出
    bb_dir = find_blackboard_dir(project_name=project_name)
    final_solution = bb_dir / "stages" / "final_solution.json"
    
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


def cmd_status(args):
    """全管线状态检查"""
    project_name = args.project_name
    
    try:
        bb_dir = find_blackboard_dir(project_name=project_name)
    except FileNotFoundError:
        print(f"❌ 找不到项目: {project_name}")
        sys.exit(1)
    
    print(f"📁 Blackboard: {bb_dir}")
    
    # Spec Pro — 搜索多个可能路径
    living_spec = None
    quality_report = None
    for sub in ["spec", "stages", ""]:
        candidate = bb_dir / sub / "living_spec.json" if sub else bb_dir / "living_spec.json"
        if candidate.exists():
            living_spec = candidate
            qr_candidate = bb_dir / sub / "quality_report.json" if sub else bb_dir / "quality_report.json"
            if qr_candidate.exists():
                quality_report = qr_candidate
            break
    
    spec_done = False
    for marker in ["stages/.completed.json", "spec/.done", ".completed.json"]:
        if (bb_dir / marker).exists():
            spec_done = True
            break
    
    print(f"\n{'✅' if spec_done else '⏳' if living_spec else '❌'} Spec Pro: ", end="")
    if living_spec:
        spec = json.loads(living_spec.read_text())
        score = "N/A"
        if quality_report:
            qr = json.loads(quality_report.read_text())
            score = qr.get("weighted_score", "N/A")
        print(f"score={score}, done={spec_done}")
    else:
        print("未初始化")
    
    # Solution Pro
    final_solution = bb_dir / "stages" / "final_solution.json"
    sol_done = (bb_dir / "stages" / ".completed.json").exists()
    
    print(f"{'✅' if sol_done else '⏳' if final_solution.exists() else '❌'} Solution Pro: ", end="")
    if final_solution.exists():
        size_kb = final_solution.stat().st_size / 1024
        print(f"{size_kb:.0f}KB, done={sol_done}")
    else:
        print("未启动")
    
    # Ship Pro
    ship_pkg = bb_dir / "ship_pro" / "stages" / "ship_package.json"
    ship_done = ship_pkg.exists()
    
    print(f"{'✅' if ship_done else '⏳' if (bb_dir / 'ship_pro').exists() else '❌'} Ship Pro: ", end="")
    if ship_done:
        pkg = json.loads(ship_pkg.read_text())
        wps = len(pkg.get("work_packages", []))
        print(f"{wps} WPs")
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
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
