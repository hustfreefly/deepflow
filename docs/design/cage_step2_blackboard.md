# 契约笼子 Step 2: blackboard.py

## 声明

**目标**: 修改 STAGE_PATH_REGISTRY，stage 路径加域前缀 `solution/`。

**改动**:
1. STAGE_PATH_REGISTRY 中所有 stage 路径从 `stages/xxx` 改为 `solution/stages/xxx`
2. `__init__` 中 base_path 构造适配 V2 session_id（`{slug}/runs/{run_id}` 格式）

**不改**:
- 类名、其他方法、blackboard_manager 等

## 验证标准

| # | 验证项 | 方法 | 通过条件 |
|:---|:---|:---|:---|
| V1 | STAGE_PATH_REGISTRY 有 solution/ 前缀 | 代码检查 | 所有值以 `solution/` 开头 |
| V2 | V2 session_id 初始化 BlackboardManager | 运行测试 | base_path 正确 |
| V3 | V1 session_id 仍可初始化（兼容） | 运行测试 | 不报错 |
| V4 | 语法检查 | python3 import | 无语法错误 |
