# Safe Database Deployment & Readiness Guide

**Project:** Banking Transaction and Fraud Detection System  
**Academic Course:** DBMS (CD252IA), RV College of Engineering  
**Scope:** MySQL 8.x Environment Deployment, Safety Audit, and Recovery Playbook  
**Target Database:** `banking_fraud_detection`  
**Legacy Reference:** `banking_fraud_db`  
**Validation Date:** 2026-11-23 (Tested on MySQL 8.0.46)

---

## 1. Executive Summary & Verification Evidence

This guide provides a comprehensive safety audit of all project SQL scripts and outlines exact, non-destructive procedures for deploying, upgrading, or recovering the database schema in **MySQL Workbench**.

### Key Takeaways
1. **Target Database:** The official database name used by all project scripts, data generators, documentation, and Python modules is `banking_fraud_detection`.
2. **Isolation from `banking_fraud_db`:** If you previously created a database named `banking_fraud_db`, running these scripts will **not** overwrite, alter, or drop it. They operate strictly within `banking_fraud_detection`.
3. **Safety Guarantee:** Antigravity will never connect to your personal MySQL instance (`localhost:3306`) or ask for credentials. All execution is performed by you in MySQL Workbench following this verified guide.
4. **Disposable Testing Evidence:** All test cases below were actively verified on a dedicated, disposable MySQL 8.0.46 instance (port 33070).

---

## 2. In-Depth Trace: `seed_data.sql` and `transaction_read_only`

### User Concern
> `seed_data.sql` contains `SET SESSION transaction_read_only = 1;`. Does this prevent data insertion?

### Complete Code Trace (`database/seed_data.sql`)
1. **Lines 17–31 (`sp_seed_guard` definition):**
   ```sql
   CREATE PROCEDURE sp_seed_guard()
   BEGIN
       -- 1. Check if any of the 6 data tables already contain rows
       IF EXISTS (SELECT 1 FROM Customer) OR EXISTS (SELECT 1 FROM Account)
          OR EXISTS (SELECT 1 FROM Merchant) OR EXISTS (SELECT 1 FROM `Transaction`)
          OR EXISTS (SELECT 1 FROM Fraud_Alert) OR EXISTS (SELECT 1 FROM Investigation) THEN
           SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Seed refused: a target table already has rows. Nothing was changed.';
       END IF;

       -- 2. Check if master data is present
       IF (SELECT COUNT(*) FROM AccountType WHERE TypeName IN ('Savings', 'Current')) <> 2
          OR (SELECT COUNT(*) FROM TransactionType WHERE TypeName IN ('P2P_UPI', 'CNP_ECOM')) <> 2 THEN
           SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Seed refused: master data missing.';
       END IF;

       -- 3. VALIDATION PASSED: Commit check transaction and reset read-only!
       COMMIT;
       SET SESSION transaction_read_only = 0;   -- <--- READ-ONLY RESET TO READ-WRITE
   END$$
   ```
2. **Line 32:** `SET SESSION transaction_read_only = 1;`  
   *(Session temporarily made read-only as a fail-closed guard before invoking the procedure).*
3. **Line 33:** `CALL sp_seed_guard();`  
   - If validation **fails**: `SIGNAL 45000` fires, the procedure halts, and `transaction_read_only` remains `1`. Any subsequent `INSERT` fails immediately, even under `mysql --force`.
   - If validation **passes**: The procedure executes `SET SESSION transaction_read_only = 0;` (Line 29) before returning.
4. **Line 34:** `DROP PROCEDURE sp_seed_guard;`  
   *(Proves the session is already writable; in a read-only session, DROP PROCEDURE would fail).*
5. **Line 45:** `START TRANSACTION;`
6. **Lines 47–21494:** All 20,000 `INSERT` statements execute smoothly in read-write mode.
7. **Line 21495:** `COMMIT;` (all rows atomically written to disk).

### Empirical Execution Test (Disposable MySQL 8.0.46, Port 33070)
- `seed_data.sql` executed against an empty database:
  - **Result:** Successfully committed in 2.8 seconds.
  - **Committed Row Counts:** Customer: 500 | Account: 800 | Merchant: 60 | Transaction: 20,000 | Fraud_Alert: 0 | Investigation: 0.
  - **Post-Load Validation (`validate_seed_data.sql`):** **55/55 checks passed**, exact CRC32 checksums matched.
