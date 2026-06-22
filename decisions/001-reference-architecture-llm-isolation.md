# ADR-001: 引用式架构与 LLM 隔离

- **状态**: 已决策
- **日期**: 2026-06-22
- **决策者**: 忠礼 + 6 位 AI 专家（3 位讨论 + 3 位裁决）

---

## 背景

### 核心问题
DeepFlow 多域架构（4 个域：Solution Pro / Ship Pro / Spec Pro / Research Pro）在快速迭代中遇到**改动联动问题**：
- 改一个域名（如 `solution` → `solution_pro`）→ 需要修改 **27-58 处**
- 改一个 stage 路径（如 `planning.json` → `plan.json`）→ 需要修改 **11 处**
- 根因：**字符串散播**（路径、名字硬编码在多处）

### 触发事件
- 2026-06-22 端到端测试发现 **79 个带病运行问题**：
  - 29 个 import 错误（路径不一致）
  - 35 个路径错误（字符串拼接）
  - 15 个工具调用失败（路径不存在）
- 6 Phase 修复后意识到：每次改动都有"蝴蝶效应"，需要系统性解决

### 约束条件
- **AI Native 第一原则**: Simplicity First（不要过度设计）
- **用户偏好**: 忠礼明确不喜欢过度设计
- **现实**: 代码主要由 LLM 生成，LLM 不会主动查 Registry 再写代码

---

## 考虑的选项

### 选项 1: 四层 Enum 体系
**提出者**: 架构师（Qwen3.7 Max）

```python
class DomainID(Enum):
    SOLUTION_PRO = auto()
    @property
    def dir_name(self) -> str:
        return self.name.lower()
```

**优点**: 类型安全、IDE 可重构、编译时检查  
**缺点**: 
- 需要为每个概念建 Enum，代码量增加 30%+
- LLM 生成代码时需要理解 Enum 模式，更多 token
- 高变化频率下维护成本高

**结论**: ❌ 过度设计

---

### 选项 2: Capability-Based Discovery
**提出者**: 批判者（DeepSeek V3）

```python
# 消费者引用"能力"而非"路径"
planning = stage_broker.resolve("planning")

@stage("planning", aliases=["plan"])
class PlanningStage:
    pass
```

**优点**: 彻底解耦，改名不影响消费者  
**缺点**:
- 引入 broker/resolver 层，系统复杂度增加
- 调试困难（间接调用链）
- LLM 需要理解装饰器注册机制

**结论**: ❌ 复杂度过高

---

### 选项 3: Registry dict（当前方案）
**提出者**: 实践者（Kimi K2.5）

```python
STAGE_PATH_REGISTRY = {
    "planning": "domains/solution_pro/stages/planning.json",
    "execution": "domains/solution_pro/stages/execution.json",
}
```

**优点**:
- 简单、已验证（6 Phase 迁移完成，4 域统一）
- LLM 最熟悉的数据结构，零认知负担
- 高变化频率下维护成本最低

**缺点**: 不够类型安全（可接受）

**结论**: ✅ 保持现状

---

### 选项 4: Schema-Driven Generation
**提出者**: 裁决专家 B（Kimi K2.6）

```yaml
# schema/stage_schema.yaml（人写）
stages:
  planning:
    path: stages/planning.json
    type: json
```

```python
# generated/bindings.py（机器生成，LLM 只读）
PLANNING_PATH = "stages/planning.json"
```

**优点**:
- **LLM 根本接触不到路径**，问题在源头被消除
- 人写 schema，机器生成代码，LLM 只写业务逻辑
- 完全适配 AI Native 特性

**缺点**: 
- 需要新增 codegen 工具
- 需要配置 CI 防止绕过

**结论**: ✅ 新增此机制

---

### 选项 5: constants.py
**提出者**: 架构师（Qwen3.7 Max）

```python
# core/config/domain_ids.py — 只放域标识
# core/config/stage_ids.py — 只放 stage 标识
```

**优点**: 集中管理  
**缺点**:
- 分层拆分是"把一坨屎分成五盘"（裁决专家 C 原话）
- 所有模块依赖一个文件 → 该文件改不动
- 命名混乱（DIR_PLANNING / STAGE_PLANNING / FILE_PLANNING）
- 循环依赖风险

