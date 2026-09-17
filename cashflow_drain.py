"""
cashflow_drain.py
-----------------
Purpose : Detect accounts that received large inflows and then drained most
          of the balance within a short sliding window (Cash Flow Drain pattern).

Usage:
    python cashflow_drain.py [--large_in_min N] [--outflow_ratio_min R] [--window_days D]

Parameters:
    --large_in_min      Minimum total inflow (DEP) within a window to flag.
                        Must be > 0. Default: 500000
    --outflow_ratio_min Minimum ratio (outflow / inflow) to flag.
                        Must be > 0 and <= 1.0. Default: 0.80
    --window_days       Number of days in the forward sliding window starting
                        from each DEP anchor. Must be integer >= 1. Default: 3

Safety guarantees:
    - Parameters are validated BEFORE the database is opened.
    - Database is opened in READ-ONLY mode (URI ?mode=ro).
    - SQL uses parameterized queries — no user input is concatenated into SQL.
    - Output contains aggregate counts only (no account_id, operator_id, or PII).
    - Results are saved to output/cashflow_drain_report.json.

Assumption:
    Sliding window = [anchor_date, anchor_date + window_days] (forward from DEP).
    All values equal to a threshold boundary ARE included in the check (inclusive).
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Constants — change here without touching core logic (PROJECT_RULES §4)
# ---------------------------------------------------------------------------

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB  = os.path.join(BASE_DIR, "data", "training_data.sqlite3").replace("\\", "/")
DB_PATH     = os.environ.get("AUDIT_DB_PATH", f"file:{DEFAULT_DB}?mode=ro")   # Read-Only
OUTPUT_DIR  = os.path.join(BASE_DIR, "output")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "cashflow_drain_report.json")

# Default threshold values — separated from logic so they are easy to change
DEFAULT_LARGE_IN_MIN      = 500_000   # baht; must be > 0
DEFAULT_OUTFLOW_RATIO_MIN = 0.80      # ratio; must be > 0 and <= 1.0
DEFAULT_WINDOW_DAYS       = 3         # integer; must be >= 1

# Direction values from DB diagnostic (Overrides H-1 assumption)
DIR_INFLOW  = "IN"
DIR_OUTFLOW = "OUT"

# ---------------------------------------------------------------------------
# Section 2: Parameter Validation (must run BEFORE any DB access)
# ---------------------------------------------------------------------------

def validate_params(large_in_min, outflow_ratio_min, window_days):
    """
    Validate all three threshold parameters.

    Returns a list of human-readable error strings.
    An empty list means all parameters are valid.
    Error messages do NOT reveal DB paths, secrets, or internal details.
    """
    errors = []

    # large_in_min: numeric, must be > 0
    if not isinstance(large_in_min, (int, float)) or isinstance(large_in_min, bool):
        errors.append(
            f"[ERROR] large_in_min ต้องเป็นตัวเลขที่มากกว่า 0 (ได้รับ: {large_in_min!r})"
        )
    elif large_in_min <= 0:
        errors.append(
            f"[ERROR] large_in_min ต้องมากกว่า 0 (ได้รับ: {large_in_min})"
        )

    # outflow_ratio_min: numeric, must be > 0 and <= 1.0
    if not isinstance(outflow_ratio_min, (int, float)) or isinstance(outflow_ratio_min, bool):
        errors.append(
            f"[ERROR] outflow_ratio_min ต้องเป็นตัวเลขที่มากกว่า 0 และไม่เกิน 1.0 (ได้รับ: {outflow_ratio_min!r})"
        )
    elif not (0 < outflow_ratio_min <= 1.0):
        errors.append(
            f"[ERROR] outflow_ratio_min ต้องมากกว่า 0 และไม่เกิน 1.0 (ได้รับ: {outflow_ratio_min})"
        )

    # window_days: must be a true integer (not float like 2.5), >= 1
    if not isinstance(window_days, int) or isinstance(window_days, bool):
        errors.append(
            f"[ERROR] window_days ต้องเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป (ได้รับ: {window_days!r})"
        )
    elif window_days < 1:
        errors.append(
            f"[ERROR] window_days ต้องเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป (ได้รับ: {window_days})"
        )

    return errors

# ---------------------------------------------------------------------------
# Section 3: Database Connection (opened ONLY after validation passes)
# ---------------------------------------------------------------------------

def get_connection():
    """
    Open the training database in strict READ-ONLY mode.
    Uses SQLite URI interface with ?mode=ro to prevent any writes.
    """
    return sqlite3.connect(DB_PATH, uri=True)

# ---------------------------------------------------------------------------
# Section 4: Cash Flow Drain Analysis
# ---------------------------------------------------------------------------

def run_cashflow_drain(conn, large_in_min, outflow_ratio_min, window_days):
    """
    Detect Cash Flow Drain windows using a forward sliding window.

    Assumption:
        For each DEP transaction on anchor_date, the window covers
        [anchor_date, anchor_date + window_days] (inclusive on both ends).

    Parameters confirmed by Human (H-1, H-2, H-3, H-4):
        - direction 'DEP' = inflow, 'WDL' = outflow
        - transaction_code 3rd value: included via direction column
        - Sliding window (overlapping windows possible per account)
        - All matching windows are reported (a single account may appear multiple times)

    Output: aggregate counts only — no account_id or PII is returned.

    Args:
        conn              : sqlite3 Connection (read-only)
        large_in_min      : float  — minimum inflow threshold (inclusive)
        outflow_ratio_min : float  — minimum outflow/inflow ratio (inclusive)
        window_days       : int    — forward window length in days

    Returns:
        dict with flagged_windows_count and flagged_accounts_count
    """
    cursor = conn.cursor()

    # Parameterized query — record_status value is passed as a bound parameter,
    # never concatenated into the SQL string.
    # Only the 4 columns needed for the analysis are selected (no SELECT *).
    SQL = """
        SELECT account_id, transacted_at, direction, amount
        FROM   transactions
        WHERE  record_status = ?
        ORDER  BY account_id, transacted_at
    """
    cursor.execute(SQL, ("NORMAL",))
    rows = cursor.fetchall()

    # --- Group rows by account_id ---
    # Structure: { account_id: [(datetime, direction, amount), ...] }
    accounts: dict[str, list] = {}
    for account_id, transacted_at_str, direction, amount in rows:
        try:
            clean = transacted_at_str.replace("T", " ").split(".")[0]
            dt = datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue  # skip rows with unparseable timestamps
        accounts.setdefault(account_id, []).append((dt, direction, float(amount)))

    # --- Sliding window analysis ---
    # Assumption: window = [anchor_date, anchor_date + window_days] forward.
    # Boundary values are included (>=, <=).
    window_delta = timedelta(days=window_days)

    flagged_windows_count = 0
    flagged_account_ids: set[str] = set()  # kept only for counting distinct accounts

    for account_id, txs in accounts.items():
        # Find all DEP transactions that could be anchors
        dep_txs = [(dt, amt) for (dt, direction, amt) in txs if direction == DIR_INFLOW]

        for anchor_dt, _ in dep_txs:
            window_end = anchor_dt + window_delta

            # Aggregate inflows and outflows within this account's window
            total_in  = sum(
                amt for (dt, direction, amt) in txs
                if direction == DIR_INFLOW and anchor_dt <= dt <= window_end
            )
            total_out = sum(
                amt for (dt, direction, amt) in txs
                if direction == DIR_OUTFLOW and anchor_dt <= dt <= window_end
            )

            # Apply thresholds — both boundaries are inclusive (>=)
            if total_in <= 0:
                continue
            if total_in >= large_in_min and (total_out / total_in) >= outflow_ratio_min:
                flagged_windows_count += 1
                flagged_account_ids.add(account_id)   # used only for count

    return {
        "flagged_windows_count":  flagged_windows_count,
        "flagged_accounts_count": len(flagged_account_ids),
    }

# ---------------------------------------------------------------------------
# Section 5: Save Report (Aggregate Only — no PII)
# ---------------------------------------------------------------------------

def save_report(result, params):
    """
    Persist the aggregate result to output/cashflow_drain_report.json.
    The report contains NO account_id, transaction_id, operator_id, or raw rows.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "parameters": {
            "large_in_min":      params["large_in_min"],
            "outflow_ratio_min": params["outflow_ratio_min"],
            "window_days":       params["window_days"],
            "window_direction":  "forward_from_anchor",
        },
        "assumption": (
            "Window covers [anchor_date, anchor_date + window_days] starting from each "
            "DEP transaction. Boundary values are inclusive. All matching windows are "
            "reported; a single account may contribute more than one flagged window."
        ),
        "results": {
            "flagged_windows_count":  result["flagged_windows_count"],
            "flagged_accounts_count": result["flagged_accounts_count"],
        },
        "data_filter": "record_status = 'NORMAL' only",
        "pii_note":    "This report contains aggregate counts only. No account_id, "
                       "transaction_id, operator_id, or other PII is included.",
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

