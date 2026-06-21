# Super Loop（超级循环）

> DeepFlow 的编排执行层 — 把高质量方案转化为可运行代码

---

## 品牌定位

| 品牌 | 定位 | 阶段 |
|------|------|------|
| **DeepFlow** | 需求→方案（深度流） | ✅ 已成熟 |
| **Super Loop** | 方案→代码（超级循环） | 🚧 Phase 1 待启动 |

**品牌矩阵**：DeepFlow（深度）+ Super Loop（超级）

---

## 核心使命

DeepFlow 产出高质量的 Ship Package（Work Packages + AC + Dependencies），Super Loop 负责：

1. **解析** Ship Package
2. **编排** 编码执行（Codex/Claude Code）
3. **追踪** WP 状态（Kanban）
4. **验证** AC 通过

---

## 两阶段路线

### Phase 1（方案 A）：Hermes + Codex 快速上线

**目标**：1 周内跑通 Ship Package → 编码执行链路

**架构**：
```
忠礼（飞书）
  ↕
Hermes Agent（编排大脑）
  ├── 持久记忆（MEMORY.md + USER.md + Skills）
  ├── Codex Runtime（编码执行引擎）
  │     ├── shell / apply_patch / update_plan
  │     └── GitHub / Gmail 插件
  └── MCP 回调（浏览器/图像/TTS 等）
  ↕
DeepFlow Ship Package（文件系统传递）
```

**当前状态**：

| 组件 | 状态 | 说明 |
|------|------|------|
| Hermes Gateway | ✅ 运行中 | PID 95755, launchd 管理 |
| 飞书连接 | ✅ 已连通 | 2 个 DM channel |
| 模型（Kimi for Coding） | ✅ 可用 | 支持长程任务 |
| Kanban 系统 | ✅ 已初始化 | kanban.db 存在 |
| Codex 认证 | ❌ 未登录 | 需 `hermes auth` |
| Ship Executor Skill | ❌ 未开发 | Phase 1 核心任务 |
| Ship Package 格式 | ❌ 未定义 | 需设计 DeepFlow→Hermes 数据对接 |

### Phase 2（方案 B）：自建编排引擎

**目标**：2-8 月逐步构建核心组件

**架构**：
```
忠礼（飞书）
  ↕
自建编排引擎
  ├── 策展记忆（结构化 + 蒸馏判断器）
  ├── 技能自动创建
  ├── Codex App Server SDK（双向通信）
  ├── Claude Agent SDK（hooks + streaming）
  └── DeepFlow 集成层
  ↕
Codex / Claude Code（执行引擎）
```

**自建优先级**：

| 优先级 | 组件 | 理由 |
|--------|------|------|
| P1 | 编排引擎 | DeepFlow 集成需要定制化逻辑 |
| P2 | 策展记忆 | 蒸馏判断器的基础，Hermes 不够 |
| P3 | 技能自动创建 | DeepFlow domain 技能有特殊需求 |
| P4 | Codex/Claude SDK 封装 | ACP 协议受限，SDK 直连更完整 |

**工作量预估**：25 人周，~6 个月

---

## Phase 1 三步走

### Step 1: 环境准备（今天）
- [ ] 给 Hermes 配置 Codex 认证（`hermes auth`）
- [ ] 确认 Codex Runtime 可用

### Step 2: 开发 Ship Executor Skill（1-3 天）
- [ ] 创建 `~/.hermes/skills/deepflow/ship-executor/SKILL.md`
- [ ] 写 `parse_ship_package.py`（解析 Ship Package JSON）
- [ ] 设计 Ship Package 数据格式（DeepFlow 输出 → Hermes 消费）
- [ ] 利用 Hermes 内置 Kanban 管理 WP 状态

### Step 3: 端到端验证（1 周内）
- [ ] 从 DeepFlow 产出一个简单 Ship Package（2-3 个 WP）
- [ ] 通过飞书发给 Hermes，触发 Ship Executor Skill
- [ ] Hermes 调 Codex 执行编码
- [ ] 验证：WP 完成 + AC 通过 + 代码可运行

---

## 调研资料

详见：`.deepflow/docs/research/archive/2026-06-16_orchestration_engine_decision/`

| 报告 | 大小 | 说明 |
|------|------|------|
| `codex_integration_research.md` | 48KB | Codex 集成方式 |
| `claude_code_integration_research.md` | 31KB | Claude Code 集成方式 |
| `openclaw_orchestration_capabilities.md` | 15KB | OpenClaw 编排能力 |
| `industry_orchestration_patterns.md` | 26KB | 业界编排模式 |
| `architecture_pattern_comparison.md` | 43KB | 架构选型对比 |
| `hermes_agent_research.md` | 47KB | Hermes Agent 编排 Codex |
| `hermes_correction_report.md` | 16KB | Hermes 纠错报告 |
| `plan_b_implementation_research.md` | 79KB | 方案 B 实现调研 |
| `hermes_skill_development_guide.md` | 24KB | Hermes Skill 开发指南 |
| `SYNTHESIS_REPORT.md` | 11KB | 综合报告 |
| `DECISION.md` | 5KB | **决策记录** |

**总调研资料**：~340KB

---

## 决策时间线

| 日期 | 事件 |
|------|------|
| 2026-06-09 | 忠礼提出：OpenClaw 能否借鉴 Hermes 的长程执行能力 |
| 2026-06-16 | 10 路并行调研，产出 340KB 报告 |
| 2026-06-16 | 最终决策：方案 A 先行 → 方案 B 渐进 |
| 2026-06-18 | 项目命名：**Super Loop** |
| 2026-06-18 | 文档归档，准备启动 Phase 1 |

---

*Created: 2026-06-18 | Status: Phase 1 待启动*
