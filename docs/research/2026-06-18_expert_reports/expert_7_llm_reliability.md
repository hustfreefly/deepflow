# 专家 7：LLM 可靠性工程师报告

> **角色**: LLM-as-Compiler 可行性评估  
> **日期**: 2026-06-18  
> **评估对象**: Ship Pro 从"确定性编译器"改为"LLM 引导编译器"

---

## 执行摘要

**总体评估**: ⚠️ 有条件可行，但需要严格的 guardrails

修正方案将 Ship Pro 从 1048 行确定性 Python 改为 LLM 引导编译器，这是一个**高风险但合理**的决策。LLM 在解析非结构化/半结构化数据方面确实有优势，但必须认识到：

- ✅ LLM 可以处理格式多样性（5 种 final_result 结构）
- ⚠️ 输出稳定性需要多层保障（schema validation + retry）
- ❌ 不能完全放弃确定性逻辑（核心组装必须确定性）

**实施信心评分**: 6/10

---

## 一、实际数据分析

### 1.1 三种 final_result.json 结构对比

| 维度 | 跨境算力中转站 | 智能简历系统 | 电商订单系统 |
|------|---------------|-------------|-------------|
| **架构信息路径** | `architecture.core_components` | `final_solution.detailed_solution.architecture.components` | `architecture`（扁平对象） |
| **组件表示** | 数组，每项含 name/component/role/deployment/license | 数组，每项含 id/name/summary/tier | 16 个独立字段（api_gateway/microservices_framework/cache 等） |
| **实施计划** | ✅ `implementation_plan.phases`（3 phases，有 tasks） | ✅ `implementation.phases`（3 phases，有 deliverables） | ❌ 无（只有 timeline 字符串） |
| **技术栈位置** | 分散在 core_components 的 component 字段 | 分散在 components 的 summary 文本中 | 集中在 architecture 对象的字段值中 |
| **数据密度** | 高（~70KB，71 需求覆盖） | 中（~15KB，6 需求覆盖） | 中（~20KB，18 需求覆盖） |

### 1.2 提取难度评估

**跨境算力（难度：低）**
```json
// 路径明确，结构规整
architecture.core_components[0] = {
  "name": "API网关层",
  "component": "New API",
  "role": "核心引擎：多供应商聚合...",
  "deployment": "Docker on Railway"
}
```
→ LLM 可以直接提取，无需推理

**智能简历（难度：中）**
```json
// 信息压缩在 summary 文本中
components[1] = {
  "name": "JD解析与匹配引擎",
  "summary": "三层匹配：关键词(35%) + 语义(45%) + 行业术语(20%)..."
}
```
→ LLM 需要从 summary 文本中解析技术细节（权重公式、模型名称）

**电商订单（难度：高）**
```json
// 扁平结构，技术栈是字段值
architecture = {
  "api_gateway": "APISIX",
  "cache": "Redis Cluster + Caffeine + 布隆过滤器",
  "database": "MySQL 8.0 + ShardingSphere-JDBC + 半同步复制"
}
```
→ LLM 需要理解"Redis Cluster + Caffeine + 布隆过滤器"是三层缓存架构，拆分成组件

### 1.3 关键发现

1. **格式多样性是真实的**：5 种案例有 5 种不同结构，确定性编译器需要写 5 套解析逻辑
2. **信息密度差异大**：从 15KB 到 70KB，LLM context 不是问题，但信息提取难度不同
3. **隐式知识存在**：简历系统的"三层匹配 35/45/20"在 summary 文本中，需要理解才能提取
4. **部分案例缺少 implementation_plan**：LLM 需要自己生成 Work Package 拆分

---

## 二、Q1-Q5 评估与建议

### Q1: Ship Pro 用 LLM 还是确定性编译器？

**建议**: **混合架构** — LLM 提取 + 确定性组装

