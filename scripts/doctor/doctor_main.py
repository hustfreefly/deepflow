#!/usr/bin/env python3
"""
DeepFlow Doctor V2 — 主入口

三层漏斗架构:
  L1 (确定性代码): parse transcript → detect candidates
  L2 (LLM 分析):  candidates + context → structured diagnosis + fix suggestions
  L3 (格式化输出): diagnosis → human-readable report

用法:
    python3 scripts/doctor/doctor_main.py                    # 扫描最近 24h
    python3 scripts/doctor/doctor_main.py --hours 6          # 扫描最近 6h
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
from pattern_detector import detect_issues
from causal_tracer import build_session_tree, get_session_family, trace_causal_chain, find_recent_pipeline_sessions


def main():
    parser = argparse.ArgumentParser(description="DeepFlow Doctor V2 — AI Native 多 Agent 运行诊断")
    parser.add_argument("--hours", type=int, default=24, help="扫描最近 N 小时的 sessions")
    parser.add_argument("--session", type=str, help="扫描指定 session (key 或 id)")
    parser.add_argument("--all-today", action="store_true", help="扫描今天所有管线")
    parser.add_argument("--no-llm", action="store_true", help="跳过 L2 LLM 分析，只输出 L1 候选")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--quiet", action="store_true", help="只输出问题，不输出正常 session 信息")
    args = parser.parse_args()

    # ── Step 1: 构建 session 树 ──
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
            "diagnosis": None,  # Will be filled by L2
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

    # ── Step 5: L3 输出 ──
    if args.json:
        # Remove raw events from JSON output (too large)
        for r in session_reports:
            r.pop("events_count", None)
        print(json.dumps(session_reports, indent=2, ensure_ascii=False, default=str))
    else:
        print_report_v2(session_reports, quiet=args.quiet)


def print_report_v2(reports: list[dict], quiet: bool = False):
    """V2 报告：包含 LLM 诊断 + 修复建议 + 反思。"""
    print(f"\n{'='*65}")
    print(f"  🩺 DeepFlow Doctor V2 诊断报告")
    print(f"  扫描 {len(reports)} 条管线")
    print(f"{'='*65}")

    for report in reports:
        label = report["root_label"][:45]
        diagnosis = report.get("diagnosis")

        # Header
        print(f"\n  📦 {label}")
        print(f"     Agents: {report['agents']} | Tokens: {report['tokens']:,} | Runtime: {report['runtime_ms']//1000}s")
        print(f"     L1 候选: {len(report['candidates'])} 个")

        if diagnosis is None:
            print(f"     L2: 未启用（--no-llm）")
            # Fallback: show L1 candidates
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

        # ── True Positives (deduplicated by root_cause) ──
        true_diagnoses = [d for d in diagnosis.get("diagnoses", []) if d.get("verdict") == "true_positive"]
        systemic = diagnosis.get("systemic_issues", [])
        systemic_cluster_ids = {s.get("cluster_id") for s in systemic}

        if true_diagnoses:
            # Group by root_cause to deduplicate
            by_root = {}
            for d in true_diagnoses:
                rc = d.get("root_cause", "未知")
                if rc not in by_root:
                    by_root[rc] = []
                by_root[rc].append(d)

            print(f"\n     🔴 真实问题 ({len(true_diagnoses)} 个, {len(by_root)} 个独立根因):")
            for root_cause, items in by_root.items():
                count = len(items)
                d = items[0]  # representative
                impact_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(d.get("impact", ""), "⚪")
                suffix = f" (×{count})" if count > 1 else ""
                print(f"       {impact_icon} [{d.get('impact','?').upper()}] {root_cause}{suffix}")
                print(f"          理由: {d.get('reason', '')}")
                print()

        # ── Systemic Issues ──
        if systemic:
            print(f"\n     🔧 系统性修复建议 ({len(systemic)} 个):")
            for s in systemic:
                print(f"       [{s.get('priority', '?')}] {s.get('root_cause', '')}")
                print(f"          影响: {s.get('affected_count', 0)} 个问题共享此根因")
                print(f"          修复: {s.get('systemic_fix', '')}")
                print()

        # ── Isolated Fixes (non-systemic true positives) ──
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

        # ── Top Priority ──
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
    print(f"  误报率: {total_fp/(total_candidates or 1)*100:.0f}%")

    if all_top_fixes:
        print(f"\n  🎯 优先修复清单:")
        for i, fix in enumerate(all_top_fixes[:5], 1):
            print(f"     {i}. {fix}")

    print(f"\n{'='*65}\n")


if __name__ == "__main__":
    main()
