"""Run the repository's named SQL examples against a read-only SQLite connection."""
import argparse
import json
import re
import sqlite3
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sql = (Path(__file__).resolve().parents[1] / "sql/analysis.sql").read_text()
    results = {}
    connection = sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        for statement in sql.split(";"):
            name = re.search(r"^-- name: (\w+)$", statement, re.MULTILINE)
            if name:
                results[name.group(1)] = [dict(row) for row in connection.execute(statement)]
    finally:
        connection.close()
    output = json.dumps(results, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
