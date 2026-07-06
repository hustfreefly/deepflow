# Spec Pro 系统性修复计划 v1.0

> 基于 4 Agent 并行审计报告（数据流 + 边界条件 + Prompt契约 + 下游消费）
> 共发现 30 个去重后问题（8 P0 + 12 P1 + 10 P2）

---

## 一、根因分析（不是逐个修 bug，而是找根因）

30 个问题归纳为 **5 个根因**：

### RC1: Prompt 指令缺乏显式写操作（影响 3 个 P0）

**根因**: coordinator.py 的 init/collecting 阶段指令中，部分 Step 只描述了"数据应该是什么格式"，但没有给出 `write` 或 `exec` 命令让 Orchestrator Worker 实际创建文件。

**受影响问题**:
- P0-4: Round 1 缺 round_result.json 写指令
- P0-5: collecting 分支 C 缺 round_result.json 写指令  
- P0-5b: conversation_log.json 缺更新命令

### RC2: Prompt-Code 数据契约不一致（影响 3 个 P0 + 2 个 P1 + 4 个 P2）

**根因**: 7 个 Worker Prompt 各自定义了输入/输出 JSON schema，但 Python 代码（merge_spec.py / coordinator.py）对这些 schema 的假设与 Prompt 定义不完全对齐。没有一个统一的 Schema 定义文件。

**受影响问题**:
- P0-1: 4 个 confirmed 字段（benchmark_references 等）Prompt 有但代码无
- P0-2: meta_signals 缺 directive_stop_asking 字段
- P0-3: quality 对象结构 proposal vs summary/done 不一致
- P1-20: dimensions 数组 vs 字典无代码保障
- P1-21: user_directives 嵌套层级不一致
- P2-22/23/24/25: parse.md 缺字段、success_metrics 格式、问题数量矛盾、harness nullable

### RC3: 防御性编程不足（影响 2 个 P0 + 7 个 P1 + 2 个 P2）

**根因**: Python 代码假设输入数据格式正确，缺乏类型校验和边界处理。

**受影响问题**:
- P0-6: Session ID 碰撞（md5(time)[:8]）
- P0-7: ParseWorker fallback 不创建 living_spec.json
- P0-8: 损坏字段类型崩溃
- P1-14: safety_stop 后仍可调用
- P1-15: process_guard 负 delta 语义
- P1-17: fallback 数据结构不完整
- P1-18/19: API JSON 损坏未处理
- P2-29: NaN 序列化
- P2-30: 空 dict 接受

### RC4: Spec Pro → Solution Pro 下游消费断层（影响 3 个 P0 + 4 个 P1 + 2 个 P2）

**根因**: Spec Pro 生成了丰富的元数据（route_recommendation、user_directives、inferred_pending、layer2_hints、anti_patterns、requirement_annotations），但 Solution Pro 只消费了 confirmed 层的 10 个核心字段 + guardrails + focus_areas。元数据层的传递完全断裂。

**受影响问题**:
- P0-9: route_recommendation 零消费
- P0-10: user_directives 不传递
- P0-11: inferred_pending 忽略
- P1-12: requirement_annotations 无消费者
- P1-13: guardrails 传递不完整
- P1-5a: layer2_hints 未消费
- P1-6a: anti_patterns 未消费
- P2-8: hints 展平语义丢失
- P2-9: executive_summary vs task_builder 不一致

### RC5: 代码冗余（影响 1 个 P1 + 2 个 P2）

**受影响问题**:
- P1-16: process_guard 双份实现
- P2-26: user_confirmation.md 扩展名
- P2-27: Round 1 自引用循环

---

## 二、系统性修复方案（5 个根因 → 5 个修复策略）

### 策略 S1: 引入 Schema 契约层（解决 RC2）

**核心思路**: 创建一个 `schemas/` 目录，用 Python dict 定义所有关键 JSON 文件的 Schema。Prompt 和 Code 都从这个 Schema 生成或校验。

**具体行动**:
1. 创建 `domains/spec_pro/schemas.py`，定义：
   - `LIVING_SPEC_SCHEMA` — confirmed 层完整字段（含 user_directives）
   - `ROUND_RESULT_SCHEMA` — 统一 quality 对象结构（所有 action 模式都用完整格式）
   - `RESPONSE_SCHEMA` — parse_response 输出格式（含 meta_signals 完整字段）
   - `QUALITY_REPORT_SCHEMA` — assess 输出格式