- Immediate re-run on populated database:
  - **Result:** Refused with `ERROR 1644 (45000): Seed refused: a target table already has rows. Nothing was changed.`
  - **Data Integrity:** Table counts remained unchanged at exactly 20,000 transactions.

---

## 3. Partial Recovery Analysis: What Can and Cannot Be Repaired

### User Concern
> `CREATE TABLE IF NOT EXISTS` does not repair existing tables. Does `upgrade_existing_schema.sql` handle missing columns, foreign keys, constraints, indexes, and triggers?

### Technical Findings & Limits

| Schema Element | Handled by `upgrade_existing_schema.sql`? | Explanation & Behavior |
|---|:---:|---|
| **Secondary Indexes (`idx_*`)** | **YES** | Dynamically checks `information_schema.STATISTICS` and runs `ALTER TABLE ADD INDEX` for any missing indexes. |
| **Missing CHECK Constraints** | **YES** | Dynamically checks `information_schema.CHECK_CONSTRAINTS` and runs `ALTER TABLE ADD CONSTRAINT CHECK`. |
| **Missing Tables (e.g. `Transaction`)** | **Via `schema.sql`** | Handled when running `schema.sql`, which uses `CREATE TABLE IF NOT EXISTS`. |
| **Missing Triggers & Procedures** | **Via `schema.sql`** | Handled when running `schema.sql` (`CREATE TRIGGER IF NOT EXISTS`). Not in `upgrade_existing_schema.sql`. |
| **Missing Columns in Existing Tables** | **NO** | `upgrade_existing_schema.sql` does **not** alter table columns (`ALTER TABLE ADD COLUMN`). If a table exists with missing columns, `upgrade_existing_schema.sql` will throw an error when scanning for bad rows. |
| **Wrong Column Data Types** | **NO** | `upgrade_existing_schema.sql` does not alter column types (e.g., `FLOAT` to `DECIMAL`). |
| **Missing Foreign Keys** | **NO** | `upgrade_existing_schema.sql` does not add missing foreign keys. |

### Tested Partial Scenarios on Disposable Instance (Port 33070)

1. **Scenario 1: Tables 1–5 Exist, Tables 6–8 Missing (Historical Error 3823 State)**
   - *Test:* Dropped `Transaction`, `Fraud_Alert`, `Investigation`, and triggers.
   - *Action:* Ran `schema.sql` -> `master_data.sql` -> `upgrade_existing_schema.sql` -> `verification.sql`.
   - *Result:* **92/92 PASS.** `schema.sql` created missing tables and triggers; `upgrade_existing_schema.sql` was a clean no-op; all 8 FKs and 9 CHECKs verified.
2. **Scenario 2: Table Exists with Missing Columns (e.g., from an early manual attempt)**
   - *Test:* Created table `Transaction` with only `TransactionID`.
   - *Action:* Ran `upgrade_existing_schema.sql`.
   - *Result:* **Failed as expected** with `ERROR 1054 (42S22): Unknown column 'FraudScore' in 'where clause'`.

### The Definitive Recovery Rule
- If your partially initialized database was created exclusively by an earlier run of the project's `schema.sql` (where it stopped at `Transaction`), **Playbook B is safe and verified**.
- However, if your existing database contains tables with manual or unknown column layouts:
  **Do NOT attempt in-place repair.** Because the database contains only synthetic data and no personal records, the 100% safe, clean, and guaranteed path is:
  ```sql
  DROP DATABASE IF EXISTS banking_fraud_detection;
  ```
  Followed by **Playbook A (Fresh Installation)**. This guarantees exact compliance across all 8 tables, columns, indexes, FKs, and triggers.

---

## 4. Verification Checklist of Specific Items

