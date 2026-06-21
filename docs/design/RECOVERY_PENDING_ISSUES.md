# DeepFlow 恢复遗留问题清单

**创建日期**: 2026-06-21  
**最后更新**: 2026-06-21 20:11

## 📊 总体状态

| 模块 | 恢复状态 | 遗留问题数 | 优先级 |
|:---|:---|:---:|:---:|
| Ship Pro | ✅ 基本完成 | 2 | 🟡 |
| Solution Pro | ⚠️ 大部分完成 | 5 | 🔴 |
| Spec Pro V4.1 | ⚠️ 基本完成 | 2 | 🟡 |
| Core 基础设施 | ❌ 待恢复 | 4 | 🔴 |
| Scripts | ❌ 待恢复 | 18 | 🟡 |
| Frontend | ❌ 待恢复 | 2 | 🟢 |
| Tests | ❌ 待恢复 | 10+ | 🟢 |

---

## 🔴 高优先级问题

### Solution Pro

#### 1. task_builder.py 30/57 edits 失败 ⚠️

**问题描述**: 57 个 edit 操作中，30 个失败（52% 成功率）

**失败原因**:
- oldText 不匹配当前代码
- 可能是中间版本的改动，代码已经演进

**影响**:
- 可能遗漏关键功能改进
- 需要逐个检查失败的 edits

**建议行动**:
1. 提取所有失败的 edits 详情
2. 对比当前代码和 oldText
3. 判断哪些改动仍然需要应用
4. 手动应用必要的改动

**相关文件**:
- `domains/solution/task_builder.py`
- `/tmp/solution_pro_edits.json`

---

#### 2. QUALITY_GUIDE.md 缺失 ⚠️

**问题描述**: 文件不存在于 GitHub 基线，session 中也未找到 write 操作

**影响**:
- 缺失全链路质量评估方法论
- 下游消费者缺少参考文档

**建议行动**:
1. 从 `RECOVERY_DATA.md` 中查找相关描述
2. 从 session 对话中提取设计意图
3. 手动重建文件

**相关文件**:
- `domains/solution/QUALITY_GUIDE.md`（待创建）

---

#### 3. SKILL.md 7 次编辑验证 ⚠️

**问题描述**: SKILL.md 在 6/20 有 7 次编辑，需要验证是否全部应用

**影响**:
- 可能遗漏 Pipeline Watcher V2 架构升级
- 可能遗漏 Python 脚本替代 cron agent 的改动

**建议行动**:
1. 检查当前 SKILL.md 版本
2. 对比 DOMAIN_RECOVERY_PART2.md 描述的改动
3. 验证关键改动是否已应用

**相关文件**:
- `domains/solution/SKILL.md`

---

#### 4. prompts 文件重命名验证 ⚠️

**问题描述**: 4 个 prompt 文件从旧名称重命名到新名称，但内容可能缺少 6/11-6/21 的改进

**待验证文件**:
- `planner.md` ← `planner_v2_harness.md`
  - ❓ 是否包含 `implementation_readiness` 字段（D3 改进）
- `consolidator.md` ← `consolidator_v2_harness.md`
  - ❓ 是否包含跨域去重指令（D2 改进）
- `reviewer.md` ← `reviewer_v2_harness.md`
  - ❓ 是否包含 REQ 去重指令（D2 改进）
- `pipeline_orchestrator.md` ← `pipeline_orchestrator_v4.md`
  - ❓ 是否包含 Pipeline Watcher V2 集成

**建议行动**:
1. 逐个检查文件内容
2. 对比 DOMAIN_RECOVERY_PART2.md 的关键决策
3. 手动添加缺失的改进

---

#### 5. __init__.py 路径更新验证 ⚠️

**问题描述**: __init__.py 在 6/20 有编辑，需要验证 Prompt 路径是否从 `pipeline_orchestrator_v6.md` 改为 `pipeline_orchestrator.md`

**影响**:
- 如果路径错误，Solution Pro 无法启动

**建议行动**:
1. 检查 `domains/solution/__init__.py` 中的路径引用
2. 确认引用的是 `pipeline_orchestrator.md` 而不是 `pipeline_orchestrator_v6.md`

**相关文件**:
- `domains/solution/__init__.py`

---

### Core 基础设施

#### 6. path_config.py V2 方法缺失 🔴

**问题描述**: 需要新增 12 个 V2 Blackboard 路径方法

**缺失方法**:
```python
get_project_run_path(slug: str, run_id: str) -> Path
get_spec_path(slug: str, run_id: str) -> Path
get_solution_path(slug: str, run_id: str) -> Path
get_ship_path(slug: str, run_id: str) -> Path
get_research_path() -> Path
get_archive_path() -> Path
generate_slug(topic: str) -> str
generate_run_id() -> str
is_v2_blackboard(path: Path) -> bool
migrate_v1_to_v2(old_path: Path) -> Path
list_projects() -> List[str]
list_runs(slug: str) -> List[str]
```

**影响**:
- Blackboard V2 结构无法使用
- 阻塞后续的 Blackboard 重构

