"""
test_fast_in_out.py
-------------------
Standalone unit test suite for FAST_IN_OUT_3D rule logic.
Validates TC-01 to TC-07 scenarios as specified in implementation_plan.md.

TC-07 uses an in-memory SQLite database so that boundary behaviour
can be verified without the real training DB and without opening a browser.
"""

import sqlite3
from app.services.fast_in_out import evaluate_fast_in_out_3d, validate_fast_in_out_params
from app.services.audit_service import get_fast_in_out_summary

DB_PATH = "file:data/training_data.sqlite3?mode=ro"

def test_tc01_default_values():
    print("[TC-01] Default values (500000, 0.80, 3)...")
    errs = validate_fast_in_out_params(500000, 0.80, 3)
    assert len(errs) == 0, "Default values should pass validation"
    
    conn = sqlite3.connect(DB_PATH, uri=True)
    try:
        res = evaluate_fast_in_out_3d(conn, 500000, 0.80, 3)
        assert res["status"] == "SUCCESS"
        assert res["expected_count"] == "UNKNOWN"
        print(f"  [OK] TC-01 Passed: audited={res['audited_count']}, flagged={res['flagged_count']}")
    finally:
        conn.close()

def test_tc02_boundary_upper_lower():
    print("[TC-02] Upper/Lower Boundary values (500000, 1.0, 1)...")
    errs = validate_fast_in_out_params(500000, 1.0, 1)
    assert len(errs) == 0, "Upper/Lower boundary params should pass validation"
    
    conn = sqlite3.connect(DB_PATH, uri=True)
    try:
        res = evaluate_fast_in_out_3d(conn, 500000, 1.0, 1)
        assert res["status"] == "SUCCESS"
        print(f"  [OK] TC-02 Passed: audited={res['audited_count']}, flagged={res['flagged_count']}")
    finally:
        conn.close()

def test_tc03_boundary_inclusive_logic():
    print("[TC-03] Exact Boundary Inflow/Outflow inclusive checks...")
    conn = sqlite3.connect(DB_PATH, uri=True)
    try:
        res = evaluate_fast_in_out_3d(conn, 500000, 0.80, 3)
        assert res["boundary_behavior"]["large_in_min_inclusive"] is True
        assert res["boundary_behavior"]["outflow_ratio_min_inclusive"] is True
        assert res["boundary_behavior"]["cancelled_excluded"] is True
        assert res["boundary_behavior"]["outflow_before_inflow_excluded"] is True
        print("  [OK] TC-03 Passed: All boundary flags set to True")
    finally:
        conn.close()

def test_tc04_invalid_large_in_min():
    print("[TC-04] Invalid large_in_min (<= 0)...")
    errs1 = validate_fast_in_out_params(0, 0.80, 3)
    errs2 = validate_fast_in_out_params(-50, 0.80, 3)
    assert len(errs1) > 0, "large_in_min = 0 must fail"
    assert len(errs2) > 0, "large_in_min = -50 must fail"
    
    # Test service level validation before DB connection
    res = get_fast_in_out_summary(large_in_min=0)
    assert res["status"] == "ERROR", "Service must return ERROR and stop before DB"
    print("  [OK] TC-04 Passed: Stopped before DB access with error message")

def test_tc05_invalid_outflow_ratio_min():
    print("[TC-05] Invalid outflow_ratio_min (<= 0 or > 1.0)...")
    errs1 = validate_fast_in_out_params(500000, 0, 3)
    errs2 = validate_fast_in_out_params(500000, 1.2, 3)
    assert len(errs1) > 0, "ratio = 0 must fail"
    assert len(errs2) > 0, "ratio = 1.2 must fail"
    
    res = get_fast_in_out_summary(outflow_ratio_min=1.2)
    assert res["status"] == "ERROR", "Service must return ERROR and stop before DB"
    print("  [OK] TC-05 Passed: Stopped before DB access with error message")

def test_tc06_invalid_window_days():
    print("[TC-06] Invalid window_days (< 1 or Float)...")
    errs1 = validate_fast_in_out_params(500000, 0.80, 0)
    errs2 = validate_fast_in_out_params(500000, 0.80, 2.5) # float
    assert len(errs1) > 0, "window_days = 0 must fail"
    assert len(errs2) > 0, "window_days = 2.5 must fail"
    
    res = get_fast_in_out_summary(window_days=0)
    assert res["status"] == "ERROR", "Service must return ERROR and stop before DB"
    print("  [OK] TC-06 Passed: Stopped before DB access with error message")

# ---------------------------------------------------------------------------
# TC-07: Exact Boundary Behaviour — in-memory SQLite (no real DB required)
# ---------------------------------------------------------------------------

def _create_in_memory_db():
    """
    Build a minimal in-memory SQLite DB with a transactions table.
    Schema mirrors the real training_data.sqlite3 (only columns used by the rule).
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE transactions (
            account_id    TEXT,
            transacted_at TEXT,
            direction     TEXT,
            amount        REAL,
            record_status TEXT
        )
    """)
    return conn


