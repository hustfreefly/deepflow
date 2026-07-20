# DeepFlow Wiki

> 系统架构、数据流、测试覆盖的完整知识库  
> **版本**: V2.1.1 | **最后更新**: 2026-07-08

---

## 📚 文档索引

| # | 文档 | 内容 | 适合谁看 |
|:---|:---|:---|:---|
| 1 | [系统总览](1-系统总览.md) | 四域架构 + DAL + 三层门控 + AI Native 原则 | 新人入门、全局理解 |
| 2 | [域详解](2-域详解.md) | 每个域的工作流 + 关键组件 + 文件清单 | 开发者、调试者 |
| 3 | [Blackboard结构](3-Blackboard结构.md) | 文件组织规范 + 核心文件格式 | 开发者、数据恢复 |
| 4 | [Prompt注册表](4-Prompt注册表.md) | 56 个 Prompt 模板清单 + 调用关系 | Prompt 工程师 |
| 5 | [测试覆盖地图](5-测试覆盖地图.md) | 531 测试用例分布 + 运行命令 | 测试工程师 |
| 6 | [恢复手册](6-恢复手册.md) | 数据丢失后的完整恢复指南 | 运维、灾难恢复 |
| 7 | [CodeGraph](7-CodeGraph.md) | 核心函数调用关系图 | 架构理解 |
| 8 | [Changelog](changelog.md) | 版本变更历史 | 所有人 |
| 9 | [Overview (EN)](deepflow_overview.md) | English architecture overview | External readers |

---

## 🎯 系统状态

| 维度 | 状态 |
|:---|:---|
| **Spec Pro** | V2.2.0 · 52 tests · 8 prompts · 18 modules |
| **Solution Pro** | V2.1.1 · 137 tests · 39 prompts · 26 modules |
| **Ship Pro** | V2.0.0 · 19 tests · 1 prompt · 3 modules |
| **Research Pro** | V2.0.0 · 136 tests · 8 prompts · 10 modules |
| **Core + Integration** | 187 tests |
| **Total** | **531 tests** · **56 domain prompts** |

---

## 🔑 快速查询

| "我想了解..." | 看哪个文档 |
|:---|:---|
| DeepFlow 是什么？ | [1-系统总览](1-系统总览.md) |
| Spec Pro 怎么工作？ | [2-域详解 → Spec Pro](2-域详解.md#1-spec-pro) |
| DAL 是什么？ | [1-系统总览 → DAL](1-系统总览.md#dal-domain-adaptation-layer) |
| 三层门控怎么运作？ | [1-系统总览 → 三层门控](1-系统总览.md#三层门控架构) |
| LivingSpec 长什么样？ | [3-Blackboard结构](3-Blackboard结构.md) |
| 某个 prompt 被谁调用？ | [4-Prompt注册表](4-Prompt注册表.md) |
| 怎么跑测试？ | [5-测试覆盖地图](5-测试覆盖地图.md) |
| 数据丢了怎么恢复？ | [6-恢复手册](6-恢复手册.md) |
| 函数调用关系？ | [7-CodeGraph](7-CodeGraph.md) |
