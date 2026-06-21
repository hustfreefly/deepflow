# 系统架构师视角评审：DeepFlow Blackboard v2.0.0-draft

> **评审人**: 系统架构师视角（subagent）
> **评审日期**: 2026-06-21
> **评审对象**: `blackboard_system_redesign.md` v2.0.0-draft

---

## 核心判断（一句话）

**三层结构 `projects/{slug}/runs/{ts}/` 的方向正确，能解决 P1-P5；但方案内部存在结构性矛盾（D5 数据流描述的 `input/`/`output/` 在 3.1 目录树中不存在），且跨域数据消费的寻址机制没有定义清楚。修好这些可以进入实施。**

---

## 逐项评审（对应 6 个问题）

### 1. 三层结构 `projects/{slug}/runs/{ts}/` 是否合理？

**合理。没有更简洁的替代方案能同时满足需求。**

分析：
- `projects/{slug}/` 提供人类可读的项目分组 → Dashboard 友好
- `runs/{ts}/` 提供运行隔离 → 解决 P1（覆盖问题）
- 第三层域目录（`spec/`、`solution/`、`ship/`）提供域分离 → 解决 P2（套娃问题）

尝试过的替代方案及否决理由：
- ~~`{slug}/{ts}/`（两层）~~：丢失域分离，Ship Pro 又会嵌套进 Solution Pro
- ~~`{slug}/{ts}_{domain}/`（扁平化）~~：跨域数据流变成跨目录跳转，逻辑上是一个 run 的东西被拆散了
- ~~`{hash}/{ts}/`（hash 代替 slug）~~：人类不可读，违反 LLM 可预测性原则

**一个改进建议**：考虑在 `projects/{slug}/` 和 `runs/` 之间不加额外层级。当前设计已经就是这样，确认这是对的。

### 2. spec/solution/ship 三个域放在 run 内，数据流方向是否清晰？

**方向基本清晰，但方案文档内部有矛盾，需要修正。**

**矛盾点**：
- 3.1 目录树显示：`spec/`、`solution/`、`ship/` 是 run 下的平级兄弟
- D5 数据流描述却用了 `input/living_spec.json` 和 `output/final_result.json`，这些路径在 3.1 的树中不存在

**需要明确回答的问题**：
- Ship Pro 怎么读 Solution Pro 的输出？答案应该是：`ship/` 域读 `../solution/final_result.json`
- 这个跨域引用是隐式约定（硬编码相对路径）还是显式声明（run.json 里记录上游路径）？

**建议**：采用显式声明。在 `run.json` 中增加字段：
```json
{
  "data_flow": {
    "solution": {
      "input_from": "spec/living_spec.json",
      "output": "solution/final_result.json"
    },
    "ship": {
      "input_from": "solution/final_result.json",
      "output": "ship/final_result.json"
    }
  }
}
```
好处：(1) 数据流可审计 (2) Loop Engine 迭代时可以修改 data_flow (3) Dashboard 可以可视化数据链路

**如果不加这个**，至少要在设计文档中明确写出：域间通过 `../{sibling}/final_result.json` 寻址，这是约定而非隐式行为。

### 3. Research Pro 独立存放是否合理？

**当前合理。但需要预留一个轻量级的引用机制。**

当前 Research Pro 跟主链路无数据流，放进 `projects/` 是假关联。独立存放是正确的。

**但如果未来 research 输出要喂给 Solution Pro**，有两种方案：

| 方案 | 机制 | 代价 |
|:---|:---|:---|
| **A: 复制引用** | Loop Engine 启动 run 时，把 research 输出复制到 `run/spec/research_input/` | 数据冗余，但 run 自包含 |
| **B: 路径引用** | `run.json` 加 `external_refs: [{type: "research", path: "research/20260620_xxx/"}]` | 零冗余，但 run 不自包含 |

**建议**：现在不实现，但在 `run.json` schema 中预留 `external_refs` 字段（默认空数组）。零成本保险。

