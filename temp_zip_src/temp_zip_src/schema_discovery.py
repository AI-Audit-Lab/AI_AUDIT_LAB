"""
schema_discovery.py
-------------------
Purpose : Explore the structure of a SQLite database and produce a
          schema report (JSON) for use in downstream AI-assisted analysis.

Safety guarantees:
  - Opens the database in READ-ONLY mode (URI mode, ?mode=ro).
  - Never executes SELECT * or reads row-level data.
  - Only aggregate statistics (COUNT, COUNT(DISTINCT)) are computed.
  - No sample values or raw text are included in the output.
  - Flags column names that may contain PII for human review.

Output  : output/schema_report.json
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration — change these without touching the core logic
# ---------------------------------------------------------------------------

DB_PATH = Path("data/training_data.sqlite3")
OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / "schema_report.json"

# Keywords that suggest a column may hold PII or sensitive data.
# This list is intentionally broad; false positives are acceptable here
# because the purpose is to prompt human review, not to block execution.
PII_KEYWORDS = [
    "name", "email", "phone", "mobile", "address", "postcode", "zipcode",
    "dob", "birth", "age", "gender", "sex", "national", "passport", "ssn",
    "tax", "nid", "cid", "citizen", "id_card", "salary", "income", "wage",
    "password", "passwd", "secret", "token", "credential", "pin",
    "account", "card", "bank", "iban", "swift",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flag_pii(column_name: str) -> bool:
    """Return True if the column name matches any PII keyword."""
    lower = column_name.lower()
    return any(kw in lower for kw in PII_KEYWORDS)


def _open_readonly(db_path: Path) -> sqlite3.Connection:
    """
    Open a SQLite database in read-only mode using the URI interface.
    Raises FileNotFoundError if the file does not exist.
    """
    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found: {db_path}\n"
            "Please verify the path relative to the project root."
        )
    # Relative URI — complies with Path Portability rules (PROJECT_RULES §4).
    # SQLite resolves relative file: URIs from the current working directory.
    conn = sqlite3.connect(
        "file:data/training_data.sqlite3?mode=ro",
        uri=True
    )
    conn.row_factory = sqlite3.Row
    return conn


def _get_table_names(conn: sqlite3.Connection) -> list[str]:
    """Return all user-defined table names (excludes SQLite internal tables)."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    )
    return [row["name"] for row in cur.fetchall()]


def _get_columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    """
    Return column metadata using PRAGMA table_info.
    Fields returned: cid, name, type, notnull, dflt_value, pk.
    """
    cur = conn.execute(f"PRAGMA table_info({table})")  # noqa: S608 – safe, no user input
    return [dict(row) for row in cur.fetchall()]


def _get_foreign_keys(conn: sqlite3.Connection, table: str) -> list[dict]:
    """Return foreign key definitions using PRAGMA foreign_key_list."""
    cur = conn.execute(f"PRAGMA foreign_key_list({table})")  # noqa: S608
    return [dict(row) for row in cur.fetchall()]


def _get_row_count(conn: sqlite3.Connection, table: str) -> int:
    """Return the total number of rows in a table."""
    cur = conn.execute(f"SELECT COUNT(*) AS cnt FROM \"{table}\"")  # noqa: S608
    return cur.fetchone()["cnt"]


def _get_column_stats(
    conn: sqlite3.Connection, table: str, column: str, row_count: int
) -> dict:
    """
    Compute null_count and distinct_count for a single column.
    No row values are retrieved — only aggregate counts.
    """
    col_q = f'"{column}"'   # Quote column name to handle reserved words / spaces
    tbl_q = f'"{table}"'

    null_cur = conn.execute(
        f"SELECT COUNT(*) - COUNT({col_q}) AS null_cnt FROM {tbl_q}"  # noqa: S608
    )
    null_count = null_cur.fetchone()["null_cnt"]

    distinct_cur = conn.execute(
        f"SELECT COUNT(DISTINCT {col_q}) AS dist_cnt FROM {tbl_q}"  # noqa: S608
    )
    distinct_count = distinct_cur.fetchone()["dist_cnt"]

    return {
        "null_count": null_count,
        "null_pct": round(null_count / row_count * 100, 2) if row_count > 0 else None,
        "distinct_count": distinct_count,
    }


# ---------------------------------------------------------------------------
# Core discovery
# ---------------------------------------------------------------------------

def discover_schema(db_path: Path) -> dict:
    """
    Open the database read-only and collect schema + aggregate statistics.
    Returns a dict ready for JSON serialisation.
    No row-level data is accessed.
    """
    conn = _open_readonly(db_path)
    pii_warnings: list[str] = []
    tables_report: list[dict] = []

    try:
        table_names = _get_table_names(conn)

        for table in table_names:
            columns_meta = _get_columns(conn, table)
            foreign_keys = _get_foreign_keys(conn, table)
            row_count = _get_row_count(conn, table)

            columns_report: list[dict] = []
            for col in columns_meta:
                col_name: str = col["name"]
                is_pii = _flag_pii(col_name)
                if is_pii:
                    pii_warnings.append(f"{table}.{col_name}")

                stats = _get_column_stats(conn, table, col_name, row_count)

                columns_report.append({
                    "name": col_name,
                    "type": col["type"] or "UNKNOWN",
                    "is_primary_key": bool(col["pk"]),
                    "not_null_constraint": bool(col["notnull"]),
                    "default_value": col["dflt_value"],   # metadata only, not data
                    "null_count": stats["null_count"],
                    "null_pct": stats["null_pct"],
                    "distinct_count": stats["distinct_count"],
                    "pii_flag": is_pii,
                })

            fk_report = [
                {
                    "column": fk["from"],
                    "references_table": fk["table"],
                    "references_column": fk["to"],
                }
                for fk in foreign_keys
            ]

            tables_report.append({
                "table_name": table,
                "row_count": row_count,
                "column_count": len(columns_report),
                "columns": columns_report,
                "foreign_keys": fk_report,
            })

    finally:
        conn.close()

    return {
        "database": str(db_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "table_count": len(tables_report),
        "tables": tables_report,
        "pii_warnings": pii_warnings,
        "notes": (
            "This report contains schema metadata and aggregate statistics only. "
            "No row-level data was accessed or stored. "
            "Columns listed under 'pii_warnings' have names that may indicate "
            "personally identifiable or sensitive information — please review "
            "before sharing this report externally."
        ),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("schema_discovery.py - SQLite Schema Report")
    print("=" * 60)
    print(f"  Database : {DB_PATH}")
    print(f"  Output   : {OUTPUT_FILE}")
    print(f"  Mode     : READ-ONLY | No row data accessed")
    print("=" * 60)

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/2] Discovering schema and computing aggregate statistics ...")
    report = discover_schema(DB_PATH)

    print("[2/2] Writing report ...")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


    # -----------------------------------------------------------------------
    # Summary printed to console (no raw data — counts and names only)
    # -----------------------------------------------------------------------
    print("\n--- Summary ---")
    print(f"  Tables found : {report['table_count']}")
    for t in report["tables"]:
        print(f"    * {t['table_name']:30s}  rows={t['row_count']:>10,}  cols={t['column_count']}")

    if report["pii_warnings"]:
        print("\n[!] PII WARNING -- columns with potentially sensitive names detected:")
        for w in report["pii_warnings"]:
            print(f"    * {w}")
        print("  -> Please review before sharing the schema report externally.")
    else:
        print("\n[OK] No obvious PII-named columns detected.")

    print(f"\n[OK] Report saved to: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
