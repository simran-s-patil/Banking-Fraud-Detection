# Banking Transaction and Fraud Detection System

An academic database management and machine learning prototype developed for the **DBMS Course (CD252IA)** at **RV College of Engineering**, Bengaluru.

---

## 👥 Project Team

- **Sharvani Mysoremath** (1RV24CI113)
- **Janvi S Hegde** (1RV24CI145)
- **Simran S Patil** (1RV24CI146)

---

## 📌 Project Overview

This project implements a normalized relational database in **MySQL 8.x** integrated with a Python-based fraud detection pipeline. It handles transaction processing across two primary channels within a unified relational structure:
1. **Real-Time P2P/UPI Transfers** (account-to-account and UPI-addressed payments).
2. **Card-Not-Present (CNP) / E-Commerce Transactions** (merchant transactions with tokenized card references).

The system enforces data integrity through primary keys, foreign keys (`RESTRICT` actions to preserve auditability), multi-column `CHECK` constraints, and category-enforcing database triggers.

---

## 🚀 5-Phase Development Roadmap

The project is structured into five sequential phases:

```
Phase 1: Database Foundation (Complete, Validated on MySQL 8.0)
Phase 2: Synthetic Data Generation & Population (Complete, Validated Offline & SQL)
Phase 3: Fraud Detection ML Pipeline (Feature Engineering, Logistic Regression & Random Forest)
Phase 4: Backend & DBMS Integration (Alert Generation, Investigation Workflows, Optimization)
Phase 5: Application & Final Validation (Streamlit Monitoring UI & End-to-End Demo)
```

- **Phase 1: Database Foundation**  
  - Relational architecture covering 8 entities: `Customer`, `AccountType`, `Account`, `TransactionType`, `Merchant`, `Transaction`, `Fraud_Alert`, `Investigation`.
  - Enforces non-negative balances, PAN protection guards (`NFR-03`), and P2P vs. CNP channel invariants via triggers.
  - Automated test harness with 92 unit and constraint tests running inside an isolated, rolled-back transaction.
- **Phase 2: Synthetic Data Generation & Population**  
  - Deterministic, seeded Python generator producing 20,000 realistic transactions (60% P2P, 40% CNP).
  - Simulates 7 fraud patterns (`high_amount`, `velocity_burst`, `odd_hour`, `fan_out`, `merchant_anomaly`, `card_testing`, `device_geo_change`) and 7 matched legitimate look-alikes.
  - Full double-entry ledger replay ensuring non-negative balances and exact reconciliation.
  - Fail-closed guard (`sp_seed_guard`) and 55-assertion SQL validation suite.
- **Phase 3: Fraud Detection ML Pipeline** *(Upcoming)*  
  - Feature engineering across velocity, time, amount distributions, and merchant category risk.
  - Baseline Logistic Regression and Random Forest classification.
  - Model evaluation via Precision, Recall, F1-Score, and Confusion Matrix.
- **Phase 4: Backend & DBMS Integration** *(Upcoming)*  
  - Automated scoring pipeline and fraud alert creation.
  - Compliance investigator workflow management.
- **Phase 5: Application & Final Validation** *(Upcoming)*  
  - Streamlit dashboard with real-time transaction monitoring and alert review interfaces.

---

## 📂 Repository Structure

```text
Banking-Fraud-Detection/
├── database/                           # MySQL 8.x schema DDL and verification suites
│   ├── schema.sql                      # Core DDL for 8 tables, indexes, constraints, triggers
│   ├── master_data.sql                 # Idempotent reference data seeding
│   ├── upgrade_existing_schema.sql     # Safe schema repair & upgrade script
│   ├── verification.sql                # 92 positive/negative validation tests
│   ├── seed_data.sql                   # 20,000 synthetic transaction records (4.1 MB)
│   ├── validate_seed_data.sql          # 55 SQL assertion checks & content fingerprints
│   └── inspect_environment.sql         # 100% read-only pre-deployment diagnostic tool
├── data_generation/                    # Python synthetic data generation engine
│   ├── config.py                       # Configuration parameters, distributions, and pools
│   ├── generate_data.py                # Deterministic dataset generator (seed 42)
│   ├── validate_data.py                # 74 offline integrity and envelope checks
│   ├── README.md                       # Data generation documentation
│   └── output/                         # Generated artifacts (labels, opening balances, manifest)
├── docs/                               # Architecture, designs, and deployment guides
│   ├── ARCHITECTURE_DECISIONS.md       # Rationale for constraint and schema choices
│   ├── DATABASE_DEPLOYMENT_GUIDE.md    # Deployment runbooks and error handling
│   ├── DATABASE_DESIGN.md              # Column-level schema specification
│   ├── PHASE_TRACKER.md                # 5-phase project milestone tracker
│   ├── PROJECT_CONTEXT.md              # Academic scope, constraints, and requirements
│   ├── PROJECT_HANDOVER.md             # Antigravity migration and audit report
│   ├── PHASE2_DATA_GENERATION.md       # Synthetic dataset generation report
│   ├── Banking_Requirements.docx.docx  # Source requirements specification
│   ├── Banking_ER_Notes.docx.docx      # Source ER specifications
│   ├── Banking_Fraud_Detection_DFD.pdf # Source Level-1 Data Flow Diagram
│   └── Banking_Synopsis.pdf.pdf        # Submitted project synopsis
└── README.md                           # Project documentation
```

---

## 🛠️ Technology Stack

- **Database Engine:** MySQL 8.x (requires >= 8.0.29 for `IF NOT EXISTS` trigger and routine clauses)
- **Database Architecture:** InnoDB, `utf8mb4` encoding, `utf8mb4_0900_ai_ci` collation
- **Programming Language:** Python 3.11+
- **Machine Learning & Analytics:** pandas, NumPy, scikit-learn, joblib
- **Visualization & UI:** Streamlit, Plotly

---

## 🛡️ Database Deployment & Verification

To verify or deploy the database on a local MySQL 8.x server:

1. **Pre-Deployment Inspection:**
   Execute `database/inspect_environment.sql` in MySQL Workbench to confirm version compatibility and examine existing schemas.
2. **Execute Deployment Scripts in Order:**
   ```sql
   database/schema.sql                  -- Creates database and tables
   database/master_data.sql             -- Seeds reference data
   database/upgrade_existing_schema.sql -- Applies missing CHECKs/indexes
   ```
3. **Run Test Harness:**
   Reconnect to the server in Workbench (`Query > Reconnect to Server`), then run:
   ```sql
   database/verification.sql            -- Verifies 92 tests (expected failed = 0, rollback = PASS)
   ```
4. **Populate Synthetic Data:**
   Run `database/seed_data.sql`, followed by `database/validate_seed_data.sql` (all 55 assertions must return `PASS`).

---

## 📜 Academic Integrity & Data Ethics

This project is conducted exclusively using **synthetically generated data**. No real banking accounts, customer identities, credit card numbers, or live banking APIs are utilized. In accordance with ethical constraints (`NFR-12`), fraud prediction scores serve as investigative review signals rather than conclusive proof of fraud.
