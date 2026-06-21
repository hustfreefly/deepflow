---
id: deepflow/eval/serenity_skills_astock
type: case_study
title: "基线案例：Serenity Skills A股适配"
related:
  - ../QUALITY_GUIDE.md
status: baseline
created: 2026-06-20
---

# 基线案例：Serenity Skills A股适配

> **日期**: 2026-06-20 | **链路**: Spec Pro → Solution Pro → Ship Pro
> **总耗时**: ~2h（Spec Pro ~1h + Solution Pro ~48min + Ship Pro ~7min）

---

## 用户原始输入

> "将 Serenity Skills（5个美股买方投研 Codex Skill）迁移为 OpenClaw Skill，并适配中国上市公司。5个skill：serenity-alpha（新闻→Alpha假设）、bayesian-intrinsic-growth-valuation（贝叶斯内在增长估值）、gf-dma-health-index（GF-DMA健康指数）、tam-adj-peg（TAM调整PEG）、buy-side-equity-research-memo（买方研究备忘录）。适配要求：数据源从SEC filings切换到中国数据源（巨潮资讯/上交所/深交所公告、Tushare、东方财富等），估值体系和均线系统需要适配A股市场特点。与现有skills并行，目标用户为忠礼本人。"

---

## 维度一：模块内质量

### Spec Pro — 92/A

| 采集项 | 数据 |
|--------|------|
| 对话轮次 | 4轮 |
| 问题总数 | 9（R1=4, R2=2, R3=3） |
| 确认需求 | 11类 |
| 推断项 | 10个（7 confirmed + 3 pending） |
| 护栏 | always_do 4 + should_do 2 + never_do 6 |
| 用户指令 | 7条 |
| route_recommendation | ⚠️ null |
| solution_pro_hints | ⚠️ null |

**7维度评分**：

| 维度 | 得分 | Delta |
|------|:----:|:-----:|
| 目标与痛点 | 90 | -2 |
| 用户与场景 | 85 | +3 |
| 能力边界 | 92 | 0 |
| 质量属性 | 90 | 0 |
| 约束条件 | 90 | +15 |
| 环境与集成 | 92 | 0 |
| 风险与假设 | 85 | 0 |

**亮点**：
- 4轮收敛到92分，效率高
- 捕捉了用户的元指令（设计委托、无效问题标记、软目标降级）

**问题**：
- `route_recommendation = null`（交接协议缺陷）
- `solution_pro_hints = null`（交接协议缺陷）
- 4个推断项仍是 pending（Spec Pro 与 Solution Pro 之间缺少状态回写）

### Solution Pro — 0.89/PASS

| 采集项 | 数据 |
|--------|------|
| 阶段完成 | 10/10 |
| 需求总数 | 96 |
| 覆盖率 | 93 covered / 2 partial / 1 omitted = 97% |
| P0 缺失 | 0 |
| 审计发现 | 11（4 major + 4 minor + 3 info） |
| 修复率 | 100% |

**Harness 四维**：

| 维度 | 得分 | 等级 |
|------|:----:|:----:|
| 完整性 | 0.90 | HIGH |
| 必要性 | 0.93 | HIGH |
| 对齐度 | 0.91 | HIGH |
| 全局影响 | 0.83 | MEDIUM |

**三 Research 专家**：

| 专家 | 角度 | 搜索轮次 | 覆盖需求 |
|------|------|:--------:|:--------:|
| Expert 1 | OpenClaw 架构 + 数据源工程 | 3 | 5 |
| Expert 2 | A股投研领域适配 | 3 | 6 |
| Expert 3 | Serenity 方法论完整性保留 | 3 | 3 |

**三 Reviewer 发现**：

| Reviewer | Findings | 关键风险 |
|----------|:--------:|---------|
| Business | 9（4+/4r/1n） | 单用户无法规模化、A股框架适配不确定 |
| Risk | 11（4H/7M） | Tushare单点、Revision替代、估值参数无回测 |
| Technical | 10（4+/3r/3n） | 数据源覆盖度缺口、memo整合复杂度被低估 |

**亮点**：
- 审计-修复闭环完整，11/11 全修
- 5个 ADR 决策规范，理由清晰

**问题**：
- 🔴 v5.3.0 六个结构化字段全部缺失（regression）
- ⚠️ final_result.json 纯 markdown，下游需解析
- ⚠️ Global Impact = 0.83 (MEDIUM)，拖后腿

### Ship Pro — PASS（首轮通过）

| 采集项 | 数据 |
|--------|------|
| 阶段完成 | 5/5 |
| Reviewer 判定 | PASS（第1轮） |
| AC 可验证性 | 83 |
| 模块覆盖率 | 100%（7/7） |
| Issues | 2个 low severity |
| WP 数量 | 7（1 critical + 5 complex + 1 medium） |
| 文件数量 | 30 |
| effort 估算 | ⚠️ 字段为空 |

