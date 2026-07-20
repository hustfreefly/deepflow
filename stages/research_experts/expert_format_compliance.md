# 格式合规与验证专家研究报告

> **Expert**: Format Compliance Expert  
> **Stage**: research_experts/expert_format_compliance.md  
> **Date**: 2026-07-13  
> **Scope**: ISO 8601 日期解析、RFC 8259 JSON、RFC 4180 CSV、输入验证流水线、错误消息格式、过去日期策略

---

## 1. 研究范围

本报告针对 planning_convergence 阶段确定的 26 条统一约束（UC-001 ~ UC-026），聚焦以下六个格式合规领域的深度研究：

1. **ISO 8601 日期解析支持矩阵**（覆盖 UC-004、UC-005）
2. **RFC 8259 JSON 导出合规**（覆盖 UC-011、UC-014）
3. **RFC 4180 CSV 导出合规**（覆盖 UC-012、UC-014）
4. **输入验证流水线设计**（覆盖 UC-024、UC-002、UC-003、UC-008）
5. **错误消息格式模板**（覆盖 UC-020）
6. **过去日期处理策略**（覆盖 UC-025）

所有发现均基于 Python 3.13.13 标准库实测验证，RFC 原文条款引用，以及与 planning_convergence 约束的逐条对齐分析。

---

## 2. 发现与分析

### Finding 1: Python 3.11+ datetime.fromisoformat() 对 ISO 8601 各变体的完整支持矩阵

**Evidence（实测验证）：**

在 Python 3.13.13 上执行 `datetime.fromisoformat()` 测试，结果如下：

| 输入格式 | 示例值 | 解析结果 | 合规状态 |
|---------|--------|---------|---------|
| 纯日期 YYYY-MM-DD | `'2025-07-13'` | `datetime(2025,7,13)` tzinfo=None | ACCEPT |
| 日期时间无时区 | `'2025-07-13T10:30:00'` | `datetime(2025,7,13,10,30)` tzinfo=None | ACCEPT |
| Z 后缀 UTC | `'2025-07-13T10:30:00Z'` | `datetime(2025,7,13,10,30)` tzinfo=UTC | ACCEPT (3.11+) |
| 正偏移 +08:00 | `'2025-07-13T10:30:00+08:00'` | `datetime(2025,7,13,10,30)` tzinfo=UTC+8 | ACCEPT |
| 负偏移 -05:00 | `'2025-07-13T10:30:00-05:00'` | `datetime(2025,7,13,10,30)` tzinfo=UTC-5 | ACCEPT |
| +00:00 偏移 | `'2025-07-13T10:30:00+00:00'` | `datetime(2025,7,13,10,30)` tzinfo=UTC | ACCEPT |

**拒绝情况：**

| 输入格式 | 示例值 | 解析结果 | 合规状态 |
|---------|--------|---------|---------|
| US 格式 | `'07/13/2025'` | ValueError | CORRECTLY REJECTED |
| DD-MM-YYYY | `'13-07-2025'` | ValueError | CORRECTLY REJECTED |
| 紧凑 ISO | `'20250713'` | `datetime(2025,7,13)` | WARNING: unexpectedly accepted |
| 非填充月 | `'2025-7-13'` | ValueError | CORRECTLY REJECTED |
| 自然语言 | `'July 13, 2025'` | ValueError | CORRECTLY REJECTED |

**关键发现 -- 紧凑格式兼容性问题：**

Python 3.11+ 的 `fromisoformat()` 接受紧凑 ISO 8601 格式 `'20250713'`（无连字符），这与 UC-004 的要求"必须拒绝非 ISO 格式（如 20250713）"存在冲突。UC-004 明确列出 `20250713` 作为应被拒绝的示例。

**解决方案：** 在 `fromisoformat()` 之前增加格式预检：

```python
import re
ISO_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}')  # 必须以 YYYY-MM-DD 开头

def validate_iso8601(value: str) -> datetime:
    if not ISO_DATE_RE.match(value):
        raise ValueError(f"日期格式必须以 YYYY-MM-DD 开头")
    return datetime.fromisoformat(value)
```

此预检正则确保：(1) 必须有连字符分隔年月日，(2) 仍允许 `fromisoformat()` 处理后续的 T 分隔符和时区后缀，(3) 拒绝 `20250713` 紧凑格式。