```
┌─────────────────────────────────────────────────────────────┐
│                    Ship Pro 混合架构                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ final_result │───▶│  LLM 提取层  │───▶│ 中间表示 IR  │  │
│  │    .json     │    │ (理解+提取)  │    │  (结构化)    │  │
│  └──────────────┘    └──────────────┘    └──────┬───────┘  │
│                                                  │          │
│                                                  ▼          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ ship_package │◀───│  确定性组装  │◀───│  WP 生成规则 │  │
│  │   .json      │    │   (Python)   │    │  (可测试)    │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**理由**:
1. **LLM 擅长**：从不统一的 JSON 结构中识别"这是组件信息"、"这是技术栈"
2. **确定性擅长**：按规则生成 WP ID、计算依赖关系、验证 schema 合规
3. **分离好处**：LLM 层可替换（换模型/换 prompt），组装层可测试（单元测试覆盖）

**实施细节**:
- LLM 输出**中间表示 (IR)**，不是最终 ship_package
- IR 有严格 schema（Pydantic 验证）
- 确定性代码从 IR 生成 ship_package.json

**信心评分**: 8/10

---

### Q2: 输出 ship_package.json 的格式稳定性如何保证？

**建议**: 三层保障机制

#### 第一层：Constrained Decoding（原生结构化输出）

```python
# 使用 OpenAI/Gemini 的 native structured output
response = client.chat.completions.create(
    model="gpt-4o",
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "ship_pro_ir",
            "strict": True,
            "schema": IR_SCHEMA
        }
    },
    messages=[...]
)
```

**效果**: 语法层面 100% schema 合规（constrained decoding 屏蔽不合规 token）

#### 第二层：Application-Side Validation（业务逻辑验证）

```python
from pydantic import BaseModel, validator

class WorkPackage(BaseModel):
    id: str
    title: str
    phase: int
    estimated_hours: int
    dependencies: list[str]
    acceptance_criteria: list[AcceptanceCriterion]
    
    @validator('id')
    def validate_id_format(cls, v):
        if not v.startswith('WP-'):
            raise ValueError('WP ID must start with WP-')
        return v
    
    @validator('estimated_hours')
    def validate_hours_range(cls, v):
        if v < 1 or v > 500:
            raise ValueError(f'Unreasonable hours: {v}')
        return v

class ShipPackageIR(BaseModel):
    work_packages: list[WorkPackage]
    total_estimated_hours: int
    critical_path: list[str]
    
    @validator('total_estimated_hours')
    def validate_total(cls, v, values):
        wps = values.get('work_packages', [])
        computed = sum(wp.estimated_hours for wp in wps)
        if abs(v - computed) > 10:
            raise ValueError(f'Total mismatch: {v} vs computed {computed}')
        return v
```

#### 第三层：Retry with Corrective Feedback

```python
MAX_RETRIES = 3

for attempt in range(MAX_RETRIES):
    try:
        ir = extract_with_llm(final_result)
        validated_ir = ShipPackageIR.parse_obj(ir)
        break
    except ValidationError as e:
        if attempt == MAX_RETRIES - 1:
            raise
        # 将错误反馈给 LLM 重试
        error_feedback = f"Previous output failed validation:\n{e}\nPlease fix."
        messages.append({"role": "assistant", "content": previous_output})
        messages.append({"role": "user", "content": error_feedback})
