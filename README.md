# Mini Financial Audit Tool

ระบบเครื่องมือตรวจสอบข้อมูลการเงินย่อย (Audit Suite & Web Dashboard) ที่เน้นความมั่นคงปลอดภัยของข้อมูลตามมาตรฐาน Read-Only และ Zero PII Leakage

## คุณสมบัติหลัก (Key Features)
- **Read-Only SQLite Database Connection**: เชื่อมต่อฐานข้อมูลผ่าน URI `file:...mode=ro` ป้องกันการแก้ไขหรือลบข้อมูลต้นทาง 100%
- **Dynamic Dataset Configuration**: สามารถเปลี่ยน Dataset ได้ผ่าน Environment Variable หรือ Relative Path
- **Aggregate-Only Security**: แสดงเฉพาะผลลัพธ์การสรุปเชิงสถิติ (Count, Sum, Avg) ไม่เปิดเผย Raw Data หรือ PII

## วิธีการใช้งาน (How to Run)

### 1. เรียกใช้งานผ่าน CLI Script
```bash
# รันชุดตรวจสอบ Audit Suite หลัก
python audit_suite.py

# รันชุดตรวจจับ Cashflow Drain (พร้อมพารามิเตอร์)
python cashflow_drain.py --large_in_min 500000 --outflow_ratio_min 0.80 --window_days 3
```

### 2. เรียกใช้งานผ่าน Web Dashboard (FastAPI / Uvicorn)
```bash
python -m uvicorn app.main:app --reload
```
เข้าใช้งานผ่านเบราว์เซอร์ที่ `http://127.0.0.1:8000`

## การเปลี่ยน Dataset Path (Changing Dataset)
คุณสามารถเปลี่ยนตำแหน่งฐานข้อมูลได้โดยไม่ต้องแก้ไข Code ผ่าน Environment Variable:
```bash
# บน Linux/macOS
export AUDIT_DB_PATH="file:data/custom_dataset.sqlite3?mode=ro"

# บน Windows PowerShell
$env:AUDIT_DB_PATH="file:data/custom_dataset.sqlite3?mode=ro"
```
