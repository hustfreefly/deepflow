"""
AgentCaller - LLM Agent 调用封装

集成 OpenClaw sessions_spawn 进行 Agent 调用。
提供两种模式:
  1. MockAgentCaller - 本地 mock (无外部依赖, 用于测试)
  2. OpenClawAgentCaller - 通过 OpenClaw sessions_spawn 调用真实 LLM

使用示例:
    caller = MockAgentCaller()           # 测试模式
    result = caller.call_agent("p1_parser", {"task": "..."})
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("ship_pro.v5.agent_caller")


# ────────────────────────────────
# 基础抽象
# ────────────────────────────────

class AgentCaller:
    """Agent 调用基类"""

    def call_agent(
        self, agent_name: str, input_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def call_agents_parallel(
        self, tasks: List[Tuple[str, Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """默认串行 fallback; 子类可覆盖为并行实现"""
        results = {}
        for name, data in tasks:
            results[name] = self.call_agent(name, data)
        return results


# ────────────────────────────────
# Mock 实现 (零依赖, 本地测试用)
# ────────────────────────────────

class MockAgentCaller(AgentCaller):
    """Mock Agent Caller - 返回结构化假数据, 用于本地测试和 CI"""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.call_count = 0

    def call_agent(
        self, agent_name: str, input_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        self.call_count += 1
        logger.debug("[Mock] %s call #%d", agent_name, self.call_count)

        # 根据 agent_name 返回结构化 mock 数据
        return self._generate_mock(agent_name, input_data)

    def _generate_mock(
        self, agent_name: str, input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """根据 agent 类型生成合理的 mock 输出"""

        if "parser" in agent_name:
            return {
                "entities": ["User", "Order", "Product"],
                "relations": [{"from": "User", "to": "Order", "type": "1:N"}],
                "constraints": ["性能 < 200ms", "可用性 99.9%"],
            }

        if "explorer" in agent_name:
            return {
                "findings": [
                    {"area": "domain", "insight": "需要支持秒杀场景"},
                    {"area": "tech", "insight": "推荐使用消息队列"},
                ],
                "risks": ["高并发下单", "库存超卖"],
            }

        if "architect" in agent_name:
            if "step1" in agent_name:
                return {
                    "work_packages": [
                        {
                            "id": "WP-001",
                            "name": "订单核心服务",
                            "scope": "订单创建/查询/状态流转",
                        },
                        {
                            "id": "WP-002",
                            "name": "支付集成",
                            "scope": "支付渠道对接/回调处理",
                        },
                    ],
                    "architecture_pattern": "微服务",
                }
            return {
                "rationale": "选择微服务架构以支持独立扩展和部署",
                "tradeoffs": ["运维复杂度增加", "服务间调用延迟"],
            }

        if "critic" in agent_name or "judge" in agent_name:
            return {
                "verdict": "pass" if self.call_count % 3 != 0 else "fail",
                "issues": (
                    []
                    if self.call_count % 3 != 0
                    else [
                        {
                            "severity": "warning",
                            "message": "Mock: 发现潜在问题",
                        }
                    ]
                ),
                "score": 85,
            }

        if "consolidator" in agent_name:
            if "p1" in agent_name:
                return {
                    "blueprint": {
                        "id": f"bp-{self.call_count:04d}",
                        "work_packages": input_data.get("blueprint", {}).get(
                            "work_packages", []
                        ),
                        "rationale": "consolidated",
                    }
                }
            return {
                "ship_package": {
                    "id": f"sp-{self.call_count:04d}",
                    "acceptance_criteria": input_data.get("package", {}).get(
                        "acceptance_criteria", []
                    ),
                    "status": "ready",
                }
            }

        if "fix" in agent_name:
            data = input_data.get("data", {})
            issues = input_data.get("issues", [])
            return {
                **data,
                "_fixed_issues": [i.get("rule", "unknown") for i in issues],
                "_fix_version": self.call_count,
            }

        if "ac_writer" in agent_name:
            return {
                "acceptance_criteria": [
                    {
                        "id": "AC-001",
                        "wp_id": "WP-001",
                        "given": "用户已登录",
                        "when": "提交订单",
                        "then": "订单状态为待支付",
                    }
                ],
                "work_packages": [
                    {
                        "id": "WP-001",
                        "name": "订单核心服务",
                    }
                ],
            }

        if "consistency" in agent_name:
            return {
                "verdict": "consistent",
                "conflicts_found": 0,
            }

        # 通用 fallback
        return {
            "agent": agent_name,
            "status": "mock_ok",
            "input_keys": list(input_data.keys()),
            "timestamp": time.time(),
        }


# ────────────────────────────────
# OpenClaw 集成实现 (真实 LLM 调用)
# ────────────────────────────────

class OpenClawAgentCaller(AgentCaller):
    """
    通过 OpenClaw sessions_spawn 调用真实 LLM Agent。

    环境要求:
      - OpenClaw Gateway 正在运行
      - 可用模型: bailian/qwen3.7-plus 或 gpt-4

    配置:
      - SHIP_PRO_MODEL: 指定模型 (默认 bailian/qwen3.7-plus)
      - SHIP_PRO_MAX_TOKENS: 最大 token 数 (默认 8000)
    """

    def __init__(
        self,
        prompts_dir: Path | None = None,
        model: str | None = None,
        max_tokens: int = 8000,
        temperature: float = 0.3,
        timeout: int = 300,
    ):
        self.prompts_dir = prompts_dir or Path(__file__).parent.parent / "prompts"
        self.model = model or os.environ.get(
            "SHIP_PRO_MODEL", "bailian/qwen3.7-plus"
        )
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.executor = ThreadPoolExecutor(max_workers=4)

    # ────────────────────────────────
    # Prompt 加载
    # ────────────────────────────────

    def _load_prompt(self, agent_name: str) -> str:
        """从 core.prompt_registry 加载对应 Agent 的 system prompt"""
        from core.prompt_registry import read_prompt
        try:
            return read_prompt(f"ship_pro/{agent_name}")
        except (KeyError, FileNotFoundError):
            # fallback: 查找通用 prompt
            try:
                return read_prompt("ship_pro/generic_agent")
            except (KeyError, FileNotFoundError):
                return f"# Agent: {agent_name}\n请根据输入数据完成分析并返回 JSON。"

    # ────────────────────────────────
    # 单次调用
    # ────────────────────────────────

    def call_agent(
        self, agent_name: str, input_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """同步调用单个 LLM Agent"""
        prompt = self._load_prompt(agent_name)
        temperature = kwargs.get("temperature", self.temperature)
        max_tokens = kwargs.get("max_tokens", self.max_tokens)

        # 构建完整请求
        full_prompt = self._build_prompt(prompt, input_data)

        # 调用 OpenClaw (通过 subprocess 调用 openclaw CLI)
        response_text = self._invoke_openclaw(
            full_prompt, temperature=temperature, max_tokens=max_tokens
        )

        # 解析 JSON 输出
        return self._parse_json_response(response_text, agent_name)

    def _build_prompt(
        self, system_prompt: str, input_data: Dict[str, Any]
    ) -> str:
        """组合 system prompt + 结构化输入"""
        input_json = json.dumps(input_data, ensure_ascii=False, indent=2)
        return f"""{system_prompt}