```

**预期效果**:
- 第一层：解决 95% 的语法错误（JSON 格式、字段类型）
- 第二层：捕获业务逻辑错误（工时不合理、依赖循环）
- 第三层：修复剩余 5% 的问题

**信心评分**: 7/10

---

### Q3: 需要哪些 guardrails？

**建议**: 五类 guardrails

#### 3.1 输入 Guardrails

| Guardrail | 目的 | 实现 |
|-----------|------|------|
| 文件大小限制 | 防止 context 溢出 | final_result > 100KB 时截断/分块 |
| JSON 合法性检查 | 防止无效输入 | `json.loads()` 预检查 |
| 关键字段存在性 | 防止空输入 | 检查 `architecture` 或 `final_solution` 存在 |

#### 3.2 提取 Guardrails

| Guardrail | 目的 | 实现 |
|-----------|------|------|
| 组件数量范围 | 防止幻觉/遗漏 | 检查 3 ≤ components ≤ 30 |
| 技术栈可验证性 | 防止虚构技术 | 组件名必须在已知技术列表或允许自由文本但标记 |
| 工时合理性 | 防止离谱估算 | 单 WP 工时 ∈ [4, 200] 小时 |

#### 3.3 输出 Guardrails

| Guardrail | 目的 | 实现 |
|-----------|------|------|
| Schema 完整性 | 防止字段缺失 | Pydantic strict mode |
| 依赖关系有效性 | 防止悬空引用 | 所有 dependencies 必须指向存在的 WP ID |
| 阶段连续性 | 防止阶段跳跃 | phases 必须从 1 开始，连续递增 |

#### 3.4 一致性 Guardrails

| Guardrail | 目的 | 实现 |
|-----------|------|------|
| 需求覆盖检查 | 防止遗漏需求 | RTM 中的 REQ-ID 必须被 WP 覆盖 |
| 技术栈一致性 | 防止自相矛盾 | WP 中的技术必须与 architecture 提取的一致 |

#### 3.5 降级 Guardrails

| Guardrail | 目的 | 实现 |
|-----------|------|------|
| LLM 超时 | 防止无限等待 | 30 秒超时 → 重试 → 降级到规则提取 |
| 多次失败 | 防止死循环 | 3 次验证失败 → 降级到确定性编译器 |
| 置信度阈值 | 防止低质量输出 | LLM 自评估置信度 < 0.7 → 标记人工审核 |

**信心评分**: 8/10

---

### Q4: 失败时的降级策略是什么？

**建议**: 三级降级机制

```
┌─────────────────────────────────────────────────────────────┐
│                    降级决策树                                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  LLM 提取成功 ──▶ Schema 验证通过 ──▶ 输出 ship_package    │
│       │                    │                                │
│       │                    ▼                                │
│       │              验证失败                               │
│       │                │    │                               │
│       │                │    ▼                               │
│       │                │  重试 ≤3 次 ──▶ 成功 ──▶ 输出     │
│       │                │       │                           │
│       │                │       ▼                           │
│       │                │   重试耗尽                        │
│       │                │       │                           │
│       ▼                ▼       ▼                           │
│  LLM 超时/错误    无法提取    ──▶ 降级 Level 1             │
│                                                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Level 1: 规则提取（部分确定性）                      │    │
│  │ - 尝试已知路径（architecture.core_components 等）   │    │
│  │ - 成功 ──▶ 输出（标记 auto_extracted=true）         │    │
│  │ - 失败 ──▶ Level 2                                  │    │
│  └────────────────────────────────────────────────────┘    │
│                          │                                  │
│                          ▼                                  │
│  ┌────────────────────────────────────────────────────┐    │
│  │ Level 2: 最小化输出 + 人工审核标记                   │    │
│  │ - 输出骨架 ship_package（只有 WP 标题，无细节）      │    │
│  │ - 标记 needs_human_review=true                      │    │
│  │ - 通知用户手动补充                                  │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**降级触发条件**:

| 场景 | 触发 | 降级级别 |
|------|------|---------|
| LLM API 超时 (>30s) | 网络/服务问题 | Level 1 |
| LLM 返回空/无效 JSON | 模型拒绝/错误 | Level 1 |
| Schema 验证失败 3 次 | 模型无法理解任务 | Level 1 |
| 规则提取也失败 | 完全未知的格式 | Level 2 |
| 置信度 < 0.5 | 模型不确定 | Level 2 |

**关键原则**: 
- **永远有输出**：即使降级，也输出骨架，不让下游 Super Loop 空等
- **显式标记**：降级输出必须标记 `degraded: true`，便于追踪
- **快速失败**：不要无限重试，3 次够了

