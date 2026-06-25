# Ship Pro AI Native 方案 V2 评审总结

> **评审日期**: 2026-06-25  
> **评审轮次**: 第二轮（V2）  
> **评审专家**: 4 位

---

## 综合评分

| 专家 | V1 评分 | V2 评分 | 提升 | P0/P1 修复率 | 建议 |
|------|--------|--------|------|-------------|------|
| AI Native 架构师 | 7.2 | **8.7** | +1.5 | 10/10 (100%) | ✅ 进入实施 |
| OpenClaw 平台专家 | 6.5 | **8.5** | +2.0 | 5/5 (100%) | ✅ 进入实施 |
| 管线工程专家 | 5.5 | **8.0** | +2.5 | 6/6 (100%) | ✅ 进入实施 |
| 可靠性工程专家 | 4.5 | **8.0** | +3.5 | 6/7 (86%)¹ | ✅ 进入实施 |
| **平均** | **5.9** | **8.3** | **+2.4** | **27/28 (96%)** | **全票通过** |

> ¹ 可靠性专家第 7 个问题（并行阶段失败处理）部分修复，降级为 P2

---

## 核心改进（V1 → V2）

### 1. 代码级护栏（修复所有 P0 问题）
- `validate-plan --required` — 代码级强制关键阶段不可跳过
- `check-retry-limit` — 代码级强制重试上限
- `check-budget` — 代码级强制时间/token 预算
- `can-parallel` — 代码级判断并行安全性

### 2. 三层验证机制（修复质量门控退化）
- Layer 1: `validate-format`（Pydantic 格式校验）
- Layer 2: `validate-quality`（Python gate 语义校验）
- Layer 3: LLM 自主评估（质量维度评分）

### 3. 显式依赖管理（修复数据依赖不透明）
- `stage-dependencies.json` — 单文件声明所有阶段依赖
- `build-prompt` 自动注入前置阶段输出
- `list-dependencies` 供调试

### 4. 五层可靠性架构（从"裸奔"到"工程级"）
- 第一层：Session 超时（Worker 300s / Orchestrator 1800s）
- 第二层：预算检查（代码护栏）
- 第三层：状态安全（枚举校验 + 原子写入 + .heartbeat）
- 第四层：断点恢复（resume-context + 启动强制检查）
- 第五层：回滚兜底（版本标记 + V4 resume 兼容）

### 5. 上下文管理（修复注意力崩溃）
- `compact-history` — 每 2 阶段压缩一次
- `resume-context` — 断点续接完整上下文

---

## 剩余问题（均为 P2/P3，不阻塞实施）

| # | 来源 | 严重度 | 问题 | 建议 |
|---|------|--------|------|------|
| 1 | 架构师 | P2 | 命令数量不一致（标题 12 vs 实际 16） | 更新标题 |
| 2 | 架构师 | P2 | compact-history 实现机制未明确 | 明确为纯提取 |
| 3 | 架构师 | P2 | Judge Worker 失败处理未定义 | 增加 fail 分支 |
| 4 | 架构师 | P2 | validate-quality 与 gate 函数关系需澄清 | 明确硬/软约束分工 |
| 5 | 架构师 | P2 | build-prompt --context-file 格式未定义 | 定义为 JSON |
| 6 | 架构师 | P2 | 并行执行 sessions_yield 语义不明确 | 默认串行，后续优化 |
| 7 | 平台专家 | P2 | maxSpawnDepth 未显式确认 | 实施前 5 秒检查 |
| 8 | 平台专家 | P2 | cwd 硬编码为绝对路径 | 改用 DEEPFLOW_HOME 变量 |
| 9 | 平台专家 | P2 | exec 环境约束仅在 prompt 中 | 可接受，强化注释 |
| 10 | 管线专家 | P2 | validate-quality 对自创阶段 gate_fn 映射 | fallback 到 format-only |
| 11 | 管线专家 | P2 | compact-history 信息丢失边界 | 改为字段级摘要 |
| 12 | 管线专家 | P2 | Judge Worker 失败降级路径 | Orchestrator 自评 fallback |
| 13 | 管线专家 | P3 | 并行阶段 blackboard 文件写入冲突 | 未来引入文件锁 |
| 14 | 可靠性专家 | P2 | compact-history 可能丢失失败细节 | 保留最近 2 阶段完整记录 |
| 15 | 可靠性专家 | P2 | 并行阶段部分失败策略模糊 | 增加具体策略 |
| 16 | 可靠性专家 | P2 | write-status 时序窗口 | resume-context 增加文件扫描 |
| 17 | 可靠性专家 | P2 | Judge Worker 评估可靠性 | 与 Python gate 交叉验证 |

**统计**: P2 × 16, P3 × 1 — 全部不阻塞实施

---

## 实施建议（综合 4 位专家）

### 优先级排序
1. **stage-dependencies.json** — 所有护栏命令的基础，最先定义
2. **io_helper.py 护栏命令** — validate-plan, check-retry-limit, can-parallel, validate-quality
3. **io_helper.py I/O 命令** — read-input, write-status, write-completed
4. **io_helper.py 恢复/调试命令** — resume-context, compact-history, list-dependencies
5. **Orchestrator Prompt** — 集成所有命令的使用规范
6. **SKILL.md V5.0** — 入口守卫 + 完整步骤

### 验证策略
1. 单阶段测试（architect 阶段独立运行）
2. 多阶段串行测试（5 阶段串行全流程）
3. 断点恢复测试（中途 kill → 重启 → 从断点继续）
4. 超时保护测试（Worker 300s / Orchestrator 1800s）
5. 回滚测试（AI Native → V4 兼容）

### 实施前 5 秒检查
- `openclaw config get maxSpawnDepth` 确认 ≥ 2
- `cwd` 改用 `DEEPFLOW_HOME` 变量注入

---

## 结论

**4/4 专家全票通过，V2 方案可进入实施阶段。**

V1 → V2 核心进化：
- 从"LLM 即兴发挥"到"代码护栏内的 AI Native"
- 从"可靠性裸奔"到"五层防护"
- 从"隐式数据传递"到"显式依赖声明"
- 从"prompt 约束"到"代码强制"

平均评分 **5.9 → 8.3**（+2.4），P0/P1 修复率 **96%**，剩余 17 个问题均为 P2/P3。

---

*总结完成 | 2026-06-25*