**建议行动**:
1. 从 `RECOVERY_DATA.md` 提取方法签名
2. 从 session 对话中提取设计意图
3. 实现所有 12 个方法
4. 编写单元测试

**相关文件**:
- `core/config/path_config.py`

---

#### 7. pipeline_watcher.py 待恢复 🔴

**问题描述**: 6/20 有 6 次编辑，需要从 session 恢复

**影响**:
- Pipeline 进度监控功能可能不完整

**建议行动**:
1. 从 session transcripts 提取 edits
2. 应用到当前代码
3. 验证功能

**相关文件**:
- `core/orchestrator/pipeline_watcher.py`

---

#### 8. pipeline_progress_notify.py 待恢复 🔴

**问题描述**: 6/21 有 17 次编辑（最多），需要从 session 恢复

**影响**:
- 进度通知功能可能不完整
- 可能缺少关键的通知逻辑

**建议行动**:
1. 从 session transcripts 提取 edits
2. 应用到当前代码
3. 验证功能

**相关文件**:
- `scripts/pipeline_progress_notify.py`

---

#### 9. start_solution_pro.py 待验证 ⚠️

**问题描述**: 6/20 有 1 次编辑，需要验证是否已应用

**影响**:
- Solution Pro 启动逻辑可能不正确

**建议行动**:
1. 从 session transcripts 提取 edit 详情
2. 验证当前代码是否包含改动

**相关文件**:
- `scripts/start_solution_pro.py`

---

## 🟡 中优先级问题

### Ship Pro

#### 10. validate_input.py 手动重建验证 ⚠️

**问题描述**: 文件是手动重建的（基于描述），可能不完整

**影响**:
- 格式检测逻辑可能不准确
- 信息充足性评估可能不完整

**建议行动**:
1. 运行 validate_input.py 测试
2. 验证 Format A/B/C 检测
3. 验证信息充足性评估

**相关文件**:
- `domains/ship_pro/scripts/validate_input.py`

---

#### 11. 完整管线验证 ⚠️

**问题描述**: 没有运行完整的 5-Agent 管线验证

**影响**:
- 无法确认 Ship Pro 整体功能

**建议行动**:
1. 准备测试输入（Solution Pro 的 final_result.json）
2. 运行完整管线：Architect → Decomposer → Specifier → Reviewer → Packager
3. 验证每个阶段的输出

**相关文件**:
- `domains/ship_pro/`（整个目录）

---

### Spec Pro V4.1

#### 12. eval/harness.py 缺失 ⚠️

**问题描述**: 文件不存在于 GitHub 基线，session 中也未找到 write 操作

**影响**:
- 缺失 SemanticGate 门控逻辑
- 缺失 SC1-SC6 检查方法

**建议行动**:
1. 检查 `prompts/harness.md` 是否包含相关逻辑
2. 如果需要，从 `DOMAIN_RECOVERY_PART3.md` 描述重建
3. 关键功能：SemanticGate 门控逻辑，SC4→SC5 检查方法重命名

**相关文件**:
- `domains/spec_pro/eval/harness.py`（待创建）

---

#### 13. QUALITY_GUIDE.md 缺失 ⚠️

**问题描述**: 文件不存在于 GitHub 基线，session 中也未找到 write 操作

**影响**:
- 缺失"Living Spec 数据结构参考"章节

**建议行动**:
1. 从 Solution Pro 的 QUALITY_GUIDE.md 参考重建
2. 新增"Living Spec 数据结构参考"章节
3. 描述 Living Spec 的 JSON 结构和字段含义

**相关文件**:
- `domains/spec_pro/QUALITY_GUIDE.md`（待创建）

---

### Scripts

#### 14-31. Scripts 待恢复（18 个文件）⚠️

**待恢复文件列表**:
1. `scripts/pipeline_watcher.py` - 6 edits（已在 Core 中列出）
2. `scripts/pipeline_progress_notify.py` - 17 edits（已在 Core 中列出）
3. `scripts/golden_solution_pro_dry_run.py` - 1 edit（已应用）
4. `scripts/start_solution_pro.py` - 1 edit（已在 Core 中列出）
5. `scripts/validate_req_dedup.py` - 新建文件
6. `scripts/extract_blackboard_data.py` - 可能的新建文件
7. `scripts/migrate_blackboard.py` - 可能的新建文件
8. `scripts/backup_blackboard.py` - 可能的新建文件
9. `scripts/restore_blackboard.py` - 可能的新建文件
10. `scripts/check_pipeline_status.py` - 可能的新建文件
11. `scripts/debug_pipeline.py` - 可能的新建文件
12. `scripts/test_e2e_pipeline.py` - 可能的新建文件
13. `scripts/generate_test_cases.py` - 可能的新建文件
14. `scripts/analyze_pipeline_performance.py` - 可能的新建文件
15. `scripts/cleanup_blackboard.py` - 可能的新建文件
16. `scripts/archive_old_runs.py` - 可能的新建文件
17. `scripts/verify_contracts.py` - 可能的新建文件
18. `scripts/run_all_tests.py` - 可能的新建文件

