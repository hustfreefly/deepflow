"""
UC Coverage Verifier — AI Native 版本

核心理念：UC 覆盖验证是语义理解任务，只能由 LLM 做判断。

架构（能力正交）：
- 代码（确定性工作）: 提取 UC 定义、加载方案文档、格式化 Judge 输入、解析 Judge 输出
- LLM（语义判断）:   判断方案是否实质覆盖每个 UC 的核心要求
- 合并（决策）:       汇总判定结果

禁止事项（4.1 铁律）：
- ❌ 用 re.match 匹配 UC ID 来判断覆盖（ID 是元数据，不是语义内容）
- ❌ 用关键词计数来判断覆盖（计数 ≠ 理解）
- ❌ 用 if/elif 分支来分类覆盖（硬编码 ≠ 语义判断）

版本历史：
- （已废弃）: 用 regex 匹配 UC ID → 8% 覆盖率 → 违反 4.1
- （已废弃）: 用关键词提取匹配 → ~30% → 仍然是硬编码思维
- （当前）: LLM-as-Judge 语义判断 → 代码只做 I/O
"""

import json
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class UCCoverageResult:
    """UC 覆盖率验证结果"""
    total_uc: int
    coverage_details: list[dict] = field(default_factory=list)
    overall_verdict: str = "UNKNOWN"  # PASS / CONDITIONAL / FAIL
    coverage_rate: float = 0.0
    verification_method: str = "llm_as_judge"
    
    @property
    def pass_count(self) -> int:
        return sum(1 for d in self.coverage_details if d.get("verdict") == "PASS")
    
    @property
    def conditional_count(self) -> int:
        return sum(1 for d in self.coverage_details if d.get("verdict") == "CONDITIONAL")
    
    @property
    def fail_count(self) -> int:
        return sum(1 for d in self.coverage_details if d.get("verdict") == "FAIL")
    
    def to_dict(self) -> dict:
        return {
            "total_uc": self.total_uc,
            "pass": self.pass_count,
            "conditional": self.conditional_count,
            "fail": self.fail_count,
            "overall_verdict": self.overall_verdict,
            "coverage_rate": self.coverage_rate,
            "verification_method": self.verification_method,
            "details": self.coverage_details,
        }


