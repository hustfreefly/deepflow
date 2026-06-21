# DeepFlow 按功能模块开发恢复手册 — Part 4: Research Pro

---

## 4. Research Pro（深度研究）

### 4.1 概述

独立研究域，支持用户输入任意研究主题，自动生成带行内引用标注的深度研究报告。

核心架构: 四阶段状态机管线 (Plan → Confirm → Execute → Report)
Agent模式: 三级切换 (A/B/C), 遵循Simplicity First
防幻觉: Source Registry + 五步引用验证循环
搜索: 三阶段编排 (Breadth-First → Depth-First → Structured Data)
引用: 行内标注 [N] + 文末参考列表 + 置信度标签

差异化定位: "通用研究用Gemini, 投资研究用ResearchPro"

### 4.2 发布就绪审计（6/11）

5个Agent并行审计（代码质量/测试覆盖/文档UX/安全/架构）

审计前评级: 🟡 YELLOW — 需要修复12项问题后方可发布

### 4.3 13项修复（全部完成，6/11）

| # | 级别 | 修复项 | 状态 |
|:---|:---|:---|:---|
| P0-1 | 🔴 | 搜索架构重构（主路径web_search，DDGS降级） | ✅ |
| P0-2 | 🔴 | 去subprocess（提取ddgs_client.py） | ✅ |
| P0-3 | 🔴 | 解循环导入（提取url_utils.py） | ✅ |
| P0-4 | 🔴 | 创建SKILL.md | ✅ |
| P0-5 | 🔴 | 创建README.md | ✅ |
| P0-6 | 🔴 | 创建requirements.txt | ✅ |
| P0-7 | 🔴 | UnifiedEntry注册 | ✅ |
| P1-1 | 🟡 | 添加LICENSE (MIT) | ✅ |
| P1-2 | 🟡 | 类型标注完善 | ✅ |
| P1-3 | 🟡 | 占位逻辑标注TODO | ✅ |
| P1-4 | 🟡 | 补充关键测试 | ✅ |
| P1-5 | 🟡 | 便捷入口函数 | ✅ |
| P1-6 | 🟡 | orchestrator代码组织 | ✅ |

### 4.4 新增/修改文件

| 文件 | 操作 | 说明 |
|:---|:---|:---|
| url_utils.py | 🆕 | URL安全验证（从source_registry提取） |
| ddgs_client.py | 🆕 | DuckDuckGo搜索客户端（替代subprocess） |
| SKILL.md | 🆕 | OpenClaw技能入口文件 |
| README.md | 🆕 | 开源项目文档 |
| requirements.txt | 🆕 | 依赖声明 |
| LICENSE | 🆕 | MIT License |
| tests/test_url_utils.py | 🆕 | URL安全验证测试(15 tests) |
| orchestrator.py | ✏️ | 搜索架构重构+去subprocess+类型标注+web_search_fn注入 |
| source_registry.py | ✏️ | URL验证迁移到url_utils |
| safe_fetcher.py | ✏️ | URL验证迁移到url_utils |
| __init__.py | ✏️ | 添加run_research_pro便捷入口 |
| tests/test_safe_fetcher.py | ✏️ | 补充6个测试 |
| core/unified_entry.py | ✏️ | 注册research_pro领域 |

### 4.5 搜索架构（修复后）

```
搜索请求
   │
   ├── 主路径: _search_web()
   │     → OpenClaw web_search工具（Brave/Perplexity/Gemini...）
   │     → 通过web_search_fn注入
   │
   ├── 降级: _search_ddgs()
   │     → DuckDuckGo Search (ddgs_client.py, 直接import)
   │     → 仅在web_search不可用或返回空时调用
   │
   └── 最终降级: _fallback_search_results()
         → 基于关键词的结构化降级数据
```

### 4.6 测试结果

```
非orchestrator模块: 87/87 passed (18.98s)
Orchestrator模块:    49/49 passed (107.68s)
总计:               136/136 passed ✅
```

### 4.7 关键决策

#### D1: 搜索架构重构
旧: subprocess.run执行动态Python代码字符串（DDGS）
新: web_search主路径 + ddgs_client.py直接import降级
原因: subprocess代码注入风险是危险反模式

#### D2: 解循环导入
safe_fetcher.py ↔ source_registry.py 互导
修复: 提取url_utils.py作为共享工具

### 4.8 发布就绪评估

| 维度 | 修复前 | 修复后 |
|:---|:---|:---|
| 代码质量 | 🟡 YELLOW | 🟢 GREEN |
| 测试覆盖 | 🟡 YELLOW (37/115) | 🟢 GREEN (136/136) |
| 文档UX | 🟡 YELLOW | 🟢 GREEN |
| 安全 | 🟢 GREEN | 🟢 GREEN |
| 架构集成 | 🟡 YELLOW | 🟢 GREEN |
| 总体 | 🟡 YELLOW | 🟢 GREEN |
