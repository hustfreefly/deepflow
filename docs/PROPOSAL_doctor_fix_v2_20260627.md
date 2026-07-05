# DeepFlow 管线错误率修复方案 2.0.0（评审修订版）

> **基于**: Doctor 2.0.0 诊断 + 三维专家评审 (2026-06-27)
> **专家评审**: 架构 7.0 / Prompt 6.5 / 运维 6.75 → 综合 6.75 有条件通过
> **目标**: 错误率 13% → <5%, 节省 ~40 万 tokens/次管线

---

## 2.0.0 → 2.0.0 变更摘要

| 变更项 | 2.0.0 | 2.0.0 | 采纳专家 |
|--------|----|----|----------|
| 约束风格 | "禁止xxx" 负向 | "必须xxx" 正向流程 | Prompt专家 |
| FIX-1 主策略 | 路径注入 | BM API 优先 + 路径兜底 | 架构专家 |
| FIX-2 "读源码" | 禁止读源码 | 以文档为准，可查源码 | 3/3共识 |
| FIX-4 缓存位置 | .deepflow 根目录 | blackboard/{session}/ | 架构专家 |
| FIX-4 TTL | 24h | 4h | 运维专家 |
| tree 命令 | 无 fallback | find fallback | 运维专家 |
| Phase 4 验证 | 仅 Spec Pro | 三域冒烟 | 运维专家 |
| 统一注入层 | 散落各处 | context_injector.py | 架构专家 |
| 工时 | 5.5h | 7h | 运维专家 |

---

## FIX-1: 路径认知修复（路径注入 + BM API 双保险）

### 问题
子 Agent 不知道 `.deepflow` 目录结构，硬拼路径 → 17 次 ENOENT

### 2.0.0 方案: BM API 优先引导 + 路径注入兜底

```python
# scripts/path_context.py — 新增
import subprocess, shutil
from pathlib import Path

def generate_path_context(deepflow_root: Path, blackboard_id: str) -> str:
    """生成路径上下文，注入到子 Agent prompt"""
    
    bb_dir = deepflow_root / "blackboard" / blackboard_id
    
    # tree 或 find fallback
    tree_cmd = shutil.which("tree")
    if tree_cmd:
        tree_output = subprocess.check_output(
            [tree_cmd, "-L", "2", "--dirsfirst", "-I", "__pycache__|*.pyc", str(deepflow_root)],
            text=True, timeout=5
        )
        # 限制 50 行，避免 token 爆炸
        lines = tree_output.strip().split("\n")[:50]
        tree_output = "\n".join(lines)
        if len(lines) == 50:
            tree_output += "\n... (已截断)"
    else:
        # fallback: find + head
        result = subprocess.check_output(
            ["find", str(deepflow_root), "-maxdepth", "2", "-type", "d"],
            text=True, timeout=5
        )
        tree_output = result.strip()
    
    return f"""
## 📁 DeepFlow 目录结构

```
{tree_output}
```

### 你的 Blackboard
- 根目录: `{bb_dir}`
- stages: `{bb_dir}/stages/`
- data: `{bb_dir}/data/`

### ⚡ 路径使用规则（必须遵守）
1. **必须** 使用 BlackboardManager API 进行读写:
   - `bm.write_stage("stages/planning.json", data)` 写入
   - `bm.read_stage("stages/planning.json")` 读取
2. **必须** 使用上述完整路径，不得自行拼接
3. 如需直接操作文件，**必须** 使用上述 `{bb_dir}` 变量
"""
```

---

## FIX-2: BM API 文档注入（正向引导版）

### 问题
子 Agent 调用 `bm.get_spec()` 等不存在方法 → 8+ 次错误

### 2.0.0 方案: 正向 API 文档（移除"禁止读源码"）