**亮点**：
- 首轮即通过
- AC 达到 L3+ 级别，含可执行测试命令
- Risk 标记嵌入 WP constraints

**问题**：
- ⚠️ `estimated_effort` 字段为空
- ⚠️ 2个 low issue 未修复（记录但未修）
- ⚠️ Packager `_meta` 缺失

---

## 维度二：跨模块对齐

### 2A: 用户意图 → Solution Pro

**覆盖度：✅ 符合**

| 用户意图 | 覆盖 | 体现位置 |
|----------|:----:|---------|
| 5个 skill 全部迁移 | ✅ | Comp-001~005 |
| 数据源从美股→A股 | ✅ | Comp-006 + 三级降级链 |
| 估值体系适配A股 | ✅ | Comp-002/003/004 A股适配 |
| 格式 Codex→OpenClaw | ✅ | SKILL.md 格式 |
| 与 stock-research-engine 独立共存 | ✅ | 独立 skill |
| gf-dma Python 精度 | ✅ | dma_calculator.py |
| buy-side memo 核心交付物 | ✅ | Comp-005 定义为核心 |

**过度工程：⚠️ 轻度 Over（+20%）**

| 额外设计 | 分类 | 判定 |
|----------|------|------|
| 三级降级链 | 必要余量 | ✅ 合理 |
| 合规护栏 | 合规底线 | ✅ 合理 |
| 敏感性分析 | 方法论保真 | ✅ 合理 |
| 中特估因子 | 锦上添花 | ⚠️ 待商榷 |
| shared 基础设施层 | 轻度过度架构 | ⚠️ 可简化 |

### 2B: Solution Pro → Ship Pro

**组件映射：✅ 7:7 完美映射**

| Solution Pro | Ship Pro | 对齐 |
|-------------|----------|:----:|
| Comp-006 数据源体系 | WP-001 | ✅ |
| Comp-007 A股适配层 | WP-002 | ✅ |
| Comp-001 serenity-alpha | WP-003 | ✅ |
| Comp-002 bayesian | WP-004 | ✅ |
| Comp-003 gf-dma-health | WP-005 | ✅ |
| Comp-004 tam-adj-peg | WP-006 | ✅ |
| Comp-005 buy-side-memo | WP-007 | ✅ |

**ADR 传播：✅ 5/5 完美传播**

| ADR | 体现位置 | 对齐 |
|-----|---------|:----:|
| ADR-001 两层分离 | WP-007 deps = 全部4个框架 | ✅ |
| ADR-002 PE(0.4)+PB(0.3)+PEG(0.3) | WP-006 AC 第2条 | ✅ |
| ADR-003 Revision三层替代 | WP-005 AC 第3条 | ✅ |
| ADR-004 cache目录共享 | WP-001 outputs cache_manager.py | ✅ |
| ADR-005 DMA位移=10 | WP-005 AC 第1条 | ✅ |

**文件映射：✅ 完全匹配**（Solution Pro 目录结构中的每个文件都在 Ship Pro outputs 中）

### 2C: 端到端追溯

**需求膨胀追踪**：

| 阶段 | 需求数 | 膨胀来源 |
|------|:------:|---------|
| 用户原话 | 1段（~150字） | — |
| Living Spec confirmed | 11类 | 结构化拆解 |
| Frozen Spec groups | 90 REQ | 推断展开 + 细化 |
| Solution Pro covered | 96 REQ | 研究/审计补充 |
| Ship Pro WP requirements | ~45 REQ（去重分配） | 分配到具体 WP |

膨胀合理：细化的是技术约束和 A 股适配细节，没有引入用户明确不需要的功能。

---

## 综合判定

| 维度 | 判定 | 说明 |
|------|------|------|
| Spec Pro 自身 | A（92） | 对话高效，交接字段缺失 |
| Solution Pro 自身 | B+（0.89） | 覆盖面广，v5.3.0 缺失 |
| Ship Pro 自身 | A-（首轮PASS） | AC 精确，effort 缺失 |
| 用户意图→Solution Pro | ✅+⚠️ | 符合 + 轻度Over(+20%) |
| Solution Pro→Ship Pro | ✅ | 严格贴着(~98%) |

**改进方向**：
1. 🔴 Solution Pro v5.3.0 字段缺失（regression，需修复 consolidator/summarizer prompt）
2. ⚠️ Spec Pro 交接字段（route_recommendation + solution_pro_hints）需补齐
3. ⚠️ Solution Pro final_result.json 需要结构化（sections/components/requirements 字段）
4. ⚠️ Ship Pro estimated_effort 字段需补齐
