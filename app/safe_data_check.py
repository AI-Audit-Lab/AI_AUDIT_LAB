"""
app/safe_data_check.py
Module for verifying Safe Data compliance against Baseline Allowlist and PII Blocklist.
Strictly displays only: Field names, count of forbidden fields found, and PASS/FAIL.
Local processing only, zero external LLM connection.
"""

import sys
import os
import json
from typing import Dict, Any, List, Union, Set

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.safe_data_service import (
    BASELINE_ALLOWLIST,
    PII_BLOCKLIST,
    prepare_safe_data,
    create_baseline_summary
)


def verify_allowlist_and_forbidden(
    data: Union[List[Dict[str, Any]], Dict[str, Any]],
    allow_account_token: bool = False
) -> Dict[str, Any]:
    """
    Checks data against BASELINE_ALLOWLIST and verifies forbidden fields do not appear.
    Returns dictionary with:
      - field_names: list of unique field names detected
      - forbidden_count: count of forbidden/unauthorized fields found across all records
      - status: 'PASS' if only allowed fields exist and zero forbidden fields, else 'FAIL'
    """
    if isinstance(data, dict):
        records = [data]
    elif isinstance(data, list):
        records = data
    else:
        return {
            "field_names": [],
            "forbidden_count": 1,
            "status": "FAIL"
        }

    observed_fields: Set[str] = set()
    forbidden_count = 0

    # Build current allowable set
    allowed_set = set(BASELINE_ALLOWLIST)
    if allow_account_token:
        allowed_set.add("account_token")

    for row in records:
        if not isinstance(row, dict):
            forbidden_count += 1
            continue

        for key in row.keys():
            key_clean = str(key).strip().lower()
            observed_fields.add(str(key))

            # 1. Check if key matches or contains any PII blocklist term
            is_blocked = any(blocked in key_clean for blocked in PII_BLOCKLIST)

            # 2. Check account_id explicitly (forbidden in baseline)
            if key_clean == "account_id":
                is_blocked = True

            # 3. Check against Allowlist
            is_allowed = key_clean in allowed_set

            if is_blocked or (not is_allowed):
                forbidden_count += 1

    status = "PASS" if (forbidden_count == 0 and len(observed_fields) > 0) else "FAIL"

    return {
        "field_names": sorted(list(observed_fields)),
        "forbidden_count": forbidden_count,
        "status": status
    }


def display_check_summary(result: Dict[str, Any]) -> None:
    """
    Displays strictly:
    - ชื่อช่อง (Field Names)
    - จำนวนช่องต้องห้ามที่พบ (Forbidden fields count)
    - PASS/FAIL
    """
    fields_str = ", ".join(result["field_names"]) if result["field_names"] else "ไม่มี"
    print(f"ชื่อช่อง: {fields_str}")
    print(f"จำนวนช่องต้องห้ามที่พบ: {result['forbidden_count']}")
    print(f"ผลการตรวจสอบ: {result['status']}")


if __name__ == "__main__":
    # Self-test demonstration for Human review
    print("=== ทดสอบที่ 1: ตรวจสอบข้อมูลดิบที่มีข้อมูลต้องห้าม (Raw / Dirty Data) ===")
    mock_dirty_data = [
        {
            "rule_id": "FAST_IN_OUT_3D",
            "records_checked": 500,
            "records_matched": 3,
            "large_in_min": 500000.0,
            "outflow_ratio_min": 0.8,
            "window_days": 3,
            "full_name": "นายทดสอบ มั่งมี",
            "national_id": "1100400123456",
            "account_id": "ACC-00123",
            "phone": "0812345678",
            "secret": "TOP_SECRET_HASH",
            "operator_id": "OP_99",
            "workstation_id": "WS_01",
            "note": "ข้อมูลโอนเงินผิดปกติ"
        }
    ]
    res1 = verify_allowlist_and_forbidden(mock_dirty_data)
    display_check_summary(res1)

    print("\n=== ทดสอบที่ 2: ตรวจสอบข้อมูล Baseline ที่คัดกรองแล้ว (Clean Baseline Data) ===")
    clean_baseline_data = prepare_safe_data(mock_dirty_data, allow_account_token=False)
    res2 = verify_allowlist_and_forbidden(clean_baseline_data)
    display_check_summary(res2)

    print("\n=== ทดสอบที่ 3: ตรวจสอบกรณีโจทย์ท้าทายที่ Human อนุมัติ Token (Challenge Mode) ===")
    challenge_safe_data = prepare_safe_data(mock_dirty_data, allow_account_token=True)
    res3 = verify_allowlist_and_forbidden(challenge_safe_data, allow_account_token=True)
    display_check_summary(res3)