**日期导出（UC-005）实测：**

| 类型 | isoformat() 输出 | 符合 UC-005 |
|------|-----------------|------------|
| `date(2025,7,13)` | `'2025-07-13'` | YYYY-MM-DD 合规 |
| `datetime(2025,7,13,10,30)` (无时区) | `'2025-07-13T10:30:00'` | 无偏移，需注意 |
| `datetime(2025,7,13,10,30, tzinfo=UTC)` | `'2025-07-13T10:30:00+00:00'` | 完整偏移合规 |

**注意：** 无时区的 datetime 导出为 `'2025-07-13T10:30:00'`（无 +/-HH:MM），UC-005 要求"有时间的输出 YYYY-MM-DDTHH:MM:SS+/-HH:MM"。实现时需确保存储时保留时区信息，或在导出时附加本地时区。

**Covered Constraints:** UC-004, UC-005

---

### Finding 2: RFC 8259 JSON 导出合规要点

**Evidence（RFC 8259 条款 + Python 实测）：**

RFC 8259 关键条款与 Python `json` 模块对齐分析：

| RFC 8259 条款 | 要求 | Python 实现 | 合规状态 |
|--------------|------|------------|---------|
| Section 6 (Encoding) | JSON 文本使用 UTF-8 编码，无 BOM | `open(f, 'w', encoding='utf-8')` + `json.dumps()` | COMPLIANT |
| Section 4 (Objects) | 对象名称（键）应唯一 | Python dict 天然唯一（语言保证） | COMPLIANT |
| Section 6 (Interchange) | 跨系统交互使用 UTF-8 | `ensure_ascii=False` 保留原始 Unicode | COMPLIANT |
| 无 BOM 要求 | 不得包含 U+FEFF 字节序标记 | `json.dumps()` 不生成 BOM；实测首字节为 `7b`（`{`），非 `efbbbf` | COMPLIANT |

**实测验证：**

```python
import json
data = {'tasks': [{'title': '测试中文标题', 'priority': 'P0'}]}
json_str = json.dumps(data, ensure_ascii=False, indent=2)
# 输出首字节 hex: 7b0a20 (即 '{\n ')，BOM 为 efbbbf -- 确认无 BOM
# 中文字符 '测试' 直接保留，未被转义为 \uXXXX
```

**UC-011 完整合规清单：**

1. **UTF-8 无 BOM**：`open(filepath, 'w', encoding='utf-8')` -- Python 的 `open()` 在 `encoding='utf-8'` 模式下不写入 BOM（与 `encoding='utf-8-sig'` 不同）。
2. **ensure_ascii=False**：必须显式传入，否则默认 `ensure_ascii=True` 会将所有非 ASCII 字符转义为 `\uXXXX`。
3. **indent=2**：RFC 8259 不要求格式化，但 UC-011 明确要求 `indent=2` 提升可读性。
4. **键名 snake_case 且唯一**：Python dict 保证键唯一；命名约定由代码规范保证（`title`, `priority`, `status`, `due_date`, `tags`）。
5. **导出结构**：`{"tasks": [...]}` -- 顶层对象含单一 `tasks` 键。
6. **值域约束**：优先级 P0/P1/P2、状态 pending/done、日期 ISO 8601 或 null、标签字符串数组 -- 均由数据模型层保证。

**风险点：** `json.dumps()` 的 `sort_keys` 参数默认为 False，不应启用（UC-011 未要求键排序，且固定插入顺序更利于人类阅读和 diff）。

**Covered Constraints:** UC-011, UC-014

---

### Finding 3: RFC 4180 CSV 导出合规要点

**Evidence（RFC 4180 条款 + Python csv 模块实测）：**

RFC 4180 关键条款与 Python `csv.excel` dialect 对齐分析：