# ---------------------------------------------------------------------------
# Section 6: CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Cash Flow Drain Detection — aggregate analysis on training database."
    )
    parser.add_argument(
        "--large_in_min",
        type=float,
        default=DEFAULT_LARGE_IN_MIN,
        help=(
            f"Minimum total inflow (DEP) within a window to flag (must be > 0). "
            f"Default: {DEFAULT_LARGE_IN_MIN:,}"
        ),
    )
    parser.add_argument(
        "--outflow_ratio_min",
        type=float,
        default=DEFAULT_OUTFLOW_RATIO_MIN,
        help=(
            f"Minimum outflow/inflow ratio to flag (must be > 0 and <= 1.0). "
            f"Default: {DEFAULT_OUTFLOW_RATIO_MIN}"
        ),
    )
    parser.add_argument(
        "--window_days",
        type=int,
        default=DEFAULT_WINDOW_DAYS,
        help=(
            f"Forward sliding window in days from each DEP anchor (integer >= 1). "
            f"Default: {DEFAULT_WINDOW_DAYS}"
        ),
    )

    args = parser.parse_args()

    # Collect resolved parameter values
    params = {
        "large_in_min":      args.large_in_min,
        "outflow_ratio_min": args.outflow_ratio_min,
        "window_days":       args.window_days,
    }

    print("=" * 56)
    print("  Cash Flow Drain Detection")
    print("=" * 56)
    print(f"  large_in_min      : {params['large_in_min']:>15,.2f} บาท")
    print(f"  outflow_ratio_min : {params['outflow_ratio_min'] * 100:>14.1f}%")
    print(f"  window_days       : {params['window_days']:>14} วัน")
    print("=" * 56)

    # --- Step 1: Validate BEFORE opening the database ---
    print("[INFO] Validating parameters...")
    errors = validate_params(
        params["large_in_min"],
        params["outflow_ratio_min"],
        params["window_days"],
    )
    if errors:
        for msg in errors:
            print(msg)
        print("[STOP] พารามิเตอร์ไม่ถูกต้อง — ยกเลิกก่อนเปิดฐานข้อมูล")
        sys.exit(1)
    print("[OK]   Parameters validated.")

    # --- Step 2: Open DB (read-only) and run analysis ---
    print("[INFO] Connecting to database (read-only)...")
    conn = get_connection()
    try:
        print("[INFO] Running Cash Flow Drain analysis...")
        result = run_cashflow_drain(
            conn,
            params["large_in_min"],
            params["outflow_ratio_min"],
            params["window_days"],
        )
    finally:
        conn.close()

    # --- Step 3: Save and display results ---
    save_report(result, params)

    print("[OK]   Analysis complete.")
    print()
    print("--- Results (Aggregate Only) ---")
    print(f"  Windows ที่ตรงเงื่อนไข : {result['flagged_windows_count']}")
    print(f"  บัญชีที่พบ (distinct)   : {result['flagged_accounts_count']}")
    print()
    print(f"[SUCCESS] Report saved to: {OUTPUT_FILE}")
    print("=" * 56)


if __name__ == "__main__":
    main()
