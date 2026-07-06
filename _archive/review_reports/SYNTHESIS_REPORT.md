# DeepFlow 架构复盘 — 6 专家评审综合报告

> **日期**: 2026-06-23 | **评审方法**: 6 模型 × 6 视角并行评审 | **综合**: 小满

---

## 一、专家阵容

| # | 角色 | 模型 | 核心主张（一句话） |
|---|------|------|-------------------|
| E1 | 分布式系统架构师 | deepseek-v4-pro | 不止 1 个根因，是 **3 个维度的问题** |
| E2 | 平台工程专家 | kimi-k2.6 | 真正根因是 **没有执行引擎**，管线靠手写 spawn 驱动 |
| E3 | 多Agent系统研究者 | kimi-for-coding | 契约应该是 **Pydantic 模型**，从模型正向生成 Prompt/Gate/Schema |
| E4 | Contract-First 设计专家 | kimi-k2.5 | 128 个错误 = "实现太随意 + 契约未共享"，Contract Layer **过度工程化** |
| E5 | 质量工程专家 | qwen3.7-max | 真正根因是 **测试策略与生产脱节**，测试用合成数据不用真实输出 |
| E6 | 技术债务战略师 | qwen3.7-plus | 诊断准确但 **治疗过重**，单人项目完整 Contract Layer ROI 不佳 |

---

## 二、共识矩阵：6 位专家同意什么、反对什么

### ✅ 6/6 共识（全体同意）

| 观点 | 支持 |
|------|------|
| "缺少合同层"的诊断 **部分正确** | E1 E2 E3 E4 E5 E6 |
| 但 **不是唯一根因**，还有更深层/并行的问题 | E1 E2 E3 E4 E5 E6 |
| 完整 Contract Layer 对单人项目 **过度工程化** | E1 E2 E3 E4 E5 E6 |
| **先止血**（修 P1 问题），再做系统性方案 | E1 E2 E3 E4 E5 E6 |
| 原方案的 Phase 顺序 **需要调整** | E1 E2 E3 E4 E5 E6 |

### 📊 5/6 多数共识

| 观点 | 支持 | 反对 |
|------|------|------|
| 真相源应该是 **Pydantic 模型**（不是 YAML） | E2 E3 E4 E5 E6 | E1（未明确表态） |
| 执行引擎化比合同层 **优先级更高** | E1 E2 E3 E4 E6 | E5（认为测试优先） |
| LLM 不确定性是 **放大器不是根因** | E1 E3 E4 E5 E6 | E2（认为也是根因之一） |

### ⚡ 分歧点

| 议题 | 正方 | 反方 |
|------|------|------|
| 先修什么？ | 执行引擎 (E1/E2/E4) vs 测试策略 (E5) vs 止血 (E6) | — |
| Pydantic 能否约束 LLM？ | 能，配合 JSON mode (E3/E5) | 有限，LLM 可能不遵守 (E4) |
| 项目值不值得大投入？ | 值得，是核心基础设施 (E1/E2) | 不值得，容忍带病运行 (E6) |

---

## 三、综合诊断：真正的根因是什么

6 位专家共同揭示了一个 **比原始诊断更深** 的根因结构：

```
                    ┌─────────────────────────────┐
                    │  根因：DeepFlow 是一个         │
                    │  "有人写、无人管"的系统         │
                    └─────────────┬───────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
    ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
    │ 维度1: 数据契约   │ │ 维度2: 执行权力   │ │ 维度3: 状态真相   │
    │ (What)           │ │ (How)           │ │ (When)          │
    │                  │ │                 │ │                 │
    │ 5份文档各自描述   │ │ 3条路径+手写     │ │ 多个状态文件     │
    │ 对数据的理解      │ │ spawn=无引擎     │ │ 各自独立更新     │
    │                  │ │                 │ │                 │
    │ → 128个Schema错  │ │ → 主Agent绕过    │ │ → .completed    │
    │ → Gate检查幽灵   │ │   run_pipeline  │ │   ≠ .stage_prog │
    │   字段           │ │                 │ │   ≠ pipeline_st │
    └─────────────────┘ └─────────────────┘ └─────────────────┘
```

**原始诊断只覆盖了维度1（数据契约），遗漏了维度2（执行引擎）和维度3（状态源）。**

---

## 四、综合方案：最小可行架构加固（MVH）

综合 6 位专家的建议，形成共识方案：

### 4.1 对比：原方案 vs 共识方案

| 项目 | 原方案（Contract Layer） | 共识方案（MVH） |
|------|------------------------|----------------|
| 真相源 | `contract.yaml` | **Pydantic 模型**（E3/E5 推荐） |
| 生成方向 | yaml → prompt + gate + schema | **Pydantic → JSON Schema → prompt 段落 + gate 代码** |
| 执行引擎 | Phase 2（后置） | **Phase 0（前置）**，消灭手写 spawn |
| 测试策略 | 未提及 | **生产数据回放 + 契约测试**（E5 推荐） |
| 状态管理 | 未提及 | **单一状态文件 + 原子更新**（E1/E2 推荐） |
| 工作量 | 8-13 天（E6 估算） | **3-4 天**（E6 估算） |
| ROI | 6-12 月回本 | **1-3 月回本** |

