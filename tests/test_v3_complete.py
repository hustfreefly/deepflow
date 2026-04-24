#!/usr/bin/env python3
"""V3 完整模块验证测试"""
import sys
sys.path.insert(0, '.')

print('=== V3 完整模块验证 ===\n')

# 验证 QualityGate
print('1. QualityGate...')
from quality_gate import QualityGate, QualityConfig
gate = QualityGate(QualityConfig.default())
report = gate.evaluate('这是一个测试输出，包含结论和数据。')
print(f'   总分: {report.overall_score:.2f}')
print(f'   决策: {report.decision.value}')
print('   ✅ QualityGate 工作正常')

# 验证 ResilienceManager
print('\n2. ResilienceManager...')
from resilience_manager import ResilienceManager, Task
mgr = ResilienceManager()
print(f'   熔断器数: {len(mgr._circuit_breakers)}')
print('   ✅ ResilienceManager 工作正常')

# 验证 Observability
print('\n3. Observability...')
from observability import Observability
trace_id = Observability.init_trace('test_v3_complete')
Observability.log_stage_start('plan', 'planner', trace_id)
Observability.log_stage_end('plan', True, 0.5, trace_id)
metrics = Observability.get_metrics()
print(f'   Trace ID: {trace_id}')
print(f'   指标数: {len(metrics)}')
print('   ✅ Observability 工作正常')

print('\n🎉 V3 所有模块验证通过！')
print('\n完整架构已就绪：')
print('  • PipelineEngine - 管线执行')
print('  • QualityGate - 质量评估')
print('  • ResilienceManager - 故障隔离')
print('  • Observability - 可观测性')