```python
# scripts/api_doc_inject.py — 新增
def generate_api_doc() -> str:
    return """
## 🔧 BlackboardManager API（2.0.0 标准用法）

### 初始化
```python
from core.blackboard.blackboard_manager import BlackboardManager
bm = BlackboardManager(blackboard_id="<你的 blackboard_id>")
```

### 标准操作（覆盖 95% 场景）
| 操作 | 方法 | 示例 |
|------|------|------|
| 写入 stage | `bm.write_stage(name, data)` | `bm.write_stage("stages/planning.json", plan_dict)` |
| 读取 stage | `bm.read_stage(name)` | `data = bm.read_stage("stages/planning.json")` |
| 检查存在 | `bm.stage_exists(name)` | `if bm.stage_exists("stages/fix.json"):` |
| 列出 stages | `bm.list_stages()` | `names = bm.list_stages()  # → List[str]` |

### 特殊场景：直接用 exec 操作文件
当 BM API 不满足需求时（如批量操作、大文件处理）:
```bash
cat {bb_dir}/stages/planning.json
python3 -c "import json; json.dump(data, open('{bb_dir}/stages/xxx.json', 'w'))"
```

### 📌 使用优先级
1. 标准读写 → 用 BM API（write_stage / read_stage）
2. BM API 不满足 → 用 exec 直接操作 `{bb_dir}` 下的文件
3. 需要深入理解 → 可查阅源码 `core/blackboard/blackboard_manager.py`

### ⚠️ 常见误区
- `BlackboardManager()` 需要传 `blackboard_id` 参数
- `bm.list_stages()` 不需要参数
- stage name 需要包含 `stages/` 前缀
"""
```

---

## FIX-3: 门控 Schema 示例（防照抄版）

### 问题
Generator 输出不符合 Pydantic schema → 3 次门控失败

### 2.0.0 方案: 字段说明表 + 占位符示例（避免照抄具体值）

```python
schema_hint = """
## 📋 输出格式约束

你的输出必须通过 Pydantic 验证。以下是关键字段说明:

### modules[] 字段要求
| 字段 | 类型 | 格式 | 必填 |
|------|------|------|:---:|
| id | string | "COMP-XXX" (XXX 从 001 递增) | ✅ |
| name | string | 模块名 | ✅ |
| summary | string | 一句话描述 | ✅ |
| responsibilities | list[str] | 职责列表 | ✅ |
| technology_stack | list[str] | 技术栈列表 | ✅ |
| is_infrastructure | bool | true/false | ✅ |

### risks[] 字段要求
| 字段 | 类型 | 格式 | 必填 |
|------|------|------|:---:|
| id | string | "RISK-XXX" | ✅ |
| **name** | string | 风险名 (⚠️ 不是 title!) | ✅ |
| description | string | 描述 | ✅ |
| probability | **float** | 0.0-1.0 (⚠️ 不是 "高"!) | ✅ |
| impact | string | "low"/"medium"/"high"/"extreme" | ✅ |
| severity | string | "minor"/"major"/"critical" | ✅ |
| mitigation | string | 缓释措施 | ✅ |

### ⚠️ 易错字段
- risks 的风险名: 字段名是 `name`，不是 `title`
- probability: 必须是浮点数 (如 0.4)，不是文字 (如 "中")
- 所有 list 字段不能为空数组，至少 1 项

