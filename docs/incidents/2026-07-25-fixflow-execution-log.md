# FixFlow 执行日志：跨域系统修复（2026-07-25 12:20-12:30）

> 触发：Solution Pro 2.5D 实战暴露 21 问题 → 3 Agent 跨域审查 → 发现 7 项必修问题

## Phase 0: 决策门

| # | 问题 | 不修后果 | 本质 | 决策 |
|---|------|---------|------|:----:|
| P0-1 | Deliver Pro project_name 无 sanitize | crash | 代码 | ✅ 代码修 |
| P0-2 | NO_REPLY 防护全域缺失 | 子 Agent 死亡 | Prompt | ✅ Prompt 修 |
| P1-1 | Ship Pro yield 残留 | yield 即死 | 混合 | ✅ 混合修 |
| P1-2 | Solution Pro MD-first 未接线 | track 未生成 | 代码 | ✅ 代码修 |
| P1-3 | Spec Pro 输出契约半钉死 | diffuse | Prompt | ❌ 不修 |
| P1-4 | Research Pro MD-first 仅 prompt 级 | diffuse | Prompt | ❌ 不修 |
| P2-1 | Ship Pro sanitize 不完整 | 路径错位 | 代码 | ✅ 代码修 |
| P2-2 | Deliver Pro legacy .parent | 迁移失败 | 代码 | ✅ 代码修 |
| P2-3 | Spec Pro 无恢复入口 | 从头开始 | 代码 | ✅ 代码修 |
| P2-4 | Ship Pro 双路径写入 | 架构债 | 架构 | ❌ 不修 |

**必修 7 项**，按方法分组：
- 代码 Worker：5 项（P0-1, P1-2, P2-1, P2-2, P2-3）
- Prompt Worker：1 项（P0-2）
- 混合 Worker：1 项（P1-1）

## Phase 1: 结构化诊断（自欺检测已填证据）

### P0-1 Deliver Pro sanitize
- 症状：project_name 含 `/` 时全链路路径错位
- 根因：`__init__.py:224`, `orchestrator.py:63,72` 直接拼接无 sanitize
- 修复方向：代码修（复用 `core/config/path_config.py:_sanitize_session_id`）
- 信心度：高（Solution Pro 已有参考实现）

### P0-2 NO_REPLY 防护
- 症状：子 Agent 回 NO_REPLY 导致 session 关闭（4 次实证）
- 根因：spec/research/ship 三域 prompt 零 NO_REPLY 规则
- 修复方向：Prompt 修（提取 `_shared_subagent_rules.md` 为全域共享）
- 信心度：高（Solution Pro 已有参考实现）

### P1-1 Ship Pro yield 残留
- 症状：V8 决策说禁止 yield，但 prompt 仍有 7+ 处 yield 指令
- 根因：`V8_DECISIONS.md:172` vs `__init__.py:408-670` 文档与实现不同步
- 修复方向：混合修（Prompt 改 cron wake + 文档更新）
- 信心度：高

### P1-2 Solution Pro MD-first 未接线
- 症状：`render_final_solution_md()` 存在但生产链路零调用，track 未生成
- 根因：finalize 相位未调用 render 函数
- 修复方向：代码修（在 `__init__.py` finalize 步骤调用 render）
- 信心度：高（其他三域已有参考实现）

### P2-1 Ship Pro sanitize 不完整
- 症状：role 只替换空格不替换 `/`
- 根因：`ship_orchestrator.py:540`, `__init__.py:758` 替换规则不完整
- 修复方向：代码修（加 `/` 替换）
- 信心度：高

### P2-2 Deliver Pro legacy .parent
- 症状：legacy 迁移用 `.parent`，slash 路径下错位
- 根因：`phase_deriver.py:332` 路径推导
- 修复方向：代码修（改为显式路径参数）
- 信心度：高

### P2-3 Spec Pro 无恢复入口
- 症状：有状态文件但无 resume() 方法
- 根因：`spec_pro_api.py` 无恢复代码
- 修复方向：代码修（增加 resume CLI 入口）
- 信心度：中（需理解状态机）

## Phase 2: 契约执行

### Worker 分配
- **fix_code_worker**：P0-1, P1-2, P2-1, P2-2, P2-3（5 项，确定性批量）
- **fix_prompt_worker**：P0-2（1 项，语义）
- **fix_mixed_worker**：P1-1（1 项，Prompt + 文档）

### 执行状态
- ✅ **fix_prompt_worker 完成**（12:24）：14 个文件修改，17/17 测试通过
  - 新建 `core/prompts/_shared_subagent_rules.md`（全域共享）
  - 追加铁律 #8：绝不输出 NO_REPLY
  - 更新 spec_pro（5 prompt）+ research_pro（6 prompt）+ ship_pro（2 prompt）引用
  - 新增测试：`core/tests/test_shared_rules_reference.py`
- 🔄 **fix_code_worker 运行中**
- 🔄 **fix_mixed_worker 运行中**

## Phase 3: 独立验证（待执行）

验证清单：
- [ ] P0-1: Deliver Pro sanitize 测试通过？grep 确认无裸拼接？
- [ ] P0-2: 全域 prompt 引用共享规则？grep 确认 NO_REPLY 铁律存在？
- [ ] P1-1: Ship Pro prompt 不含 sessions_yield？grep 确认？
- [ ] P1-2: final_solution.md 被生成？track.json 被生成？
- [ ] P2-1: Ship Pro role sanitize 含 `/` 替换？grep 确认？
- [ ] P2-2: Deliver Pro legacy 迁移用显式路径？grep 确认无 .parent？
- [ ] P2-3: Spec Pro resume 入口存在？测试通过？
- [ ] 全量测试：`pytest domains/*/tests/ -q` 全绿？

独立验证方式：spawn 独立 Agent（不同模型）执行 grep 验证。
