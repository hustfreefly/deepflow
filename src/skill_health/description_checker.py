"""
DescriptionChecker — Length validation and quality scoring for skill descriptions.

Validates description length, computes a quality score based on action verbs,
target objects, and ideal length range, and generates human-readable suggestions.
"""

import re
from typing import List

from src.skill_health.check_result import CheckResult


# Predefined action verbs for quality scoring.
# Each entry is matched with word-boundary regex to avoid substring false positives
# (e.g. 'create' inside 'procreate').
ACTION_VERBS: List[str] = [
    # English action verbs commonly found in skill/tool descriptions
    "analyze",
    "build",
    "calculate",
    "check",
    "collect",
    "compare",
    "convert",
    "create",
    "delete",
    "deploy",
    "detect",
    "download",
    "edit",
    "evaluate",
    "execute",
    "export",
    "extract",
    "fetch",
    "format",
    "generate",
    "get",
    "import",
    "install",
    "integrate",
    "list",
    "manage",
    "monitor",
    "parse",
    "process",
    "query",
    "read",
    "remove",
    "render",
    "report",
    "resolve",
    "run",
    "scan",
    "search",
    "send",
    "set",
    "sort",
    "start",
    "stop",
    "sync",
    "test",
    "track",
    "transform",
    "update",
    "upload",
    "validate",
    "verify",
    "watch",
    # Chinese action verbs (matched as whole tokens between non-word boundaries)
    "分析",
    "构建",
    "计算",
    "检查",
    "收集",
    "比较",
    "转换",
    "创建",
    "删除",
    "部署",
    "检测",
    "下载",
    "编辑",
    "评估",
    "执行",
    "导出",
    "提取",
    "获取",
    "格式化",
    "生成",
    "导入",
    "安装",
    "集成",
    "列出",
    "管理",
    "监控",
    "解析",
    "处理",
    "查询",
    "读取",
    "移除",
    "渲染",
    "报告",
    "解析",
    "运行",
    "扫描",
    "搜索",
    "发送",
    "设置",
    "排序",
    "启动",
    "停止",
    "同步",
    "测试",
    "跟踪",
    "转换",
    "更新",
    "上传",
    "验证",
    "校验",
    "监控",
]

# Predefined target objects for quality scoring.
TARGET_OBJECTS: List[str] = [
    # English target objects
    "api",
    "application",
    "browser",
    "cache",
    "channel",
    "cluster",
    "command",
    "component",
    "config",
    "configuration",
    "connection",
    "container",
    "dashboard",
    "database",
    "data",
    "device",
    "document",
    "email",
    "endpoint",
    "error",
    "event",
    "file",
    "folder",
    "function",
    "gateway",
    "host",
    "image",
    "index",
    "instance",
    "interface",
    "job",
    "key",
    "layer",
    "log",
    "message",
    "metric",
    "model",
    "module",
    "network",
    "node",
    "notification",
    "package",
    "page",
    "parameter",
    "path",
    "permission",
    "pipeline",
    "plugin",
    "policy",
    "port",
    "process",
    "project",
    "protocol",
    "queue",
    "record",
    "registry",
    "report",
    "repository",
    "request",
    "resource",
    "response",
    "role",
    "route",
    "rule",
    "schema",
    "script",
    "server",
    "service",
    "session",
    "signal",
    "socket",
    "storage",
    "stream",
    "table",
    "task",
    "template",
    "thread",
    "token",
    "topic",
    "url",
    "user",
    "variable",
    "volume",
    "worker",
    # Chinese target objects
    "接口",
    "应用",
    "浏览器",
    "缓存",
    "频道",
    "集群",
    "命令",
    "组件",
    "配置",
    "连接",
    "容器",
    "仪表板",
    "数据库",
    "数据",
    "设备",
    "文档",
    "邮件",
    "端点",
    "错误",
    "事件",
    "文件",
    "文件夹",
    "函数",
    "网关",
    "主机",
    "镜像",
    "索引",
    "实例",
    "接口",
    "任务",
    "密钥",
    "层",
    "日志",
    "消息",
    "指标",
    "模型",
    "模块",
    "网络",
    "节点",
    "通知",
    "包",
    "页面",
    "参数",
    "路径",
    "权限",
    "管道",
    "插件",
    "策略",
    "端口",
    "进程",
    "项目",
    "协议",
    "队列",
    "记录",
    "注册表",
    "报告",
    "仓库",
    "请求",
    "资源",
    "响应",
    "角色",
    "路由",
    "规则",
    "模式",
    "脚本",
    "服务器",
    "服务",
    "会话",
    "信号",
    "套接字",
    "存储",
    "流",
    "表",
    "任务",
    "模板",
    "线程",
    "令牌",
    "主题",
    "链接",
    "用户",
    "变量",
    "卷",
    "工作器",
]


