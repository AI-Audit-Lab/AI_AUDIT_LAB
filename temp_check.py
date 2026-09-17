"""Temporary diagnostic — aggregate checks only, no raw rows or PII."""
import sqlite3

conn = sqlite3.connect("file:data/training_data.sqlite3?mode=ro", uri=True)
cur = conn.cursor()

# 1. Distinct direction values + counts
cur.execute(
    "SELECT direction, COUNT(*) as cnt, SUM(amount) as total "
    "FROM transactions WHERE record_status='NORMAL' GROUP BY direction ORDER BY direction"
)
print("Direction distribution (NORMAL records):")
for r in cur.fetchall():
    print(f"  direction={r[0]!r:<10}  count={r[1]:>5}  total={r[2]:>15,.2f}")

# 2. Amount range
cur.execute("SELECT MAX(amount), MIN(amount) FROM transactions WHERE record_status='NORMAL'")
r = cur.fetchone()
print(f"\nAmount range (NORMAL): max={r[0]:,.2f}  min={r[1]:,.2f}")

# 3. Max single-account DEP per day
cur.execute(
    "SELECT substr(transacted_at,1,10) as day, account_id, SUM(amount) as daily_in "
    "FROM transactions "
    "WHERE record_status='NORMAL' AND direction='DEP' "
    "GROUP BY day, account_id "
    "ORDER BY daily_in DESC "
    "LIMIT 5"
)
print("\nTop-5 daily DEP totals per account (no PII: just amounts):")
for i, r in enumerate(cur.fetchall(), 1):
    print(f"  #{i}  day={r[0]}  daily_in={r[2]:>12,.2f}")

conn.close()
print("\n[DONE]")
