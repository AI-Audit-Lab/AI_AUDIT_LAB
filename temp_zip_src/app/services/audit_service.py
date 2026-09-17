import json
import os
from app.config import REPORT_JSON_PATH, APP_NAME
from app.database import get_safe_aggregate_metrics, check_db_status

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
            
    anomaly_summary = {
        "inactive_transactions_count": 0,
        "duplicate_references_count": 0,
        "off_hours_transactions_count": 0,
        "statistical_outliers_count": 0
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

    return {
        "system_name": APP_NAME,
        "db_status": db_status,
        "metrics": db_metrics,
        "audit_summary": {
            "reconciliation": reconciliation_summary,
            "anomaly": anomaly_summary
        }
    }
