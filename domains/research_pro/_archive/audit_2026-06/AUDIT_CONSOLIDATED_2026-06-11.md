# Research Pro — GitHub 发布就绪审计报告

> **审计日期**: 2026-06-11  
> **审计标准**: 能否正式推到 GitHub，让其他用户正常使用  
> **审计方式**: 5 个专项 Agent 并行审计（代码质量 / 测试覆盖 / 文档UX / 安全 / 架构）

---

## 总体评级: 🟡 YELLOW — 需要修复 12 项问题后方可发布

| 审计维度 | 评级 | 亮点 | 最大问题 |
|---------|------|------|---------|
| **代码质量** | 🟡 YELLOW | SSRF 防护优秀、并发安全 | subprocess 代码注入风险 |
| **测试覆盖** | 🟡 YELLOW | 3 个模块 100% 覆盖 | 78/115 测试被依赖阻塞 |
| **文档与 UX** | 🟡 YELLOW | Prompt 质量高 | 缺 SKILL.md / README / 安装说明 |
| **安全** | 🟢 GREEN | 无凭证泄露、SSRF 防护完善 | 缺 requirements.txt / LICENSE |
| **架构集成** | 🟡 YELLOW | Cage 契约完整、状态机清晰 | 未注册到 UnifiedEntry |

---

## 🔴 P0 — 阻塞发布（必须修复，共 6 项）

### P0-1: subprocess 代码注入风险
**位置**: `orchestrator.py` `_search_ddgs()`  
**问题**: 使用 `subprocess.run` 执行动态生成的 Python 代码字符串，虽然是硬编码脚本相对安全，但这是危险的反模式  
**修复**: 将 DDGS 搜索逻辑提取为独立模块 `ddgs_client.py`，直接导入调用  
**影响**: 安全性 + 代码质量  

### P0-2: 循环导入风险
**位置**: `safe_fetcher.py` ↔ `source_registry.py`  
**问题**: `safe_fetcher.py` 导入 `source_registry._validate_safe_url`，`source_registry` 又被 `orchestrator` 导入  
**修复**: 将 `_validate_safe_url` 提取到 `url_utils.py`  
**影响**: 稳定性  

### P0-3: SKILL.md 缺失
**位置**: `.deepflow/domains/research_pro/SKILL.md`  
**问题**: OpenClaw 技能系统的入口文件不存在，OpenClaw 无法识别 Research Pro 为可用技能  
**修复**: 创建标准格式 SKILL.md（触发词、参数、示例）  
**影响**: 功能可用性  

### P0-4: 无 README / 快速开始
**位置**: 缺少 `README.md` 或 `QUICKSTART.md`  
**问题**: 新用户无法在 10 分钟内理解并运行系统，缺少安装说明、代码示例、前置依赖  
**修复**: 创建 README.md（3 分钟快速开始 + 代码示例 + 依赖说明）  
**影响**: 用户体验  

### P0-5: 无 requirements.txt / pyproject.toml
**位置**: 项目根目录  
**问题**: 用户无法知道需要安装什么依赖（`duckduckgo-search` 等），导致 78/115 测试无法运行  
**修复**: 创建 `requirements.txt` 声明外部依赖  
**影响**: 安装可用性 + 测试可运行性  

### P0-6: 未注册到 UnifiedEntry
**位置**: `core/unified_entry.py`  
**问题**: Research Pro 未注册到 DeepFlow 统一入口，无法通过 `UnifiedEntry.run(domain="research_pro")` 启动  
**修复**: 在 `_register_domains()` 中添加 research_pro 领域注册  
**影响**: 架构完整性  

---

## 🟡 P1 — 重要（发布前应修复，共 6 项）

### P1-1: LICENSE 文件缺失
**修复**: 添加 MIT 或 Apache-2.0 开源许可证  

### P1-2: orchestrator.py 函数过长（1,100+ 行）
**问题**: `_execute_mode_c` (150+行), `_evaluate_completion` (150+行), `execute_research` (100+行)  
**修复**: 拆分为 `state_machine.py` / `search_pipeline.py` / `report_generator.py`  

### P1-3: 类型标注不完整
**问题**: 缺少 `from __future__ import annotations`，`spawn_fn` 类型不精确  
**修复**: 统一添加 future import，精确标注所有公共接口  

### P1-4: 关键测试缺失
**缺失测试**:
- SafeFetcher: 超时、TLS、DNS 失败
- CitationVerifier: content_hash 不匹配、网络超时
- Orchestrator: `_execute_search_pipeline()`, `_fallback_search_results()`, `_evaluate_completion()`  
**修复**: 补充 P0 级测试用例  

