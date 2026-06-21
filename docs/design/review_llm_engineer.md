# LLM 工程视角评审 — Blackboard 重构方案

> **评审人**: LLM Engineer（sub-agent）
> **日期**: 2026-06-21
> **评审对象**: `blackboard_system_redesign.md` v2.0.0-draft

---

## 核心判断（一句话）

**方案对 LLM 消费路径几乎零影响**——因为 LLM Worker 从不自己拼接路径，它们只是从 prompt 模板里复制 `_get_stage_path()` 预计算好的完整路径。路径多一层 `solution/` 对 LLM 来说只是字符串多了 49 个字符，不影响出错概率。真正需要关注的是 prompt 膨胀和路径注入机制的健壮性。

---

## 逐项评审

### 1. 路径从 2 层变 3 层，LLM 拼接出错概率增加多少？

**结论：增加 0%。LLM 不拼接路径。**

实测代码证据：

```python
# task_builder.py line 96-113
def _get_stage_path(session_id: str, stage_name: str) -> str:
    if stage_name in STAGE_PATH_REGISTRY:
        return f"{_DEEPFLOW_BASE}/blackboard/{session_id}/{STAGE_PATH_REGISTRY[stage_name]}"
    return f"{_DEEPFLOW_BASE}/blackboard/{session_id}/{stage_name}"
```

`task_builder.py` 中有 **29 处** `_get_stage_path` 调用。每个 Worker 的 prompt 模板里，路径是**预计算好的完整字符串**，LLM 只需要 copy-paste 到 `write(path=...)` 或 `read(path=...)` 里。

| 指标 | 旧路径 | 新路径 |
|:---|:---|:---|
| 示例 | `.deepflow/blackboard/{sid}/stages/planning.json` | `.deepflow/blackboard/projects/{slug}/runs/{ts}/solution/stages/planning.json` |
| 字符数 | ~54 | ~103 |
| 增量 | — | +49 chars/reference |
| 10 次引用增量 | — | +490 chars/prompt |

**经验判断**：490 chars 在一个通常 3000-8000 chars 的 Worker prompt 里占比 <10%，对 LLM 的路径复制准确率无实质影响。LLM 复制字符串的错误率主要取决于字符串是否被截断或换行打断，而不是长度。

**唯一风险**：如果 prompt 过长导致 LLM 注意力分散（lost-in-the-middle 效应），但 +490 chars 远不到触发阈值。

### 2. LLM 的 `write` 工具是否支持相对路径？相对 vs 绝对？

**结论：支持相对路径（相对 workspace），当前已经在用。新方案继续用相对路径即可。**

OpenClaw 的 `write` 工具 path 参数是相对于 workspace 目录（`/Users/allen/.openclaw/workspace`）的。当前 `_get_stage_path` 返回的就是 `.deepflow/blackboard/...` 这样的相对路径。

新方案下路径变成 `.deepflow/blackboard/projects/{slug}/runs/{ts}/solution/stages/planning.json`，仍然是相对路径，没有问题。

**相对路径 vs 绝对路径的取舍**：
- 相对路径（当前方案）✅：跨环境可移植，prompt 里更短
- 绝对路径 ❌：换机器就坏，prompt 更长

**建议**：保持相对路径，不需要改。

### 3. 新结构下 LLM 需要知道哪些路径信息？从哪里获取？

**结论：LLM 只需要知道"完整路径字符串"，来源是 prompt 模板注入（当前机制），不需要新增任何信息通道。**

当前机制已经完备：

```
Python 代码（_get_stage_path）
  → 计算完整路径
  → 注入到 prompt 模板（如 "将结果写入 {path}"）
  → LLM 从 prompt 中读取路径
  → LLM 调用 write(path=...) 或 read(path=...)
```

新方案只需要改 `_get_stage_path` 的实现：

```python
# 改前
def _get_stage_path(session_id: str, stage_name: str) -> str:
    return f"{_DEEPFLOW_BASE}/blackboard/{session_id}/{STAGE_PATH_REGISTRY[stage_name]}"

# 改后
def _get_stage_path(session_id: str, stage_name: str) -> str:
    # session_id 现在是 "{slug}/runs/{timestamp}" 格式
    # 加上 domain 前缀
    return f"{_DEEPFLOW_BASE}/blackboard/{session_id}/{domain}/{STAGE_PATH_REGISTRY[stage_name]}"
```

**不需要**：
- ❌ 环境变量
- ❌ 配置文件
- ❌ LLM 自己拼接路径的任何逻辑

### 4. LLM 频繁拼错路径的降级策略

**结论：当前架构下 LLM 几乎不会"拼错"路径（因为是复制），但可能出现的错误场景和降级策略如下：**

| 错误场景 | 原因 | 降级策略 |
|:---|:---|:---|
| 路径被 prompt 截断 | prompt 过长，路径在 context window 边缘 | 路径放在 prompt **末尾**（而非开头），利用 recency bias |
| LLM 输出时路径变形 | 模型幻觉（罕见但存在） | `completion_handler.py` 校验写入路径是否存在于预期目录 |
| `session_id` 含特殊字符 | slug 里有空格或 Unicode | slug 生成时强制 ASCII + hyphen（方案已覆盖） |
| 路径多一层导致 LLM 漏掉中间段 | 如写了 `stages/planning.json` 漏掉 `solution/` | **不需要降级**——因为路径是完整字符串注入的，LLM 不会自己构造 |

**真正的降级策略应该是 Python 侧的**：
- `_get_stage_path` 返回路径前，`os.makedirs` 确保目录存在
- `write` 工具本身已有自动创建父目录的能力（OpenClaw 内置）

### 5. 是否符合 AI Native 原则？

