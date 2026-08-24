"""SQLite persistence layer and SQL-based test execution.

The project demonstrates *both* approaches an audit D&A team uses:

* Python/pandas tests (``je_tests.py``) for flexible, in-memory analysis.
* Pure-SQL tests (``sql/je_tests.sql``) that can run directly against a client
  database (SQL Server, Oracle, etc.). SQLite is used here as a zero-install
  stand-in so the project runs anywhere.

The SQL in ``sql/`` is written in portable ANSI-style SQL and is commented to
explain how each query would map to a real audit test.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict

import pandas as pd

from .config_loader import PROJECT_ROOT, resolve_path

SQL_DIR = PROJECT_ROOT / "sql"


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Open (creating if needed) a SQLite connection."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def load_dataframe(conn: sqlite3.Connection, df: pd.DataFrame,
                   table: str = "journal_entries") -> None:
    """Create the schema and load a DataFrame into the database."""
    schema_sql = (SQL_DIR / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    df.to_sql(table, conn, if_exists="replace", index=False)
    conn.commit()


def load_csv_to_db(csv_path: str | Path, db_path: str | Path) -> int:
    """Load the raw CSV into SQLite. Returns the number of rows loaded."""
    df = pd.read_csv(csv_path)
    conn = get_connection(db_path)
    try:
        load_dataframe(conn, df)
    finally:
        conn.close()
    return len(df)


def run_sql_tests(db_path: str | Path) -> pd.DataFrame:
    """Execute the SQL audit tests and return their combined findings.

    The SQL file ``sql/je_tests.sql`` defines a series of named SELECT
    statements, each producing ``entry_id``, ``test_name`` and ``detail``
    columns. They are concatenated with UNION ALL so a single query returns all
    findings.
    """
    sql = (SQL_DIR / "je_tests.sql").read_text(encoding="utf-8")
    conn = get_connection(db_path)
    try:
        findings = pd.read_sql_query(sql, conn)
    finally:
        conn.close()
    return findings


def query(db_path: str | Path, sql: str) -> pd.DataFrame:
    """Run an arbitrary read-only query (handy for notebooks / debugging)."""
    conn = get_connection(db_path)
    try:
        return pd.read_sql_query(sql, conn)
    finally:
        conn.close()