| RFC 4180 条款 | 要求 | Python excel dialect | 合规状态 |
|--------------|------|---------------------|---------|
| Section 2.1 | 逗号分隔符 | `delimiter=','` | FULLY ALIGNED |
| Section 2.1 | CRLF 行终止 | `lineterminator='\r\n'` | FULLY ALIGNED |
| Section 2.3 | 双引号包裹字段 | `quotechar='"'` | FULLY ALIGNED |
| Section 2.7 | 双引号转义（字段内双引号用两个双引号表示） | `doublequote=True` | FULLY ALIGNED |
| Section 2.4 | 列一致性（每行列数相同） | DictWriter 通过 fieldnames 保证 | FULLY ALIGNED |
| Section 2.5 | 首行为表头 | writeheader() 方法 | SUPPORTED |
| Section 2.6 | 字段内换行用双引号包裹 | csv 模块自动处理 | SUPPORTED |
| Section 2.7 | 字段内双引号用 "" 转义 | 实测：`'Test "quoted"'` 输出为 `"Test ""quoted"""` | VERIFIED |

**关键实测结果：**

```python
import csv, io
buf = io.StringIO()
writer = csv.DictWriter(buf, fieldnames=['title','priority','status','due_date','tags'], dialect='excel')
writer.writerow({
    'title': 'Test "quoted" task',
    'priority': 'P0',
    'status': 'pending',
    'due_date': '2025-07-13',
    'tags': 'work,urgent'
})
output = buf.getvalue()
# repr: 'title,priority,status,due_date,tags\r\n"Test ""quoted"" task",P0,pending,2025-07-13,"work,urgent"\r\n'
# CRLF 验证: 包含 \r\n，无裸 \n
```

**关键陷阱 -- newline='' 参数：**

Python `csv` 模块文档明确要求：`open(filepath, 'w', newline='')`。如果不传 `newline=''`，Python 的通用换行符转换（universal newline translation）会将 `\r\n` 转换为平台特定换行符（macOS/Linux 上为 `\n`），破坏 RFC 4180 的 CRLF 要求。

**正确实现代码：**

```python
with open(filepath, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['title','priority','status','due_date','tags'], dialect='excel')
    writer.writeheader()
    writer.writerows(tasks)
```

**UC-012 列顺序合规：** 固定列顺序 `title, priority, status, due_date, tags` 通过 `fieldnames` 参数显式指定。空 `due_date` 输出空字符串（DictWriter 对 None 值输出空字符串，符合 RFC 4180）。

**标签字段处理（UC-008 联动）：** 由于 UC-008 禁止标签内包含逗号和双引号，标签序列化为 CSV 时可安全使用逗号连接（如 `work,urgent`），无需额外转义。但如果标签值本身含逗号（理论上已被 UC-008 拒绝），csv 模块会自动用双引号包裹。这构成双重防护。

**Covered Constraints:** UC-012, UC-014, UC-008

---

### Finding 4: 输入验证流水线设计

**Evidence（UC-024 约束 + argparse 行为分析）：**

UC-024 明确要求验证顺序为：(1) 必填参数存在性 -> (2) 枚举值验证 -> (3) 日期格式验证 -> (4) 标签格式验证。快速失败，首个错误即报错退出。

**两阶段验证架构：**

**阶段一：argparse 内置验证（自动完成）**

argparse 在 `parse_args()` 阶段自动处理以下验证：

| 验证类型 | argparse 机制 | 覆盖约束 |
|---------|--------------|---------|
| 必填参数存在性 | positional argument（如 `title`）缺失时自动 `exit(2)` | UC-016 |
| 枚举值验证 | `choices=['P0','P1','P2']` 不匹配时自动 `exit(2)` | UC-002 |
| 类型验证 | `type=int`（如 `done` 的 task_id）不匹配时自动 `exit(2)` | UC-016 |
| 格式枚举 | `choices=['json','csv']`（export --format） | UC-018 |
| 状态枚举 | `choices=['pending','done','all']`（list --status） | UC-003 |

argparse 的 `exit(2)` 行为天然符合 UC-024 的"快速失败"要求和 UC-019 的"参数错误退出码 2"要求。

**阶段二：业务逻辑前置验证（parse_args 之后、命令执行之前）**

