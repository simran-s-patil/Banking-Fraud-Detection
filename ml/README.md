# ml/ — Phase 3: Fraud Detection ML Pipeline

**Status: IMPLEMENTED and run successfully against the seed-42 synthetic
dataset.** Design docs: `docs/PHASE3_ML_DESIGN.md`,
`docs/ML_FEATURE_DICTIONARY.md`.

Trained **only** against the disposable test instance's copy of the Phase 2
data (`127.0.0.1:33070`) — never against the user's real database. Real-DB
scoring is Phase 4 work, not this.

## Commands (run from the project root)

```
pip install -r ml/requirements.txt
python ml/data_extraction.py [--force]   # MySQL (disposable instance) + labels.csv -> ml/data/raw_features.csv
python ml/eda.py                          # dataset readiness checks (counts, label balance, missingness, pattern breakdown)
python ml/train.py [--force-extract] [--dataset-source NAME]  # full pipeline: features -> split -> train LR + RF -> tune threshold -> evaluate -> ablation -> persist
```

`--dataset-source` defaults to `disposable_33070` (the only source this has
been run against so far) and tags every output filename; see "Re-running
against the real database" below for why.

`ml/data_extraction.py` refuses to connect to port 3306 unless
`ML_ALLOW_PORT_3306=1` is explicitly set (see `ml/db.py`) — that flag should
never be set by an agent on its own.

## What `train.py` does

1. Extracts (or reuses the cached CSV) Transaction+Account+Merchant data,
   merged with `labels.csv`'s `IsFraud` target (never read from SQL — the
   schema has no label column by design).
2. Builds category-aware features (`ml/features.py`): common, P2P-specific,
   CNP-specific — see `docs/ML_FEATURE_DICTIONARY.md` for every column's
   source and leakage justification. All "prior history" aggregates
   (velocity, fan-out, new-receiver/new-merchant, device/location change)
   use strictly earlier transactions only.
3. Time-aware split (`ml/splits.py`): train Jan–Aug 2025, validation
   Sep–Oct, test Nov–Dec — never shuffled.
4. Adds `merchant_risk_rate` with leave-one-out encoding on the training
   split only (the one feature that touches the label at feature-engineering
   time — see `add_merchant_risk_rate`'s docstring).
5. Fits a shared `ColumnTransformer` (median-impute + scale numeric,
   constant-impute + one-hot categorical) inside an sklearn `Pipeline`,
   fitted on the training split only.
6. Trains Logistic Regression (`class_weight='balanced'`) and Random Forest
   (`class_weight='balanced_subsample'`, small manual depth/leaf grid
   selected by validation PR-AUC — not cross-validated, to respect the
   chronological split).
7. Tunes the decision threshold on validation (maximize F1), reports a
   threshold neighborhood rather than one number (validation has only ~81
   fraud rows — see `docs/PHASE3_ML_DESIGN.md` Section 9).
8. Evaluates once on test: precision, recall, F1, confusion matrix, ROC-AUC,
   PR-AUC, plus recall broken down by the generator's `Pattern` ground truth
   (analysis only, never a feature).
9. Re-runs the whole thing with `is_high_risk_category` removed (the
   documented synthetic-dataset circularity — see the caveat in
   `docs/PHASE3_ML_DESIGN.md`) and reports the metric deltas.
10. Persists each fitted pipeline to
    `ml/models/<model>_<label>_<dataset_source>.joblib` with a sidecar
    `.json` (feature list, threshold, metrics, seed, dataset source, DB
    host/port — never credentials), and writes a full experiment log to
    `ml/experiments/run_<dataset_source>_<timestamp>.json`. Refuses to run
    at all if that exact filename already exists, so a later run against a
    different dataset (see "Re-running against the real database" below)
    can never silently overwrite an earlier one's models or metrics.

## Headline result (seed 42, one run — see `ml/experiments/` for the exact log)

Random Forest clearly outperforms the Logistic Regression baseline:
test PR-AUC 0.65 vs 0.30, test ROC-AUC 0.965 vs 0.950, at thresholds tuned on
validation. Both catch ~72% of test-split fraud at their tuned threshold;
Random Forest does so at much higher precision (0.48 vs 0.34). Recall is
uneven across the 7 fraud patterns — strongest on `fan_out`/`high_amount`/
`velocity_burst` (>0.82), weakest on `device_geo_change` (0.35), which is a
genuine finding worth reporting, not a bug. Removing `is_high_risk_category`
barely moves the aggregate metrics but does cost `merchant_anomaly` recall
specifically (RF: 0.56 → 0.50), confirming the documented circularity is
real but modest in this dataset, not a model-breaking leak.

## Hard rules carried over from the project (unchanged, verified in code)

- Never connects to the user's real MySQL instance (`ml/db.py` hard-refuses
  port 3306 without an explicit opt-in that nothing in this codebase sets).
