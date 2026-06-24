#!/usr/bin/env python3
"""
DeepFlow Doctor V2 — 主入口

三层漏斗架构:
  L1 (确定性代码): parse transcript → detect candidates
  L2 (LLM 分析):  candidates + context → structured diagnosis + fix suggestions
  L3 (格式化输出): diagnosis → human-readable report

用法:
    # ── 按范围检查 ──
    python3 scripts/doctor/doctor_main.py --scope pipeline          # 只查管线执行
    python3 scripts/doctor/doctor_main.py --scope pipeline --hours 6  # 最近 6h 管线
    python3 scripts/doctor/doctor_main.py --scope pipeline --run-id run_20260624  # 指定 run
    python3 scripts/doctor/doctor_main.py --scope agent              # 整个会话 (默认)
    python3 scripts/doctor/doctor_main.py --scope time-range --from 09:21 --to 09:29

    # ── 兼容旧参数 ──
    python3 scripts/doctor/doctor_main.py --hours 6          # = --scope agent --hours 6
    python3 scripts/doctor/doctor_main.py --session <id>     # 扫描指定 session
    python3 scripts/doctor/doctor_main.py --no-llm           # 跳过 L2, 只输出 L1 候选
    python3 scripts/doctor/doctor_main.py --json             # JSON 格式输出
"""

import argparse
import json
import sys
import time
from pathlib import Path

# 确保可以 import 同目录模块
sys.path.insert(0, str(Path(__file__).parent))
# 确保可以 import deepflow 根目录模块
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from transcript_parser import parse_transcript
from pattern_detector import detect_issues, detect_pipeline_issues
from causal_tracer import build_session_tree, get_session_family, trace_causal_chain, find_recent_pipeline_sessions
from pipeline_scope import discover_pipeline_runs, filter_events_by_run, get_run_summary


