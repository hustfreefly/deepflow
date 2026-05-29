#!/usr/bin/env python3
"""
Solution Orchestration - 执行所有7个任务
"""
import sys
import json
import os

sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow')

from domains.solution.orchestrator_agent import SolutionOrchestratorV21

# 定义7个任务
tasks_config = [
    {
        'id': '_solution_1a0c3e6b',
        'topic': '契约笼子验证测试 - 验证DeepFlow契约笼子三层强制机制、Phase门禁流程、AI提示词约束',
        'type': 'architecture',
        'constraints': ['验证契约笼子三层强制机制', '验证Phase门禁流程', '验证AI提示词约束'],
        'stakeholders': ['开发团队', '架构师', 'QA团队']
    },
    {
        'id': '_solution_1fbf8ddd',
        'topic': '端到端验证测试 - 验证DeepFlow端到端执行流程',
        'type': 'architecture',
        'constraints': ['验证端到端执行流程', '验证各阶段衔接', '验证输出质量'],
        'stakeholders': ['开发团队', '测试团队']
    },
    {
        'id': '_solution_d68971de',
        'topic': '端到端完整验证 - 完整验证DeepFlow Solution Pro全流程',
        'type': 'architecture',
        'constraints': ['完整执行10阶段流程', '验证所有Worker输出', '验证Harness评分'],
        'stakeholders': ['架构师', 'QA团队', '产品经理']
    },
    {
        'id': 'task_solution_b7b6e4de',
        'topic': '端到端验证修复 - 修复端到端验证中发现的问题',
        'type': 'architecture',
        'constraints': ['修复验证发现的问题', '优化执行流程', '提升输出质量'],
        'stakeholders': ['开发团队', '架构师']
    },
    {
        'id': 'dryrun_solution_dc926cb3',
        'topic': 'dryrun验证 - 执行Solution Pro dryrun测试',
        'type': 'architecture',
        'constraints': ['验证dryrun模式', '测试快速执行路径', '验证最小可行输出'],
        'stakeholders': ['开发团队', '测试团队']
    },
    {
        'id': 'CRP_solution_f8d9356f',
        'topic': '算力中继平台架构设计 - 设计AI算力调度与交易平台',
        'type': 'architecture',
        'constraints': ['支持10000+并发', '延迟<5秒', '支持平台方、供给方、需求方多角色'],
        'stakeholders': ['平台运营方', '算力供给方', '算力需求方', '技术团队']
    },
    {
        'id': 'CRP_solution_e91d9abd',
        'topic': '算力中继平台架构设计(复杂任务) - 设计高可用AI算力调度平台',
        'type': 'architecture',
        'constraints': ['高可用架构', '弹性伸缩', '多租户隔离', '安全合规'],
        'stakeholders': ['平台运营方', '算力供给方', '算力需求方', '安全团队', '运维团队']
    },
]

results = []

for task in tasks_config:
    try:
        print(f"\n{'='*60}")
        print(f"处理任务: {task['id']}")
        print(f"主题: {task['topic']}")
        print(f"{'='*60}")

        # 创建 Orchestrator
        orch = SolutionOrchestratorV21(
            topic=task['topic'],
            solution_type=task['type'],
            mode='standard',
            constraints=task['constraints'],
            stakeholders=task['stakeholders'],
            session_prefix=task['id']
        )

        # 初始化
        session_id = orch.init()
        print(f"✅ Session initialized: {session_id}")

        # 获取所有任务
        tasks = orch.get_all_tasks()
        print(f"✅ Generated {len(tasks)} task stages: {list(tasks.keys())}")

        # 保存执行计划
        orch.save_execution_plan()
        print(f"✅ Execution plan saved")

        # 保存任务详情
        orch.save_tasks()
        print(f"✅ Tasks saved")

        results.append({
            'task_id': task['id'],
            'status': 'initialized',
            'session_id': session_id,
            'base_path': orch.base_path,
            'tasks_count': len(tasks)
        })

    except Exception as e:
        print(f"❌ Error: {e}")
        results.append({
            'task_id': task['id'],
            'status': 'failed',
            'error': str(e)
        })

# 输出汇总
print(f"\n{'='*60}")
print("执行汇总")
print(f"{'='*60}")
for r in results:
    print(f"{r['task_id']}: {r['status']}")
    if r['status'] == 'initialized':
        print(f"  - Session: {r['session_id']}")
        print(f"  - Tasks: {r['tasks_count']}")
    elif r['status'] == 'failed':
        print(f"  - Error: {r.get('error', 'Unknown')}")

print(f"\n{json.dumps(results, indent=2, ensure_ascii=False)}")
