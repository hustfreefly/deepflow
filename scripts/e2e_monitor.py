#!/usr/bin/env python3
"""
e2e_monitor.py — DeepFlow 重建期轻量 E2E 监控

功能:
  1. 扫描 blackboard/ 下所有活跃会话
  2. 检测每个会话的阶段进度（哪些文件已产出）
  3. 验证阶段文件的 JSON 完整性 + 必需字段
  4. 记录阶段耗时（基于文件 mtime）
  5. 输出 .progress.json 供 Agent/用户查看
  6. 可选：检测新进展并输出通知文本

用法:
  python3 scripts/e2e_monitor.py                    # 扫描所有活跃会话
  python3 scripts/e2e_monitor.py --session <name>   # 扫描指定会话
  python3 scripts/e2e_monitor.py --notify           # 输出变更通知（给 cron 用）
  python3 scripts/e2e_monitor.py --report           # 输出汇总报告

设计原则: 单文件、无外部依赖、重建完成后即可删除。
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent
BLACKBOARD_DIR = DEEPFLOW_ROOT / "blackboard"

# Solution Pro 10 阶段（按顺序）
SOLUTION_STAGES = [
    "planning",
    "reviewer_technical",
    "reviewer_business",
    "reviewer_risk",
    "fix",
    "research_expert_1",
    "research_expert_2",
    "research_expert_3",
    "consolidator",
    "audit",
    "fixer_expert",
    "harness_final",
    "summarizer",
]

# Spec Pro 关键文件
SPEC_PRO_FILES = [
    "spec/living_spec.json",
    "spec/harness_report.json",
    "spec/conversation_log.json",
]

# Ship Pro 关键文件
SHIP_PRO_FILES = [
    "ship/architect_output.json",
    "ship/specifier_output.json",
    "ship/decomposer_output.json",
    "ship/packager_output.json",
    "ship/ship_package.json",
]

# 终态文件
TERMINAL_FILES = ["final_result.json", "final_solution.md"]

# 会话活跃判定：最近 2 小时内有文件变更
ACTIVE_WINDOW_SECONDS = 2 * 3600

PROGRESS_FILE = ".progress.json"

# 阶段文件大小阈值（bytes）
MIN_STAGE_SIZE = 100  # 太小 = 可能是空结果或错误
MAX_STAGE_SIZE = 500_000  # 太大 = 可能是幻觉或重复

# 阶段间隔超时阈值（秒）
STAGE_TIMEOUT_SECONDS = 1800  # 30 分钟无新阶段 = 可能卡住


# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------


def _scan_stage_files(session_path: Path) -> dict[str, Any]:
    """扫描会话目录中的阶段文件。"""
    stages: dict[str, Any] = {}
    
    # Solution Pro 阶段
    stages_dir = session_path / "stages"
    if stages_dir.is_dir():
        for stage_name in SOLUTION_STAGES:
            stage_info = _check_stage(stages_dir, stage_name)
            if stage_info:
                stages[stage_name] = stage_info
    
    # Spec Pro 文件
    for rel_path in SPEC_PRO_FILES:
        full = session_path / rel_path
        if full.exists():
            key = rel_path.replace("/", "_")
            stages[key] = _file_info(full)
    
    # Ship Pro 文件
    ship_dir = session_path / "ship"
    if ship_dir.is_dir():
        for rel_path in SHIP_PRO_FILES:
            full = session_path / rel_path
            if full.exists():
                key = rel_path.replace("/", "_")
                stages[key] = _file_info(full)
    
    return stages


def _scan_terminal_files(session_path: Path) -> dict[str, Any]:
    """扫描会话目录中的终态文件。"""
    terminal: dict[str, Any] = {}
    for tf in TERMINAL_FILES:
        full = session_path / tf
        if full.exists():
            terminal[tf] = _file_info(full)
    return terminal


def _compute_summary(stages: dict, terminal: dict, session_path: Path) -> dict:
    """计算会话进度汇总，包括错误和警告。"""
    summary = {
        "total_stages": len(stages),
        "completed_stages": sum(1 for s in stages.values() if s.get("valid_json", True)),
        "failed_stages": sum(1 for s in stages.values() if not s.get("valid_json", True)),
        "is_finished": len(terminal) > 0,
        "domain": _detect_domain(session_path),
    }
    
    # 收集错误和警告
    errors = []
    warnings = []
    for name, info in stages.items():
        if info.get("error"):
            errors.append(f"{name}: {info['error']}")
        if info.get("warning"):
            warnings.append(f"{name}: {info['warning']}")
    
    # 检查是否卡住（最后阶段距今超过阈值）
    mtimes = [s["mtime_ts"] for s in stages.values() if "mtime_ts" in s]
    if mtimes and not summary["is_finished"]:
        newest = max(mtimes)
        idle_seconds = time.time() - newest
        if idle_seconds > STAGE_TIMEOUT_SECONDS:
            warnings.append(f"可能卡住: 已 {int(idle_seconds/60)} 分钟无新阶段")
    
    if errors:
        summary["errors"] = errors
    if warnings:
        summary["warnings"] = warnings
    
    # 计算总耗时
    if len(mtimes) >= 2:
        summary["duration_seconds"] = round(max(mtimes) - min(mtimes))
        summary["duration_human"] = _format_duration(summary["duration_seconds"])
    
    return summary


def _check_subagent_health(session_path: Path) -> list[str]:
    """检查子Agent执行健康度（从 session 日志推断）。"""
    issues = []
    
    # 检查 .completed 文件
    completed_file = session_path / ".completed"
    if completed_file.exists():
        try:
            content = completed_file.read_text(encoding="utf-8").strip()
            if not content or len(content) < 10:
                issues.append(".completed 文件内容为空或过短")
        except Exception as e:
            issues.append(f".completed 文件读取失败: {e}")
    
    # 检查 .stage_progress.json（如果存在）
    progress_file = session_path / ".stage_progress.json"
    if progress_file.exists():
        try:
            data = json.loads(progress_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                current = data.get("current_stage", "")
                status = data.get("status", "")
                if status in ("error", "failed", "timeout"):
                    issues.append(f"进度文件显示状态: {status}")
        except Exception:
            issues.append(".stage_progress.json 解析失败")
    
    # 检查 stages/ 目录下是否有错误日志
    stages_dir = session_path / "stages"
    if stages_dir.is_dir():
        for log_file in stages_dir.glob("*.log"):
            try:
                content = log_file.read_text(encoding="utf-8")
                if "error" in content.lower() or "exception" in content.lower():
                    issues.append(f"日志文件 {log_file.name} 包含错误")
            except Exception:
                pass
    
    return issues


def scan_session(session_path: Path) -> dict[str, Any]:
    """扫描单个会话目录，返回进度信息。"""
    stages = _scan_stage_files(session_path)
    terminal = _scan_terminal_files(session_path)
    summary = _compute_summary(stages, terminal, session_path)
    
    # 子Agent 健康检查
    subagent_issues = _check_subagent_health(session_path)
    if subagent_issues:
        summary.setdefault("warnings", []).extend(subagent_issues)
    
    # 计算相对路径（兼容测试环境）
    try:
        rel_path = str(session_path.relative_to(DEEPFLOW_ROOT))
    except ValueError:
        # 路径不在 DEEPFLOW_ROOT 下（测试环境）
        rel_path = str(session_path)
    
    return {
        "session": session_path.name,
        "path": rel_path,
        "scanned_at": datetime.now().isoformat(timespec="seconds"),
        "stages": stages,
        "terminal": terminal,
        "summary": summary,
    }


def _check_stage(stages_dir: Path, stage_name: str) -> dict[str, Any] | None:
    """检查单个阶段文件，包括质量问题检测。"""
    stage_file = stages_dir / f"{stage_name}.json"
    if not stage_file.exists():
        return None

    info = _file_info(stage_file)

    # 大小检测
    size = info.get("size", 0)
    if size < MIN_STAGE_SIZE:
        info["warning"] = f"too_small ({size} bytes)"
    elif size > MAX_STAGE_SIZE:
        info["warning"] = f"too_large ({size:,} bytes)"

    # JSON 完整性 + 必需字段检查
    if info.get("valid_json"):
        data = info.pop("_data", None)
        if data and isinstance(data, dict):
            info["has_status"] = "status" in data
            info["has_stage"] = "stage" in data
            
            # 检查常见错误标志
            if data.get("status") in ("error", "failed", "timeout"):
                info["error"] = f"stage_status={data['status']}"
            if "error" in data:
                info["error"] = str(data["error"])[:100]
            
            # 提取 harness 分数（如果有）
            if stage_name == "harness_final":
                info["harness_score"] = _extract_harness_score(data)
    else:
        # JSON 解析失败 = 严重问题
        info["error"] = info.get("json_error", "invalid_json")

    return info


def _file_info(path: Path) -> dict[str, Any]:
    """获取文件基本信息 + JSON 验证。"""
    info: dict[str, Any] = {
        "valid_json": False,
    }
    
    # 检查文件是否存在
    if not path.exists():
        info["json_error"] = "file_not_found"
        return info
    
    try:
        stat = path.stat()
        info["size"] = stat.st_size
        info["mtime"] = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
        info["mtime_ts"] = stat.st_mtime
    except OSError as e:
        info["json_error"] = f"stat_error: {e}"
        return info

    # JSON 验证
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        info["valid_json"] = True
        info["_data"] = data  # 临时保留，供上层提取字段后删除
    except (json.JSONDecodeError, UnicodeDecodeError):
        info["json_error"] = "parse_failed"
    except OSError as e:
        info["json_error"] = str(e)

    return info


def _extract_harness_score(data: dict) -> int | None:
    """从 harness_final.json 提取总分。"""
    # 尝试多种常见结构
    for key in ("overall_score", "total_score", "score"):
        if key in data:
            val = data[key]
            if isinstance(val, (int, float)):
                return int(val)
    # 嵌套结构
    result = data.get("result", {})
    if isinstance(result, dict):
        for key in ("overall_score", "total_score", "score"):
            if key in result:
                val = result[key]
                if isinstance(val, (int, float)):
                    return int(val)
    return None


def _detect_domain(session_path: Path) -> str:
    """根据目录名和内容判断属于哪个域。"""
    name = session_path.name.lower()
    if "spec_pro" in name or name.startswith("spec_"):
        return "spec_pro"
    if "ship" in name:
        return "ship_pro"
    if (session_path / "stages").is_dir():
        return "solution_pro"
    if (session_path / "spec").is_dir():
        return "spec_pro"
    return "unknown"


def _format_duration(seconds: int) -> str:
    """秒数 → 人类可读时长。"""
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m{secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h{mins}m"


# ---------------------------------------------------------------------------
# 活跃会话发现
# ---------------------------------------------------------------------------


def find_active_sessions() -> list[Path]:
    """找到最近活跃的会话目录。"""
    if not BLACKBOARD_DIR.is_dir():
        return []

    now = time.time()
    active = []

    for d in BLACKBOARD_DIR.iterdir():
        if not d.is_dir():
            continue
        if d.name.startswith("."):
            continue

        # 检查最近修改时间
        try:
            newest = max(
                (f.stat().st_mtime for f in d.rglob("*") if f.is_file()),
                default=0,
            )
        except (OSError, ValueError):
            continue

        if now - newest < ACTIVE_WINDOW_SECONDS:
            active.append(d)

    # 按修改时间倒序
    active.sort(key=lambda p: _newest_mtime(p), reverse=True)
    return active


def _newest_mtime(path: Path) -> float:
    """目录中最新文件的 mtime。"""
    try:
        return max((f.stat().st_mtime for f in path.rglob("*") if f.is_file()), default=0)
    except (OSError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# 输出模式
# ---------------------------------------------------------------------------


def write_progress(session_result: dict) -> Path:
    """将进度写入会话目录的 .progress.json。"""
    session_path = DEEPFLOW_ROOT / session_result["path"]
    progress_file = session_path / PROGRESS_FILE
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(session_result, f, ensure_ascii=False, indent=2)
    return progress_file


def detect_changes(session_result: dict) -> list[str]:
    """检测与上次 .progress.json 相比的变更。"""
    session_path = DEEPFLOW_ROOT / session_result["path"]
    progress_file = session_path / PROGRESS_FILE

    old_stages: set[str] = set()
    if progress_file.exists():
        try:
            with open(progress_file, encoding="utf-8") as f:
                old = json.load(f)
            old_stages = set(old.get("stages", {}).keys())
        except (json.JSONDecodeError, OSError):
            pass

    new_stages = set(session_result["stages"].keys())
    added = new_stages - old_stages

    changes = []
    for stage in sorted(added):
        info = session_result["stages"][stage]
        status = "✅" if info.get("valid_json") else "❌"
        changes.append(f"{status} {stage} ({info.get('size', 0):,} bytes)")

    if session_result["summary"]["is_finished"] and not old.get("summary", {}).get("is_finished"):
        changes.append("🏁 会话已完成！")

    return changes


def format_notification(session_result: dict, changes: list[str]) -> str:
    """格式化通知文本（给飞书/cron 用）。"""
    name = session_result["session"]
    domain = session_result["summary"]["domain"]
    completed = session_result["summary"]["completed_stages"]
    total = session_result["summary"]["total_stages"]
    duration = session_result["summary"].get("duration_human", "-")

    lines = [f"📊 E2E 进度: {name} ({domain})"]
    lines.append(f"阶段: {completed}/{total} | 耗时: {duration}")

    if changes:
        lines.append("")
        for c in changes:
            lines.append(f"  {c}")

    if session_result["summary"]["failed_stages"] > 0:
        failed = [
            name for name, info in session_result["stages"].items()
            if not info.get("valid_json")
        ]
        lines.append(f"\n⚠️ JSON 解析失败: {', '.join(failed)}")

    # 新增：错误和警告
    errors = session_result["summary"].get("errors", [])
    if errors:
        lines.append(f"\n❌ 错误 ({len(errors)}):")
        for err in errors[:5]:  # 最多显示 5 个
            lines.append(f"  - {err}")
    
    warnings = session_result["summary"].get("warnings", [])
    if warnings:
        lines.append(f"\n⚠️ 警告 ({len(warnings)}):")
        for warn in warnings[:5]:
            lines.append(f"  - {warn}")

    return "\n".join(lines)


def _format_session_report(result: dict) -> list[str]:
    """格式化单个会话的报告行。"""
    lines = []
    name = result["session"][:40]
    domain = result["summary"]["domain"]
    completed = result["summary"]["completed_stages"]
    total = result["summary"]["total_stages"]
    finished = "✅完成" if result["summary"]["is_finished"] else "⏳进行中"
    duration = result["summary"].get("duration_human", "-")
    failed = result["summary"]["failed_stages"]
    errors = result["summary"].get("errors", [])
    warnings = result["summary"].get("warnings", [])

    lines.append(f"\n📁 {name}")
    lines.append(f"   域: {domain} | 阶段: {completed}/{total} | 耗时: {duration} | {finished}")

    if failed > 0:
        bad = [n for n, i in result["stages"].items() if not i.get("valid_json")]
        lines.append(f"   ⚠️ JSON失败: {', '.join(bad)}")

    if errors:
        lines.append(f"   ❌ 错误 ({len(errors)}):")
        for err in errors[:3]:
            lines.append(f"      - {err}")
        if len(errors) > 3:
            lines.append(f"      ... 还有 {len(errors)-3} 个")

    if warnings:
        lines.append(f"   ⚠️ 警告 ({len(warnings)}):")
        for warn in warnings[:3]:
            lines.append(f"      - {warn}")
        if len(warnings) > 3:
            lines.append(f"      ... 还有 {len(warnings)-3} 个")

    # 阶段明细
    for stage, info in result["stages"].items():
        status = "✅" if info.get("valid_json") else "❌"
        size_kb = info.get("size", 0) / 1024
        extra = ""
        if info.get("warning"):
            extra = f" ⚠️{info['warning']}"
        if info.get("error"):
            extra = f" ❌{info['error']}"
        if info.get("harness_score"):
            extra += f" 📊{info['harness_score']}"
        lines.append(f"   {status} {stage} ({size_kb:.1f} KB){extra}")
    
    return lines


def format_report(all_results: list[dict]) -> str:
    """格式化全量报告。"""
    lines = ["=" * 60]
    lines.append("DeepFlow E2E 监控报告")
    lines.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"活跃会话: {len(all_results)}")
    
    # 全局统计
    total_errors = sum(len(r["summary"].get("errors", [])) for r in all_results)
    total_warnings = sum(len(r["summary"].get("warnings", [])) for r in all_results)
    if total_errors or total_warnings:
        lines.append(f"全局: {total_errors} 错误, {total_warnings} 警告")
    lines.append("=" * 60)

    for r in all_results:
        lines.extend(_format_session_report(r))

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="DeepFlow E2E 轻量监控")
    parser.add_argument("--session", help="指定会话名（模糊匹配）")
    parser.add_argument("--notify", action="store_true", help="输出变更通知")
    parser.add_argument("--report", action="store_true", help="输出汇总报告")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    return parser.parse_args()


def _find_sessions(args: argparse.Namespace) -> list[Path]:
    """根据参数找到目标会话。"""
    if args.session:
        return [
            d for d in BLACKBOARD_DIR.iterdir()
            if d.is_dir() and args.session.lower() in d.name.lower()
        ]
    return find_active_sessions()


def _output_results(results: list[dict], args: argparse.Namespace) -> None:
    """根据模式输出结果。"""
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.report:
        print(format_report(results))
    elif args.notify:
        for result in results:
            changes = detect_changes(result)
            if changes:
                print(format_notification(result, changes))
                print()
    else:
        # 默认：简洁输出
        for result in results:
            name = result["session"][:50]
            completed = result["summary"]["completed_stages"]
            total = result["summary"]["total_stages"]
            finished = "完成" if result["summary"]["is_finished"] else "进行中"
            duration = result["summary"].get("duration_human", "-")
            failed = result["summary"]["failed_stages"]
            print(f"{name}: {completed}/{total} 阶段 | {duration} | {finished}", end="")
            if failed:
                print(f" | ⚠️ {failed} 失败", end="")
            print()


def main() -> int:
    """CLI 入口：解析参数、扫描会话、输出结果。"""
    args = _parse_args()
    sessions = _find_sessions(args)

    if not sessions:
        print("没有找到活跃会话。")
        print(f"扫描目录: {BLACKBOARD_DIR}")
        print(f"活跃窗口: 最近 {ACTIVE_WINDOW_SECONDS // 60} 分钟")
        return 0

    results = []
    for session_path in sessions:
        result = scan_session(session_path)
        write_progress(result)
        results.append(result)

    _output_results(results, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