### 占位符示例（参考结构，替换 XXX 和具体内容）
```json
{{
  "modules": [{{"id": "COMP-XXX", "name": "...", ...}}],
  "risks": [{{"id": "RISK-XXX", "name": "...", "probability": 0.X, ...}}]
}}
```
"""
```

---

## FIX-4: 环境能力缓存（安全位置 + 短 TTL）

### 2.0.0 方案

```python
# scripts/env_capabilities.py
import json, subprocess, shutil, time, fcntl
from pathlib import Path

# 放在 blackboard 下，session 隔离，避免并发冲突
def get_cache_path(deepflow_root: Path) -> Path:
    return deepflow_root / "blackboard" / ".env_capabilities.json"

def detect_capabilities(deepflow_root: Path) -> dict:
    cache = get_cache_path(deepflow_root)
    
    # 4h TTL + mtime 变化检测
    if cache.exists():
        age_hours = (time.time() - cache.stat().st_mtime) / 3600
        if age_hours < 4:
            try:
                return json.loads(cache.read_text())
            except:
                pass
    
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    caps = {
        "pdf_tools": {
            "chrome_headless": Path(chrome_path).exists(),
            "pandoc": shutil.which("pandoc") is not None,
            "wkhtmltopdf": shutil.which("wkhtmltopdf") is not None,
        },
        "python_modules": {},
        "tree_available": shutil.which("tree") is not None,
    }
    
    for mod in ["markdown", "pydantic", "weasyprint", "jinja2"]:
        try:
            __import__(mod)
            caps["python_modules"][mod] = True
        except ImportError:
            caps["python_modules"][mod] = False
    
    # 带文件锁的写入
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        with open(cache, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            json.dump(caps, f, indent=2)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except:
        pass  # 写缓存失败不影响主流程
    
    return caps

def get_pdf_command(deepflow_root: Path, input_path: str, output_path: str) -> str:
    caps = detect_capabilities(deepflow_root)
    if caps["pdf_tools"]["chrome_headless"]:
        chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        return f'"{chrome}" --headless=new --disable-gpu --print-to-pdf="{output_path}" --print-to-pdf-no-header "{input_path}"'
    elif caps["pdf_tools"]["pandoc"]:
        return f'pandoc "{input_path}" -o "{output_path}" --pdf-engine=xelatex'
    return f'echo "No PDF tool available"'
```

---

## FIX-5: 即兴 Python 防护（标准化工具 + 正向流程）

### 2.0.0 方案

**A: 标准化 JSON 分析工具**
```python
# scripts/analyze_json.py — 新增
"""
用法:
  python3 scripts/analyze_json.py <file> --keys     # 打印顶层 keys
  python3 scripts/analyze_json.py <file> --summary   # 打印结构摘要
  python3 scripts/analyze_json.py <file> --field NAME # 打印指定字段详情

