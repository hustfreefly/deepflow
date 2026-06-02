#!/usr/bin/env python3
"""
Solution Pro E2E Golden Case 验证脚本

用法:
    cd ~/.openclaw/workspace/.deepflow
    python3 tests/golden/verify_golden_case.py <session_id>

退出码:
    0 = PASS（全部验证通过）
    1 = PARTIAL（部分通过，≥70%）
    2 = FAIL（低于70%或关键断言失败）
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

# 确保 deepflow 在 path 中
DEEPFLOW_ROOT = Path(__file__).resolve().parent.parent.parent  # .deepflow/
sys.path.insert(0, str(DEEPFLOW_ROOT))

from domains.solution.blackboard import STAGE_PATH_REGISTRY


class GoldenCaseVerifier:
    """Golden Case E2E 验证器"""

    def __init__(self, session_id: str, golden_case_path: str = None):
        self.session_id = session_id
        self.base_path = DEEPFLOW_ROOT / "blackboard" / session_id
        self.results = []
        self.passed = 0
        self.failed = 0
        self.warnings = 0

        # 加载 golden case 定义
        if golden_case_path is None:
            golden_case_path = Path(__file__).parent / "golden_case_001.json"
        with open(golden_case_path, "r", encoding="utf-8") as f:
            self.golden = json.load(f)

    def _check(self, name: str, condition: bool, detail: str = "", critical: bool = False):
        """记录一个检查项"""
        status = "✅ PASS" if condition else ("🔴 FAIL" if critical else "🟡 WARN")
        self.results.append({
            "name": name,
            "status": status,
            "detail": detail,
            "critical": critical,
            "passed": condition,
        })
        if condition:
            self.passed += 1
        elif critical:
            self.failed += 1
        else:
            self.warnings += 1

    def _read_json(self, rel_path: str) -> dict | None:
        """读取 blackboard 下的 JSON 文件"""
        path = self.base_path / rel_path
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return None
        return None

    def _file_exists(self, rel_path: str) -> bool:
        return (self.base_path / rel_path).exists()

    # =========================================================================
    # 验证阶段
    # =========================================================================

    def verify_infrastructure(self):
        """1. 基础设施验证"""
        print("\n" + "=" * 60)
        print("📦 Phase 1: 基础设施验证")
        print("=" * 60)

        self._check(
            "blackboard目录存在",
            self.base_path.exists(),
            f"路径: {self.base_path}",
            critical=True,
        )

        self._check(
            "execution_plan.json存在",
            self._file_exists("execution_plan.json"),
            critical=True,
        )

        self._check(
            "tasks.json存在",
            self._file_exists("tasks.json"),
            critical=True,
        )

        self._check(
            "data/frozen_spec.json存在",
            self._file_exists("data/frozen_spec.json"),
            critical=True,
        )

    def verify_execution_plan(self):
        """2. 执行计划验证"""
        print("\n" + "=" * 60)
        print("📋 Phase 2: 执行计划验证")
        print("=" * 60)

        plan = self._read_json("execution_plan.json")
        if plan is None:
            self._check("execution_plan可读", False, "文件不存在或JSON格式错误", critical=True)
            return

        self._check("execution_plan可读", True, critical=True)

        phases = plan.get("phases", [])
        self._check(
            "固定10阶段",
            len(phases) == 10,
            f"实际阶段数: {len(phases)}",
            critical=True,
        )

        # 检查关键阶段存在
        stage_names = [p.get("stage") for p in phases]
        required_stages = [
            "data_collection", "planning", "reviewers", "research",
            "consolidator", "audit", "fix", "fixer_expert",
            "harness_final", "summarizer"
        ]
        for stage in required_stages:
            self._check(
                f"阶段 '{stage}' 存在",
                stage in stage_names,
                critical=True,
            )

        # 检查并行阶段
        reviewers_phase = next((p for p in phases if p.get("stage") == "reviewers"), None)
        research_phase = next((p for p in phases if p.get("stage") == "research"), None)

        if reviewers_phase:
            self._check(
                "reviewers并行执行",
                reviewers_phase.get("parallel") is True,
            )
            self._check(
                "reviewers包含3个worker",
                len(reviewers_phase.get("workers", [])) == 3,
                f"实际: {reviewers_phase.get('workers', [])}",
            )

        if research_phase:
            self._check(
                "research并行执行",
                research_phase.get("parallel") is True,
            )
            self._check(
                "research包含3个worker",
                len(research_phase.get("workers", [])) == 3,
                f"实际: {research_phase.get('workers', [])}",
            )

    def verify_frozen_spec(self):
        """3. Frozen Spec 验证"""
        print("\n" + "=" * 60)
        print("🔒 Phase 3: Frozen Spec 验证")
        print("=" * 60)

        spec = self._read_json("data/frozen_spec.json")
        if spec is None:
            self._check("frozen_spec可读", False, critical=True)
            return

        self._check("frozen_spec可读", True, critical=True)

        requirements = spec.get("requirements", [])
        expectations = self.golden["frozen_spec_expectations"]

        self._check(
            f"需求数量≥{expectations['min_requirements']}",
            len(requirements) >= expectations["min_requirements"],
            f"实际: {len(requirements)}条",
        )

        # 检查 P0 需求存在
        p0_reqs = [r for r in requirements if r.get("priority") == "P0"]
        self._check(
            "存在P0需求",
            len(p0_reqs) > 0,
            f"P0需求数: {len(p0_reqs)}",
            critical=True,
        )

        # 检查需求类别覆盖
        categories = set(r.get("category") for r in requirements)
        for cat in expectations["required_categories"]:
            self._check(f"包含类别 '{cat}'", cat in categories)

        # 检查 topic 写入
        self._check(
            "topic字段非空",
            bool(spec.get("topic", "").strip()),
            f"topic: {spec.get('topic', '')[:50]}...",
        )

        # 检查 REQ-ID 格式
        for req in requirements:
            rid = req.get("id", "")
            valid = rid.startswith("REQ-") and rid[4:].isdigit()
            if not valid:
                self._check(f"REQ-ID格式正确 ({rid})", False, f"非法格式: {rid}")
                break
        else:
            self._check("所有REQ-ID格式正确", True)

    def verify_stages(self):
        """4. 各阶段输出验证"""
        print("\n" + "=" * 60)
        print("🔍 Phase 4: 各阶段输出验证")
        print("=" * 60)

        expectations = self.golden["stage_expectations"]

        for stage_name, stage_exp in expectations.items():
            if stage_name in ("reviewers", "research"):
                # 并行阶段
                self._verify_parallel_stage(stage_name, stage_exp)
            else:
                # 串行阶段
                self._verify_serial_stage(stage_name, stage_exp)

    def _verify_serial_stage(self, stage_name: str, exp: dict):
        output_path = exp["output_path"]
        exists = self._file_exists(output_path)

        self._check(
            f"[{stage_name}] 输出文件存在",
            exists,
            f"路径: {output_path}",
        )

        if exists:
            data = self._read_json(output_path)
            if data is None:
                self._check(f"[{stage_name}] JSON可读", False, "JSON解析失败")
                return

            self._check(f"[{stage_name}] JSON可读", True)

            # 检查必需字段
            for field in exp.get("must_contain_fields", []):
                self._check(
                    f"[{stage_name}] 包含字段 '{field}'",
                    field in data,
                )

            # 检查别名必需字段（字段 A 不存在时，别名 B 可代替）
            for primary, aliases in exp.get("alias_fields", {}).items():
                if primary in data:
                    self._check(
                        f"[{stage_name}] 包含字段 '{primary}'",
                        True,
                    )
                else:
                    found = [a for a in aliases if a in data]
                    self._check(
                        f"[{stage_name}] 包含 '{primary}' 或别名 {aliases}",
                        bool(found),
                        f"找到: {found}" if found else "缺失",
                    )

            # 检查 status（仅当 stage_exp 定义了 status_must_be 时）
            if "status_must_be" in exp:
                self._check(
                    f"[{stage_name}] status={exp['status_must_be']}",
                    data.get("status") == exp["status_must_be"],
                    f"实际: {data.get('status')}",
                )

    def _verify_parallel_stage(self, stage_name: str, exp: dict):
        workers = exp.get("workers", {})
        min_success = exp.get("min_success_workers", 2)
        success_count = 0

        for worker_id, worker_exp in workers.items():
            output_path = worker_exp["output_path"]
            exists = self._file_exists(output_path)

            self._check(
                f"[{stage_name}.{worker_id}] 输出文件存在",
                exists,
                f"路径: {output_path}",
            )

            if exists:
                data = self._read_json(output_path)
                if data:
                    success_count += 1
                    for field in worker_exp.get("must_contain_fields", []):
                        self._check(
                            f"[{stage_name}.{worker_id}] 包含字段 '{field}'",
                            field in data,
                        )
                    # 别名必需字段
                    for primary, aliases in worker_exp.get("alias_fields", {}).items():
                        if primary in data:
                            self._check(
                                f"[{stage_name}.{worker_id}] 包含字段 '{primary}'",
                                True,
                            )
                        else:
                            found = [a for a in aliases if a in data]
                            self._check(
                                f"[{stage_name}.{worker_id}] 包含 '{primary}' 或别名 {aliases}",
                                bool(found),
                                f"找到: {found}" if found else "缺失",
                            )

        self._check(
            f"[{stage_name}] 至少{min_success}个worker成功",
            success_count >= min_success,
            f"成功: {success_count}/{len(workers)}",
        )

    def verify_global_artifacts(self):
        """5. 全局产物验证"""
        print("\n" + "=" * 60)
        print("🏗️ Phase 5: 全局产物验证")
        print("=" * 60)

        g = self.golden["global_expectations"]

        if g["control_contract_must_exist"]:
            self._check(
                "control_contract.json存在",
                self._file_exists("control_contract.json"),
                critical=True,
            )

        if g["traceability_matrix_must_exist"]:
            self._check(
                "requirements_traceability_matrix.json存在",
                self._file_exists("requirements_traceability_matrix.json"),
            )

        if g["completed_file_must_exist"]:
            self._check(
                ".completed文件存在",
                self._file_exists(".completed"),
                critical=True,
            )
            completed = self._read_json(".completed")
            if completed:
                allowed = g["completed_status_must_be"]
                self._check(
                    f".completed status ∈ {allowed}",
                    completed.get("status") in allowed,
                    f"实际: {completed.get('status')}",
                    critical=True,
                )

                # 完成率
                min_rate = g["min_stage_completion_rate"]
                rate = completed.get("completion_rate", 0)
                if rate == 0 and completed.get("stages_completed"):
                    rate = completed["stages_completed"] / 10
                self._check(
                    f"完成率≥{min_rate}",
                    rate >= min_rate,
                    f"实际: {rate:.1%}",
                )

    def verify_final_solution(self):
        """6. 最终报告验证"""
        print("\n" + "=" * 60)
        print("📄 Phase 6: 最终报告验证")
        print("=" * 60)

        summarizer_exp = self.golden["stage_expectations"].get("summarizer", {})
        final_path = summarizer_exp.get("final_solution_path", "final_solution.md")

        exists = self._file_exists(final_path)
        self._check(
            "final_solution.md存在",
            exists,
            critical=True,
        )

        if exists:
            with open(self.base_path / final_path, "r", encoding="utf-8") as f:
                content = f.read()

            self._check(
                "报告非空",
                len(content) > 100,
                f"字符数: {len(content)}",
            )

            for section in summarizer_exp.get("final_solution_must_contain_sections", []):
                self._check(
                    f"包含章节 '{section}'",
                    section in content,
                )

    def verify_req_traceability(self):
        """7. REQ-ID 追踪验证"""
        print("\n" + "=" * 60)
        print("🔗 Phase 7: REQ-ID 追踪验证")
        print("=" * 60)

        spec = self._read_json("data/frozen_spec.json")
        if not spec:
            self._check("frozen_spec可读(跳过追踪验证)", False)
            return

        valid_req_ids = set(r["id"] for r in spec.get("requirements", []))

        matrix = self._read_json("requirements_traceability_matrix.json")
        if matrix:
            self._check("追踪矩阵JSON可读", True)

            # 检查矩阵是否覆盖所有 P0 REQ-ID
            p0_ids = [
                r["id"] for r in spec.get("requirements", [])
                if r.get("priority") == "P0"
            ]
            matrix_req_ids = set()
            if isinstance(matrix, dict):
                # 矩阵可能是 {REQ-001: {...}} 或 {requirements: [{req_id/id: ...}]}
                if "requirements" in matrix and isinstance(matrix["requirements"], list):
                    for item in matrix["requirements"]:
                        if isinstance(item, dict):
                            # 支持 req_id 或 id 两种命名
                            rid = item.get("req_id") or item.get("id") or ""
                            matrix_req_ids.add(rid)
                else:
                    matrix_req_ids = set(matrix.keys())

            for pid in p0_ids:
                self._check(
                    f"P0 {pid} 在追踪矩阵中",
                    pid in matrix_req_ids,
                )
        else:
            self._check("追踪矩阵存在", False, "文件不存在或不可读")

    # =========================================================================
    # 执行 & 报告
    # =========================================================================

    def run_all(self) -> int:
        """执行全部验证，返回退出码"""
        print(f"\n{'🧪' * 20}")
        print(f"  Solution Pro E2E Golden Case 验证")
        print(f"  Session: {self.session_id}")
        print(f"  Golden:  {self.golden['meta']['name']}")
        print(f"  时间:    {datetime.now().isoformat()}")
        print(f"{'🧪' * 20}")

        self.verify_infrastructure()
        self.verify_execution_plan()
        self.verify_frozen_spec()
        self.verify_stages()
        self.verify_global_artifacts()
        self.verify_final_solution()
        self.verify_req_traceability()

        return self._print_summary()

    def _print_summary(self) -> int:
        """打印总结并返回退出码"""
        total = self.passed + self.failed + self.warnings
        pass_rate = self.passed / total if total > 0 else 0

        print(f"\n{'=' * 60}")
        print(f"📊 验证结果总结")
        print(f"{'=' * 60}")
        print(f"  总计: {total} 项检查")
        print(f"  ✅ PASS:    {self.passed}")
        print(f"  🔴 FAIL:    {self.failed}")
        print(f"  🟡 WARN:    {self.warnings}")
        print(f"  通过率:     {pass_rate:.1%}")
        print(f"{'=' * 60}")

        # 逐项打印
        print("\n详细结果:")
        for r in self.results:
            line = f"  {r['status']}  {r['name']}"
            if r["detail"]:
                line += f"  ({r['detail']})"
            print(line)

        # 退出码
        if self.failed > 0 and pass_rate < 0.7:
            verdict = "❌ FAIL"
            exit_code = 2
        elif self.failed > 0:
            verdict = "⚠️ PARTIAL"
            exit_code = 1
        else:
            verdict = "✅ PASS"
            exit_code = 0

        print(f"\n{'=' * 60}")
        print(f"  最终判定: {verdict} (exit code: {exit_code})")
        print(f"{'=' * 60}\n")

        return exit_code


def main():
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <session_id> [golden_case_path]")
        print(f"示例: {sys.argv[0]} golden_001_architecture_abc123")
        sys.exit(2)

    session_id = sys.argv[1]
    golden_path = sys.argv[2] if len(sys.argv) > 2 else None

    verifier = GoldenCaseVerifier(session_id, golden_path)
    exit_code = verifier.run_all()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
