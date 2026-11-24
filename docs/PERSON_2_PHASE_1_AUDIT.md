# Person 2 – Phase 1: Machine Learning Foundation & Repository Audit Report

**Project:** Banking Transaction and Fraud Detection System  
**Role:** Person 2 – Machine Learning Developer  
**Date:** 2026-11-24  
**Audit Scope:** Repository Architecture, ML Pipeline, Feature Engineering, Preprocessing, Models, Evaluation Metrics, and Risk Assessment.

---

## 1. Executive Summary

As Person 2 (Machine Learning Developer) on this two-person team, this audit evaluates the existing machine learning codebase located in `ml/` and associated documentation in `docs/`. Person 1 is independently building the MySQL backend, database write-back, batch scoring, and fraud alert insertion.

### Key Audit Findings:
1. **Pipeline Architecture:** The ML foundation is designed around a strictly temporal workflow (chronological train/validation/test split) on 20,000 synthetic transactions generated in Phase 2.
2. **Models Implemented:** A Logistic Regression baseline and a Random Forest classifier have been implemented and trained against the disposable test database (`127.0.0.1:33070`) / cached `raw_features.csv`.
3. **Artifact Integrity:** Model pipelines and sidecar metadata exist under `ml/models/`. Evaluation metrics have been reproduced cleanly without hardcoding (Test PR-AUC: 0.6534, ROC-AUC: 0.9651, Precision: 0.4802, Recall: 0.7185 at threshold 0.21).
4. **Critical Gap – Merchant Risk Rate Serialization:** In `ml/features.py`, `add_merchant_risk_rate` computes leave-one-out encoding for training and empirical rates for validation/test, but the resulting mapping is never serialized as an independent artifact. At inference time (when `IsFraud` labels are unavailable), scoring cannot compute this feature without a persisted encoder artifact.
5. **Detection Vulnerability – `device_geo_change`:** The Random Forest achieves only **35.3% recall (6/17)** on `device_geo_change` fraud patterns in the test set. This represents the single weakest detection area in the model.
6. **Testing Gap:** Prior to this phase, no formal automated unit test suite (`pytest`) existed for the ML modules.

---

## 2. Repository File Structure & Roles

```text
Banking-Fraud-Detection/
├── ml/
│   ├── data/
│   │   └── raw_features.csv            # Cached join of MySQL tables + labels.csv (20,000 rows)
│   ├── experiments/
│   │   ├── run_20261123T180856Z.json   # Experiment metadata and metric logs
│   │   └── run_20261123T180951Z.json   # Benchmark run log
│   ├── models/
│   │   ├── logistic_regression_full_disposable_33070.joblib
│   │   ├── logistic_regression_full_disposable_33070.json
│   │   ├── random_forest_full_disposable_33070.joblib
│   │   ├── random_forest_full_disposable_33070.json
│   │   ├── random_forest_ablation_no_high_risk_category_disposable_33070.joblib
│   │   └── random_forest_ablation_no_high_risk_category_disposable_33070.json
│   ├── data_extraction.py              # Queries MySQL Transaction/Account/Merchant tables & merges labels
│   ├── db.py                           # MySQL connector with port 3306 refusal guard
│   ├── eda.py                          # Dataset profiling & sanity checks
│   ├── evaluate.py                     # Metric calculation, threshold tuning, and pattern recall
│   ├── features.py                     # Category-aware feature engineering & merchant risk rate
│   ├── splits.py                       # Chronological train/val/test split assignment
│   ├── train.py                        # Training pipeline, grid search, threshold tuning, persistence
│   ├── requirements.txt                # ML dependencies
│   └── README.md                       # ML module usage guide
├── docs/
│   ├── PHASE3_ML_DESIGN.md             # Complete design specification for ML pipeline
│   ├── ML_FEATURE_DICTIONARY.md        # Feature definitions, formulas, and leakage notes
│   ├── MERCHANT_RISK_RATE.md           # (Deliverable) Audit and contract for merchant risk
│   ├── ML_FEATURE_CONTRACT.md          # (Deliverable) Input/output schema for Person 1
│   └── PERSON_2_PHASE_1_AUDIT.md       # (This document)
└── tests/                              # (Deliverable) Pytest validation suite
```

