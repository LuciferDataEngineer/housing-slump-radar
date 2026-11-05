"""Compare DuckDB and local ClickHouse on one synthetic scan.

The rows are generated. They are not official prices. ClickHouse is queried
through the HTTP interface on localhost, and server time is read back from
system.query_log so the container startup is not counted as query time.
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import time
import urllib.request
from pathlib import Path

import duckdb

ROWS = 2_000_000
DUCK_QUERY = """
select state_id, count(*) as n, median(price) as median_price, avg(yoy) as avg_yoy
from bench_synthetic
group by state_id
order by state_id
"""
CLICKHOUSE_QUERY = """
select state_id, count(*) as n, median(price) as median_price, avg(yoy) as avg_yoy
from bench.synthetic
group by state_id
order by state_id
"""


def _clickhouse(query: str) -> str:
    user = os.environ.get("CLICKHOUSE_USER", "radar")
    password = os.environ.get("CLICKHOUSE_PASSWORD", "radar")
    request = urllib.request.Request(
        f"http://localhost:8123/?user={user}&password={password}",
        data=query.encode(),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode()


def _time_calls(action, repeats: int = 7) -> list[float]:
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        action()
        samples.append((time.perf_counter() - started) * 1000)
    return samples


def _median_tail(samples: list[float]) -> float:
    return round(statistics.median(samples[2:]), 2)


def main() -> None:
    machine = {
        "python": platform.python_version(),
        "system": platform.platform(),
        "processor": platform.processor(),
    }
    connection = duckdb.connect()
    connection.execute(
        f"""
        create table bench_synthetic as
        select
            (i % 8)::integer as state_id,
            (400000 + (i % 1700000))::double as price,
            (((i % 100) - 50) / 100.0)::double as yoy
        from range({ROWS}) t(i)
        """
    )
    duck_samples = _time_calls(lambda: connection.execute(DUCK_QUERY).fetchall())
    _clickhouse("CREATE DATABASE IF NOT EXISTS bench")
    _clickhouse("DROP TABLE IF EXISTS bench.synthetic")
    _clickhouse(
        """
        CREATE TABLE bench.synthetic (
            state_id UInt8,
            price Float64,
            yoy Float64
        ) ENGINE = MergeTree ORDER BY state_id
        """
    )
    connection.execute("copy bench_synthetic to '/tmp/hsr-bench.csv' (header false)")
    with Path("/tmp/hsr-bench.csv").open("rb") as handle:
        payload = handle.read()
    user = os.environ.get("CLICKHOUSE_USER", "radar")
    password = os.environ.get("CLICKHOUSE_PASSWORD", "radar")
    request = urllib.request.Request(
        "http://localhost:8123/?query=INSERT%20INTO%20bench.synthetic%20FORMAT%20CSV"
        f"&user={user}&password={password}",
        data=payload,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180):
        pass

    def run_clickhouse() -> None:
        _clickhouse(CLICKHOUSE_QUERY + " FORMAT Null")

    client_samples = _time_calls(run_clickhouse)
    _clickhouse("SYSTEM FLUSH LOGS")
    log_rows = _clickhouse(
        """
        SELECT query_duration_ms
        FROM system.query_log
        WHERE type = 'QueryFinish'
          AND query LIKE '%bench.synthetic%'
          AND query LIKE '%FORMAT Null%'
        ORDER BY event_time_microseconds DESC
        LIMIT 5
        FORMAT TabSeparated
        """
    )
    server_samples = [float(line) for line in log_rows.splitlines() if line.strip()]
    result = {
        "rows": ROWS,
        "query": "group by state_id with count, median(price), avg(yoy)",
        "data": "synthetic, generated in DuckDB, not official prices",
        "machine": machine,
        "duckdb_in_process_ms": {"samples_ms": [round(item, 2) for item in duck_samples], "median_excluding_warmup": _median_tail(duck_samples)},
        "clickhouse_http_client_ms": {
            "samples_ms": [round(item, 2) for item in client_samples],
            "median_excluding_warmup": _median_tail(client_samples),
        },
        "clickhouse_server_ms": {
            "samples_ms": server_samples,
            "median": round(statistics.median(server_samples), 2) if server_samples else None,
        },
        "cost_aud": 0,
        "note": "Both engines ran on this machine. DuckDB time is in-process. ClickHouse server time excludes the HTTP client. There is no cloud bill.",
    }
    destination = Path(__file__).resolve().parents[2] / "documentation" / "bench-results.json"
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(destination.read_text())


if __name__ == "__main__":
    main()
