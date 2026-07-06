# DeepFlow 管线错误率修复方案

> **基于**: Doctor 2.0.0 全流程诊断 (2026-06-27, 54 sessions, 90 errors, 13% 错误率)
> **目标**: 错误率从 13% 降至 <5%, 节省 ~40 万 tokens/次管线

---

## 问题全景

| # | 根因 | 错误次数 | 占比 | 影响阶段 |
|---|------|:---:|:---:|----------|
| ❶ | 路径认知偏差 | 17 | 19% | Spec/Solution/Ship Pro |
| ❷ | BM API 使用混乱 | 8+ | 9% | Spec/Solution Pro |
| ❸ | 门控 schema 对齐不足 | 3 | 3% | Ship Pro |
| ❹ | 工具/环境探测重复 | 6+ | 7% | 全部 |
| ❺ | 即兴 Python 错误 | 5+ | 6% | 全部 |
| — | 其他(isError_flag) | ~50 | 56% | 各类混合 |

---

## 修复方案

### FIX-1: 路径注入 (针对 ❶)

**问题**: 子 Agent 不知道 `.deepflow` 目录结构，硬拼路径导致 ENOENT。

**方案**: 在 `start_xxx_pro.py` 输出的 spawn_params.task 中注入目录树快照。

**实现**:
```python
# scripts/path_context.py — 新增
def generate_path_context(deepflow_root: Path, blackboard_id: str) -> str:
    """生成目录树 + 关键路径速查表，注入到每个子 Agent prompt"""
    
    tree_output = subprocess.check_output(
        ["tree", "-L", "2", "--dirsfirst", "-I", "__pycache__|*.pyc", str(deepflow_root)],
        text=True
    )
    
    bb_dir = deepflow_root / "blackboard" / blackboard_id
    
    return f"""
## 📁 DeepFlow 目录结构 (只读参考，禁止猜测路径)

```
{tree_output}
```

### 当前 Blackboard 路径
- 根目录: `{bb_dir}`
- stages 目录: `{bb_dir}/stages/`
- data 目录: `{bb_dir}/data/`

### ⛔ 路径规则
1. **禁止**自己拼接路径，必须使用上述路径
2. stages/ 文件写入用 `write_stage(stage_name, data)` 
3. stages/ 文件读取用 `read_stage(stage_name)`
4. 如果目录不存在，先用 `mkdir -p` 创建
"""
```

**集成点**:
- `start_spec_pro.py` → spawn_params.task 拼接 `generate_path_context()`
- `start_solution_pro.py` → 同上
- `start_ship_pro.py` → 同上

**预期效果**: 路径错误减少 80%+ (17 → ~3)

---

### FIX-2: BM API 文档对齐 (针对 ❷)

**问题**: 子 Agent 尝试调用 `bm.get_spec()` / `bm.list_stages()` 等不存在的方法。

**方案**: 在子 Agent prompt 中嵌入 **精确的 API 签名 + 示例**，并明确标注 "禁止读源码"。

**实现**:
```python
# scripts/api_doc_inject.py — 新增
def generate_api_doc() -> str:
    """从 BlackboardManager 实际代码提取公共 API，生成子 Agent 可读文档"""
    
    return """
## 🔧 BlackboardManager API (2.0.0 唯一正确用法)

```python
from core.blackboard.blackboard_manager import BlackboardManager

# 初始化 (必须传 blackboard_id)
bm = BlackboardManager(blackboard_id="<你的 blackboard_id>")

# 写入 stage 数据
bm.write_stage("stages/planning.json", data_dict)

# 读取 stage 数据
result = bm.read_stage("stages/planning.json")

# 检查 stage 是否存在
exists = bm.stage_exists("stages/planning.json")

# 列出所有 stages
stages = bm.list_stages()  # 返回 List[str]
```

### ⛔ 禁止事项
- ❌ 禁止 `bm.get_spec()` — 不存在
- ❌ 禁止 `bm.list_stages(id)` — 无参数
- ❌ 禁止 `bm.blackboard_path` — 不是公开属性
- ❌ 禁止 `BlackboardManager()` 无参构造 — 必须传 blackboard_id
- ❌ **禁止读 blackboard_manager.py 源码** — 以本文档为准

### ✅ 正确做法
如果 API 不满足需求，直接用 `exec` 操作文件:
```bash
cat {bb_dir}/stages/planning.json
python3 -c "import json; json.dump(data, open('{bb_dir}/stages/xxx.json', 'w'))"
```
"""
```

**集成点**: 同 FIX-1，注入到 spawn_params.task

**预期效果**: BM API 错误减少 90%+ (8 → 0-1)

---

### FIX-3: 门控 Schema 示例注入 (针对 ❸)

**问题**: Generator 不知道输出该长什么样，Pydantic 验证连续失败。

**方案**: 在 Generator prompt 中嵌入 JSON Schema 示例 + 常见错误字段说明。

