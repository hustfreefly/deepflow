"""
Ship Pro v0.2.0 — 数据驱动工作包分解器

V2 架构：所有领域知识来自 LLM 预扫描生成的 domain_config.json。
编译器本身零硬编码，纯数据映射。

核心函数：
- _decompose_work_packages(bp, domain_config) → List[Dict]
- _validate_and_fallback(bp, domain_config) → domain_config or None
"""

from typing import Any, Dict, List, Optional

from .utils import (
    _safe_get,
    _phase_to_num,
)


# ============================================================================
# Phase Map Computation（保留 V1 逻辑，结构性代码）
# ============================================================================

def _compute_phase_map(modules: List[Dict], bp: Dict) -> Dict:
    """
    Compute phase assignment for each module.

    Strategy:
    1. Use compilation_order from domain_config if available
    2. Parse module tier field (e.g., "T1/2/3", "T1", "T2/3")
    3. Fallback: distribute by position

    Returns: {module_id_or_index: "phase_N"}
    """
    import re
    phase_map = {}
    if not modules:
        return phase_map

    style = _safe_get(bp, "architecture", "style", default="").lower()

    # Detect tier count from architecture style
    tier_count = 3  # default
    if any(k in style for k in ["四层", "4层", "four-tier", "4-tier"]):
        tier_count = 4
    elif any(k in style for k in ["三层", "3层", "three-tier", "3-tier", "三层架构"]):
        tier_count = 3
    elif any(k in style for k in ["两层", "2层", "two-tier", "2-tier"]):
        tier_count = 2

    # Try to parse tier field from modules
    has_tier_field = any(
        isinstance(m, dict) and m.get("tier") for m in modules
    )

    if has_tier_field:
        tier_phases = {}
        for i, mod in enumerate(modules, 1):
            mod_id = mod.get("id", f"module_{i}")
            tier_str = str(mod.get("tier", ""))

            if tier_str:
                match = re.search(r'[Tt]?(\d+)', tier_str)
                if match:
                    first_tier = int(match.group(1))
                    phase_num = min(first_tier, tier_count)
                    tier_phases[mod_id] = f"phase_{phase_num}"
                    tier_phases[i] = f"phase_{phase_num}"
                    continue

            tier_phases[mod_id] = _position_phase(i, len(modules), tier_count)
            tier_phases[i] = tier_phases[mod_id]

        # Check: if all modules ended up in the same phase, tier didn't differentiate
        unique_phases = set(tier_phases.values())
        if len(unique_phases) <= 1 and len(modules) > tier_count:
            for i, mod in enumerate(modules, 1):
                mod_id = mod.get("id", f"module_{i}")
                phase_map[mod_id] = _position_phase(i, len(modules), tier_count)
                phase_map[i] = phase_map[mod_id]
        else:
            phase_map = tier_phases
    else:
        for i, mod in enumerate(modules, 1):
            mod_id = mod.get("id", f"module_{i}")
            phase_map[mod_id] = _position_phase(i, len(modules), tier_count)
            phase_map[i] = phase_map[mod_id]

    return phase_map


def _position_phase(index: int, total: int, tier_count: int) -> str:
    """Assign phase by position: first third = phase_1, etc."""
    if total <= 0 or tier_count <= 0:
        return "phase_1"
    if total <= tier_count:
        return f"phase_{index}"

    chunk = total / tier_count
    phase_num = min(int((index - 1) / chunk) + 1, tier_count)
    return f"phase_{phase_num}"


# ============================================================================
# 依赖解析（数据驱动）
# ============================================================================

def _resolve_dependencies(
    mod_id: str,
    wp_id: str,
    domain_config: Optional[Dict],
    mod_to_wp: Dict[str, str],
    phase_num: int,
    all_packages: List[Dict],
) -> List[str]:
    """
    解析模块依赖关系。

    数据源优先级：
    1. domain_config.dependency_hints（LLM 预扫描推导）
    2. Blueprint modules[].dependencies（模块级声明）
    3. Phase 顺序（后期依赖前期）

    泛化设计：不硬编码任何领域关键词。
    """
    dependencies = []

    # Source 1: dependency_hints from domain_config
    if domain_config:
        for hint in domain_config.get("dependency_hints", []):
            if hint.get("from") == mod_id:
                to_id = hint.get("to", "")
                dep_wp_id = mod_to_wp.get(to_id)
                if dep_wp_id and dep_wp_id != wp_id and dep_wp_id not in dependencies:
                    dependencies.append(dep_wp_id)

    # Source 2: Phase-based fallback (later phases depend on earlier phases)
    if not dependencies and phase_num > 1:
        for prev_wp in all_packages:
            prev_phase_num = _phase_to_num(prev_wp["phase"])
            if prev_phase_num == phase_num - 1:
                if prev_wp["id"] not in dependencies:
                    dependencies.append(prev_wp["id"])

    return dependencies


