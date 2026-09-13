import os
import duckdb

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data").replace("\\", "/")


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(f"CREATE VIEW sessions AS SELECT * FROM read_json_auto('{DATA_DIR}/sessions.jsonl.gz')")
    con.execute(f"CREATE VIEW steps AS SELECT * FROM read_json_auto('{DATA_DIR}/agent_steps.jsonl.gz')")
    con.execute(f"CREATE VIEW turns AS SELECT * FROM read_json_auto('{DATA_DIR}/turns.jsonl.gz')")
    con.execute(f"CREATE VIEW config_timeline AS SELECT * FROM read_csv_auto('{DATA_DIR}/config_timeline.csv')")
    return con


if __name__ == "__main__":
    con = connect()
    print(con.execute("SELECT COUNT(*) FROM sessions").fetchone())
    print(con.execute("SELECT COUNT(*) FROM steps").fetchone())
    print(con.execute("SELECT COUNT(*) FROM turns").fetchone())
    print(con.execute("SELECT * FROM config_timeline LIMIT 3").fetchdf())
