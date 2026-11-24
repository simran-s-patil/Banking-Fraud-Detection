# Handoff (shared session memory)

Read this first, then only the files your task names. Keep it under 80 lines: replace
stale entries instead of appending history. Long-term status lives in
`docs/PHASE_TRACKER.md`.

## Now
- Phase 3 (ML pipeline) IMPLEMENTED and run end-to-end, 2026-11-23, against the
  disposable instance's data (`127.0.0.1:33070`) — never the user's real DB (port 3306).
  Logistic Regression + Random Forest trained, threshold-tuned, evaluated, ablated
  (`is_high_risk_category`), persisted. See `ml/README.md` for the headline result and
  `ml/experiments/run_*.json` for full numbers.
- Phase 1 and Phase 2 remain UNVERIFIED on the user's real database — Phase 3 trained on
  the disposable instance's data per the user's explicit instruction not to wait on
  real-DB confirmation. Don't treat Phase 3 completion as evidence Phase 1/2 are done.
- Next: user chose Option 2 — verify Phase 1/2 on the real DB first, don't start Phase 4.
  Checklist for the user: `docs/DEPLOYMENT_VERIFICATION_CHECKLIST.md` (still PENDING, no
  result reported). Safe real-DB rerun procedure (uses `--dataset-source`, never
  overwrites existing artifacts — see below): `ml/README.md` → "Re-running against the
  real database". Never set `ML_ALLOW_PORT_3306=1` without the user's direct say-so.
- Safe to `/clear`: YES.
- Do NOT start Phase 4 (backend/DB write-back) or Phase 5 (Streamlit) without approval.
- Stray empty file `AS t;` at repo root — not created by any session here, flagged to
  user, not deleted.
- UNRESOLVED (user's call): Phase 1 blank-UPI trigger gap at `schema.sql:263`.

## Phase 3 files (`ml/`)
- `db.py` (hard-refuses port 3306 without `ML_ALLOW_PORT_3306=1`), `data_extraction.py`
  (MySQL + labels.csv -> `ml/data/raw_features.csv`), `features.py` (category-aware,
  leakage-safe: prior-only aggregates, LOO-encoded `merchant_risk_rate`), `splits.py`
  (time-aware Jan-Aug/Sep-Oct/Nov-Dec), `evaluate.py`, `eda.py`, `train.py`,
  `requirements.txt` (pinned, already installed: pandas 3.0.2, numpy 2.4.4,
  scikit-learn 1.8.0, joblib 1.5.3, mysql-connector-python 26.10.0).
- `models/*_disposable_33070.joblib` + `.json` sidecars (LR/RF x full/ablation; renamed
  2026-11-23 to tag dataset source, content unchanged); `experiments/run_2026*.json`.
  `train.py` now refuses to overwrite any existing `{model}_{label}_{dataset_source}`
  filename — verified: re-running with the same tag raises `FileExistsError` as intended.
- Headline: RF beats LR (test PR-AUC 0.65 vs 0.30); both ~72% test recall, RF much higher
  precision; weakest pattern `device_geo_change` (0.35 recall, a real finding, not a bug).
  `is_high_risk_category` ablation: aggregate metrics barely move, `merchant_anomaly`
  recall does (RF 0.56->0.50) — confirms the circularity caveat is real but modest.
- Design docs: `docs/PHASE3_ML_DESIGN.md`, `docs/ML_FEATURE_DICTIONARY.md` (both reviewed
  against real measured data — split fraud counts, the high-risk-category circularity —
  not left as estimates).

## Phase 1 + 2 status (re-verified live, not just cited, 2026-11-23)
- Disposable instance (`127.0.0.1:33070`, MySQL 8.0.46, data dir
  `E:/tmp_banking_mysql_test`, KEEP it) was STOPPED on 2026-11-24; last held the clean, verified
  seed: 500/800/60/20000/0/0; `verification.sql` 92/92 PASS; `validate_seed_data.sql`
  55/55 PASS; re-seed correctly refused (1644). It had drifted once this session
  (Transaction emptied by earlier scenario testing) and was rebuilt from `schema.sql`
  onward — don't assume a state described in an older report still holds; re-check.
- Real database (`localhost:3306`): password unknown here, NEVER connect/change/request
  it. 2026-11-24 user shared their own Workbench inspection: `customer`/`accounttype`/
  `account`/`transactiontype`/`merchant` exist, all 0 rows; `Transaction`/`Fraud_Alert`/
  `Investigation` missing. Matches `docs/DATABASE_DEPLOYMENT_GUIDE.md` §3 "Scenario 1"
  (tested safe, 92/92 PASS) IF those 5 tables are unmodified `schema.sql` output -- can't
  confirm column/FK-level match from table names + row counts alone. Gave user the exact
  `schema.sql -> master_data.sql -> upgrade_existing_schema.sql -> verification.sql`
  sequence + expected output. User's version: 8.0.46 (OK). `accounttype` DDL matches; other
  4 DDLs were truncated in Workbench. Read-only fingerprint baseline from disposable DB
  (items/CRC): check 1/3965989311, column 25/273880238, foreign_key 2/553555561, index
  11/4106244010, table 5/3066246241. Nothing run on this DB by Claude.
- NEXT: user double-clicks `database/RUN_RECOVERY.bat` (runs `deploy_real_db.ps1`, safety
  checks then Phase 1+2), then says done. Read `database/deployment_report.txt` (no password).
  Rehearsed on throwaway 33071 (now deleted): wrong password/altered table/rerun all refused
  unchanged; exact state passed 92/92 + 55/55. Password prompt itself not exercised.
- Client: HeidiSQL 12.22 at `E:\Apps\HeidiSQL\heidisql.exe` (hash-verified). User logs in,
  Claude never does. Project scripts are NOT tested in HeidiSQL (all tests used `mysql.exe`).
- Only allowed reset: `banking_fraud_detection` on port 33070. Synthetic data only.

## Decisions
- CodeGraph 1.6.4 at `E:/tmp_codegraph_tool` (not global). CLI:
  `E:/tmp_codegraph_tool/node_modules/.bin/codegraph`. Index: `.codegraph/`. Use
  `callers`/`callees`/`impact` before reading files; `sync <root>` after code changes.
- Agents: Haiku scouts (read-only), Sonnet builds, Opus reviews.

## User actions needed
- Report `verification.sql`/`validate_seed_data.sql` results from the real database so
  Phase 1/2 can be signed off there (steps: `docs/DATABASE_DEPLOYMENT_GUIDE.md`).
- Review Phase 3 results (`ml/README.md`) and approve/redirect before Phase 4 starts.
- Subagents: report anything the user must do to the orchestrator, who notifies the user
  under a "Your action needed" heading with exact steps.