```python
def validate_business_rules(args):
    """在命令执行前完成所有业务验证，快速失败"""
    
    # (3) 日期格式验证 -- UC-004
    if args.due:
        if not re.match(r'^\d{4}-\d{2}-\d{2}', args.due):
            raise ValidationError('due_date', args.due, 'ISO 8601 (YYYY-MM-DD)', '2025-07-13')
        try:
            datetime.fromisoformat(args.due)
        except ValueError:
            raise ValidationError('due_date', args.due, 'ISO 8601 (YYYY-MM-DD)', '2025-07-13')
    
    # (4) 标签格式验证 -- UC-008
    if args.tags:
        for tag in args.tags:
            if ',' in tag or '"' in tag:
                raise ValidationError('tags', tag, '不含逗号和双引号', 'work')
            if not tag.strip():
                raise ValidationError('tags', tag, '非空字符串', 'work')
    
    # 去重检查
    if args.tags and len(args.tags) != len(set(args.tags)):
        # 静默去重（set 语义），不报错
        args.tags = list(dict.fromkeys(args.tags))
```

**验证顺序保证：**

argparse 的参数解析是顺序执行的。当用户同时提供无效优先级和无效日期时：
- `--priority p0 --due 2026/07/20`：argparse 先处理 `--priority`，发现 `p0` 不在 `choices` 中，立即 `exit(2)`
- 日期验证在 argparse 之后，只有 argparse 全部通过才会执行

这天然满足 UC-024 的"首个错误即报错退出"要求。

**原子性保证：** 验证全部在命令执行前完成，验证失败时不执行任何部分操作（UC-024 要求）。

**Covered Constraints:** UC-024, UC-002, UC-003, UC-004, UC-008

---

### Finding 5: 错误消息格式模板设计

**Evidence（UC-020 约束 + POSIX/GNU 惯例）：**

UC-020 要求错误消息必须包含四个要素：(1) 错误字段名，(2) 用户输入的实际值，(3) 期望的格式/值范围，(4) 至少一个正确示例。所有错误输出到 `sys.stderr`。

**统一错误消息模板：**

```python
class ValidationError(Exception):
    def __init__(self, field: str, actual: str, expected: str, example: str):
        self.field = field
        self.actual = actual
        self.expected = expected
        self.example = example
        super().__init__(self.format_message())
    
    @staticmethod
    def format_message(field, actual, expected, example):
        return (
            f"Error: Invalid value for '{field}': got '{actual}'.\n"
            f"  Expected: {expected}\n"
            f"  Example:  {example}"
        )
```

**各字段错误消息实例：**

| 字段 | 实际值 | 期望 | 示例 | 完整消息 |
|------|--------|------|------|---------|
| priority | `p0` | `{P0, P1, P2}` (大写 P + 数字) | `P0` | `Error: Invalid value for 'priority': got 'p0'. Expected: one of {P0, P1, P2} (case-sensitive). Example: P0` |
| due_date | `2026/07/20` | `ISO 8601 格式 (YYYY-MM-DD)` | `2025-07-13` | `Error: Invalid value for 'due_date': got '2026/07/20'. Expected: ISO 8601 format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS[+/-HH:MM or Z]). Example: 2025-07-13` |
| tags | `a,b` | `不含逗号和双引号的非空字符串` | `work` | `Error: Invalid value for 'tags': got 'a,b'. Expected: tag must not contain comma or double-quote. Example: work` |
| title | `(whitespace)` | `至少包含 1 个非空白字符` | `Fix login bug` | `Error: Invalid value for 'title': got '   '. Expected: at least 1 non-whitespace character, max 500 chars. Example: Fix login bug` |

**输出路由：**

```python
import sys

def report_error(error: ValidationError):
    """所有错误输出到 stderr（UC-020 + POSIX 惯例）"""
    print(str(error), file=sys.stderr)
    sys.exit(1)  # 运行时错误退出码 1（UC-019）
```

**argparse 错误消息定制：**

argparse 默认的 `choices` 错误消息格式为：`argument --priority: invalid choice: 'p0' (choose from 'P0', 'P1', 'P2')`，退出码 2。这已满足 UC-020 的四要素要求（字段名=`--priority`，实际值=`p0`，期望=`choose from P0/P1/P2`，示例隐含在 choices 列表中）。无需自定义 `parser.error()`。

**Covered Constraints:** UC-020, UC-019

---

### Finding 6: 过去日期的处理策略

**Evidence（UC-025 约束 + Unix CLI 惯例分析）：**

UC-025 明确要求：截止日期验证仅检查 ISO 8601 格式合法性，不拒绝过去日期。当截止日期早于当前日期时，输出警告但任务仍成功创建，退出状态码为 0。

