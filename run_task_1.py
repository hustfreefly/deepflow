#!/usr/bin/env python3
import sys
import json
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow')

from domains.solution.orchestrator_agent import SolutionOrchestratorV21

# 初始化第一个任务
orch = SolutionOrchestratorV21(
    topic='契约笼子验证测试 - 验证DeepFlow契约笼子机制',
    solution_type='architecture',
    mode='standard',
    constraints=['验证契约笼子三层强制机制', '验证Phase门禁流程', '验证AI提示词约束'],
    stakeholders=['开发团队', '架构师', 'QA团队'],
    session_prefix='solution_1a0c3e6b'
)
session_id = orch.init()
print(f'Session initialized: {session_id}')

# 获取所有任务
tasks = orch.get_all_tasks()
print(f'Generated {len(tasks)} task stages')

# 保存执行计划和任务
orch.save_execution_plan()
orch.save_tasks()

# 输出任务配置
result = {
    'session_id': session_id,
    'base_path': orch.base_path,
    'tasks': list(tasks.keys())
}
print(json.dumps(result, indent=2, ensure_ascii=False))