# ============================================================================
# 需求分配（保留 V1 逻辑 + domain_config 增强）
# ============================================================================

def _assign_requirements(
    requirements: List[Dict], packages: List[Dict]
) -> None:
    """将需求分配到 Work Packages。

    策略（按优先级）：
    1. 按 module 功能匹配（req.description 与 WP 的 module name/summary 关键词重叠）
    2. 轮询分配（确保均匀分布）
    3. 每个 WP 至少关联 1 个 requirement（如果有的话）
    """
    if not requirements or not packages:
        return

    unassigned = []

    # Pass 1: 尝试按功能匹配
    for req in requirements:
        if not isinstance(req, dict):
            continue
        req_desc = (req.get("description", "") or req.get("text", "") or "").lower()
        req_id = req.get("req_id", "") or req.get("id", "")

        best_match = None
        best_score = 0

        for wp in packages:
            mod_name = wp.get("title", "").lower().replace("实现 ", "")
            score = 0
            for word in mod_name.split():
                if len(word) >= 2 and word in req_desc:
                    score += 1
            source_ref = wp.get("source_ref", "").lower()
            for word in source_ref.split():
                if len(word) >= 3 and word in req_desc:
                    score += 1

            if score > best_score:
                best_score = score
                best_match = wp

        if best_match and best_score >= 2:
            if req_id not in best_match["requirements"]:
                best_match["requirements"].append(req_id)
        else:
            unassigned.append(req_id)

    # Pass 2: 轮询分配未匹配的需求
    if unassigned and packages:
        wp_idx = 0
        for req_id in unassigned:
            attempts = 0
            while attempts < len(packages):
                target = packages[wp_idx % len(packages)]
                wp_idx += 1
                attempts += 1
                if not target["requirements"] or req_id not in target["requirements"]:
                    target["requirements"].append(req_id)
                    break
            else:
                if packages:
                    packages[-1]["requirements"].append(req_id)


# ============================================================================
# 需求级联传播（P2 保留）
# ============================================================================

def _propagate_requirements(packages: List[Dict]) -> None:
    """沿依赖图级联传播 requirements。"""
    wp_map = {wp["id"]: wp for wp in packages}

    for wp in packages:
        if not wp.get("requirements"):
            continue
        for dep_id in wp.get("dependencies", []):
            dep_wp = wp_map.get(dep_id)
            if dep_wp and not dep_wp.get("requirements"):
                for req_id in wp["requirements"][:2]:
                    if req_id not in dep_wp.get("requirements", []):
                        dep_wp.setdefault("requirements", []).append(req_id)


# ============================================================================
# V2 核心：数据驱动工作包分解
# ============================================================================

