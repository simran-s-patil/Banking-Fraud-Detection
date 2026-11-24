# Project Handover: Banking Transaction and Fraud Detection System

**Date:** 2026-11-23  
**Project:** Banking Transaction and Fraud Detection System  
**Academic Context:** DBMS Course (CD252IA), RV College of Engineering  
**Team Members:** Sharvani Mysoremath (1RV24CI113), Janvi S Hegde (1RV24CI145), Simran S Patil (1RV24CI146)  
**Transition:** Migrated development workflow from Claude Code CLI to Google Antigravity.

> **Addendum (2026-11-23, back in Claude Code CLI):** This document's numbers
> were independently re-verified, not accepted as-is — see the addendum at
> the top of `docs/PHASE_TRACKER.md` for the full trace. One discrepancy was
> found and corrected: the disposable instance's `Transaction` table had been
> emptied by later scenario testing (Section 3 below) after this document's
> 55/55 result was recorded, so a live re-check briefly failed 7/55 until the
> instance was rebuilt from `schema.sql` onward. All counts and test totals
> in this document are otherwise accurate and reproduced live. Phase 3 design
> docs (`PHASE3_ML_DESIGN.md`, `ML_FEATURE_DICTIONARY.md`) now exist; `ml/`
> has no training code.

---

## 1. Executive Summary & Status Overview

The project roadmap has been consolidated from the original 8 development phases into **5 comprehensive phases**.

| Phase | Description | Implementation Status | Real DB Verification (port 3306) |
|---|---|---|---|
| **Phase 1: Database Foundation** | ER design, MySQL schema, constraints, indexes, verification script | **Code Complete** (92/92 tests pass on disposable DB) | **Pending User Verification** |
| **Phase 2: Synthetic Data Generation & Population** | Generator, 20k transactions, P2P/CNP mix, fraud patterns, ledger replay, seed scripts | **Code Complete** (74/74 offline tests pass, 55/55 SQL validation pass on disposable DB) | **Pending Data Population** |
| **Phase 3: Fraud Detection ML Pipeline** | Feature engineering, baseline Logistic Regression, Random Forest, metrics & confusion matrix | **Not Started** | N/A |
| **Phase 4: Backend & DBMS Integration** | Python-MySQL connection, triggers, procedures, views, auto-alert pipeline, investigation workflow | **Not Started** | N/A |
| **Phase 5: Application & Final Validation** | Streamlit dashboard, monitoring UI, investigation interface, end-to-end evaluation | **Not Started** | N/A |

### Genuine Completion Assessment:
- **Phase 1**: **Technically complete in code, but NOT verified on the user's real database.** All SQL scripts (`schema.sql`, `master_data.sql`, `upgrade_existing_schema.sql`, `verification.sql`) pass completely on a disposable MySQL 8.0.46 instance. It requires execution confirmation from the user on `localhost:3306`.
- **Phase 2**: **Technically complete in code and offline validation, but data is NOT loaded into the real database.** Seed generation is reproducible (seed 42), passes 74 offline tests and 55 SQL validation checks on the disposable DB. However, the data has not been seeded into the real MySQL database, and one minor trigger edge-case remains unresolved.

---

## 2. Existing Project Directory Structure

