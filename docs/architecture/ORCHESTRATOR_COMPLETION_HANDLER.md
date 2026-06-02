# Orchestrator 完成后处理流程

## 场景
主 Agent 通过 sessions_yield() 等待 orchestrator 子 Agent 完成，收到 completion event 后需要执行的标准流程。

## 必须执行的步骤

### 1. 检查阶段完成状态
```python
import os, json
from pathlib import Path

def check_stages(base_path: str, session_id: str) -> dict:
    """检查所有阶段的完成状态"""
    stages_dir = Path(base_path) / "stages"
    data_dir = Path(base_path) / "data"
    
    # 预期阶段文件映射（考虑不同的输出路径）
    expected = {
        'data_collection': ['stages/data_collection.json', 'data/collection.json'],
        'planning': ['stages/planning.json'],
        'reviewer_technical': ['stages/reviewer_technical.json'],
        'reviewer_business': ['stages/reviewer_business.json'],
        'reviewer_risk': ['stages/reviewer_risk.json'],
        'research_expert_1': ['stages/research_expert_1.json'],
        'research_expert_2': ['stages/research_expert_2.json'],
        'research_expert_3': ['stages/research_expert_3.json'],
        'consolidator': ['stages/consolidator.json'],
        'audit_completeness': ['stages/audit_completeness.json', 'stages/audit.json'],
        'audit_architecture': ['stages/audit_architecture.json'],
        'audit_risk': ['stages/audit_risk.json'],
        'fix': ['stages/fix.json'],
        'fixer_expert': ['stages/fixer_expert.json'],
        'harness_final': ['stages/harness_final.json'],
        'summarizer': ['final_solution.md'],  # 在 base_path 根目录
    }
    
    results = {}
    for stage, possible_paths in expected.items():
        found = False
        for rel_path in possible_paths:
            full_path = Path(base_path) / rel_path
            if full_path.exists():
                size = full_path.stat().st_size
                results[stage] = {
                    'status': 'completed',
                    'path': str(full_path),
                    'size_kb': round(size / 1024, 1)
                }
                found = True
                break
        if not found:
            results[stage] = {'status': 'missing', 'path': None, 'size_kb': 0}
    
    return results
```

### 2. 更新 tasks 数据库
```python
import sqlite3
from pathlib import Path

def update_task_status(session_id: str, status: str, error_message: str = None):
    """更新 tasks 数据库中的任务状态"""
    db_path = Path('~/.openclaw/workspace/.deepflow/frontend/backend/data/tasks.db').expanduser()
    
    conn = sqlite3.connect(str(db_path))
    try:
        # 检查任务是否存在
        cursor = conn.execute('SELECT id FROM tasks WHERE id = ?', (session_id,))
        exists = cursor.fetchone() is not None
        
        if exists:
            # 更新状态
            import time
            now = time.time()
            conn.execute(
                'UPDATE tasks SET status = ?, updated_at = ?, error_message = ? WHERE id = ?',
                (status, now, error_message, session_id)
            )
        else:
            # 创建新任务记录（用于测试场景）
            import time, json
            now = time.time()
            conn.execute(
                'INSERT INTO tasks (id, session_id, domain, status, parameters, created_at, updated_at, webhook_sent, webhook_retries, error_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (session_id, session_id, 'solution', status, '{}', now, now, 0, 0, error_message)
            )
        
        conn.commit()
    finally:
        conn.close()
```

### 3. 生成完成报告
```python
def generate_completion_report(session_id: str, stage_results: dict) -> str:
    """生成用户友好的完成报告"""
    completed = sum(1 for r in stage_results.values() if r['status'] == 'completed')
    total = len(stage_results)
    
    report = f"## Solution Pro 任务完成报告\n\n"
    report += f"**Session ID**: {session_id}\n\n"
    report += f"**状态**: {completed}/{total} 阶段完成\n\n"
    
    if completed == total:
        report += "✅ **所有阶段已完成**\n\n"
    else:
        report += "⚠️ **部分阶段未完成**\n\n"
        missing = [k for k, v in stage_results.items() if v['status'] == 'missing']
        report += f"缺失阶段: {', '.join(missing)}\n\n"
    
    # 最终输出
    if 'summarizer' in stage_results and stage_results['summarizer']['status'] == 'completed':
        report += f"📄 **最终方案**: {stage_results['summarizer']['path']} ({stage_results['summarizer']['size_kb']}KB)\n\n"
    
    return report
```

### 4. 发送报告给用户
```python
def notify_user(report: str):
    """通过飞书发送报告给用户"""
    # 使用飞书 API 发送消息
    # 具体实现参考 core/notification/feishu.py
    pass
```

## 完整处理流程

```python
def handle_orchestrator_completion(session_id: str, base_path: str):
    """orchestrator 完成后的完整处理流程"""
    
    # 1. 检查阶段状态
    stage_results = check_stages(base_path, session_id)
    
    # 2. 判断整体状态
    completed = sum(1 for r in stage_results.values() if r['status'] == 'completed')
    total = len(stage_results)
    
    if completed == total:
        status = 'completed'
        error_message = None
    elif completed > 0:
        status = 'partial'
        missing = [k for k, v in stage_results.items() if v['status'] == 'missing']
        error_message = f"Missing stages: {', '.join(missing)}"
    else:
        status = 'failed'
        error_message = 'No stages completed'
    
    # 3. 更新数据库
    update_task_status(session_id, status, error_message)
    
    # 4. 生成报告
    report = generate_completion_report(session_id, stage_results)
    
    # 5. 发送通知
    notify_user(report)
    
    return {
        'status': status,
        'stage_results': stage_results,
        'report': report
    }
```

## 主 Agent 的行为规范

**当收到 orchestrator completion event 时，主 Agent 必须：**

1. ✅ 立即执行 `handle_orchestrator_completion()`
2. ✅ 向用户发送完成报告（包含状态、文件路径、下一步建议）
3. ✅ 如果状态不是 completed，主动分析原因并提供修复建议
4. ❌ 不要只是简单回复"任务完成"
5. ❌ 不要忽略 completion event

## 下一步建议

根据任务状态，提供不同的后续操作建议：

- **completed**: "可以查看 final_solution.md，或启动下一阶段任务"
- **partial**: "建议检查缺失阶段，或重新运行任务"
- **failed**: "建议检查 orchestrator 日志，分析失败原因"
