#!/usr/bin/env python3
"""
DeepFlow Doctor V2 — Full Pipeline Scan (精确版)
正确解析 OpenClaw JSONL 格式，区分真实错误 vs 内容关键词
"""

import json
import sys
import os
import re
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

SESSIONS_DIR = Path.home() / ".openclaw" / "agents" / "researcher" / "sessions"

def load_session(fpath):
    events = []
    for line in fpath.read_text(errors="replace").strip().split("\n"):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except:
            pass
    return events

def extract_text_from_content(content):
    """Extract text from content array"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    texts.append(part.get("text", ""))
                elif "text" in part:
                    texts.append(part["text"])
        return "\n".join(texts)
    return str(content)

def is_real_error(tool_result_msg):
    """Distinguish real errors from content containing error-like keywords"""
    is_error_flag = tool_result_msg.get("isError", False)
    text = extract_text_from_content(tool_result_msg.get("content", ""))
    
    # isError flag is definitive
    if is_error_flag:
        return True, "isError_flag", text[:400]
    
    # Real Python traceback
    if "Traceback (most recent call last)" in text:
        return True, "traceback", text[:400]
    
    # Command failed
    if "(Command exited with code 1)" in text and ("Error" in text or "error" in text or "Traceback" in text):
        return True, "command_error", text[:400]
    
    # Process killed
    if "Process exited with signal SIGKILL" in text or "SIGTERM" in text:
        return True, "process_killed", text[:400]
    
    # File/dir not found (actual ls/find errors, not JSON content)
    if re.search(r"^(ls|find|cat|cd):.*No such file or directory", text, re.MULTILINE):
        return True, "file_not_found", text[:400]
    
    # Module not found
    if "ModuleNotFoundError" in text or "No module named" in text:
        return True, "module_not_found", text[:400]
    
    # pip install failed
    if "externally-managed-environment" in text:
        return True, "env_error", text[:400]
    
    # write_stage failed
    if "write_stage failed" in text or "read_stage failed" in text:
        return True, "stage_io_error", text[:400]
    
    # MISSING files report
    if re.search(r"❌.*MISSING", text):
        return True, "missing_file", text[:400]
    
    # Gate FAIL
    if '"decision": "FAIL"' in text or '"gate_decision": "FAIL"' in text:
        return True, "gate_fail", text[:400]
    
    return False, None, None

def analyze_session(sid, events):
    report = {
        "sid": sid[:12],
        "full_sid": sid,
        "event_count": len(events),
        "tool_calls": [],
        "real_errors": [],
        "gate_failures": [],
        "llm_confusion": [],
        "retry_chains": [],
        "degradation": [],
        "scope_creep": [],
    }
    
    # Build tool call → result mapping
    tool_call_map = {}  # toolCallId → {name, args}
    
    for i, e in enumerate(events):
        if e.get("type") != "message":
            continue
        msg = e.get("message", {})
        role = msg.get("role", "")
        content = msg.get("content", [])
        
        # ── Tool calls ──
        if role == "assistant" and isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "toolCall":
                    tcid = part.get("id", "")
                    tcname = part.get("name", "")
                    tcargs = part.get("arguments", {})
                    tool_call_map[tcid] = {
                        "index": i,
                        "name": tcname,
                        "args_preview": str(tcargs)[:200]
                    }
                    report["tool_calls"].append({
                        "index": i,
                        "id": tcid,
                        "name": tcname,
                    })
        
        # ── Tool results ──
        if role == "toolResult":
            tcid = msg.get("toolCallId", "")
            tcname = msg.get("toolName", "")
            is_err, err_type, err_text = is_real_error(msg)
            
            if is_err:
                call_info = tool_call_map.get(tcid, {})
                report["real_errors"].append({
                    "index": i,
                    "tool": tcname,
                    "tool_id": tcid,
                    "error_type": err_type,
                    "error_preview": err_text[:300],
                    "call_args": call_info.get("args_preview", "?")[:200],
                })
                
                if err_type == "gate_fail":
                    report["gate_failures"].append({
                        "index": i,
                        "preview": err_text[:300]
                    })
        
        # ── LLM confusion (in assistant text) ──
        if role == "assistant" and isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text", "")
                    # Strong confusion signals (not just hedging)
                    strong_signals = [
                        "让我重新", "let me re-", "让我再试", "让我换个",
                        "之前搞错了", "I was wrong", "my mistake",
                        "不对，", "等等，", "wait,",
                        "抱歉，", "sorry,",
                        "让我纠正", "correction",
                        "实际上应该是", "actually it should",
                        "看来不行", "doesn't work",
                        "没有找到", "not found",
                        "这个路径不对", "wrong path",
                        "让我检查一下", "let me check",
                    ]
                    for sig in strong_signals:
                        if sig in text.lower():
                            report["llm_confusion"].append({
                                "index": i,
                                "signal": sig,
                                "preview": text[max(0, text.lower().find(sig)-40):text.lower().find(sig)+100]
                            })
                            break
        
        # ── Degradation ──
        if role == "assistant" and isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text", "")
                    deg_signals = ["fallback", "降级", "mock", "模拟数据",
                                   "跳过此步", "skip this", "暂时使用",
                                   "使用默认值"]
                    for sig in deg_signals:
                        if sig in text.lower():
                            report["degradation"].append({
                                "index": i,
                                "signal": sig,
                                "preview": text[max(0, text.lower().find(sig)-40):text.lower().find(sig)+100]
                            })
                            break
    
    # ── Retry chains ──
    if len(report["real_errors"]) >= 2:
        chain = [report["real_errors"][0]]
        for j in range(1, len(report["real_errors"])):
            gap = report["real_errors"][j]["index"] - chain[-1]["index"]
            if gap <= 10:
                chain.append(report["real_errors"][j])
            else:
                if len(chain) >= 2:
                    report["retry_chains"].append({
                        "length": len(chain),
                        "tools": [c["tool"] for c in chain],
                        "types": [c["error_type"] for c in chain],
                    })
                chain = [report["real_errors"][j]]
        if len(chain) >= 2:
            report["retry_chains"].append({
                "length": len(chain),
                "tools": [c["tool"] for c in chain],
                "types": [c["error_type"] for c in chain],
            })
    
    return report

def main():
    print("=" * 80)
    print("🩺 DeepFlow Doctor V2 — Full Pipeline Scan (精确版)")
    print("   扫描范围: 2026-06-27 researcher agent 全部 sessions")
    print("=" * 80)
    
    # Load all today's sessions
    all_reports = []
    for fpath in sorted(SESSIONS_DIR.glob("*.jsonl")):
        if "trajectory" in fpath.name:
            continue
        mtime = datetime.fromtimestamp(fpath.stat().st_mtime)
        if mtime.date() != datetime(2026, 6, 27).date():
            continue
        events = load_session(fpath)
        if not events:
            continue
        report = analyze_session(fpath.stem, events)
        all_reports.append(report)
    
    print(f"\n📁 扫描 {len(all_reports)} 个 session")
    
    # ── Global stats ──
    total_tools = sum(len(r["tool_calls"]) for r in all_reports)
    total_errors = sum(len(r["real_errors"]) for r in all_reports)
    total_gates = sum(len(r["gate_failures"]) for r in all_reports)
    total_confusion = sum(len(r["llm_confusion"]) for r in all_reports)
    total_chains = sum(len(r["retry_chains"]) for r in all_reports)
    total_degradation = sum(len(r["degradation"]) for r in all_reports)
    
    error_type_counter = Counter()
    tool_error_counter = Counter()
    for r in all_reports:
        for err in r["real_errors"]:
            error_type_counter[err["error_type"]] += 1
            tool_error_counter[err["tool"]] += 1
    
    print(f"\n{'='*80}")
    print(f"📊 全局统计")
    print(f"{'='*80}")
    print(f"  总 Tool 调用:           {total_tools}")
    print(f"  🔴 真实错误:            {total_errors} ({total_errors*100//(total_tools or 1)}% 错误率)")
    print(f"  🔴 门控失败:            {total_gates}")
    print(f"  🟡 重试链:              {total_chains}")
    print(f"  🟣 LLM 困惑:           {total_confusion}")
    print(f"  🟡 静默降级:            {total_degradation}")
    
    print(f"\n📊 错误类型分布:")
    for etype, count in error_type_counter.most_common():
        bar = "█" * min(count, 30)
        print(f"  {etype:25s} {count:3d} {bar}")
    
    print(f"\n📊 出错工具分布:")
    for tool, count in tool_error_counter.most_common():
        bar = "█" * min(count, 30)
        print(f"  {tool:25s} {count:3d} {bar}")
    
    # ── Per-session detail ──
    print(f"\n{'='*80}")
    print(f"🔍 逐 Session 详细分析")
    print(f"{'='*80}")
    
    for r in sorted(all_reports, key=lambda x: -(len(x["real_errors"]) + len(x["llm_confusion"]))):
        if not r["real_errors"] and not r["llm_confusion"]:
            continue
        
        err_count = len(r["real_errors"])
        conf_count = len(r["llm_confusion"])
        icon = "🔴" if err_count > 5 else ("🟡" if err_count > 0 else "🟢")
        
        print(f"\n{'─'*70}")
        print(f"{icon} Session {r['sid']}... | {r['event_count']} events | "
              f"{len(r['tool_calls'])} tools | {err_count} errors | {conf_count} confusion")
        
        if r["real_errors"]:
            print(f"   🔴 错误明细:")
            for err in r["real_errors"]:
                preview = err["error_preview"][:160].replace("\n", " ").strip()
                print(f"     [{err['error_type']:20s}] {err['tool']:12s} → {preview}")
        
        if r["retry_chains"]:
            print(f"   🟡 重试链:")
            for chain in r["retry_chains"]:
                flow = " → ".join(chain["types"])
                tools = " → ".join(chain["tools"])
                print(f"     链长 {chain['length']}: {tools}")
                print(f"       类型: {flow}")
        
        if r["gate_failures"]:
            print(f"   🔴 门控失败: {len(r['gate_failures'])} 次")
        
        if r["llm_confusion"]:
            print(f"   🟣 LLM 困惑 ({conf_count} 次):")
            for c in r["llm_confusion"][:5]:
                preview = c["preview"][:120].replace("\n", " ").strip()
                print(f"     [{c['signal']}] {preview}")
        
        if r["degradation"]:
            print(f"   🟡 降级 ({len(r['degradation'])} 次):")
            for d in r["degradation"][:3]:
                preview = d["preview"][:120].replace("\n", " ").strip()
                print(f"     [{d['signal']}] {preview}")
    
    # ── Root Cause Analysis ──
    print(f"\n{'='*80}")
    print(f"🔬 系统性根因分析")
    print(f"{'='*80}")
    
    # Cluster by root cause
    file_path_errors = [e for r in all_reports for e in r["real_errors"] 
                        if e["error_type"] in ("file_not_found", "stage_io_error", "missing_file")]
    module_errors = [e for r in all_reports for e in r["real_errors"] 
                     if e["error_type"] == "module_not_found"]
    gate_fails = [e for r in all_reports for e in r["real_errors"] 
                  if e["error_type"] == "gate_fail"]
    env_errors = [e for r in all_reports for e in r["real_errors"] 
                  if e["error_type"] in ("env_error", "process_killed")]
    cmd_errors = [e for r in all_reports for e in r["real_errors"] 
                  if e["error_type"] in ("command_error", "traceback") 
                  and e["error_type"] != "gate_fail"]
    
    print(f"\n  ━━━ 问题类别 1: 路径/文件问题 ({len(file_path_errors)} 次) ━━━")
    if file_path_errors:
        path_patterns = Counter()
        for e in file_path_errors:
            preview = e["error_preview"]
            # Extract path patterns
            for match in re.finditer(r'/[^\s"\'<>]+', preview):
                p = match.group()
                if ".deepflow" in p or "blackboard" in p or "stages" in p:
                    path_patterns[p[:100]] += 1
        print(f"  根因: LLM 对 .deepflow 目录结构认知不准确")
        print(f"  表现: 路径拼接错误、目录不存在、文件缺失")
        for p, c in path_patterns.most_common(8):
            print(f"    [{c}x] {p}")
    
    print(f"\n  ━━━ 问题类别 2: 模块导入问题 ({len(module_errors)} 次) ━━━")
    if module_errors:
        for e in module_errors:
            preview = e["error_preview"][:200].replace("\n", " ")
            print(f"    [{e['tool']}] {preview}")
        print(f"  根因: 子 Agent 环境缺少 PYTHONPATH 或依赖未安装")
    
    print(f"\n  ━━━ 问题类别 3: 门控失败 ({len(gate_fails)} 次) ━━━")
    if gate_fails:
        for e in gate_fails[:5]:
            preview = e["error_preview"][:200].replace("\n", " ")
            print(f"    {preview}")
        print(f"  根因: LLM 输出不符合 Pydantic schema → 需要 fix_and_rerun")
        print(f"  评估: 这是设计预期行为，但过多失败说明 prompt/schema 对齐不足")
    
    print(f"\n  ━━━ 问题类别 4: 环境问题 ({len(env_errors)} 次) ━━━")
    if env_errors:
        for e in env_errors:
            preview = e["error_preview"][:200].replace("\n", " ")
            print(f"    [{e['error_type']}] {preview}")
    
    print(f"\n  ━━━ 问题类别 5: 代码执行错误 ({len(cmd_errors)} 次) ━━━")
    if cmd_errors:
        for e in cmd_errors[:5]:
            preview = e["error_preview"][:200].replace("\n", " ")
            print(f"    [{e['tool']}] {preview}")
    
    # ── Waste estimation ──
    print(f"\n{'='*80}")
    print(f"💸 Token 浪费估算")
    print(f"{'='*80}")
    # Each error costs: the failed call (~1500 tokens) + recovery call (~2000 tokens) + confusion text (~500 tokens)
    error_waste = total_errors * 4000
    chain_waste = sum(c["length"] * 3000 for r in all_reports for c in r["retry_chains"])
    confusion_waste = total_confusion * 2000
    gate_waste = total_gates * 8000  # gate failures trigger full re-generation
    total_waste = error_waste + chain_waste + confusion_waste + gate_waste
    
    print(f"  Tool 错误浪费:     ~{error_waste:,} tokens ({total_errors} errors × 4K)")
    print(f"  重试链浪费:        ~{chain_waste:,} tokens")
    print(f"  门控重做浪费:      ~{gate_waste:,} tokens ({total_gates} gates × 8K)")
    print(f"  LLM 困惑浪费:     ~{confusion_waste:,} tokens ({total_confusion} × 2K)")
    print(f"  ─────────────────────────")
    print(f"  总浪费估算:        ~{total_waste:,} tokens")
    
    # ── Recommendations ──
    print(f"\n{'='*80}")
    print(f"💡 系统性改进建议")
    print(f"{'='*80}")
    
    print("""
  1. 【路径认知】LLM 不知道 .deepflow 目录结构
     → 在 prompt 中注入目录树 (tree -L 2 .deepflow/)
     → 或提供 path_helper.py 让 LLM 调用而非硬拼路径

  2. 【模块导入】子 Agent 缺 PYTHONPATH/依赖
     → sessions_spawn 的 prompt 模板强制包含 PYTHONPATH=.
     → 关键依赖 (markdown, pydantic) 预装到 venv

  3. 【门控失败】Pydantic schema 与 LLM 输出不对齐
     → 分析 FAIL 原因，优化 schema 的 Field description
     → 在 prompt 中提供 JSON 示例输出

  4. 【工具探测】LLM 试错式检查工具可用性 (pandoc/wkhtmltopdf/xelatex)
     → 在环境初始化时一次性检测并缓存结果
     → 避免每个 session 重复探测

  5. 【PDF 生成】MD→PDF 路径反复失败
     → 固化为 Chrome headless 方案 (已验证可用)
     → 写入 SKILL.md 作为标准路径