**信心评分**: 7/10

---

### Q5: 代码量和维护成本的变化？

**建议**: 代码量减少，但维护复杂度增加

#### 代码量对比

| 组件 | 当前（确定性） | 修正后（混合） | 变化 |
|------|--------------|---------------|------|
| 解析逻辑 | ~400 行（5 种格式 × 80 行） | ~150 行（LLM prompt + IR schema） | -62% |
| 组装逻辑 | ~500 行 | ~300 行（IR → ship_package） | -40% |
| 验证逻辑 | ~50 行 | ~200 行（Pydantic + guardrails） | +300% |
| 降级逻辑 | 0 行 | ~100 行 | 新增 |
| Prompt 工程 | 0 行 | ~100 行（版本化的 prompt 模板） | 新增 |
| **总计** | ~1048 行 | ~850 行 | -19% |

#### 维护成本对比

| 维度 | 当前（确定性） | 修正后（混合） |
|------|--------------|---------------|
| **新增格式支持** | 写新解析器（80 行/格式） | 调整 prompt（通常 < 20 行） |
| **输出格式变更** | 改代码 + 测试 | 改 Pydantic schema + 测试 |
| **模型升级** | 无影响 | 可能需要调整 prompt |
| **调试难度** | 低（确定性可复现） | 中（LLM 输出不完全可复现） |
| **测试覆盖** | 容易（mock 输入 → 断言输出） | 需要 LLM mock + 集成测试 |

#### 隐性成本

1. **Prompt 版本管理**: prompt 是代码，需要版本控制 + 回归测试
2. **LLM 成本**: 每次运行消耗 token（~33KB 输入 + ~10KB 输出 ≈ $0.01-0.05/次）
3. **延迟**: LLM 调用增加 5-15 秒（确定性编译器 < 1 秒）
4. **可观测性**: 需要记录 LLM 输入/输出用于调试

**结论**: 代码量略减，但**维护复杂度增加**。好处是**扩展性提升**（新格式不需要写代码）。

**信心评分**: 6/10

---

## 三、盲点与风险

### 3.1 未解决的问题

#### 问题 1: 信息丢失风险

LLM 提取可能遗漏关键细节。例如：

```json
// 简历系统的组件 summary
"summary": "三层匹配：关键词(35%) + 语义(45%) + 行业术语(20%)。中文自动切换text2vec-base-chinese。"
```

LLM 可能只提取"三层匹配"，遗漏具体的权重比例 (35/45/20) 和模型名称 (text2vec-base-chinese)。

**缓解**: Prompt 明确要求"提取所有数字、比例、模型名称"，并在 IR 中设置对应字段。

#### 问题 2: 幻觉风险

LLM 可能"补充"不存在的组件或技术。例如：

- 输入：6 个组件
- 输出：7 个组件（LLM "合理推测"了一个监控组件）

**缓解**: 验证层检查"输出组件数 ≥ 输入组件数"，如果多了，标记异常。

#### 问题 3: 不一致风险

同一个项目，两次运行可能产生不同的 WP 拆分。

**缓解**: 
- 使用 temperature=0（确定性采样）
- 缓存 LLM 输出（相同输入 → 相同输出）
- 接受"合理范围内的不一致"

### 3.2 最大风险

**风险**: `_ship_pro_hints` 约定增加 Solution Pro 脆弱性

上下文文件提到让 Solution Pro 输出 `_ship_pro_hints` 字段，指向关键数据位置。这有隐患：

1. Solution Pro 的 prompt 已经很长，增加字段增加失败概率
2. hints 本身可能错误（LLM 生成的导航信息不可靠）
3. 增加了两个系统的耦合度

**建议**: 
- `_ship_pro_hints` 作为**可选**字段，不作为强依赖
- Ship Pro 的 LLM 提取层应该能独立工作（无 hints 也能提取）
- 如果 hints 存在，用来**验证**提取结果，而不是**指导**提取过程

