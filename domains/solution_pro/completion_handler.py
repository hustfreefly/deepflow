"""
完成处理器，使用 STAGE_PATH_REGISTRY 检查任务完成状态

Version: 2.1.0
Author: DeepFlow Solution Pro
Date: 2026-06-01
"""

"""
Orchestrator 完成后处理工具

当 orchestrator 子 Agent 完成任务后，主 Agent 调用此函数：
1. 检查所有阶段的完成状态
2. 更新 tasks 数据库
3. 生成完成报告
4. 发送通知给用户
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

# 深度流根目录（使用 PathConfig 解析）
from core.config.path_config import PathConfig
from domains.solution_pro.blackboard import BlackboardManager, STAGE_PATH_REGISTRY
from domains.solution_pro.task_builder import validate_stage_output, HARNESS_EXEMPT_STAGES

DEEPFLOW_ROOT = PathConfig.resolve().base_dir
DB_PATH = DEEPFLOW_ROOT / 'frontend' / 'backend' / 'data' / 'tasks.db'

DEFAULT_SOLUTION_EXPECTED_OUTPUTS = {
    'data_collection': [STAGE_PATH_REGISTRY['data_collection']],
    'planning': [STAGE_PATH_REGISTRY['planning']],
    'reviewers': [
        STAGE_PATH_REGISTRY['reviewer_technical'],
        STAGE_PATH_REGISTRY['reviewer_business'],
        STAGE_PATH_REGISTRY['reviewer_risk'],
    ],
    'research': [
        STAGE_PATH_REGISTRY['research_expert_1'],
        STAGE_PATH_REGISTRY['research_expert_2'],
        STAGE_PATH_REGISTRY['research_expert_3'],
    ],
    'consolidator': [STAGE_PATH_REGISTRY['consolidator']],
    'audit': [STAGE_PATH_REGISTRY['audit']],
    'fix': [STAGE_PATH_REGISTRY['fix']],
    'fixer_expert': [STAGE_PATH_REGISTRY['fixer_expert']],
    'harness_final': [STAGE_PATH_REGISTRY['harness_final']],
    'summarizer': [STAGE_PATH_REGISTRY['summarizer']],
}

REQUIRED_SOLUTION_FINAL_ARTIFACTS = [
    STAGE_PATH_REGISTRY['requirements_traceability_matrix'],
    'final_result.json',
    'final_solution.md',
]

def ensure_tasks_db() -> bool:
    """Create tasks.db and the tasks table when the frontend DB is absent."""
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT UNIQUE NOT NULL,
                    domain TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    parameters TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    webhook_sent INTEGER DEFAULT 0,
                    webhook_retries INTEGER DEFAULT 0,
                    error_message TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_webhook ON tasks(webhook_sent, webhook_retries)")
            conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"❌ 初始化 tasks.db 失败: {e}")
        return False


def check_orchestrator_completion(
    session_id: str,
    domain: str = 'solution'
) -> Dict:
    """
    检查 orchestrator 的完成状态
    
    Args:
        session_id: 会话 ID
        domain: 领域类型 (solution/investment/code)
    
    Returns:
        {
            'status': 'completed' | 'partial' | 'failed',
            'completed_stages': [...],
            'missing_stages': [...],
            'completion_rate': 0.0-1.0,
            'final_output': path or None,
            'updated_at': timestamp
        }
    """
    base_path = DEEPFLOW_ROOT / 'blackboard' / session_id

    # Solution Pro V4.2: execution_plan.json is the completion contract.
    # Prefer expected_output_path from the actual plan so dynamic Planner
    # workers are validated correctly.
    if domain == 'solution':
        plan_path = base_path / 'execution_plan.json'
        try:
            with plan_path.open('r', encoding='utf-8') as f:
                plan = json.load(f)
            expected = _expected_outputs_from_plan(plan)
            if expected:
                return _check_expected_outputs(
                    base_path,
                    expected,
                    required_artifacts=REQUIRED_SOLUTION_FINAL_ARTIFACTS,
                )
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

    # 根据 domain 定义预期阶段
    stage_definitions = {}
    
    if domain == 'solution':
        # Fallback uses the actual 10-stage Solution Pro pipeline, not every
        # registry entry. Some registry paths are optional artifacts.
        stage_definitions = DEFAULT_SOLUTION_EXPECTED_OUTPUTS
    elif domain == 'investment':
        stage_definitions = {
            'data_collection': ['data/collection.json'],
            'planning': ['stages/planning.json'],
            'research': ['stages/research.json'],
            'analysis': ['stages/analysis.json'],
            'summarizer': ['final_report.md'],
        }
    elif domain == 'code':
        stage_definitions = {
            'analysis': ['stages/analysis.json'],
            'review': ['stages/review.json'],
            'fix': ['stages/fix.json'],
            'summarizer': ['final_report.md'],
        }
    
    if not stage_definitions:
        return {
            'status': 'failed',
            'error': f'Unknown domain: {domain}',
            'completed_stages': [],
            'missing_stages': [],
            'completion_rate': 0.0,
            'final_output': None,
            'updated_at': datetime.now().isoformat()
        }

    if domain == 'solution':
        return _check_expected_outputs(
            base_path,
            stage_definitions,
            required_artifacts=REQUIRED_SOLUTION_FINAL_ARTIFACTS,
        )
    
    expected_stages = stage_definitions
    completed_stages = []
    missing_stages = []
    
    # 检查每个阶段
    for stage_name, possible_paths in expected_stages.items():
        found = False
        for rel_path in possible_paths:
            full_path = base_path / rel_path
            if full_path.exists():
                completed_stages.append(stage_name)
                found = True
                break
        if not found:
            missing_stages.append(stage_name)
    
    # 计算完成率
    total_stages = len(expected_stages)
    completion_rate = len(completed_stages) / total_stages if total_stages > 0 else 0.0
    
    # 确定状态
    if completion_rate == 1.0:
        status = 'completed'
    elif completion_rate > 0:
        status = 'partial'
    else:
        status = 'failed'
    
    # 检查最终输出
    final_output = None
    for stage_name, paths in expected_stages.items():
        if 'summarizer' in stage_name or 'final' in stage_name.lower():
            for rel_path in paths:
                full_path = base_path / rel_path
                if full_path.exists():
                    final_output = str(full_path)
                    break
    
    return {
        'status': status,
        'completed_stages': completed_stages,
        'missing_stages': missing_stages,
        'completion_rate': completion_rate,
        'final_output': final_output,
        'updated_at': datetime.now().isoformat()
    }


def _expected_outputs_from_plan(plan: Dict) -> Dict[str, list]:
    expected = {}
    for phase in plan.get('phases', []):
        stage = phase.get('stage', f"phase_{phase.get('phase', '?')}")
        if phase.get('parallel'):
            paths = []
            for worker in phase.get('workers', []):
                if isinstance(worker, dict):
                    rel_path = worker.get('expected_output_path')
                else:
                    rel_path = None
                if rel_path:
                    paths.append(rel_path)
            if paths:
                expected[stage] = paths
        else:
            rel_path = phase.get('expected_output_path')
            if rel_path:
                expected[stage] = [rel_path]
    return expected


def _check_expected_outputs(
    base_path: Path,
    expected_stages: Dict[str, list],
    required_artifacts: Optional[list] = None,
) -> Dict:
    completed_stages = []
    missing_stages = []
    missing_outputs = {}
    missing_artifacts = []

    schema_errors = {}
    
    for stage_name, paths in expected_stages.items():
        missing = []
        for rel_path in paths:
            if not (base_path / rel_path).exists():
                missing.append(rel_path)
        if missing:
            missing_stages.append(stage_name)
            missing_outputs[stage_name] = missing
        else:
            completed_stages.append(stage_name)
            
            # 🆕 改动 D: 接入 Schema 验证器
            for rel_path in paths:
                if rel_path.endswith('.json'):
                    try:
                        with open(base_path / rel_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        valid, err_msg = validate_stage_output(data, stage_name)
                        if not valid:
                            schema_errors[stage_name] = err_msg
                    except json.JSONDecodeError as e:
                        schema_errors[stage_name] = f"JSON parse error: {str(e)}"
                    except Exception as e:
                        schema_errors[stage_name] = f"Validation error: {str(e)}" 

    total_stages = len(expected_stages)
    completion_rate = len(completed_stages) / total_stages if total_stages > 0 else 0.0

    if completion_rate == 1.0:
        status = 'completed'
    elif completion_rate > 0:
        status = 'partial'
    else:
        status = 'failed'

    for rel_path in required_artifacts or []:
        if not (base_path / rel_path).exists():
            missing_artifacts.append(rel_path)

    final_output = None
    for rel_path in ['final_solution.md', 'final_result.json', 'final_report.md', 'stages/final_solution.md']:
        full_path = base_path / rel_path
        if full_path.exists():
            final_output = str(full_path)
            break

    # 🆕 改动 D: 如果有 schema 错误，降级为 partial 并记录
    if (schema_errors or missing_artifacts) and status == 'completed':
        status = 'partial'
        
    return {
        'status': status,
        'completed_stages': completed_stages,
        'missing_stages': missing_stages,
        'missing_outputs': missing_outputs,
        'missing_artifacts': missing_artifacts,
        'schema_errors': schema_errors,
        'completion_rate': completion_rate,
        'final_output': final_output,
        'updated_at': datetime.now().isoformat()
    }


def update_task_status(
    session_id: str,
    status: str,
    error_message: Optional[str] = None
) -> bool:
    """
    更新 tasks 数据库中的任务状态
    
    Args:
        session_id: 会话 ID
        status: 新状态 (completed/partial/failed)
        error_message: 错误信息（可选）
    
    Returns:
        是否成功更新
    """
    try:
        if not ensure_tasks_db():
            return False
        
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        # 检查 tasks 表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='tasks'
        """)
        if not cursor.fetchone():
            print(f"⚠️ tasks 表不存在于 {DB_PATH}，跳过状态更新")
            conn.close()
            return False
        
        now = datetime.now().timestamp()
        
        cursor.execute('''
            UPDATE tasks 
            SET status = ?, updated_at = ?, error_message = ?
            WHERE session_id = ?
        ''', (status, now, error_message, session_id))
        
        affected = cursor.rowcount
        if affected == 0:
            cursor.execute('''
                INSERT INTO tasks (
                    id, session_id, domain, status, parameters,
                    created_at, updated_at, webhook_sent, webhook_retries, error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
            ''', (
                session_id,
                session_id,
                'solution',
                status,
                '{}',
                now,
                now,
                error_message,
            ))
            affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return affected > 0
        
    except sqlite3.Error as e:
        print(f"❌ 更新数据库失败: {e}")
        return False