### 4. slug 生成策略（自动生成+冲突加后缀）是否可行？

**可行，但有一个边界条件需要处理。**

slug 生成逻辑：
```python
def generate_slug(topic: str, existing_slugs: set) -> str:
    base = to_slug(topic)  # "DeepFlow 可观测性" → "deepflow-observability"
    if base not in existing_slugs:
        return base
    # 冲突：加 hash 后缀
    h = hashlib.md5(topic.encode()).hexdigest()[:6]
    return f"{base}-{h}"
```

**边界条件**：
- 同一个 topic 在不同语境下可能生成相同 slug（如"DeepFlow 架构设计"和"DeepFlow 系统架构设计"都可能 → `deepflow-architecture-design`）
- 这不是 hash 冲突，是语义冲突。hash 后缀能解决唯一性，但两个语义不同的项目看起来很像

**建议**：
1. slug 生成后，**首次创建项目时打印给用户确认**（"项目 slug: deepflow-observability，按 Y 确认"）。后续自动继承。
2. 如果用户不想交互，提供 `--slug` 参数覆盖
3. 这符合"方案 C（用户指定）为兜底，方案 A 为默认"的混合策略

**不建议**纯 hash（方案 B）：180 个目录变 180 个 hash，人类无法导航。

### 5. 这个设计能支撑 Loop Engine 的未来需求吗？缺什么？

**能支撑基本场景。缺三个东西：**

**缺 1：Run 之间的因果链**
Loop Engine 的 Iteration #2 是基于 Iteration #1 的 feedback 跑的。当前设计没有机制表达"Run B 是 Run A 的迭代"。

建议：`run.json` 增加 `parent_run_id` 字段：
```json
{
  "run_id": "20260622_100000",
  "parent_run_id": "20260621_104400",  // null for first run
  "iteration": 2,
  "change_summary": "基于 V1 反馈修改了 REQ-003 和 REQ-015"
}
```

**缺 2：Feedback 的存放位置**
3.4 节提到 `feedback/` 但没有给出目录结构。Feedback 是 Loop Engine 的核心产物，需要明确：
```
runs/{ts}/
  └── feedback/
      ├── user_review.json      ← 用户评审
      ├── test_results.json     ← 测试结果
      └── change_requests.json  ← 变更请求（喂给下一轮 Spec Pro）
```

**缺 3：跨 Run 对比的支撑**
P5 要求 A/B 对比。当前设计靠 `runs.json` 列出所有 run，但没有定义对比的机制。

建议：不需要专门的对比目录。提供 `blackboard_manager.py compare(run_a, run_b)` API，读取两个 run 的 `final_result.json` 和 `stages/` 生成 diff 报告。这是工具层的事，不是目录结构的事。

### 6. 盲点与潜在问题

**盲点 1：3.1 目录树和 D5 数据流描述不一致（已在上文指出）**

3.1 的树：
```
runs/{ts}/
  ├── spec/
  ├── solution/
  │   └── stages/
  └── ship/
      └── stages/
```

D5 的数据流：
```
spec → input/living_spec.json
solution → output/final_result.json
ship → output/ship_package.json
```

**这两个不是同一个结构。** 需要统一。要么改树（加 `input/`/`output/`），要么改 D5（用域名寻址）。我倾向于改 D5 匹配 3.1 的树——少一层目录，LLM 拼路径更简单。

**盲点 2：run.json 的单复数混乱**

文档中同时出现：
- `run.json`（每次运行一个）
- `runs.json`（项目级，所有 run 的索引）
- 3.3 节标题是 "project.json 和 run.json 设计"，但内容展示了 `runs.json`

需要明确：
- `project.json`：项目级元数据，一个项目一个
- `runs.json`：运行索引，一个项目一个（不是每个 run 一个）
- `run.json`：运行元数据，每个 run 一个