### 4.2 实施路线图（4 Phase）

#### Phase 0: 止血（今天，~1小时）
- [ ] P1-2: Architect prompt 加 `project_type` + `mapped_components` → 消除 Gate CONDITIONAL
- [ ] P1-1: Packager prompt 与 Schema 对齐 → 消除 128 个 Schema 错误
- [ ] P1-4: completion_handler 同步更新 `.stage_progress.json`

#### Phase 1: Pydantic 真相源（Week 1，~2天）
```python
# domains/ship_pro/contracts.py — 唯一真相源
from pydantic import BaseModel, Field

class Requirement(BaseModel):
    req_id: str
    description: str
    priority: Literal["P0", "P1", "P2"]
    mapped_components: list[str]  # Gate 检查的就是这个！

class ArchitectOutput(BaseModel):
    project_type: str  # Gate 检查的就是这个！
    modules: list[Module]
    requirements: list[Requirement]
    ...

# 自动生成：
# 1. JSON Schema: ArchitectOutput.model_json_schema()
# 2. Prompt 段落: 从 JSON Schema 生成
# 3. Gate 检查: ArchitectOutput.model_validate(data)
```

#### Phase 2: 执行引擎化（Week 2，~1天）
- [ ] 统一执行路径：只有 `run_pipeline.py` CLI
- [ ] SKILL.md 只说"调用 CLI"，不描述流程细节
- [ ] orchestrator.py 废弃或合并到 run_pipeline.py

#### Phase 3: 状态单一化（Week 3，~半天）
- [ ] 合并为 1 个状态文件 `pipeline_state.json`
- [ ] 所有状态更新通过 `run_pipeline.py` CLI（原子操作）
- [ ] 禁止直接写状态文件

---

## 五、各专家独特洞察（盲点发现）

| 专家 | 独特发现 |
|------|---------|
| E1 | 问题不是 1 个根因，是 **3 个正交维度**（数据/执行/状态） |
| E2 | DeepFlow 没有执行引擎——是 **"人工程序员手写 spawn"充当引擎** |
| E3 | 真相源应该是 **Pydantic 模型**，不是 YAML；JSON mode 可以强制 LLM 输出结构 |
| E4 | 128 个错误 = "实现太随意"，不是"spec 太严格"；**传统 API 治理的成熟 pattern 直接可用** |
| E5 | **测试用合成 fixture 不用真实 LLM 输出**——这才是为什么 128 个错误没被发现 |
| E6 | **Wardley Map 分析**：管线编排应该用商品化工具（Temporal），不值得自建 |

---

## 六、风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|:---:|:---:|------|
| Pydantic 模型太严格，LLM 经常校验失败 | 中 | 中 | 配合 JSON mode + 分级校验（strict/warning） |
| 止血后失去改进动力 | 高 | 中 | 设定 Phase 1 启动日期（止血后 3 天内） |
| 单人维护瓶颈 | 高 | 低 | 用 AI 辅助生成代码（Pydantic → Schema 已验证） |
| 过度抽象 | 低 | 中 | MVH 保持最小化，不做 YAML 配置系统 |

---

## 七、决策建议

### 给忠礼的建议

**立即执行**：Phase 0 止血（今天 1 小时，消除 P1 问题）

**本周执行**：Phase 1 Pydantic 真相源（2 天，系统性消除数据契约断裂）

**下周执行**：Phase 2 执行引擎化（1 天，消除 3 条路径分裂）

**可选延后**：Phase 3 状态单一化（半天，消除状态不一致）

**总投入**：~4 天，预期 1-3 月回本（减少 bug 修复时间）

### 不建议做的

- ❌ 完整的 `contract.yaml` 配置系统（过度工程化）
- ❌ 引入 Temporal 等外部编排框架（单人项目太重）
- ❌ OpenTelemetry 全链路追踪（过重，轻量日志即可）
- ❌ 一次性大重构（渐进式更安全）

---

## 附录：原始评审报告

| 文件 | 专家 | 字数 |
|------|------|-----:|
| `expert_1_distributed_systems.md` | 分布式系统架构师 | ~1500 |
| `expert_2_platform_engineering.md` | 平台工程专家 | ~1800 |
| `expert_3_multi_agent.md` | 多Agent系统研究者 | ~1800 |
| `expert_4_contract_first.md` | Contract-First设计专家 | ~900 |
| `expert_5_quality_engineering.md` | 质量工程专家 | ~2700 |
| `expert_6_tech_debt.md` | 技术债务战略师 | ~1500 |

**总评审文本量**: ~10,200 字 | **总 token 消耗**: ~600K
