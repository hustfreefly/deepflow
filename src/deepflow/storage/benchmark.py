"""
性能基准测试模块。

提供 SQLite+WAL 存储引擎的性能测试功能。
"""

import argparse
import json
import time
from pathlib import Path
from typing import Dict, Any

from deepflow.storage.sqlite_engine import SQLiteEngine
from deepflow.storage.schema_manager import SchemaManager


def run_benchmark(inserts: int = 10000, db_path: str = None) -> Dict[str, Any]:
    """
    运行性能基准测试。
    
    测量：
    - 总耗时
    - 每条插入平均时间
    - 插入速度（条/秒）
    - WAL 文件大小
    - 数据库文件大小
    
    Args:
        inserts: 插入的事件数量
        db_path: 数据库文件路径（默认为临时文件）
    
    Returns:
        包含测试结果的字典
    """
    # 默认使用内存数据库
    if db_path is None:
        db_path = ":memory:"
    
    results = {}
    
    # 初始化引擎和 schema
    engine = SQLiteEngine(db_path)
    schema_manager = SchemaManager(engine)
    
    try:
        # 创建 schema
        start_create = time.perf_counter()
        schema_manager.create_initial_schema()
        create_time = time.perf_counter() - start_create
        
        # 生成测试数据
        test_events = []
        for i in range(inserts):
            test_events.append({
                "run_id": f"run-{i // 100}",
                "event_type": "test_event",
                "event_seq": i % 1000,
                "timestamp": f"2026-06-22T20:00:{i % 60:02d}.000Z",
                "worker_id": f"worker-{i % 10}",
                "phase_name": f"phase-{i % 5}",
                "duration_ms": 100 + i % 900,
                "tokens_in": 1000 + i * 10,
                "tokens_out": 500 + i * 5,
                "cost": 0.01 + i * 0.001,
                "model": "test-model",
                "status": "success",
                "error_type": None,
                "error_message": None,
                "metadata": json.dumps({"index": i}),
                "collector_source": "benchmark",
            })
        
        # 批量插入
        start_insert = time.perf_counter()
        inserted = engine.insert_events(test_events)
        insert_time = time.perf_counter() - start_insert
        
        # 查询验证
        start_query = time.perf_counter()
        cursor = engine.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM events")
        count = cursor.fetchone()[0]
        query_time = time.perf_counter() - start_query
        
        # WAL checkpoint
        start_checkpoint = time.perf_counter()
        checkpoint_result = engine.checkpoint(mode="PASSIVE")
        checkpoint_time = time.perf_counter() - start_checkpoint
        
        # 文件大小
        db_file = Path(db_path)
        wal_file = Path(f"{db_path}-wal")
        shm_file = Path(f"{db_path}-shm")
        
        db_size = db_file.stat().st_size if db_file.exists() else 0
        wal_size = wal_file.stat().st_size if wal_file.exists() else 0
        shm_size = shm_file.stat().st_size if shm_file.exists() else 0
        
        # 计算统计
        avg_insert_time = insert_time / inserts if inserts > 0 else 0
        insert_rate = inserts / insert_time if insert_time > 0 else 0
        
        results = {
            "inserts": inserts,
            "inserted_count": inserted,
            "total_time_seconds": round(insert_time, 4),
            "avg_insert_time_ms": round(avg_insert_time * 1000, 4),
            "insert_rate_per_second": round(insert_rate, 2),
            "create_schema_time_seconds": round(create_time, 4),
            "query_time_seconds": round(query_time, 4),
            "query_result_count": count,
            "checkpoint_time_seconds": round(checkpoint_time, 4),
            "checkpoint_result": checkpoint_result,
            "file_sizes": {
                "database_bytes": db_size,
                "wal_bytes": wal_size,
                "shm_bytes": shm_size,
                "database_kb": round(db_size / 1024, 2),
                "wal_kb": round(wal_size / 1024, 2),
            },
        }
        
    finally:
        engine.close()
    
    return results


def print_results(results: Dict[str, Any]):
    """
    打印测试结果。
    
    Args:
        results: 测试结果字典
    """
    print("\n" + "=" * 60)
    print("SQLite+WAL Performance Benchmark Results")
    print("=" * 60)
    
    print("\n【Insert Performance】")
    print(f"  Inserted:      {results['inserted_count']:,} records")
    print(f"  Total Time:    {results['total_time_seconds']:.4f} seconds")
    print(f"  Avg/Record:    {results['avg_insert_time_ms']:.4f} ms")
    print(f"  Speed:         {results['insert_rate_per_second']:,.2f} records/sec")
    
    print("\n【Schema Creation】")
    print(f"  Time:          {results['create_schema_time_seconds']:.4f} seconds")
    
    print("\n【Query Test】")
    print(f"  Count Query:   {results['query_result_count']:,} records")
    print(f"  Query Time:    {results['query_time_seconds']:.4f} seconds")
    
    print("\n【WAL Checkpoint】")
    print(f"  Checkpoint:    {results['checkpoint_time_seconds']:.4f} seconds")
    if results.get('checkpoint_result'):
        print(f"  Result:        {results['checkpoint_result']}")
    
    print("\n【File Sizes (After Checkpoint)】")
    sizes = results['file_sizes']
    print(f"  Database:      {sizes['database_kb']:,.2f} KB ({sizes['database_bytes']:,} bytes)")
    print(f"  WAL:           {sizes['wal_kb']:,.2f} KB ({sizes['wal_bytes']:,} bytes)")
    print(f"  SHM:           {sizes['shm_bytes']:,} bytes")
    
    print("\n" + "=" * 60)
    
    # 验收标准检查
    print("\n【Acceptance Criteria Check】")
    
    # 10000 条插入 < 5 秒
    if results['total_time_seconds'] < 5:
        print("  ✅ 10000 insertions < 5 seconds")
    else:
        print(f"  ❌ 10000 insertions too slow: {results['total_time_seconds']:.2f}s")
    
    # WAL checkpoint 后文件 < 10MB
    wal_size_kb = sizes['wal_kb']
    if wal_size_kb < 10 * 1024:  # 10MB = 10240 KB
        print("  ✅ WAL file < 10MB")
    else:
        print(f"  ⚠️  WAL file larger than 10MB: {wal_size_kb:,.2f} KB")
    
    print("=" * 60 + "\n")


def main():
    """命令行入口。"""
    parser = argparse.ArgumentParser(
        description="Run SQLite+WAL benchmark tests"
    )
    parser.add_argument(
        "--inserts",
        type=int,
        default=10000,
        help="Number of records to insert (default: 10000)"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Database file path (default: :memory:)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file path"
    )
    
    args = parser.parse_args()
    
    # 运行测试
    results = run_benchmark(inserts=args.inserts, db_path=args.db_path)
    
    # 打印结果
    print_results(results)
    
    # 输出 JSON 文件（可选）
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Results saved to: {args.output}")


if __name__ == "__main__":
    main()
