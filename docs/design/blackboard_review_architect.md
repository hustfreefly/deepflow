# Blackboard 重构方案评审 — 系统架构师视角

> **评审人**: 系统架构师（架构合理性、扩展性、实施风险）
> **评审日期**: 2026-06-21

---

## 总体判断

**方案核心设计合理，建议按此实施。** 理由：

1. `projects/{slug}/runs/{ts}/` 三层结构精准解决了覆盖问题（P1、P5）和套娃问题（P2）
2. 域分离（spec/solution/ship）让数据流从"隐式约定"变成"显式结构"
3. Research Pro 独立是正确的——没有数据流的域不应该强行关联
4. 不拆 input/output/state 是对的，符合忠礼"够用就行"的价值观

但有几个需要澄清的点，否则实施时会踩坑。

---

## 详细评审

### 1. slug 生成策略需要更明确

**当前方案**：从 topic 自动生成，冲突时加 hash 后缀。

**问题**：
- 如果两个项目 topic 相似（"AI 客服系统" vs "AI 智能客服系统"），slug 可能都是 `ai-kefu`，需要加后缀区分
- slug 一旦生成，后续能否修改？如果能改，路径怎么办？
- slug 的字符集限制是什么？中文 slug 会导致路径编码问题吗？

**建议**：
```
slug = slugify(topic[:30]) + "-" + hash8

示例：
- "DeepFlow 开发者可观测性系统" → "deepflow-observability-a1b2c3d4"
- "跨境 AI 算力中转站" → "cross-border-ai-compute-e5f6g7h8"
```

这样既保持可读性，又天然避免冲突，不需要"冲突检测+加后缀"的额外逻辑。

### 2. 跨域路径引用需要统一规范

**当前问题**：Solution Pro 需要读 `spec/living_spec.json`，Ship Pro 需要读 `solution/final_result.json`。这些路径是相对的还是绝对的？

**建议**：统一用**相对于 run 根目录的路径**。

```
run 根目录 = /blackboard/projects/{slug}/runs/{ts}/

Solution Pro 读 Spec：
  relative: ../spec/living_spec.json
  absolute: /blackboard/projects/{slug}/runs/{ts}/spec/living_spec.json

Ship Pro 读 Solution：
  relative: ../solution/final_result.json
  absolute: /blackboard/projects/{slug}/runs/{ts}/solution/final_result.json
```

**为什么用相对路径**：
- LLM sub-agent 的 working directory 通常是 run 根目录
- 相对路径更短，拼接出错概率更低
- 便于未来迁移（整个 projects/ 目录移动，相对路径不变）

### 3. 路径深度增加的影响需要验证

**当前**：`stages/planning.json`（2 层）
**新方案**：`solution/stages/planning.json`（3 层）

**风险**：LLM sub-agent 拼接路径时，多一层意味着多一次出错机会。

**建议**：
1. 在 `blackboard.py` 中提供 helper 函数：
   ```python
   def get_stage_path(run_dir: str, domain: str, stage: str) -> str:
       return os.path.join(run_dir, domain, "stages", f"{stage}.json")
   ```
2. 先在一个新项目上试点，观察 LLM sub-agent 是否能正确处理新路径
3. 如果 LLM 频繁出错，可以考虑在 run 根目录放一个 `paths.json`，列出所有关键路径

### 4. 旧数据处理策略

**当前方案**：不迁移，保留 `_legacy/` 原样。

**问题**：
- 旧项目还能被读取吗？如果能，路径解析逻辑需要兼容
- 如果用户想对比新旧项目的数据，怎么办？

**建议**：
- 写一个简单的迁移脚本（50 行代码），把现有项目移到 `_legacy/`
- 新代码只认 `projects/{slug}/runs/{ts}/` 结构
- 旧数据保留但不再更新，作为历史参考

### 5. runs.json 的维护策略

**当前方案**：未明确由谁维护 `runs.json`。

**建议**：由 `completion_handler.py` 在 run 完成时写入。

```python
def update_runs_index(project_dir: str, run_id: str, status: str):
    index_path = os.path.join(project_dir, "index.json")
    if os.path.exists(index_path):
        with open(index_path) as f:
            index = json.load(f)
    else:
        index = {"runs": []}
    
    index["runs"].append({
        "run_id": run_id,
        "status": status,
        "completed_at": datetime.now().isoformat(),
        "domains": ["spec", "solution", "ship"]
    })
    
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
```

这样 `index.json` 是自动维护的，不需要用户手动更新。

---

## 盲点检查

### 我发现了什么方案没提到的问题？

**1. 并发写入风险**

如果用户同时跑两个 Solution Pro（比如开了两个终端），两个 run 的 `spec/living_spec.json` 会不会冲突？

**答案**：不会，因为每个 run 有自己的 `spec/` 目录。但需要确保 `project.json` 和 `index.json` 的写入是原子操作（用 `tempfile` + `rename`）。

**2. 磁盘空间管理**

每次 run 都会生成完整的 stages/ 数据。如果用户频繁重跑（比如调试阶段一天跑 10 次），磁盘空间会快速增长。

**建议**：加一个简单的清理策略：
```bash
# 保留最近 10 个 run，删除更早的
find /blackboard/projects/*/runs/ -maxdepth 1 -type d -mtime +7 | xargs rm -rf
```

**3. 调试友好性**

当 LLM sub-agent 出错时，用户需要快速定位是哪个 run、哪个域、哪个 stage。新结构下，用户需要：
```bash
cd /blackboard/projects/{slug}/runs/{ts}/solution/stages/
ls -lh
```

这比旧结构的 `cd /blackboard/{session_id}/stages/` 多了一层。

**建议**：在 run 根目录放一个 `README.md`，列出所有关键路径和状态。

---

## 最终建议

1. **方案可行，建议实施**
2. **补充 slug 生成规则**：`slugify(topic[:30]) + "-" + hash8`
3. **统一跨域路径引用**：相对路径，相对于 run 根目录
4. **先试点再推广**：在一个新项目上验证 LLM sub-agent 的路径拼接
5. **加清理策略**：避免磁盘空间快速增长

---

**评审完成**。如有需要，可以进一步讨论实施细节。
