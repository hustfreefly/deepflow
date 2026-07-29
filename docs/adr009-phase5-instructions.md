# ADR-009 Phase 5: 跨域消费迁移 — 子 Agent 指令

## 任务概述

Ship Pro 从 `frozen_spec.md` 读取，不再读 `frozen_spec.json`。

---

## 改动范围

**目标目录**: `domains/ship_pro/`

**当前残留**:
- `domains/ship_pro/__init__.py:23` — 注释中的路径说明
- `domains/ship_pro/__init__.py:627` — 文档说明
- `domains/ship_pro/orchestrator/ship_orchestrator.py:1502` — 代码逻辑

---

## 具体步骤

### 1. 修改 `ship_orchestrator.py`

找到读取 frozen_spec 的代码，改为：
```python
# Before:
frozen_spec = bm.read_json('data/frozen_spec.json')

# After:
from domains.solution_pro.frozen_living_md import parse_frozen_spec_md
frozen_spec_md = bm.read('data/frozen_spec.md')
frozen_spec = parse_frozen_spec_md(frozen_spec_md)
```

### 2. 修改 `__init__.py` 注释/文档

- Line 23: `data/frozen_spec.json` → `data/frozen_spec.md`
- Line 627: `frozen_spec.json` → `frozen_spec.md`

### 3. 检查其他消费点

```bash
grep -rn "frozen_spec\.json" domains/ship_pro/ --include="*.py"
```

确保无遗漏。

---

## 验证标准

- [ ] `grep -rn "frozen_spec\.json" domains/ship_pro/` 返回空
- [ ] Ship Pro 能正常从 MD 读取并解析 frozen_spec
- [ ] 现有测试通过

---

## 完成后报告

1. 修改了哪些文件
2. 每个文件改了什么
3. 测试是否通过
