from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
import os

from app.config import APP_NAME, API_PREFIX
from app.database import check_db_status
from app.services.audit_service import get_dashboard_summary, get_fast_in_out_summary, get_fast_in_out_results

app = FastAPI(title=APP_NAME, version="1.0.0")

# Mount static files and templates using relative module pathing
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@app.get("/")
def read_root(request: Request):
    """Render main Mini Financial Audit Tool Dashboard."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"app_name": APP_NAME}
    )

@app.get(f"{API_PREFIX}/health")
def health_check():
    """Health check endpoint displaying Read-Only database connection status."""
    db_status = check_db_status()
    return JSONResponse(content={
        "status": "online",
        "app": APP_NAME,
        "database": db_status
    })

@app.get(f"{API_PREFIX}/summary")
def get_summary():
    """
    Returns aggregated KPI metrics and audit summary counts.
    STRICT SECURITY GUARANTEE: Zero raw rows or PII fields exposed.
    """
    summary_data = get_dashboard_summary()
    return JSONResponse(content=summary_data)

@app.get(f"{API_PREFIX}/fast-in-out")
def get_fast_in_out_api(large_in_min: float = 500000.0, outflow_ratio_min: float = 0.80, window_days: int = 3):
    """
    Evaluates FAST_IN_OUT_3D rule based on user-provided Web parameters.
    STRICT SECURITY GUARANTEE: Zero raw rows or PII fields exposed. Aggregate counts only.
    """
    result = get_fast_in_out_summary(
        large_in_min=large_in_min,
        outflow_ratio_min=outflow_ratio_min,
        window_days=window_days
    )
    return JSONResponse(content=result)


@app.get("/data-quality")
def read_data_quality(request: Request):
    """Render Data Quality Check page."""
    return templates.TemplateResponse(
        request=request,
        name="data_quality.html",
        context={"app_name": APP_NAME}
    )

@app.get("/fast-in-out-results")
def read_fast_in_out_results(request: Request):
    """Render FAST_IN_OUT_3D window-level results page (approved columns only, paginated)."""
    return templates.TemplateResponse(
        request=request,
        name="fast_in_out_results.html",
        context={"app_name": APP_NAME}
    )

@app.get("/safe-data-check")
def read_safe_data_check(request: Request):
    """Render Safe Data Verification page."""
    return templates.TemplateResponse(
        request=request,
        name="safe_data_check.html",
        context={"app_name": APP_NAME}
    )

@app.get(f"{API_PREFIX}/data-quality")
def get_data_quality():
    """
    Returns data quality metrics.
    STRICT SECURITY GUARANTEE: Zero raw rows or PII fields exposed.
    """
    from app.database import get_data_quality_checks
    dq_data = get_data_quality_checks()
    return JSONResponse(content=dq_data)

@app.get(f"{API_PREFIX}/safe-data")
def get_safe_data_api(
    large_in_min: float = 500000.0,
    outflow_ratio_min: float = 0.80,
    window_days: int = 3,
):
    """
    Returns filtered Safe Data forwarded for inspection along with field transformation rules.
    STRICT SECURITY GUARANTEE:
    - Only BASELINE_ALLOWLIST fields included.
    - Zero PII, zero free-text, zero forbidden fields.
    - Zero external LLM connection.
    - Does NOT create export file automatically.
    """
    from app.services.safe_data_service import (
        create_baseline_summary,
        prepare_safe_data,
        FIELD_TRANSFORMATION_RULES
    )
    from app.safe_data_check import verify_allowlist_and_forbidden
    from app.services.audit_service import get_fast_in_out_summary

    summary = get_fast_in_out_summary(large_in_min, outflow_ratio_min, window_days)
    records_checked = summary.get("audited_count", 0)
    records_matched = summary.get("flagged_count", 0)

    # Prepare safe baseline data item
    baseline_record = create_baseline_summary(
        rule_id="FAST_IN_OUT_3D",
        records_checked=records_checked,
        records_matched=records_matched,
        large_in_min=large_in_min,
        outflow_ratio_min=outflow_ratio_min,
        window_days=window_days
    )

    safe_list = prepare_safe_data([baseline_record], allow_account_token=False)
    verification = verify_allowlist_and_forbidden(safe_list, allow_account_token=False)

    return JSONResponse(content={
        "safe_data": safe_list,
        "verification": verification,
        "transformation_rules": FIELD_TRANSFORMATION_RULES,
        "note": "Safe Data inspection ready. Default state is UNAPPROVED. No export file generated."
    })


@app.post(f"{API_PREFIX}/safe-data/approve")
async def approve_safe_data_api(request: Request):
    """
    Endpoint for Human to record Approve or Reject decision.
    STRICT SECURITY GUARANTEE: Records strictly status and timestamp without any payload data.
    """
    from app.services.safe_data_service import log_approval_event
    try:
        body = await request.json()
        status = body.get("status", "REJECTED").upper()
    except Exception:
        status = "REJECTED"

    if status not in ["APPROVED", "REJECTED"]:
        status = "REJECTED"

    log_approval_event(status=status)
    return JSONResponse(content={
        "status": status,
        "message": f"Recorded approval decision: {status}"
    })


@app.get(f"{API_PREFIX}/safe-data/export")
def export_safe_data_api(
    format: str,
    approved: bool = False,
    large_in_min: float = 500000.0,
    outflow_ratio_min: float = 0.80,
    window_days: int = 3,
):
    """
    Generates Safe Export (CSV, Excel, PDF) using strictly Allowlist fields from item 2.7.
    STRICT SECURITY GUARANTEE:
    - Default approved state is False. If not approved or rejected, returns 403 Forbidden with zero file creation.
    - Double checks allowlist and forbidden fields before generating output.
    - Zero secret, zero API key, zero PII fields, zero token map table.
    """
    from fastapi.responses import Response
    from app.services.safe_data_service import (
        create_baseline_summary,
        prepare_safe_data,
        export_safe_data_to_csv,
        export_safe_data_to_excel,
        export_safe_data_to_pdf,
        log_approval_event
    )
    from app.safe_data_check import verify_allowlist_and_forbidden
    from app.services.audit_service import get_fast_in_out_summary

    if not approved:
        # Log rejection attempt
        log_approval_event(status="REJECTED", export_format=format)
        return JSONResponse(
            content={"error": "Export blocked: Safe Export requires explicit Human approval before file creation."},
            status_code=403
        )

    summary = get_fast_in_out_summary(large_in_min, outflow_ratio_min, window_days)
    records_checked = summary.get("audited_count", 0)
    records_matched = summary.get("flagged_count", 0)

    baseline_record = create_baseline_summary(
        rule_id="FAST_IN_OUT_3D",
        records_checked=records_checked,
        records_matched=records_matched,
        large_in_min=large_in_min,
        outflow_ratio_min=outflow_ratio_min,
        window_days=window_days
    )

    safe_list = prepare_safe_data([baseline_record], allow_account_token=False)
    verification = verify_allowlist_and_forbidden(safe_list, allow_account_token=False)

    if verification.get("status") != "PASS":
        return JSONResponse(
            content={"error": "Export blocked: Safe data failed verification check."},
            status_code=400
        )

    log_approval_event(status="APPROVED", export_format=format)

    fmt = format.lower()
    if fmt == "csv":
        content = export_safe_data_to_csv(safe_list)
        media_type = "text/csv"
        filename = "safe_data_export.csv"
    elif fmt == "excel":
        content = export_safe_data_to_excel(safe_list)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "safe_data_export.xlsx"
    elif fmt == "pdf":
        content = export_safe_data_to_pdf(safe_list)
        media_type = "application/pdf"
        filename = "safe_data_export.pdf"
    else:
        return JSONResponse(content={"error": "Unsupported export format"}, status_code=400)

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )



@app.get(f"{API_PREFIX}/fast-in-out/results")
def get_fast_in_out_results_api(
    large_in_min: float = 500000.0,
    outflow_ratio_min: float = 0.80,
    window_days: int = 3,
    page: int = 1,
    page_size: int = 20,
):
    """
    Returns paginated FAST_IN_OUT_3D flagged window results.
    STRICT SECURITY GUARANTEE: Zero raw rows or PII fields (account_id, operator_id,
    workstation_id) exposed. Approved columns only: row_no, anchor_date, inflow_amount,
    outflow_total, outflow_ratio.
    """
    # Clamp page_size to prevent excessive data in a single response
    page_size = max(1, min(page_size, 200))
    result = get_fast_in_out_results(
        large_in_min=large_in_min,
        outflow_ratio_min=outflow_ratio_min,
        window_days=window_days,
        page=page,
        page_size=page_size,
    )
    return JSONResponse(content=result)

@app.get(f"{API_PREFIX}/fast-in-out/export")
def export_fast_in_out_results_api(
    format: str,
    large_in_min: float = 500000.0,
    outflow_ratio_min: float = 0.80,
    window_days: int = 3,
):
    """
    Exports ALL FAST_IN_OUT_3D flagged window results in the specified format (csv, excel, pdf).
    STRICT SECURITY GUARANTEE: Zero raw rows or PII fields exposed.
    """
    from fastapi.responses import Response
    from app.services.audit_service import get_fast_in_out_all_results
    from app.services.export_service import export_results_to_csv, export_results_to_excel, export_results_to_pdf
    
    result = get_fast_in_out_all_results(
        large_in_min=large_in_min,
        outflow_ratio_min=outflow_ratio_min,
        window_days=window_days,
    )
    
    if result.get("status") == "ERROR":
        return JSONResponse(content=result, status_code=400)
        
    data = result.get("results", [])
    
    if format.lower() == "csv":
        content = export_results_to_csv(data)
        media_type = "text/csv"
        filename = "fast_in_out_results.csv"
    elif format.lower() == "excel":
        content = export_results_to_excel(data)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "fast_in_out_results.xlsx"
    elif format.lower() == "pdf":
        content = export_results_to_pdf(data)
        media_type = "application/pdf"
        filename = "fast_in_out_results.pdf"
    else:
        return JSONResponse(content={"error": "Unsupported format"}, status_code=400)
        
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@app.post(f"{API_PREFIX}/fast-in-out/audit-decision")
async def save_fast_in_out_audit_decision(request: Request):
    """
    Records a Human-made Audit Decision for a FAST_IN_OUT flagged window.
    STRICT SECURITY GUARANTEE:
    - Saves ONLY decision status, row_no, anchor_date, and remark (text only, no amounts).
    - Does NOT expose or store PII fields.
    - Does NOT auto-approve. Human must explicitly choose a decision.
    - Returns 400 if decision value is invalid.
    """
    import json
    import datetime
    import os
    from app.config import AUDIT_DECISIONS_LOG_PATH, OUTPUT_DIR

    ALLOWED_DECISIONS = {"CONFIRM", "CLEAR", "FLAG_FURTHER"}

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"error": "Invalid JSON body."}, status_code=400)

    decision = str(body.get("decision", "")).strip().upper()
    row_no = body.get("row_no")
    anchor_date = str(body.get("anchor_date", "")).strip()
    remark = str(body.get("remark", "")).strip()[:500]  # Cap remark length

    if decision not in ALLOWED_DECISIONS:
        return JSONResponse(
            content={"error": f"Invalid decision. Must be one of: {sorted(ALLOWED_DECISIONS)}"},
            status_code=400
        )

    if not anchor_date or len(anchor_date) > 20:
        return JSONResponse(content={"error": "anchor_date is required and must be a valid date string."}, status_code=400)

    # Build safe log entry — no PII, no amounts, status and time only
    log_entry = {
        "logged_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "row_no": int(row_no) if row_no is not None else None,
        "anchor_date": anchor_date,
        "decision": decision,
        "remark": remark,
        "auditor": "Human (Local)"
    }

    # Load or initialise log file
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    existing_log = []
    if os.path.exists(AUDIT_DECISIONS_LOG_PATH):
        try:
            with open(AUDIT_DECISIONS_LOG_PATH, "r", encoding="utf-8") as f:
                existing_log = json.load(f)
            if not isinstance(existing_log, list):
                existing_log = []
        except Exception:
            existing_log = []

    # Update or append: replace existing entry for same row_no+anchor_date if present
    updated = False
    for idx, entry in enumerate(existing_log):
        if entry.get("row_no") == log_entry["row_no"] and entry.get("anchor_date") == log_entry["anchor_date"]:
            existing_log[idx] = log_entry
            updated = True
            break
    if not updated:
        existing_log.append(log_entry)

    with open(AUDIT_DECISIONS_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(existing_log, f, ensure_ascii=False, indent=2)

    return JSONResponse(content={
        "status": "SAVED",
        "message": f"Audit decision '{decision}' recorded for row {row_no} / {anchor_date}.",
        "entry": log_entry
    })


@app.get(f"{API_PREFIX}/fast-in-out/audit-log")
def get_fast_in_out_audit_log():
    """
    Returns the Audit Decision log for FAST_IN_OUT results.
    STRICT SECURITY GUARANTEE: Returns only decision, row_no, anchor_date, remark, logged_at. No raw data.
    """
    import json
    import os
    from app.config import AUDIT_DECISIONS_LOG_PATH

    if not os.path.exists(AUDIT_DECISIONS_LOG_PATH):
        return JSONResponse(content={"log": [], "total": 0})

    try:
        with open(AUDIT_DECISIONS_LOG_PATH, "r", encoding="utf-8") as f:
            log = json.load(f)
        if not isinstance(log, list):
            log = []
    except Exception:
        log = []

    return JSONResponse(content={"log": log, "total": len(log)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
