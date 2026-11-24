# Phase Tracker: Banking Transaction and Fraud Detection System

**Consolidated Roadmap (5 Phases)**  
Last Updated: 2026-11-23

> **Independent re-verification (2026-11-23, Claude Code CLI session):** The
> Antigravity audit's 92/92 and 55/55 disposable-instance claims below were
> re-run live, not taken on the prior report alone. Found the disposable
> instance (`127.0.0.1:33070`) had drifted into an inconsistent state from
> earlier scenario testing — `Customer`/`Account`/`Merchant` still held rows
> (500/800/60) but `Transaction` had been emptied back to 0, so
> `validate_seed_data.sql` currently failed 7/55. Rebuilt via `DROP DATABASE
> banking_fraud_detection` → `schema.sql` → `master_data.sql` →
> `upgrade_existing_schema.sql` → `verification.sql` (92/92 PASS,
> `rollback_check = PASS`) → `seed_data.sql` (20,000 rows, ~2s) →
> `validate_seed_data.sql` (55/55 PASS) → re-ran `seed_data.sql` once more to
> confirm the guard still refuses a second load (`ERROR 1644`, no data
> changed). This is the same disposable instance from `handoff.md`, port
> 33070 only — `localhost:3306` was never touched. The figures below are
> accurate as code-level and disposable-instance results; they are **not**
> evidence of anything loaded into the user's real database.

> **Deployment-readiness review (2026-11-23, follow-up):** Real-database
> status is still **PENDING** — the user has not reported a result for any
> of the 5 checklist items in `docs/DEPLOYMENT_VERIFICATION_CHECKLIST.md`
> (schema verification, master data, row counts, all 55 seed checks,
> dataset consistency). No SQL was run and no connection was made to
> `localhost:3306` while preparing that checklist. Separately, the Phase 3
> implementation (`ml/`) was audited line-by-line against
> `docs/PHASE3_ML_DESIGN.md`/`docs/ML_FEATURE_DICTIONARY.md`: it matches the
> approved feature list, split dates, and leakage safeguards, with one
> documented deviation (`account_status` dropped — confirmed constant
> `'ACTIVE'` for every transaction in this dataset, so it carried no
> signal) and one gap fixed (`accuracy` is now reported as an explicitly
> secondary metric, per Section 10 of the design doc, never used for model
> selection). `ml/train.py` now tags every run with `--dataset-source` and
> refuses to overwrite an existing run's models/metrics under the same tag
> — the existing disposable-instance artifacts were renamed (not retrained)
> to `*_disposable_33070.*` to fit this scheme. See `ml/README.md`'s
> "Re-running against the real database" section for the exact, safe
> procedure once the checklist above is confirmed. **Phase 4 does not begin
> until the user explicitly approves it, independent of checklist status.**

---

## Roadmap Overview

- [x] **Phase 1: Database Foundation** (Code complete; passes 92/92 tests on disposable DB; **User DB verification pending**)
- [x] **Phase 2: Synthetic Data Generation and Population** (Code complete; passes 74/74 offline tests and 55/55 SQL tests on disposable DB; **Real DB population pending**)
- [x] **Phase 3: Fraud Detection ML Pipeline** (Implemented and run end-to-end against the disposable instance's data, 2026-11-23; RF beats LR baseline; **trained on disposable-instance data only, not the user's real database**)
- [ ] **Phase 4: Backend and DBMS Integration** (Not started)
- [ ] **Phase 5: Application and Final Validation** (Not started)

---

## Phase 1: Database Foundation

**Status:** Code complete and fully verified on disposable MySQL 8.0.46 instance (92/92 tests pass). **User's real database (port 3306) is pending verification.**

### Deliverables & Files
- `database/schema.sql`: Core schema (8 tables, PKs, FKs with RESTRICT, CHECK constraints, inline indexes, triggers, validation procedure).
- `database/master_data.sql`: Master table seeding (`AccountType`, `TransactionType`) with idempotent checks.
- `database/upgrade_existing_schema.sql`: Safe schema patch adding missing CHECKs/indexes without data loss.
- `database/verification.sql`: 92 positive/negative tests executed inside a self-reverting transaction.
- `docs/DATABASE_DESIGN.md`: Schema and entity-relationship specifications.
- `docs/ARCHITECTURE_DECISIONS.md`: Design rationale and constraint justifications.

### Progress & Checklist
- [x] ER design across all 8 required entities finalized.
- [x] Foreign-key referential integrity (`RESTRICT`) verified against MySQL Error 3823.
- [x] Non-negative monetary checks and PAN pattern detection guards (`NFR-03`) implemented.
- [x] P2P vs CNP business constraints enforced via triggers (`trg_txn_category_bi`, `trg_txn_category_bu`).
- [x] 92/92 Section G verification tests passing on disposable instance (`127.0.0.1:33070`).
- [ ] **User Action:** Run `schema.sql`, `master_data.sql`, `upgrade_existing_schema.sql`, and `verification.sql` on `localhost:3306`.
- [ ] **User Action:** Confirm `failed = 0` and `rollback_check = 'PASS: nothing persisted'`.
- Full checklist with expected-vs-actual rows to fill in: `docs/DEPLOYMENT_VERIFICATION_CHECKLIST.md` (sections 1–2).

---

## Phase 2: Synthetic Data Generation and Population

**Status:** Code complete, reproducible, and fully verified offline (74/74 checks) and on disposable DB (55/55 checks). **Pending population on the user's real database.**