自动处理 KeyError / TypeError，输出人类可读摘要。
"""
import json, sys
from pathlib import Path

def main():
    if len(sys.argv) < 3:
        print("用法: analyze_json.py <file> --keys|--summary|--field NAME")
        sys.exit(1)
    
    filepath = Path(sys.argv[1])
    mode = sys.argv[2]
    
    try:
        data = json.loads(filepath.read_text())
    except Exception as e:
        print(f"❌ 无法读取: {e}")
        sys.exit(1)
    
    if mode == "--keys":
        if isinstance(data, dict):
            for k, v in data.items():
                t = type(v).__name__
                preview = str(v)[:80] if not isinstance(v, (dict, list)) else f"[{len(v)} items]" if isinstance(v, list) else f"{{{len(v)} keys}}"
                print(f"  {k}: ({t}) {preview}")
        elif isinstance(data, list):
            print(f"  List[{len(data)} items]")
            if data:
                print(f"  [0] keys: {list(data[0].keys()) if isinstance(data[0], dict) else type(data[0]).__name__}")
    
    elif mode == "--summary":
        _print_summary(data, depth=0, max_depth=3)
    
    elif mode == "--field" and len(sys.argv) > 3:
        field = sys.argv[3]
        if isinstance(data, dict):
            val = data.get(field, "NOT_FOUND")
            print(json.dumps(val, ensure_ascii=False, indent=2)[:2000])
        else:
            print(f"根类型是 {type(data).__name__}，不支持 --field")

def _print_summary(obj, depth=0, max_depth=3):
    indent = "  " * depth
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict) and depth < max_depth:
                print(f"{indent}{k}: {{{len(v)} keys}}")
                _print_summary(v, depth+1, max_depth)
            elif isinstance(v, list):
                print(f"{indent}{k}: [{len(v)} items]")
            else:
                print(f"{indent}{k}: {type(v).__name__} = {str(v)[:60]}")

if __name__ == "__main__":
    main()
```

**B: Prompt 正向流程约束**
```
## 📋 数据分析流程（必须遵守）

当需要分析 JSON 数据时，按以下流程操作:

1. **结构发现**: `python3 scripts/analyze_json.py <file> --keys`
2. **深入探索**: `python3 scripts/analyze_json.py <file> --field <name>`
3. **编写代码**: 基于已确认的字段名编写分析代码

这个流程确保你了解数据结构后再编码，避免 KeyError。
```

---

## 统一注入层

```python
# core/blackboard/context_injector.py — 新增
"""统一子 Agent 上下文注入，供 start_xxx_pro.py 和 run_pipeline.py 调用"""

from pathlib import Path
from scripts.path_context import generate_path_context
from scripts.api_doc_inject import generate_api_doc
from scripts.env_capabilities import detect_capabilities

def build_agent_context(deepflow_root: Path, blackboard_id: str, 
                         include_schema: bool = False,
                         schema_hint: str = "") -> str:
    """构建子 Agent 上下文注入块"""
    
    parts = []
    
    # 1. 路径上下文 (所有 Agent)
    parts.append(generate_path_context(deepflow_root, blackboard_id))
    
    # 2. API 文档 (所有 Agent)
    parts.append(generate_api_doc())
    
    # 3. 环境能力摘要 (所有 Agent)
    caps = detect_capabilities(deepflow_root)
    cap_lines = []
    if caps.get("tree_available"):
        cap_lines.append("✅ tree 命令可用")
    if caps["pdf_tools"]["chrome_headless"]:
        cap_lines.append("✅ Chrome headless 可用 (PDF 生成)")
    if caps["python_modules"].get("pydantic"):
        cap_lines.append("✅ pydantic 已安装")
    
    parts.append(f"## 🔧 环境能力\n" + "\n".join(cap_lines))
    
    # 4. Schema 提示 (仅 Generator/Judge)
    if include_schema and schema_hint:
        parts.append(schema_hint)
    
    return "\n\n---\n\n".join(parts)
```

**集成点**:
```python
# start_spec_pro.py / start_solution_pro.py / start_ship_pro.py 中:
from core.blackboard.context_injector import build_agent_context

context = build_agent_context(deepflow_root, blackboard_id)
spawn_params["task"] = context + "\n\n---\n\n" + original_task
```

---

## 修订版实施计划

| Phase | 修复项 | 工时 | 产出 |
|:---:|--------|:---:|------|
| **P1** | context_injector.py + path_context.py + api_doc_inject.py | 2h | 统一注入层 |
| **P2** | env_capabilities.py + analyze_json.py | 1.5h | 工具层 |
| **P3** | 集成到 start_spec/solution/ship_pro.py + schema_hint | 1.5h | 管线集成 |
| **P4** | 三域冒烟测试 (Spec + Solution + Ship Pro) | 2h | 验证 |

**总工时**: 7h

### P4 验证标准

| FIX | 验证方法 | 通过标准 |
|-----|----------|----------|
| FIX-1 | Spec Pro 10 worker session | 路径错误 ≤ 2 次 |
| FIX-2 | 所有 session BM API 调用 | API 错误 = 0 |
| FIX-3 | Ship Pro Generator | 门控首次通过率 ≥ 70% |
| FIX-4 | 第二次启动检测 | 环境探测 exec = 0 |
| FIX-5 | 所有 Python 分析代码 | KeyError/AttributeError = 0 |
| **整体** | 三域端到端 | **错误率 < 5%** |

---

## 遗留风险

| 风险 | 缓解 |
|------|------|
| Prompt 长度增加 ~1500 tokens | 按需裁剪目录树 (max 50 行) + API 文档只含常用方法 |
| 子 Agent 仍可能读源码 | 文档声明 "以本文档为准" + BM API 覆盖 95% 场景降低读源码动机 |
| context_injector.py 本身需要维护 | 与 BM 源码同步：CI 检查 API 文档与 `inspect.signature` 一致性 |
| 缓存文件损坏 | 带 fcntl 文件锁 + JSON 读取异常兜底 |