class UCCoverageVerifier:
    """
    UC 覆盖率验证器
    
    职责分工（能力正交）：
    
    代码（本类）:
      1. 从 planning_convergence.json 提取 UC 定义
      2. 加载 solution_document
      3. 格式化 LLM Judge 的输入材料
      4. 解析 Judge 输出，生成 UCCoverageResult
    
    LLM Judge（由 spawn_fn 注入）:
      1. 读取 UC 定义 + 方案文档
      2. 对每个 UC 做语义判断：方案是否实质覆盖
      3. 输出: {uc_id, verdict, evidence, gap?}
    
    注意：代码不做任何覆盖判断。所有"是否覆盖"的决策由 LLM 做出。
    """
    
    # LLM Judge prompt 模板
    JUDGE_PROMPT_TEMPLATE = """你是一名独立的 UC 覆盖验证专家。

## 你的任务
判断一份架构方案是否实质覆盖了每个 UC（Unified Constraint）的核心要求。

## 判断标准
- ✅ PASS: 方案在架构层面明确覆盖了该 UC 的核心要求
- ⚠️ CONDITIONAL: 方案提到了相关概念但实现细节不够明确（可接受，留给下游阶段细化）
- ❌ FAIL: 方案完全没有涉及该 UC 的核心要求

## 重要原则
1. 不要求 UC ID（如 UC-001）显式出现在方案中 — ID 是元数据，不是语义内容
2. 不要求实现细节完备 — 架构方案允许将细节留给下游实现阶段
3. 关注核心要求是否被覆盖，不是逐条检查每个子项
4. 如果 UC 的核心概念在方案中有对应的架构设计或组件，即为 PASS

## 输入材料

### UC 定义（共 {total_uc} 个）
{uc_definitions}

### 架构方案
{solution_document}

## 输出格式（JSON）
请对每个 UC 输出一条判定：
```json
{{
  "results": [
    {{"uc_id": "UC-XXX", "verdict": "PASS|CONDITIONAL|FAIL", "evidence": "方案中支持此判定的关键内容", "gap": "如果是 CONDITIONAL，说明缺失什么"}}
  ]
}}
```
"""

    def __init__(self, blackboard_path: Path, spawn_fn=None):
        """
        Args:
            blackboard_path: Blackboard 目录路径
            spawn_fn: 可选的 spawn 函数（用于 LLM Judge）
                      如果不提供，verify() 只准备 Judge 材料，不做判断
        """
        self.blackboard_path = Path(blackboard_path)
        self.spawn_fn = spawn_fn
    
    def prepare_judge_input(self) -> dict:
        """
        代码做的确定性工作：提取 UC 定义 + 加载方案 + 格式化
        
        Returns:
            {uc_definitions: list, solution_document: str, judge_prompt: str}
        """
        uc_definitions = self._extract_uc_definitions()
        solution_text = self._load_solution_document()
        
        # 格式化 UC 定义供 LLM 阅读
        uc_text = ""
        for uc in uc_definitions:
            uc_text += f"\n### {uc['uc_id']} [{uc['priority']}]\n{uc['description'][:500]}\n"
        
        judge_prompt = self.JUDGE_PROMPT_TEMPLATE.format(
            total_uc=len(uc_definitions),
            uc_definitions=uc_text,
            solution_document=solution_text[:8000]
        )
        
        return {
            "uc_definitions": uc_definitions,
            "solution_document": solution_text,
            "judge_prompt": judge_prompt,
        }
    
    def verify(self, judge_output: Optional[dict] = None) -> UCCoverageResult:
        """
        执行 UC 覆盖率验证
        
        两种模式：
        1. 传入 judge_output（LLM 已判断）→ 代码解析并生成结果
        2. 不传 judge_output → 只准备输入材料，返回空结果
        
        Args:
            judge_output: LLM Judge 的输出（如果有）
        
        Returns:
            UCCoverageResult
        """
        if judge_output is None:
            # 没有 Judge 输出，只准备材料
            logger.info("No judge_output provided, preparing judge input only")
            return UCCoverageResult(total_uc=len(self._extract_uc_definitions()))
        
        # 代码做的确定性工作：解析 Judge 输出
        results = judge_output.get("results", [])
        
        pass_count = sum(1 for r in results if r.get("verdict") == "PASS")
        total = len(results)
        rate = pass_count / total if total > 0 else 0.0
        
        if rate >= 0.8:
            verdict = "PASS"
        elif rate >= 0.6:
            verdict = "CONDITIONAL"
        else:
            verdict = "FAIL"
        
        return UCCoverageResult(
            total_uc=total,
            coverage_details=results,
            overall_verdict=verdict,
            coverage_rate=rate,
            verification_method="llm_as_judge"
        )
    
    def _extract_uc_definitions(self) -> list[dict]:
        """
        代码做的确定性工作：从 planning_convergence 提取 UC 定义
        """
        convergence_file = self.blackboard_path / "stages" / "planning_convergence.json"
        if not convergence_file.exists():
            return []
        
        try:
            data = json.loads(convergence_file.read_text())
            if isinstance(data, str):
                data = json.loads(data)
            
            constraints = data.get("unified_constraints", [])
            return [
                {
                    "uc_id": c["constraint_id"],
                    "description": c.get("description", ""),
                    "priority": c.get("priority", "SHOULD"),
                }
                for c in constraints
                if isinstance(c, dict) and c.get("constraint_id")
            ]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to extract UC definitions: {e}")
            return []
    
    def _load_solution_document(self) -> str:
        """代码做的确定性工作：加载方案文档"""
        doc_file = self.blackboard_path / "stages" / "solution_document.json"
        if doc_file.exists():
            try:
                data = json.loads(doc_file.read_text())
                if isinstance(data, str):
                    return data
                if isinstance(data, dict):
                    return data.get("content", "") or json.dumps(data, ensure_ascii=False)
            except json.JSONDecodeError:
                pass
        return ""


__all__ = ["UCCoverageVerifier", "UCCoverageResult"]
