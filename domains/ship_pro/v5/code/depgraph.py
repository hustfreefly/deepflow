"""
P2-3 DepGraph Builder - 依赖图构建器（纯代码，不用 LLM）

拓扑排序 + 并行分组 + 关键路径 + 循环依赖检测。
确定性算法，100% 可预测。
"""
from collections import defaultdict, deque
from typing import Dict, List, Any, Tuple, Optional


def build_dependency_graph(work_packages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    输入: [{id: "WP-001", dependencies: ["WP-002", "WP-003"]}, ...]
    输出: {
        execution_order: ["WP-001", "WP-002", ...],
        parallel_groups: [["WP-001"], ["WP-002", "WP-003"], ...],
        critical_path: ["WP-001", "WP-003", "WP-005"],
        edges: [{from: "WP-002", to: "WP-001"}, ...],
        has_cycle: bool
    }
    """
    wp_ids = [wp["id"] for wp in work_packages]
    wp_map = {wp["id"]: wp for wp in work_packages}

    # 构建邻接表 (dep → wp, 即 dep 必须在 wp 之前完成)
    # graph[dep] = [wp1, wp2, ...] 表示 dep 完成后才能开始 wp1, wp2
    graph: Dict[str, List[str]] = defaultdict(list)
    in_degree: Dict[str, int] = {wp_id: 0 for wp_id in wp_ids}

    for wp in work_packages:
        wp_id = wp["id"]
        for dep in wp.get("dependencies", []):
            if dep in wp_map:  # 只处理存在的依赖
                graph[dep].append(wp_id)
                in_degree[wp_id] = in_degree.get(wp_id, 0) + 1

    # Kahn 拓扑排序
    queue = deque([wp_id for wp_id in wp_ids if in_degree.get(wp_id, 0) == 0])
    topo_order: List[str] = []
    level: Dict[str, int] = {}

    while queue:
        node = queue.popleft()
        topo_order.append(node)

        # 计算 level: 所有依赖的最大 level + 1
        node_deps = wp_map[node].get("dependencies", [])
        if not node_deps:
            level[node] = 0
        else:
            level[node] = max((level.get(dep, 0) for dep in node_deps if dep in level), default=0) + 1

        for neighbor in graph.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    has_cycle = len(topo_order) != len(wp_ids)

    # 并行分组 (同 level 的 WP 可以并行)
    parallel_groups_dict: Dict[int, List[str]] = defaultdict(list)
    for wp_id, lvl in level.items():
        parallel_groups_dict[lvl].append(wp_id)
    parallel_groups = [parallel_groups_dict[k] for k in sorted(parallel_groups_dict.keys())]

    # 关键路径 (最长路径)
    critical_path = _find_critical_path(work_packages, wp_map, graph)

    # 构建 edges
    edges = []
    for wp in work_packages:
        for dep in wp.get("dependencies", []):
            if dep in wp_map:
                edges.append({"from": dep, "to": wp["id"]})

    return {
        "execution_order": topo_order,
        "parallel_groups": parallel_groups,
        "critical_path": critical_path,
        "edges": edges,
        "has_cycle": has_cycle,
        "max_parallel": max(len(g) for g in parallel_groups) if parallel_groups else 0,
        "total_levels": len(parallel_groups),
    }


def _find_critical_path(
    work_packages: List[Dict],
    wp_map: Dict[str, Dict],
    graph: Dict[str, List[str]],
) -> List[str]:
    """找最长路径（关键路径）"""
    # 用动态规划: dist[node] = 从 node 出发的最长路径长度
    dist: Dict[str, int] = {}
    successor: Dict[str, Optional[str]] = {}

    def dfs(node: str, visited: set) -> int:
        if node in dist:
            return dist[node]
        if node in visited:
            return 0  # 循环依赖，返回 0

        visited.add(node)
        max_dist = 0
        best_next = None

        for neighbor in graph.get(node, []):
            d = dfs(neighbor, visited)
            if d + 1 > max_dist:
                max_dist = d + 1
                best_next = neighbor

        dist[node] = max_dist
        successor[node] = best_next
        visited.discard(node)
        return max_dist

    # 从所有入度为 0 的节点开始
    roots = [wp["id"] for wp in work_packages if not wp.get("dependencies")]
    if not roots:
        roots = [work_packages[0]["id"]] if work_packages else []

    max_path_len = 0
    best_root = None
    for root in roots:
        d = dfs(root, set())
        if d > max_path_len:
            max_path_len = d
            best_root = root

    # 重建路径
    if best_root is None:
        return []

    path = [best_root]
    current = best_root
    while successor.get(current) is not None:
        current = successor[current]
        path.append(current)

    return path


if __name__ == "__main__":
    # 测试用例 1: 线性链
    test_wps_linear = [
        {"id": "WP-001", "dependencies": []},
        {"id": "WP-002", "dependencies": ["WP-001"]},
        {"id": "WP-003", "dependencies": ["WP-002"]},
    ]

    result = build_dependency_graph(test_wps_linear)
    print("=== 测试 1: 线性链 ===")
    print(f"  执行顺序: {result['execution_order']}")
    print(f"  并行分组: {result['parallel_groups']}")
    print(f"  关键路径: {result['critical_path']}")
    print(f"  循环依赖: {result['has_cycle']}")
    assert result["execution_order"] == ["WP-001", "WP-002", "WP-003"]
    assert result["critical_path"] == ["WP-001", "WP-002", "WP-003"]
    assert not result["has_cycle"]

    # 测试用例 2: 并行分支
    test_wps_parallel = [
        {"id": "WP-001", "dependencies": []},
        {"id": "WP-002", "dependencies": ["WP-001"]},
        {"id": "WP-003", "dependencies": ["WP-001"]},
        {"id": "WP-004", "dependencies": ["WP-002", "WP-003"]},
    ]

    result = build_dependency_graph(test_wps_parallel)
    print("\n=== 测试 2: 并行分支 ===")
    print(f"  执行顺序: {result['execution_order']}")
    print(f"  并行分组: {result['parallel_groups']}")
    print(f"  关键路径: {result['critical_path']}")
    print(f"  最大并行: {result['max_parallel']}")
    assert set(result["parallel_groups"][1]) == {"WP-002", "WP-003"}
    assert result["max_parallel"] == 2
    assert not result["has_cycle"]

    # 测试用例 3: 循环依赖
    test_wps_cycle = [
        {"id": "WP-001", "dependencies": ["WP-003"]},
        {"id": "WP-002", "dependencies": ["WP-001"]},
        {"id": "WP-003", "dependencies": ["WP-002"]},
    ]

    result = build_dependency_graph(test_wps_cycle)
    print("\n=== 测试 3: 循环依赖 ===")
    print(f"  循环依赖: {result['has_cycle']}")
    print(f"  拓扑排序: {result['execution_order']} (不完整)")
    assert result["has_cycle"]

    # 测试用例 4: 复杂 DAG (类似 ObserveHub)
    test_wps_complex = [
        {"id": "WP-001", "dependencies": []},           # Agent Collector
        {"id": "WP-002", "dependencies": ["WP-001"]},   # Gateway Collector
        {"id": "WP-003", "dependencies": ["WP-002"]},   # Kafka
        {"id": "WP-004", "dependencies": ["WP-003"]},   # ClickHouse
        {"id": "WP-005", "dependencies": ["WP-004"]},   # Object Storage
        {"id": "WP-006", "dependencies": ["WP-004", "WP-005"]},  # Query API
        {"id": "WP-007", "dependencies": ["WP-004"]},   # Alert Engine
        {"id": "WP-008", "dependencies": ["WP-007", "WP-006"]},  # RCA Engine
        {"id": "WP-009", "dependencies": ["WP-001", "WP-002", "WP-003", "WP-004"]},  # Self-Monitoring
    ]

    result = build_dependency_graph(test_wps_complex)
    print("\n=== 测试 4: 复杂 DAG (ObserveHub) ===")
    print(f"  执行顺序: {result['execution_order']}")
    print(f"  并行分组: {result['parallel_groups']}")
    print(f"  关键路径: {result['critical_path']}")
    print(f"  总层级: {result['total_levels']}")
    print(f"  最大并行: {result['max_parallel']}")
    assert not result["has_cycle"]
    assert result["execution_order"][0] == "WP-001"  # 第一个必须是 WP-001
    assert "WP-004" in result["critical_path"]  # ClickHouse 在关键路径上

    print("\n✅ 所有测试通过")
