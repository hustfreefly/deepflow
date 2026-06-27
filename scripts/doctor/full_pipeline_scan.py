#!/usr/bin/env python3
"""
DeepFlow Doctor — Full Pipeline Scan
系统性扫描 Spec Pro → Solution Pro → Ship Pro 全流程
检测: T1 工具错误自恢复 | T2 门控失效 | T3 静默降级 | T4 范围失控 | T5 LLM困惑
"""

import json
import sys
import os
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

SESSIONS_DIR = Path.home() / ".openclaw" / "agents" / "researcher" / "sessions"

# ── 1. Load all today's sessions ──
def load_sessions():
    sessions = {}
    for f in SESSIONS_DIR.glob("*.jsonl"):
        if "trajectory" in f.name:
            continue
        sid = f.stem
        events = []
        for line in f.read_text(errors="replace").strip().split("\n"):
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        if events:
            # Check if session is from today
            first_ts = events[0].get("ts", events[0].get("timestamp", ""))
            if "2026-06-27" in str(first_ts) or "2026-06-27" in str(f.stat().st_mtime):
                sessions[sid] = events
    return sessions

def get_session_label(events):
    """Extract session label from first user message or system context"""
    for e in events[:5]:
        if e.get("role") == "user":
            content = str(e.get("content", ""))[:100]
            if content:
                return content[:80]
        if e.get("role") == "system":
            content = str(e.get("content", ""))
            if "label" in content:
                try:
                    d = json.loads(content)
                    return d.get("label", "?")[:80]
                except:
                    pass
    return "?"

