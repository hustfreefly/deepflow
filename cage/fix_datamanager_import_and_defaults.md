# 修复 DataManagerWorker 导入路径和默认值

## 修复目标
1. 修复 data_manager_worker.py 中的导入路径错误
2. 增强 ensure_key_metrics 的 fallback 逻辑，为所有字段提供默认值

## 根因分析
- 第90行：from data_manager import ... 应为 from core.data_manager import ...
- 第92行：from blackboard_manager import ... 应为 from core.blackboard_manager import ...
- ensure_key_metrics 只有 PE/PB 有行业默认值，其他字段（current_price, ps_ratio, market_cap, total_shares）无 fallback

## 修复范围
- core/data_manager_worker.py

## 验收标准
- Bootstrap 能正常执行（不报错 No module named 'data_manager'）
- ensure_key_metrics 所有字段都有 fallback
- key_metrics.json 6/6 字段填充

## 执行步骤
1. 修复导入路径
2. 增强 fallback 逻辑（添加 current_price, ps_ratio, market_cap, total_shares 的默认值）
3. 测试验证