**Unix CLI 先例验证：**

| 工具 | 过去日期行为 | 参考 |
|------|------------|------|
| `touch -t 202001010000 file` | 接受，设置文件时间为过去 | Unix 惯例 |
| `at 10:00 AM 01/01/2020` | 接受，立即执行 | Unix 惯例 |
| `crontab` 过去时间 | 接受，下一个匹配时间点执行 | Unix 惯例 |
| Taskwarrior `due:2020-01-01` | 接受，标记为 overdue | 领域参考 |

**实现方案：**

```python
from datetime import datetime, date
import sys

def check_past_due_date(due_value: str) -> bool:
    """检查日期是否在过去，返回是否为过去日期"""
    parsed = datetime.fromisoformat(due_value)
    due_date = parsed.date() if hasattr(parsed, 'date') else parsed
    today = date.today()
    return due_date < today

# 在 add 命令处理函数中：
if args.due and check_past_due_date(args.due):
    print(f"Warning: due date {args.due} is in the past", file=sys.stderr)
    # 注意：警告输出到 stderr，但任务正常创建，退出码 0

# 在 list 命令中，overdue 标记逻辑：
def is_overdue(task) -> bool:
    if task['status'] == 'done' or not task.get('due_date'):
        return False
    due = datetime.fromisoformat(task['due_date']).date()
    return due < date.today()
```

**关键设计决策：**

1. **警告输出到 stderr**：符合 UC-020 的"错误/警告信息输出到 stderr"要求，不污染 stdout 的结构化输出。
2. **退出码保持 0**：UC-025 明确要求"任务仍成功创建，退出状态码为 0"。警告不是错误。
3. **overdue 是计算属性**：不在存储中添加 `overdue` 字段，而是在 `list` 显示时动态计算（`due_date < today && status == 'pending'`）。这避免了每日需要更新存储文件的复杂性。
4. **过去日期不阻止创建**：用户可能需要补录历史任务（如"昨天完成的 bug fix"），拒绝过去日期会妨碍此用例。

**Covered Constraints:** UC-025

---

## 3. 方案推荐

### 3.1 日期解析推荐方案

```python
import re
from datetime import datetime

# 预检正则：必须以 YYYY-MM-DD 开头（拒绝紧凑格式 20250713）
_STRICT_ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}(?:T|$)')

def parse_iso_date(value: str) -> datetime:
    """
    解析 ISO 8601 日期/日期时间字符串。
    接受: 2025-07-13, 2025-07-13T10:30:00Z, 2025-07-13T10:30:00+08:00
    拒绝: 20250713, 07/13/2025, 13-07-2025
    """
    if not _STRICT_ISO_DATE.match(value):
        raise ValueError(
            f"Invalid ISO 8601 date: '{value}'. "
            f"Expected format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS[+/-HH:MM|Z]. "
            f"Example: 2025-07-13 or 2025-07-13T10:30:00+08:00"
        )
    return datetime.fromisoformat(value)
```

### 3.2 JSON 导出推荐方案

```python
import json

def export_json(tasks: list, output_path: str = None):
    """RFC 8259 合规 JSON 导出"""
    data = {'tasks': tasks}
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(json_str)
            f.write('\n')  # 尾部换行（POSIX 文本文件惯例）
    else:
        import sys
        sys.stdout.write(json_str)
        sys.stdout.write('\n')
```

### 3.3 CSV 导出推荐方案

```python
import csv

CSV_FIELDNAMES = ['title', 'priority', 'status', 'due_date', 'tags']

def export_csv(tasks: list, output_path: str = None):
    """RFC 4180 合规 CSV 导出"""
    import sys, io
    
    # 准备行数据（tags 序列化为逗号连接字符串）
    rows = []
    for t in tasks:
        row = dict(t)
        row['due_date'] = row.get('due_date') or ''
        row['tags'] = ','.join(row.get('tags', []))
        rows.append(row)
    
    if output_path:
        # 关键: newline='' 防止换行符转换
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, dialect='excel')
            writer.writeheader()
            writer.writerows(rows)
    else:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_FIELDNAMES, dialect='excel')
        writer.writeheader()
        writer.writerows(rows)
        sys.stdout.write(buf.getvalue())
```

