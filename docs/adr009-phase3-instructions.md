# ADR-009 Phase 3: 执行层翻转 — 子 Agent 指令

## 任务概述

修改 Solution Pro 的 `__init__.py`，让 MD 成为主写入路径，JSON 退化为衍生品。

---

## 核心改动

### 1. 写入顺序翻转

**当前（JSON 主写 + MD 侧车）**:
```python
bm.write_stage('final_solution', solution_dict)        # ← JSON 真相源
md = render_final_solution_md(solution_dict)
bm.write('final_solution.md', md)                       # ← MD 侧车（失败不阻断）
```

**目标（MD 主写 + JSON 衍生品）**:
```python
md = render_final_solution_md(solution_dict)
bm.write_stage('final_solution', md)                    # ← MD 真相源（str → .md）
# JSON 衍生品可选生成（Gate 仪表盘用）
```

### 2. frozen_spec 同理

**当前**:
```python
bm.write("data/frozen_spec.json", frozen_spec)
bm.write("data/frozen_spec.md", render_frozen_spec_md(frozen_spec))
```

**目标**:
```python
bm.write("data/frozen_spec.md", render_frozen_spec_md(frozen_spec))  # ← 真相源
# JSON 衍生品可选生成
```

### 3. render 失败从 log ERROR 变为 raise

**当前**:
```python
except Exception as e:
    logging.error(f"MD render failed: {e}")  # 不阻断
```

**目标**:
```python
# MD render 失败 → raise ValueError（ADR-009 契约违反）
# 不捕获异常，让调用方知道 MD 渲染失败
```

---

## 具体步骤

1. **读取 `domains/solution_pro/__init__.py`**，找到所有 `write_stage` / `write` 调用
2. **识别交付物写入点**：
   - `final_solution` / `final_solution.json` → 改为 MD 主写
   - `frozen_spec` / `frozen_spec.json` → 改为 MD 主写
   - `solution_document` / `solution_document.json` → 改为 MD 主写
3. **翻转写入顺序**：先 render MD → write_stage(md_string) → 可选生成 JSON 索引
4. **移除 try/except 吞错误**：MD render 失败应该 raise
5. **删除双写逻辑**：不再同时写 JSON 和 MD，只写 MD

---

## 验证标准

- [ ] `final_solution.md` 是主产物（不是侧车）
- [ ] `frozen_spec.md` 是主产物（不是侧车）
- [ ] MD render 失败会 raise，不会静默跳过
- [ ] 现有测试通过（或合理更新）
- [ ] 无 JSON 主写入残留（交付物相关）

---

## 注意事项

- 不要改 prompt 文件（那是 Phase 4）
- 不要改 Ship Pro 消费端（那是 Phase 5）
- 只改 `__init__.py` 的写入逻辑
- 保留 JSON 衍生品的可选生成（如果 Gate 需要）

---

## 完成后报告

1. 修改了哪些函数/方法
2. 测试是否通过
3. 是否有遗留问题
