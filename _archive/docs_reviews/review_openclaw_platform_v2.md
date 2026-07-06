# 第二轮评审报告：OpenClaw 平台专家

> **评审日期**: 2026-06-25  
> **评审对象**: Ship Pro AI Native 改造方案 V2  
> **评审人**: OpenClaw 平台专家（Sub-agent）  
> **第一轮评分**: 6.5/10

---

## V1 → V2 改进追踪

| # | V1 问题 | 严重度 | V2 修复状态 | 说明 |
|---|---------|--------|-----------|------|
| 1 | `spawn_params` 缺少 `cwd` | **P0** | ✅ **已修复** | §7 文件改造清单明确 `start_ship_pro.py` 改造为"spawn_params（含 cwd）"；§5.1 Orchestrator prompt 中 sessions_spawn 规范强制要求 `cwd="/Users/allen/.openclaw/workspace/.deepflow"` |
| 2 | Worker spawn 未要求 `cwd` | **P0** | ✅ **已修复** | §5.1 明确写出 Worker sessions_spawn 规范（含 cwd 注释 ⚠️ 必须传 cwd），Judge Worker spawn 也同样包含 cwd |
| 3 | `io_helper.py` 不存在 | **P1** | ✅ **已修复** | §3 完整设计 12 个命令；§7 迁移步骤明确"从 run_pipeline.py 提取 I/O + 护栏 → io_helper.py"，预估 ~400 行 |
| 4 | `io_helper.py` API 未完整定义 | **P1** | ✅ **已修复** | §3.1 列出 12 命令清单（名称+类型+用途）；§3.2 详细定义 5 个护栏命令的参数、逻辑、输出 JSON schema；§3.3-3.5 定义状态写入、断点续接、上下文管理的完整接口 |
| 5 | SKILL.md V5.0 缺少入口守卫设计 | **P1** | ✅ **已修复** | §8.2 定义了 Step 0 防偏检查：3 项确认清单（不直接写代码、按 SKILL.md 步骤启动、有正确输入路径），不满足则停止向用户确认 |

**修复率: 5/5 = 100%**

---

## 新评分

- **总评分**: **8.5/10**（V1: 6.5/10，提升 +2.0）
- **核心判断**: V1 的 5 个 P0/P1 问题全部修复，且修复质量高——不是简单补丁，而是系统性地融入了架构设计（cwd 进入 sessions_spawn 规范、io_helper.py 完整 CLI 设计、入口守卫成为 SKILL.md Step 0）。方案已具备进入实施阶段的条件。

---

## V2 新发现的问题

### P2（建议改进，不阻塞实施）

| # | 问题 | 说明 | 建议 |
|---|------|------|------|
| 1 | `maxSpawnDepth` 未显式确认 | Main → Orchestrator → Worker 是 2 层嵌套 spawn。V1 评审提到需确认 `maxSpawnDepth` 配置 ≥ 2，V2 未回应此点。 | 实施前 `openclaw config get maxSpawnDepth` 确认 ≥ 2（默认值通常足够）。 |
| 2 | cwd 硬编码为绝对路径 | §5.1 中 `cwd="/Users/allen/.openclaw/workspace/.deepflow"` 硬编码。虽然当前环境正确，但降低了可移植性。 | 建议 `start_ship_pro.py` 中用 `DEEPFLOW_HOME` 变量注入到 Orchestrator prompt 模板，而非硬编码。 |
| 3 | `exec` 环境约束仅在 prompt 中提醒 | §5.1 prompt 写了"⛔ exec 中禁止 `from openclaw import ...`"，但这是 prompt 级约束，LLM 可能在边界情况下违反。 | 可接受（prompt 约束对 LLM 足够强），实施时可在 io_helper.py 的 shebang/header 中加注释强化。 |

### 无新 P0/P1 问题

V2 没有引入新的平台能力层面的 P0/P1 问题。新增的功能（Judge Worker、compact-history、resume-context、.heartbeat）都正确使用了 OpenClaw 平台能力。

---

## V2 亮点（相比 V1 的额外改进）

1. **io_helper.py 12 命令完整设计**：不仅修复了"API 未定义"问题，还超出了预期——区分了 I/O、护栏、恢复、调试四类命令，每个都有输入输出 schema。

2. **双重验证机制**（validate-format + validate-quality）：保留了 Python gate 函数的语义校验能力，避免了"质量门控退化"这个跨域问题。

3. **断点恢复设计**（resume-context + .heartbeat）：解决了 V1 完全没有断点续接的问题，`.heartbeat` 文件也回应了我 V1 的 P2 建议。

4. **上下文膨胀防护**（compact-history）：前瞻性设计，Orchestrator 在长管线中不会因 context 溢出而丢失关键信息。

5. **错误恢复策略菜单**：给 Orchestrator 提供了明确的恢复决策表，减少了 LLM 在错误场景下的"自由发挥"空间。

6. **stage-dependencies.json**：将阶段依赖从硬编码变为显式声明，`can-parallel` 基于此做确定性判断，比 LLM 猜测可靠。

---

## 是否可以进入实施阶段？

- [x] **是**
- [ ] 需要第三轮

**理由**：
1. 所有 P0/P1 问题已修复（5/5）
2. 无新 P0/P1 问题
3. P2 问题均为"实施时注意"级别，不阻塞
4. 迁移策略稳健（保留旧 run_pipeline.py、分步迁移、回滚 SOP 完整）
5. 验证计划覆盖了关键场景（单阶段、多阶段、断点恢复、超时、回滚）

**实施建议**：
- 优先修复 P2 #2（cwd 变量化），在 `start_ship_pro.py` 中用 `DEEPFLOW_HOME` 常量注入 prompt 模板
- 实施第一步先确认 `maxSpawnDepth` 配置（P2 #1，5 秒检查）
- io_helper.py 的 12 个命令建议分批实现：先 I/O 类（read-input, write-status, write-completed），再护栏类（validate-format, validate-quality, check-retry-limit, validate-plan, can-parallel, check-budget），最后恢复/调试类

---

*评审完成 | 2026-06-25 21:12*
