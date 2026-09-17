import sqlite3
import json
import os
import math
from datetime import datetime

DB_PATH = "file:data/training_data.sqlite3?mode=ro"
OUTPUT_DIR = "output"
JSON_REPORT_PATH = os.path.join(OUTPUT_DIR, "audit_summary_report.json")
MD_REPORT_PATH = os.path.join(OUTPUT_DIR, "audit_summary_report.md")

def get_connection():
    return sqlite3.connect(DB_PATH, uri=True)

def run_reconciliation_module(conn):
    """
    Module 1: Subledger vs General Ledger (GL) Reconciliation
    """
    cursor = conn.cursor()
    findings = []
    
    # Check 1: gl_daily readiness status and differences
    cursor.execute("""
        SELECT gl_date, subledger_net, gl_net, difference_amount, readiness_status, note
        FROM gl_daily
        WHERE difference_amount != 0 OR readiness_status != 'READY'
        ORDER BY gl_date
    """)
    gl_daily_diffs = cursor.fetchall()
    
    gl_daily_issues = []
    for row in gl_daily_diffs:
        gl_daily_issues.append({
            "gl_date": row[0],
            "subledger_net": row[1],
            "gl_net": row[2],
            "difference_amount": row[3],
            "readiness_status": row[4],
            "note": row[5]
        })
        
    # Check 2: Sum of deposit_accounts balance vs GL Trial Balance
    cursor.execute("""
        SELECT SUM(current_balance) FROM deposit_accounts
    """)
    subledger_deposit_total = cursor.fetchone()[0] or 0.0
    
    cursor.execute("""
        SELECT account_id, debit_amount, credit_amount, period_end_date
        FROM gl_trial_balance
    """)
    tb_rows = cursor.fetchall()
    tb_summary = []
    for row in tb_rows:
        tb_summary.append({
            "account_id": row[0],
            "debit_amount": row[1],
            "credit_amount": row[2],
            "period_end_date": row[3]
        })
        
    return {
        "gl_daily_issues_count": len(gl_daily_issues),
        "gl_daily_issues": gl_daily_issues,
        "subledger_deposit_total": subledger_deposit_total,
        "gl_trial_balance_summary": tb_summary
    }

def run_anomaly_module(conn):
    """
    Module 2: Transaction Anomaly & Fraud Detection
    """
    cursor = conn.cursor()
    
    # 1. Non-NORMAL record status (e.g. CANCELLED, REVERSED)
    cursor.execute("""
        SELECT transaction_id, account_id, transacted_at, transaction_code, direction, amount, record_status, channel, operator_id, workstation_id
        FROM transactions
        WHERE record_status != 'NORMAL'
    """)
    inactive_txs = [
        {
            "transaction_id": r[0],
            "account_id": r[1],
            "transacted_at": r[2],
            "transaction_code": r[3],
            "direction": r[4],
            "amount": r[5],
            "record_status": r[6],
            "channel": r[7],
            "operator_id": r[8],
            "workstation_id": r[9]
        } for r in cursor.fetchall()
    ]
    
    # 2. Duplicate source references
    cursor.execute("""
        SELECT source_ref, COUNT(*) as cnt
        FROM transactions
        GROUP BY source_ref
        HAVING cnt > 1
    """)
    duplicate_refs = [{"source_ref": r[0], "count": r[1]} for r in cursor.fetchall()]
    
    # 3. Off-hours transactions (Outside 08:00 - 17:00 or weekends)
    cursor.execute("""
        SELECT transaction_id, transacted_at, amount, channel, operator_id
        FROM transactions
    """)
    all_txs = cursor.fetchall()
    off_hours_txs = []
    amounts = []
    
    for r in all_txs:
        tx_id, tx_time_str, amt, channel, op_id = r
        amounts.append(amt)
        try:
            # ISO format parsing e.g. 2026-01-15 18:30:00 or 2026-01-15T18:30:00
            clean_time_str = tx_time_str.replace("T", " ")
            dt = datetime.strptime(clean_time_str.split(".")[0], "%Y-%m-%d %H:%M:%S")
            # Weekend: Saturday(5), Sunday(6) or Hour < 8 or Hour >= 17
            if dt.weekday() >= 5 or dt.hour < 8 or dt.hour >= 17:
                off_hours_txs.append({
                    "transaction_id": tx_id,
                    "transacted_at": tx_time_str,
                    "amount": amt,
                    "channel": channel,
                    "operator_id": op_id,
                    "reason": "Weekend" if dt.weekday() >= 5 else f"Off-hour ({dt.hour:02d}:00)"
                })
        except Exception:
            pass

    # 4. Statistical Outliers (Z-score > 3)
    outliers = []
    if amounts:
        mean_amt = sum(amounts) / len(amounts)
        variance = sum((x - mean_amt) ** 2 for x in amounts) / len(amounts)
        std_dev = math.sqrt(variance) if variance > 0 else 0
        
        if std_dev > 0:
            for r in all_txs:
                tx_id, tx_time_str, amt, channel, op_id = r
                z_score = (amt - mean_amt) / std_dev
                if z_score > 3.0:
                    outliers.append({
                        "transaction_id": tx_id,
                        "amount": amt,
                        "z_score": round(z_score, 2),
                        "operator_id": op_id
                    })

    # 5. High volume operator activity
    cursor.execute("""
        SELECT operator_id, COUNT(*) as tx_count, SUM(amount) as total_amount
        FROM transactions
        GROUP BY operator_id
        ORDER BY tx_count DESC
    """)
    operator_summary = [{"operator_id": r[0], "tx_count": r[1], "total_amount": r[2]} for r in cursor.fetchall()]

    return {
        "inactive_transactions_count": len(inactive_txs),
        "inactive_transactions": inactive_txs,
        "duplicate_references_count": len(duplicate_refs),
        "duplicate_references": duplicate_refs,
        "off_hours_transactions_count": len(off_hours_txs),
        "off_hours_transactions": off_hours_txs[:15], # sample top 15
        "statistical_outliers_count": len(outliers),
        "statistical_outliers": outliers,
        "operator_summary": operator_summary
    }