## 输入数据
```json
{input_json}
```

## 要求
- 严格返回合法 JSON, 不要包含 markdown 代码块标记
- 不要添加解释性文字
- 确保 JSON 可解析
"""

    def _invoke_openclaw(
        self, prompt: str, temperature: float, max_tokens: int
    ) -> str:
        """
        通过 OpenClaw CLI 调用 LLM。

        命令格式:
            openclaw message send --model <model> --prompt <prompt> --raw
        """
        # 将 prompt 写入临时文件 (避免命令行过长)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(prompt)
            prompt_file = f.name

        try:
            # 构建 CLI 命令
            cmd = [
                "openclaw",
                "message",
                "send",
                "--model",
                self.model,
                "--prompt-file",
                prompt_file,
                "--raw",
                "--max-tokens",
                str(max_tokens),
                "--temperature",
                str(temperature),
            ]

            logger.debug("[OpenClaw] cmd: %s", " ".join(cmd))

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
            )

            if result.returncode != 0:
                logger.error(
                    "[OpenClaw] stderr: %s", result.stderr[:500]
                )
                raise RuntimeError(
                    f"OpenClaw 调用失败 (rc={result.returncode}): {result.stderr[:200]}"
                )

            return result.stdout

        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"OpenClaw 调用超时 ({self.timeout}s)"
            )
        except FileNotFoundError:
            raise RuntimeError(
                "OpenClaw CLI 未找到。请确认 openclaw 已安装并加入 PATH。"
            )
        finally:
            try:
                os.unlink(prompt_file)
            except OSError:
                pass

    def _parse_json_response(
        self, text: str, agent_name: str
    ) -> Dict[str, Any]:
        """从 LLM 输出中提取并解析 JSON"""
        text = text.strip()

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown 代码块中提取
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end != -1:
                try:
                    return json.loads(text[start:end].strip())
                except json.JSONDecodeError:
                    pass

        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end != -1:
                try:
                    return json.loads(text[start:end].strip())
                except json.JSONDecodeError:
                    pass

        # 尝试查找第一个 { 和最后一个 }
        try:
            start = text.index("{")
            end = text.rindex("}")
            return json.loads(text[start : end + 1])
        except (ValueError, json.JSONDecodeError):
            pass

        logger.error(
            "[OpenClaw] 无法解析 %s 的 JSON 输出:\n%s", agent_name, text[:500]
        )
        raise ValueError(
            f"Agent {agent_name} 返回非 JSON 输出: {text[:200]}"
        )

    # ────────────────────────────────
    # 并行调用
    # ────────────────────────────────

    def call_agents_parallel(
        self, tasks: List[Tuple[str, Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """使用线程池并行调用多个 Agent"""
        logger.info("[OpenClaw] 并行调用 %d agents", len(tasks))
        results: Dict[str, Any] = {}
        futures = {
            self.executor.submit(self.call_agent, name, data): name
            for name, data in tasks
        }

        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
                logger.debug("[OpenClaw] %s 完成", name)
            except Exception as exc:
                logger.error("[OpenClaw] %s 失败: %s", name, exc)
                raise

        return results

    def shutdown(self):
        """关闭线程池"""
        self.executor.shutdown(wait=True)


# ────────────────────────────────
# 便捷工厂
# ────────────────────────────────

def create_caller(
    mode: str = "mock",
    prompts_dir: Path | None = None,
    **kwargs,
) -> AgentCaller:
    """
    创建 AgentCaller 实例

    Args:
        mode: "mock" | "openclaw"
        prompts_dir: prompt 文件目录
        **kwargs: 传递给具体 caller 的参数
    """
    if mode == "mock":
        # MockAgentCaller 只接受 seed
        mock_kwargs = {k: v for k, v in kwargs.items() if k == "seed"}
        return MockAgentCaller(**mock_kwargs)
    elif mode == "openclaw":
        return OpenClawAgentCaller(prompts_dir=prompts_dir, **kwargs)
    else:
        raise ValueError(f"未知 caller 模式: {mode}")


# ────────────────────────────────
# 内建测试
# ────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("=" * 60)
    print("🧪 AgentCaller 测试")
    print("=" * 60)

    # 测试 MockAgentCaller
    print("\n1️⃣  MockAgentCaller 测试")
    mock = MockAgentCaller()

    test_agents = [
        ("p1_parser", {"task": "设计电商系统"}),
        ("p1_explorer", {"parsed": {"entities": ["User"]}}),
        ("p1_architect_step1", {"findings": []}),
        ("p1_architect_step2", {"wp_list": []}),
        ("p1_coverage_critic", {"blueprint": {}}),
        ("p1_consolidator", {"blueprint": {}, "critics": {}}),
        ("p2_ac_writer", {"blueprint": {}}),
    ]

    for name, data in test_agents:
        result = mock.call_agent(name, data)
        print(f"  ✅ {name:25s} → keys={list(result.keys())}")

    # 测试并行调用
    print("\n2️⃣  并行调用测试")
    parallel_tasks = [
        ("p1_coverage_critic", {"blueprint": {}}),
        ("p1_granularity_critic", {"blueprint": {}}),
        ("p1_feasibility_critic", {"blueprint": {}}),
    ]
    parallel_results = mock.call_agents_parallel(parallel_tasks)
    for name, result in parallel_results.items():
        print(f"  ✅ {name:25s} → verdict={result.get('verdict', 'N/A')}")

    # 测试 JSON 解析
    print("\n3️⃣  JSON 解析测试")
    openclaw = OpenClawAgentCaller.__new__(OpenClawAgentCaller)
    test_cases = [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"b": 2}\n```', {"b": 2}),
        ('some text\n{"c": 3}\nmore text', {"c": 3}),
    ]
    for raw, expected in test_cases:
        parsed = openclaw._parse_json_response(raw, "test")
        assert parsed == expected, f"解析失败: {raw}"
        print(f"  ✅ 解析成功: {raw[:40]}")

    print("\n" + "=" * 60)
    print("🎉 所有测试通过!")
    print("=" * 60)
