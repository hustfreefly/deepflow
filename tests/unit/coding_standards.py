"""
Coding Standards Module — DeepFlow V3.0 编码风格规范

本模块定义 .deepflow/ 核心模块的编码风格规范，基于三个独立审计的综合发现：
- Style Auditor 1: 代码风格审计（P0×3, P1×5, P2×5, P3×3）
- Style Auditor 2: API接口设计审计（P0×3, P1×6, P2×5）
- Style Auditor 3: 防御性编程审计（P0×5, P1×4, P2×5, P3×5）

作者: 小满 (综合审计结果)
日期: 2026-04-15
版本: 1.0
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, Union

# ─────────────────────────────────────────────────────────
# 核心规范常量
# ─────────────────────────────────────────────────────────

# 日志格式规范
LOG_FORMAT_VERSION = "2.0"  # 纯字符串 + kwargs 模式
LOG_MESSAGE_MAX_LENGTH = 1000

# Score 尺度规范（关键！）
SCORE_SCALE_0_1 = "0-1"      # ConfigLoader, Observability
SCORE_SCALE_0_100 = "0-100"  # QualityGate, PipelineEngine
SCALE_CONVERSION_FACTOR = 100.0

# 命名规范
LOGGER_NAME_PATTERN = r"^[a-z][a-z0-9_]*$"  # snake_case
MODULE_SEPARATOR = "# ──"  # 统一分隔线风格

# 类型注解规范
REQUIRED_TYPE_ANNOTATION_THRESHOLD = 0.90  # 90% 覆盖率

# 文档规范
DOCSTRING_STYLE = "google"  # Google Style
MAX_METHOD_LINES = 50  # 方法长度上限


# ─────────────────────────────────────────────────────────
# 规范违规检测器
# ─────────────────────────────────────────────────────────

# 类型定义
ViolationLevel = Literal["P0", "P1", "P2", "P3"]
ViolationCategory = Literal["日志", "尺度", "类型", "防御性", "命名", "格式", "文档", "风格", "IO", "编码", "文件"]


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    error: Optional[str] = None


@dataclass
class Violation:
    """规范违规记录"""
    level: ViolationLevel  # P0/P1/P2/P3
    category: ViolationCategory  # 日志/尺度/类型/防御性/命名
    file: str
    line: int
    rule: str
    description: str  # 必须无默认值
    rule_code: str = ""  # 可选，有默认值
    current_code: str = ""  # 可选，有默认值
    suggested_fix: str = ""  # 可选，有默认值
    exception_type: Optional[str] = None  # 可选，有默认值
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "category": self.category,
            "file": self.file,
            "line": self.line,
            "rule": self.rule,
            "rule_code": self.rule_code,
            "description": self.description,
            "current_code": self.current_code[:200] if self.current_code else "",
            "current_code_truncated": len(self.current_code) > 200 if self.current_code else False,
            "suggested_fix": self.suggested_fix[:200] if self.suggested_fix else "",
            "suggested_fix_truncated": len(self.suggested_fix) > 200 if self.suggested_fix else False,
            "exception_type": self.exception_type,
        }


@dataclass
class AuditReport:
    """审计报告"""
    module_name: str
    total_violations: int = 0
    p0_count: int = 0
    p1_count: int = 0
    p2_count: int = 0
    p3_count: int = 0
    violations: List[Violation] = field(default_factory=list)
    
    def add_violation(self, v: Violation) -> None:
        self.violations.append(v)
        self.total_violations += 1
        if v.level == "P0":
            self.p0_count += 1
        elif v.level == "P1":
            self.p1_count += 1
        elif v.level == "P2":
            self.p2_count += 1
        elif v.level == "P3":
            self.p3_count += 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_name": self.module_name,
            "summary": {
                "total": self.total_violations,
                "P0": self.p0_count,
                "P1": self.p1_count,
                "P2": self.p2_count,
                "P3": self.p3_count,
            },
            "violations": [v.to_dict() for v in self.violations],
        }


# ─────────────────────────────────────────────────────────
# 规范检查规则库（基于审计发现）
# ─────────────────────────────────────────────────────────

class CodingStandardsChecker:
    """
    编码风格规范检查器
    
    检测以下违规模式：
    1. 日志格式违规（P0）
    2. Score尺度混用（P0）
    3. 裸except捕获（P0）
    4. 类型注解缺失（P1）
    5. 命名不一致（P1）
    6. 魔法数字（P1）
    7. 防御性编程缺陷（P0/P1）
    """
    
    # P0 严重违规模式
    P0_PATTERNS = {
        "bare_except": {
            "pattern": r"except\s*:\s*$|except\s+Exception\s*:\s*$|except\s+Exception\s+as\s+\w+\s*:\s*$",
            "description": "裸except或过于宽泛的Exception捕获（包括SystemExit、KeyboardInterrupt）",
            "suggestion": "使用具体异常类型，如 `except OSError:` 或 `except (ValueError, TypeError):`",
        },
        "fstring_in_logger": {
            "pattern": r'logger\.(info|warning|error|debug|critical)\s*\(\s*f["\']',
            "description": "日志中使用f-string嵌入变量，破坏结构化日志解析",
            "suggestion": "使用纯字符串 + kwargs: `logger.info(\"msg\", key=value)`",
        },
        "unused_logging_import": {
            "pattern": r"^import logging$",
            "context_check": "Observability.get_logger",
            "description": "死导入 — 使用Observability.get_logger()而非标准logging",
            "suggestion": "删除 `import logging`，保留 `from observability import Observability`",
        },
        "score_scale_confusion_0_1": {
            "pattern": r"threshold\s*=\s*0\.\d+",
            "context_check": "DimensionConfig",
            "description": "Score尺度混用：0-1尺度值用于要求0-100尺度的接口",
            "suggestion": "统一转换为0-100: `threshold=dim.threshold * 100`",
        },
        "os_write_no_check": {
            "pattern": r"os\.write\s*\([^)]+\)\s*$",
            "description": "os.write()不检查返回值，大内容可能截断",
            "suggestion": "检查返回值: `written = os.write(...); assert written == len(data)`",
        },
    }
    
    # P1 重要违规模式
    P1_PATTERNS = {
        "missing_param_type": {
            "pattern": r"def\s+\w+\s*\(\s*self\s*,\s*\w+\s*\)(?!\s*->)",
            "description": "方法参数缺少类型注解",
            "suggestion": "添加类型注解: `def method(self, param: Type) -> ReturnType:`",
        },
        "logger_name_inconsistent": {
            "pattern": r'Observability\.get_logger\s*\(\s*["\'](?!coordinator|pipeline_engine|config_loader|quality_gate|blackboard_manager|resilience_manager|observability)(?!.*\{)',
            "description": "logger命名与模块名不一致（排除模板字符串如{module_name}）",
            "suggestion": "统一使用模块snake_case名: `Observability.get_logger(\"module_name\")`",
        },
    }
    
    # 注意: import_order_violation 规则已删除，因为逐行扫描无法实现跨行匹配
    # 建议使用 isort 或 ruff 工具进行 import 排序检查
    
    # P2 建议改进模式
    P2_PATTERNS = {
        "magic_number": {
            "pattern": r"(?<!_)\b(?!\d+\s*=)(?!.*['\"]\d+.*['\"])(?!.*#.*\d+)(?!.*\"\"\".*\d+.*\"\"\")(200|1000|100|50)\b(?!\s*=)",
            "description": "建议将数字提取为命名常量（排除常量定义、字符串、注释）",
            "suggestion": "考虑提取为模块级常量: `OUTPUT_PREVIEW_LENGTH = 200`",
        },
        "v26_fix_comment": {
            "pattern": r"#\s*V2\.6-FIX:",
            "description": "残留的历史修复标记注释",
            "suggestion": "清理为常规注释或docstring",
        },
        "getattr_chain": {
            "pattern": r"getattr\([^)]+getattr\(",
            "description": "getattr链式调用过于冗长",
            "suggestion": "使用hasattr检查或dataclasses.asdict()",
        },
    }
    
    # 注意: single_line_docstring 规则已移除，因为对于简单类/方法是合理的
    # 只有在 strict_mode=True 且明确需要详细文档时才检查
    # P3 可选优化模式
    P3_PATTERNS = {
        "unused_set_import": {
            "pattern": r"^from typing import.*\bSet\b",
            "context_check": "Set",
            "description": "typing.Set 导入后未使用",
            "suggestion": "删除未使用的 Set 导入",
        },
        "old_style_type_hints": {
            "pattern": r"\b(Dict|List|Optional|Tuple)\[",
            "description": "使用旧式 typing 类型，而非新 style (dict|list|)",
            "suggestion": "使用新 style: `dict[str, Any]` 替代 `Dict[str, Any]`",
        },
    }
    
    def __init__(self, strict_mode: bool = False):
        self.strict_mode = strict_mode
        self.violations: List[Violation] = []
        # 预编译所有正则表达式
        self._compiled_patterns: Dict[str, Dict[str, Any]] = {}
        for level, patterns in [("P0", self.P0_PATTERNS), ("P1", self.P1_PATTERNS), 
                                ("P2", self.P2_PATTERNS), ("P3", self.P3_PATTERNS)]:
            self._compiled_patterns[level] = {
                name: {**rule, "_regex": re.compile(rule["pattern"])}
                for name, rule in patterns.items()
            }
    
    def check_file(self, filepath: Path) -> AuditReport:
        """检查单个文件"""
        report = AuditReport(module_name=filepath.stem)
        
        try:
            content = filepath.read_text(encoding="utf-8")
            lines = content.split("\n")
        except FileNotFoundError as e:
            raise FileNotFoundError(f"文件不存在: {filepath}") from e
        except PermissionError as e:
            raise PermissionError(f"无权限读取文件: {filepath}") from e
        except UnicodeDecodeError as e:
            raise UnicodeDecodeError(e.encoding, e.object, e.start, e.end, f"文件编码不是UTF-8: {filepath}") from e
        except OSError as e:
            raise OSError(f"操作系统错误读取文件: {filepath}: {e}") from e
        
        # 检查P0模式（使用预编译正则）
        for rule_name, rule in self._compiled_patterns["P0"].items():
            # 基础设施模块例外：允许使用标准logging库
            INFRASTRUCTURE_MODULES = {"observability"}
            if rule_name == "unused_logging_import" and filepath.stem in INFRASTRUCTURE_MODULES:
                continue
            for i, line in enumerate(lines, 1):
                if rule["_regex"].search(line):
                    # 上下文检查（如果有）
                    if "context_check" in rule:
                        if rule["context_check"] not in content:
                            continue
                    
                    v = Violation(
                        level="P0",
                        category="防御性" if "except" in rule_name or "os_write" in rule_name else "日志",
                        file=str(filepath),
                        line=i,
                        rule=rule_name,
                        description=rule["description"],
                        current_code=line.strip(),
                        suggested_fix=rule["suggestion"],
                    )
                    report.add_violation(v)
        
        # 检查P1模式（使用预编译正则）
        for rule_name, rule in self._compiled_patterns["P1"].items():
            for i, line in enumerate(lines, 1):
                if rule["_regex"].search(line):
                    v = Violation(
                        level="P1",
                        category="类型" if "type" in rule_name else "命名" if "logger" in rule_name else "格式",
                        file=str(filepath),
                        line=i,
                        rule=rule_name,
                        description=rule["description"],
                        current_code=line.strip(),
                        suggested_fix=rule["suggestion"],
                    )
                    report.add_violation(v)
        
        # 检查P2模式（使用预编译正则）
        if self.strict_mode:
            for rule_name, rule in self._compiled_patterns["P2"].items():
                for i, line in enumerate(lines, 1):
                    if rule["_regex"].search(line):
                        v = Violation(
                            level="P2",
                            category="风格",
                            file=str(filepath),
                            line=i,
                            rule=rule_name,
                            description=rule["description"],
                            current_code=line.strip(),
                            suggested_fix=rule["suggestion"],
                        )
                        report.add_violation(v)
        
        # 检查P3模式（使用预编译正则）
        if self.strict_mode:
            for rule_name, rule in self._compiled_patterns["P3"].items():
                for i, line in enumerate(lines, 1):
                    if rule["_regex"].search(line):
                        v = Violation(
                            level="P3",
                            category="风格",
                            file=str(filepath),
                            line=i,
                            rule=rule_name,
                            description=rule["description"],
                            current_code=line.strip(),
                            suggested_fix=rule["suggestion"],
                        )
                        report.add_violation(v)
        
        return report
    
    def check_directory(self, directory: Path, pattern: str = "*.py") -> List[AuditReport]:
        """检查整个目录，异常文件记录错误但继续扫描"""
        reports = []
        for pyfile in directory.rglob(pattern):
            # 跳过__pycache__
            if "__pycache__" in str(pyfile):
                continue
            try:
                report = self.check_file(pyfile)
                reports.append(report)
            except (FileNotFoundError, PermissionError, UnicodeDecodeError, OSError) as e:
                # 创建错误报告，包含异常信息
                error_report = AuditReport(module_name=pyfile.stem)
                error_report.add_violation(Violation(
                    level="P0",
                    category="IO",
                    file=str(pyfile),
                    line=0,
                    rule="file_access_error",
                    rule_code="CS-P0-005",
                    description=f"无法访问文件: {type(e).__name__}: {e}",
                    exception_type=type(e).__name__,
                ))
                reports.append(error_report)
        return reports


# ─────────────────────────────────────────────────────────
# Score 尺度转换工具（关键！）
# ─────────────────────────────────────────────────────────

class ScoreScaleConverter:
    """
    Score尺度转换器
    
    解决审计发现的严重问题：0-1 vs 0-100 尺度混用
    """
    
    @staticmethod
    def to_0_100(score_0_1: float) -> float:
        """0-1 → 0-100"""
        if math.isnan(score_0_1) or math.isinf(score_0_1):
            raise ValueError(f"Score must be finite, got {score_0_1}")
        if not 0.0 <= score_0_1 <= 1.0:
            raise ValueError(f"Score {score_0_1} out of 0-1 range")
        return score_0_1 * SCALE_CONVERSION_FACTOR
    
    @staticmethod
    def to_0_1(score_0_100: float) -> float:
        """0-100 → 0-1"""
        if math.isnan(score_0_100) or math.isinf(score_0_100):
            raise ValueError(f"Score must be finite, got {score_0_100}")
        if not 0.0 <= score_0_100 <= 100.0:
            raise ValueError(f"Score {score_0_100} out of 0-100 range")
        return score_0_100 / SCALE_CONVERSION_FACTOR
    
    @staticmethod
    def validate_scale(score: float, expected_scale: str) -> bool:
        """验证score是否在指定尺度范围内"""
        if math.isnan(score) or math.isinf(score):
            return False
        if expected_scale == SCORE_SCALE_0_1:
            return 0.0 <= score <= 1.0
        elif expected_scale == SCORE_SCALE_0_100:
            return 0.0 <= score <= 100.0
        return False
    
    @staticmethod
    def auto_convert(score: float, from_scale: str, to_scale: str) -> float:
        """自动尺度转换"""
        if math.isnan(score) or math.isinf(score):
            raise ValueError(f"Score must be finite, got {score}")
        VALID_SCALES = (SCORE_SCALE_0_1, SCORE_SCALE_0_100)
        if from_scale not in VALID_SCALES or to_scale not in VALID_SCALES:
            raise ValueError(f"Unknown scale: {from_scale} → {to_scale}. Valid: {VALID_SCALES}")
        if from_scale == to_scale:
            return score
        if from_scale == SCORE_SCALE_0_1 and to_scale == SCORE_SCALE_0_100:
            return ScoreScaleConverter.to_0_100(score)
        if from_scale == SCORE_SCALE_0_100 and to_scale == SCORE_SCALE_0_1:
            return ScoreScaleConverter.to_0_1(score)
        raise ValueError(f"Unknown scale conversion: {from_scale} → {to_scale}")


# ─────────────────────────────────────────────────────────
# 日志格式规范工具
# ─────────────────────────────────────────────────────────

class LoggerFormatValidator:
    """
    日志格式验证器
    
    确保所有模块使用统一的结构化日志格式
    """
    
    VALID_LOG_LEVELS = {"info", "warning", "error", "debug", "critical", "exception"}
    
    @classmethod
    def validate_log_call(cls, level: str, message: str, kwargs: Dict[str, Any]) -> ValidationResult:
        """
        验证日志调用是否符合规范
        
        Returns:
            ValidationResult: is_valid=True/False, error=错误消息或None
        """
        # 检查日志级别
        if level not in cls.VALID_LOG_LEVELS:
            return ValidationResult(is_valid=False, error=f"Invalid log level: {level}")
        
        # 检查消息格式（必须为纯字符串，无f-string）
        if "{" in message and "}" in message:
            return ValidationResult(is_valid=False, error="Message contains f-string interpolation, use kwargs instead")
        
        return ValidationResult(is_valid=True, error=None)
    
    @classmethod
    def build_log_call(cls, level: str, event: str, **kwargs: Any) -> str:
        """
        构建规范的日志调用代码
        
        Example:
            >>> build_log_call("info", "stage_executing", stage_name="init", score=0.85)
            'logger.info("stage_executing", stage_name="init", score=0.85)'
        """
        kwargs_str = ", ".join([f"{k}={repr(v)}" for k, v in kwargs.items()])
        return f'logger.{level}("{event}"{", " + kwargs_str if kwargs_str else ""})'


# ─────────────────────────────────────────────────────────
# 代码模板生成器
# ─────────────────────────────────────────────────────────

class CodeTemplateGenerator:
    """
    生成符合规范的代码模板
    """
    
    @staticmethod
    def module_header(module_name: str, description: str) -> str:
        """生成模块头部注释"""
        return f'''"""
{module_name} — {description}

