"""Feature extractor — convert graph nodes/edges into numerical feature tensors.

Provides deterministic feature extraction from Node and Edge objects into
normalized NumPy arrays suitable for PyTorch Geometric Data objects.

AC-2.2: Node feature dimension ≥ 8 (service_type one-hot, resource_usage, error_rate, etc.)
AC-2.3: Edge feature dimension ≥ 5 (latency, call_count, protocol, success_rate, etc.)
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

# Ordered service type vocabulary for one-hot encoding.
# New types default to the last index (8, "other").
SERVICE_TYPES: List[str] = [
    "api-gateway",
    "backend",
    "database",
    "cache",
    "queue",
    "frontend",
    "auth",
    "worker",
    "other",
]

# Ordered protocol vocabulary for one-hot encoding.
PROTOCOLS: List[str] = [
    "http",
    "grpc",
    "tcp",
    "udp",
    "amqp",
    "other",
]

# ── Node feature indices (12 dimensions) ──
# 0-8: service_type one-hot (9 dims)
# 9:   language (numeric encoding)
# 10:  replica_count (normalized)
# 11:  cpu_usage (normalized 0-1)
# 12:  mem_usage (normalized 0-1)
# 13:  error_rate (0-1)
# 14:  avg_response_time_ms (log-normalized)
# 15:  request_count (log-normalized)
NODE_FEATURE_DIM: int = 16

# ── Edge feature indices (9 dimensions) ──
# 0-5: protocol one-hot (6 dims)
# 6:   call_count (log-normalized)
# 7:   latency_p99_ms (log-normalized)
# 8:   avg_latency_ms (log-normalized)
# 9:   success_rate (0-1)
# 10:  error_count (log-normalized)
EDGE_FEATURE_DIM: int = 11

# Language numeric encoding
LANGUAGE_MAP: Dict[str, int] = {
    "python": 0,
    "java": 1,
    "go": 2,
    "javascript": 3,
    "typescript": 4,
    "rust": 5,
    "cpp": 6,
    "ruby": 7,
    "php": 8,
    "csharp": 9,
    "unknown": 10,
}


class FeatureExtractor:
    """Extracts numerical features from Node and Edge objects.

    All feature values are normalized to [0, 1] or log-scaled for stable
    GNN training.

    Example:
        >>> extractor = FeatureExtractor()
        >>> node_feats = extractor.extract_node_features(nodes)
        >>> edge_index, edge_attr = extractor.extract_edge_features(nodes, edges)
    """

    def __init__(self) -> None:
        self.service_type_index = {t: i for i, t in enumerate(SERVICE_TYPES)}
        self.protocol_index = {p: i for i, p in enumerate(PROTOCOLS)}

    def extract_node_features(self, nodes: List) -> np.ndarray:
        """Extract normalized node features.

        Args:
            nodes: List of Node objects.

        Returns:
            (N, NODE_FEATURE_DIM) float32 array.
        """
        if not nodes:
            return np.empty((0, NODE_FEATURE_DIM), dtype=np.float32)

        N = len(nodes)
        features = np.zeros((N, NODE_FEATURE_DIM), dtype=np.float32)

        # Collect raw values for normalization
        replica_counts = np.array([n.replica_count for n in nodes], dtype=np.float32)
        request_counts = np.array([n.request_count for n in nodes], dtype=np.float32)
        avg_response_times = np.array([n.avg_response_time_ms for n in nodes], dtype=np.float32)

        for i, node in enumerate(nodes):
            # Column 0-8: service_type one-hot
            st_idx = self.service_type_index.get(node.service_type, len(SERVICE_TYPES) - 1)
            features[i, st_idx] = 1.0

            # Column 9: language index (normalized to [0, 1])
            lang_idx = LANGUAGE_MAP.get(node.language, len(LANGUAGE_MAP) - 1)
            features[i, 9] = lang_idx / max(1.0, float(len(LANGUAGE_MAP) - 1))

            # Column 10: replica_count (log-normalized)
            features[i, 10] = self._log_normalize(
                node.replica_count, replica_counts.max()
            )

            # Column 11: cpu_usage (already 0-100, normalize to 0-1)
            features[i, 11] = np.clip(node.cpu_usage / 100.0, 0.0, 1.0)

            # Column 12: mem_usage (already 0-100, normalize to 0-1)
            features[i, 12] = np.clip(node.mem_usage / 100.0, 0.0, 1.0)

            # Column 13: error_rate (already 0-1)
            features[i, 13] = np.clip(node.error_rate, 0.0, 1.0)

            # Column 14: avg_response_time_ms (log-normalized)
            features[i, 14] = self._log_normalize(
                node.avg_response_time_ms, avg_response_times.max()
            )

            # Column 15: request_count (log-normalized)
            features[i, 15] = self._log_normalize(
                node.request_count, request_counts.max()
            )

        return features

    def extract_edge_features(
        self, node_list: List, edge_list: List
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Extract edge index and edge features.

        Args:
            node_list: Ordered list of Node objects (defines node index mapping).
            edge_list: List of Edge objects.

        Returns:
            Tuple of:
                edge_index: (2, E) int64 array of [source_idx, target_idx].
                edge_attr: (E, EDGE_FEATURE_DIM) float32 array.
        """
        if not edge_list:
            return (
                np.empty((2, 0), dtype=np.int64),
                np.empty((0, EDGE_FEATURE_DIM), dtype=np.float32),
            )

        # Build node name -> index mapping
        node_to_idx = {node.service_name: i for i, node in enumerate(node_list)}

        E = len(edge_list)
        edge_index = np.zeros((2, E), dtype=np.int64)
        edge_attr = np.zeros((E, EDGE_FEATURE_DIM), dtype=np.float32)

        # Collect raw values for normalization
        call_counts = np.array([e.call_count for e in edge_list], dtype=np.float32)
        latency_p99s = np.array([e.latency_p99_ms for e in edge_list], dtype=np.float32)
        avg_latencies = np.array([e.avg_latency_ms for e in edge_list], dtype=np.float32)
        error_counts = np.array([e.error_count for e in edge_list], dtype=np.float32)

        for i, edge in enumerate(edge_list):
            # Edge index
            src_idx = node_to_idx.get(edge.source, -1)
            tgt_idx = node_to_idx.get(edge.target, -1)
            if src_idx == -1 or tgt_idx == -1:
                # Skip edges referencing unknown nodes
                edge_index[:, i] = 0
                continue
            edge_index[0, i] = src_idx
            edge_index[1, i] = tgt_idx

            # Column 0-5: protocol one-hot
            p_idx = self.protocol_index.get(edge.protocol, len(PROTOCOLS) - 1)
            edge_attr[i, p_idx] = 1.0

            # Column 6: call_count (log-normalized)
            edge_attr[i, 6] = self._log_normalize(
                edge.call_count, call_counts.max()
            )

            # Column 7: latency_p99_ms (log-normalized)
            edge_attr[i, 7] = self._log_normalize(
                edge.latency_p99_ms, latency_p99s.max()
            )

            # Column 8: avg_latency_ms (log-normalized)
            edge_attr[i, 8] = self._log_normalize(
                edge.avg_latency_ms, avg_latencies.max()
            )

            # Column 9: success_rate (0-1)
            edge_attr[i, 9] = np.clip(edge.success_rate, 0.0, 1.0)

            # Column 10: error_count (log-normalized)
            edge_attr[i, 10] = self._log_normalize(
                edge.error_count, error_counts.max()
            )

        return edge_index, edge_attr

    @staticmethod
    def _log_normalize(value: float, max_value: float, eps: float = 1e-8) -> float:
        """Log-scale normalization: log(1 + value) / log(1 + max_value).

        Returns 0.0 when max_value is 0 or near-zero.
        """
        if max_value < eps:
            return 0.0
        return float(np.log1p(value) / np.log1p(max_value))