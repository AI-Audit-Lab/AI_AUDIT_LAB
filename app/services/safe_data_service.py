"""
app/services/safe_data_service.py
Service for preparing safe audit data according to Human-approved Baseline rules.
Strictly local execution, zero external LLM connection, zero automated external export.
"""

import os
import json
import hashlib
from typing import Dict, Any, List, Optional

# Approved Baseline Allowlist fields
BASELINE_ALLOWLIST = {
    "rule_id",
    "records_checked",
    "records_matched",
    "large_in_min",
    "outflow_ratio_min",
    "window_days",
}

# Strictly forbidden PII and sensitive fields
PII_BLOCKLIST = {
    "full_name",
    "national_id",
    "email",
    "phone",
    "address",
    "note",
    "operator_id",
    "workstation_id",
    "secret",
    "credential",
}

# Separate location for Token Mapping (MUST NOT be included in export files)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOKEN_MAP_FILE = os.path.join(BASE_DIR, "data", "token_map.json")
SAFE_DATA_OUTPUT_DIR = os.path.join(BASE_DIR, "output", "safe_data")


def get_or_create_token(account_id: str) -> str:
    """
    Generate a pseudonymized token for account_id.
    Saved exclusively to data/token_map.json (separate from safe export files).
    """
    token_map = {}
    if os.path.exists(TOKEN_MAP_FILE):
        try:
            with open(TOKEN_MAP_FILE, "r", encoding="utf-8") as f:
                token_map = json.load(f)
        except Exception:
            token_map = {}

    if account_id in token_map:
        return token_map[account_id]

    # Generate token using MD5 hash digest
    token = f"ACCT_TOKEN_{hashlib.md5(account_id.encode('utf-8')).hexdigest()[:8].upper()}"
    token_map[account_id] = token

    os.makedirs(os.path.dirname(TOKEN_MAP_FILE), exist_ok=True)
    with open(TOKEN_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(token_map, f, indent=2, ensure_ascii=False)

    return token


def prepare_safe_data(
    raw_data: List[Dict[str, Any]],
    allow_account_token: bool = False
) -> List[Dict[str, Any]]:
    """
    Filter data rows using strict Allowlist and Blocklist.
    - Preserves only BASELINE_ALLOWLIST fields.
    - Removes all PII/sensitive blocklist fields.
    - account_id is excluded from Baseline; only converted to account_token if challenge mode is approved.
    - Operates strictly in-memory locally.
    """
    safe_data_list = []

    for row in raw_data:
        safe_row = {}
        for key, value in row.items():
            key_lower = key.lower()

            # 1. Reject if key contains any PII blocklist pattern
            if any(blocked in key_lower for blocked in PII_BLOCKLIST):
                continue

            # 2. Reject account_id unless challenge tokenization is explicitly enabled
            if key_lower == "account_id":
                if allow_account_token:
                    safe_row["account_token"] = get_or_create_token(str(value))
                continue

            # 3. Only include fields in the Baseline Allowlist
            if key_lower in BASELINE_ALLOWLIST:
                safe_row[key] = value

        safe_data_list.append(safe_row)

    return safe_data_list


def create_baseline_summary(
    rule_id: str,
    records_checked: int,
    records_matched: int,
    large_in_min: float,
    outflow_ratio_min: float,
    window_days: int
) -> Dict[str, Any]:
    """
    Constructs a clean Baseline summary dictionary adhering strictly to the Allowlist.
    Uses counts and threshold parameters instead of transaction details.
    """
    return {
        "rule_id": rule_id,
        "records_checked": int(records_checked),
        "records_matched": int(records_matched),
        "large_in_min": float(large_in_min),
        "outflow_ratio_min": float(outflow_ratio_min),
        "window_days": int(window_days)
    }


def save_safe_data_locally(data: Any, filename: str = "safe_data_baseline.json") -> str:
    """
    Saves filtered safe data to a dedicated output/safe_data directory,
    completely separate from detailed audit results.
    """
    os.makedirs(SAFE_DATA_OUTPUT_DIR, exist_ok=True)
    target_path = os.path.join(SAFE_DATA_OUTPUT_DIR, filename)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return target_path


# Field transformation mapping definitions for Human inspection
FIELD_TRANSFORMATION_RULES = [
    {"field_name": "rule_id", "category": "Allowlist", "method": "เก็บ (Keep)", "description": "รหัสกฎการตรวจสอบการทุจริต"},
    {"field_name": "records_checked", "category": "Allowlist", "method": "รวมยอด (Aggregate)", "description": "จำนวนรายการที่ผ่านการตรวจเช็กทั้งหมด"},
    {"field_name": "records_matched", "category": "Allowlist", "method": "รวมยอด (Aggregate)", "description": "จำนวนรายการที่ตรงเงื่อนไขสุ่มเสี่ยง"},
    {"field_name": "large_in_min", "category": "Allowlist", "method": "เก็บ (Keep)", "description": "เกณฑ์ยอดเงินเข้าขั้นต่ำ"},
    {"field_name": "outflow_ratio_min", "category": "Allowlist", "method": "เก็บ (Keep)", "description": "เกณฑ์สัดส่วนเงินออกขั้นต่ำ"},
    {"field_name": "window_days", "category": "Allowlist", "method": "เก็บ (Keep)", "description": "กรอบระยะเวลาพิจารณา (วัน)"},
    {"field_name": "account_token", "category": "Allowlist (Challenge)", "method": "แทนค่า (Substitute)", "description": "รหัสแทนบัญชี (MD5 Hash Digest) ไม่ออกเลขจริง"},
    {"field_name": "full_name / national_id", "category": "Blocklist (PII)", "method": "ตัดออก (Drop)", "description": "ชื่อ-นามสกุล และเลขประจำตัวประชาชน ถูกตัดออก 100%"},
    {"field_name": "account_id", "category": "Blocklist (PII)", "method": "ปิดบัง / ตัดออก (Mask/Drop)", "description": "เลขที่บัญชีธนาคารจริง ถูกปิดบังและตัดออกใน Baseline"},
    {"field_name": "secret / api_key / password", "category": "Forbidden Secret", "method": "ปิดบัง / ตัดออก (Forbidden)", "description": "รหัสลับและคีย์ของระบบ ถูกปิดกั้นและตัดออก 100%"},
    {"field_name": "token_map.json", "category": "Internal Lookup", "method": "ปิดบัง (Internal Only)", "description": "ตารางเทียบรหัส Token ถูกจัดเก็บแยกต่างหาก ห้ามนำออกเด็ดขาด"},
]


def log_approval_event(status: str, export_format: str = "") -> None:
    """
    Logs approval decision status and timestamp strictly WITHOUT any actual audit payload or user data.
    """
    import datetime
    os.makedirs(SAFE_DATA_OUTPUT_DIR, exist_ok=True)
    log_file = os.path.join(SAFE_DATA_OUTPUT_DIR, "approval_audit.log")
    
    log_entry = {
        "status": status.upper(),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "export_format": export_format.upper() if export_format else "NONE"
    }
    
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


def export_safe_data_to_csv(safe_records: List[Dict[str, Any]]) -> bytes:
    """
    Exports clean safe records to CSV using ONLY Allowlist fields.
    """
    import csv
    import io
    
    if not safe_records:
        return b""

    # Determine allowable headers present in records
    headers = list(safe_records[0].keys())
    # Extra check: Ensure no forbidden field slips through
    headers = [h for h in headers if h.lower() in BASELINE_ALLOWLIST or h.lower() == "account_token"]

    output = io.StringIO()
    output.write('\ufeff')  # UTF-8 BOM
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    
    for row in safe_records:
        clean_row = {k: v for k, v in row.items() if k in headers}
        writer.writerow(clean_row)
        
    return output.getvalue().encode('utf-8')


def export_safe_data_to_excel(safe_records: List[Dict[str, Any]]) -> bytes:
    """
    Exports clean safe records to Excel using ONLY Allowlist fields.
    """
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment

    output = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.title = "Safe Export Baseline"

    if not safe_records:
        wb.save(output)
        return output.getvalue()

    headers = [h for h in list(safe_records[0].keys()) if h.lower() in BASELINE_ALLOWLIST or h.lower() == "account_token"]
    ws.append(headers)
    
    for col in range(1, len(headers) + 1):
        ws.cell(row=1, column=col).font = Font(bold=True)
        ws.cell(row=1, column=col).alignment = Alignment(horizontal='center')

    for row in safe_records:
        row_values = [row.get(h, "") for h in headers]
        ws.append(row_values)

    wb.save(output)
    return output.getvalue()


def export_safe_data_to_pdf(safe_records: List[Dict[str, Any]]) -> bytes:
    """
    Exports clean safe records to PDF using ONLY Allowlist fields.
    """
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4)
    elements = []

    styles = getSampleStyleSheet()
    title = Paragraph("Safe Export Baseline Report", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 12))

    if not safe_records:
        elements.append(Paragraph("No Safe Data Available", styles['Normal']))
        doc.build(elements)
        return output.getvalue()

    headers = [h for h in list(safe_records[0].keys()) if h.lower() in BASELINE_ALLOWLIST or h.lower() == "account_token"]
    table_data = [headers]

    for row in safe_records:
        table_data.append([str(row.get(h, "")) for h in headers])

    t = Table(table_data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.navy),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))

    elements.append(t)
    doc.build(elements)
    return output.getvalue()

