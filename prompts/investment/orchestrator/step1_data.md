## STEP 1: DataManager 数据采集

**目标**：采集基础数据到 Blackboard/data/v0/

**执行**：
```python
# 从环境变量获取参数
code = os.environ.get('DEEPFLOW_CODE')
name = os.environ.get('DEEPFLOW_NAME')

# 初始化DataManager
from data_manager import DataEvolutionLoop, ConfigDrivenCollector
from data_providers.investment import register_providers
from blackboard_manager import BlackboardManager

register_providers()
config_path = "/Users/allen/.openclaw/workspace/.deepflow/data_sources/investment.yaml"
blackboard = BlackboardManager(session_id)
collector = ConfigDrivenCollector(config_path)
data_loop = DataEvolutionLoop(collector, blackboard)

# 执行采集
context = {"code": code, "name": name}
bootstrap_data = data_loop.bootstrap_phase(context)
```

**验证清单**：
- [ ] blackboard/{session_id}/data/INDEX.json 存在
- [ ] blackboard/{session_id}/data/01_financials/key_metrics.json 存在

**完成后输出**：
```
[PHASE_COMPLETE: data_collection]
```