### Deliverables & Files
- `data_generation/config.py`: Distributions, ratios, identity pools, and fraud patterns.
- `data_generation/generate_data.py`: Seeded synthetic data generator (seed 42).
- `data_generation/validate_data.py`: 74 offline integrity and envelope assertions.
- `database/seed_data.sql`: 21,496-line SQL script loading 20,000 transactions with safety guards.
- `database/validate_seed_data.sql`: 55 exact-expectation SQL checks verifying loaded tables and CRC32 fingerprints.
- `data_generation/output/labels.csv`: Ground-truth labels (TransactionID, IsFraud, Scenario, Pattern).
- `data_generation/output/opening_balances.csv`: Account ledger opening/closing balances.
- `data_generation/output/manifest.json`: Checksums and dataset parameters.
- `docs/PHASE2_DATA_GENERATION.md`: Generation methodology and evaluation.

### Progress & Checklist
- [x] Deterministic data generator implemented (500 customers, 800 accounts, 60 merchants, 20,000 transactions).
- [x] 7 fraud patterns and 7 paired legitimate look-alikes generated (3% fraud, 5% edge case).
- [x] Double-entry ledger replay ensuring non-negative balances and valid closing reconciliations.
- [x] Guard procedure `sp_seed_guard` prevents accidental overwrites or re-runs on non-empty databases.
- [x] Offline validator (`validate_data.py`) passing 74/74 tests.
- [x] Disposable instance loaded and verified (55/55 tests in `validate_seed_data.sql` pass).
- [ ] **User Action:** Run `database/seed_data.sql` on real MySQL database after Phase 1 sign-off.
- [ ] **User Action:** Run `database/validate_seed_data.sql` and confirm `SUMMARY: checks failed = 0`.
- Full checklist, including the dataset-consistency check against what Phase 3 trained
  on: `docs/DEPLOYMENT_VERIFICATION_CHECKLIST.md` (sections 3–5).

---

## Phase 3: Fraud Detection ML Pipeline

**Status:** Implemented and run end-to-end (2026-11-23) against the disposable
instance's Phase 2 data (`127.0.0.1:33070`). **Never touched the user's real database.**
Design docs: `docs/PHASE3_ML_DESIGN.md`, `docs/ML_FEATURE_DICTIONARY.md`. Code and
results: `ml/README.md`, `ml/experiments/run_*.json`.

### Scope & Tasks
- [x] Feature engineering (sender velocity/fan-out, amount z-scores, nocturnal/festival
  flags, merchant risk rate, device/location-change) — category-aware, P2P vs CNP,
  `ml/features.py`.
- [x] Data preprocessing pipeline: `Account.Balance`, `opening_balances.csv`,
  `Transaction.Status`, `FraudScore`/`FraudPrediction`/`RiskStatus`, `Fraud_Alert`/
  `Investigation`, and the label's own `Scenario`/`Pattern` are structurally excluded
  (never selected by `data_extraction.py`, never in the feature lists).
- [x] Time-aware split (train Jan-Aug, val Sep-Oct, test Nov-Dec), never shuffled.
- [x] Logistic Regression baseline (`class_weight='balanced'`).
- [x] Random Forest (`class_weight='balanced_subsample'`, small validation-selected grid).
- [x] Model evaluation: Precision, Recall, F1, Confusion Matrix, ROC-AUC, PR-AUC, plus
  per-fraud-pattern recall breakdown and an ablation on `is_high_risk_category`.
- [x] Model persistence using `joblib` (`ml/models/`) with metadata sidecars.
- [x] Headline result: Random Forest test PR-AUC 0.65 vs Logistic Regression's 0.30;
  both ~72% test recall, RF at much higher precision (0.48 vs 0.34). Weakest fraud
  pattern: `device_geo_change` (0.35 recall) — a genuine limitation, not a bug.
- [x] Implementation audited against the approved design docs (2026-11-23): feature
  list, split dates, and leakage safeguards all match; `accuracy` added as an explicit
  secondary metric (was missing); every run now tagged with `--dataset-source` and
  refuses to overwrite another run's artifacts (existing ones renamed to
  `*_disposable_33070.*`, not retrained).
- [ ] **User Action:** Review `ml/README.md` and the experiment log; approve before
  Phase 4 (writing scores back to a real database) begins.
- [ ] Re-run against real-database data once `docs/DEPLOYMENT_VERIFICATION_CHECKLIST.md`
  is fully confirmed — safe procedure: `ml/README.md` → "Re-running against the real
  database" (uses `--dataset-source real_db_<date>`, never overwrites the existing run).

---

## Phase 4: Backend and DBMS Integration

**Status:** Not started.

### Scope & Tasks
- [ ] Python–MySQL connection manager using secure credentials.
- [ ] Fraud-scoring integration pipeline (scoring unscored transactions and writing back `FraudScore`, `FraudPrediction`, and `RiskStatus`).
- [ ] Automated fraud alert generation logic (trigger or application service inserting into `Fraud_Alert`).
- [ ] Investigation tracking workflows (creating and updating `Investigation` records).
- [ ] Stored procedures, views, and triggers for administrative analytics.
- [ ] Query optimization and execution plan analysis (`EXPLAIN`).

---

## Phase 5: Application and Final Validation

**Status:** Not started.

### Scope & Tasks
- [ ] Streamlit web application architecture.
- [ ] Real-time transaction monitoring and filtering dashboard with Plotly charts.
- [ ] Fraud alert review and disposition queue.
- [ ] Investigation workflow interface for compliance and fraud analysts.
- [ ] End-to-end integration testing against project requirements.
- [ ] Final documentation, DBMS project report, and academic demonstration preparation.
