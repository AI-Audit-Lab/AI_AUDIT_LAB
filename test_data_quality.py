"""
test_data_quality.py
--------------------
Standalone test script for Data Quality Check rules.
Executes rules directly against Read-Only database without browser or web server.
"""

import sqlite3
from app.services.data_quality_service import evaluate_data_quality_rules

DB_PATH = "file:data/training_data.sqlite3?mode=ro"

def main():
    print("==================================================")
    print(" Running Data Quality Rules Standalone Test Suite")
    print("==================================================")
    
    conn = sqlite3.connect(DB_PATH, uri=True)
    try:
        res = evaluate_data_quality_rules(conn)
        assert res["status"] == "SUCCESS", f"Evaluation failed: {res}"
        assert "total_transactions" in res, "Missing total_transactions"
        assert "unmatched_account_count" in res, "Missing unmatched_account_count"
        assert "duplicate_source_ref_groups" in res, "Missing duplicate_source_ref_groups"
        assert "invalid_code_count" in res, "Missing invalid_code_count"
        assert res["expected_result"] == "UNKNOWN", "Expected result must be UNKNOWN"

        print("  [OK] Rule 1 - Total Transactions        :", res["total_transactions"])
        print("  [OK] Rule 2 - Unmatched Account IDs     :", res["unmatched_account_count"])
        print("  [OK] Rule 3 - Duplicate source_ref Groups:", res["duplicate_source_ref_groups"], f"(rows: {res['duplicate_source_ref_rows']})")
        print("  [OK] Rule 4 - Invalid Tx Codes (!DEP/WDL):", res["invalid_code_count"])
        print("  [OK] Overall Pass Rate                  :", f"{res['overall_pass_rate']}%")
        print("  [OK] Expected Result Status             :", res["expected_result"])
    finally:
        conn.close()

    print("==================================================")
    print(" [SUCCESS] Data Quality standalone test passed!")
    print("==================================================")

if __name__ == "__main__":
    main()