**实现**:
```python
# domains/ship_pro/scripts/run_pipeline.py 修改 task 命令
# 在 generator task prompt 末尾追加:

schema_hint = """
## 📋 输出格式强制约束

你的输出必须通过 Pydantic GeneratorOutput 验证。关键要求:

1. **modules**: List[Module]，每个 Module 必须有:
   - id: "COMP-XXX" (字符串)
   - name: 模块名 (字符串)
   - summary: 一句话描述 (字符串)
   - responsibilities: List[str]
   - technology_stack: List[str]
   - is_infrastructure: bool

2. **risks**: List[Risk]，每个 Risk 必须有:
   - id: "RISK-XXX"
   - name: 风险名 (不是 title!)
   - description: 描述
   - probability: float (0-1)
   - impact: "low"|"medium"|"high"|"extreme"
   - severity: "minor"|"major"|"critical"
   - mitigation: 缓释措施

3. **所有列表字段不能为空**，至少包含 1 项

⛔ 常见错误:
- risk 用 "title" 而非 "name" → 验证失败
- probability 用 "高" 而非 0.5 → 类型错误
- modules 漏掉 is_infrastructure → 验证失败
"""
```

**集成点**: `run_pipeline.py task generator` 命令输出追加 schema_hint

**预期效果**: 门控失败从 3 次降至 0-1 次

---

### FIX-4: 环境能力缓存 (针对 ❹)

**问题**: 每个 session 都重新探测 pandoc/wkhtmltopdf/markdown 可用性。

**方案**: 首次探测结果写入 `.deepflow/.env_capabilities.json`，后续直接读取。

**实现**:
```python
# scripts/env_capabilities.py — 新增
import json, subprocess, shutil
from pathlib import Path

CACHE_FILE = Path(__file__).parent.parent / ".env_capabilities.json"

def detect_capabilities() -> dict:
    """探测环境能力并缓存"""
    if CACHE_FILE.exists():
        age_hours = (time.time() - CACHE_FILE.stat().st_mtime) / 3600
        if age_hours < 24:  # 24 小时内有效
            return json.loads(CACHE_FILE.read_text())
    
    caps = {
        "pdf_tools": {
            "chrome_headless": shutil.which("google-chrome") is not None 
                or Path("/Applications/Google Chrome.app").exists(),
            "pandoc": shutil.which("pandoc") is not None,
            "wkhtmltopdf": shutil.which("wkhtmltopdf") is not None,
        },
        "python_modules": {},
    }
    
    for mod in ["markdown", "pydantic", "weasyprint", "jinja2"]:
        try:
            __import__(mod)
            caps["python_modules"][mod] = True
        except ImportError:
            caps["python_modules"][mod] = False
    
    CACHE_FILE.write_text(json.dumps(caps, indent=2))
    return caps

def get_pdf_command() -> str:
    """返回可用的 PDF 生成命令模板"""
    caps = detect_capabilities()
    if caps["pdf_tools"]["chrome_headless"]:
        return '"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --print-to-pdf="{output}" --print-to-pdf-no-header "{input}"'
    elif caps["pdf_tools"]["pandoc"]:
        return "pandoc {input} -o {output} --pdf-engine=xelatex"
    else:
        return "echo 'No PDF tool available'"
```

**集成点**: 
- PDF 生成场景直接调用 `get_pdf_command()` 而非探测
- 子 Agent prompt 注入环境能力摘要

**预期效果**: 探测错误归零，每次节省 3-5 次无效 exec

---

### FIX-5: 即兴 Python 防护 (针对 ❺)

**问题**: LLM 在不了解数据结构的情况下直接写代码，字段名猜错。

**方案**: 双层防护 — prompt 约束 + 标准化分析脚本。

**实现 A: Prompt 约束**:
```
## ⛔ Python 代码规则
1. 分析 JSON 数据前，**必须先用 exec 打印 keys**: 
   `python3 -c "import json; print(list(json.load(open('file.json')).keys()))"`
2. 确认 keys 后再写分析代码
3. 禁止猜测字段名 — 如果不确定，先 read 文件看结构
```

**实现 B: 标准化分析脚本**:
```python
# scripts/analyze_json.py — 新增通用 JSON 分析器
"""
用法: python3 scripts/analyze_json.py <file> [--summary] [--keys] [--field NAME]
自动处理 KeyError / TypeError，输出人类可读摘要。
"""
```

**预期效果**: KeyError/AttributeError 减少 80%+

---

## 实施计划

| 阶段 | 修复项 | 预计工时 | 依赖 |
|------|--------|:---:|------|
| **Phase 1** | FIX-1 路径注入 + FIX-2 API 文档 | 2h | 无 |
| **Phase 2** | FIX-3 门控示例 + FIX-4 环境缓存 | 1.5h | 无 |
| **Phase 3** | FIX-5 Python 防护 + 集成测试 | 1h | Phase 1-2 |
| **Phase 4** | 端到端验证 (重跑 Spec Pro) | 1h | Phase 3 |

**总工时**: ~5.5h
**预期效果**: 错误率 13% → <5%, 每次管线节省 ~40 万 tokens

---

## 风险与限制

1. **路径注入可能过期**: 目录结构变化后缓存失效 → 用 mtime 检测自动刷新
2. **API 文档维护成本**: BM 升级后文档需同步 → 用 AST 从代码自动生成
3. **门控示例可能误导**: LLM 照抄示例而非理解 schema → 示例标注 "仅供参考结构"
4. **子 Agent 可能忽略约束**: prompt 太长导致约束被截断 → 关键约束放最前面

---

## 验证标准

- [ ] FIX-1: Spec Pro 10 个 worker session 路径错误 ≤ 2 次
- [ ] FIX-2: BM API 调用错误 = 0
- [ ] FIX-3: Ship Pro Generator 门控首次通过率 ≥ 70%
- [ ] FIX-4: 环境探测 exec 调用 = 0 (除首次)
- [ ] FIX-5: KeyError/AttributeError = 0
- [ ] 整体: 错误率 < 5%, 管线端到端成功
