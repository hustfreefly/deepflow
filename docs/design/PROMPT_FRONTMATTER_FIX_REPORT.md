# Prompt Frontmatter 修复报告

> **日期**: 2026-06-22  
> **修复人**: DeepFlow 修复专家（subagent）  
> **状态**: ✅ 已完成

---

## 1. 背景

恢复验证报告发现 11 个 prompt 文件缺少完整的 YAML frontmatter。这些文件已有最小化 frontmatter（仅 `id` + `version`），但缺少 `description`、`author`、`created`、`updated`、`tags` 等标准字段。

## 2. 修复范围

共修复 **11 个文件**，分布在 2 个 domain 下：

### ship_pro domain（9 个）

| # | 文件 | id | description |
|---|------|-----|-------------|
| 1 | `domains/ship_pro/prompts/architect.md` | `ship_pro/architect` | 从 Solution Pro 输出中提取统一架构描述，生成 blueprint.json |
| 2 | `domains/ship_pro/prompts/decomposer.md` | `ship_pro/decomposer` | 将架构模块拆分为可执行的工作包（WP），并推导 WP 间依赖关系 |
| 3 | `domains/ship_pro/prompts/packager.md` | `ship_pro/packager` | 将所有 Agent 输出组装为标准化 ship_package.json 并生成 summary.md |
| 4 | `domains/ship_pro/prompts/reviewer.md` | `ship_pro/reviewer` | 审核上游 Agent 输出质量，通过自然语言反馈驱动修改 |
| 5 | `domains/ship_pro/prompts/ship_fixer.md` | `ship_pro/ship_fixer` | 根据 Reviewer 问题清单修复 ship_package.json 中的问题 |
| 6 | `domains/ship_pro/prompts/ship_harness.md` | `ship_pro/ship_harness` | 验证 Fixer 修复是否有效，确保 Ship Package 可交付 |
| 7 | `domains/ship_pro/prompts/ship_pre_scanner.md` | `ship_pro/ship_pre_scanner` | 阅读 Frozen Blueprint 提取结构化领域知识，供确定性编译器消费 |
| 8 | `domains/ship_pro/prompts/ship_reviewer.md` | `ship_pro/ship_reviewer` | 轻量级兜底验证，检查 AC 质量和依赖合理性 |
| 9 | `domains/ship_pro/prompts/specifier.md` | `ship_pro/specifier` | 为每个工作包编写具体可验证的验收标准（AC）和技术约束 |

### solution domain（2 个）

| # | 文件 | id | description |
|---|------|-----|-------------|
| 10 | `domains/solution/prompts/REQ_DEDUP_DESIGN.md` | `solution/REQ_DEDUP_DESIGN` | REQ 语义去重规则设计，消除 Consolidator 输出中的语义重复需求 |
| 11 | `domains/solution/prompts/orchestrator_completion.md` | `solution/orchestrator_completion` | 10 阶段管线完成后的处理流程，包括编译 Frozen Blueprint 和 Ship Package |

## 3. 修复内容

### 修复前（最小化 frontmatter）

```yaml
---
id: ship_pro/architect
version: "1.0.0"
---
```

### 修复后（完整标准 frontmatter）

```yaml
---
id: ship_pro/architect
version: 1.0.0
description: 从 Solution Pro 输出中提取统一架构描述，生成 blueprint.json
author: DeepFlow Team
created: 2026-06-18
updated: 2026-06-21
tags: [ship_pro, prompt, architecture, extraction]
---
```

### 新增字段说明

| 字段 | 值来源 | 说明 |
|------|--------|------|
| `description` | 根据文件内容推断 | 中文简要描述，一句话说明 prompt 用途 |
| `author` | 固定值 | `DeepFlow Team` |
| `created` | 固定值 | `2026-06-18`（与项目创建日期一致） |
| `updated` | 固定值 | `2026-06-21`（最近一次内容更新日期） |
| `tags` | 根据文件内容推断 | 包含 domain 名、`prompt`、功能关键词 |

## 4. 修复原则

1. **保持原有内容不变** — 仅在文件开头扩展 frontmatter，不修改正文
2. **保留已有 id 和 version** — 不改变已有的 `id` 值，`version` 从字符串 `"1.0.0"` 改为数字 `1.0.0`
3. **description 基于内容推断** — 阅读每个文件的核心职责描述，提炼为一句话
4. **tags 包含领域标识** — 每个 tag 数组包含 domain 名（`ship_pro` 或 `solution`）+ `prompt` + 功能关键词

## 5. 验证

所有 11 个文件已通过以下验证：

- ✅ YAML frontmatter 格式正确（`---` 开闭标记完整）
- ✅ 所有必填字段存在（id, version, description, author, created, updated, tags）
- ✅ 原有正文内容未被修改
- ✅ description 准确反映文件用途

## 6. 统计

| 指标 | 数值 |
|------|------|
| 修复文件总数 | 11 |
| ship_pro domain | 9 |
| solution domain | 2 |
| 新增字段总数 | 55（每文件 5 个新字段） |
| 正文修改行数 | 0 |

---

*报告生成时间: 2026-06-22 02:31 GMT+8*