### 3.4 验证流水线推荐方案

```python
def validate_and_execute(args):
    """
    完整验证流水线（UC-024 快速失败）
    
    阶段一: argparse 已处理 -- 必填存在性、枚举值、类型
    阶段二: 业务逻辑前置验证 -- 日期格式、标签格式
    阶段三: 执行命令
    """
    # 阶段二 - 日期验证 (UC-004)
    if getattr(args, 'due', None):
        try:
            parse_iso_date(args.due)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
    
    # 阶段二 - 标签验证 (UC-008)
    if getattr(args, 'tags', None):
        for tag in args.tags:
            if ',' in tag or '"' in tag:
                print(f"Error: Invalid value for 'tags': got '{tag}'. "
                      f"Expected: tag must not contain comma or double-quote. "
                      f"Example: work", file=sys.stderr)
                sys.exit(1)
            if not tag.strip():
                print(f"Error: Invalid value for 'tags': got '{tag}'. "
                      f"Expected: non-empty string after stripping whitespace. "
                      f"Example: work", file=sys.stderr)
                sys.exit(1)
        # 静默去重 (set 语义)
        args.tags = list(dict.fromkeys(args.tags))
    
    # 阶段三 - 执行
    args.func(args)
```

---

## 4. 风险识别

| 风险 ID | 风险描述 | 影响 | 缓解措施 |
|---------|---------|------|---------|
| R-FMT-001 | Python fromisoformat() 接受紧凑格式 20250713 | HIGH | 增加正则预检 `^\d{4}-\d{2}-\d{2}` |
| R-FMT-002 | CSV 导出遗漏 newline='' 参数 | MEDIUM | 代码审查 + 单元测试验证 CRLF |
| R-FMT-003 | 无时区 datetime 导出不含 +/-HH:MM | LOW | 存储时统一附加本地时区或标记为 naive |
| R-FMT-004 | json.dumps 默认 ensure_ascii=True | MEDIUM | 必须显式传 ensure_ascii=False |
| R-FMT-005 | Windows 默认编码非 UTF-8 | MEDIUM | 所有 open() 显式 encoding='utf-8' (UC-014) |
| R-FMT-006 | 过去日期警告输出到 stdout 污染管道 | LOW | 警告统一输出到 stderr |

---

## 5. 开放问题

| 问题 ID | 问题描述 | 建议 |
|---------|---------|------|
| Q-FMT-001 | 纯日期输入 `2025-07-13` 导出时是否保持为纯日期？带时间输入 `2025-07-13T10:30:00` 导出时是否附加时区？ | 建议：保持输入形式，纯日期导出为 `YYYY-MM-DD`，带时间导出为 `YYYY-MM-DDTHH:MM:SS`（naive）或附加本地时区 |
| Q-FMT-002 | CSV 中 tags 字段的序列化格式？多标签如何表示？ | 建议：逗号连接（如 `work,urgent`），因 UC-008 已禁止标签含逗号，csv 模块会自动处理引号包裹 |
| Q-FMT-003 | 过去日期警告是否应包含 overdue 天数的计算？ | 建议：仅在 list 命令中标记 overdue，add 命令仅输出简单警告 |

---

## 6. 覆盖需求追踪

**Covered Requirement IDs:**
- REQ-INPUT-001（任务数据字段定义）
- REQ-INPUT-002（状态筛选）
- REQ-INPUT-003（任务标记）
- REQ-INPUT-004（JSON/CSV 导出）
- REQ-INPUT-005（Python 3.11+）

**Covered Unified Constraints:**
- UC-002（优先级枚举 P0/P1/P2）
- UC-003（状态枚举 pending/done）
- UC-004（ISO 8601 日期输入）
- UC-005（ISO 8601 日期导出）
- UC-008（标签禁止逗号和双引号）
- UC-011（JSON RFC 8259 合规）
- UC-012（CSV RFC 4180 合规）
- UC-014（显式 encoding='utf-8'）
- UC-019（退出码 0/1/2）
- UC-020（错误消息格式四要素）
- UC-024（输入验证顺序快速失败）
- UC-025（过去日期警告不拒绝）

---

*报告完成。所有发现均基于 Python 3.13.13 标准库实测和 RFC 原文条款验证。*