---

## 3. Training Workflow & Preprocessing Pipeline

### 3.1 Data Flow
1. **Extraction (`ml/data_extraction.py`):** Queries MySQL for 16 raw transaction, account, and merchant attributes. Performs an inner join on `TransactionID` with `data_generation/output/labels.csv` to attach `IsFraud`, `Scenario`, and `Pattern`. Caches output to `ml/data/raw_features.csv`.
2. **Feature Engineering (`ml/features.py:build_features`):** Generates 26 numeric features and 3 categorical features. All rolling and historical features are strictly expanding/rolling on a timestamp-sorted index, excluding the current row.
3. **Temporal Split (`ml/splits.py`):**
   - **Train (Jan 1 – Aug 31, 2025):** 12,555 transactions (384 fraud, 3.06%).
   - **Validation (Sep 1 – Oct 31, 2025):** 3,578 transactions (81 fraud, 2.26%).
   - **Test (Nov 1 – Dec 31, 2025):** 3,867 transactions (135 fraud, 3.49%).
4. **Target Encoding (`ml/features.py:add_merchant_risk_rate`):** Adds the 27th numeric feature (`merchant_risk_rate`). Computes leave-one-out encoding on the train split and maps the train merchant mean to validation and test splits.
5. **Preprocessing Pipeline (`ml/train.py:build_preprocessor`):**
   - **Numeric features (27 features):** `SimpleImputer(strategy='median')` followed by `StandardScaler()`.
   - **Categorical features (3 features):** `SimpleImputer(strategy='constant', fill_value='MISSING')` followed by `OneHotEncoder(handle_unknown='ignore')`.
6. **Model Training & Hyperparameter Selection:**
   - **Baseline:** `LogisticRegression(class_weight='balanced', max_iter=2000, random_state=42)`.
   - **Candidate Model:** `RandomForestClassifier(class_weight='balanced_subsample', random_state=42)`. Hyperparameters evaluated on validation PR-AUC:
     - `n_estimators=300`, `max_depth=None`, `min_samples_leaf=1` (Selected as best pipeline, Val PR-AUC = 0.4808).
7. **Threshold Tuning:**
   - Scans Precision-Recall curve on validation predictions to maximize F1-score. Selected threshold: **0.21** (for Random Forest).

---

## 4. Complete Feature Inventory (30 Features)

### 4.1 Common Numeric Features (ALL Transactions)
| Feature Name | Source / Formula | Leakage Safeguard |
|---|---|---|
| `amount` | `Transaction.Amount` | Raw transaction value known at creation. |
| `amount_log` | `log1p(Amount)` | Monotonic transformation. |
| `amount_zscore_sender` | `(Amount - mean) / std` of sender's prior transactions | Strictly prior transactions via `shift().expanding()`; imputed to 0 if first txn. |
| `hour_of_day` | `TransactionTimestamp.hour` (0–23) | Transaction timestamp. |
| `day_of_week` | `TransactionTimestamp.dayofweek` (0–6) | Transaction timestamp. |
| `is_night` | `hour_of_day in {0, 1, 2, 3, 4, 5}` | Aligns with synthetic night pattern. |
| `is_festival_day` | Date in static 2025 festival calendar | Static domain knowledge; no label leakage. |
| `sender_account_age_days` | `(TransactionTimestamp - Account.CreatedAt).days` | Standing account metadata. |
| `has_sender_history` | `1` if sender has prior transactions else `0` | Prior history indicator. |
| `sender_txn_count_10m` | Sender txn count in prior 10 minutes | Rolling window on datetime index minus 1 (current row). |
| `sender_txn_count_60m` | Sender txn count in prior 60 minutes | Rolling window on datetime index minus 1. |
| `sender_txn_count_1440m` | Sender txn count in prior 24 hours | Rolling window on datetime index minus 1. |
| `sender_amount_sum_60m` | Sender txn amount sum in prior 60 minutes | Rolling sum minus current row amount. |

