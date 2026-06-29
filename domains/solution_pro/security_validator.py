"""
安全验证器，提供输入清理和路径遍历检测

Version: 2.1.0
Author: DeepFlow Solution Pro
Date: 2026-06-01
"""

"""
V1-LEGACY: This file is part of V1 pipeline (10-stage architecture).
V2 uses MasterOrchestrator + PlanningOrchestrator + ResearchOrchestrator + ReviewQCOrchestrator.
Do not import this file for new V2 workflows.
"""

"""
Security Validator - 纯安全验证器
==================================

职责：
1. 输入参数验证（topic, solution_type, mode等）
2. Unicode字符过滤与清理
3. 路径遍历检测
4. 枚举值验证

禁止：任何执行逻辑、外部调用、状态修改
"""

import re
import unicodedata
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """验证结果数据类"""
    is_valid: bool
    errors: List[str]
    sanitized_topic: Optional[str] = None


class SecurityValidator:
    """纯安全验证器，无执行逻辑"""
    
    # 允许的mode
    VALID_MODES = ["standard", "rigorous"]
    # 允许的solution_type
    VALID_TYPES = ["architecture", "business", "technical"]
    # 危险路径模式
    DANGEROUS_PATTERNS = ['..', '../', '..\\', './', '~', '/', '\\']
    
    def validate_inputs(self, topic: str, solution_type: str, mode: str, 
                       constraints: list = None, stakeholders: list = None) -> ValidationResult:
        """
        验证所有输入参数
        
        Args:
            topic: 设计主题
            solution_type: 方案类型
            mode: 运行模式
            constraints: 约束条件列表
            stakeholders: 利益相关者列表
        
        Returns:
            ValidationResult: 验证结果
        """
        errors = []
        
        # 验证topic
        if not topic or len(topic.strip()) == 0:
            errors.append("Topic cannot be empty")
        elif len(topic) < 5:
            errors.append(f"Topic too short (minimum 5 characters): '{topic}'")
        elif len(topic) > 200:
            errors.append(f"Topic too long (maximum 200 characters)")
        
        # 验证solution_type
        if solution_type not in self.VALID_TYPES:
            errors.append(f"Invalid solution_type: {solution_type}, must be one of {self.VALID_TYPES}")
        
        # 验证mode
        if mode not in self.VALID_MODES:
            errors.append(f"Invalid mode: {mode}, must be one of {self.VALID_MODES}")
        
        # 验证constraints类型
        if constraints is not None and not isinstance(constraints, list):
            errors.append("Constraints must be a list or None")
        
        # 验证stakeholders类型
        if stakeholders is not None and not isinstance(stakeholders, list):
            errors.append("Stakeholders must be a list or None")
        
        # 路径遍历检查（仅当topic有效时执行）
        if topic and len(errors) == 0:
            try:
                self.check_path_traversal(topic)
            except ValueError as e:
                errors.append(str(e))
        
        # 清理topic（仅当topic有效时执行）
        sanitized = self.sanitize_topic(topic) if topic and len([e for e in errors if "Topic" in e]) == 0 else None
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            sanitized_topic=sanitized
        )
    
    def sanitize_topic(self, topic: str) -> str:
        """
        清理topic，仅保留安全字符
        
        过滤规则：
        - 只保留字母、数字、下划线、中文字符、连字符
        - 移除控制字符、格式字符、代理字符等危险Unicode类别
        - 截断到30字符
        
        Args:
            topic: 原始主题字符串
        
        Returns:
            清理后的安全主题字符串
        """
        # 替换危险字符为下划线
        safe_topic = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', topic)
        # 过滤控制字符
        safe_topic = ''.join(
            c for c in safe_topic 
            if unicodedata.category(c) not in ['Cc', 'Cf', 'Cs', 'Co', 'Cn']
        )
        return safe_topic[:30]  # 限制长度
    
    def check_path_traversal(self, topic: str) -> None:
        """
        检查topic中是否包含路径遍历模式
        
        检测的危险模式包括：
        - '..' (父目录引用)
        - '../' 或 '..\\' (相对路径遍历)
        - './' (当前目录引用)
        - '~' (用户主目录)
        - '/' 或 '\\' (绝对路径)
        
        Args:
            topic: 待检查的主题字符串
        
        Raises:
            ValueError: 当检测到路径遍历模式时抛出异常
        """
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in topic:
                raise ValueError(f"Path traversal detected: '{pattern}'")
