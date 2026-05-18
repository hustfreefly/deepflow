"""
Spec Pro LLM Extractor - 需求分析引擎 V0.1

调用 `openclaw agent --agent product` 进行需求文档理解。

职责:
1. 接收原始文档文本
2. 调用 OpenClaw Agent 提取结构化需求
3. 返回 topic/constraints/stakeholders/solution_type

红线:
- 不在 exec 环境调用 openclaw 模块
- 通过 CLI 调用 OpenClaw（subprocess，非 import）
- 提取失败时降级返回空结果，不阻断流程
"""
import json
import re
import subprocess
from typing import Optional, Dict, Any


# ── 系统 Prompt ──

SYSTEM_INSTRUCTION = """你是一个需求分析专家。请从用户提供的文档中提取结构化信息。

输出要求：
1. topic: 设计主题，5-200字的一句话描述核心目标
2. solution_type: 方案类型，三选一：architecture(架构设计) / business(商业方案) / technical(技术方案)
3. constraints: 约束条件列表，最多5条（如预算、时间、技术限制）
4. stakeholders: 利益相关者列表，最多10个（如角色、部门、外部合作方）

严格以 JSON 格式输出，不要额外解释。JSON 格式如下：
{
  "topic": "...",
  "solution_type": "architecture" 或 "business" 或 "technical" 或 null,
  "constraints": ["约束1", "约束2"],
  "stakeholders": ["角色1", "角色2"]
}

如果文档信息不足以确定某个字段，设为 null 或空数组。"""


class SpecExtractor:
    """
    需求分析提取器。

    通过 `openclaw agent --agent product` CLI 调用产品经 Agent 进行提取。
    失败时降级返回空结果，不阻断流程。
    """

    def __init__(self, timeout: int = 60):
        """
        初始化提取器。

        Args:
            timeout: CLI 调用超时（秒）
        """
        self.timeout = timeout

    def extract_requirements(
        self,
        text: str,
        solution_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        从文档文本中提取结构化需求。

        Args:
            text: 文档原始文本内容
            solution_type: 用户预选方案类型（可为 None）

        Returns:
            dict: {topic, solution_type, constraints, stakeholders, extracted_text, confidence}
        """
        if not text or not text.strip():
            return self._empty_result(text)

        # 截断过长文本
        truncated_text = text[:30000]

        user_prompt = (
            f"{SYSTEM_INSTRUCTION}\n\n"
            f"请从以下文档中提取结构化需求信息：\n\n"
            f"---\n{truncated_text}\n---"
        )
        if solution_type:
            user_prompt += (
                f"\n\n用户预选方案类型: {solution_type}，请优先考虑此类型。"
            )

        try:
            result = self._call_agent(user_prompt)
            return result
        except Exception as e:
            print(f"[SpecExtractor] Agent extraction failed: {e}")
            return self._empty_result(text, error=str(e))

    def _call_agent(self, prompt: str) -> Dict[str, Any]:
        """
        调用 openclaw agent CLI 进行 LLM 提取。

        Args:
            prompt: 完整 prompt

        Returns:
            结构化提取结果

        Raises:
            subprocess.TimeoutExpired: 超时
            subprocess.CalledProcessError: 命令失败
            ValueError: LLM 返回无法解析
        """
        result = subprocess.run(
            [
                "openclaw", "agent",
                "--agent", "product",
                "--message", prompt,
            ],
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise RuntimeError(f"openclaw agent failed (rc={result.returncode}): {stderr[:200]}")

        stdout = result.stdout.strip()
        return self._parse_agent_response(stdout)

    def _parse_agent_response(self, content: str) -> Dict[str, Any]:
        """
        解析 Agent 返回的响应，提取 JSON。

        Args:
            content: Agent 返回的文本

        Returns:
            结构化提取结果

        Raises:
            ValueError: 无法解析 JSON
        """
        # 尝试从响应中提取 JSON 块
        json_str = self._extract_json(content)
        if not json_str:
            raise ValueError(f"Could not extract JSON from agent response: {content[:200]}")

        parsed = json.loads(json_str)

        # 构建标准返回格式
        return {
            "topic": parsed.get("topic", ""),
            "solution_type": parsed.get("solution_type"),
            "constraints": parsed.get("constraints", []) or [],
            "stakeholders": parsed.get("stakeholders", []) or [],
            "confidence": 0.8,
            "extracted_text": "",
        }

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """
        从文本中提取 JSON 字符串。

        支持:
        - 纯 JSON
        - ```json ... ``` 包裹
        - 文本中的 JSON 对象

        Args:
            text: 输入文本

        Returns:
            JSON 字符串，或 None
        """
        # 尝试 1: 直接解析
        text = text.strip()
        if text.startswith("{"):
            return text

        # 尝试 2: 提取 ```json ... ``` 块
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 尝试 3: 找到第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start:end + 1]

        return None

    @staticmethod
    def _empty_result(
        text: str, error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        构建空结果（降级方案）。

        Args:
            text: 原始文本
            error: 可选错误信息

        Returns:
            空结构化结果
        """
        return {
            "topic": "",
            "solution_type": None,
            "constraints": [],
            "stakeholders": [],
            "confidence": 0.0,
            "extracted_text": text[:5000],
            "error": error,
        }
