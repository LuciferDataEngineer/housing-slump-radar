"""Stream a small replay of published observations through Redpanda into ClickHouse.

The events are copies of figures already in the tidy tables. They are not a live market feed.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

from kafka import KafkaProducer
from kafka.errors import KafkaError

from housing_radar.prepare import load_cash_rate, load_mean_prices

TOPIC = "housing.events"
BOOTSTRAP = os.environ.get("REDPANDA_BROKERS", "127.0.0.1:9092")
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "radar")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "radar")
CLICKHOUSE = (
    f"http://localhost:8123/?user={CLICKHOUSE_USER}&password={CLICKHOUSE_PASSWORD}"
)


def _wait_http(url: str, attempts: int = 30) -> None:
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {url}")


def _clickhouse(query: str) -> str:
    request = urllib.request.Request(CLICKHOUSE, data=query.encode(), method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode()


def sample_events() -> list[dict]:
    """A short replay: the latest cash rate and the latest mean price in each state."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    cash = load_cash_rate()[-1]
    events = [
        {
            "event_time": now,
            "domain": "credit",
            "series": "cash_rate_target",
            "period": cash["date"].isoformat(),
            "value": float(cash["target"]),
            "unit": "percent",
            "source": "RBA F1 replay",
        }
    ]
    latest_quarter = max(row["quarter"] for row in load_mean_prices())
    for row in load_mean_prices():
        if row["quarter"] != latest_quarter:
            continue
        events.append(
            {
                "event_time": now,
                "domain": "prices",
                "series": f"mean_price_{row['region_code']}",
                "period": row["quarter"],
                "value": float(row["mean_price_aud"]),
                "unit": "aud",
                "source": "ABS RES_DWELL_ST replay",
            }
        )
    return events


def ensure_tables() -> None:
    statements = [
        "CREATE DATABASE IF NOT EXISTS housing",
        """
        CREATE TABLE IF NOT EXISTS housing.events (
            event_time DateTime,
            domain String,
            series String,
            period String,
            value Float64,
            unit String,
            source String
        ) ENGINE = MergeTree
        ORDER BY (domain, series, period, event_time)
        """,
        """
        CREATE TABLE IF NOT EXISTS housing.events_kafka (
            event_time DateTime,
            domain String,
            series String,
            period String,
            value Float64,
            unit String,
            source String
        ) ENGINE = Kafka
        SETTINGS
            kafka_broker_list = '127.0.0.1:9092',
            kafka_topic_list = 'housing.events',
            kafka_group_name = 'housing_slump_radar',
            kafka_format = 'JSONEachRow',
            kafka_num_consumers = 1
        """,
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS housing.events_mv
        TO housing.events AS
        SELECT * FROM housing.events_kafka
        """,
    ]
    for statement in statements:
        _clickhouse(statement)


def main() -> None:
    _wait_http("http://localhost:8123/ping")
    producer = None
    for _ in range(30):
        try:
            producer = KafkaProducer(bootstrap_servers=BOOTSTRAP)
            break
        except (KafkaError, OSError):
            time.sleep(1)
    if producer is None:
        raise RuntimeError("Redpanda is not accepting connections on localhost:19092")
    ensure_tables()
    events = sample_events()
    for event in events:
        producer.send(TOPIC, json.dumps(event).encode())
    producer.flush()
    producer.close()
    deadline = time.time() + 40
    count = "0"
    while time.time() < deadline:
        count = _clickhouse("SELECT count() FROM housing.events FORMAT TabSeparated").strip()
        if int(count) >= len(events):
            break
        time.sleep(1)
    print(_clickhouse(
        "SELECT domain, count() AS events, round(avg(value), 1) AS avg_value "
        "FROM housing.events GROUP BY domain ORDER BY domain FORMAT PrettyCompact"
    ))
    if int(count) < len(events):
        raise RuntimeError(f"ClickHouse has {count} events; sent {len(events)}")
    print(f"Streamed {len(events)} published observations into ClickHouse")


if __name__ == "__main__":
    main()