def main():
    parser = argparse.ArgumentParser(description="DeepFlow Doctor V2 — AI Native 多 Agent 运行诊断")
    parser.add_argument("--hours", type=int, default=24, help="扫描最近 N 小时的 sessions")
    parser.add_argument("--session", type=str, help="扫描指定 session (key 或 id)")
    parser.add_argument("--all-today", action="store_true", help="扫描今天所有管线")
    parser.add_argument("--no-llm", action="store_true", help="跳过 L2 LLM 分析，只输出 L1 候选")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--quiet", action="store_true", help="只输出问题，不输出正常 session 信息")
    # ── Scope 参数 ──
    parser.add_argument("--scope", choices=["pipeline", "agent", "time-range"], default="agent",
                        help="检查范围: pipeline=管线执行 | agent=整个会话(默认) | time-range=自定义时间窗口")
    parser.add_argument("--from", dest="time_from", type=str,
                        help="时间窗口起始 (HH:MM 或 ISO), 配合 --scope time-range")
    parser.add_argument("--to", dest="time_to", type=str,
                        help="时间窗口结束 (HH:MM 或 ISO), 配合 --scope time-range")
    parser.add_argument("--pipeline-dir", type=str,
                        help="指定管线 blackboard 目录 (跳过自动发现)")
    parser.add_argument("--run-id", type=str,
                        help="指定 run_id 精确匹配管线运行")
    args = parser.parse_args()

    # ── Pipeline scope: 直接从 blackboard 发现管线运行 ──
    if args.scope == "pipeline":
        session_reports = _run_pipeline_scope(args)
        if not session_reports:
            print("没有发现管线运行。")
            print("提示: 使用 --hours 扩大搜索范围，或 --pipeline-dir 指定目录")
            return
        _output_reports(session_reports, args)
        return

    # ── Agent / time-range scope: 从 sessions.json 发现 ──
    tree = build_session_tree()
    if not tree["sessions"]:
        print("❌ 无法加载 sessions.json")
        return

    # ── Step 2: 确定要扫描的 sessions ──
    if args.session:
        target_keys = [k for k in tree["sessions"] if args.session in k]
        if not target_keys:
            print(f"❌ 未找到包含 '{args.session}' 的 session")
            return
        clusters = [[(k, tree["sessions"][k]) for k in target_keys]]
    else:
        import datetime
        if args.all_today:
            cutoff = int(datetime.datetime.now().replace(hour=0, minute=0, second=0).timestamp() * 1000)
        else:
            cutoff = int((time.time() - args.hours * 3600) * 1000)

        sub_sessions = sorted(
            [(k, v) for k, v in tree["sessions"].items()
             if v["started_at"] >= cutoff and "subagent" in k],
            key=lambda x: x[1]["started_at"]
        )

        if not sub_sessions:
            print(f"最近 {args.hours}h 没有子 Agent session。")
            return

        # 按时间窗口分组（2h gap = 不同管线）
        clusters = []
        current_cluster = [sub_sessions[0]]
        for item in sub_sessions[1:]:
            prev_ts = current_cluster[-1][1]["started_at"]
            curr_ts = item[1]["started_at"]
            if curr_ts - prev_ts > 2 * 3600 * 1000:
                clusters.append(current_cluster)
                current_cluster = [item]
            else:
                current_cluster.append(item)
        clusters.append(current_cluster)

    if not clusters:
        print("没有管线 session。")
        return

    # ── Step 3: L1 确定性检测（逐 cluster）──
    session_reports = []

    for cluster in clusters:
        cluster_keys = [item[0] for item in cluster]
        cluster_infos = {item[0]: item[1] for item in cluster}

        first_info = cluster[0][1]
        first_label = first_info.get("label", "")
        if not first_label:
            import datetime
            ts = first_info["started_at"] / 1000
            dt = datetime.datetime.fromtimestamp(ts)
            first_label = f"管线 {dt.strftime('%H:%M')}"

        all_candidates = []
        all_events = []

        for session_key in cluster_keys:
            info = cluster_infos[session_key]
            transcript = info.get("transcript", info.get("sessionFile", ""))
            if not transcript or not Path(transcript).exists():
                continue

            events = parse_transcript(transcript)
            if not events:
                continue

            # time-range scope: 过滤时间窗口
            if args.scope == "time-range":
                events = _filter_events_time_range(events, args.time_from, args.time_to)

            all_events.extend(events)

            # L1: detect candidates
            candidates = detect_issues(events, info.get("label", ""))
            for c in candidates:
                c["session_key"] = session_key
                c["session_label"] = info.get("label", session_key.split(":")[-1][:20])
            all_candidates.extend(candidates)

        runtime_ms = sum(cluster_infos[k].get("runtime_ms", 0) for k in cluster_keys)
        tokens = sum(cluster_infos[k].get("tokens", 0) for k in cluster_keys)

        report = {
            "root_key": cluster_keys[0],
            "root_label": first_label,
            "agents": len(cluster_keys),
            "tokens": tokens,
            "runtime_ms": runtime_ms,
            "candidates": all_candidates,
            "events_count": len(all_events),
            "diagnosis": None,
            "chains": [],
        }

        # ── Step 4: L2 LLM 分析 ──
        if not args.no_llm and all_candidates:
            try:
                from llm_analyzer import analyze_candidates
                print(f"  🔍 L2: 分析 {len(all_candidates)} 个候选问题...", file=sys.stderr)
                pipeline_meta = {
                    "agent_count": len(cluster_keys),
                    "runtime_seconds": runtime_ms // 1000,
                    "tokens": tokens,
                }
                diagnosis = analyze_candidates(
                    candidates=all_candidates,
                    events=all_events,
                    session_label=first_label,
                    pipeline_meta=pipeline_meta,
                )
                report["diagnosis"] = diagnosis
            except Exception as e:
                print(f"  ⚠️ L2 LLM 分析失败: {e}", file=sys.stderr)
                report["diagnosis"] = {"error": str(e)}

        session_reports.append(report)

    _output_reports(session_reports, args)


# ---------------------------------------------------------------------------
# Pipeline scope implementation
# ---------------------------------------------------------------------------

