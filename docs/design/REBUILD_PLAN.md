# DeepFlow 重建计划

> **日期**: 2026-06-21
> **基线**: GitHub main 分支 (commit 887c300, 2026-06-11)
> **目标**: 恢复到 2026-06-21 16:45 之前的状态

---

## 一、重建原则

1. **底层优先**：先建基础设施，再建上层应用
2. **数据驱动**：有完整 session 日志的先做，没有的放后面
3. **依赖顺序**：被依赖的先建，依赖它的后建
4. **验证闭环**：每个阶段完成后验证，确保可运行

---

## 二、重建顺序（7 个阶段）

### Phase 1: Core 基础设施 (5 个文件)
**优先级**: 🔴 最高  
**理由**: 所有域都依赖 core，必须先建  
**预计时间**: 30 分钟

| 文件 | 改动次数 | 数据源 |
|:---|:---|:---|
| `core/config/path_config.py` | 1x | 今天 session (Step 1) |
| `core/orchestrator/pipeline_orchestrator.py` | 1x | 今天 session (Step 3) |
| `core/orchestrator/pipeline_watcher.py` | 6x | 6/20 session (5e67a492) |
| `scripts/pipeline_progress_notify.py` | 17x | 6/21 session (86924325) |
| `scripts/start_solution_pro.py` | 1x | 6/20 session (5e67a492) |

**验证**: 
- path_config.py 单元测试 (27 个测试用例)
- pipeline_orchestrator 语法检查

**恢复方法**: 
- 从 session 日志中提取最后一次 write 操作的完整内容
- 如果 session 日志不完整，从 RECOVERY_DATA.md 中的代码片段手工重建

---

### Phase 2: Spec Pro V4.1 (12 个文件)
**优先级**: 🔴 高  
**理由**: Solution Pro 依赖 Spec Pro 的 Living Spec 输出  
**预计时间**: 45 分钟

| 文件 | 改动次数 | 数据源 |
|:---|:---|:---|
| `domains/spec_pro/coordinator.py` | 1x | 6/20 session (ac22d0d8) |
| `domains/spec_pro/merge_spec.py` | 2x | 6/20 session (5e67a492) |
| `domains/spec_pro/requirement_structuring.py` | 1x | 6/20 session (5e67a492) |
| `domains/spec_pro/prompts/assess.md` | 2x | 6/20 session (ac22d0d8) |
| `domains/spec_pro/prompts/guide.md` | 1x | 6/20 session (ac22d0d8) |
| `domains/spec_pro/prompts/parse.md` | 1x | 6/20 session (ac22d0d8) |
| `domains/spec_pro/prompts/parse_response.md` | 1x | 6/20 session (ac22d0d8) |
| `domains/spec_pro/prompts/structure.md` | 2x | 6/20 session (ac22d0d8) |
| `domains/spec_pro/eval/harness.py` | 2x | 6/20 session (ac22d0d8) |
| `domains/spec_pro/QUALITY_GUIDE.md` | 2x | 6/20 session (a6112077) |

**验证**:
- Spec Pro 单元测试
- 运行一次 Spec Pro 生成 Living Spec

**恢复方法**:
- 从 6/20 的 session 日志中提取
- 如果日志不完整，从 spec_pro_v4.1_proposal.md 和 DISCUSSIONS.md 中推断改动

---

### Phase 3: Solution Pro 改动 (26 个文件)
**优先级**: 🔴 高  
**理由**: Ship Pro 依赖 Solution Pro 的 final_result.json  
**预计时间**: 90 分钟

**3.1 核心改动 (7 个文件)**:

| 文件 | 改动次数 | 数据源 |
|:---|:---|:---|
| `domains/solution/blackboard.py` | 2x | 今天 session (Step 2) |
| `domains/solution/task_builder.py` | 12x | 今天 session (Step 3) + 6/20 |
| `domains/solution/completion_handler.py` | 1x | 今天 session (Step 4) |
| `domains/solution/prompts/summarizer.md` | 1x | 今天 session (Step 1) |
| `domains/solution/__init__.py` | 1x | 6/20 session (a6112077) |
| `domains/solution/SKILL.md` | 7x | 6/20 session (5e67a492) |
| `domains/solution/frozen_spec.py` | 3x | 6/20 session (5e67a492) |

**3.2 新建文件 (2 个)**:

