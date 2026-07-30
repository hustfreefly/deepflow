"""
Phase Deriver — Deliver Pro V3 核心：derive, don't sync.

文件系统是唯一真相。phase / worker 进度 / validate 轮次全部从文件推导，
不依赖任何持久化状态文件做决策。

推导规则（task 级）：
  - 任务目录存在 + 无 MANIFEST  → running（超时 → failed）
  - 任务目录存在 + MANIFEST     → 按 MANIFEST.status（FAILED → failed，其余 → completed）
  - 任务目录不存在              → pending
  - 依赖中包含 failed           → blocked（级联，按 failed 处理）

推导规则（phase 级，最高 artifact 胜出）：
  delivery_manifest.json + final_deliverable 非空 → DONE
  validation_result.json                          → PACKAGING
  integrated_draft/DELIVERABLE.md                 → VALIDATING
  execution_plan.json + 全部任务已解决            → ASSEMBLING
  execution_plan.json                             → GENERATING
  否则                                            → PENDING

关键配套约定：
  - 重新进入某阶段时必须失效下游 artifact（invalidate_downstream），
    例如 fix-loop 重跑 integrate 前删除 validation_result.json，
    否则旧 verdict 会让推导跳到 PACKAGING。
"""

from __future__ import annotations

import glob
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Worker 超时：目录存在但长时间无 MANIFEST → 判定死亡
# 30 分钟：宁可慢检测，不误杀慢 Worker（误杀会级联 block 下游任务）
WORKER_TIMEOUT_SECONDS = 1800

# DONE 契约（K3, Pulse V1.1）：交付目录至少含一个 ≥50B 的实质文件。
# 防空 DELIVERABLE.md 过关（2026-07-24 STORE-003 实证：0B 交付物也曾被判 DONE）。
# 单位注意（DryRun R1 C#2）：本层按【字节】(st_size) 检测；worker 层 wp_runner
# 按【字符】(len) 检测 MIN_DELIVERABLE_LENGTH=50。50 字符 ASCII ≥ 50 字节，
# 通过 worker 层的产物必然通过本层 —— 宽松方向，不会误杀。
DONE_MIN_FILE_BYTES = 50

# Phase 常量（与 orchestrator 历史字符串保持一致）
PHASE_DONE = "DONE"
PHASE_PACKAGING = "PACKAGING"
PHASE_VALIDATING = "VALIDATING"
PHASE_ASSEMBLING = "ASSEMBLING"
PHASE_GENERATING = "GENERATING"
PHASE_PENDING = "PENDING"


def _fresh_mtime(path: Path) -> float:
    """递归 rglob 取目录内最新文件 mtime（含目录本身）。

    L0 fix（2026-07-28 重复 spawn 事故）：目录 mtime 只在目录项增删时更新，
    Worker 改写已有文件不刷新它 → 慢 Worker 被误判超时 → 重复 spawn。
    递归取所有文件 mtime 的最大值，慢 Worker 写文件时保持新鲜。
    """
    latest = path.stat().st_mtime
    for f in path.rglob("*"):
        if f.is_file():
            try:
                latest = max(latest, f.stat().st_mtime)
            except OSError:
                pass
    return latest


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _has_substantial_file(directory: Path, min_bytes: int = DONE_MIN_FILE_BYTES) -> bool:
    """DONE 契约检查：交付目录至少含一个 ≥min_bytes 的实质文件。

    K2 排除规则（Pulse V1.1）：final_deliverable 内嵌套的 worker_outputs/
    目录是 package agent 违规灌入的原始中间产物（SDK-001 实证 284MB），
    不计入交付物。
    """
    for f in directory.rglob("*"):
        if not f.is_file():
            continue
        try:
            if "worker_outputs" in f.relative_to(directory).parts:
                continue
            if f.stat().st_size >= min_bytes:
                return True
        except (OSError, ValueError):
            continue
    return False


