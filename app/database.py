import sqlite3
from app.config import DB_URI

def get_db_connection():
    """Connect to SQLite strictly in Read-Only mode using relative URI."""
    return sqlite3.connect(DB_URI, uri=True)

def check_db_status():
    """Check database connection status and return table count without fetching raw rows."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT count(name) FROM sqlite_master WHERE type='table';")
        table_count = cursor.fetchone()[0]
        conn.close()
        return {
            "status": "Connected (Read-Only)",
            "connected": True,
            "table_count": table_count,
            "mode": "read-only"
        }
    except Exception as e:
        return {
            "status": f"Disconnected: {str(e)}",
            "connected": False,
            "table_count": 0,
            "mode": "disconnected"
        }

def get_safe_aggregate_metrics():
    """
    Executes aggregate-only SQL queries (COUNT, SUM, AVG).
    STRICT SECURITY: Zero SELECT * or raw row dumps allowed.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Member counts by status
        cursor.execute("""
            SELECT member_status, COUNT(*) 
            FROM members 
            GROUP BY member_status
        """)
        member_counts = {row[0]: row[1] for row in cursor.fetchall()}
        
        # 2. Deposit accounts aggregate summary
        cursor.execute("""
            SELECT 
                COUNT(*) as total_accounts,
                SUM(current_balance) as total_balance,
                AVG(current_balance) as avg_balance
            FROM deposit_accounts
        """)
        dep_row = cursor.fetchone()
        deposit_summary = {
            "total_accounts": dep_row[0] or 0,
            "total_balance": dep_row[1] or 0.0,
            "avg_balance": round(dep_row[2] or 0.0, 2)
        }
        
        # 3. Loan contracts aggregate summary
        cursor.execute("""
            SELECT 
                COUNT(*) as total_contracts,
                SUM(principal_amount) as total_principal,
                SUM(outstanding_amount) as total_outstanding
            FROM loan_contracts
        """)
        loan_row = cursor.fetchone()
        loan_summary = {
            "total_contracts": loan_row[0] or 0,
            "total_principal": loan_row[1] or 0.0,
            "total_outstanding": loan_row[2] or 0.0
        }
        
        # 4. GL daily readiness aggregate summary
        cursor.execute("""
            SELECT 
                COUNT(*) as total_days,
                SUM(CASE WHEN difference_amount != 0 THEN 1 ELSE 0 END) as diff_days_count,
                SUM(CASE WHEN readiness_status != 'READY' THEN 1 ELSE 0 END) as warning_days_count
            FROM gl_daily
        """)
        gl_row = cursor.fetchone()
        gl_summary = {
            "total_days_logged": gl_row[0] or 0,
            "difference_days_count": gl_row[1] or 0,
            "warning_days_count": gl_row[2] or 0
        }
        
        # 5. Transactions aggregate summary
        cursor.execute("""
            SELECT 
                COUNT(*) as total_transactions,
                SUM(amount) as total_volume,
                SUM(CASE WHEN record_status != 'NORMAL' THEN 1 ELSE 0 END) as non_normal_count
            FROM transactions
        """)
        tx_row = cursor.fetchone()
        transaction_summary = {
            "total_transactions": tx_row[0] or 0,
            "total_volume": tx_row[1] or 0.0,
            "non_normal_count": tx_row[2] or 0
        }

        return {
            "members": member_counts,
            "deposits": deposit_summary,
            "loans": loan_summary,
            "gl": gl_summary,
            "transactions": transaction_summary
        }
    finally:
        conn.close()

def get_data_quality_checks():
    """
    Run 4 data quality rules on the transactions table via data_quality_service.
    Returns aggregate counts only — zero raw rows or PII exposed.
    Database is opened in read-only mode via get_db_connection().
    """
    from app.services.data_quality_service import evaluate_data_quality_rules
    conn = get_db_connection()
    try:
        return evaluate_data_quality_rules(conn)
    finally:
        conn.close()