| 文件 | 数据源 |
|:---|:---|
| `domains/solution/normalize.py` | 6/20 session (5e67a492) |
| `domains/solution/orchestrator_agent.py` | 6/20 session (5e67a492) |

**3.3 其他改动 (17 个)**:
- prompts/pipeline_orchestrator.md, planner.md
- eval/ 目录下的测试和契约文件
- check_contract.py
- 等

**验证**:
- Solution Pro 单元测试
- 运行一次 Solution Pro 生成 final_result.json
- 验证 final_result.json 包含 covered_req_ids

**恢复方法**:
- 核心改动从今天的 session 日志中提取（数据完整）
- 其他改动从 6/20 session 中提取

---

### Phase 4: Ship Pro 完整域 (25 个文件)
**优先级**: 🔴 最高（完整域重建）  
**理由**: GitHub 上从未有过 Ship Pro，必须完整重建  
**预计时间**: 120 分钟

**4.1 核心代码 (8 个文件)**:

| 文件 | 数据源 |
|:---|:---|
| `domains/ship_pro/scripts/run_pipeline.py` | 6/20 session (5e67a492) |
| `domains/ship_pro/scripts/validate_input.py` | 6/19 session (多个) |
| `domains/ship_pro/prompts/architect.md` | 6/20 session (a6112077) |
| `domains/ship_pro/SKILL.md` | 6/20 session (5e67a492) |
| `domains/ship_pro/eval/gates.py` | 6/19 session (18cd5278) |
| `domains/ship_pro/eval/eval_code_checks.py` | 6/18 session (c5f378a2) |
| `domains/ship_pro/eval/test_eval_checks.py` | 6/18 session (c5f378a2) |
| `domains/ship_pro/eval/test_gates.py` | 6/19 session (18cd5278) |

**4.2 测试输出 (12 个文件)**:
- test_output/e2e_case1/
- test_output/loop_case1_tc09_todo/
- test_output/loop_case2_tc10_ecommerce/
- test_output/loop_case3_resume/
- test_output/v31_real_case/
- test_output/cancel_diagnosis.md

**4.3 文档 (5 个文件)**:
- docs/research/2026-06-18_ship_pro_v3_development_plan.md
- 其他 Ship Pro 相关设计文档

**验证**:
- 运行 Ship Pro 5 阶段管线
- 验证 Architect → Decomposer → Specifier → Reviewer → Packager 完整流程

**恢复方法**:
- 从 6/18-6/20 的 session 日志中提取完整文件内容
- 如果 session 日志不完整，从 test_output 和 DISCUSSIONS.md 中推断

---

### Phase 5: Scripts 和工具 (18 个文件)
**优先级**: 🟡 中  
**理由**: 辅助工具，不影响核心流程  
**预计时间**: 45 分钟

| 文件 | 改动次数 | 数据源 |
|:---|:---|:---|
| `scripts/pipeline_watcher.py` | 6x | 6/20 session |
| `scripts/pipeline_progress_notify.py` | 17x | 6/21 session |
| `scripts/golden_solution_pro_dry_run.py` | 1x | 今天 session |
| `scripts/start_solution_pro.py` | 1x | 6/20 session |
| 其他脚本 | - | 各个 session |

**验证**:
- 运行 golden_solution_pro_dry_run.py
- 验证 pipeline_watcher 可以监控进度

---

### Phase 6: Frontend (2 个文件)
**优先级**: 🟢 低  
**理由**: 前端不影响后端流程  
**预计时间**: 15 分钟

| 文件 | 改动次数 | 数据源 |
|:---|:---|:---|
| `frontend/backend/routers/status_v2.py` | 1x | 今天 session (Step 6) |
| `frontend/backend/routers/tasks_v2.py` | 1x | 6/20 session |

**验证**:
- 启动前端服务
- 访问状态页面，验证 JSON 渲染

---

### Phase 7: 测试和文档 (15+ 个文件)
**优先级**: 🟢 低  
**理由**: 测试和文档可以最后补  
**预计时间**: 30 分钟