- Never uses `Account.Balance`, `opening_balances.csv`, `Transaction.Status`,
  `FraudScore`/`FraudPrediction`/`RiskStatus`, `Fraud_Alert`/`Investigation`,
  or the label's own `Scenario`/`Pattern` columns as features — enforced
  structurally: `data_extraction.py` never selects the excluded DB columns,
  and `features.py`'s `NUMERIC_FEATURES`/`CATEGORICAL_FEATURES` never include
  `Scenario`/`Pattern`.
- `random_state=42` everywhere a model or sampling step takes one.
- Stays inside the fixed tech stack (`ml/requirements.txt`): pandas,
  NumPy, scikit-learn, joblib, mysql-connector-python — all explicitly
  listed in `docs/PROJECT_CONTEXT.md`'s "later phases" stack. No new
  frameworks introduced.

## Re-running against the real database (once Phase 1/2 are signed off there)

**Do not do this until the user has confirmed every item in
`docs/DEPLOYMENT_VERIFICATION_CHECKLIST.md` against their real database.**
Nothing in this repo sets `ML_ALLOW_PORT_3306=1` on its own — that is the
user's call, made explicitly, at the moment they want this run to happen.

```
# 1. Point at the real database (the user supplies host/credentials; an
#    agent never requests or stores them — these are illustrative names).
export ML_DB_HOST=localhost
export ML_DB_PORT=3306
export ML_DB_USER=<user-supplied>
export ML_DB_PASSWORD=<user-supplied>
export ML_ALLOW_PORT_3306=1   # only ever set by the user, in the moment, never by an agent

# 2. Extract fresh (writes a NEW raw_features.csv over the cached one --
#    the cache is disposable-instance-specific data, not a model or metric,
#    so overwriting it is fine and intended).
python ml/data_extraction.py --force

# 3. Train with a distinct --dataset-source so nothing from the disposable
#    run is touched. train.py refuses outright if the tag collides with an
#    existing one.
python ml/train.py --dataset-source real_db_$(date +%Y%m%d)
```

This preserves, unchanged, every safeguard already reviewed: the same
`ml/features.py` category-aware engineering, the same chronological
Jan-Aug/Sep-Oct/Nov-Dec split (`ml/splits.py`), the same train-only /
leave-one-out `merchant_risk_rate`, the same threshold-tuning and evaluation
methodology (`ml/evaluate.py`). Only the data source changes. Results land
in new, separately-named files:

- `ml/models/{logistic_regression,random_forest}_{full,ablation_no_high_risk_category}_real_db_<date>.joblib` (+ `.json` sidecars, which record `dataset_source`, `db_host`, `db_port` — never the password).
- `ml/experiments/run_real_db_<date>_<timestamp>.json`.

The existing `*_disposable_33070.*` artifacts and `run_2026*.json` logs are
left exactly as they are — nothing from this session's run is overwritten.
Compare the two `dataset_source`s' metrics side by side once both exist.

## Not yet done

- `ml/models/*.joblib` are committed-locally only; `random_forest_*.joblib`
  are ~17 MB each — worth `.gitignore`-ing (or Git LFS) once this becomes a
  git repository, rather than committing them directly.
- No automated test suite for the feature-engineering functions yet (only
  the end-to-end run was exercised). Worth adding targeted unit tests for
  the leakage-sensitive functions (`add_merchant_risk_rate`, the rolling
  velocity/fan-out helpers) before extending the pipeline further.
- Phase 4 (writing `FraudScore`/`FraudPrediction`/`RiskStatus` back to a real
  database) has not started.