def _run_pipeline_scope(args) -> list[dict]:
    """
    Pipeline 模式: 从 blackboard 发现管线运行，聚焦 gate 门控检测。
    """
    # 发现管线运行
    runs = discover_pipeline_runs(
        blackboard_dir=args.pipeline_dir,
        hours=args.hours,
    )

    if args.run_id:
        runs = [r for r in runs if args.run_id in r["run_id"]]

    if not runs:
        return []

    # 打印发现的管线
    print(f"  📋 发现 {len(runs)} 条管线运行 (scope=pipeline)", file=sys.stderr)
    for r in runs:
        print(f"     {get_run_summary(r)}", file=sys.stderr)

    # 需要找到对应的 session transcript
    # 策略: 扫描所有 agent sessions，找与管线时间窗口重叠的
    tree = build_session_tree()
    session_reports = []

    for run in runs:
        report = _analyze_single_pipeline_run(run, tree, args)
        if report:
            session_reports.append(report)

    return session_reports


def _analyze_single_pipeline_run(run: dict, tree: dict, args) -> dict | None:
    """分析单条管线运行。"""
    started = run["started_at"]
    completed = run["completed_at"]
    label = f"{run['pipeline_name']} [{run['domain']}]"

    # 找匹配的 session transcript（只匹配 subagent sessions，排除 main session）
    matching_transcripts = []
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    _shanghai_tz = _tz(_td(hours=8))

    for session_key, info in tree["sessions"].items():
        # 只匹配 subagent sessions（管线在子 Agent 中执行）
        if "subagent" not in session_key:
            continue

        session_start_ms = info.get("started_at", 0)
        if not session_start_ms:
            continue

        session_start = _dt.fromtimestamp(session_start_ms / 1000, tz=_shanghai_tz)

        # 检查时间重叠: subagent 启动时间在管线窗口内
        buffer = _td(minutes=5)
        if (started - buffer) <= session_start <= (completed + buffer):
            transcript = info.get("transcript", info.get("sessionFile", ""))
            if transcript and Path(transcript).exists():
                matching_transcripts.append((session_key, transcript, info))

    if not matching_transcripts:
        # 没有匹配的 session，仍然从 run_info 生成基本报告
        return _report_from_run_info(run, label)

    all_candidates = []
    all_events = []

    for session_key, transcript, info in matching_transcripts:
        events = parse_transcript(transcript)
        if not events:
            continue

        # 按管线时间窗口过滤
        filtered = filter_events_by_run(events, run)
        all_events.extend(filtered)

        # 使用管线专用检测器
        candidates = detect_pipeline_issues(filtered, run_info=run)
        for c in candidates:
            c["session_key"] = session_key
            c["session_label"] = label
        all_candidates.extend(candidates)

    runtime_secs = int((completed - started).total_seconds())
    tokens = sum(info.get("tokens", 0) for _, _, info in matching_transcripts)

    report = {
        "root_key": matching_transcripts[0][0] if matching_transcripts else "unknown",
        "root_label": label,
        "agents": len(run.get("agents", {})),
        "tokens": tokens,
        "runtime_ms": runtime_secs * 1000,
        "candidates": all_candidates,
        "events_count": len(all_events),
        "total_events_before_filter": sum(
            len(parse_transcript(t)) for _, t, _ in matching_transcripts
        ),
        "scope": "pipeline",
        "run_info": {
            "run_id": run["run_id"],
            "domain": run["domain"],
            "status": run["status"],
            "agents": run["agents"],
        },
        "diagnosis": None,
        "chains": [],
    }

    # L2 LLM 分析
    if not args.no_llm and all_candidates:
        try:
            from llm_analyzer import analyze_candidates
            print(f"  🔍 L2: 分析 {len(all_candidates)} 个候选问题...", file=sys.stderr)
            diagnosis = analyze_candidates(
                candidates=all_candidates,
                events=all_events,
                session_label=label,
                pipeline_meta={
                    "agent_count": len(run.get("agents", {})),
                    "runtime_seconds": runtime_secs,
                    "tokens": tokens,
                },
            )
            report["diagnosis"] = diagnosis
        except Exception as e:
            print(f"  ⚠️ L2 LLM 分析失败: {e}", file=sys.stderr)

    return report