def test_tc07_exact_boundary_in_memory():
    """
    TC-07: Boundary behaviour verified with in-memory SQLite.

    Test parameters: large_in_min=500000, outflow_ratio_min=0.80, window_days=3

    Scenarios embedded in the dataset
    ----------------------------------
    ACC-A  : 1 inflow at EXACTLY 500000 (must be included as anchor),
             1 outflow of 400000 at anchor_time (= 500000 * 0.80, exact boundary) → REVIEW

    ACC-B  : 1 inflow at 499999 (just below large_in_min) → must NOT be an anchor (audited_count unchanged)

    ACC-C  : 1 inflow at 600000 (valid anchor)
             1 outflow of 200000 at anchor_time - 1 sec (BEFORE anchor) → must NOT be summed
             Expected: outflow_total = 0 < threshold → no REVIEW for this window

    ACC-D  : 1 inflow at CANCELLED status → must be excluded from everything
             1 outflow at CANCELLED status → must be excluded
    """
    print("[TC-07] Exact Boundary — in-memory SQLite...")

    LARGE_IN_MIN = 500000.0
    OUTFLOW_RATIO_MIN = 0.80
    WINDOW_DAYS = 3

    conn = _create_in_memory_db()

    rows = [
        # ACC-A: inflow at exact boundary + outflow at exact ratio boundary
        ("ACC-A", "2024-01-10 10:00:00", "IN",  500000.0, "NORMAL"),
        ("ACC-A", "2024-01-10 12:00:00", "OUT", 400000.0, "NORMAL"),   # 500000 * 0.80 = 400000

        # ACC-B: inflow just below large_in_min — must NOT become an anchor
        ("ACC-B", "2024-01-10 10:00:00", "IN",  499999.0, "NORMAL"),

        # ACC-C: outflow BEFORE anchor_time — must NOT be included in window sum
        ("ACC-C", "2024-01-10 10:00:00", "IN",  600000.0, "NORMAL"),
        ("ACC-C", "2024-01-10 09:59:59", "OUT", 200000.0, "NORMAL"),   # 1 second before anchor

        # ACC-D: CANCELLED rows — must be excluded entirely
        ("ACC-D", "2024-01-10 10:00:00", "IN",  900000.0, "CANCELLED"),
        ("ACC-D", "2024-01-10 11:00:00", "OUT", 800000.0, "CANCELLED"),
    ]
    conn.executemany(
        "INSERT INTO transactions (account_id, transacted_at, direction, amount, record_status) VALUES (?,?,?,?,?)",
        rows
    )
    conn.commit()

    res = evaluate_fast_in_out_3d(
        conn,
        large_in_min=LARGE_IN_MIN,
        outflow_ratio_min=OUTFLOW_RATIO_MIN,
        window_days=WINDOW_DAYS
    )
    conn.close()

    assert res["status"] == "SUCCESS", f"Expected SUCCESS, got: {res['status']}"

    # TC-07a: ACC-A inflow at exactly large_in_min must be audited (boundary inclusive)
    # ACC-B inflow at 499999 must NOT add an anchor
    # ACC-C inflow at 600000 is a valid anchor
    # ACC-D rows are CANCELLED → excluded
    # Valid anchors: ACC-A (1) + ACC-C (1) = 2
    assert res["audited_count"] == 2, (
        f"TC-07a FAILED: audited_count should be 2 (ACC-A + ACC-C), got {res['audited_count']}. "
        f"Check that inflow at large_in_min is included and inflow below is excluded."
    )
    print("  [OK] TC-07a: inflow at exact large_in_min is included (audited_count=2)")

    # TC-07b: ACC-A outflow = 500000 * 0.80 = 400000 (exact threshold) must trigger REVIEW
    # ACC-C outflow is before anchor → outflow_total = 0 < threshold → no REVIEW
    # At least 1 flagged window (ACC-A), ACC-C must NOT be flagged
    assert res["flagged_count"] >= 1, (
        f"TC-07b FAILED: flagged_count should be >= 1 (ACC-A hits exact ratio boundary), got {res['flagged_count']}"
    )
    print(f"  [OK] TC-07b: outflow at exact ratio boundary triggers REVIEW (flagged_count={res['flagged_count']})")

    # TC-07c: CANCELLED rows (ACC-D) must not contribute to valid transaction count
    # total_valid_transactions counts only non-CANCELLED rows = ACC-A(2) + ACC-B(1) + ACC-C(2) = 5
    assert res["total_valid_transactions"] == 5, (
        f"TC-07c FAILED: total_valid_transactions should be 5 (CANCELLED excluded), got {res['total_valid_transactions']}"
    )
    print(f"  [OK] TC-07c: CANCELLED transactions excluded (total_valid_transactions=5)")

    # TC-07d: ACC-C outflow is 1 second BEFORE anchor → must not be summed → ACC-C not flagged
    # If ACC-C were incorrectly included, flagged_count would be 2; it must remain 1
    assert res["flagged_count"] == 1, (
        f"TC-07d FAILED: flagged_count should be 1 (ACC-C outflow is before anchor, excluded), got {res['flagged_count']}"
    )
    print("  [OK] TC-07d: outflow before anchor_time is excluded (ACC-C not flagged)")

    print(f"  [OK] TC-07 All boundary assertions passed. audited={res['audited_count']}, flagged={res['flagged_count']}")


def main():
    print("==================================================")
    print(" Running FAST_IN_OUT_3D Test Cases (TC-01..TC-07)")
    print("==================================================")
    test_tc01_default_values()
    test_tc02_boundary_upper_lower()
    test_tc03_boundary_inclusive_logic()
    test_tc04_invalid_large_in_min()
    test_tc05_invalid_outflow_ratio_min()
    test_tc06_invalid_window_days()
    test_tc07_exact_boundary_in_memory()
    print("==================================================")
    print(" [SUCCESS] All 7 Test Cases passed cleanly!")
    print("==================================================")

if __name__ == "__main__":
    main()
