import os

# Calculate project base directory relative to config.py location
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_FILE = os.path.join(BASE_DIR, "data", "training_data.sqlite3").replace("\\", "/")
DB_FILE = os.environ.get("AUDIT_DB_FILE", DEFAULT_DB_FILE)
DB_PATH_POSIX = DB_FILE.replace("\\", "/")
DB_URI = os.environ.get("AUDIT_DB_URI", f"file:{DB_PATH_POSIX}?mode=ro")

APP_NAME = "Mini Financial Audit Tool"
API_PREFIX = "/api/v1"

# Strict PII Blocklist to prevent raw data exposure
PII_BLOCKLIST = {
    "members": ["full_name", "national_id", "email", "phone", "address"],
    "deposit_accounts": ["account_id"],
    "loan_contracts": ["contract_id"],
    "transactions": ["account_id", "operator_id", "workstation_id"]
}

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
REPORT_JSON_PATH = os.path.join(OUTPUT_DIR, "audit_summary_report.json")
CASHFLOW_DRAIN_REPORT_PATH = os.path.join(OUTPUT_DIR, "cashflow_drain_report.json")
AUDIT_DECISIONS_LOG_PATH = os.path.join(OUTPUT_DIR, "fast_in_out_audit_decisions.json")

