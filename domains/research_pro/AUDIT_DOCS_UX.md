# Research Pro 文档与用户体验审计报告

> **审计日期**: 2026-06-11  
> **审计标准**: 新用户能否在 10 分钟内理解并运行  
> **审计员**: DeepFlow Research Pro 文档与用户体验审计员

---

## 总体评级: 🟡 **YELLOW** (需要改进)

**总体评估**: Research Pro 的文档结构完整，技术细节充分，但存在关键的"新用户入门"缺口。有经验的开发者可以理解系统，但新用户需要更多引导才能上手。

---

## 逐文件审计

### 1. `_overview.md` — 模块概览

| 维度 | 评级 | 说明 |
|------|------|------|
| 完整性 | 🟡 **YELLOW** | 有代码索引和配置索引，但缺少安装/运行说明 |
| 准确性 | 🟢 **GREEN** | 文件列表与实际一致 |
| 易用性 | 🟡 **YELLOW** | 缺少"快速开始"段落，新用户不知道第一步做什么 |

**问题列表**:
- ❌ 没有说明如何启动一个研究任务（入口点不明确）
- ❌ 没有说明前置依赖（Python 版本、需要的 API Key 等）
- ❌ 没有示例命令或用法展示
- ❌ 缺少与其他模块的关系说明（如何被调用）

**建议**:
```markdown
## 快速开始
```python
from domains.research_pro.orchestrator import ResearchProOrchestrator

orch = ResearchProOrchestrator(mode="standard")
session = orch.init_session("分析贵州茅台的投资价值")
plan = orch.generate_plan()
# 等待用户确认...
```
```

---

### 2. `config/research_pro.yaml` — 主配置

| 维度 | 评级 | 说明 |
|------|------|------|
| 完整性 | 🟢 **GREEN** | 包含组件版本、Agent 定义、超时设置 |
| 准确性 | 🟢 **GREEN** | 与实际代码一致 |
| 易用性 | 🟡 **YELLOW** | 缺少配置项说明和修改示例 |

**问题列表**:
- ⚠️ `timeout` 值的单位不明确（秒？分钟？）
- ⚠️ 没有说明如何覆盖默认配置
- ⚠️ 缺少配置验证说明

---

### 3. `config/tier_domains.json` — 数据源分级

| 维度 | 评级 | 说明 |
|------|------|------|
| 完整性 | 🟢 **GREEN** | 完整的 Tier 1/2/3 域名列表 |
| 准确性 | 🟢 **GREEN** | 域名列表合理 |
| 易用性 | 🟢 **GREEN** | 有清晰的权重说明和匹配策略 |

**问题列表**:
- ✅ 无明显问题
- 💡 建议: 添加如何添加自定义域名的示例

---

### 4. `config/time_budgets.json` — 时间预算

| 维度 | 评级 | 说明 |
|------|------|------|
| 完整性 | 🟢 **GREEN** | 包含 quick/standard 两种模式 |
| 准确性 | 🟢 **GREEN** | 与代码中的超时处理一致 |
| 易用性 | 🟡 **YELLOW** | 缺少如何选择模式的说明 |

**问题列表**:
- ⚠️ `confirming` 阶段的 86400 秒（24小时）对新用户来说可能意外
- ⚠️ 没有说明各阶段超时的降级行为

---

### 5. `config/completion_criteria.json` — 完成标准

| 维度 | 评级 | 说明 |
|------|------|------|
| 完整性 | 🟢 **GREEN** | 包含质量标准、降级规则 |
| 准确性 | 🟢 **GREEN** | 与代码逻辑一致 |
| 易用性 | 🟡 **YELLOW** | 缺少质量分数计算示例 |

**问题列表**:
- ⚠️ `degradation_rules` 中的值是字符串描述，不是代码可执行的

---

### 6. `prompts/planning.md` — 规划器 Prompt

| 维度 | 评级 | 说明 |
|------|------|------|
| 完整性 | 🟢 **GREEN** | 职责、输出格式、策略完整 |
| 准确性 | 🟢 **GREEN** | 与代码期望的 JSON 格式一致 |
| 易用性 | 🟡 **YELLOW** | 输出格式要求严格，但没有验证工具说明 |
| Prompt 质量 | 🟢 **GREEN** | 结构清晰，有安全声明 |

**问题列表**:
- ⚠️ "必须输出严格的 JSON 格式" — 但没有说明如果失败怎么处理
- ✅ 有明确的输入/输出格式
- ✅ 有安全声明（RED-DC-004, RED-DC-007）

---

### 7. `prompts/search.md` — 搜索器 Prompt

| 维度 | 评级 | 说明 |
|------|------|------|
| 完整性 | 🟢 **GREEN** | 三阶段搜索流程清晰 |
| 准确性 | 🟢 **GREEN** | 与代码中的 Source Registry 要求一致 |
| 易用性 | 🟢 **GREEN** | 有清晰的输出格式示例 |
| Prompt 质量 | 🟢 **GREEN** | 有 RED-DC-001 引用要求 |

**问题列表**:
- ✅ 无明显问题

---

### 8. `prompts/finance_analysis.md` — 金融分析器 Prompt

| 维度 | 评级 | 说明 |
|------|------|------|
| 完整性 | 🟢 **GREEN** | 10维度分析框架完整 |
| 准确性 | 🟢 **GREEN** | 与代码期望的报告结构一致 |
| 易用性 | 🟢 **GREEN** | 有清晰的章节模板 |
| Prompt 质量 | 🟢 **GREEN** | 有引用规范说明 |

**问题列表**:
- ✅ 无明显问题
- 💡 建议: 添加示例报告片段

---

### 9. `prompts/citation_verify.md` — 引用验证器 Prompt