# ── 2. Pattern Detection ──
def analyze_session(sid, events):
    """Analyze a single session for all issue types"""
    report = {
        "sid": sid,
        "label": get_session_label(events),
        "event_count": len(events),
        "tool_calls": [],
        "tool_errors": [],
        "t1_self_recovery": [],
        "t2_gate_failures": [],
        "t3_silent_degradation": [],
        "t4_scope_creep": [],
        "t5_llm_confusion": [],
        "wasted_tokens": 0,
        "retry_chains": [],
    }
    
    prev_tool_error = None
    tool_chain = []
    exec_errors = []
    
    for i, e in enumerate(events):
        role = e.get("role", "")
        
        # ── Track tool calls ──
        if role == "assistant":
            # Check for tool_use in content
            content = e.get("content", "")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "tool_use":
                        tool_name = part.get("name", "")
                        tool_input = part.get("input", {})
                        report["tool_calls"].append({
                            "index": i,
                            "name": tool_name,
                            "input_preview": str(tool_input)[:150]
                        })
            elif isinstance(content, str) and "tool_use" in content:
                pass  # already parsed
        
        # ── Track tool results (errors) ──
        if role == "tool":
            content = str(e.get("content", ""))
            tool_id = e.get("tool_call_id", e.get("tool_use_id", ""))
            
            is_error = any(kw in content.lower() for kw in [
                "error", "traceback", "exception", "failed", "not found",
                "permission denied", "no such file", "modulenotfound",
                "filenotfound", "keyerror", "attributeerror", "importerror",
                "typeerror", "valueerror", "indexerror", "nameerror",
                "command not found", "exit code", "returned non-zero",
                "timed out", "timeout", "killed", "segfault"
            ])
            
            if is_error:
                error_type = "unknown"
                if "ModuleNotFoundError" in content or "ImportError" in content:
                    error_type = "import_error"
                elif "FileNotFoundError" in content or "No such file" in content:
                    error_type = "file_not_found"
                elif "KeyError" in content:
                    error_type = "key_error"
                elif "AttributeError" in content:
                    error_type = "attribute_error"
                elif "TypeError" in content:
                    error_type = "type_error"
                elif "Permission denied" in content:
                    error_type = "permission"
                elif "command not found" in content or "not recognized" in content:
                    error_type = "command_not_found"
                elif "timeout" in content.lower() or "timed out" in content.lower():
                    error_type = "timeout"
                elif "JSONDecodeError" in content or "json.decoder" in content.lower():
                    error_type = "json_parse_error"
                elif "ValueError" in content:
                    error_type = "value_error"
                elif "IndexError" in content:
                    error_type = "index_error"
                elif "NameError" in content:
                    error_type = "name_error"
                elif "exit code" in content.lower() or "returned non-zero" in content:
                    error_type = "exit_code_error"
                
                report["tool_errors"].append({
                    "index": i,
                    "tool_id": tool_id,
                    "error_type": error_type,
                    "error_preview": content[:300]
                })
                exec_errors.append({"index": i, "type": error_type, "content": content[:500]})
                
                # T1: Check if next assistant message retries the same tool
                if prev_tool_error is not None and (i - prev_tool_error["index"]) <= 3:
                    report["t1_self_recovery"].append({
                        "error_index": prev_tool_error["index"],
                        "recovery_index": i,
                        "error_type": prev_tool_error["error_type"],
                    })
                prev_tool_error = report["tool_errors"][-1]
            else:
                prev_tool_error = None
        
        # ── T3: Silent degradation detection ──
        if role == "assistant":
            content = str(e.get("content", ""))
            # Check for fallback/degradation language
            degradation_signals = [
                "fallback", "降级", "mock", "模拟", "跳过", "skip",
                "暂时使用", "简化处理", "忽略此步骤", "继续执行",
                "使用默认值", "default value", "not available, using",
                "couldn't find, will use", "failed but continuing"
            ]
            for sig in degradation_signals:
                if sig in content.lower():
                    report["t3_silent_degradation"].append({
                        "index": i,
                        "signal": sig,
                        "preview": content[max(0, content.find(sig)-50):content.find(sig)+100]
                    })
                    break
        
        # ── T4: Scope creep detection ──
        if role == "assistant":
            content = str(e.get("content", ""))
            scope_signals = [
                "顺便", "另外我注意到", "同时优化", "额外添加",
                "虽然不在范围内", "额外发现", "unrelated", "bonus",
                "while I'm at it", "also noticed", "refactoring"
            ]
            for sig in scope_signals:
                if sig in content.lower():
                    report["t4_scope_creep"].append({
                        "index": i,
                        "signal": sig,
                        "preview": content[max(0, content.find(sig)-50):content.find(sig)+100]
                    })
                    break
        
        # ── T5: LLM confusion detection ──
        if role == "assistant":
            content = str(e.get("content", ""))
            confusion_signals = [
                "我不确定", "我不太确定", "不太清楚", "可能是",
                "让我试试", "let me try", "I'm not sure",
                "这可能需要", "hmm", "奇怪", "unexpected",
                "让我检查一下", "let me check", "让我看看",
                "让我重新", "let me re-", "让我再",
                "抱歉", "sorry", "apologies",
                "我之前搞错了", "I was wrong", "my mistake",
                "实际上", "actually", "原来", "apparently",
                "wait,", "等等", "不对",
                "让我纠正", "correction", "修正"
            ]
            for sig in confusion_signals:
                if sig in content.lower():
                    report["t5_llm_confusion"].append({
                        "index": i,
                        "signal": sig,
                        "preview": content[max(0, content.find(sig)-30):content.find(sig)+120]
                    })
                    break
    
    # ── Build retry chains (consecutive errors on same topic) ──
    if len(exec_errors) >= 2:
        chain = [exec_errors[0]]
        for j in range(1, len(exec_errors)):
            if exec_errors[j]["index"] - exec_errors[j-1]["index"] <= 8:
                chain.append(exec_errors[j])
            else:
                if len(chain) >= 2:
                    report["retry_chains"].append({
                        "length": len(chain),
                        "errors": [{"index": c["index"], "type": c["type"]} for c in chain]
                    })
                chain = [exec_errors[j]]
        if len(chain) >= 2:
            report["retry_chains"].append({
                "length": len(chain),
                "errors": [{"index": c["index"], "type": c["type"]} for c in chain]
            })
    
    return report