```text
Banking-Fraud-Detection/
├── .codegraph/                         # CodeGraph dependency tracking database
│   ├── .gitignore
│   └── codegraph.db
├── CLAUDE.md                           # Legacy Claude Code CLI instructions
├── handoff.md                          # Previous session memory and status notes
├── database/                           # MySQL 8.x schema and verification scripts
│   ├── schema.sql                      # DDL for 8 tables, constraints, inline indexes, triggers
│   ├── master_data.sql                 # Reference data for AccountType and TransactionType
│   ├── upgrade_existing_schema.sql     # Idempotent patch adding missing CHECKs/indexes
│   ├── verification.sql                # 92 positive/negative validation tests inside rolled-back txn
│   ├── seed_data.sql                   # Synthetic data load script (20,000 txns, 4.1 MB)
│   └── validate_seed_data.sql          # Exact fingerprint and assertion validation on loaded data
├── data_generation/                    # Python 3 synthetic data generation suite (stdlib only)
│   ├── config.py                       # Tunable distributions, pools, fraud patterns, tolerances
│   ├── generate_data.py                # Deterministic synthetic data generator (seed 42)
│   ├── validate_data.py                # 74 offline integrity and behavior checks
│   ├── README.md                       # Documentation for data generation
│   └── output/                         # Deterministic outputs generated for seed 42
│       ├── labels.csv                  # Ground truth labels (TransactionID, IsFraud, Scenario, Pattern)
│       ├── opening_balances.csv        # Account opening/closing ledger balances
│       └── manifest.json               # Row counts, parameters, and SHA-256 hashes
└── docs/                               # Project documentation and specifications
    ├── ARCHITECTURE_DECISIONS.md       # Rationale for architectural and schema choices
    ├── Banking_ER_Notes.docx.docx      # Original source specification: ER notes
    ├── Banking_Fraud_Detection_DFD.pdf # Original source specification: Level-1 DFD
    ├── Banking_Requirements.docx.docx  # Original source specification: Requirements & acceptance criteria
    ├── Banking_Synopsis.pdf.pdf        # Original source specification: Synopsis
    ├── DATABASE_DESIGN.md              # Detailed column-level relational specifications
    ├── PHASE2_DATA_GENERATION.md       # Technical specs & test results for Phase 2
    ├── PHASE_TRACKER.md                # Roadmap milestone tracker (consolidated 5-phase)
    ├── PROJECT_CONTEXT.md              # Team, scope constraints, and tech stack details
    └── PROJECT_HANDOVER.md             # This document (Antigravity handover audit)
```

---

## 3. Files Implemented and Roles

### Database Layer (`database/`)
1. `schema.sql`:
   - Creates database `banking_fraud_detection`.
   - Defines 8 normalized tables: `Customer`, `AccountType`, `Account`, `TransactionType`, `Merchant`, `Transaction`, `Fraud_Alert`, `Investigation`.
   - Configures foreign keys with `ON UPDATE RESTRICT ON DELETE RESTRICT` for financial auditability and to avoid MySQL Error 3823.
   - Enforces business rules via `CHECK` constraints (e.g., non-negative balances, positive amounts, valid score ranges, token not containing 12+ PAN digits).
   - Enforces P2P vs CNP business constraints using BEFORE INSERT/UPDATE triggers (`trg_txn_category_bi`, `trg_txn_category_bu`) calling stored procedure `sp_validate_transaction_category`.
2. `master_data.sql`:
   - Seeds `AccountType` (`Savings`, `Current`) and `TransactionType` (`P2P_UPI`, `CNP_ECOM`) idempotently using `INSERT ... SELECT ... WHERE NOT EXISTS`.
3. `upgrade_existing_schema.sql`:
   - Safe migration script that inspects existing tables and applies missing `CHECK` constraints and indexes without dropping tables. Halts safely if invalid rows exist.
4. `verification.sql`:
   - Contains structural inspection, relational JOIN checks, and 92 automated tests (Section G) covering uniqueness, FKs, CHECK constraints, and triggers inside a self-reverting `ROLLBACK` transaction.
5. `seed_data.sql`:
   - Generated dataset containing 500 customers, 800 accounts, 60 merchants, and 20,000 transactions.
   - Guarded by `sp_seed_guard` ensuring it only runs on empty tables and in `STRICT_ALL_TABLES` mode.
6. `validate_seed_data.sql`:
   - 55 read-only SQL validation checks verifying record counts, balance reconciliations, foreign keys, lack of blank strings, and exact CRC32 content fingerprints.

