# Changelog

## [Unreleased] - 2026-09-17

### Added / Changed (Approved Gap Fixes)
- **Configurable Dataset Path**: ปรับปรุง [`app/config.py`](file:///d:/AI_AUDIT_LAB/app/config.py), [`audit_suite.py`](file:///d:/AI_AUDIT_LAB/audit_suite.py) และ [`cashflow_drain.py`](file:///d:/AI_AUDIT_LAB/cashflow_drain.py) ให้รองรับการเปลี่ยน Dataset Path ผ่าน Environment Variable (`AUDIT_DB_PATH`, `AUDIT_DB_URI`) และ Relative Path คำนวณจาก `BASE_DIR`
- **Read-Only Safety Guarantee**: กำชับการต่อเชื่อมฐานข้อมูลแบบ Read-Only (`mode=ro`) ป้องกันการแก้ไข Source Database

### Regression Tests Passed
- `python audit_suite.py` — ผ่าน 100%
- `python cashflow_drain.py` — ผ่าน 100%
- `python -m pytest` — ผ่าน 100%

### Constraints & Security Guarantees
- ไม่มีการเปิด Raw Data หรือ PII
- ไม่มีการเพิ่ม External Package หรือ Dependencies ใหม่
- คง Parameterized Query และ Audit Logic เดิมทั้งหมด
