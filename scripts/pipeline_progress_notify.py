#!/usr/bin/env python3
"""
管线进度通知脚本 — 设计总监版 v3

参考: GitHub Actions (结构化) + Linear (语义化) + Vercel (进度条可视化)
设计原则: 状态优先 / 项目身份 / 进度可视化 / 信息分层 / 时间感知

用法: python3 pipeline_progress_notify.py --workspace <path> [--pipeline ship|solution]

输出: 格式化的飞书进度通知文本（stdout）
退出码: 0=进度更新 1=完成 2=异常 3=无变化(不推送)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

TZ_SHANGHAI = timezone(timedelta(hours=8))

# ── 管线配置 ──

PIPELINE_CONFIGS = {
    "solution": {
        "display_name": "Solution Pro",
        "phases": [
            ("data_collection", "数据收集", "📊"),
            ("planning", "规划", "📝"),
            ("reviewers", "评审 (×3)", "👁️"),
            ("research", "研究 (×3)", "🔬"),
            ("consolidator", "整合", "🧩"),
            ("audit", "审计", "🔍"),
            ("fix", "修复", "🔧"),
            ("fixer_expert", "深度修复", "🛠️"),
            ("harness_final", "最终验证", "✅"),
            ("summarizer", "总结", "📋"),
        ],
        "progress_file": ".stage_progress.json",
        "phase_field": "current_phase",
        "completed_field": "completed_phases",
        "failed_field": "failed_phases",
    },
    "ship": {
        "display_name": "Ship Pro",
        "phases": [
            ("architect", "Architect", "🏗️"),
            ("decomposer", "Decomposer", "🧩"),
            ("specifier", "Specifier", "📐"),
            ("reviewer", "Reviewer", "👁️"),
            ("packager", "Packager", "📦"),
        ],
        "progress_file": "blackboard/.stage_progress.json",
        "phase_field": "current_stage",
        "completed_field": "completed_stages",
        "failed_field": "failed_stages",
    },
}

STATUS_ICONS = {
    "running": "🟠",
    "completed": "✅",
    "failed": "🔴",
    "stalled": "⚠️",
}


def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def format_duration(started_at_str):
    """返回 (分钟数, 格式化字符串)"""
    try:
        started = datetime.fromisoformat(started_at_str)
        if started.tzinfo is None:
            started = started.replace(tzinfo=TZ_SHANGHAI)
        now = datetime.now(TZ_SHANGHAI)
        delta = now - started
        total_seconds = int(delta.total_seconds())
        minutes = max(0, total_seconds // 60)
        if minutes >= 60:
            hours = minutes // 60
            mins = minutes % 60
            return minutes, f"{hours}h{mins}m"
        return minutes, f"{minutes}m"
    except Exception:
        return 0, "—"


def estimate_remaining(elapsed_minutes, completed_count, total):
    if completed_count <= 0 or elapsed_minutes <= 0:
        return "计算中"
    avg_per_phase = elapsed_minutes / completed_count
    remaining = total - completed_count
    remaining_minutes = int(avg_per_phase * remaining)
    if remaining_minutes < 1:
        return "即将完成"
    if remaining_minutes >= 60:
        h = remaining_minutes // 60
        m = remaining_minutes % 60
        return f"{h}h{m}m"
    return f"{remaining_minutes}m"


def check_idle_minutes(progress_path):
    try:
        mtime = os.path.getmtime(progress_path)
        mtime_dt = datetime.fromtimestamp(mtime, TZ_SHANGHAI)
        now = datetime.now(TZ_SHANGHAI)
        return int((now - mtime_dt).total_seconds() / 60)
    except Exception:
        return 0


def progress_bar(completed, total, width=20):
    """Unicode 进度条"""
    if total <= 0:
        return "░" * width
    filled = int(width * completed / total)
    filled = min(filled, width)
    return "█" * filled + "░" * (width - filled)


def get_project_short_name(ws):
    """从路径中提取项目短名称"""
    # 从 workspace 路径提取: DeepFlow_开发者可观测性系统架构_architecture_xxx
    basename = os.path.basename(ws.rstrip("/"))
    # 尝试从 frozen_spec 获取 topic
    frozen_spec_path = os.path.join(ws, "data", "frozen_spec.json")
    if os.path.exists(frozen_spec_path):
        data = load_json(frozen_spec_path)
        if data and data.get("topic"):
            topic = data["topic"]
            # 缩短：取前 12 个字符
            if len(topic) > 12:
                return topic[:12] + "…"
            return topic
    # fallback: 从目录名提取
    parts = basename.split("_")
    if len(parts) >= 2:
        return parts[0]
    return basename[:12]


def get_phase_info(config, phase_num):
    """阶段序号 → (key, name, icon)"""
    phases = config["phases"]
    if 1 <= phase_num <= len(phases):
        return phases[phase_num - 1]
    return (f"phase_{phase_num}", f"Phase {phase_num}", "❓")


def build_phase_icon_chain(config, completed_set, current, failed_set):
    """构建阶段图标链: 🏗️✅ 🧩⏳ 📐○ 👁️○ 📦○"""
    parts = []
    for i, (key, name, icon) in enumerate(config["phases"], 1):
        if i in failed_set:
            parts.append(f"{icon}❌")
        elif i in completed_set:
            parts.append(f"{icon}✅")
        elif i == current:
            parts.append(f"{icon}⏳")
        else:
            parts.append(f"{icon}○")
    return " ".join(parts)


def list_stage_files(ws, config):
    """统计交付物文件"""
    progress_file = config["progress_file"]
    blackboard_dir = os.path.dirname(os.path.join(ws, progress_file))
    if not os.path.exists(blackboard_dir):
        return 0
    count = 0
    for f in os.listdir(blackboard_dir):
        if f.endswith(".json") and not f.startswith("."):
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--pipeline", default="solution",
                       choices=list(PIPELINE_CONFIGS.keys()))
    args = parser.parse_args()

    ws = args.workspace
    config = PIPELINE_CONFIGS[args.pipeline]
    total = len(config["phases"])
    display_name = config["display_name"]
    project_short = get_project_short_name(ws)

    progress_path = os.path.join(ws, config["progress_file"])
    completed_path = os.path.join(ws, ".completed")

    # ── 检查 .completed ──
    completed = load_json(completed_path)
    if completed:
        status = completed.get("status", "unknown")
        completion_rate = completed.get("completion_rate", 0)
        stages = completed.get("stages_completed", 0)
        failed = completed.get("failed_stages", [])

        progress = load_json(progress_path)
        if progress:
            prog_completed = progress.get(config["completed_field"], [])
            prog_failed = progress.get(config["failed_field"], [])
            if prog_completed and not stages:
                stages = len(prog_completed)
            if prog_failed and not failed:
                failed = prog_failed
            if progress.get("status") == "completed" and not failed:
                status = "completed"

        started_at = progress.get("started_at", "") if progress else ""
        elapsed_min, duration = format_duration(started_at)

        is_completed = (status == "completed" and not failed) or \
                       (status == "partial" and completion_rate >= 1.0 and not failed)

        if is_completed:
            file_count = list_stage_files(ws, config)
            bar = progress_bar(total, total, 20)
            print(f"✅ [{project_short}] {display_name} 完成\n")
            print(f"{bar} {total}/{total} 阶段")
            print(f"⏱️ 总耗时 {duration}")
            print(f"📄 {file_count} 个交付物")
            sys.exit(1)
        else:
            completed_count = stages if isinstance(stages, int) else 0
            current = completed_count + 1
            _, current_name, _ = get_phase_info(config, current)
            bar = progress_bar(completed_count, total, 20)

            print(f"🔴 [{project_short}] 阶段失败：{current_name}\n")
            print(f"{bar} {completed_count}/{total} 阶段")
            print(f"❗ orchestrator 执行中断")
            print(f"💡 建议：检查日志 → 从断点继续\n")
            print(f"⏱️ 已运行 {duration}")
            sys.exit(2)

    # ── 检查 progress ──
    progress = load_json(progress_path)
    if not progress:
        sys.exit(3)

    current = progress.get(config["phase_field"], 0)
    completed_phases = progress.get(config["completed_field"], [])
    failed_phases = progress.get(config["failed_field"], [])
    started_at = progress.get("started_at", "")

    completed_set = set(completed_phases or [])
    failed_set = set(failed_phases or [])
    completed_count = len(completed_set)

    # ── 超时检查 ──
    idle_minutes = check_idle_minutes(progress_path)

    if idle_minutes > 60:
        _, current_name, current_icon = get_phase_info(config, current)
        elapsed_min, duration = format_duration(started_at)
        bar = progress_bar(completed_count, total, 20)

        print(f"⚠️ [{project_short}] 阶段停滞：{current_name}\n")
        print(f"{bar} {completed_count}/{total} 阶段")
        print(f"❗ 已停滞 {idle_minutes} 分钟无更新")
        print(f"💡 建议：检查 orchestrator 状态\n")
        print(f"⏱️ 已运行 {duration}")
        sys.exit(2)

    if current == 0:
        sys.exit(3)

    # ── 正常进度更新（紧凑版）──
    _, current_name, current_icon = get_phase_info(config, current)
    elapsed_min, duration = format_duration(started_at)
    remaining = estimate_remaining(elapsed_min, completed_count, total)
    bar = progress_bar(completed_count, total, 20)

    print(f"🟠 [{project_short}] {current_name}")
    print(f"{bar} {completed_count}/{total} 阶段")
    print(f"⏱️ 已运行 {duration} · 预计剩余 {remaining}")

    sys.exit(0)


if __name__ == "__main__":
    main()
