#!/usr/bin/env python3
"""从 session 日志中全量恢复 blackboard/ 目录下的所有文件"""

import json
import os
import sys
import re
from pathlib import Path
from collections import defaultdict

SESSIONS_DIR = Path.home() / ".openclaw/agents"
WORKSPACE = Path.home() / ".openclaw/workspace/.deepflow"
BLACKBOARD = WORKSPACE / "blackboard"

def find_all_sessions():
    sessions = []
    for agent_dir in SESSIONS_DIR.iterdir():
        if not agent_dir.is_dir():
            continue
        sessions_dir = agent_dir / "sessions"
        if not sessions_dir.is_dir():
            continue
        for f in sorted(sessions_dir.glob("*.jsonl")):
            if "trajectory" not in f.name:
                sessions.append(f)
    # Sort by modification time (older first, so newer overwrites)
    sessions.sort(key=lambda p: p.stat().st_mtime)
    return sessions

def extract_blackboard_writes(session_file):
    """从 session JSONL 中提取所有 blackboard/ 下的 write 操作"""
    writes = {}
    try:
        with open(session_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                msg = obj.get('message', {})
                if not isinstance(msg, dict):
                    continue
                
                content = msg.get('content', '')
                if not isinstance(content, list):
                    continue
                
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    # OpenClaw format: toolCall + arguments
                    if block.get('type') == 'toolCall' and block.get('name') == 'write':
                        args = block.get('arguments', {})
                        path = args.get('path', '')
                        content_text = args.get('content', '')
                        
                        if 'blackboard/' not in path or not content_text:
                            continue
                        
                        # Normalize path to relative
                        match = re.search(r'blackboard/(.+)', path)
                        if not match:
                            continue
                        rel_path = "blackboard/" + match.group(1)
                        
                        # Skip metadata/temp files
                        skip = ['.cron_job_id', '.cron_run_count', '.notified_stages',
                                '.pipeline_watcher', '.watcher_', '.DS_Store',
                                '.delivery_config', '.completed', '.stage_progress',
                                '.prompts/']
                        if any(p in rel_path for p in skip):
                            continue
                        
                        # Skip very small files
                        if len(content_text) < 20:
                            continue
                        
                        writes[rel_path] = content_text
    
    except Exception as e:
        print(f"  Error reading {session_file.name}: {e}", file=sys.stderr)
    
    return writes

def main():
    print
    
    sessions = find_all_sessions()
    print(f"找到 {len(sessions)} 个 session 文件\n")
    
    all_writes = {}  # path -> content (later sessions overwrite)
    
    for i, session_file in enumerate(sessions):
        if i % 50 == 0:
            print(f"  扫描 {i+1}/{len(sessions)}...")
        writes = extract_blackboard_writes(session_file)
        if writes:
            print(f"  ✅ {session_file.name}: {len(writes)} 个 blackboard 文件")
            all_writes.update(writes)
    
    print(f"\n总计: {len(all_writes)} 个唯一文件路径")
    
    # Group by case
    cases = defaultdict(list)
    for path in sorted(all_writes.keys()):
        parts = path.split("/")
        if len(parts) >= 2:
            case_name = parts[1]
            cases[case_name].append(path)
    
    print(f"涉及 {len(cases)} 个案例目录:\n")
    for case_name, files in sorted(cases.items()):
        total_size = sum(len(all_writes[f]) for f in files)
        print(f"  📁 {case_name}: {len(files)} 个文件 ({total_size:,} bytes)")
    
    # Write all files
    print(f"\n开始写入...")
    restored = 0
    errors = 0
    
    for rel_path, content in all_writes.items():
        full_path = WORKSPACE / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            restored += 1
        except Exception as e:
            print(f"  ❌ 写入失败 {rel_path}: {e}")
            errors += 1
    
    print(f"\n=== 恢复完成 ===")
    print(f"  ✅ 成功: {restored} 个文件")
    print(f"  ❌ 失败: {errors} 个文件")
    
    # Detailed manifest
    print(f"\n=== 文件清单 ===")
    for case_name in sorted(cases.keys()):
        print(f"\n📁 {case_name}/")
        for path in sorted(cases[case_name]):
            full_path = WORKSPACE / path
            size = full_path.stat().st_size if full_path.exists() else 0
            display = path.replace("blackboard/", "")
            print(f"  {display} ({size:,} bytes)")

if __name__ == "__main__":
    main()