三者职责不同，文档需要统一命名。

**盲点 3：时间戳没有时区**

`20260621_104400` 是本地时间还是 UTC？如果忠礼在不同时区跑（比如出差到美国），或者未来有多用户，时间戳可能混淆。

建议：时间戳用 UTC，格式 `20260621T024400Z`。或者保持本地时间但在 `run.json` 中记录 timezone offset。

**盲点 4：并发安全**

如果两个 Solution Pro 同时启动（比如 cron watcher 误触发），它们会创建不同的 run 目录（因为时间戳不同），所以不会覆盖。但 `runs.json` 和 `project.json` 会被并发写入。

建议：`runs.json` 采用 append-only 策略（每次运行完成追加一行 JSONL），不用 JSON 数组。或者用文件锁。对于单用户系统，JSONL 更简单。

**盲点 5：`state/` 子目录的代价**

D3 提议把所有 `.xxx` 状态文件放入 `state/` 子目录。这解决了 P3（状态散落），但增加了一层目录。

权衡：
- 当前：状态文件在域目录根 → 跟交付文件混在一起
- 新方案：`state/` 子目录 → 分离清晰，但 LLM 拼路径多一层

**我支持加 `state/`**。状态文件是内部实现细节，LLM 不需要关心 `.completed` 在哪。LLM 关心的是 `stages/` 和 `final_result.json`，这些保持在域目录根。

**盲点 6：`project.json` 的 `runs_count` 是冗余字段**

`runs_count` 可以从 `runs.json` 计算得出。如果手动维护，迟早会不一致。

建议：删除 `runs_count`，或者改为 `cached_runs_count` + `last_updated` 时间戳，明确这是缓存值。

---

## 具体建议（可操作的）

### 必须修正（阻塞实施）

1. **统一 3.1 目录树和 D5 数据流描述**
   - 选定一个结构，文档中只保留一个版本
   - 推荐：保留 3.1 的树结构（无 `input/`/`output/` 中间层），修改 D5 用域名寻址

2. **明确 run.json vs runs.json vs project.json 的职责和数量**
   - `project.json`：1 个/项目，元数据
   - `runs.json`：1 个/项目，所有 run 的索引（建议改名为 `index.json`，跟 3.1 目录树对齐）
   - `run.json`：1 个/run，运行元数据

### 强烈建议（不阻塞但会后悔）

3. **run.json 增加 `parent_run_id` 和 `iteration` 字段**
   - 零成本为 Loop Engine 铺路
   - 现在不实现写入逻辑，但 schema 先定义好

4. **run.json 预留 `external_refs` 字段**
   - 为 Research Pro 未来接入留口子
   - 默认空数组，不增加复杂度

5. **runs.json 改为 JSONL 格式（append-only）**
   - 避免并发写入问题
   - 每行一个 run 摘要，追加即可
   - 读取时逐行解析，性能无差异（几十到几百行）

### 可以延后（Phase 3+）

6. **slug 确认机制**（首次打印给用户确认）
7. **Feedback 目录结构定义**（Loop Engine 实施时再定）
8. **跨 run 对比 API**（工具层，不影响目录结构）

---

## 总结

| 维度 | 判断 |
|:---|:---|
| 结构合理性 | ✅ 三层结构正确，无更优替代 |
| 数据流清晰度 | ⚠️ 文档内部矛盾需修正，跨域寻址机制需明确 |
| 扩展性 | ✅ 基本够用，需预留 2-3 个字段 |
| 命名一致性 | ⚠️ run.json/runs.json/index.json 混乱需统一 |
| Loop Engine 支撑 | ⚠️ 缺 parent_run_id 和 feedback 定义 |
| 实施可行性 | ✅ 改动量评估准确，Phase 分步合理 |

**结论**：方向正确，修正文档矛盾后可以进入实施。修正量不大（主要是文档统一 + 2-3 个字段预留），不影响架构决策。