def write_completion_marker(
    session_id: str,
    status: str,
    completion_rate: float
) -> Path:
    """
    写入完成标记文件，供 HEARTBEAT 检查
    
    Args:
        session_id: 会话 ID
        status: 完成状态
        completion_rate: 完成率
    
    Returns:
        标记文件路径
    """
    base_path = DEEPFLOW_ROOT / 'blackboard' / session_id
    marker_path = base_path / '.completed'
    
    marker_data = {
        'session_id': session_id,
        'status': status,
        'completion_rate': completion_rate,
        'completed_at': datetime.now().isoformat()
    }
    
    with open(marker_path, 'w', encoding='utf-8') as f:
        json.dump(marker_data, f, ensure_ascii=False, indent=2)
    
    return marker_path


def generate_completion_report(result: Dict) -> str:
    """
    生成用户友好的完成报告
    
    Args:
        result: check_orchestrator_completion 的返回值
    
    Returns:
        格式化的报告文本
    """
    session_id = result.get('session_id', 'unknown')
    status = result['status']
    completed = result['completed_stages']
    missing = result['missing_stages']
    rate = result['completion_rate']
    final_output = result.get('final_output')
    
    report = []
    report.append("=" * 80)
    report.append("📊 Solution Pro 任务完成报告")
    report.append("=" * 80)
    report.append(f"Session ID: {session_id}")
    report.append(f"状态: {status.upper()}")
    report.append(f"完成率: {rate*100:.1f}% ({len(completed)}/{len(completed)+len(missing)} 阶段)")
    report.append("")
    
    if status == 'completed':
        report.append("✅ 所有阶段已完成")
    elif status == 'partial':
        report.append("⚠️ 部分阶段完成")
        report.append(f"缺失阶段: {', '.join(missing)}")
    else:
        report.append("❌ 任务失败")
    
    report.append("")
    
    if final_output:
        report.append(f"📄 最终输出: {final_output}")
    
    report.append(f"🕐 更新时间: {result['updated_at']}")
    report.append("=" * 80)
    
    return "\n".join(report)