def _report_from_run_info(run: dict, label: str) -> dict:
    """
    没有匹配 session transcript 时，从 pipeline_state.json 生成基本报告。
    只检查 gate 健康度（不需要 transcript）。
    """
    candidates = detect_pipeline_issues([], run_info=run)

    return {
        "root_key": "no-transcript",
        "root_label": label + " (无 transcript)",
        "agents": len(run.get("agents", {})),
        "tokens": 0,
        "runtime_ms": 0,
        "candidates": candidates,
        "events_count": 0,
        "scope": "pipeline",
        "run_info": {
            "run_id": run["run_id"],
            "domain": run["domain"],
            "status": run["status"],
            "agents": run["agents"],
        },
        "diagnosis": None,
        "chains": [],
    }


def _filter_events_time_range(events: list[dict], time_from: str | None, time_to: str | None) -> list[dict]:
    """按时间窗口过滤事件。"""
    from datetime import datetime, timezone, timedelta
    from pipeline_scope import _parse_event_ts

    shanghai_tz = timezone(timedelta(hours=8))

    def parse_time_arg(t: str) -> datetime:
        """解析 HH:MM 或 ISO 格式。"""
        if ":" in t and len(t) <= 5:
            # HH:MM → today
            h, m = int(t.split(":")[0]), int(t.split(":")[1])
            now = datetime.now(shanghai_tz)
            return now.replace(hour=h, minute=m, second=0, microsecond=0)
        else:
            # ISO format
            dt = datetime.fromisoformat(t)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=shanghai_tz)
            return dt

    if not time_from and not time_to:
        return events

    window_start = parse_time_arg(time_from) if time_from else None
    window_end = parse_time_arg(time_to) if time_to else None

    filtered = []
    for ev in events:
        ev_ts = _parse_event_ts(ev.get("ts"))
        if ev_ts is None:
            continue
        if window_start and ev_ts < window_start:
            continue
        if window_end and ev_ts > window_end:
            continue
        filtered.append(ev)

    return filtered


def _output_reports(session_reports: list[dict], args):
    """统一输出入口。"""
    # ── Step 5: L3 输出 ──
    if args.json:
        for r in session_reports:
            r.pop("events_count", None)
            r.pop("total_events_before_filter", None)
            r.pop("run_info", None)
        print(json.dumps(session_reports, indent=2, ensure_ascii=False, default=str))
    else:
        print_report_v2(session_reports, quiet=args.quiet)