---

## 四、替代方案

### 方案 A: 纯确定性编译器（当前方案）

```
优点: 100% 可复现，< 1 秒，无 LLM 成本
缺点: 每种新格式需要写解析器（80 行/格式）
适用: 格式稳定，变化少
```

### 方案 B: 纯 LLM 编译器（修正方案）

```
优点: 灵活，新格式无需改代码
缺点: 不可复现，5-15 秒，有 LLM 成本，需要 guardrails
适用: 格式多样，变化频繁
```

### 方案 C: 混合架构（推荐）

```
优点: 兼顾灵活性和可靠性，核心逻辑可测试
缺点: 架构复杂度高，需要维护两套逻辑
适用: DeepFlow 当前场景
```

### 方案 D: 渐进式方案（我的建议）

```
Phase 1: 保持确定性编译器，但重构为"插件式"
         - 每种格式一个解析器（Plugin）
         - 新格式 = 新 Plugin（不需要改核心）
         
Phase 2: 增加 LLM 提取层作为"兜底"
         - 已知格式 → 确定性解析器（快、准）
         - 未知格式 → LLM 提取（慢、但能处理）
         
Phase 3: 逐步迁移
         - LLM 处理过的格式，如果重复出现，写成确定性解析器
         - LLM 只处理"长尾"格式
```

**优势**:
- 风险可控：核心路径仍是确定性
- 学习曲线：通过 LLM 输出学习新格式，再固化成规则
- 成本优化：常用格式不走 LLM

---

## 五、最终建议

### 5.1 核心建议

1. **采用混合架构**：LLM 提取 + 确定性组装（Q1）
2. **三层保障输出稳定性**：Constrained Decoding + Pydantic + Retry（Q2）
3. **五类 guardrails 缺一不可**：输入/提取/输出/一致性/降级（Q3）
4. **三级降级机制**：保证永远有输出（Q4）
5. **渐进式迁移**：不要一步到位，先插件化再引入 LLM（Q5）

### 5.2 实施路线图

```
Week 1-2: 重构确定性编译器为插件式
          - 抽出 5 个格式的解析器
          - 定义统一 IR schema
          
Week 3-4: 增加 LLM 提取层（实验性）
          - 实现 LLM 提取 → IR
          - 与确定性解析器对比测试
          
Week 5-6: 增加 guardrails + 降级
          - Pydantic 验证
          - 重试机制
          - 降级到规则提取
          
Week 7-8: 集成测试 + 灰度
          - 8 个案例全量测试
          - 对比确定性 vs LLM 提取质量
          - 决定生产环境切换时机
```

### 5.3 信心评分汇总

| 问题 | 信心评分 | 说明 |
|------|---------|------|
| Q1: LLM vs 确定性 | 8/10 | 混合架构是业界共识 |
| Q2: 输出稳定性 | 7/10 | 三层保障可行，但需要持续调优 |
| Q3: Guardrails | 8/10 | 五类 guardrails 覆盖全面 |
| Q4: 降级策略 | 7/10 | 降级逻辑清晰，但 Level 2 需要人工介入 |
| Q5: 代码量/维护 | 6/10 | 代码量略减，但维护复杂度增加 |
| **总体** | **6/10** | **可行但需谨慎，建议渐进式迁移** |

---

## 六、结论

修正方案的方向是对的——**用 LLM 处理格式多样性，用确定性逻辑保证输出质量**。但实施细节需要调整：

1. ❌ 不要完全替换确定性编译器
2. ✅ 让 LLM 和确定性逻辑**共存**，各司其职
3. ✅ 渐进式迁移，降低风险
4. ✅ 投入足够的 guardrails 和降级机制

**一句话总结**: LLM-as-Compiler 可行，但需要"确定性笼子"关住它。

---

*报告完成时间: 2026-06-18 21:45*  
*专家角色: LLM 可靠性工程师*  
*信心评分: 6/10*