### Data Generation Layer (`data_generation/`)
1. `config.py`: Parameter definitions for 2025 time window, identity pools, fraud ratios (3% fraud, 5% legit look-alikes), and patterns.
2. `generate_data.py`: Deterministic data generator implementing 7 distinct fraud patterns and matched legitimate look-alikes with double-entry ledger bookkeeping.
3. `validate_data.py`: Validates generated artifacts offline across 74 checks (schema rules, distributions, adult age, ledger consistency, zero simple-rule leakage).

---

## 4. Phase-by-Phase Status & Test Evidence

### Phase 1: Database Foundation
- **Target Specifications**: 8 tables, 8 foreign keys, 9 CHECK constraints, 10 secondary indexes, 2 triggers, 1 validation procedure.
- **Verification Evidence (Disposable MySQL 8.0.46 on port 33070)**:
  - 92/92 test cases passed in `verification.sql`.
  - Zero rows persisted after execution (`rollback_check: PASS`).
  - Idempotent execution verified (multiple consecutive runs produce no duplicate errors).
- **Real Database Status (localhost:3306)**:
  - **UNVERIFIED**. An initial run of an early schema draft failed with MySQL error 3823 (`fk_txn_sender` had `ON UPDATE CASCADE` on a column with a CHECK). While fixed in `schema.sql`, the user has not reported the outcome of the corrected script run.

### Phase 2: Synthetic Data Generation and Population
- **Target Specifications**: 500 customers, 800 accounts, 60 merchants, 20,000 transactions (12,024 P2P, 7,976 CNP; 600 fraud, 1,000 legit look-alike edge cases).
- **Verification Evidence (Offline)**:
  - `python data_generation/validate_data.py` executed: **74/74 checks passed**.
  - Verified: No minor customers (<18 yrs), all timestamps in 2025, ledger never overdrawn, all rows unscored (`RiskStatus = 'NOT_SCORED'`), simple detection rules cannot exceed 90% precision.
- **Verification Evidence (Disposable DB)**:
  - Seed loaded cleanly in 1.7 seconds.
  - `validate_seed_data.sql`: **55/55 checks passed**.
  - Guard procedure verified: attempts to reload with `--force` safely rejected (Error 1644).
- **Real Database Status**:
  - **NOT LOADED**. Awaiting user verification of Phase 1 before running `seed_data.sql`.

---

## 5. Consolidated 5-Phase Roadmap Mapping

The original 8-phase plan has been consolidated into 5 coherent phases:

```
[Original Roadmap (8 Phases)]               [Consolidated Roadmap (5 Phases)]
Phase 1: Database Design & Schema     --->   Phase 1: Database Foundation
Phase 2: Synthetic Data Generation    --->   Phase 2: Synthetic Data Generation & Population
Phase 3: Feature Engineering & EDA    ---\
Phase 4: ML Model Training & Eval     --->   Phase 3: Fraud Detection ML Pipeline
Phase 5: Fraud-Scoring Integration    ---\
Phase 6: Backend/Application Layer    --->   Phase 4: Backend & DBMS Integration
Phase 7: Interface (Streamlit/Plotly) ---\
Phase 8: Testing, Documentation, Demo --->   Phase 5: Application & Final Validation
```

### Detailed Phase Scope:
1. **Phase 1: Database Foundation**
   - ER design and relational architecture
   - MySQL 8.x schema, tables, relationships
   - Primary/foreign keys, CHECK constraints, inline indexes, trigger validation
   - SQL verification via automated test harness
2. **Phase 2: Synthetic Data Generation and Population**
   - Python synthetic data generator (reproducible seed)
   - P2P/UPI and CNP/e-commerce transaction generation
   - 7 fraud scenarios and paired legitimate look-alikes
   - Database population, guard procedures, and SQL validation
