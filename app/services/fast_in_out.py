"""
app/services/fast_in_out.py
---------------------------
Service module for evaluating FAST_IN_OUT_3D rule on transactions.

Rule calculation requirements:
1. Exclude CANCELLED transactions (record_status != 'CANCELLED').
2. Parameterized SQL query selecting explicit columns (no SELECT *).
3. Anchor inflows: direction = 'IN' and amount >= large_in_min (inclusive boundary).
4. Forward sliding window: [anchor_time, anchor_time + window_days].
5. Outflow calculation: sum direction = 'OUT' where transacted_at >= anchor_time within window.
   (Outflows before anchor_time are strictly EXCLUDED).
6. Trigger REVIEW when outflow_total >= inflow_amount * outflow_ratio_min (inclusive boundary).
7. Return aggregate counts and metrics only (no raw data or PII).

Results page (get_fast_in_out_flagged_windows):
- Returns paginated window-level results for flagged anchors only.
- Approved display columns: row_no, anchor_date (date only), inflow_amount,
  outflow_total, outflow_ratio. account_id and all PII fields are excluded.
- All string values from DB are returned as plain text (no HTML).
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Configurable page size for results page (rows per page)
RESULTS_PAGE_SIZE = 20

def validate_fast_in_out_params(large_in_min: float, outflow_ratio_min: float, window_days: int) -> list[str]:
    """Validate parameters for FAST_IN_OUT_3D calculation."""
    errors = []
    
    # 1. large_in_min: numeric > 0
    if not isinstance(large_in_min, (int, float)) or isinstance(large_in_min, bool):
        errors.append("กรุณาแก้ไขช่อง large_in_min: ต้องเป็นตัวเลขที่มากกว่า 0 (ได้รับค่าไม่ถูกต้อง)")
    elif large_in_min <= 0:
        errors.append("กรุณาแก้ไขช่อง large_in_min: ต้องเป็นตัวเลขที่มากกว่า 0 (ห้ามเป็น 0 หรือติดลบ)")
        
    # 2. outflow_ratio_min: numeric > 0 and <= 1.0
    if not isinstance(outflow_ratio_min, (int, float)) or isinstance(outflow_ratio_min, bool):
        errors.append("กรุณาแก้ไขช่อง outflow_ratio_min: ต้องเป็นตัวเลข")
    elif outflow_ratio_min <= 0:
        errors.append("กรุณาแก้ไขช่อง outflow_ratio_min: ต้องเป็นตัวเลขที่มากกว่า 0 (ห้ามเป็น 0 หรือติดลบ)")
    elif outflow_ratio_min > 1.0:
        errors.append("กรุณาแก้ไขช่อง outflow_ratio_min: สัดส่วนต้องไม่เกิน 100% (ไม่เกิน 1.00)")
        
    # 3. window_days: integer >= 1
    if isinstance(window_days, float) and not window_days.is_integer():
        errors.append("กรุณาแก้ไขช่อง window_days: ต้องเป็นจำนวนเต็มเท่านั้น (ห้ามป้อนทศนิยม)")
    elif not isinstance(window_days, int) or isinstance(window_days, bool):
        errors.append("กรุณาแก้ไขช่อง window_days: ต้องเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป")
    elif window_days < 1:
        errors.append("กรุณาแก้ไขช่อง window_days: ต้องเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป (ห้ามเป็น 0 หรือติดลบ)")
        
    return errors


def evaluate_fast_in_out_3d(
    conn: sqlite3.Connection,
    large_in_min: float = 500000.0,
    outflow_ratio_min: float = 0.80,
    window_days: int = 3
) -> Dict[str, Any]:
    """
    Evaluate FAST_IN_OUT_3D rule on transactions table.
    
    Args:
        conn: sqlite3 Read-Only Connection
        large_in_min: minimum inflow amount threshold (inclusive >=)
        outflow_ratio_min: minimum outflow/inflow ratio threshold (inclusive >=)
        window_days: forward sliding window duration in days

    Returns:
        Dict containing aggregate metrics, audited count, flagged REVIEW count.
    """
    params_errors = validate_fast_in_out_params(large_in_min, outflow_ratio_min, window_days)
    if params_errors:
        return {
            "status": "ERROR",
            "errors": params_errors,
            "rule_name": "FAST_IN_OUT_3D",
            "audited_count": 0,
            "flagged_count": 0,
            "expected_count": "UNKNOWN"
        }

    cursor = conn.cursor()
    # Explicit column selection and parameterized query (exclude CANCELLED)
    sql = """
        SELECT account_id, transacted_at, direction, amount, record_status
        FROM transactions
        WHERE record_status != ?
        ORDER BY account_id, transacted_at
    """
    cursor.execute(sql, ("CANCELLED",))
    rows = cursor.fetchall()

    # Group by account_id
    accounts_txs: Dict[str, list] = {}
    total_valid_tx_count = len(rows)

    for account_id, transacted_at_str, direction, amount, status in rows:
        try:
            clean_str = transacted_at_str.replace("T", " ").split(".")[0]
            dt = datetime.strptime(clean_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        accounts_txs.setdefault(account_id, []).append((dt, direction, float(amount)))

    window_delta = timedelta(days=window_days)
    total_anchor_inflows_audited = 0
    flagged_windows_count = 0
    flagged_accounts: set[str] = set()

    for account_id, txs in accounts_txs.items():
        # Find all anchor inflows where amount >= large_in_min (inclusive boundary)
        anchor_inflows = [
            (dt, amt) for (dt, dir_val, amt) in txs
            if dir_val == "IN" and amt >= large_in_min
        ]

        for anchor_dt, inflow_amt in anchor_inflows:
            total_anchor_inflows_audited += 1
            window_end = anchor_dt + window_delta

            # Sum outflows (direction == 'OUT') occurring AFTER OR AT anchor_dt within window
            # Outflows BEFORE anchor_dt (dt < anchor_dt) are EXCLUDED
            outflow_total = sum(
                amt for (dt, dir_val, amt) in txs
                if dir_val == "OUT" and anchor_dt <= dt <= window_end
            )

            target_outflow_threshold = inflow_amt * outflow_ratio_min

            # Trigger REVIEW if outflow_total >= target_outflow_threshold (inclusive boundary)
            if outflow_total >= target_outflow_threshold:
                flagged_windows_count += 1
                flagged_accounts.add(account_id)

    return {
        "status": "SUCCESS",
        "rule_name": "FAST_IN_OUT_3D",
        "parameters": {
            "large_in_min": large_in_min,
            "outflow_ratio_min": outflow_ratio_min,
            "window_days": window_days
        },
        "total_valid_transactions": total_valid_tx_count,
        "audited_count": total_anchor_inflows_audited,
        "flagged_count": flagged_windows_count,
        "flagged_accounts_count": len(flagged_accounts),
        "review_status": "REVIEW" if flagged_windows_count > 0 else "PASS",
        "expected_count": "UNKNOWN",
        "boundary_behavior": {
            "large_in_min_inclusive": True,
            "outflow_ratio_min_inclusive": True,
            "cancelled_excluded": True,
            "outflow_before_inflow_excluded": True
        }
    }


def get_fast_in_out_flagged_windows(
    conn: sqlite3.Connection,
    large_in_min: float = 500000.0,
    outflow_ratio_min: float = 0.80,
    window_days: int = 3,
    page: int = 1,
    page_size: int = RESULTS_PAGE_SIZE,
    get_all: bool = False
) -> Dict[str, Any]:
    """
    Return paginated window-level results for FAST_IN_OUT_3D flagged anchors.

    Approved display columns per result row (NO PII):
        - row_no        : sequential integer (1-based, global across pages)
        - anchor_date   : ISO date string (date only, no time) from anchor inflow
        - inflow_amount : anchor inflow amount (float)
        - outflow_total : sum of outflows within window (float)
        - outflow_ratio : outflow_total / inflow_amount rounded to 4 dp (float)

    account_id, operator_id, workstation_id are EXCLUDED (PII_BLOCKLIST).

    Args:
        conn          : sqlite3 Read-Only Connection
        large_in_min  : minimum inflow amount threshold (inclusive >=)
        outflow_ratio_min : minimum outflow/inflow ratio threshold (inclusive >=)
        window_days   : forward sliding window duration in days
        page          : 1-based page number
        page_size     : rows per page (default: RESULTS_PAGE_SIZE)
        get_all       : if True, returns all results without pagination

    Returns:
        Dict with pagination metadata and list of approved result dicts.
    """
    params_errors = validate_fast_in_out_params(large_in_min, outflow_ratio_min, window_days)
    if params_errors:
        return {
            "status": "ERROR",
            "errors": params_errors,
            "rule_name": "FAST_IN_OUT_3D",
            "results": [],
            "total_flagged": 0,
            "total_pages": 0,
            "current_page": page,
            "page_size": page_size,
        }

    if not isinstance(page, int) or page < 1:
        page = 1
    if not isinstance(page_size, int) or page_size < 1 or page_size > 200:
        page_size = RESULTS_PAGE_SIZE

    cursor = conn.cursor()
    # Explicit column selection — account_id included here only for grouping;
    # it is NEVER included in the output response.
    sql = """
        SELECT account_id, transacted_at, direction, amount
        FROM transactions
        WHERE record_status != ?
        ORDER BY account_id, transacted_at
    """
    cursor.execute(sql, ("CANCELLED",))
    rows = cursor.fetchall()

    # Group by account_id (account_id used internally only, never returned)
    accounts_txs: Dict[str, List] = {}
    for account_id, transacted_at_str, direction, amount in rows:
        try:
            clean_str = transacted_at_str.replace("T", " ").split(".")[0]
            dt = datetime.strptime(clean_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        accounts_txs.setdefault(account_id, []).append((dt, direction, float(amount)))

    window_delta = timedelta(days=window_days)
    flagged_windows: List[Dict[str, Any]] = []

    for account_id, txs in accounts_txs.items():
        anchor_inflows = [
            (dt, amt) for (dt, dir_val, amt) in txs
            if dir_val == "IN" and amt >= large_in_min
        ]
        for anchor_dt, inflow_amt in anchor_inflows:
            window_end = anchor_dt + window_delta
            outflow_total = sum(
                amt for (dt, dir_val, amt) in txs
                if dir_val == "OUT" and anchor_dt <= dt <= window_end
            )
            threshold = inflow_amt * outflow_ratio_min
            if outflow_total >= threshold:
                ratio = round(outflow_total / inflow_amt, 4) if inflow_amt > 0 else 0.0
                flagged_windows.append({
                    # account_id deliberately omitted — PII_BLOCKLIST
                    "anchor_date": anchor_dt.strftime("%Y-%m-%d"),   # date only, no time
                    "inflow_amount": round(inflow_amt, 2),
                    "outflow_total": round(outflow_total, 2),
                    "outflow_ratio": ratio,
                })

    total_flagged = len(flagged_windows)
    
    if get_all:
        page_slice = flagged_windows
        total_pages = 1
        current_page = 1
        offset = 0
    else:
        total_pages = max(1, (total_flagged + page_size - 1) // page_size)
        current_page = min(page, total_pages)
        offset = (current_page - 1) * page_size
        page_slice = flagged_windows[offset: offset + page_size]

    # Add 1-based global row_no for display
    results_with_rowno = [
        {"row_no": offset + idx + 1, **item}
        for idx, item in enumerate(page_slice)
    ]

    return {
        "status": "SUCCESS",
        "rule_name": "FAST_IN_OUT_3D",
        "parameters": {
            "large_in_min": large_in_min,
            "outflow_ratio_min": outflow_ratio_min,
            "window_days": window_days,
        },
        "total_flagged": total_flagged,
        "total_pages": total_pages,
        "current_page": current_page,
        "page_size": page_size,
        "results": results_with_rowno,
    }
