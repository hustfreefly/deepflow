"""
完成处理器，使用 BlackboardManager V6 API 检查任务完成状态

Version: 2.2.0
Author: DeepFlow Solution Pro
Date: 2026-06-23

变更:
- 移除所有路径泄漏，全面迁移到 BlackboardManager V6 API
- 不再使用 STAGE_PATH_REGISTRY 作为文件路径
- 使用 write_stage/read_stage/stage_exists/list_stages
"""

"""
Orchestrator 完成后处理工具

当 orchestrator 子 Agent 完成任务后，主 Agent 调用此函数：
1. 检查所有阶段的完成状态
2. 更新 tasks 数据库
3. 生成完成报告
4. 发送通知给用户
"""

import sys as _sys; _p=__import__('pathlib').Path(__file__).resolve(); _r=next((d for d in _p.parents if (d/'core'/'blackboard').is_dir()),None); _sys.path.insert(0,str(_r)) if _r and str(_r) not in _sys.path else None  # 契约笼子: 自动发现 .deepflow 根目录
import json
import sqlite3
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from core.config.path_config import PathConfig
from domains.solution_pro.blackboard import BlackboardManager
from domains.solution_pro.task_builder import validate_stage_output, HARNESS_EXEMPT_STAGES

DEEPFLOW_ROOT = PathConfig.resolve().base_dir
DB_PATH = DEEPFLOW_ROOT / 'frontend' / 'backend' / 'data' / 'tasks.db'

# V6: 使用 stage 名称而非文件路径
# data_collection 输出在 data/ 子目录，保留完整路径
DEFAULT_SOLUTION_EXPECTED_OUTPUTS = {
    'data_collection': ['data/collection.json'],
    'planning': ['planning'],
    'reviewers': ['reviewer_technical', 'reviewer_business', 'reviewer_risk'],
    'research': ['research_expert_1', 'research_expert_2', 'research_expert_3'],
    'consolidator': ['consolidator'],
    'audit': ['audit'],
    'fix': ['fix'],
    'fixer_expert': ['fixer_expert'],
    'harness_final': ['harness_final'],
    'summarizer': ['summarizer'],
}

REQUIRED_SOLUTION_FINAL_ARTIFACTS = [
    'requirements_traceability_matrix.json',
    'final_result.json',
    'final_solution.md',
]


# ── V6 辅助函数：标识符解析 ──

def _plan_path_to_identifier(path: str) -> str:
    """
    将 plan 中的文件路径转换为 BlackboardManager 可用标识符。

    stage 文件路径      → stage 名称 (如 planning)
    其他路径            → 保持原样    (非 stage 文件)
    """
    p = Path(path)
    if len(p.parts) > 1 and p.parts[0] == 'stages' and p.suffix == '.json':
        return p.stem
    return path


def _identifier_exists(bb: BlackboardManager, identifier: str) -> bool:
    """
    检查 stage 或文件是否存在。

    优先使用 stage_exists（检查 stage 文件），
    回退到 session_dir 下的文件路径检查。
    """
    if bb.stage_exists(identifier):
        return True
    if (bb.get_session_dir() / identifier).exists():
        return True
    return False


def _read_identifier_json(bb: BlackboardManager, identifier: str) -> Optional[Dict]:
    """
    从 stage 或文件读取 JSON 数据。

    优先使用 read_stage（读取 stage 文件），
    回退到 session_dir 下的文件读取。
    """
    data = bb.read_stage(identifier)
    if data is not None:
        return data
    file_path = bb.get_session_dir() / identifier
    if file_path.exists():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _resolve_identifier_path(bb: BlackboardManager, identifier: str) -> Optional[Path]:
    """将标识符解析为实际文件路径。"""
    if bb.stage_exists(identifier):
        return bb._stage_path(identifier)
    path = bb.get_session_dir() / identifier
    if path.exists():
        return path
    return None


