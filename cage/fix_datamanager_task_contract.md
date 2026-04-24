# 契约笼子：DataManager Task 修复（选项B）

## 目标
修复 task_builder.py 中的 build_data_manager_task()，使其使用 DataManagerWorker 类而非旧版 DataEvolutionLoop

## 根因
- task_builder.py 生成的 DataManager Task 调用旧版 data_manager.py 的 bootstrap_phase()
- 旧版方法不生成 key_metrics.json
- data_manager_worker.py 中的 ensure_key_metrics() 方法封装了完整的估值数据获取逻辑，但未被调用

## 修复范围
- core/task_builder.py: build_data_manager_task() 方法

## 修复方案（选项B）
将 Task 从：
```python
from core.data_manager import DataEvolutionLoop, ConfigDrivenCollector
# ... 旧版逻辑，不生成 key_metrics
```

改为：
```python
from core.data_manager_worker import DataManagerWorker
# ... 调用 worker.run() 执行完整流程（含 ensure_key_metrics）
```

## 验收标准
- [ ] Task 中调用 DataManagerWorker 类
- [ ] Task 执行后生成 key_metrics.json（含 PE/PB/PS/市值）
- [ ] data_manager_result.json 正常生成
- [ ] 语法验证通过
- [ ] Git 提交

## 执行步骤
1. 备份 task_builder.py
2. 修改 build_data_manager_task() 方法
3. 语法验证
4. 测试生成 Task 内容
5. 提交 Git