### P1-5: 未实现的占位逻辑
**位置**: `orchestrator.py` `_generate_analysis_plan()`  
**问题**: 注释说"简化版，实际应调用 LLM"，生产代码不应包含未实现的占位逻辑  
**修复**: 实现完整逻辑或添加明确的 TODO + issue 链接  

### P1-6: 便捷入口函数缺失
**问题**: 缺少 `run_research_pro()` 便捷函数，用户需要手动管理状态机流转  
**修复**: 在 `__init__.py` 添加便捷入口  

---

## 🟢 P2 — 建议（发布后可迭代，共 6 项）

| # | 项目 | 说明 |
|---|------|------|
| P2-1 | 前端状态同步 | 参考 Solution Pro 的 BlackboardBridge 添加进度同步 |
| P2-2 | 关键词生成可配置化 | 将 `_SYNONYMS` 移到配置文件 |
| P2-3 | 复用 BlackboardManager | 从直接文件操作迁移到 Core 的 BlackboardManager |
| P2-4 | 架构图和流程图 | 四阶段状态机图 + Agent 模式 A/B/C 对比图 |
| P2-5 | 调试指南 | 日志位置、常见问题排查、状态恢复说明 |
| P2-6 | CI/CD 集成 | GitHub Actions + codecov 覆盖率报告 |

---

## 亮点总结（值得保留的好设计）

### 安全工程 🛡️
- **SSRF 防护**: DNS 预解析 + IP 黑名单 + 重定向验证，堪称教科书级别
- **路径安全**: 路径遍历防护 + 符号链接检测 + 原子写入
- **并发安全**: RLock 保护 + ThreadPoolExecutor 限制 + 原子文件操作
- **无凭证泄露**: 全代码库扫描零硬编码密钥

### 架构设计 🏗️
- **Cage 契约**: 7 条红线 + 4 层 Harness + 完整 Blackboard 布局，DeepFlow 中最详细的契约
- **四阶段状态机**: planning → confirming → executing → reporting，清晰可控
- **三级 Agent 模式**: A(快速) / B(标准) / C(并行子Agent)，灵活适配不同场景
- **降级策略**: 搜索失败、抓取失败、超时都有合理的 fallback

### 测试质量 🧪
- **TierClassifier**: 100% 覆盖，17 个测试
- **SourceRegistry**: 100% 覆盖，14 个测试（含并发安全、原子写入、损坏恢复）
- **Mock 合理**: 不过度 mock，保留核心逻辑测试

---

## 与 Solution Pro 成熟度对比

| 维度 | Solution Pro | Research Pro | 差距 |
|------|-------------|-------------|------|
| 统一入口 | ✅ UnifiedEntry 注册 | ❌ 未注册 | 🔴 缺失 |
| EntryHarness | ✅ 完整使用 | ❌ 未使用 | 🔴 缺失 |
| 管线编排 | PipelineOrchestrator | 自研状态机 | 🟡 设计差异 |
| BlackboardManager | ✅ 使用 | 直接文件操作 | 🟡 未复用 |
| Cage 契约 | ✅ 完整 | ✅ **更详细** | ✅ 领先 |
| spawn_fn 注入 | ✅ 正确 | ✅ 正确 | ✅ 一致 |
| SKILL.md | ✅ 存在 | ❌ 缺失 | 🔴 缺失 |
| 安全防护 | SecurityValidator | SafeFetcher + URL 验证 | ✅ 等价 |
| 文档 | 有 README | ❌ 无 README | 🔴 缺失 |

---

## 修复路线图

```
Week 1 (P0 修复)
├── P0-1: 重构 subprocess → ddgs_client.py 模块
├── P0-2: 提取 url_utils.py 解决循环导入
├── P0-3: 创建 SKILL.md
├── P0-4: 创建 README.md + QUICKSTART.md
├── P0-5: 创建 requirements.txt
└── P0-6: 注册到 UnifiedEntry

Week 2 (P1 修复)
├── P1-1: 添加 LICENSE
├── P1-2: 拆分 orchestrator.py
├── P1-3: 完善类型标注
├── P1-4: 补充关键测试
├── P1-5: 实现 _generate_analysis_plan
└── P1-6: 添加便捷入口函数

Week 3 (验证 & 发布)
├── 全量测试通过
├── 文档审查
├── GitHub 仓库初始化
└── 发布 v1.0
```

---

## 审计 Agent 详细报告索引

| 报告 | 路径 |
|------|------|
| 代码质量 | `AUDIT_CODE_QUALITY.md` |
| 测试覆盖 | `AUDIT_TEST_COVERAGE.md` |
| 文档与 UX | `AUDIT_DOCS_UX.md` |
| 安全与依赖 | `AUDIT_SECURITY.md` |
| 架构与集成 | `AUDIT_ARCHITECTURE.md` |

---

*5 Agent 并行审计完成 | 2026-06-11 | 小满 🦞*