# ── 核心逻辑 ──

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
    bb = BlackboardManager(session_id=session_id)

    # Solution Pro V4.2: execution_plan.json is the completion contract.
    # Prefer expected_output_path from the actual plan so dynamic Planner
    # workers are validated correctly.
    if domain == 'solution':
        plan = bb.read_json("execution_plan.json")
        if plan is not None:
            expected = _expected_outputs_from_plan(plan)
            if expected:
                return _check_expected_outputs(
                    bb,
                    expected,
                    required_artifacts=REQUIRED_SOLUTION_FINAL_ARTIFACTS,
                )

    # 根据 domain 定义预期阶段
    stage_definitions = {}

    if domain == 'solution':
        # Fallback uses the actual 10-stage Solution Pro pipeline, not every
        # registry entry. Some registry paths are optional artifacts.
        stage_definitions = DEFAULT_SOLUTION_EXPECTED_OUTPUTS
    elif domain == 'investment':
        stage_definitions = {
            'data_collection': ['data/collection.json'],
            'planning': ['planning'],
            'research': ['research'],
            'analysis': ['analysis'],
            'summarizer': ['final_report.md'],
        }
    elif domain == 'code':
        stage_definitions = {
            'analysis': ['analysis'],
            'review': ['review'],
            'fix': ['fix'],
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
            bb,
            stage_definitions,
            required_artifacts=REQUIRED_SOLUTION_FINAL_ARTIFACTS,
        )

    expected_stages = stage_definitions
    completed_stages = []
    missing_stages = []

    # 检查每个阶段
    for stage_name, identifiers in expected_stages.items():
        found = False
        for identifier in identifiers:
            if _identifier_exists(bb, identifier):
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
    for stage_name, identifiers in expected_stages.items():
        if 'summarizer' in stage_name or 'final' in stage_name.lower():
            for identifier in identifiers:
                file_path = _resolve_identifier_path(bb, identifier)
                if file_path:
                    final_output = str(file_path)
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
                    paths.append(_plan_path_to_identifier(rel_path))
            if paths:
                expected[stage] = paths
        else:
            rel_path = phase.get('expected_output_path')
            if rel_path:
                expected[stage] = [_plan_path_to_identifier(rel_path)]
    return expected


def _check_expected_outputs(
    bb: BlackboardManager,
    expected_stages: Dict[str, list],
    required_artifacts: Optional[list] = None,
) -> Dict:
    completed_stages = []
    missing_stages = []
    missing_outputs = {}
    missing_artifacts = []

    schema_errors = {}

    for stage_name, identifiers in expected_stages.items():
        missing = []
        for identifier in identifiers:
            if not _identifier_exists(bb, identifier):
                missing.append(identifier)
        if missing:
            missing_stages.append(stage_name)
            missing_outputs[stage_name] = missing
        else:
            completed_stages.append(stage_name)

            # 🆕 改动 D: 接入 Schema 验证器
            for identifier in identifiers:
                data = _read_identifier_json(bb, identifier)
                if data is not None:
                    try:
                        valid, err_msg = validate_stage_output(data, stage_name)
                        if not valid:
                            schema_errors[stage_name] = err_msg
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
        if not (bb.get_session_dir() / rel_path).exists():
            missing_artifacts.append(rel_path)

    final_output = None
    for rel_path in ['final_solution.md', 'final_result.json', 'final_report.md']:
        full_path = bb.get_session_dir() / rel_path
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
    bb = BlackboardManager(session_id=session_id)

    marker_data = {
        'session_id': session_id,
        'status': status,
        'completion_rate': completion_rate,
        'completed_at': datetime.now().isoformat()
    }

    marker_path = bb.write('.completed', marker_data)

    # 同步更新 .stage_progress.json，避免状态不一致（P1-4 修复）
    try:
        progress_raw = bb.read('.stage_progress', subdir='stages')
        if progress_raw:
            import json as _json
            progress_data = _json.loads(progress_raw)
            progress_data['status'] = 'completed' if status == 'completed' else 'failed'
            progress_data['completed_at'] = marker_data['completed_at']
            bb.write('.stage_progress', progress_data, subdir='stages')
    except Exception:
        pass  # 非关键路径，不阻塞主流程

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