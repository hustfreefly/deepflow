#!/usr/bin/env python3
"""
Pipeline Watcher V3 - AI Native Architecture

Core Principle: Use LLM for semantic understanding, not deterministic code.

Input: blackboard/{session_id}/stages/*.json
Processing: LLM reads all stage JSON → understands state → judges completion → generates notification
Output: Feishu message (natural language, no templates)

Why this works:
- No template maintenance (wrapper_prompt.md + templates/*.md)
- No timezone handling (LLM understands timestamps)
- No state machine (LLM judges completion)
- No string parsing (LLM reads JSON directly)
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List

# Blackboard path (injected by Cron Watcher)
BLACKBOARD_ROOT = os.environ.get('BLACKBOARD_ROOT', str(Path.home() / '.openclaw' / 'workspace' / '.deepflow' / 'blackboard'))

def read_all_stages(session_id: str) -> Dict[str, Any]:
    """Read all stage JSON files from blackboard."""
    stages_dir = Path(BLACKBOARD_ROOT) / session_id / 'stages'
    
    if not stages_dir.exists():
        return {'error': f'Stages directory not found: {stages_dir}'}
    
    stages = {}
    for json_file in sorted(stages_dir.glob('*.json')):
        if json_file.name.startswith('.'):
            continue
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                stages[json_file.stem] = json.load(f)
        except Exception as e:
            stages[json_file.stem] = {'error': str(e)}
    
    return stages

def generate_watcher_prompt(session_id: str, stages: Dict[str, Any]) -> str:
    """Generate LLM prompt for AI Native Watcher."""
    return f"""
You are Pipeline Watcher V3 (AI Native).

## Your Task
Analyze the current state of Solution Pro pipeline and generate a user-friendly Feishu notification.

## Session ID
{session_id}

## Current Stages
{json.dumps(stages, indent=2, ensure_ascii=False)}

## Your Analysis Process

### Step 1: Understand State
- Read each stage JSON
- Identify which stages are completed, in-progress, pending, or failed
- Extract key metrics (scores, coverage, errors)

### Step 2: Judge Completion
- Count completed stages vs total stages
- Identify any blocking issues (failed stages, missing dependencies)
- Determine overall progress percentage

### Step 3: Generate Notification
- Write natural language summary (no templates, no formatting rules)
- Include: progress bar, completed stages, current stage, next stage, any issues
- Use emojis appropriately (✅ ⏳ ❌ 🔍 🔧 ⚙️ 🏆 📝)
- Estimate remaining time based on completed stages

### Step 4: Detect Completion
- If all stages are completed (status='completed' or has final_result.json), mark as COMPLETE
- If any stage failed (status='failed' or has critical errors), mark as FAILED
- Otherwise mark as IN_PROGRESS

## Output Format
Return a JSON object with:
```json
{{
  "status": "IN_PROGRESS|COMPLETE|FAILED",
  "progress_percentage": <int>,
  "notification_text": "<natural language Feishu message>",
  "should_notify": <bool>,
  "reasoning": "<why you made this decision>"
}}
```

## Rules
1. **No template usage** - generate natural language directly
2. **No timezone handling** - timestamps in JSON are already in ISO format, just read them
3. **No state machine** - use your judgment based on stage content
4. **No string parsing** - read JSON directly, don't use regex or string matching
5. **Be concise** - notification should be 1-3 lines max
6. **Be honest** - if something is unclear, say so in reasoning

Now analyze the stages and generate your response.
"""

def call_llm_for_analysis(prompt: str) -> Dict[str, Any]:
    """
    Call LLM to analyze pipeline state.
    
    In production, this would use sessions_spawn or direct LLM API call.
    For now, this is a placeholder that shows the architecture.
    """
    # TODO: Replace with actual LLM call
    # Option 1: sessions_spawn(runtime="subagent", task=prompt)
    # Option 2: Direct API call to Qwen/GPT
    # Option 3: Use existing OpenClaw LLM tools
    
    # For demonstration, return a mock response
    return {
        "status": "IN_PROGRESS",
        "progress_percentage": 40,
        "notification_text": "🟠 [DeepFlow] Solution Pro ████████░░░░░░░░░░░░ 4/10 阶段\n📊⏳ 📋○ 👥○ 🔍○ 🧩✅ 🔎✅ 🔧✅ ⚙️✅ 🏆○ 📝○\n预计剩余: 39m",
        "should_notify": True,
        "reasoning": "Mock response - architecture demonstration only"
    }

def send_feishu_notification(text: str) -> None:
    """Send notification to Feishu."""
    # TODO: Implement Feishu API call
    # For now, just print to stdout
    print(f"Feishu Notification:\n{text}")

def main():
    """Main entry point for AI Native Watcher."""
    if len(sys.argv) < 2:
        print("Usage: pipeline_watcher_v3.py <session_id>")
        sys.exit(1)
    
    session_id = sys.argv[1]
    
    # Step 1: Read all stages
    stages = read_all_stages(session_id)
    
    # Step 2: Generate LLM prompt
    prompt = generate_watcher_prompt(session_id, stages)
    
    # Step 3: Call LLM for analysis
    analysis = call_llm_for_analysis(prompt)
    
    # Step 4: Send notification if needed
    if analysis.get('should_notify', False):
        send_feishu_notification(analysis['notification_text'])
    
    # Step 5: Output analysis for debugging
    print(json.dumps(analysis, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