def run_loan_risk_module(conn):
    """
    Module 3: Loan Portfolio Risk & Integrity Audit
    """
    cursor = conn.cursor()
    
    # 1. Outstanding amount > Principal amount
    cursor.execute("""
        SELECT contract_id, member_id, principal_amount, outstanding_amount, started_date, contract_status
        FROM loan_contracts
        WHERE outstanding_amount > principal_amount
    """)
    over_principal = [
        {
            "contract_id": r[0],
            "member_id": r[1],
            "principal_amount": r[2],
            "outstanding_amount": r[3],
            "started_date": r[4],
            "contract_status": r[5]
        } for r in cursor.fetchall()
    ]
    
    # 2. Loan Contracts Summary
    cursor.execute("""
        SELECT 
            COUNT(*) as total_contracts,
            SUM(principal_amount) as total_principal,
            SUM(outstanding_amount) as total_outstanding,
            MIN(started_date) as earliest_date,
            MAX(started_date) as latest_date
        FROM loan_contracts
    """)
    summary_row = cursor.fetchone()
    portfolio_summary = {
        "total_contracts": summary_row[0],
        "total_principal": summary_row[1],
        "total_outstanding": summary_row[2],
        "earliest_date": summary_row[3],
        "latest_date": summary_row[4]
    }
    
    return {
        "over_principal_contracts_count": len(over_principal),
        "over_principal_contracts": over_principal,
        "portfolio_summary": portfolio_summary
    }

