"""
app/services/data_quality_service.py
------------------------------------
Service layer module for Data Quality Check rules on transactions table.

Rules:
1. Rule 1 (Total Records): COUNT(*) in transactions
2. Rule 2 (Deposit Account Integrity): COUNT(*) in transactions where account_id not in deposit_accounts
3. Rule 3 (Source Ref Uniqueness): COUNT(*) duplicate groups and SUM(cnt) duplicate rows for non-empty source_ref
4. Rule 4 (Valid Tx Code): COUNT(*) where transaction_code not in ('DEP', 'WDL')

Security & Safety:
- Database must be opened in Read-Only mode.
- Explicit column selection / parameterized queries only (no SELECT *).
- Aggregate metrics returned only — zero raw rows or PII exposed.
- Expected count for test data: UNKNOWN.
"""

import sqlite3
from typing import Dict, Any

def evaluate_data_quality_rules(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Evaluate 4 data quality rules on the transactions table.

    Args:
        conn: sqlite3 Read-Only Connection

    Returns:
        Dict containing aggregate metrics, rules summary, and pass rates.
    """
    cursor = conn.cursor()

    # Rule 1: Total transactions count
    cursor.execute("SELECT COUNT(*) FROM transactions")
    total_transactions = cursor.fetchone()[0] or 0

    # Rule 2: Transactions with account_id not found in deposit_accounts
    cursor.execute("""
        SELECT COUNT(*)
        FROM transactions t
        WHERE NOT EXISTS (
            SELECT 1
            FROM deposit_accounts d
            WHERE d.account_id = t.account_id
        )
    """)
    unmatched_account_count = cursor.fetchone()[0] or 0

    # Rule 3: Non-empty source_ref values appearing more than once
    # returns duplicate_source_ref_groups (distinct groups) and duplicate_source_ref_rows (sum of rows)
    cursor.execute("""
        SELECT COUNT(*), SUM(cnt)
        FROM (
            SELECT source_ref, COUNT(*) AS cnt
            FROM transactions
            WHERE source_ref IS NOT NULL AND source_ref != ''
            GROUP BY source_ref
            HAVING cnt > 1
        ) AS dup
    """)
    dup_row = cursor.fetchone()
    duplicate_source_ref_groups = dup_row[0] or 0
    duplicate_source_ref_rows = int(dup_row[1]) if dup_row[1] else 0

    # Rule 4: Transactions with transaction_code not in ('DEP', 'WDL')
    cursor.execute("""
        SELECT COUNT(*)
        FROM transactions
        WHERE transaction_code NOT IN (?, ?)
    """, ("DEP", "WDL"))
    invalid_code_count = cursor.fetchone()[0] or 0

    # Distribution of transaction_code for audit traceability
    cursor.execute("""
        SELECT transaction_code, COUNT(*) 
        FROM transactions 
        GROUP BY transaction_code
        ORDER BY COUNT(*) DESC
    """)
    code_distribution = {row[0]: row[1] for row in cursor.fetchall()}

    total_issues = unmatched_account_count + duplicate_source_ref_rows + invalid_code_count
    clean_transactions = max(0, total_transactions - total_issues)
    overall_pass_rate = round((clean_transactions / total_transactions * 100), 2) if total_transactions else 100.0

    rules = [
        {
            "id": 1,
            "code": "RULE_1",
            "name": "ความครบถ้วนของธุรกรรม (Total Records)",
            "category": "Completeness",
            "status": "PASS",
            "passed": total_transactions,
            "issues": 0,
            "pass_rate": 100.0,
            "expected_count": "UNKNOWN",
            "description": "นับจำนวนแถวทั้งหมดในตาราง transactions"
        },
        {
            "id": 2,
            "code": "RULE_2",
            "name": "ความสัมพันธ์บัญชีเงินฝาก (Deposit Account Integrity)",
            "category": "Referential Integrity",
            "status": "FAIL" if unmatched_account_count > 0 else "PASS",
            "passed": max(0, total_transactions - unmatched_account_count),
            "issues": unmatched_account_count,
            "pass_rate": round(max(0, total_transactions - unmatched_account_count) / total_transactions * 100, 2) if total_transactions else 100.0,
            "expected_count": "UNKNOWN",
            "description": "จำนวนรายการที่มี account_id แต่ไม่พบในตาราง deposit_accounts"
        },
        {
            "id": 3,
            "code": "RULE_3",
            "name": "ความไม่ซ้ำซ้อนของเลขอ้างอิง (Source Ref Uniqueness)",
            "category": "Uniqueness",
            "status": "WARN" if duplicate_source_ref_groups > 0 else "PASS",
            "passed": max(0, total_transactions - duplicate_source_ref_rows),
            "issues": duplicate_source_ref_rows,
            "groups": duplicate_source_ref_groups,
            "pass_rate": round(max(0, total_transactions - duplicate_source_ref_rows) / total_transactions * 100, 2) if total_transactions else 100.0,
            "expected_count": "UNKNOWN",
            "description": "จำนวนกลุ่มและรายการของ source_ref ที่ไม่ว่างและซ้ำกัน"
        },
        {
            "id": 4,
            "code": "RULE_4",
            "name": "ความถูกต้องของรหัสธุรกรรม (Valid Tx Code: DEP/WDL)",
            "category": "Validity",
            "status": "FAIL" if invalid_code_count > 0 else "PASS",
            "passed": max(0, total_transactions - invalid_code_count),
            "issues": invalid_code_count,
            "pass_rate": round(max(0, total_transactions - invalid_code_count) / total_transactions * 100, 2) if total_transactions else 100.0,
            "expected_count": "UNKNOWN",
            "description": "จำนวนรายการที่ transaction_code ไม่อยู่ในชุดค่าที่คาดหวัง ('DEP', 'WDL')"
        }
    ]

    return {
        "status": "SUCCESS",
        "total_transactions": total_transactions,
        "unmatched_account_count": unmatched_account_count,
        "duplicate_source_ref_groups": duplicate_source_ref_groups,
        "duplicate_source_ref_rows": duplicate_source_ref_rows,
        "invalid_code_count": invalid_code_count,
        "clean_transactions": clean_transactions,
        "total_issues": total_issues,
        "overall_pass_rate": overall_pass_rate,
        "code_distribution": code_distribution,
        "expected_result": "UNKNOWN",
        "rules": rules
    }