Author: 小满
Date: 2026-04-15
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────
# 导入规范: stdlib → third-party → local
# ─────────────────────────────────────────────────────────

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml  # third-party

from observability import Observability  # local

# 使用Observability结构化logger（禁止import logging）
logger = Observability.get_logger("{module_name}")

# ─────────────────────────────────────────────────────────
# 常量定义（禁止魔法数字）
# ─────────────────────────────────────────────────────────

DEFAULT_TIMEOUT = 120
MAX_RETRIES = 3
OUTPUT_PREVIEW_LENGTH = 200
'''
    
    @staticmethod
    def method_template(method_name: str, params: List[Tuple[str, str, str]]) -> str:
        """
        生成符合规范的方法模板
        
        Args:
            method_name: 方法名
            params: [(param_name, param_type, default_value), ...]
        """
        # 构建参数列表
        param_list = ["self"]
        for name, ptype, default in params:
            if default:
                param_list.append(f"{name}: {ptype} = {default}")
            else:
                param_list.append(f"{name}: {ptype}")
        
        params_str = ", ".join(param_list)
        
        return f'''
    def {method_name}({params_str}) -> Any:
        """
        方法描述
        
        Args:
{chr(10).join([f"            {name}: 参数描述" for name, _, _ in params])}
        
        Returns:
            返回类型描述
        """
        # 结构化日志记录
        logger.info("{method_name}_start", {", ".join([f"{name}={name}" for name, _, _ in params])})
        
        try:
            # 方法实现
            result = None  # TODO: 实现
            
            logger.info("{method_name}_complete", result=result)
            return result
            
        except (RuntimeError, OSError) as e:
            logger.error("{method_name}_failed", error=str(e), error_type=type(e).__name__)
            raise