**结论：基本符合。路径结构面向人类可读性是可以接受的，因为 LLM 不消费目录结构——它只消费完整路径字符串。**

AI Native 原则检验：

| 原则 | 检验 | 结论 |
|:---|:---|:---|
| 语义任务用 LLM，确定性任务用代码 | 路径管理 = 确定性任务 → 由 `_get_stage_path`（代码）负责 ✅ | ✅ 符合 |
| LLM 是消费者 | LLM 只消费完整路径字符串，不关心目录层级 ✅ | ✅ 符合 |
| 不过度设计 | 多一层 `solution/` 是为了人类可读 + 跨域隔离，不是为了"架构美感" ✅ | ✅ 符合 |
| 路径要简单、可预测 | 新路径 103 chars vs 旧路径 54 chars，"可预测性"不变（都是确定性的） ✅ | ✅ 符合 |

**唯一扣分项**：`project.json`、`run.json`、`index.json` 这些元数据文件是面向 Dashboard/人类的，LLM 不需要它们。但这不是"过度设计"——它们是 Loop Engine 和 A/B 对比的基础设施，有明确用途。

### 6. 盲点发现

**盲点 1：prompt 里的路径引用密度**

`task_builder.py` 有 29 处路径引用。一个完整的 orchestrator prompt 可能引用 5-10 个不同阶段的路径。新方案下每个路径 +49 chars，10 个路径 = +490 chars。

当前 Worker prompt 已经很长（3000-8000 chars），+490 chars 不致命，但值得监控。如果未来 prompt 继续膨胀，可能需要：
- 把路径引用集中到 prompt 末尾的"输出路径"区块
- 或者用变量占位符（`{{OUTPUT_PATH}}`）在 prompt 末尾统一替换

**盲点 2：`_get_stage_path` 是单点**

当前所有路径生成都走 `_get_stage_path` 一个函数。这是好事（改一处即可），但也意味着：
- 如果这个函数出 bug（如 `session_id` 格式不对），所有 Worker 的路径全错
- 建议：加一个 `assert "/" in session_id` 的格式校验（新方案下 session_id 必须含 `/`）

**盲点 3：Worker 的 `read` 路径没有讨论**

方案重点讨论了 `write` 路径，但 Worker 也需要 `read` 上游阶段的输出。例如 Stage 3 的 Worker 需要 read Stage 1 和 Stage 2 的输出。这些 read 路径也是 `_get_stage_path` 生成的，同样会变长。方案没有单独讨论 read 路径的影响——但因为机制相同，影响也相同（+49 chars/reference）。

**盲点 4：跨域数据传递的路径暴露**

方案 D5 说 Ship Pro 从 `solution/final_result.json` 读取输入。这意味着 Ship Pro 的 prompt 里需要包含 Solution Pro 的输出路径。当前 Ship Pro 的 `run_pipeline.py` 是怎么获取这个路径的？如果是硬编码的，需要同步更新。如果是动态获取的，需要确保新格式兼容。

**盲点 5：LLM 的 context window 里路径的"可区分性"**

当 prompt 里同时出现 10 个类似的路径时：
```
.deepflow/blackboard/projects/x/runs/20260621_104400/solution/stages/planning.json
.deepflow/blackboard/projects/x/runs/20260621_104400/solution/stages/design.json
.deepflow/blackboard/projects/x/runs/20260621_104400/solution/stages/audit.json
...
```

这些路径只有最后一段不同（`planning` vs `design` vs `audit`），前面 90+ 字符完全相同。LLM 在"选择正确路径"时可能因为路径过于相似而选错（尤其是并行阶段引用多个路径时）。

**缓解**：在 prompt 里用标签标注每个路径的用途（当前已经在做，如"前置输入1. 设计方案: {path}"），这足够防止混淆。

---

## 具体建议

### 必须做（P0）

1. **保持 `_get_stage_path` 作为唯一路径生成入口**。新方案的路径变更只改这一个函数，不动 prompt 模板。
2. **新方案下 `session_id` 格式校验**。在 `_get_stage_path` 入口加 `assert` 确保 `session_id` 符合 `{slug}/runs/{timestamp}` 格式，尽早暴露 bug。
3. **确保 `write` 工具的自动建目录行为在新路径下正常工作**。新路径多了 `solution/`、`ship/` 等中间目录，需要验证 `write` 能自动 `mkdir -p`。

### 建议做（P1）

4. **路径引用集中化**。把 prompt 里散落的路径引用集中到一个"## 输出路径"区块，减少 lost-in-the-middle 风险。格式如：
   ```
   ## 你的输出路径
   - 本阶段输出: {output_path}
   - 需要读取的上游: {upstream_paths}
   ```
5. **Ship Pro 跨域路径传递机制明确化**。方案 D5 描述了数据流，但没有说清楚 Ship Pro 的 prompt 里如何获取 Solution Pro 的输出路径。建议显式设计这个传递机制。

### 不需要做

6. **不需要为 LLM 设计"路径纠错"机制**。LLM 不拼路径，不需要纠错。如果 write 失败，Python 侧的 `completion_handler` 自然会检测到。
7. **不需要环境变量或配置文件传递路径**。当前的 prompt 注入机制已经足够，新增信息通道是过度设计。

---

## 总结

从 LLM 工程视角，这个方案**可以安全实施**。路径深度增加对 LLM 的影响为零（因为 LLM 不构造路径），唯一的实际影响是 prompt 长度增加约 490 chars（<10%），在可接受范围内。

需要关注的真正风险不在 LLM 侧，而在 **Python 侧的路径生成逻辑**（`_get_stage_path` 的改造）和 **跨域数据传递的路径解析**（Ship Pro 如何找到 Solution Pro 的输出）。