### 4.2 P2P/UPI-Specific Numeric Features
| Feature Name | Source / Formula | Value for CNP Rows |
|---|---|---|
| `is_new_receiver` | `1` if first time sender pays this receiver else `0` | `0` |
| `sender_fanout_60m` | Distinct receivers paid by sender in prior 60 minutes | `0.0` |
| `sender_fanout_1440m` | Distinct receivers paid by sender in prior 24 hours | `0.0` |

### 4.3 CNP/E-Commerce-Specific Numeric Features
| Feature Name | Source / Formula | Value for P2P Rows |
|---|---|---|
| `is_high_risk_category` | `1` if MerchantCategory in `{Gaming, Digital Goods, Jewellery, Electronics}` | `0` |
| `is_new_merchant_for_customer` | `1` if first time customer shops with merchant | `0` |
| `has_device_id` | `1` if `DeviceID` is not NULL | `0` |
| `has_ip_address` | `1` if `IPAddress` is not NULL | `0` |
| `has_location` | `1` if `Location` is not NULL | `0` |
| `has_card_token` | `1` if `CardReferenceToken` is not NULL | `0` |
| `is_merchant_missing` | `1` if `MerchantID` is NULL | `0` |
| `device_changed_for_account` | `1` if device differs from sender's last non-null device | `0` |
| `location_changed_for_account` | `1` if location differs from sender's last non-null location | `0` |
| `has_device_history` | `1` if sender has prior device/location history | `0` |
| `merchant_risk_rate` | Leave-one-out train fraud rate; train merchant mean for val/test | Global train fraud rate (`0.0306`) |

### 4.4 Categorical Features (3 Features)
| Feature Name | Domain / Categories | Missing Value Imputation |
|---|---|---|
| `sender_account_type` | `Savings`, `Current` | Imputed as `'MISSING'` |
| `receiver_shape` | `account_only`, `account_and_upi`, `external_upi_only`, `NOT_APPLICABLE` | Imputed as `'MISSING'` |
| `merchant_category` | 10 merchant categories, or `NOT_APPLICABLE` | Imputed as `'MISSING'` |

---

## 5. Model Artifacts and Verification

Artifacts located in `ml/models/`:
- `random_forest_full_disposable_33070.joblib` (17.1 MB): Scikit-learn Pipeline containing fitted `ColumnTransformer` and `RandomForestClassifier`.
- `random_forest_full_disposable_33070.json`: Model sidecar with thresholds, feature lists, and metrics.
- `logistic_regression_full_disposable_33070.joblib` (7.6 KB): Baseline Scikit-learn Pipeline.
- `logistic_regression_full_disposable_33070.json`: Logistic Regression sidecar metadata.

### Benchmark Metrics Verification (Test Split: 3,867 rows, 135 fraud)

| Metric | Logistic Regression (Baseline) | Random Forest (Full) | Reference Target | Status |
|---|:---:|:---:|:---:|:---:|
| **Optimal Threshold** | 0.7944 | **0.2100** | 0.21 | **Verified Exact** |
| **Precision** | 0.3440 | **0.4802** | 0.4802 | **Verified Exact** |
| **Recall** | 0.7185 | **0.7185** | 0.7185 | **Verified Exact** |
| **F1-Score** | 0.4652 | **0.5757** | 0.5757 | **Verified Exact** |
| **ROC-AUC** | 0.9495 | **0.9651** | 0.9651 | **Verified Exact** |
| **PR-AUC** | 0.2957 | **0.6534** | 0.653 | **Verified Exact** |
| **True Positives (TP)** | 97 | **97** | 97 | **Verified Exact** |
| **False Positives (FP)** | 185 | **105** | 105 | **Verified Exact** |
| **False Negatives (FN)** | 38 | **38** | 38 | **Verified Exact** |
| **True Negatives (TN)** | 3547 | **3627** | 3627 | **Verified Exact** |

