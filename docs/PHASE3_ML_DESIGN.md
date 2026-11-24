# Phase 3 Design: Fraud Detection ML Pipeline

**Status: DESIGN ONLY. No training code exists yet. Do not begin implementation
without explicit user approval (per `CLAUDE.md` and `docs/PHASE_TRACKER.md`).**

This document designs the ML pipeline against the schema in `docs/DATABASE_DESIGN.md`
and the synthetic dataset described in `docs/PHASE2_DATA_GENERATION.md`
(seed 42; 500 customers, 800 accounts, 60 merchants, 20,000 transactions; 600
labelled fraud, 1,000 legitimate edge cases; 7 fraud patterns with paired
look-alikes). It assumes Phase 1 and Phase 2 are signed off before any code
in this plan is written.

---

## 1. Data extraction

Two sources, joined in Python — never in SQL, because the label does not live
in the schema:

- **Features**: MySQL (`Transaction` joined to `Account`, `Customer`,
  `TransactionType`, `Merchant`). Read-only `SELECT`s, run against the
  disposable test instance during development, never against the user's real
  `localhost:3306` database per project rules.
- **Label**: `data_generation/output/labels.csv` (`TransactionID, IsFraud,
  Scenario, Pattern`). This file is intentionally outside the schema (see
  `handoff.md`: "Labels are NOT in the schema") — `Scenario`/`Pattern` are
  dataset-generation ground truth, not something a production scorer would
  ever see, so they are used only to build the training label and for error
  analysis, never as a feature.

Extraction merges features and labels in pandas on `TransactionID` (inner
join — every seeded transaction has a label row by construction). A CSV
export path (`extract_features.csv`) is also kept so EDA and later phases
don't need a live DB connection for every run.

Planned module: `ml/data_extraction.py` (not yet written) — a single
read-only query plus the CSV merge, parameterized by DB connection info via
environment variables, never hardcoded credentials.

## 2. Exploratory data analysis (EDA)

Planned notebook/script: `ml/eda.py` or `ml/notebooks/01_eda.ipynb` (not yet
written). Scope:

- Class balance: 600/20,000 = 3.0% fraud — confirms this is a severe
  imbalance problem, not a balanced classification problem.
- Univariate distributions of `Amount`, hour-of-day, day-of-week, `Status`,
  `TransactionTypeID` (P2P vs CNP), split by `IsFraud`.
- Missingness: `CNP_FIELD_NULL_RATE` (5%, each of device/IP/location/token)
  and `CNP_MERCHANT_NULL_RATE` (2%) are generator-injected and must be
  profiled, since a naive model could learn "missing device ID" as a
  shortcut that may or may not generalize.
- Pattern/scenario breakdown (`manifest.json` `pattern_counts`) to confirm
  all 7 fraud patterns and their look-alikes are present in whatever split
  is used later (Section 5).
- Correlation / mutual information of candidate features against `IsFraud`,
  specifically to sanity-check that no single raw column trivially separates
  the classes (the generator's own `validate_data.py` already checks that no
  simple rule exceeds 90% precision — EDA re-confirms this on the full
  feature set, not just the two rules the generator tests).

## 3. Category-aware feature engineering

P2P/UPI and CNP/e-commerce transactions have different fraud signatures, so
features are split into three groups. Full definitions, source columns, and
leakage notes are in `docs/ML_FEATURE_DICTIONARY.md` — this section only
gives the rationale per group.