- tests/golden/verify_golden_case.py
- domains/solution/eval/test_v6_improvements.py
- 各种契约文件 (cage/*.yaml)
- docs/design/ 下的设计文档

---

## 三、重建方法

### 方法 1: Session 日志提取（优先）
```bash
# 从 session 日志中提取最后一次 write 操作的完整内容
python3 scripts/extract_code.py --session SESSION_ID --file FILE_PATH
```

**适用场景**: 
- 今天的改动（session 日志完整）
- 6/18-6/20 的核心改动（大 session 文件）

### 方法 2: 手工重建（备选）
**适用场景**: 
- Session 日志不完整
- 只有 edit 操作，没有完整 write

**步骤**:
1. 从 RECOVERY_DATA.md 中找到代码片段
2. 从 DISCUSSIONS.md 中找到改动原因
3. 手工应用到 GitHub 基线代码

### 方法 3: 从 test_output 推断（最后手段）
**适用场景**:
- Ship Pro 的 prompt 文件（session 日志可能不完整）
- 从测试输出反推输入格式

---

## 四、验证清单

每个 Phase 完成后，执行对应的验证：

### Phase 1 验证
- [ ] path_config.py 单元测试通过 (27 个用例)
- [ ] pipeline_orchestrator.py 语法检查通过
- [ ] pipeline_watcher.py 可以启动

### Phase 2 验证
- [ ] Spec Pro 单元测试通过
- [ ] 运行 Spec Pro 生成 Living Spec
- [ ] Living Spec 包含 quality_report.json

### Phase 3 验证
- [ ] Solution Pro 单元测试通过
- [ ] 运行 Solution Pro 生成 final_result.json
- [ ] final_result.json 包含 covered_req_ids
- [ ] Summarizer 只写一个文件 (final_result.json)

### Phase 4 验证
- [ ] Ship Pro 5 阶段管线运行成功
- [ ] Architect 输出包含 modules 和 dependencies
- [ ] Decomposer 输出包含 work_packages
- [ ] Specifier 输出包含 acceptance_tests
- [ ] Reviewer 输出包含 issues 和 verdict
- [ ] Packager 输出包含 ship_package.json

### Phase 5 验证
- [ ] golden_solution_pro_dry_run.py 通过
- [ ] pipeline_watcher 可以监控进度
- [ ] pipeline_progress_notify 可以发送通知

### Phase 6 验证
- [ ] 前端服务启动成功
- [ ] 状态页面显示 JSON 渲染的报告

### Phase 7 验证
- [ ] 所有单元测试通过
- [ ] 所有契约笼子验证通过

---

## 五、时间估算

| Phase | 预计时间 | 累计时间 |
|:---|:---|:---|
| Phase 1: Core | 30 分钟 | 30 分钟 |
| Phase 2: Spec Pro | 45 分钟 | 75 分钟 |
| Phase 3: Solution Pro | 90 分钟 | 165 分钟 |
| Phase 4: Ship Pro | 120 分钟 | 285 分钟 |
| Phase 5: Scripts | 45 分钟 | 330 分钟 |
| Phase 6: Frontend | 15 分钟 | 345 分钟 |
| Phase 7: Tests | 30 分钟 | 375 分钟 |
| **总计** | **6 小时 15 分钟** | - |

**建议**: 分 2-3 天完成，每天 2-3 小时。

---

## 六、风险和缓解

### 风险 1: Session 日志不完整
**概率**: 中  
**影响**: 无法提取完整文件内容  
**缓解**: 
- 优先处理今天的改动（session 日志最完整）
- 对于不完整的文件，使用 RECOVERY_DATA.md 中的代码片段手工重建

### 风险 2: Ship Pro 代码量大
**概率**: 高  
**影响**: 重建时间长，容易出错  
**缓解**: 
- 先重建核心 8 个文件，验证管线可运行
- 测试输出和文档可以后面补

### 风险 3: 依赖关系复杂
**概率**: 中  
**影响**: 某个 Phase 失败导致后续无法进行  
**缓解**: 
- 严格按依赖顺序执行
- 每个 Phase 完成后立即验证

---

## 七、下一步行动

1. **立即开始 Phase 1** (Core 基础设施)
   - 从今天的 session 日志中提取 path_config.py
   - 验证 27 个单元测试通过

2. **准备 Phase 2 的材料**
   - 从 DISCUSSIONS.md 中收集 Spec Pro V4.1 的设计决策
   - 从 6/20 session 日志中定位 coordinator.py 的改动

3. **通知忠礼**
   - 确认重建计划
   - 询问是否有其他优先事项