# ── 3. Main ──
def main():
    print("=" * 80)
    print("🩺 DeepFlow Doctor — Full Pipeline Scan")
    print("   扫描范围: 2026-06-27 全天 sessions")
    print("=" * 80)
    
    sessions = load_sessions()
    print(f"\n📁 发现 {len(sessions)} 个今日 session")
    
    all_reports = []
    total_tool_calls = 0
    total_errors = 0
    total_t1 = 0
    total_t3 = 0
    total_t4 = 0
    total_t5 = 0
    total_chains = 0
    
    error_type_counter = Counter()
    confusion_signal_counter = Counter()
    
    for sid, events in sorted(sessions.items(), key=lambda x: x[1][0].get("ts", "")):
        report = analyze_session(sid, events)
        all_reports.append(report)
        
        total_tool_calls += len(report["tool_calls"])
        total_errors += len(report["tool_errors"])
        total_t1 += len(report["t1_self_recovery"])
        total_t3 += len(report["t3_silent_degradation"])
        total_t4 += len(report["t4_scope_creep"])
        total_t5 += len(report["t5_llm_confusion"])
        total_chains += len(report["retry_chains"])
        
        for err in report["tool_errors"]:
            error_type_counter[err["error_type"]] += 1
        
        for conf in report["t5_llm_confusion"]:
            confusion_signal_counter[conf["signal"]] += 1
    
    # ── Summary ──
    print(f"\n{'='*80}")
    print(f"📊 全局统计")
    print(f"{'='*80}")
    print(f"  总 Tool 调用:        {total_tool_calls}")
    print(f"  总 Tool 错误:        {total_errors} ({total_errors*100//(total_tool_calls or 1)}% 错误率)")
    print(f"  T1 自恢复:           {total_t1}")
    print(f"  T3 静默降级:         {total_t3}")
    print(f"  T4 范围失控:         {total_t4}")
    print(f"  T5 LLM 困惑:        {total_t5}")
    print(f"  重试链:              {total_chains}")
    
    print(f"\n📊 错误类型分布:")
    for etype, count in error_type_counter.most_common(15):
        bar = "█" * count
        print(f"  {etype:25s} {count:3d} {bar}")
    
    print(f"\n📊 LLM 困惑信号分布:")
    for sig, count in confusion_signal_counter.most_common(15):
        bar = "█" * count
        print(f"  {sig:25s} {count:3d} {bar}")
    
    # ── Per-session detail (only sessions with issues) ──
    print(f"\n{'='*80}")
    print(f"🔍 逐 Session 分析 (仅展示有问题的)")
    print(f"{'='*80}")
    
    issue_sessions = [r for r in all_reports if 
                      r["tool_errors"] or r["t1_self_recovery"] or 
                      r["t3_silent_degradation"] or r["t5_llm_confusion"] or
                      r["retry_chains"]]
    
    for r in sorted(issue_sessions, key=lambda x: -(len(x["tool_errors"]) + len(x["t5_llm_confusion"]))):
        has_issues = (r["tool_errors"] or r["t5_llm_confusion"] or r["retry_chains"])
        if not has_issues:
            continue
            
        print(f"\n{'─'*60}")
        print(f"📋 Session: {r['sid'][:12]}...")
        print(f"   Label: {r['label']}")
        print(f"   Events: {r['event_count']}")
        print(f"   Tool Calls: {len(r['tool_calls'])} | Errors: {len(r['tool_errors'])} | "
              f"T1: {len(r['t1_self_recovery'])} | T5: {len(r['t5_llm_confusion'])} | "
              f"Chains: {len(r['retry_chains'])}")
        
        if r["tool_errors"]:
            print(f"\n   🔴 Tool Errors:")
            for err in r["tool_errors"][:10]:
                preview = err["error_preview"][:150].replace("\n", " ")
                print(f"     [{err['error_type']:20s}] {preview}")
        
        if r["retry_chains"]:
            print(f"\n   🟡 Retry Chains:")
            for chain in r["retry_chains"][:5]:
                types = " → ".join([e["type"] for e in chain["errors"]])
                print(f"     链长 {chain['length']}: {types}")
        
        if r["t1_self_recovery"]:
            print(f"\n   🟢 T1 Self-Recovery: {len(r['t1_self_recovery'])} 次")
        
        if r["t3_silent_degradation"]:
            print(f"\n   🟡 T3 Silent Degradation:")
            for d in r["t3_silent_degradation"][:5]:
                print(f"     [{d['signal']}] {d['preview'][:120].replace(chr(10), ' ')}")
        
        if r["t5_llm_confusion"]:
            print(f"\n   🟣 T5 LLM Confusion: {len(r['t5_llm_confusion'])} 次")
            for c in r["t5_llm_confusion"][:8]:
                print(f"     [{c['signal']}] {c['preview'][:120].replace(chr(10), ' ')}")
    
    # ── Root cause analysis ──
    print(f"\n{'='*80}")
    print(f"🔬 根因分析 (系统性问题)")
    print(f"{'='*80}")
    
    # Cluster errors by type
    file_errors = [e for r in all_reports for e in r["tool_errors"] if e["error_type"] == "file_not_found"]
    import_errors = [e for r in all_reports for e in r["tool_errors"] if e["error_type"] == "import_error"]
    key_errors = [e for r in all_reports for e in r["tool_errors"] if e["error_type"] == "key_error"]
    cmd_errors = [e for r in all_reports for e in r["tool_errors"] if e["error_type"] == "command_not_found"]
    json_errors = [e for r in all_reports for e in r["tool_errors"] if e["error_type"] == "json_parse_error"]
    type_errors = [e for r in all_reports for e in r["tool_errors"] if e["error_type"] == "type_error"]
    
    if file_errors:
        print(f"\n  📁 FileNotFoundError ({len(file_errors)} 次):")
        # Extract file paths
        paths = set()
        for e in file_errors:
            preview = e["error_preview"]
            for word in preview.split():
                if "/" in word and len(word) > 5:
                    paths.add(word.strip("'\""))
        for p in sorted(paths)[:10]:
            print(f"     {p[:100]}")
    
    if import_errors:
        print(f"\n  📦 Import/Module Error ({len(import_errors)} 次):")
        modules = set()
        for e in import_errors:
            preview = e["error_preview"]
            if "No module named" in preview:
                idx = preview.find("No module named")
                mod = preview[idx:idx+60]
                modules.add(mod)
        for m in sorted(modules)[:10]:
            print(f"     {m}")
    
    if key_errors:
        print(f"\n  🔑 KeyError ({len(key_errors)} 次):")
        keys = Counter()
        for e in key_errors:
            preview = e["error_preview"]
            if "KeyError" in preview:
                keys[preview[:150]] += 1
        for k, v in keys.most_common(5):
            print(f"     [{v}x] {k[:120]}")
    
    if json_errors:
        print(f"\n  📋 JSON Parse Error ({len(json_errors)} 次)")
    
    # ── Waste estimation ──
    print(f"\n{'='*80}")
    print(f"💸 浪费估算")
    print(f"{'='*80}")
    
    # Rough: each error + recovery = ~2000 tokens wasted
    error_waste = total_errors * 2000
    retry_waste = sum(chain["length"] * 3000 for r in all_reports for chain in r["retry_chains"])
    confusion_waste = total_t5 * 1500
    total_waste = error_waste + retry_waste + confusion_waste
    
    print(f"  Tool 错误浪费:     ~{error_waste:,} tokens")
    print(f"  重试链浪费:        ~{retry_waste:,} tokens")
    print(f"  LLM 困惑浪费:     ~{confusion_waste:,} tokens")
    print(f"  总浪费估算:        ~{total_waste:,} tokens")
    
    # ── Output JSON for further analysis ──
    output_path = Path(__file__).parent.parent.parent / "reports" / "doctor_full_scan_20260627.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    json_output = {
        "scan_date": "2026-06-27",
        "total_sessions": len(sessions),
        "sessions_with_issues": len(issue_sessions),
        "summary": {
            "total_tool_calls": total_tool_calls,
            "total_errors": total_errors,
            "error_rate_pct": total_errors * 100 / (total_tool_calls or 1),
            "t1_self_recovery": total_t1,
            "t3_silent_degradation": total_t3,
            "t4_scope_creep": total_t4,
            "t5_llm_confusion": total_t5,
            "retry_chains": total_chains,
        },
        "error_types": dict(error_type_counter.most_common()),
        "confusion_signals": dict(confusion_signal_counter.most_common()),
        "waste_estimate_tokens": total_waste,
        "session_details": [
            {
                "sid": r["sid"],
                "label": r["label"],
                "events": r["event_count"],
                "tool_calls": len(r["tool_calls"]),
                "errors": len(r["tool_errors"]),
                "error_types": [e["error_type"] for e in r["tool_errors"]],
                "t1": len(r["t1_self_recovery"]),
                "t3": len(r["t3_silent_degradation"]),
                "t5": len(r["t5_llm_confusion"]),
                "chains": len(r["retry_chains"]),
            }
            for r in all_reports
        ]
    }
    
    output_path.write_text(json.dumps(json_output, ensure_ascii=False, indent=2))
    print(f"\n💾 完整 JSON 报告: {output_path}")

if __name__ == "__main__":
    main()