**Common (both categories)**
- Calendar/time: hour-of-day, day-of-week, is-night (0–5h, matching the
  generator's `NIGHT_HOURS`), is-festival-day (matching `FESTIVAL_DAYS`).
- Amount, and amount expressed relative to the sending account's own history
  (z-score against that account's *prior* transactions only — see Section 4).
- Sender account attributes that are stable, not post-event: `AccountType`
  (Savings/Current), account age in days at transaction time
  (`TransactionTimestamp - Account.CreatedAt`).
- Sender velocity: count and sum of the sender's transactions in a trailing
  window (e.g. 10/60/1440 minutes), computed strictly from transactions
  *before* the current one.

**P2P/UPI-specific**
- Receiver shape: account-only vs account+UPI vs external-UPI-only (mirrors
  `P2P_RECEIVER_MIX` in the generator — this is a real signal, not a
  generator artifact, since it reflects how the payment was routed).
- Fan-out: number of distinct receivers the sender has paid in a trailing
  window — targets the `fan_out` fraud pattern directly.
- New-receiver flag: first time this sender has paid this receiver
  account/UPI.

**CNP/e-commerce-specific**
- Merchant category and a merchant risk rate (fraud rate among that
  merchant's *prior, training-fold-only* transactions — see Section 4 for
  why this must be computed carefully).
- New-merchant flag: first time this customer has transacted with this
  merchant (targets `merchant_anomaly` / `new_merchant_trial`).
- Null-field flags for `DeviceID`, `IPAddress`, `Location`,
  `CardReferenceToken` (targets `card_testing`, `device_geo_change`), plus a
  device/location-change flag (does this transaction's device or location
  differ from the sending account's usual one, using prior history only).
- High-risk category flag (Gaming, Digital Goods, Jewellery, Electronics —
  matches the generator's `HIGH_RISK_CATEGORIES`, used as a model input
  because it's legitimately available metadata, not because the generator
  used it).

All "prior history" features are computed with pandas `groupby` + expanding/
rolling windows on a timestamp-sorted frame, explicitly excluding the current
row, never with a window function that can see the future.

## 4. Leakage prevention

Hard exclusions (from `docs/PROJECT_HANDOVER.md` Section 6 and
`handoff.md`), carried into this design unchanged:

| Excluded | Why |
|---|---|
| `Account.Balance` | Closing/current ledger balance — reflects transactions that happened, including the one being scored. Not available at decision time. |
| `data_generation/output/opening_balances.csv` | Same reason; it's a ledger replay artifact, not a point-in-time feature. |
| `Transaction.Status` | `REVERSED`/`FAILED` can be a *consequence* of fraud detection or a failed fraud attempt, not a cause — using it would let the model see the outcome of the event it's trying to predict. |
| `Transaction.FraudScore`, `FraudPrediction`, `RiskStatus` | Defined as `NULL`/`NOT_SCORED` until Phase 4 scores a row — by definition the model is trying to produce these, so they can never be inputs. |
| `Fraud_Alert`, `Investigation` tables | Exist only *because* of a fraud decision (0 rows currently, by design — see `manifest.json`). Target-derived. |
| `labels.csv` `Scenario`, `Pattern` | Ground truth about *why* a row is fraudulent — never observable in production. Used only for labels and post-hoc error analysis, stripped before the feature matrix is built. |

Process safeguards beyond column exclusion:
- **Temporal features**: every rolling/aggregate feature (velocity, fan-out,
  merchant risk rate, "new counterparty" flags) is computed using only
  transactions with an earlier `TransactionTimestamp` than the row being
  featurized. This is enforced by sorting the full frame by timestamp once
  and using `groupby(...).shift()`/`expanding()` rather than any
  whole-dataset aggregate.
- **Merchant/category risk rates**: computed from the *training split only*
  and then looked up (not recomputed) for validation/test rows, so the
  validation/test fraud rate never leaks into a feature. A merchant seen
  only in validation/test gets a fallback (e.g. the global training fraud
  rate), not an undefined value.
- **No whole-dataset statistics**: scaling (mean/std for the logistic
  regression) is fit on the training split only and applied to val/test,
  never fit on the full dataset before splitting.
- **IDs are not features**: `TransactionID`, `CustomerID`, `AccountNumber`,
  `MerchantID` are join keys only, dropped before model fitting (an
  auto-increment ID can otherwise act as a time leak or an overfit key).

## 5. Train / validation / test split

Time-aware split, since `TransactionTimestamp` spans 2025-01-01 to
2025-12-31 (`config.WINDOW_START/END`) and several fraud patterns
(`velocity_burst`, `fan_out`) are inherently about a transaction's position
in a time-ordered sequence per account:

- Sort all transactions by `TransactionTimestamp`.
- **Train**: Jan–Aug 2025 (62.8% of rows, 12,555 transactions, 384 fraud).
- **Validation**: Sep–Oct 2025 (17.9%, 3,578 transactions, 81 fraud) — used
  for threshold tuning (Section 9) and model selection between Logistic
  Regression and Random Forest.
- **Test**: Nov–Dec 2025 (19.3%, 3,867 transactions, 135 fraud) — touched
  exactly once, for final reporting.

These counts were measured directly against the seed-42 dataset (live
disposable instance, cross-checked with `labels.csv`), not assumed — see
`handoff.md` for the verification run. All 12 months carry fraud rows
(confirmed by `validate_data.py`'s "fraud spread through the year" check),
so no split is empty, but the validation split's 81 fraud rows is on the
low side for threshold tuning: a PR-curve built on ~80 positives is noisier
than one built on train-scale counts. Section 9 accounts for this explicitly
rather than treating the tuned threshold as precise to two decimal places.

Rolling/velocity features for a row are always computed from that row's own
split or earlier (never across the split boundary into the future), which
falls out naturally from the "prior timestamps only" rule in Section 4.

## 6. Logistic Regression baseline

`sklearn.linear_model.LogisticRegression` in a `Pipeline` with
`StandardScaler` (numeric features) and `OneHotEncoder` (categorical
features: account type, receiver shape, merchant category), via
`ColumnTransformer`. `class_weight='balanced'`, `random_state=42`,
`max_iter` raised as needed for convergence. This is the interpretable
baseline every later model must beat — coefficients are inspected for sanity
(e.g. night-hour and fan-out should carry positive weight).

## 7. Random Forest model

`sklearn.ensemble.RandomForestClassifier`, same `ColumnTransformer` front-end
(trees don't need scaling but the shared pipeline keeps the feature matrix
consistent between models), `class_weight='balanced_subsample'`,
`random_state=42`. Hyperparameters (`n_estimators`, `max_depth`,
`min_samples_leaf`) tuned on the validation split only via a small grid —
not cross-validation across the whole dataset, to respect the time-aware
split from Section 5. Feature importances are reported and cross-checked
against the 7 known fraud patterns as a sanity check, not as the primary
evaluation.

## 8. Class imbalance handling

Given the fixed tech stack (MySQL + Python + pandas/scikit-learn/Streamlit/
Plotly — no `imbalanced-learn`, no SMOTE), imbalance is handled via:

- `class_weight='balanced'` / `'balanced_subsample'` on both models
  (Sections 6–7), which reweights the loss instead of synthesizing rows.
- Threshold tuning on the validation split (Section 9), since the default
  0.5 cutoff is meaningless at a 3% base rate.
- Reporting PR-AUC alongside ROC-AUC (Section 10), because ROC-AUC alone is
  misleadingly optimistic under heavy class imbalance.

Random undersampling of the majority class is noted as a fallback only if
`class_weight` proves insufficient during actual experimentation — not part
of the default plan, to avoid discarding legitimate-transaction signal.

## 9. Threshold tuning

Using the validation split's predicted probabilities: compute the
precision-recall curve, select the probability threshold that maximizes F1
(or, if the user states a business preference, a minimum-recall-at-best-
precision target — e.g. "catch at least 80% of fraud"). The chosen threshold
is fixed before the single test-split evaluation in Section 10, never
re-tuned against the test split.

Caveat (confirmed against the real dataset, Section 5): the validation
split carries only 81 fraud rows, so the PR curve used for tuning is noisier
than train-scale statistics would be. Mitigation: report a small neighborhood
of thresholds around the chosen one (e.g. ±0.02) with their validation
precision/recall, so the write-up shows the threshold choice isn't a knife-
edge artifact of 81 points, and treat the test-split PR-AUC (Section 10,
135 fraud rows) as the more statistically stable of the two — if validation-
and test-split curves disagree sharply near the chosen threshold, say so
rather than reporting a single number as settled.

## 10. Evaluation metrics

Reported for both models, at the tuned threshold, on validation (for
selection) and once on test (for the final number):

- Confusion matrix (raw counts — with 3% fraud, counts matter more than a
  single accuracy number).
- Precision, Recall, F1-score at the tuned threshold.
- ROC-AUC and PR-AUC (threshold-independent, PR-AUC is the primary ranking
  metric given the class imbalance).
- Accuracy is reported only as a secondary, clearly-labelled number — never
  the headline metric, since a model predicting "never fraud" would score
  97% accuracy while being useless.

## 11. Model persistence

`joblib.dump` of the full fitted `Pipeline` (preprocessing + model) to
`ml/models/<model_name>_<run_id>.joblib`, alongside a sidecar JSON with: the
feature list, the chosen decision threshold, validation/test metrics, the
random seed, and the `manifest.json` dataset hash it was trained on — so a
later consumer (Phase 4's scoring pipeline) can load a model and know
exactly what it expects and how it was evaluated, without re-deriving it
from code history.

## 12. Reproducibility and experiment tracking

- `random_state=42` fixed everywhere a model, split, or sampling step takes
  one — matching the generator's own seed convention.
- Every run's config (split dates, feature list, hyperparameters, threshold)
  and resulting metrics are written to a small JSON log under
  `ml/experiments/` (one file per run, timestamped) — no new dependency
  (e.g. MLflow) is introduced, since the fixed tech stack is pandas/
  scikit-learn/Streamlit/Plotly only.
- The dataset's `manifest.json` SHA-256 hashes are recorded with each run, so
  a run can always be tied back to the exact seed-42 dataset it used.
- `pandas` and `scikit-learn` are confirmed available in the current Python
  (3.14.3) environment, but no `requirements.txt`/pinned-version file exists
  in the repo yet (`data_generation/` is stdlib-only by design, so this is
  the first phase that needs one). `ml/requirements.txt` with exact pinned
  versions should be added alongside the first training script — "fixed
  seed, unpinned library versions" is not fully reproducible, since model
  behavior can shift across scikit-learn versions even with the same seed.

---

## Why this avoids using information unavailable at transaction time

Every feature in Section 3 is one of: (a) a value written to the
`Transaction`/`Account`/`Customer`/`Merchant` row at or before the moment the
transaction is created (e.g. `Amount`, `DeviceID`, `AccountType`,
`Account.CreatedAt`), or (b) an aggregate over *strictly earlier* rows for
the same sender/receiver/merchant (velocity, fan-out, merchant risk rate).
Nothing is derived from `Account.Balance` (a post-transaction ledger state),
`Transaction.Status` (a post-processing outcome), or any fraud-scoring/
alert/investigation table (which exist only as a *result* of a fraud
decision). This mirrors exactly how a real-time scoring service would see
the transaction: at the instant it arrives, before it is processed or
reversed, before any alert exists.

## Known synthetic-dataset caveat: `is_high_risk_category`

Verified in the generator (`data_generation/generate_data.py:181`) and in
`validate_data.py`'s own output ("merchant_anomaly: merchant is in a
high-risk category [72/72]"): every `merchant_anomaly` fraud row is, by
construction, in one of the four `HIGH_RISK_CATEGORIES`. This is not a
leakage bug — the category is real, static merchant metadata available at
transaction time — but it means `is_high_risk_category` will look like a
near-perfect predictor for that one pattern (72 of 600 fraud rows, 12%)
specifically because the generator's label assignment used it that way, not
because real-world fraud is that cleanly separated by category. When
reporting per-pattern recall (Section 3 of `docs/ML_FEATURE_DICTIONARY.md`,
item 6), the `merchant_anomaly` number should be flagged in the write-up as
a property of this synthetic dataset's construction, not evidence that the
model would generalize that well on category alone in production.

## Next steps (not started)

1. User reviews and approves this design (and `docs/ML_FEATURE_DICTIONARY.md`).
2. User confirms Phase 1 + Phase 2 sign-off on the real database (see
   `docs/PHASE_TRACKER.md`).
3. Only then: write `ml/data_extraction.py`, `ml/eda.py` (or notebook), and
   the training scripts — each reviewed (Opus) and tested before the next
   is written, per the agent workflow in `CLAUDE.md`.