**结论**: ❌ 坚决不用

---

## 决策

### 核心原则
1. **Simplicity First** — 不要过度设计，dict 够用就不搞 Enum
2. **LLM 隔离** — 路径信息对 LLM 不可见，从 schema 生成
3. **Registry 统一** — 所有标识符都走 Registry，不引入 constants.py

### 具体决策

#### 1. 抽象程度：保持 Registry dict
**理由**: 
- AI Native 第一原则是 Simplicity First
- 高变化频率下，轻量级抽象维护成本最低
- 系统已经生产验证（6 Phase 迁移完成）

**实施**: 保持当前 `STAGE_PATH_REGISTRY` dict 模式，可选添加 `Literal` 类型提示

#### 2. LLM 约束：Schema-Driven Generation + CI 卡点
**理由**:
- Prompt 约束是"确定性失败"（LLM 不会主动查 Registry 再写代码）
- CI 卡点是好的第二道防线，但反复修复成本高
- Schema-Driven 从根本上消除问题土壤

**实施**:
```
人写 schema → 机器生成 bindings → LLM import 使用
     ↑                                    ↓
  唯一真相源                        永远不写路径
```

四层防护：
1. **架构层**: Schema-Driven Generation（消除问题土壤）
2. **CI 层**: 检查 `generated/` 目录未被手动修改（防止绕过）
3. **Lint 层**: 禁止 import 非 generated 的路径常量（兜底）
4. **Prompt 层**: 明确告知 LLM "只使用 generated.bindings"（辅助引导）

#### 3. constants.py：坚决不用
**理由**:
- 分层拆分是"把一坨屎分成五盘"
- Registry 已能覆盖 90% 场景
- 现有基础设施骨架足够，边际成本接近于零

**替代**: Registry + Capability Discovery（可选）
- 需要新增 `capability_base.py` + `discovery.py`
- 在 DomainRegistry 中增加 `get_capability()` 方法

---

## 后果

### 正面效果
- **改动联动从 27-58 处降到 1-2 处**（只改 schema）
- **LLM 不再写错路径**（根本接触不到路径信息）
- **维护成本降低**（简单模式 + 自动化生成）

### 潜在风险
- **Schema 维护成本**: 需要人写 schema，但这比维护硬编码路径简单
- **Codegen 工具开发**: 需要一次性投入开发 codegen 工具
- **迁移成本**: 现有代码需要迁移到 Schema-Driven 模式

### 缓解措施
- **渐进迁移**: 不要求一次性迁移，新代码必须用 Schema-Driven，旧代码逐步迁移
- **CI 卡点**: 防止新代码引入硬编码路径
- **文档**: 本 ADR + 实施指南

---

## 当前架构状态评估

| 维度 | 现状 | 是否需要改 |
|:---|:---|:---|
| Registry dict | ✅ 已实现（6 Phase 迁移完成） | 不需要 |
| Schema-Driven Generation | ❌ 未实现 | **需要新增** |
| constants.py | ✅ 已避免 | 不需要 |
| Capability Discovery | ⚠️ 部分（有 Registry，无 Capability 基类） | 可选 |

**结论**: 现有架构不需要改，只需新增 Schema-Driven Generation 机制

---

## 相关文档

- **背景**: [2026-06-22 工作日志](../memory/2026-06-22.md)
- **实施**: [6 Phase 修复记录](../memory/2026-06-22.md#phase-4-5-6-全量验证)
- **讨论**: 6 位 AI 专家讨论记录（Qwen3.7 Max / Kimi K2.5 / DeepSeek V3 / Qwen3.7 Plus / Kimi K2.6 / Kimi-for-Coding）

---

## 后续行动

1. **新增 Schema-Driven Generation 机制**
   - 定义 schema 格式（YAML）
   - 实现 codegen 工具
   - 配置 CI 卡点

2. **迁移现有代码**
   - 识别所有硬编码路径
   - 逐步迁移到 Schema-Driven 模式
   - CI 卡点防止新增硬编码

3. **可选：Capability Discovery**
   - 新增 `capability_base.py` + `discovery.py`
   - 在 DomainRegistry 中增加 `get_capability()` 方法

---

**决策签署**: 忠礼 + 6 位 AI 专家  
**下次评审**: 2026-07-22（实施 1 个月后）
