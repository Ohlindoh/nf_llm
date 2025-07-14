import os
from pathlib import Path

import duckdb
import pandas as pd

_CONN: duckdb.DuckDBPyConnection | None = None


def _get_db_path() -> Path:
    base_dir = Path(__file__).resolve().parents[1]
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "nf_llm.db"


def get_conn() -> duckdb.DuckDBPyConnection:
    """Return a singleton DuckDB connection."""
    global _CONN
    if _CONN is None:
        db_path = _get_db_path()
        try:
            _CONN = duckdb.connect(str(db_path))
            # Add WAL mode to avoid multi-process locks
            _CONN.execute("PRAGMA journal_mode=wal")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to database at {db_path}: {e}") from e
    return _CONN


def exec_sql(sql: str, params: tuple | None = None) -> None:
    """Execute a SQL statement using the global connection."""
    conn = get_conn()
    if params is not None:
        conn.execute(sql, params)
    else:
        conn.execute(sql)


def insert_dataframe(df: pd.DataFrame, table: str) -> None:
    """Insert a pandas DataFrame into a table."""
    conn = get_conn()
    conn.register("tmp", df)
    conn.execute(f"INSERT INTO {table} SELECT * FROM tmp")
    conn.unregister("tmp")
