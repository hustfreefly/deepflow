"""
LLM Caller - 统一 LLM 调用接口

职责：封装 LLM 调用逻辑，供 llm_gate_checks 使用。
设计原则：
- 可测试：支持 mock
- 可配置：支持不同模型
- 可观测：记录调用日志
"""

import json
import os
import urllib.request
import urllib.error
from typing import Optional
from pathlib import Path


class LLMCaller:
    """LLM 调用器"""

    def __init__(
        self,
        model: str = "qwen3.7-max",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 60,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ):
        self.model = model
        # 尝试多种 API key 来源
        self.api_key = (
            api_key 
            or os.environ.get("DASHSCOPE_API_KEY", "")
            or os.environ.get("KIMI_CODE_API_KEY", "")
            or os.environ.get("BAILIAN_API_KEY", "")
        )
        # 根据 API key 来源自动选择 base_url
        if base_url:
            self.base_url = base_url
        elif "sk-kimi" in self.api_key:
            self.base_url = "https://api.moonshot.cn/v1"
            self.model = "moonshot-v1-32k"  # Kimi 模型
        else:
            self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._has_key = bool(self.api_key)

    def call(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        调用 LLM 并返回输出文本。

        Args:
            prompt: 用户 prompt
            system_prompt: 系统 prompt（可选）

        Returns:
            LLM 输出文本
        """
        if not self._has_key:
            return json.dumps({
                "decision": "PASS",
                "issues": [],
                "reasoning": "无 API key，LLM 语义检查降级为 PASS"
            }, ensure_ascii=False)

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }

            url = f"{self.base_url}/chat/completions"
            data = json.dumps(payload).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
                result = json.loads(body)

            return result["choices"][0]["message"]["content"]

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
            return json.dumps({
                "decision": "FAIL",
                "issues": [{
                    "type": "llm_call_error",
                    "severity": "BLOCKER",
                    "description": f"LLM HTTP 错误 {e.code}: {error_body[:200]}",
                    "affected_modules": [],
                    "suggestion": "检查 API key 和模型名称"
                }],
                "reasoning": f"LLM HTTP 错误: {e.code}"
            }, ensure_ascii=False)

        except Exception as e:
            # 降级：返回错误 JSON
            return json.dumps({
                "decision": "FAIL",
                "issues": [{
                    "type": "llm_call_error",
                    "severity": "BLOCKER",
                    "description": f"LLM 调用失败: {str(e)}",
                    "affected_modules": [],
                    "suggestion": "检查 LLM 配置和网络连接"
                }],
                "reasoning": f"LLM 调用异常: {str(e)}"
            }, ensure_ascii=False)


def create_llm_caller(model: str = "qwen3.7-max") -> LLMCaller:
    """工厂函数：创建 LLM 调用器"""
    return LLMCaller(model=model)


# ---------------------------------------------------------------------------
# 注入机制
# ---------------------------------------------------------------------------

_default_caller: Optional[LLMCaller] = None


def set_default_caller(caller: LLMCaller):
    """设置默认 LLM 调用器（依赖注入）"""
    global _default_caller
    _default_caller = caller


def get_default_caller() -> LLMCaller:
    """获取默认 LLM 调用器"""
    global _default_caller
    if _default_caller is None:
        _default_caller = create_llm_caller()
    return _default_caller
