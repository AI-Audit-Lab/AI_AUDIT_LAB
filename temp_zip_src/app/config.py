import os

# Calculate project base directory relative to config.py location
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, "data", "training_data.sqlite3")
DB_PATH_POSIX = DB_FILE.replace("\\", "/")
DB_URI = f"file:{DB_PATH_POSIX}?mode=ro"

APP_NAME = "Mini Financial Audit Tool"
API_PREFIX = "/api/v1"

# Strict PII Blocklist to prevent raw data exposure
PII_BLOCKLIST = {
    "members": ["full_name", "national_id", "email", "phone", "address"],
    "deposit_accounts": ["account_id"],
    "loan_contracts": ["contract_id"],
    "transactions": ["account_id", "operator_id", "workstation_id"]
}

REPORT_JSON_PATH = os.path.join(BASE_DIR, "output", "audit_summary_report.json")
