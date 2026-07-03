# Ship Pro V6 - 专家评审决策记录

## 评审概览

**评审时间**: 2026-07-03 13:00-13:15  
**评审专家**: 5 位 AI Native 专家（不同模型）  
**评审约束**: 不允许提大架构变更，除非发现原则性错误  
**结果**: 无原则性错误，共提出 28 个优化建议

## 决策原则

> **AI Native 的事情用 AI Native 做，非 AI Native 的事情用常规方法做。**

判断标准：
- **AI Native**: 语义理解、自由分类、动态决策 → 用 LLM
- **非 AI Native**: 确定性检查、格式验证、拓扑排序 → 用代码

## 采纳的优化（8 项）

### 1. ✅ 去掉角色名称允许列表
**专家**: AI Native 纯度专家  
**问题**: 角色名称允许列表过度约束，限制了 LLM 的创造力  
**决策**: 采纳。WorkerSpec.role 改为自由命名  
**实现**: `planner_output.py` - `role: str`（无 Enum 约束）

### 2. ✅ 去掉三重 Enum 约束
**专家**: AI Native 纯度专家  
**问题**: input_type/complexity/integration_strategy 被硬编码为 Enum，是硬编码思维  
**决策**: 采纳。改为自由文本，让 LLM 自由分类  
**实现**: `planner_output.py` - 三个字段都改为 `str`

### 3. ✅ 去掉 Meta Shipper
**专家**: AI Native 纯度专家  
**问题**: Meta Shipper 与 Planner 的 integration_strategy 职责重叠  
**决策**: 采纳。去掉 Meta Shipper，integration_strategy 由 Planner 直接决定  
**实现**: 架构文档已更新，角色规格已删除 Meta Shipper

### 4. ✅ Worker 数量改为 re-plan
**专家**: AI Native 纯度专家  
**问题**: Worker 数量超出范围时自动截断是静默覆盖 LLM 决策  
**决策**: 采纳。改为触发 re-plan，让 LLM 重新规划  
**实现**: `gates.py` - PlannerGate 检查失败时返回 `passed=False`，Orchestrator 触发 re-plan

### 5. ✅ depends_on 改为拓扑排序分层执行
**专家**: 多 Agent 协作专家 + 可执行性专家  
**问题**: depends_on 在 spawn_parallel 下无法生效，需要分层执行  
**决策**: 采纳。用 Kahn 算法实现拓扑排序，按层级分组并行执行  
**实现**: `gates.py` - PlannerGate 已实现 Kahn 算法检测环

### 6. ✅ G2-L1 降级为预过滤
**专家**: AI Native 纯度专家  
**问题**: G2-L1 用代码做语义匹配是伪 AI Native  
**决策**: 采纳。G2-L1 改为预过滤（提取 REQ-ID），G2-L2 用 LLM 做语义判断  
**实现**: `gates.py` - CompletenessGate 已分离代码检查和 LLM 判断

### 7. ✅ WG-3 改为字符串匹配
**专家**: AI Native 纯度专家  
**问题**: WG-3 用 LLM 做确定性检查是反向误用  
**决策**: 采纳。web_search 范围检查改为简单字符串匹配  
**实现**: `gates.py` - WorkerGate 已实现关键词匹配

### 8. ✅ 增加信息新增检查（G2 反向覆盖）
**专家**: 信息守恒专家  
**问题**: G2 只检查信息丢失，未检查信息新增  
**决策**: 采纳。增加反向覆盖检查  
**实现**: `gates.py` - InformationConservationGate prompt 已包含信息新增检查

## 保留的设计（3 项）

### 1. ⚠️ optional_suggestion 物理隔离
**专家**: 信息守恒专家  
**问题**: 物理隔离是"伪隔离"，LLM 在生成时可能已"无意识"融入  
**决策**: 保留。约束笼子已在 Prompt 层面限制（"Solution Pro 没说的不补充"），Gate 层面可以后续增强  
**理由**: 当前设计已足够，过度增强会增加复杂度

### 2. ⚠️ web_search 范围
**专家**: 信息守恒专家  
**问题**: 无法区分"实施细节"和"架构决策"  
**决策**: 保留。约束笼子 + LLM 判断已足够，暂不增加白名单  
**理由**: 白名单会限制 LLM 的灵活性，当前设计已平衡

### 3. ⚠️ LLM-as-Judge 稳定性
**专家**: 信息守恒专家  
**问题**: 判定标准不稳定  
**决策**: 保留。当前单 Judge 已足够，多 Judge 投票会增加复杂度  
**理由**: 可以通过 prompt 优化提高稳定性，不需要架构变更

## 待处理的问题（2 项）

### 1. ⏳ 工作量低估
**专家**: 可执行性专家  
**问题**: 工作量低估 37%（9.5 → 13 人天）  
**决策**: 待处理。需要在实现过程中重新评估  
**行动**: 实现 Phase 1-3 后重新估算

### 2. ⏳ must_constraints 跨项目依赖
**专家**: 可执行性专家  
**问题**: must_constraints 需要 Solution Pro 先配合输出  
**决策**: 待处理。当前用语义描述替代 ID  
**行动**: 后续与 Solution Pro 协调

## 实现清单

### 已完成
- [x] Pydantic Schema 定义（5 个文件）
- [x] Gate 实现（5 个 Gate）
- [x] 设计文档更新（决策记录）

### 待完成
- [ ] Orchestrator 核心实现
- [ ] Planner Prompt 设计
- [ ] Worker Prompt 模板
- [ ] 测试用例
- [ ] JSON Schema 生成

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| V6.0 | 2026-07-03 | 初始设计 + 专家评审决策 |