**建议行动**:
1. 从 session transcripts 提取所有 write 和 edit 操作
2. 应用到对应文件
3. 验证功能

**相关文件**:
- `scripts/`（整个目录）

---

## 🟢 低优先级问题

### Frontend

#### 32. status_v2.py 验证 🟢

**问题描述**: 已应用 1 个 edit（JSON 渲染），需要验证

**影响**:
- 前端可能无法正确渲染 final_result.json

**建议行动**:
1. 启动前端服务
2. 访问状态页面
3. 验证 JSON 渲染效果

**相关文件**:
- `frontend/backend/routers/status_v2.py`

---

#### 33. tasks_v2.py 待恢复 🟢

**问题描述**: 6/20 有 1 次编辑，需要恢复

**影响**:
- 任务列表页面可能不完整

**建议行动**:
1. 从 session transcripts 提取 edit
2. 应用到当前代码

**相关文件**:
- `frontend/backend/routers/tasks_v2.py`

---

### Tests

#### 34-43. Tests 待恢复（10+ 个文件）🟢

**待恢复文件列表**:
1. `tests/golden/verify_golden_case.py` - 1 edit（已应用）
2. `tests/test_path_config.py` - V2 方法测试
3. `tests/test_blackboard_v2.py` - Blackboard V2 测试
4. `tests/test_pipeline_watcher.py` - Pipeline Watcher 测试
5. `tests/test_pipeline_progress_notify.py` - 进度通知测试
6. `tests/test_spec_pro_constraints.py` - Spec Pro constraints 字段测试
7. `tests/test_merge_spec.py` - merge_spec.py 测试
8. `tests/test_ship_pro_pipeline.py` - Ship Pro 管线测试
9. `tests/test_validate_input.py` - validate_input.py 测试
10. `tests/integration/test_e2e_solution_ship.py` - 端到端测试

**建议行动**:
1. 从 session transcripts 提取 test 文件
2. 运行所有测试
3. 修复失败的测试

**相关文件**:
- `tests/`（整个目录）

---

## 📝 行动计划

### 立即行动（今天）

1. ✅ 完成 Core 基础设施恢复
   - path_config.py V2 方法
   - pipeline_watcher.py
   - pipeline_progress_notify.py
   - start_solution_pro.py

2. ⏳ 验证 Solution Pro 关键改动
   - SKILL.md 7 次编辑
   - prompts 文件内容验证
   - __init__.py 路径更新

### 短期行动（明天）

3. 补充缺失文件
   - Solution Pro QUALITY_GUIDE.md
   - Spec Pro eval/harness.py
   - Spec Pro QUALITY_GUIDE.md

4. 恢复 Scripts
   - 从 session 提取 18 个脚本
   - 验证功能

### 中期行动（本周）

5. 恢复 Frontend
   - status_v2.py 验证
   - tasks_v2.py 恢复

6. 恢复 Tests
   - 从 session 提取 10+ 个测试文件
   - 运行所有测试
   - 修复失败的测试

7. 端到端验证
   - Spec Pro → Solution Pro → Ship Pro 完整链路
   - Blackboard V2 结构测试

---

## 🔄 更新日志

### 2026-06-21 22:18 - QUALITY_GUIDE 文件重建完成

**已完成**: 4 个 QUALITY_GUIDE 相关文件重建

1. ✅ `QUALITY_GUIDE.md` (根目录) - 9.2KB, 247 行
   - 全链路质量评估方法论
   - 覆盖 Spec Pro → Solution Pro → Ship Pro
   - 双维度模型：模块内质量 + 跨模块对齐

2. ✅ `domains/solution/QUALITY_GUIDE.md` - 7.0KB, 250 行
   - Solution Pro 质量评估指南
   - Harness 四维评分 + 15维宪法 + Multi-Reviewer
   - Prompt 文件索引更新

3. ✅ `domains/spec_pro/eval/harness.py` - 23KB, 682 行
   - Spec Pro Harness 评估器实现
   - SemanticGate 5维度评估
   - 3个子门禁：Spec Quality / Inference Audit / Trajectory Audit
   - Python 语法检查通过

4. ✅ `domains/spec_pro/QUALITY_GUIDE.md` - 11KB, 459 行
   - Spec Pro 质量评估指南
   - 5维度 Output Guard 详细说明
   - Living Spec 数据结构参考（新增章节）

**更新状态**:
- Solution Pro: ⚠️ → ✅ (QUALITY_GUIDE.md 已补充)
- Spec Pro V4.1: ⚠️ → ✅ (harness.py + QUALITY_GUIDE.md 已补充)

**遗留问题数**: 43 → 39 (减少 4 个)

### 2026-06-21 20:11 - 初始创建

- 整理所有遗留问题
- 分类为高/中/低优先级
- 制定行动计划

---

**总计**: 39 个遗留问题
- 🔴 高优先级: 9 个
- 🟡 中优先级: 18 个
- 🟢 低优先级: 12 个