| 维度 | 评级 | 说明 |
|------|------|------|
| 完整性 | 🟢 **GREEN** | 五步验证循环清晰 |
| 准确性 | 🟢 **GREEN** | 与代码逻辑一致 |
| 易用性 | 🟢 **GREEN** | 有状态定义表格 |
| Prompt 质量 | 🟢 **GREEN** | 有可信度分数计算说明 |

**问题列表**:
- ✅ 无明显问题

---

### 10. `.deepflow/CONTRACTS.md` — 契约系统规范

| 维度 | 评级 | 说明 |
|------|------|------|
| 完整性 | 🟢 **GREEN** | 完整的契约系统文档 |
| 准确性 | 🟢 **GREEN** | 文件组织与实际一致 |
| 易用性 | 🟡 **YELLOW** | 作为全局文档，需要更多交叉引用 |

**问题列表**:
- ⚠️ 文档提到 `cage/active/research_pro_v1.0.yaml`，但没有链接
- ⚠️ 新用户可能不知道契约与具体模块的关系

---

### 11. `SKILL.md` — 技能描述

| 维度 | 评级 | 说明 |
|------|------|------|
| 完整性 | 🔴 **RED** | **文件不存在** |
| 准确性 | N/A | 文件不存在 |
| 易用性 | N/A | 文件不存在 |

**问题列表**:
- 🔴 **P0**: `SKILL.md` 文件缺失！这是 OpenClaw 技能系统的入口文件
- 🔴 没有 SKILL.md，OpenClaw 无法识别 Research Pro 作为可用技能

---

## 新用户体验模拟

### 从 README 到运行需要几步？

**当前路径**（假设用户从 `_overview.md` 开始）:

1. ✅ 阅读 `_overview.md` — 了解模块职责
2. ❓ **困惑**: "入口是 orchestrator.py？怎么用？"
3. ❓ **困惑**: "需要配置什么？API Key？"
4. ❓ **困惑**: "如何触发一个研究任务？"
5. 🔍 用户可能需要阅读 `orchestrator.py` 源码才能理解
6. 🔍 还需要阅读 `cage/active/research_pro_v1.0.yaml` 了解契约

**结论**: 新用户无法在 10 分钟内上手。

### 哪些步骤缺少文档？

| 步骤 | 状态 | 缺失内容 |
|------|------|----------|
| 安装依赖 | 🔴 缺失 | requirements.txt, Python 版本要求 |
| 配置 API Key | 🔴 缺失 | 搜索 API、Web Fetch 配置 |
| 启动研究 | 🔴 缺失 | 代码示例、CLI 命令 |
| 查看结果 | 🟡 部分 | 报告输出位置说明 |
| 调试问题 | 🔴 缺失 | 常见问题、日志位置 |

### 哪些假设用户已经知道？

1. **假设用户知道 DeepFlow 架构**: 用户需要理解 Blackboard、State、Agent 模式等概念
2. **假设用户知道契约系统**: 需要阅读 CONTRACTS.md 才能理解红线规则
3. **假设用户知道 Source Registry**: 这是核心概念，但没有独立文档
4. **假设用户会阅读 Python 源码**: orchestrator.py 有 1300+ 行

---

## 必须修复清单

### 🔴 P0 (阻断性)

1. **创建 `SKILL.md` 文件**
   - 位置: `.deepflow/domains/research_pro/SKILL.md`
   - 内容: OpenClaw 技能标准格式，包含触发词、参数、示例
   - 参考: 其他技能的 SKILL.md 格式

2. **添加 README.md 或 QUICKSTART.md**
   - 3 分钟快速开始指南
   - 包含代码示例
   - 说明前置依赖

3. **添加安装依赖说明**
   - requirements.txt（如果缺失）
   - Python 版本要求（≥3.10?）
   - 外部 API Key 配置（搜索 API、Web Fetch）

### 🟡 P1 (重要)

4. **`_overview.md` 添加"快速开始"章节**
   - 最小可运行代码示例
   - 解释 `mode` 参数的选择
   - 说明报告输出位置

5. **添加架构图**
   - 四阶段状态机流程图
   - Agent 模式 A/B/C 对比图
   - Source Registry 数据流图

6. **添加调试指南**
   - 日志文件位置
   - 常见问题排查
   - 状态恢复说明

7. **配置文档补充**
   - 每个配置项的详细说明
   - 环境特定的配置示例

### 🟢 P2 (建议)

8. **Prompt 文件添加使用说明**
   - 如何自定义 prompt
   - 提示词调试技巧

9. **添加示例报告**
   - 快速模式示例输出
   - 标准模式示例输出

10. **添加测试运行说明**
    - 如何运行测试
    - 如何验证安装成功

---

## 附录: 文件清单核对

| 文件 | 状态 | 备注 |
|------|------|------|
| `_overview.md` | ✅ 存在 | 需要添加快速开始 |
| `config/research_pro.yaml` | ✅ 存在 | 良好 |
| `config/tier_domains.json` | ✅ 存在 | 良好 |
| `config/time_budgets.json` | ✅ 存在 | 良好 |
| `config/completion_criteria.json` | ✅ 存在 | 良好 |
| `prompts/planning.md` | ✅ 存在 | 良好 |
| `prompts/search.md` | ✅ 存在 | 良好 |
| `prompts/finance_analysis.md` | ✅ 存在 | 良好 |
| `prompts/citation_verify.md` | ✅ 存在 | 良好 |
| `SKILL.md` | 🔴 **缺失** | **P0** |
| `README.md` | 🔴 **缺失** | **P0** |
| `QUICKSTART.md` | 🔴 **缺失** | **P0** |

---

*审计完成*
