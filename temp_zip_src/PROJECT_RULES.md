# PROJECT_RULES.md

> These are **project-specific rules** for this workspace.
> They complement — and must never weaken — the Mandatory Baseline Rules already active in this workspace.

---

## 1. Communication & Language

- Communicate with the human user **primarily in Thai**.
- English technical terms (e.g., column names, function names, library names) may be used when they aid clarity.
- Documents or instructions intended primarily for AI/Agent consumption (e.g., SKILL.md, config files, code comments) **must be written in English**.
- When explaining technical topics, **start with a plain-language summary** before going into technical detail.
- When presenting analysis results, **always separate**:
  - **Fact** — directly observed from data
  - **Assumption** — inferred or estimated, not verified
  - **Unknown** — insufficient information to determine
  - **Recommendation** — AI suggestion, subject to human judgment

> **[ภาษาไทย]** สื่อสารกับผู้ใช้เป็นภาษาไทย ใช้ศัพท์เทคนิค English ได้เมื่อช่วยให้ชัดขึ้น เอกสารสำหรับ AI ให้เขียนเป็น English และเวลาเสนอผลวิเคราะห์ให้แยก Fact / Assumption / Unknown / Recommendation ทุกครั้ง

---

## 2. Project Data Sources

- The **primary training database** for this project is: `data/training_data.sqlite3`
- Additional source data or external data sources **may only be accessed when explicitly introduced or approved by the human user** in the current session.
- Data source read/write safety is governed by the Baseline Rules — no repetition here.

> **[ภาษาไทย]** ฐานข้อมูลหลักของ Project คือ `data/training_data.sqlite3` การเข้าถึงข้อมูลแหล่งอื่นต้องได้รับการระบุหรืออนุญาตจากผู้ใช้ก่อนเสมอ

---

## 3. File Layout & Outputs

- **Reports, exports, metrics, and intermediate analysis artifacts** must be saved under `output/`.
- **Source code, configuration files, and test files** must NOT be placed inside `output/`.
- Source code, script, and technical document **filenames must use English** (snake_case or kebab-case).

```
project-root/
├── data/               ← source data (read-only)
├── output/             ← reports, exports, analysis artifacts
├── src/ or scripts/    ← source code and scripts
└── PROJECT_RULES.md
```

> **[ภาษาไทย]** ผลลัพธ์ รายงาน และ artifacts ให้เก็บใน `output/` เท่านั้น ชื่อไฟล์โค้ดและเอกสารเทคนิคให้ใช้ภาษา English

---

## 4. Path Portability

- Use **relative paths by default** in all scripts, configs, and documents.
- Avoid machine-specific absolute paths (e.g., `C:\Users\...`, `file:///Users/...`).
- Absolute paths are permitted only when technically necessary **and** explicitly specified by the human user.

> **[ภาษาไทย]** ใช้ relative paths เป็นค่าเริ่มต้น หลีกเลี่ยง absolute paths ที่ผูกกับเครื่องใดเครื่องหนึ่ง เว้นแต่จำเป็นและผู้ใช้ระบุชัดเจน

---

## 5. Baseline Relationship

- This project operates under the **Mandatory Baseline Rules** active in this workspace.
- Project-specific rules in this file **extend** the Baseline; they must not override, weaken, or contradict any Mandatory Baseline requirement.
- In case of conflict between a project rule and a Baseline rule, the **Baseline rule takes precedence**.

> **[ภาษาไทย]** Project Rules นี้ทำงานร่วมกับ Mandatory Baseline โดยห้ามลดทอนกฎด้าน Safety, Security หรือ Data Protection ของ Baseline ในกรณีที่ขัดแย้งกัน ให้ยึด Baseline เป็นหลัก
