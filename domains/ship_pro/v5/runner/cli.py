"""
Ship Pro V5 CLI

用法:
  # 准备项目目录
  python -m ship_pro.v5.runner.cli prepare <project_dir>

  # 端到端执行完整 Pipeline
  python -m ship_pro.v5.runner.cli run <project_dir> [--input input.json]

  # 仅执行 Gate 校验 (已有输出)
  python -m ship_pro.v5.runner.cli gate <project_dir> [--phase 1|2]

  # 查看执行状态
  python -m ship_pro.v5.runner.cli status <project_dir>

  # 清理输出
  python -m ship_pro.v5.runner.cli clean <project_dir>

环境变量:
  SHIP_PRO_MODE      - 运行模式: mock (默认) | openclaw
  SHIP_PRO_MODEL     - LLM 模型, 默认 bailian/qwen3.7-plus
  SHIP_PRO_LOG_LEVEL - 日志级别, 默认 INFO
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

# 确保 runner 模块可导入
sys.path.insert(0, str(Path(__file__).parent.parent))

# 支持直接运行本文件 (python cli.py) 和模块导入两种方式
if __name__ == "__main__" and __package__ is None:
    import os
    file_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, file_dir)
    from runner import ShipProV5Runner
    from agent_caller import create_caller, MockAgentCaller, OpenClawAgentCaller
else:
    from runner.runner import ShipProV5Runner
    from runner.agent_caller import create_caller, MockAgentCaller, OpenClawAgentCaller

logger = logging.getLogger("ship_pro.v5.cli")


# ────────────────────────────────
# 命令实现
# ────────────────────────────────


def cmd_prepare(project_dir: Path, args: argparse.Namespace) -> int:
    """准备项目目录结构"""
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)

    # 创建标准子目录
    (project_dir / "v5").mkdir(exist_ok=True)
    (project_dir / "input").mkdir(exist_ok=True)

    # 创建示例输入文件
    sample_input = project_dir / "input.json"
    if not sample_input.exists():
        sample = {
            "task": "请在此描述你的需求",
            "constraints": [],
            "context": {},
        }
        sample_input.write_text(
            json.dumps(sample, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"✅ 创建示例输入: {sample_input}")

    print(f"✅ 项目目录已准备: {project_dir}")
    print("  结构:")
    print(f"    {project_dir}/")
    print(f"    ├── input.json      # 输入需求")
    print(f"    ├── input/          # 附加输入文件")
    print(f"    └── v5/             # 输出目录")
    return 0


def cmd_run(project_dir: Path, args: argparse.Namespace) -> int:
    """执行端到端 Pipeline"""
    project_dir = Path(project_dir)
    input_path = Path(args.input) if args.input else project_dir / "input.json"

    if not input_path.exists():
        print(f"❌ 输入文件不存在: {input_path}")
        print(f"   提示: 先运行 'prepare' 创建项目结构")
        return 1

    # 创建 caller
    mode = args.mode or os.environ.get("SHIP_PRO_MODE", "mock")
    caller = create_caller(
        mode=mode,
        model=args.model or os.environ.get("SHIP_PRO_MODEL"),
        temperature=args.temperature,
    )

    # 执行
    runner = ShipProV5Runner(project_dir, caller=caller)
    print(f"🚀 Ship Pro V5 Pipeline 启动")
    print(f"   项目: {project_dir}")
    print(f"   输入: {input_path}")
    print(f"   模式: {mode}")
    print(f"   模型: {getattr(caller, 'model', 'N/A')}")
    print()

    try:
        result = runner.run_full_pipeline(input_path)
        runner.save_execution_log()

        output_path = runner.output_dir / "ship_package.json"
        print(f"\n✅ Pipeline 完成!")
        print(f"   输出: {output_path}")
        print(f"   文件列表:")
        for f in sorted(runner.output_dir.glob("*.json")):
            size = f.stat().st_size
            print(f"     • {f.name:25s} ({size:,} bytes)")

        if args.show_result:
            print(f"\n📦 Ship Package 预览:")
            preview = json.dumps(result, indent=2, ensure_ascii=False)
            print(preview[:2000])
            if len(preview) > 2000:
                print(f"... (共 {len(preview)} 字符, 完整内容见 {output_path})")

        return 0

    except Exception as exc:
        logger.exception("Pipeline 执行失败")
        print(f"\n❌ Pipeline 失败: {exc}")
        runner.save_execution_log()
        return 1

    finally:
        if isinstance(caller, OpenClawAgentCaller):
            caller.shutdown()


def cmd_gate(project_dir: Path, args: argparse.Namespace) -> int:
    """仅执行 Gate 校验"""
    project_dir = Path(project_dir)
    runner = ShipProV5Runner(project_dir)
    phase = args.phase or 1

    output_dir = runner.output_dir

    if phase == 1:
        blueprint_path = output_dir / "p1_consolidator.json"
        if not blueprint_path.exists():
            print(f"❌ 未找到 Blueprint 输出: {blueprint_path}")
            print(f"   请先运行 'run' 完成 Phase 1")
            return 1

        blueprint = json.loads(blueprint_path.read_text(encoding="utf-8"))
        passed, issues = runner.gate_blueprint(blueprint)
        print(f"🔍 Gate 1 (Blueprint) 结果:")
        print(f"   通过: {'✅ 是' if passed else '❌ 否'}")
        print(f"   Issues: {len(issues)}")
        for i, issue in enumerate(issues, 1):
            severity = issue.get("severity", "info")
            icon = {"blocker": "🔴", "warning": "🟡", "info": "🔵"}.get(
                severity, "⚪"
            )
            print(f"   {icon} {i}. [{severity}] {issue.get('message', '')}")

    else:
        package_path = output_dir / "ship_package.json"
        if not package_path.exists():
            print(f"❌ 未找到 Ship Package 输出: {package_path}")
            return 1

        package = json.loads(package_path.read_text(encoding="utf-8"))
        passed, issues = runner.gate_ship_package(package)
        print(f"🔍 Gate 2 (Ship Package) 结果:")
        print(f"   通过: {'✅ 是' if passed else '❌ 否'}")
        print(f"   Issues: {len(issues)}")
        for i, issue in enumerate(issues, 1):
            severity = issue.get("severity", "info")
            icon = {"blocker": "🔴", "warning": "🟡", "info": "🔵"}.get(
                severity, "⚪"
            )
            print(f"   {icon} {i}. [{severity}] {issue.get('message', '')}")

    return 0 if passed else 1


def cmd_status(project_dir: Path, args: argparse.Namespace) -> int:
    """查看项目执行状态"""
    project_dir = Path(project_dir)
    runner = ShipProV5Runner(project_dir)
    status = runner.get_status()

    print(f"📊 项目状态: {project_dir}")
    print(f"   输出目录: {status['output_dir']}")
    print(f"   输出文件: {len(status['output_files'])}")
    for f in sorted(status['output_files']):
        print(f"     • {f}")

    log_path = runner.output_dir / "execution_log.json"
    if log_path.exists():
        log = json.loads(log_path.read_text(encoding="utf-8"))
        print(f"\n   执行记录: {len(log)} 次 Agent 调用")
        ok = sum(1 for e in log if e["status"] == "ok")
        err = sum(1 for e in log if e["status"] == "error")
        print(f"     ✅ 成功: {ok}")
        print(f"     ❌ 失败: {err}")
        if log:
            total_time = sum(e.get("elapsed", 0) for e in log)
            print(f"     ⏱  总耗时: {total_time:.2f}s")

    return 0


def cmd_clean(project_dir: Path, args: argparse.Namespace) -> int:
    """清理输出目录"""
    project_dir = Path(project_dir)
    output_dir = project_dir / "v5"

    if not output_dir.exists():
        print(f"无需清理 (目录不存在): {output_dir}")
        return 0

    import shutil

    if not args.yes:
        confirm = input(f"确认删除 {output_dir}? (y/N): ")
        if confirm.lower() != "y":
            print("已取消")
            return 0

    shutil.rmtree(output_dir)
    print(f"✅ 已清理: {output_dir}")
    return 0


# ────────────────────────────────
# 主入口
# ────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ship_pro.v5.runner",
        description="Ship Pro V5 执行引擎 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s prepare ./my_project           # 准备项目
  %(prog)s run ./my_project               # 执行完整 Pipeline (mock 模式)
  %(prog)s run ./my_project --mode openclaw --model gpt-4  # 真实 LLM 模式
  %(prog)s gate ./my_project --phase 1    # 仅校验 Blueprint
  %(prog)s status ./my_project            # 查看状态
  %(prog)s clean ./my_project --yes       # 清理输出
        """,
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # prepare
    p_prepare = sub.add_parser("prepare", help="准备项目目录")
    p_prepare.add_argument("project_dir", type=Path, help="项目目录路径")

    # run
    p_run = sub.add_parser("run", help="执行端到端 Pipeline")
    p_run.add_argument("project_dir", type=Path, help="项目目录路径")
    p_run.add_argument(
        "--input", "-i", type=str, help="输入文件路径 (默认: project_dir/input.json)"
    )
    p_run.add_argument(
        "--mode", "-m", choices=["mock", "openclaw"], help="运行模式"
    )
    p_run.add_argument(
        "--model", type=str, help="LLM 模型 (仅 openclaw 模式)"
    )
    p_run.add_argument(
        "--temperature", "-t", type=float, default=0.3, help="Temperature (默认 0.3)"
    )
    p_run.add_argument(
        "--show-result", "-s", action="store_true", help="显示结果预览"
    )

    # gate
    p_gate = sub.add_parser("gate", help="执行 Gate 校验")
    p_gate.add_argument("project_dir", type=Path, help="项目目录路径")
    p_gate.add_argument(
        "--phase", "-p", type=int, choices=[1, 2], help="校验阶段 (1=Blueprint, 2=Ship)"
    )

    # status
    p_status = sub.add_parser("status", help="查看执行状态")
    p_status.add_argument("project_dir", type=Path, help="项目目录路径")

    # clean
    p_clean = sub.add_parser("clean", help="清理输出目录")
    p_clean.add_argument("project_dir", type=Path, help="项目目录路径")
    p_clean.add_argument(
        "--yes", "-y", action="store_true", help="无需确认直接删除"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口"""
    # 日志配置
    log_level = os.environ.get("SHIP_PRO_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    parser = build_parser()
    args = parser.parse_args(argv)

    commands = {
        "prepare": cmd_prepare,
        "run": cmd_run,
        "gate": cmd_gate,
        "status": cmd_status,
        "clean": cmd_clean,
    }

    handler = commands.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    return handler(args.project_dir, args)


if __name__ == "__main__":
    sys.exit(main())