---

## 6. Pattern-Wise Recall Breakdown & Vulnerability Analysis

Evaluating test-set recall across the 7 synthetic fraud patterns:

| Fraud Pattern | Test Fraud Rows | Random Forest Detected | Recall | Analysis & Diagnostic |
|---|:---:|:---:|:---:|---|
| `fan_out` | 8 | 7 | **87.5%** | Highly effective via `sender_fanout_60m` and `sender_fanout_1440m`. |
| `card_testing` | 15 | 13 | **86.7%** | Strong detection via rapid micro-transactions and token signals. |
| `high_amount` | 27 | 23 | **85.2%** | Strong signal from `amount_zscore_sender` and `amount_log`. |
| `velocity_burst` | 34 | 28 | **82.4%** | Strong signal from `sender_txn_count_10m` and `sender_txn_count_60m`. |
| `odd_hour` | 18 | 11 | **61.1%** | Moderate detection; confused by legitimate `night_shift` look-alikes. |
| `merchant_anomaly` | 16 | 9 | **56.3%** | Moderate detection; drops to 50.0% when high-risk category flag is removed. |
| **`device_geo_change`** | **17** | **6** | **35.3%** | **CRITICAL WEAKNESS**: 11 out of 17 fraud cases missed. |

### Why is `device_geo_change` Recall Low (35.3%)?
1. **Overlap with Legitimate Look-Alikes (`travel_purchase`):** 110 transactions in the synthetic dataset represent legitimate travel purchases that trigger `location_changed_for_account` without being fraudulent.
2. **Missing History:** `device_changed_for_account` requires at least one prior transaction with a non-null device ID. First-time transactions or sparse account histories result in `has_device_history = 0`.
3. **Absence of Geographic Distance Features:** The current pipeline checks exact string mismatch (`Location != last_location`). It does not compute physical velocity or geographic distance (e.g., Bengaluru to Delhi in 15 minutes).

---

## 7. Gaps, Missing Functionality & Technical Risks

1. **Missing Serializable Merchant Risk Transformer:**
   - As noted, `plain_rate` and `global_rate` are computed inside a transient function and never saved.
   - **Remedy:** Implement `MerchantRiskEncoder` class with `.fit()`, `.transform()`, `.save()`, and `.load()` to preserve the mapping for standalone inference.
2. **Inference Pipeline Absence:**
   - There is no standalone `predict.py` or prediction interface to score new, unlabelled incoming transactions for Person 1's backend.
   - **Remedy:** Formalize the input/output contract in `docs/ML_FEATURE_CONTRACT.md`.
3. **Lack of Automated Unit Tests:**
   - No pytest test suite existed to verify transformations, data types, missing value handling, and deterministic inference.
   - **Remedy:** Construct comprehensive unit test suite in `tests/`.

---

## 8. Person 2 Recommended Implementation Plan

1. **Task 3: Merchant Risk Rate Engine:**
   - Refactor `add_merchant_risk_rate` to utilize a serializable `MerchantRiskEncoder` class.
   - Save `ml/models/merchant_risk_encoder_disposable_33070.json` containing the exact fitted mapping and global fallback rate.
   - Complete `docs/MERCHANT_RISK_RATE.md`.
2. **Task 4: Pytest Test Suite:**
   - Implement `test_features.py`, `test_preprocessing.py`, `test_data_validation.py`, `test_merchant_risk.py`, and `test_model.py`.
   - Ensure 100% test passing without live MySQL dependencies.
3. **Task 5: Baseline Reproduction & Visual Reporting:**
   - Run verification, calculate all test metrics, and generate high-resolution evaluation figures under `ml/reports/figures/`.
   - Generate `ml/reports/PHASE_1_VALIDATION_REPORT.md`.
4. **Task 6: Feature Contract Specification:**
   - Publish `docs/ML_FEATURE_CONTRACT.md` detailing exact schemas, null handling, and risk bands for Person 1.
