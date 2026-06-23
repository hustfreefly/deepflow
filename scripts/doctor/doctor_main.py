#!/usr/bin/env python3
"""
DeepFlow Doctor — 主入口

用法:
    python3 scripts/doctor/doctor_main.py                    # 扫描最近 24h 的管线
    python3 scripts/doctor/doctor_main.py --hours 6          # 扫描最近 6h
    python3 scripts/doctor/doctor_main.py --session <id>     # 扫描指定 session
    python3 scripts/doctor/doctor_main.py --all-today        # 今天所有管线
"""

import argparse
import json
import sys
import time
from pathlib import Path

# 确保可以 import 同目录模块
sys.path.insert(0, str(Path(__file__).parent))

from transcript_parser import parse_transcript
from pattern_detector import detect_issues
from causal_tracer import build_session_tree, get_session_family, trace_causal_chain, find_recent_pipeline_sessions


def main():
    parser = argparse.ArgumentParser(description="DeepFlow Doctor — 多 Agent 运行诊断")
    parser.add_argument("--hours", type=int, default=24, help="扫描最近 N 小时的 sessions")
    parser.add_argument("--session", type=str, help="扫描指定 session (key 或 id)")
    parser.add_argument("--all-today", action="store_true", help="扫描今天所有管线")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--quiet", action="store_true", help="只输出问题，不输出正常 session 信息")
    args = parser.parse_args()

    # Step 1: 构建 session 树
    tree = build_session_tree()
    if not tree["sessions"]:
        print("❌ 无法加载 sessions.json")
        return

    # Step 2: 确定要扫描的 sessions
    if args.session:
        # 精确匹配
        target_keys = [k for k in tree["sessions"] if args.session in k]
        if not target_keys:
            print(f"❌ 未找到包含 '{args.session}' 的 session")
            return
    else:
        # 找今天的管线: 按时间窗口分组（2小时内的子 agent 归为同一管线）
        import datetime
        if args.all_today:
            cutoff = int(datetime.datetime.now().replace(hour=0, minute=0, second=0).timestamp() * 1000)
        else:
            cutoff = int((time.time() - args.hours * 3600) * 1000)

        # 收集所有子 agent sessions（按 started_at 排序）
        sub_sessions = sorted(
            [(k, v) for k, v in tree["sessions"].items()
             if v["started_at"] >= cutoff and "subagent" in k],
            key=lambda x: x[1]["started_at"]
        )

        if not sub_sessions:
            print(f"最近 {args.hours}h 没有子 Agent session。")
            return

        # 按时间窗口分组（2小时间隔 = 不同管线）
        clusters = []
        current_cluster = [sub_sessions[0]]
        for item in sub_sessions[1:]:
            prev_ts = current_cluster[-1][1]["started_at"]
            curr_ts = item[1]["started_at"]
            if curr_ts - prev_ts > 2 * 3600 * 1000:  # 2h gap
                clusters.append(current_cluster)
                current_cluster = [item]
            else:
                current_cluster.append(item)
        clusters.append(current_cluster)

        target_keys = clusters  # list of list of (key, info) tuples

    if not target_keys:
        print(f"没有管线 session。")
        return

    # Step 3: 逐 cluster 分析
    session_reports = []

    for cluster in target_keys:
        # cluster 是 [(key, info), ...] 列表
        cluster_keys = [item[0] for item in cluster]
        cluster_infos = {item[0]: item[1] for item in cluster}

        # 管线名: 取第一个 session 的 label，或用时间范围
        first_info = cluster[0][1]
        first_label = first_info.get("label", "")
        if not first_label:
            # 用时间范围命名
            import datetime
            ts = first_info["started_at"] / 1000
            dt = datetime.datetime.fromtimestamp(ts)
            first_label = f"管线 {dt.strftime('%H:%M')}"

        cluster_issues = []

        for session_key in cluster_keys:
            info = cluster_infos[session_key]
            transcript = info.get("transcript", info.get("sessionFile", ""))
            if not transcript or not Path(transcript).exists():
                continue

            # 解析 transcript
            events = parse_transcript(transcript)
            if not events:
                continue

            # 检测问题
            issues = detect_issues(events, info.get("label", ""))
            for issue in issues:
                issue["session_key"] = session_key
                issue["session_label"] = info.get("label", session_key.split(":")[-1][:20])
            cluster_issues.extend(issues)

        session_reports.append({
            "root_key": cluster_keys[0],
            "root_label": first_label,
            "agents": len(cluster_keys),
            "issues": cluster_issues,
            "chains": [],  # 因果链需要 parent-child 关系，当前用 cluster 模式暂跳过
            "tokens": sum(cluster_infos[k].get("tokens", 0) for k in cluster_keys),
            "runtime_ms": sum(cluster_infos[k].get("runtime_ms", 0) for k in cluster_keys),
        })

    # Step 4: 输出
    if args.json:
        print(json.dumps(session_reports, indent=2, ensure_ascii=False, default=str))
    else:
        print_report(session_reports, quiet=args.quiet)