class DescriptionChecker:
    """Validates description length and computes quality score.

    Usage::

        checker = DescriptionChecker()
        result = checker.check("Build and deploy container images to Kubernetes")
        # result.is_valid, result.quality_score, result.suggestion, ...
    """

    def __init__(
        self,
        min_length: int = 30,
        max_length: int = 500,
        ideal_low: int = 80,
        ideal_high: int = 300,
        base_score: int = 50,
        action_verb_bonus: int = 20,
        target_object_bonus: int = 15,
        ideal_length_bonus: int = 15,
    ) -> None:
        """Initialize DescriptionChecker with configurable thresholds.

        Args:
            min_length: Minimum character count for 'valid' status.
            max_length: Maximum character count for 'valid' status.
            ideal_low: Lower bound of ideal length range for bonus.
            ideal_high: Upper bound of ideal length range for bonus.
            base_score: Starting quality score before bonuses.
            action_verb_bonus: Points added when at least one action verb is found.
            target_object_bonus: Points added when at least one target object is found.
            ideal_length_bonus: Points added when length is in ideal range.
        """
        self.min_length = min_length
        self.max_length = max_length
        self.ideal_low = ideal_low
        self.ideal_high = ideal_high
        self.base_score = base_score
        self.action_verb_bonus = action_verb_bonus
        self.target_object_bonus = target_object_bonus
        self.ideal_length_bonus = ideal_length_bonus

        # Pre-compile regex patterns for performance.
        # Word-boundary regex with IGNORECASE avoids substring false positives.
        self._verb_patterns = [
            re.compile(rf"\b{re.escape(verb)}\b", re.IGNORECASE)
            for verb in ACTION_VERBS
        ]
        self._object_patterns = [
            re.compile(rf"\b{re.escape(obj)}\b", re.IGNORECASE)
            for obj in TARGET_OBJECTS
        ]

    def check(self, description: str) -> CheckResult:
        """Run length validation, quality scoring, and suggestion generation.

        Args:
            description: The skill description text to check.

        Returns:
            CheckResult with is_valid, length, status, quality_score,
            warnings, and suggestion fields populated.
        """
        # Handle None or non-string gracefully — treat as empty.
        if not isinstance(description, str):
            description = ""

        # Strip whitespace for length calculation and empty detection.
        stripped = description.strip()
        length = len(stripped)

        # --- Length validation ---
        if length < self.min_length:
            status = "too_short"
            is_valid = False
        elif length > self.max_length:
            status = "too_long"
            is_valid = False
        else:
            status = "valid"
            is_valid = True

        # --- Quality scoring ---
        quality_score = self._compute_quality_score(stripped, length)

        # --- Warnings ---
        warnings = self._collect_warnings(stripped)

        # --- Suggestions ---
        suggestion = self._generate_suggestion(status)

        return CheckResult(
            is_valid=is_valid,
            length=length,
            status=status,
            quality_score=quality_score,
            warnings=warnings,
            suggestion=suggestion,
        )

    def _compute_quality_score(self, text: str, length: int) -> int:
        """Compute quality score: base + action_verb + target_object + ideal_length.

        Score is capped at 100.
        """
        score = self.base_score

        # Check for at least one action verb (word-boundary match).
        if any(pattern.search(text) for pattern in self._verb_patterns):
            score += self.action_verb_bonus

        # Check for at least one target object (word-boundary match).
        if any(pattern.search(text) for pattern in self._object_patterns):
            score += self.target_object_bonus

        # Check if length is in ideal range.
        if self.ideal_low <= length <= self.ideal_high:
            score += self.ideal_length_bonus

        # Cap at 100.
        return min(score, 100)

    def _collect_warnings(self, text: str) -> List[str]:
        """Collect non-blocking warnings about the description."""
        warnings: List[str] = []

        # Check for non-ASCII characters.
        if any(ord(char) > 127 for char in text):
            warnings.append(
                "Description contains non-ASCII characters, "
                "which may cause display issues in some environments."
            )

        return warnings

    def _generate_suggestion(self, status: str) -> str | None:
        """Generate human-readable suggestion based on status."""
        if status == "too_short":
            return "信息不足，建议补充功能说明"
        elif status == "too_long":
            return "描述过长，建议精简至核心功能"
        return None