3. **Phase 3: Fraud Detection ML Pipeline**
   - Feature engineering (velocity, time-of-day, amounts, geographical/IP flags, merchant categories)
   - Data preprocessing & split (excluding post-event data like `Account.Balance` and `opening_balances.csv`)
   - Baseline Logistic Regression model
   - Random Forest classifier
   - Comprehensive model evaluation: Precision, Recall, F1-Score, ROC-AUC, and Confusion Matrix
   - Model artifact persistence (`joblib`)
4. **Phase 4: Backend and DBMS Integration**
   - Python-MySQL database connectivity
   - Automated fraud alert generation pipeline (scoring unscored records, inserting into `Fraud_Alert`)
   - Investigation management workflow (`Investigation` updates, audit trails)
   - SQL views, stored procedures, and triggers for operational monitoring
   - Indexing validation and query optimization
5. **Phase 5: Application and Final Validation**
   - Streamlit interactive dashboard with Plotly charts
   - Real-time transaction monitoring interface
   - Fraud alert review and investigator resolution screens
   - End-to-end system validation against requirements
   - Academic demonstration preparation and documentation

---

## 6. Bugs, Inconsistencies & Technical Nuances

1. **Blank-UPI Trigger Gap (`database/schema.sql:263`)**:
   - In `sp_validate_transaction_category`:
     ```sql
     IF v_type = 'P2P_UPI' THEN
         IF p_receiver_account IS NULL AND NULLIF(TRIM(p_receiver_upi), '') IS NULL THEN
             SIGNAL SQLSTATE '45000' ...
     ```
   - **Gap**: If `p_receiver_account` is provided, a non-null blank string (e.g., `""` or `'   '`) in `ReceiverUPIID` is currently permitted.
   - **Mitigation**: The synthetic generator never generates blank strings, and `validate_seed_data.sql` actively rejects them. However, for complete database integrity, the trigger should check `p_receiver_upi IS NOT NULL AND NULLIF(TRIM(p_receiver_upi), '') IS NULL` independently.
2. **Post-Event Feature Leakage Guard**:
   - `Account.Balance` reflects closing balances after transactions have executed.
   - `data_generation/output/opening_balances.csv` and `Transaction.Status` contain post-event information.
   - **Requirement for Phase 3**: These columns must be strictly excluded from ML training features.
3. **MySQL Version Requirement**:
   - The schema scripts rely on `CREATE PROCEDURE IF NOT EXISTS` and `CREATE TRIGGER IF NOT EXISTS`, requiring **MySQL 8.0.29 or newer**.
4. **Agent Testing Constraint**:
   - Antigravity must never connect to port 3306 or ask for root credentials. Testing by the agent must only use disposable local instances.

---

## 7. Exact Next Steps

### Action Required by User (in MySQL Workbench on localhost:3306):
1. **State Inspection**:
   Run the following query in Workbench to inspect current database state:
   ```sql
   SELECT VERSION();
   USE banking_fraud_detection;
   SHOW TABLES;
   ```
2. **Execute Phase 1 Scripts in Order**:
   - Open and execute `database/schema.sql`.
   - Open and execute `database/master_data.sql`.
   - Open and execute `database/upgrade_existing_schema.sql`.
   - Reconnect to server (`Query > Reconnect to Server`).
   - Open and execute `database/verification.sql`.
   - Confirm in the second-to-last result grid that `failed = 0`, and in the final grid that `rollback_check` is `'PASS: nothing persisted'`.
3. **Load and Validate Synthetic Data (Phase 2)**:
   - Run `database/seed_data.sql` (takes ~2 seconds).
   - Run `database/validate_seed_data.sql` and verify all 55 checks (including `SUMMARY`) return `PASS`.
4. **Report Results**:
   - Share confirmation with the agent to sign off Phase 1 and Phase 2.

### Action Pending User Approval:
- Once the user confirms the verification results and approves moving forward, we will begin **Phase 3: Fraud Detection ML Pipeline**.