def _subtree(tree: dict, root_key: str) -> dict:
    """提取以 root_key 为根的子树。"""
    family = get_session_family(tree, root_key)
    family_set = set(family)
    return {
        "roots": [root_key],
        "children": {k: [c for c in v if c in family_set] for k, v in tree["children"].items() if k in family_set},
        "sessions": {k: v for k, v in tree["sessions"].items() if k in family_set},
    }


def print_report(reports: list[dict], quiet: bool = False):
    """打印可读报告。"""
    print(f"\n{'='*65}")
    print(f"  🩺 DeepFlow Doctor 诊断报告")
    print(f"  扫描 {len(reports)} 条管线")
    print(f"{'='*65}")

    total_issues = 0
    total_red = 0
    total_yellow = 0
    total_wasted_tokens = 0
    total_wasted_seconds = 0

    for report in reports:
        issues = report["issues"]
        red = [i for i in issues if i["severity"] == "red"]
        yellow = [i for i in issues if i["severity"] == "yellow"]
        wasted_tokens = sum(i.get("wasted_tokens", 0) for i in issues)
        wasted_seconds = sum(i.get("wasted_seconds", 0) for i in issues)

        total_issues += len(issues)
        total_red += len(red)
        total_yellow += len(yellow)
        total_wasted_tokens += wasted_tokens
        total_wasted_seconds += wasted_seconds

        # Session 概览
        label = report["root_label"][:45]
        status_icon = "🔴" if red else ("🟡" if yellow else "🟢")
        print(f"\n  {status_icon} {label}")
        print(f"     Agents: {report['agents']} | Tokens: {report['tokens']:,} | Runtime: {report['runtime_ms']//1000}s")

        if not issues:
            if not quiet:
                print(f"     ✅ 无问题")
            continue

        # 按类别分组
        by_category = {}
        for i in issues:
            by_category.setdefault(i["category"], []).append(i)

        cat_labels = {
            "T1": "🔴 工具错误自动恢复",
            "T2": "🟡 门控失效",
            "T3": "🟡 静默降级",
            "T4": "🟡 范围失控",
        }

        for cat in ["T1", "T2", "T3", "T4"]:
            cat_issues = by_category.get(cat, [])
            if not cat_issues:
                continue
            print(f"\n     {cat_labels[cat]} ({len(cat_issues)} 个)")
            for issue in cat_issues[:5]:  # 最多显示 5 个
                desc = issue["description"]
                agent = issue.get("session_label", "")[:25]
                evidence = issue.get("evidence", "")[:100].replace("\n", " ")
                waste = issue.get("wasted_tokens", 0)
                print(f"       • [{agent}] {desc}")
                print(f"         {evidence}")
                if waste > 0:
                    print(f"         浪费: ~{waste:,} tokens / ~{issue.get('wasted_seconds', 0):.0f}s")
            if len(cat_issues) > 5:
                print(f"       ... 还有 {len(cat_issues)-5} 个")

        # 因果链
        if report["chains"]:
            print(f"\n     🔗 因果链:")
            for chain in report["chains"][:3]:
                print(f"       根因: {chain['root_label'][:30]}")
                print(f"       影响: {chain['downstream_sessions']} 个下游 Agent, {chain['downstream_issues']} 个问题")
                print(f"       总浪费: ~{chain['total_wasted_tokens']:,} tokens")

    # 汇总
    print(f"\n{'='*65}")
    print(f"  📊 汇总")
    print(f"{'='*65}")
    print(f"  🔴 严重问题: {total_red}")
    print(f"  🟡 警告问题: {total_yellow}")
    print(f"  总问题数: {total_issues}")
    print(f"  浪费 Token: ~{total_wasted_tokens:,}")
    print(f"  浪费时间: ~{total_wasted_seconds/60:.1f} 分钟")

    # 按错误类型汇总
    error_types = {}
    for report in reports:
        for issue in report["issues"]:
            if issue.get("error_type"):
                error_types[issue["error_type"]] = error_types.get(issue["error_type"], 0) + 1

    if error_types:
        print(f"\n  📋 错误类型分布:")
        for etype, count in sorted(error_types.items(), key=lambda x: -x[1]):
            print(f"     {etype}: {count} 次")

    print(f"\n{'='*65}\n")


if __name__ == "__main__":
    main()