def print_report_v2(reports: list[dict], quiet: bool = False):
    """V2 报告：包含 LLM 诊断 + 修复建议 + 反思。"""
    print(f"\n{'='*65}")
    print(f"  🩺 DeepFlow Doctor V2 诊断报告")
    print(f"  扫描 {len(reports)} 条管线")

    # 显示 scope 信息
    scopes = set(r.get("scope", "agent") for r in reports)
    if "pipeline" in scopes:
        print(f"  🔬 Scope: pipeline (仅管线执行窗口)")
    elif "time-range" in scopes:
        print(f"  🔬 Scope: time-range (自定义时间窗口)")
    print(f"{'='*65}")

    for report in reports:
        label = report["root_label"][:45]
        diagnosis = report.get("diagnosis")

        # Header
        scope_badge = ""
        if report.get("scope") == "pipeline":
            scope_badge = " [pipeline]"
            total_before = report.get("total_events_before_filter", 0)
            filtered_count = report.get("events_count", 0)
            if total_before > 0:
                scope_badge += f" ({filtered_count}/{total_before} events)"

        print(f"\n  📦 {label}{scope_badge}")
        print(f"     Agents: {report['agents']} | Tokens: {report['tokens']:,} | Runtime: {report['runtime_ms']//1000}s")
        print(f"     L1 候选: {len(report['candidates'])} 个")

        # Show run_info if pipeline scope
        run_info = report.get("run_info", {})
        if run_info and run_info.get("agents"):
            agents = run_info["agents"]
            passed = sum(1 for a in agents.values() if a.get("state") == "gate_pass")
            retries = sum(a.get("retry_count", 0) for a in agents.values())
            print(f"     Gate: {passed}/{len(agents)} pass | Total retries: {retries}")

        if diagnosis is None:
            print(f"     L2: 未启用（--no-llm）")
            for c in report["candidates"][:5]:
                et = c.get("error_type", c.get("category", "?"))
                print(f"       • [{c.get('session_label','')[:20]}] {et}: {c.get('evidence','')[:100]}")
            if len(report["candidates"]) > 5:
                print(f"       ... 还有 {len(report['candidates'])-5} 个")
            continue

        if "error" in diagnosis:
            print(f"     L2: ❌ 分析失败: {diagnosis['error']}")
            continue

        summary = diagnosis.get("summary", {})
        tp = summary.get("true_positives", 0)
        fp = summary.get("false_positives", 0)
        print(f"     L2: ✅ {tp} 真问题 / {fp} 误报 / {len(report['candidates'])} 候选")

        # ── True Positives ──
        true_diagnoses = [d for d in diagnosis.get("diagnoses", []) if d.get("verdict") == "true_positive"]
        systemic = diagnosis.get("systemic_issues", [])

        if true_diagnoses:
            by_root = {}
            for d in true_diagnoses:
                rc = d.get("root_cause", "未知")
                if rc not in by_root:
                    by_root[rc] = []
                by_root[rc].append(d)

            print(f"\n     🔴 真实问题 ({len(true_diagnoses)} 个, {len(by_root)} 个独立根因):")
            for root_cause, items in by_root.items():
                d = items[0]
                impact_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(d.get("impact", ""), "⚪")
                suffix = f" (×{len(items)})" if len(items) > 1 else ""
                print(f"       {impact_icon} [{d.get('impact','?').upper()}] {root_cause}{suffix}")
                print(f"          理由: {d.get('reason', '')}")
                print()

        if systemic:
            print(f"\n     🔧 系统性修复建议 ({len(systemic)} 个):")
            for s in systemic:
                print(f"       [{s.get('priority', '?')}] {s.get('root_cause', '')}")
                print(f"          影响: {s.get('affected_count', 0)} 个问题共享此根因")
                print(f"          修复: {s.get('systemic_fix', '')}")
                print()

        isolated = [d for d in true_diagnoses if not d.get("cluster_id")]
        if isolated:
            print(f"     🔩 孤立修复建议 ({len(isolated)} 个):")
            for d in isolated:
                print(f"       • {d.get('fix_suggestion', '无')}")
            print()

        # ── Reflection ──
        reflection = diagnosis.get("reflection", {})
        confidence = reflection.get("overall_confidence", 0)
        conf_icon = "🟢" if confidence >= 80 else "🟡" if confidence >= 60 else "🔴"
        print(f"\n     {conf_icon} 反思自检:")
        print(f"       置信度: {confidence}%")
        if reflection.get("missed_anything") and reflection["missed_anything"] != "无":
            print(f"       遗漏: {reflection['missed_anything']}")
        if reflection.get("contradictions") and reflection["contradictions"] not in ("无", "none", "无矛盾"):
            print(f"       矛盾: {reflection['contradictions']}")
        print(f"       覆盖: {reflection.get('coverage_check', '?')}")

        top_fix = summary.get("top_priority_fix", "")
        if top_fix:
            print(f"\n     🎯 最优先修复: {top_fix}")

    # ── Global Summary ──
    print(f"\n{'='*65}")
    print(f"  📊 全局汇总")
    print(f"{'='*65}")

    total_tp = 0
    total_fp = 0
    total_systemic = 0
    all_top_fixes = []

    for report in reports:
        diag = report.get("diagnosis", {})
        if isinstance(diag, dict) and "summary" in diag:
            s = diag["summary"]
            total_tp += s.get("true_positives", 0)
            total_fp += s.get("false_positives", 0)
            total_systemic += s.get("systemic_count", 0)
            if s.get("top_priority_fix"):
                all_top_fixes.append(s["top_priority_fix"])

    total_candidates = sum(len(r["candidates"]) for r in reports)
    print(f"  L1 候选: {total_candidates}")
    print(f"  L2 判定: {total_tp} 真问题 + {total_fp} 误报")
    print(f"  系统性问题: {total_systemic}")
    if total_candidates > 0:
        print(f"  误报率: {total_fp/total_candidates*100:.0f}%")

    if all_top_fixes:
        print(f"\n  🎯 优先修复清单:")
        for i, fix in enumerate(all_top_fixes[:5], 1):
            print(f"     {i}. {fix}")

    print(f"\n{'='*65}\n")


if __name__ == "__main__":
    main()
