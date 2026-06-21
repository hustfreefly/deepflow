## 评审：执行可靠性视角

### 评分：CONDITIONAL

### 理由（逐条对应 4 个问题）

#### 1. Fix 1（简化 delivery 逻辑）能否确保不再犯错？

**不能确保。** 原因：

- Fix 1 把分支选择逻辑从"隐式"改为"显式"，但仍然依赖 LLM 读取 Runtime 区域的 `channel=xxx` 并做出正确判断。
- **核心矛盾**：原方案规则已经写得足够清楚（"禁止硬编码 channel"、"必须先判断当前会话类型"），但主 Agent 完全无视。**规则清楚 ≠ 规则被执行。**
- Fix 1 缺少的关键要素：**默认值兜底**。如果 LLM 不判断 channel 就直接用默认值（`{"mode": "announce"}`），那 90% 的场景（webchat）就自动正确了。当前方案没有这个兜底——LLM 仍然需要"主动选择"分支 A。

#### 2. Fix 2（pre-flight self-check）步骤是否足够？

**步骤本身有逻辑缺陷：**

- `exec: echo "当前会话 channel: {从 Runtime 区域读取}"` — 这不是真正的检查，只是让 LLM 复述它认为自己知道的东西。如果 LLM 读错了 Runtime，echo 也是错的。
- 写入 `.cron_preflight.json` 本身也是 LLM 执行的步骤，可以被跳过或写错。
- **遗漏的检查点**：
  1. 没有验证 `channel` 值是否合法（只检查了"是否 feishu"，没有检查空值/未知值）
  2. 没有在 cron 创建后验证 delivery 配置是否与 preflight 一致
  3. 没有"创建后回读"步骤——创建 cron 后应该读回 job 配置确认 delivery 字段正确

#### 3. 是否过于依赖"规则写得更清楚"？

**是的，这是方案的根本弱点。**

- 原方案有 3 条禁止规则 + 3 条选择规则 → 被无视
- 新方案有 4 条 preflight 步骤 + 3 条 delivery 规则 + 4 条禁止规则 → 更多规则
- **LLM 的概率性本质**：规则从 10 条增加到 20 条，每条被遵守的概率从 95% 变成整体 60%（0.95^20）。规则越多，整体执行可靠性越低。
- **比"写更多规则"更可靠的方案**：

| 方案 | 可靠性 | 当前方案是否采用 |
|------|--------|:---:|
| **代码层面保证**：delivery 配置由启动脚本（Python/Shell）生成，不经过 LLM 判断 | 极高 | ❌ |
| **默认值兜底**：默认 `{"mode": "announce"}`，只有显式需要时才加 channel/to | 高 | ❌ |
| **去掉分支选择**：永远用 `{"mode": "announce"}`，飞书场景用 announce 也能到达 | 高（需验证） | ❌ |
| **模板化**：cron 创建代码整体由模板生成，LLM 只填 session_id/base_path | 高 | 部分（代码模板已有，但 delivery 字段仍是 LLM 选择） |

#### 4. 有没有更简单的方案？

**有。方案如下：**

**核心思路：消灭分支选择，让 LLM 没有犯错的机会。**

```
# 最简方案：delivery 永远用默认值

delivery: {"mode": "announce"}

# 就这样。不需要 channel，不需要 to，不需要 open_id。
# announce 模式自动路由到当前会话。
# 用户在 webchat 聊 → 通知到 webchat
# 用户在飞书聊 → 通知到飞书
# 完美匹配用户洞察："在哪聊就发哪"
```

**如果飞书场景确实需要指定 to**（announce 默认不能到达飞书），则：

```
# 次简方案：delivery 由启动脚本生成

# 在 solution_pro_init.sh（或 Python 启动脚本）中：
DELIVERY_CONFIG='{"mode": "announce"}'
if [ "$SESSION_CHANNEL" = "feishu" ]; then
    OPEN_ID=$(grep FEISHU_USER_OPEN_ID "$HOME/.openclaw/workspace/.credentials/feishu.env" | cut -d= -f2)
    DELIVERY_CONFIG="{\"mode\": \"announce\", \"channel\": \"feishu\", \"to\": \"$OPEN_ID\"}"
fi

# 写入 execution_plan.json，LLM 直接读取使用
echo "{\"delivery\": $DELIVERY_CONFIG}" >> "$BASE_PATH/.delivery_config.json"
```

这样 LLM 只需要读取文件并使用，不需要做任何判断。

---

### 改进建议

1. **P0 - 消灭分支选择**：将 delivery 配置改为默认值 `{"mode": "announce"}`，不需要 LLM 做任何 channel 判断。如果飞书场景确实需要指定 to，由启动脚本生成配置写入文件，LLM 只读取不判断。

2. **P1 - 如果保留分支逻辑，必须有代码兜底**：在 cron 创建后，增加一个 `exec` 步骤回读 cron job 配置，验证 delivery 字段与预期一致。这不是 LLM 自检，而是代码验证。

3. **P2 - pre-flight check 简化**：当前的 4 步 preflight 过于复杂。简化为 1 步：读取 `.delivery_config.json`（由启动脚本生成），直接使用。

4. **P3 - Fix 3（orchestrator abort 联动）方向正确**，但方案 A 的"15 分钟无活动判定死亡"可能误判（长阶段可能超过 15 分钟）。建议改为 30 分钟或从 execution_plan.json 读取预期阶段时长。

---

### 最核心的一个建议

**消灭 LLM 的分支选择权。**

当前方案的本质问题是：让一个概率性执行者（LLM）做确定性判断（if channel=webchat then A else B）。这本身就是设计错误。

正确做法：**把确定性判断移到确定性代码中（启动脚本），LLM 只负责读取结果并使用。**

或者更简单：**永远用 `{"mode": "announce"}`，让 announce 的默认行为覆盖所有场景。** 用户说"就这么简单"——方案也应该"就这么简单"。