def generate_reports(reconcile_data, anomaly_data, loan_data):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    report_json = {
        "audit_timestamp": datetime.now().isoformat(),
        "reconciliation_module": reconcile_data,
        "anomaly_module": anomaly_data,
        "loan_risk_module": loan_data
    }
    
    with open(JSON_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report_json, f, indent=2, ensure_ascii=False)

    md_content = f"""# Executive Audit Summary Report

Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Fact (ข้อเท็จจริง)
- **Reconciliation Module:**
  - พบรายการใน `gl_daily` ที่มีผลต่างหรือไม่พร้อมประมวลผล จำนวน **{reconcile_data['gl_daily_issues_count']}** รายการ
  - ยอดรวมเงินฝากใน Subledger (`deposit_accounts`): **{reconcile_data['subledger_deposit_total']:,.2f}** บาท
- **Anomaly Detection Module:**
  - รายการสถานะไม่ปกติ (`record_status` != NORMAL): **{anomaly_data['inactive_transactions_count']}** รายการ
  - รายการอ้างอิงซ้ำ (`duplicate source_ref`): **{anomaly_data['duplicate_references_count']}** รายการ
  - รายการนอกเวลาทำการ / วันหยุด (Off-hours): **{anomaly_data['off_hours_transactions_count']}** รายการ
  - รายการมูลค่าสูงผิดปกติเชิงสถิติ (Outliers, Z-score > 3): **{anomaly_data['statistical_outliers_count']}** รายการ
- **Loan Portfolio Risk Module:**
  - จำนวนสัญญาเงินกู้ทั้งหมด: **{loan_data['portfolio_summary']['total_contracts']}** สัญญา
  - ยอดเงินกู้ตามสัญญา (Principal): **{loan_data['portfolio_summary']['total_principal']:,.2f}** บาท
  - ยอดหนี้คงเหลือ (Outstanding): **{loan_data['portfolio_summary']['total_outstanding']:,.2f}** บาท
  - สัญญาที่มียอดหนี้ค้างชำระเกินวงเงินกู้ (Outstanding > Principal): **{loan_data['over_principal_contracts_count']}** สัญญา

## Assumption (ข้อสันนิษฐาน)
- รายการนอกเวลาทำการส่วนใหญ่เกิดขึ้นนอกเวลา 08:00 - 17:00 น. หรือในวันเสาร์-อาทิตย์ ซึ่งอาจเป็นระบบอัตโนมัติ (Batch Process) หรือมีความเสี่ยงจากการเข้าถึงระบบนอกเวลา
- รายการที่มีสถานะไม่ปกติหรือมี `duplicate source_ref` อาจเกิดจากการยกเลิกรายการ (Reversal) หรือข้อผิดพลาดทางเทคนิคในระบบบันทึกธุรกรรม

## Unknown (สิ่งที่ไม่ทราบ / ต้องตรวจสอบเพิ่มเติม)
- สาเหตุที่ชัดเจนของความต่างใน `gl_daily` (ต้องลงรายละเอียดเชิงลึกในบันทึก `note` ของแต่ละรายการ)
- สิทธิ์และบทบาทของผู้ใช้งาน (`operator_id`) ที่ทำรายการนอกเวลาทำการ

## Recommendation (ข้อเสนอแนะ)
1. **กระทบยอด GL:** ให้ฝ่ายบัญชีทำการตรวจสอบรายการใน `gl_daily` ที่ถูกระบุว่ามีผลต่าง เพื่อทำรายการปรับปรุงบัญชี (Adjusting Entries)
2. **ควบคุมความเสี่ยงการทำรายการ:** ตรวจสอบและจำกัดสิทธิ์ `operator_id` ที่ดำเนินรายการนอกเวลาทำการ หรือรายการที่มี Z-score สูงผิดปกติ
3. **ตรวจสอบระบบควบคุมภายในของ Subledger:** สอบทานกระบวนการออก `source_ref` เพื่อป้องกันรายการซ้ำในระบบ
"""

    with open(MD_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(md_content)

def main():
    print("[INFO] Starting Financial Audit Suite...")
    conn = get_connection()
    try:
        reconcile_data = run_reconciliation_module(conn)
        print(f"[OK] Reconciliation Module Completed. GL Issues found: {reconcile_data['gl_daily_issues_count']}")
        
        anomaly_data = run_anomaly_module(conn)
        print(f"[OK] Anomaly Module Completed. Inactive txs: {anomaly_data['inactive_transactions_count']}, Off-hours: {anomaly_data['off_hours_transactions_count']}, Outliers: {anomaly_data['statistical_outliers_count']}")
        
        loan_data = run_loan_risk_module(conn)
        print(f"[OK] Loan Risk Module Completed. Total contracts: {loan_data['portfolio_summary']['total_contracts']}")
        
        generate_reports(reconcile_data, anomaly_data, loan_data)
        print(f"[SUCCESS] Audit Reports generated successfully in '{OUTPUT_DIR}' directory.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