'''


# ─────────────────────────────────────────────────────────
# 主入口：命令行检查工具
# ─────────────────────────────────────────────────────────

def main() -> None:
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="DeepFlow Coding Standards Checker")
    parser.add_argument("path", type=Path, help="Path to file or directory to check")
    parser.add_argument("--strict", action="store_true", help="Enable strict mode (include P2 checks)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    checker = CodingStandardsChecker(strict_mode=args.strict)
    
    if args.path.is_file():
        reports = [checker.check_file(args.path)]
    else:
        reports = checker.check_directory(args.path)
    
    # 汇总
    total_p0 = sum(r.p0_count for r in reports)
    total_p1 = sum(r.p1_count for r in reports)
    total_p2 = sum(r.p2_count for r in reports)
    
    if args.json:
        import json as json_lib
        output = {
            "summary": {
                "files_checked": len(reports),
                "total_p0": total_p0,
                "total_p1": total_p1,
                "total_p2": total_p2,
            },
            "reports": [r.to_dict() for r in reports],
        }
        print(json_lib.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"\n🔍 Coding Standards Check Complete")
        print(f"   Files checked: {len(reports)}")
        print(f"   P0 (Critical): {total_p0}")
        print(f"   P1 (Important): {total_p1}")
        print(f"   P2 (Suggestion): {total_p2}")
        
        if total_p0 > 0:
            print(f"\n⚠️  {total_p0} P0 violations found — fix required before commit!")
            for r in reports:
                for v in r.violations:
                    if v.level == "P0":
                        print(f"   {v.file}:{v.line} — {v.rule}: {v.description}")


if __name__ == "__main__":
    main()
