import json
import os
from app.config import REPORT_JSON_PATH, CASHFLOW_DRAIN_REPORT_PATH, APP_NAME
from app.database import get_safe_aggregate_metrics, check_db_status, get_db_connection
from app.services.fast_in_out import (
    evaluate_fast_in_out_3d,
    validate_fast_in_out_params,
    get_fast_in_out_flagged_windows,
    RESULTS_PAGE_SIZE,
)

def get_fast_in_out_summary(large_in_min: float = 500000.0, outflow_ratio_min: float = 0.80, window_days: int = 3):
    """
    Service layer function to run FAST_IN_OUT_3D rule on Read-Only database.
    Validates parameters BEFORE opening database connection.
    """
    errors = validate_fast_in_out_params(large_in_min, outflow_ratio_min, window_days)
    if errors:
        return {
            "status": "ERROR",
            "errors": errors,
            "rule_name": "FAST_IN_OUT_3D",
            "audited_count": 0,
            "flagged_count": 0,
            "expected_count": "UNKNOWN"
        }

    conn = get_db_connection()
    try:
        result = evaluate_fast_in_out_3d(
            conn=conn,
            large_in_min=large_in_min,
            outflow_ratio_min=outflow_ratio_min,
            window_days=window_days
        )
        return result
    finally:
        conn.close()


def get_fast_in_out_results(
    large_in_min: float = 500000.0,
    outflow_ratio_min: float = 0.80,
    window_days: int = 3,
    page: int = 1,
    page_size: int = RESULTS_PAGE_SIZE,
):
    """
    Service layer function to return paginated FAST_IN_OUT_3D flagged window results.
    Validates parameters BEFORE opening database connection.
    Returns only approved, PII-free fields per flagged window.
    """
    errors = validate_fast_in_out_params(large_in_min, outflow_ratio_min, window_days)
    if errors:
        return {
            "status": "ERROR",
            "errors": errors,
            "rule_name": "FAST_IN_OUT_3D",
            "results": [],
            "total_flagged": 0,
            "total_pages": 0,
            "current_page": page,
            "page_size": page_size,
        }

    conn = get_db_connection()
    try:
        return get_fast_in_out_flagged_windows(
            conn=conn,
            large_in_min=large_in_min,
            outflow_ratio_min=outflow_ratio_min,
            window_days=window_days,
            page=page,
            page_size=page_size,
        )
    finally:
        conn.close()

def get_fast_in_out_all_results(
    large_in_min: float = 500000.0,
    outflow_ratio_min: float = 0.80,
    window_days: int = 3,
):
    """
    Service layer function to return ALL FAST_IN_OUT_3D flagged window results for exporting.
    """
    errors = validate_fast_in_out_params(large_in_min, outflow_ratio_min, window_days)
    if errors:
        return {
            "status": "ERROR",
            "errors": errors,
            "rule_name": "FAST_IN_OUT_3D",
            "results": [],
            "total_flagged": 0,
            "total_pages": 0,
            "current_page": 1,
            "page_size": 0,
        }

    conn = get_db_connection()
    try:
        return get_fast_in_out_flagged_windows(
            conn=conn,
            large_in_min=large_in_min,
            outflow_ratio_min=outflow_ratio_min,
            window_days=window_days,
            get_all=True
        )
    finally:
        conn.close()




def get_dashboard_summary():
    """Service layer providing safe metrics for the web application."""
    db_status = check_db_status()
    db_metrics = get_safe_aggregate_metrics()
    
    audit_report = None
    if os.path.exists(REPORT_JSON_PATH):
        try:
            with open(REPORT_JSON_PATH, "r", encoding="utf-8") as f:
                audit_report = json.load(f)
        except Exception:
            pass
            
    cashflow_report = None
    if os.path.exists(CASHFLOW_DRAIN_REPORT_PATH):
        try:
            with open(CASHFLOW_DRAIN_REPORT_PATH, "r", encoding="utf-8") as f:
                cashflow_report = json.load(f)
        except Exception:
            pass

    fast_in_out_res = get_fast_in_out_summary()
            
    anomaly_summary = {
        "inactive_transactions_count": 0,
        "duplicate_references_count": 0,
        "off_hours_transactions_count": 0,
        "statistical_outliers_count": 0,
        "cashflow_drain_accounts": 0,
        "cashflow_drain_windows": 0,
        "fast_in_out_3d": fast_in_out_res
    }
    reconciliation_summary = {
        "gl_daily_issues_count": 0
    }
    
    if audit_report:
        anom = audit_report.get("anomaly_module", {})
        anomaly_summary["inactive_transactions_count"] = anom.get("inactive_transactions_count", 0)
        anomaly_summary["duplicate_references_count"] = anom.get("duplicate_references_count", 0)
        anomaly_summary["off_hours_transactions_count"] = anom.get("off_hours_transactions_count", 0)
        anomaly_summary["statistical_outliers_count"] = anom.get("statistical_outliers_count", 0)
        
        recon = audit_report.get("reconciliation_module", {})
        reconciliation_summary["gl_daily_issues_count"] = recon.get("gl_daily_issues_count", 0)

    if cashflow_report:
        res = cashflow_report.get("results", {})
        anomaly_summary["cashflow_drain_accounts"] = res.get("flagged_accounts_count", 0)
        anomaly_summary["cashflow_drain_windows"] = res.get("flagged_windows_count", 0)

    return {
        "system_name": APP_NAME,
        "db_status": db_status,
        "metrics": db_metrics,
        "audit_summary": {
            "reconciliation": reconciliation_summary,
            "anomaly": anomaly_summary
        }
    }

