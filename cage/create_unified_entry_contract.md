# 创建 DeepFlow 统一入口脚本和文档更新

## 目标
1. 创建 `deepflow.py` 统一入口脚本（一键初始化 + 生成调用指令）
2. 更新 SKILL.md，明确完整的执行步骤

## 影响分析

### 选项 A（deepflow.py）对现有流程的影响

| 现有组件 | 修改方式 | 影响 |
|:---|:---|:---:|
| `core/master_agent.py` | **不修改** | ✅ 无影响 |
| `core/task_builder.py` | **不修改** | ✅ 无影响 |
| `core/data_manager_worker.py` | **不修改** | ✅ 无影响 |
| `orchestrator_agent.py` | **不修改** | ✅ 无影响 |
| `prompts/` | **不修改** | ✅ 无影响 |
| `blackboard/` | **不修改** | ✅ 无影响 |
| **新增** `deepflow.py` | 新增包装脚本 | ✅ 纯新增，可选使用 |

**结论**: `deepflow.py` 是**可选的便利包装**，现有流程完全保留。用户可以选择：
- 旧方式：`python3 core/master_agent.py` + 手动 spawn
- 新方式：`python3 deepflow.py`（一键完成初始化并输出生成调用指令）

### 设计原则
- `deepflow.py` 内部调用 `master_agent.py` 的函数（复用）
- 不修改任何现有代码
- 输出 JSON 格式的调用指令，供主 Agent 解析执行

## 验收标准
- [ ] `deepflow.py` 可以独立运行，完成初始化
- [ ] `deepflow.py` 输出包含 session_id + orchestrator_task + 调用指令
- [ ] SKILL.md 更新为完整的执行步骤（触发 → 初始化 → spawn → 等待）
- [ ] 现有 `master_agent.py` 完全不变，仍可独立使用
- [ ] 端到端验证通过

## 执行步骤
1. 创建 `deepflow.py`
2. 更新 `SKILL.md`
3. 更新 `README.md`（添加使用示例）
4. 测试验证
5. Git 提交
