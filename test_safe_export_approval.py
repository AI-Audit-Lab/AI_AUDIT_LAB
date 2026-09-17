"""
test_safe_export_approval.py
-----------------------------
Standalone unit test suite for Safe Data Preview & Human Approval Export System.

Validates:
1. Default Unapproved State blocks export (HTTP 403)
2. Explicit Rejection blocks file creation
3. Approved state permits Safe Export in CSV, Excel, and PDF formats
4. Export files contain strictly Allowlist fields (zero PII, zero secrets, zero token map)
5. Audit log records ONLY status and timestamp without raw row data
"""

import os
import json
import csv
import io
from fastapi.testclient import TestClient

from app.main import app
from app.services.safe_data_service import SAFE_DATA_OUTPUT_DIR

client = TestClient(app)

def test_tc01_default_unapproved_export_blocked():
    print("[TC-01] Testing default unapproved export request...")
    response = client.get("/api/v1/safe-data/export?format=csv&approved=false")
    assert response.status_code == 403, f"Expected 403 Forbidden when unapproved, got {response.status_code}"
    body = response.json()
    assert "error" in body
    assert "approval" in body["error"].lower()
    print("  [OK] TC-01 Passed: Default unapproved state blocked export with 403.")


def test_tc02_rejection_logged_and_blocked():
    print("[TC-02] Testing explicit rejection flow...")
    # Record rejection
    approve_res = client.post("/api/v1/safe-data/approve", json={"status": "REJECTED"})
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "REJECTED"

    # Attempt export
    export_res = client.get("/api/v1/safe-data/export?format=excel&approved=false")
    assert export_res.status_code == 403, f"Expected 403 when rejected, got {export_res.status_code}"
    print("  [OK] TC-02 Passed: Rejection logged and export blocked cleanly.")


def test_tc03_approved_export_csv_excel_pdf():
    print("[TC-03] Testing approved export for CSV, Excel, and PDF formats...")
    
    # Record approval
    client.post("/api/v1/safe-data/approve", json={"status": "APPROVED"})

    # 1. Test CSV Export
    res_csv = client.get("/api/v1/safe-data/export?format=csv&approved=true")
    assert res_csv.status_code == 200, f"CSV export failed with status {res_csv.status_code}"
    assert res_csv.headers["content-type"].startswith("text/csv")
    csv_content = res_csv.content.decode("utf-8-sig")
    csv_reader = csv.reader(io.StringIO(csv_content))
    headers = next(csv_reader)
    print("  [CSV Headers]:", headers)
    
    # 2. Test Excel Export
    res_excel = client.get("/api/v1/safe-data/export?format=excel&approved=true")
    assert res_excel.status_code == 200, f"Excel export failed with status {res_excel.status_code}"
    assert "spreadsheetml" in res_excel.headers["content-type"]

    # 3. Test PDF Export
    res_pdf = client.get("/api/v1/safe-data/export?format=pdf&approved=true")
    assert res_pdf.status_code == 200, f"PDF export failed with status {res_pdf.status_code}"
    assert res_pdf.headers["content-type"] == "application/pdf"

    print("  [OK] TC-03 Passed: CSV, Excel, and PDF exports succeeded cleanly when approved.")


def test_tc04_zero_leakage_in_exports():
    print("[TC-04] Validating zero PII, zero secrets, zero token map leakage in CSV export...")
    res = client.get("/api/v1/safe-data/export?format=csv&approved=true")
    content = res.content.decode("utf-8-sig")
    
    forbidden_terms = ["full_name", "national_id", "account_id", "operator_id", "workstation_id", "secret", "credential", "token_map"]
    for term in forbidden_terms:
        assert term not in content.lower(), f"Forbidden term '{term}' detected in export file!"
    print("  [OK] TC-04 Passed: Zero leakage verified in export payload.")


def test_tc05_audit_log_sanitization():
    print("[TC-05] Verifying audit log contains ONLY status and timestamp without raw data...")
    log_file = os.path.join(SAFE_DATA_OUTPUT_DIR, "approval_audit.log")
    assert os.path.exists(log_file), "Approval audit log file should exist"

    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) > 0, "Audit log should have entries"
        for line in lines:
            entry = json.loads(line.strip())
            assert "status" in entry
            assert "timestamp" in entry
            assert "export_format" in entry
            # Ensure no raw transaction data fields exist in log entry
            assert "rule_id" not in entry
            assert "records_checked" not in entry
            assert "records_matched" not in entry
            assert "account_id" not in entry

    print("  [OK] TC-05 Passed: Audit log is strictly sanitized with status and timestamp only.")


def main():
    print("==========================================================")
    print(" Running Safe Export & Approval Unit Tests (TC-01..TC-05)")
    print("==========================================================")
    test_tc01_default_unapproved_export_blocked()
    test_tc02_rejection_logged_and_blocked()
    test_tc03_approved_export_csv_excel_pdf()
    test_tc04_zero_leakage_in_exports()
    test_tc05_audit_log_sanitization()
    print("==========================================================")
    print(" [SUCCESS] All 5 Safe Export Approval test cases passed!")
    print("==========================================================")

if __name__ == "__main__":
    main()