2. 在 `merge_spec.py` 入口加 schema 校验
3. 更新 7 个 Prompt 的 schema 示例与 schemas.py 对齐
4. 删除 parse_response.md 中 5 个不存在的 confirmed 字段映射（benchmark_references 等），统一用 user_directives

**解决的问题**: P0-1, P0-2, P0-3, P1-20, P1-21, P2-22, P2-23, P2-24, P2-25

### 策略 S2: 统一 Prompt 写入协议（解决 RC1）

**核心思路**: 在 coordinator.py 的每个阶段指令中，为每个需要写入的文件添加显式的 `write` 或 `exec` 命令。

**具体行动**:
1. init 阶段 Step 4 后添加: `使用 write 工具将 round_result.json 写入 {Blackboard}/spec/round_result.json`
2. init 阶段末尾添加 Step 7: conversation_log 更新命令
3. collecting 分支 C 末尾添加 round_result.json 写指令
4. collecting Step 7 添加 conversation_log 更新命令

**解决的问题**: P0-4, P0-5

### 策略 S3: 防御性编程加固（解决 RC3）

**核心思路**: 对每个 Python 模块的入口和关键路径添加类型校验和边界处理。

**具体行动**:
1. `_generate_session_id()` 改用 `uuid.uuid4().hex[:16]`
2. `worker_fallback.py` ParseWorker fallback 补创建最小 living_spec.json
3. `merge_confirmed()` 每个 `setdefault()` 前加 `isinstance()` 校验
4. `build_next_round_task()` 开头检查 `self.state == KILLED`
5. `spec_pro_api.py` 所有 `json.load()` / `json.loads()` 加 try/except
6. `worker_fallback.py` FALLBACKS 补全缺失字段
7. `process_guard.py` 负 delta 分支 + NaN 校验

**解决的问题**: P0-6, P0-7, P0-8, P1-14, P1-15, P1-17, P1-18, P1-19, P2-29, P2-30

### 策略 S4: 下游消费 Adapter（解决 RC4）

**核心思路**: 在 frozen_spec.py 中建立统一的 `build_context_from_living_spec()` 函数，将 Spec Pro 所有产出（含元数据层）结构化透传。task_builder.py 改为消费这个统一 context。

**具体行动**:
1. `frozen_spec.py` 新增 `build_living_spec_context(living_spec)` 函数：
   - 提取 route_recommendation → frozen_spec.top_level
   - 提取 user_directives → frozen_spec.deliberately_omitted_dimensions
   - 提取 inferred_pending → frozen_spec.pending_inferences
   - 提取 layer2_hints → frozen_spec.layer2_hints（保持结构）
   - 提取 anti_patterns → frozen_spec.anti_patterns
   - 提取 requirement_annotations → 保持不变（但后续可消费）
2. `task_builder.py` 各 Worker context 注入 deliberately_omitted_dimensions
3. 移除 hints 展平为字符串 REQ 的逻辑

**解决的问题**: P0-9, P0-10, P0-11, P1-5a, P1-6a, P1-12, P1-13, P2-8, P2-9

### 策略 S5: 代码清理（解决 RC5）

**具体行动**:
1. 删除 `utils.py::check_process_guard()`（保留 process_guard.py 为唯一入口）
2. `user_confirmation.md` → `user_confirmation.json`
3. Round 1 QuestionWorker 删除自引用读取

**解决的问题**: P1-16, P2-26, P2-27

---

## 三、执行顺序

| 阶段 | 策略 | 工作量 | 解决问题数 | 依赖 |
|------|------|--------|-----------|------|
| Phase 1 | S1 Schema 契约层 | 3h | 9 | 无 |
| Phase 2 | S2 Prompt 写入协议 | 1h | 2 | S1（需要统一 quality schema） |
| Phase 3 | S3 防御性编程 | 2h | 10 | 无 |
| Phase 4 | S4 下游 Adapter | 3h | 9 | S1（需要 user_directives schema） |
| Phase 5 | S5 代码清理 | 30min | 3 | 无 |

**总计**: ~10h，解决 30/30 问题

---

## 四、不做的事（明确边界）

- ❌ Direct Driver 架构迁移（当前嵌套 spawn 能跑，收益不抵成本）
- ❌ 版本号统一（已文档化在 VERSION.md，不需要代码改动）
- ❌ 并发文件锁（单用户场景，并发风险极低）

---

## 五、验证标准

每个 Phase 完成后：
1. 运行现有测试 + 新增对应测试
2. 模拟完整 3 轮对话流程验证端到端
3. 检查无回归（所有之前修复的功能仍正常）