def handle_orchestrator_completion(
    session_id: str,
    domain: str = 'solution',
    notify_user: bool = True
) -> Dict:
    """
    完整的 orchestrator 完成后处理流程
    
    这是主 Agent 在收到 completion event 后应该调用的函数。
    
    Args:
        session_id: 会话 ID
        domain: 领域类型
        notify_user: 是否发送用户通知
    
    Returns:
        处理结果
    """
    print(f"🔍 检查 orchestrator 完成状态: {session_id}")
    
    # 1. 检查完成状态
    result = check_orchestrator_completion(session_id, domain)
    result['session_id'] = session_id
    
    # 2. 更新数据库
    error_msg = None
    if result['missing_stages']:
        error_msg = f"Missing stages: {', '.join(result['missing_stages'])}"
    
    updated = update_task_status(session_id, result['status'], error_msg)
    result['database_updated'] = updated
    
    # 3. 写入完成标记
    marker_path = write_completion_marker(
        session_id,
        result['status'],
        result['completion_rate']
    )
    result['marker_path'] = str(marker_path)
    
    # 4. 生成报告
    report = generate_completion_report(result)
    result['report'] = report
    
    # 5. 输出报告
    print(report)
    
    return result


if __name__ == '__main__':
    # 测试：检查当前任务
    import sys
    
    if len(sys.argv) > 1:
        test_session = sys.argv[1]
    else:
        test_session = '设计一个面向中小企业的智能客服系统_支持_architecture_1f2f4cec'
    
    result = handle_orchestrator_completion(test_session, 'solution')
    print("\n✅ 处理完成")