""")
    
    # ── Save JSON ──
    output_path = Path(__file__).parent.parent.parent / "reports" / "doctor_full_scan_20260627.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    json_output = {
        "scan_date": "2026-06-27",
        "total_sessions": len(all_reports),
        "sessions_with_errors": len([r for r in all_reports if r["real_errors"]]),
        "sessions_with_confusion": len([r for r in all_reports if r["llm_confusion"]]),
        "summary": {
            "total_tool_calls": total_tools,
            "real_errors": total_errors,
            "error_rate_pct": round(total_errors * 100 / (total_tools or 1), 1),
            "gate_failures": total_gates,
            "retry_chains": total_chains,
            "llm_confusion": total_confusion,
            "degradation": total_degradation,
        },
        "error_types": dict(error_type_counter.most_common()),
        "tool_errors": dict(tool_error_counter.most_common()),
        "waste_estimate_tokens": total_waste,
        "session_details": [
            {
                "sid": r["sid"],
                "events": r["event_count"],
                "tool_calls": len(r["tool_calls"]),
                "errors": len(r["real_errors"]),
                "error_types": [e["error_type"] for e in r["real_errors"]],
                "gate_failures": len(r["gate_failures"]),
                "llm_confusion": len(r["llm_confusion"]),
                "chains": len(r["retry_chains"]),
            }
            for r in all_reports
        ]
    }
    
    output_path.write_text(json.dumps(json_output, ensure_ascii=False, indent=2))
    print(f"\n💾 JSON 报告: {output_path}")

if __name__ == "__main__":
    main()
