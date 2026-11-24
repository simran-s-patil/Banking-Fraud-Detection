# CLAUDE.md

Project: **Banking Transaction and Fraud Detection System** — DBMS academic prototype
(RV College of Engineering, team of 3). Full context: `docs/PROJECT_CONTEXT.md`.

## Hard scope limits (apply to every phase)
- Synthetic data only. No real banking API integration. No actual money transfers.
- Never store full card numbers, CVV, or real banking credentials.
- A fraud score/alert is a review signal, not proof of fraud.
- Tech stack is fixed: MySQL 8.x + Python 3 (+ pandas/scikit-learn/Streamlit/Plotly in
  later phases). Do not introduce MongoDB, PostgreSQL, Firebase, Redis, microservices,
  or other frameworks.

## Current state (last verified 2026-11-23)
**Phase 1 (database schema) and Phase 2 (synthetic data generation) are both
code-complete and verified on a throwaway MySQL 8.0.46 instance** (port 33070):
Phase 1's `verification.sql` passes 92/92; Phase 2's generator passes 74/74
offline (`data_generation/validate_data.py`) and its `validate_seed_data.sql`
passes 55/55 after `seed_data.sql` loads 20,000 transactions. **Neither phase
is confirmed on the user's real database** (port 3306, password unknown to
Claude, never connect to it). Exact run order and safe deployment playbooks:
`docs/DATABASE_DEPLOYMENT_GUIDE.md` (start with the read-only
`database/inspect_environment.sql`). Full status and file list:
`docs/PHASE_TRACKER.md`.

**Phase 3 (ML pipeline) is implemented and run end-to-end (`ml/`), trained only
against the disposable instance's data (`127.0.0.1:33070`) — never the user's
real database.** Random Forest beats the Logistic Regression baseline (test
PR-AUC 0.65 vs 0.30); see `ml/README.md`. This does NOT mean Phase 1/2 are
verified on the user's real database — they aren't. Phase 4 (backend) and
Phase 5 (Streamlit app) have not started. Don't write Phase 4+ code unless
explicitly asked, and never without the user's sign-off on Phase 1/2 against
their real database first.

## Database design (8 entities)
Customer, Account, AccountType, Transaction, TransactionType, Merchant, Fraud_Alert,
Investigation — one common `Transaction` table for both P2P/UPI and CNP/e-commerce
(distinguished by `TransactionTypeID`, not separate tables). Full column-level design:
`docs/DATABASE_DESIGN.md`. Reasoning behind every constraint choice:
`docs/ARCHITECTURE_DECISIONS.md`.

Key points worth remembering without re-reading everything:
- At most one `Fraud_Alert` per `Transaction` (`UNIQUE(TransactionID)`).
- An `Investigation` row is optional even when an alert exists — created only once
  an investigation actually starts.
- `Transaction.FraudScore`/`FraudPrediction` are nullable — a transaction exists
  before it's scored; `RiskStatus` defaults to `'NOT_SCORED'`.
- `Transaction` is backtick-quoted everywhere as a defensive measure.
- P2P/CNP field rules are enforced by `sp_validate_transaction_category` and BEFORE
  INSERT/UPDATE triggers (requires MySQL 8.0.29+); CNP merchant is optional.
- Monetary columns are always `DECIMAL`, never `FLOAT`/`DOUBLE`.

## Where things live
- `docs/` — the 4 original source documents (read-only, source of truth) plus
  `PROJECT_CONTEXT.md`, `DATABASE_DESIGN.md`, `ARCHITECTURE_DECISIONS.md`,
  `PHASE_TRACKER.md`, `PHASE2_DATA_GENERATION.md`, `PROJECT_HANDOVER.md`,
  `DATABASE_DEPLOYMENT_GUIDE.md`, `PHASE3_ML_DESIGN.md`, `ML_FEATURE_DICTIONARY.md`.
- `database/` — `schema.sql`, `master_data.sql`, `upgrade_existing_schema.sql`,
  `verification.sql`, `inspect_environment.sql` (read-only diagnostics),
  `seed_data.sql`, `validate_seed_data.sql`.
- `data_generation/` — Phase 2 synthetic data generator (`generate_data.py`,
  `validate_data.py`, `config.py`), stdlib-only Python.
- `ml/` — Phase 3 pipeline (`db.py`, `data_extraction.py`, `features.py`, `splits.py`,
  `evaluate.py`, `eda.py`, `train.py`), `models/`, `experiments/`, `requirements.txt`.
- `handoff.md` — current session state; read it first.

## Agent workflow
- Start every session and subagent from `handoff.md`; read only the files the task names.
- Haiku scouts (read-only), Sonnet builds, Opus reviews. Pass file paths and line numbers,
  not conversation history. Update `handoff.md` at each stage.
- Loop: scout -> build -> run tests -> Opus review -> fix -> retest.
- At each phase end: update `handoff.md` and `docs/PHASE_TRACKER.md`, then tell the user
  it is safe to `/clear`. Do not begin the next phase without their go-ahead.
- Never connect to the user's MySQL on port 3306. Test on the throwaway instance described
  in `handoff.md`. Report only results that were actually executed.
- Install CodeGraph at Phase 2, once Python functions exist.
- When the user must do something, notify them under a "Your action needed" heading with
  exact steps.

## Code quality rules (Ponytail + Karpathy principles)
- Think first: state assumptions; ask when a choice changes the agreed scope.
- Simplicity: minimum code that solves the task; reuse; no speculative features.
- Surgical changes: touch only what the task needs; never overwrite user work.
- Goal-driven: define the check that proves success, then run it.

## Working conventions
- Don't silently modify agreed scope or invent requirements beyond the 4 source
  documents — if something is genuinely ambiguous, ask rather than assume.
- Keep the Transaction table singular/common — never split into separate P2P and CNP
  tables.
- Don't run destructive SQL (`DROP DATABASE`, etc.) against the project database.
- Update `docs/PHASE_TRACKER.md` when a phase's status changes.