def derive_worker_progress(
    wp_dir: Path,
    plan_task_ids: set[str] | None = None,
    task_deps: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """从文件系统推导 Worker 进度。

    Args:
        wp_dir: WP 目录（deliver_pro/{wp_subdir}）
        plan_task_ids: execution_plan 中的全部 task_id（可选，用于 pending 计算）
        task_deps: {task_id: [dep_task_id, ...]}（可选，用于 blocked 级联）

    Returns:
        {
            "completed": set[str],
            "failed": set[str],
            "blocked": set[str],   # 因依赖失败而永远无法执行（计入 failed 语义）
            "running": set[str],
            "pending": set[str],
            "timed_out": set[str], # 本次推导新发现的超时任务
            "failure_reasons": {task_id: reason},
        }
    """
    stages_dir = wp_dir / "stages"
    worker_outputs = stages_dir / "worker_outputs"

    completed: set[str] = set()
    failed: set[str] = set()
    running: set[str] = set()
    timed_out: set[str] = set()
    failure_reasons: dict[str, str] = {}

    # 扫描任务目录（目录存在 ⟺ 已 spawn）
    if worker_outputs.exists():
        for task_dir in worker_outputs.iterdir():
            if not task_dir.is_dir():
                continue
            task_id = task_dir.name
            manifest_path = task_dir / "MANIFEST.json"
            if manifest_path.exists():
                data = _read_json(manifest_path) or {}
                status = data.get("status", "")
                if status == "FAILED":
                    failed.add(task_id)
                    failure_reasons[task_id] = data.get("failure_reason", "worker_reported_failed")
                else:
                    # COMPLETE / PASS / PARTIAL / 其他 → 完成
                    completed.add(task_id)
            else:
                # 无 MANIFEST → running 或超时
                # L0 fix: 递归 rglob 取最新文件 mtime（慢 Worker 写文件时目录 mtime 不更新）
                try:
                    mtime = _fresh_mtime(task_dir)
                except OSError:
                    mtime = time.time()
                if time.time() - mtime > WORKER_TIMEOUT_SECONDS:
                    failed.add(task_id)
                    timed_out.add(task_id)
                    failure_reasons[task_id] = (
                        f"timeout: no MANIFEST for >{WORKER_TIMEOUT_SECONDS}s"
                    )
                else:
                    running.add(task_id)

    # pending = plan 中有但从未 spawn 的任务
    pending: set[str] = set()
    if plan_task_ids:
        resolved = completed | failed | running
        pending = set(plan_task_ids) - resolved

    # blocked 级联：依赖中含 failed/blocked 的任务 → blocked
    blocked: set[str] = set()
    if task_deps:
        unresolved_failed = failed | blocked
        changed = True
        while changed:
            changed = False
            for task_id, deps in task_deps.items():
                if task_id in completed or task_id in failed or task_id in blocked:
                    continue
                if any(dep in unresolved_failed for dep in deps):
                    blocked.add(task_id)
                    failure_reasons[task_id] = "dependency_failed"
                    unresolved_failed = failed | blocked
                    changed = True

    return {
        "completed": completed,
        "failed": failed,
        "blocked": blocked,
        "running": running,
        "pending": pending - blocked,
        "timed_out": timed_out,
        "failure_reasons": failure_reasons,
    }


def _validate_delivery_manifest(manifest_path: Path) -> bool:
    """校验 delivery_manifest.json 是否为有效 JSON 且符合 DeliveryManifest schema。

    B1 fix（2026-07-30）：畸形 manifest 不应让 derive_phase 返回 DONE。
    Package Agent 输出损坏时，应回退到 PACKAGING 让 package 重试。

    Returns:
        True: manifest 有效或不存在（不存在时由调用方处理）
        False: manifest 存在但损坏（JSON 无效或 schema 验证失败）
    """
    if not manifest_path.exists():
        return True  # 不存在不是损坏，由调用方判断

    data = _read_json(manifest_path)
    if data is None:
        logger.warning(f"delivery_manifest.json is invalid JSON: {manifest_path}")
        return False

    # Schema 验证：尝试用 DeliveryManifest 解析
    try:
        from domains.deliver_pro.contracts.delivery_manifest import DeliveryManifest
        DeliveryManifest.model_validate(data)
        return True
    except Exception as e:
        logger.warning(f"delivery_manifest.json failed schema validation: {manifest_path}: {e}")
        return False


def derive_phase(wp_dir: Path) -> str:
    """从文件系统推导 WP 当前 phase（最高 artifact 胜出）。

    Args:
        wp_dir: WP 目录（deliver_pro/{wp_subdir}）

    Returns:
        DONE | PACKAGING | VALIDATING | ASSEMBLING | GENERATING | PENDING
    """
    stages_dir = wp_dir / "stages"
    if not stages_dir.exists():
        return PHASE_PENDING

    # DONE: 交付清单 + 交付物目录非空 + manifest 有效
    manifest_file = stages_dir / "delivery_manifest.json"
    final_dir = stages_dir / "final_deliverable"
    if manifest_file.exists() and final_dir.exists():
        if _has_substantial_file(final_dir):
            # B1 fix: 校验 manifest 是否为有效 JSON 且符合 schema
            if _validate_delivery_manifest(manifest_file):
                return PHASE_DONE
            # manifest 损坏，回退到 PACKAGING 让 package agent 重试
            logger.warning(
                f"{wp_dir.name}: delivery_manifest.json is corrupted, "
                f"falling back to PACKAGING for retry"
            )
            return PHASE_PACKAGING
    # Legacy 兼容（2026-07-23 prompt 路径歧义事故）：package prompt 曾漏写
    # stages/ 前缀，导致 package agent 把交付物写到 WP 根目录 final_deliverable/。
    # prompt 已修复（deliver_package.md 路径铁律），此处接受旧位置但发出警告。
    legacy_final_dir = wp_dir / "final_deliverable"
    if manifest_file.exists() and legacy_final_dir.exists():
        if _has_substantial_file(legacy_final_dir):
            # B1 fix: legacy 路径也要校验 manifest
            if _validate_delivery_manifest(manifest_file):
                import warnings
                warnings.warn(
                    f"{wp_dir.name}: final_deliverable 在 WP 根目录（legacy 路径），"
                    f"应迁移到 stages/final_deliverable/",
                    DeprecationWarning,
                    stacklevel=2,
                )
                return PHASE_DONE
            # manifest 损坏，回退到 PACKAGING
            logger.warning(
                f"{wp_dir.name}: delivery_manifest.json is corrupted (legacy path), "
                f"falling back to PACKAGING for retry"
            )
            return PHASE_PACKAGING

    # PACKAGING: verdict 已产出（validate 完成，可以打包）
    if (stages_dir / "validation_result.json").exists():
        return PHASE_PACKAGING

    # VALIDATING: 拼接稿已产出（assembly 完成，可以验证）
    if (stages_dir / "integrated_draft" / "DELIVERABLE.md").exists():
        return PHASE_VALIDATING

    # ASSEMBLING / GENERATING: 看 plan + worker 进度
    plan_path = stages_dir / "execution_plan.json"
    if plan_path.exists():
        plan_data = _read_json(plan_path) or {}
        task_graph = plan_data.get("task_graph", [])
        if task_graph:
            # 兼容两种 task_graph 格式：dict（完整 TaskNode）或 str（task_id 列表）
            plan_task_ids = {
                t.get("task_id", "") if isinstance(t, dict) else str(t)
                for t in task_graph
            }
            task_deps = {
                (t.get("task_id", "") if isinstance(t, dict) else str(t)):
                    (t.get("depends_on", []) if isinstance(t, dict) else [])
                for t in task_graph
            }
            progress = derive_worker_progress(wp_dir, plan_task_ids, task_deps)
            resolved = (
                progress["completed"] | progress["failed"] | progress["blocked"]
            )
            if len(resolved) >= len(plan_task_ids):
                return PHASE_ASSEMBLING
            return PHASE_GENERATING
        # 空 plan（zero-worker）→ 直接可拼接（run_integrate 会处理空情况）
        return PHASE_ASSEMBLING

    return PHASE_PENDING


def derive_validate_round(wp_dir: Path) -> int:
    """推导当前 validate 轮次。

    优先级：validation_result.json 的 round 字段 → progress log 的 round_count → 0
    """
    stages_dir = wp_dir / "stages"
    verdict = _read_json(stages_dir / "validation_result.json")
    if verdict and isinstance(verdict.get("round"), int):
        return verdict["round"]

    log = _read_json(wp_dir / "progress_log.json")
    if log and isinstance(log.get("round_count"), int):
        return log["round_count"]

    # 兼容旧 delivery_state.json（迁移期）
    old = _read_json(wp_dir / "delivery_state.json")
    if old and isinstance(old.get("round_count"), int):
        return old["round_count"]

    return 0


def invalidate_downstream(wp_dir: Path, from_phase: str) -> list[str]:
    """重新进入某阶段前，失效其下游 artifact（防止旧产物误导推导）。

    Args:
        from_phase: 即将重新进入的阶段（"GENERATING" | "INTEGRATING" | "VALIDATING"）

    Returns:
        被删除的文件列表
    """
    stages_dir = wp_dir / "stages"
    removed: list[str] = []

    # 下游 artifact 链（按 phase 顺序）
    downstream_chain = {
        "GENERATING": [
            stages_dir / "integrated_draft" / "DELIVERABLE.md",
            stages_dir / "integrated_draft" / "integration_report.json",
            stages_dir / "validation_result.json",
            stages_dir / "delivery_manifest.json",
        ],
        "INTEGRATING": [
            stages_dir / "validation_result.json",
            stages_dir / "delivery_manifest.json",
        ],
        "VALIDATING": [
            stages_dir / "delivery_manifest.json",
        ],
    }

    for path in downstream_chain.get(from_phase, []):
        if path.exists():
            try:
                path.unlink()
                removed.append(str(path))
                logger.info(f"invalidate_downstream({from_phase}): removed {path.name}")
            except OSError as e:
                logger.warning(f"invalidate_downstream: failed to remove {path}: {e}")

    return removed


def migrate_legacy_worker_outputs(wp_dir: Path, blackboard_root: Path | None = None) -> list[str]:
    """搬迁 legacy 路径的 worker 输出到标准路径（幂等）。

    标准路径: {wp_dir}/stages/worker_outputs/
    Legacy 1: {wp_dir}/worker_outputs/（无 stages 层）
    Legacy 2: {wp_dir}/../stages/worker_outputs/（无 wp_subdir 层）

    Args:
        wp_dir: WP 目录
        blackboard_root: 可选的 blackboard 根目录，用于显式计算 Legacy 2 路径，
                         避免 .parent 在含 slash 的 project_name 下出错。

    Returns:
        搬迁的 task_id 列表
    """
    import shutil

    correct_dir = wp_dir / "stages" / "worker_outputs"
    migrated: list[str] = []

    # P2-2: 优先使用显式 blackboard_root，避免 .parent 在 slash 路径下出错
    if blackboard_root is not None:
        # 从 wp_dir 中提取 deliver_pro 子目录名作为 legacy 路径
        # wp_dir = blackboard_root / project / "deliver_pro" / wp_subdir
        legacy2_dir = blackboard_root / "stages" / "worker_outputs"
    else:
        legacy2_dir = wp_dir.parent / "stages" / "worker_outputs"

    legacy_dirs = [
        wp_dir / "worker_outputs",  # Legacy 1
        legacy2_dir,  # Legacy 2
    ]

    for legacy_dir in legacy_dirs:
        if not legacy_dir.exists() or legacy_dir == correct_dir:
            continue
        for task_dir in legacy_dir.iterdir():
            if not task_dir.is_dir():
                continue
            dst = correct_dir / task_dir.name
            if not (dst / "MANIFEST.json").exists():
                try:
                    correct_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(str(task_dir), str(dst), dirs_exist_ok=True)
                    migrated.append(task_dir.name)
                    logger.info(f"migrated legacy worker output: {task_dir.name}")
                except OSError as e:
                    logger.warning(f"failed to migrate {task_dir.name}: {e}")

    return migrated


def derive_wp_status(wp_dir: Path) -> dict[str, Any]:
    """一键推导 WP 完整状态（供 orchestrator/driver 使用）。

    Returns:
        {
            "phase": str,
            "workers": derive_worker_progress 结果（有 plan 时）,
            "validate_round": int,
        }
    """
    status: dict[str, Any] = {
        "phase": derive_phase(wp_dir),
        "validate_round": derive_validate_round(wp_dir),
    }

    plan_path = wp_dir / "stages" / "execution_plan.json"
    if plan_path.exists():
        plan_data = _read_json(plan_path) or {}
        task_graph = plan_data.get("task_graph", [])
        if task_graph:
            plan_task_ids = {
                t.get("task_id", "") if isinstance(t, dict) else str(t)
                for t in task_graph
            }
            task_deps = {
                (t.get("task_id", "") if isinstance(t, dict) else str(t)):
                    (t.get("depends_on", []) if isinstance(t, dict) else [])
                for t in task_graph
            }
            status["workers"] = derive_worker_progress(wp_dir, plan_task_ids, task_deps)

    return status