def _decompose_work_packages(
    bp: Dict,
    domain_config: Optional[Dict] = None,
    delivery: Optional[Dict] = None,
) -> List[Dict]:
    """
    Decompose architecture modules into work packages.

    V2 架构：
    - domain_config 提供所有领域知识（AC、交付物、约束、依赖）
    - 编译器零硬编码，纯数据映射
    - domain_config 为 None 时回退到 V1 行为（⚠️ 标记）

    Args:
        bp: Frozen Blueprint dict.
        domain_config: LLM 预扫描生成的领域配置（可选，None 时降级）。
        delivery: Optional delivery info dict with phases/dependency_hints.
    """
    modules = _safe_get(bp, "architecture", "modules", default=[])
    requirements = _safe_get(bp, "requirements", "items", default=[])
    forbidden = _safe_get(bp, "risks", "forbidden_changes", default=[])

    # 合并 domain_config 中的推导需求
    if domain_config:
        derived_reqs = domain_config.get("derived_requirements", [])
        for dr in derived_reqs:
            if isinstance(dr, dict) and dr.get("id"):
                requirements = list(requirements) + [dr]

    # Phase assignment
    phase_map = _compute_phase_map(modules, bp)

    # Override with delivery phases if available
    if delivery and isinstance(delivery, dict):
        delivery_phases = delivery.get("phases", [])
        if isinstance(delivery_phases, list):
            for phase_info in delivery_phases:
                if isinstance(phase_info, dict):
                    phase_name = phase_info.get("phase", "")
                    modules_in_phase = phase_info.get("modules", [])
                    if phase_name and isinstance(modules_in_phase, list):
                        for mod_id in modules_in_phase:
                            phase_map[mod_id] = phase_name

    # Override with compilation_order from domain_config
    if domain_config and domain_config.get("compilation_order"):
        comp_order = domain_config["compilation_order"]
        total = len(comp_order)
        tier_count = 3
        for idx, mid in enumerate(comp_order, 1):
            phase_map[mid] = _position_phase(idx, total, tier_count)

    # Build profiles lookup
    profiles = {}
    if domain_config:
        for p in domain_config.get("work_package_profiles", []):
            profiles[p.get("module_id", "")] = p

    # First pass: create all WPs
    packages = []

    for i, mod in enumerate(modules, 1):
        wp_id = f"WP-{i:03d}"
        mod_id = mod.get("id", f"module_{i}")
        mod_name = mod.get("name", f"Module {i}")
        mod_summary = mod.get("summary", "")

        # Phase assignment
        phase = phase_map.get(mod_id, phase_map.get(i, "phase_1"))
        phase_num = _phase_to_num(phase)

        # Get profile from domain_config
        profile = profiles.get(mod_id, {})
        confidence = profile.get("confidence", "low")

        # AC: from domain_config profile
        wp_ac = profile.get("suggested_ac", [])
        if not wp_ac:
            wp_ac = [f"⚠️ 待补充: {mod_name} 的验收标准（预扫描未覆盖此模块）"]

        # Deliverables: from domain_config profile
        deliverables = profile.get("suggested_deliverables", [])
        if not deliverables:
            deliverables = [f"⚠️ 待补充: {mod_name} 的交付物清单"]

        # Constraints: from domain_config profile + forbidden changes
        constraints = list(profile.get("suggested_constraints", []))
        for fc in forbidden:
            if isinstance(fc, str):
                constraints.append(f"禁止: {fc}")
        if not constraints:
            constraints = [f"⚠️ 待补充: {mod_name} 的技术约束"]

        # Complexity heuristic
        complexity = "medium"
        if phase_num == 1:
            complexity = "large"
        elif phase_num >= 3:
            complexity = "small"

        packages.append({
            "id": wp_id,
            "title": f"实现 {mod_name}",
            "phase": phase,
            "dependencies": [],  # Resolved in second pass
            "estimated_complexity": complexity,
            "related_modules": [mod_id],
            "requirements": [],
            "deliverables": deliverables,
            "acceptance_criteria": wp_ac,
            "constraints": constraints,
            "human_review_required": False,
            "source_ref": f"architecture.modules[{mod_id}]",
            "_mod_id": mod_id,  # Temporary, removed after dependency resolution
            "_confidence": confidence,
        })

    # Build module_id → wp_id mapping
    mod_to_wp = {}
    for wp in packages:
        for rm in wp.get("related_modules", []):
            mod_to_wp[rm] = wp["id"]

    # Second pass: resolve dependencies
    for wp in packages:
        mod_id = wp.pop("_mod_id")
        phase_num = _phase_to_num(wp["phase"])
        wp["dependencies"] = _resolve_dependencies(
            mod_id, wp["id"], domain_config, mod_to_wp, phase_num, packages
        )

    # Third pass: resolve module-level dependencies from Blueprint
    for i, mod in enumerate(modules, 1):
        mod_id = mod.get("id", f"module_{i}")
        mod_deps = mod.get("dependencies", [])
        if isinstance(mod_deps, list):
            wp_id = mod_to_wp.get(mod_id)
            if wp_id:
                for dep_mod_id in mod_deps:
                    dep_wp_id = mod_to_wp.get(dep_mod_id)
                    if dep_wp_id and dep_wp_id != wp_id:
                        for wp in packages:
                            if wp["id"] == wp_id:
                                if dep_wp_id not in wp["dependencies"]:
                                    wp["dependencies"].append(dep_wp_id)
                                break

    # Assign requirements
    _assign_requirements(requirements, packages)

    # Propagate requirements along dependency graph
    _propagate_requirements(packages)

    # Clean up temporary fields
    for wp in packages:
        wp.pop("_confidence", None)

    # Fallback: if no modules found, create catch-all WP
    if not packages:
        all_req_ids = [
            (r.get("req_id", "") or r.get("id", ""))
            for r in requirements if isinstance(r, dict)
        ]
        catch_all_constraints = [
            f"禁止: {fc}" for fc in forbidden if isinstance(fc, str)
        ]
        if not catch_all_constraints:
            catch_all_constraints.append("⚠️ 待补充: 需根据实现细节确认技术栈与边界限制")
        packages.append({
            "id": "WP-001",
            "title": _safe_get(bp, "intent", "project_name", default="项目实现"),
            "phase": "phase_1",
            "dependencies": [],
            "estimated_complexity": "large",
            "related_modules": [],
            "requirements": all_req_ids,
            "deliverables": ["⚠️ 待补充: 完整系统交付物清单"],
            "acceptance_criteria": ["⚠️ 待补充: 需根据需求确定验收标准"],
            "constraints": catch_all_constraints,
            "human_review_required": False,
            "source_ref": "intent.project_name (fallback — no architecture modules)",
        })

    return packages
