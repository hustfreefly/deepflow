# 契约笼子：三个待办事项清理

## 目标
完成搜索配置化改造后的三个遗留事项

## 待办清单

### 事项1：google.generativeai 迁移到 google.genai
- **现状**：`google-generativeai` 已弃用，安装时发出 FutureWarning
- **目标**：迁移到新的 `google-genai` 包
- **影响文件**：`core/search_engine.py` 中的 `_gemini_search` 方法
- **验证**：迁移后搜索功能正常，无警告

### 事项2：Tushare Token 环境变量配置
- **现状**：需要 `TUSHARE_TOKEN` 环境变量但未说明
- **目标**：提供配置指南，支持多种配置方式（环境变量、配置文件）
- **影响**：`data/search_config.yaml` 中的 token 配置
- **验证**：配置后 Tushare 搜索源可用

### 事项3：用户配置文档
- **现状**：用户不知道如何配置 DeepFlow
- **目标**：创建 `docs/configuration.md`，说明如何配置搜索、数据源等
- **验证**：新用户按文档可完成配置

## 实施步骤
1. 安装 google-genai 并修改 search_engine.py
2. 更新 search_config.yaml 支持多方式配置 token
3. 创建 docs/configuration.md
4. 验证所有功能正常
5. 提交 Git