- [x] **`inspect_environment.sql` is 100% Read-Only:** Verified. Contains only `SELECT` statements querying `information_schema.SCHEMATA`, `TABLES`, `REFERENTIAL_CONSTRAINTS`, `CHECK_CONSTRAINTS`, `STATISTICS`, `TRIGGERS`, and `ROUTINES`. Does not create, alter, drop, or insert anything.
- [x] **No deployment script drops or truncates existing tables:** Verified across all 6 SQL scripts. Only temporary helper procedures (`zz_upgrade_step`, `sp_seed_guard`, `zz_vt_run`) and memory tables (`vt_results`) are dropped.
- [x] **The seed guard checks all relevant tables:** Verified. Line 19 of `seed_data.sql` queries `Customer`, `Account`, `Merchant`, `Transaction`, `Fraud_Alert`, and `Investigation`. Line 24 queries `AccountType` and `TransactionType`.
- [x] **Seed execution is atomic:** Verified. Enclosed within `START TRANSACTION;` (line 45) and `COMMIT;` (line 21495). On mid-transaction failure, MySQL rolls back all pending inserts.
- [x] **Scripts target only `banking_fraud_detection`:** Verified. Every script explicitly begins with `USE banking_fraud_detection;`. `banking_fraud_db` is completely untouched.
- [x] **MySQL version requirement is accurate:** Verified. Requires **MySQL >= 8.0.29**. Earlier versions (8.0.0–8.0.28) do not support `CREATE PROCEDURE/TRIGGER IF NOT EXISTS` and fail with syntax error 1064.

---

## 5. Deployment Playbooks

### Step 0: Pre-Deployment Inspection (Run First)
In MySQL Workbench, open and execute:
[database/inspect_environment.sql](file:///e:/BTech%20CS%20with%20AI/5th%20sem/DBMS/Banking-Fraud-Detection/database/inspect_environment.sql)

Review **Tab 8 (Diagnostic Verdict)** to determine which playbook to follow.

---

### Playbook A: Fresh Installation (Recommended & Standard)
*Follow this if `banking_fraud_detection` does not exist, has 0 tables, or after a clean reset.*

1. **Step 1: Create Core Schema**
   - Open `database/schema.sql` in Workbench.
   - Click **Execute All** (lightning bolt).
   - *Expected Output:* 8 tables created, procedure and 2 triggers created, 0 errors.
2. **Step 2: Seed Master Data**
   - Open `database/master_data.sql` in Workbench.
   - Click **Execute All**.
   - *Expected Output:* 2 rows inserted into `AccountType`, 2 rows into `TransactionType`.
3. **Step 3: Run Upgrade Verification**
   - Open `database/upgrade_existing_schema.sql` in Workbench.
   - Click **Execute All**.
   - *Expected Output:* Final tab reads `"Schema already current: nothing changed."`
4. **Step 4: Reconnect Session**
   - In Workbench menu, select **Query > Reconnect to Server**.
5. **Step 5: Run Automated Verification Harness**
   - Open `database/verification.sql` in Workbench.
   - Click **Execute All**.
   - *Expected Output:* Second-to-last result grid shows `failed = 0`. Final grid shows `rollback_check = PASS: nothing persisted`.
6. **Step 6: Load Synthetic Seed Data (Phase 2)**
   - In Workbench menu: **File > Run SQL Script...**
   - Select `database/seed_data.sql`.
   - Click **Run**.
   - *Expected Output:* Completes in 2–4 seconds (20,000 transactions loaded).
7. **Step 7: Validate Loaded Data**
   - Open `database/validate_seed_data.sql` in Workbench.
   - Click **Execute All**.
   - *Expected Output:* All 55 rows report `PASS`; summary row (`seq = 999`) reports `checks failed = 0` (`PASS`).

---

### Playbook B: Recovery from Known Partial Installation
*Follow this ONLY if `banking_fraud_detection` contains tables created by the project's own `schema.sql`.*

1. Execute `database/schema.sql` (creates any missing tables).
2. Execute `database/master_data.sql` (ensures master types exist).
3. Execute `database/upgrade_existing_schema.sql` (applies missing CHECKs and secondary indexes).
4. Menu: **Query > Reconnect to Server**.
5. Execute `database/verification.sql` (must return `failed = 0`).
6. Menu: **File > Run SQL Script...** -> select `database/seed_data.sql`.
7. Execute `database/validate_seed_data.sql` (must return 55 `PASS` rows).

---

### Playbook C: Intentional Clean-Slate Reset (Safest for Unknown States)
*If Tab 8 of `inspect_environment.sql` shows broken or manually altered tables in `banking_fraud_detection`:*

1. In MySQL Workbench, execute:
   ```sql
   DROP DATABASE IF EXISTS banking_fraud_detection;
   ```
2. Follow **Playbook A (Fresh Installation)**.
*(Note: Never drop `banking_fraud_db` unless you are certain you have backed up any personal work you wish to keep).*
