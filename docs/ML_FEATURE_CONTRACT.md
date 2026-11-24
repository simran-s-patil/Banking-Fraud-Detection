# Machine Learning Feature & Inference Contract

**Project:** Banking Transaction and Fraud Detection System  
**Roles:** Person 2 (ML Developer) $\longleftrightarrow$ Person 1 (Backend & Database Developer)  
**Target Milestone:** Phase 2 Backend Scoring & Database Write-Back  
**Date:** 2026-11-24  
**Status:** Agreed Interface Specification (Implementation in Phase 2)

---

## 1. Executive Purpose

This document defines the formal **Feature and Inference Contract** between the Machine Learning pipeline (Person 2) and the Backend / Database Integration service (Person 1). 

In Phase 2, Person 1 will execute batch or stream scoring jobs against unscored transactions in MySQL, query features, invoke model inference, and write back `FraudScore`, `FraudPrediction`, and `RiskStatus` to the `Transaction` and `Fraud_Alert` tables. This contract guarantees consistent input schemas, deterministic transformations, and standardized prediction payloads.

---

## 2. Target Prediction Response Schema

When a transaction is scored by the ML module, the inference service will return a JSON/dict matching the following schema:

```json
{
  "transaction_id": 10001,
  "fraud_probability": 0.87,
  "prediction": "FRAUDULENT",
  "model_version": "rf_v1.0",
  "risk_status": "HIGH",
  "merchant_risk_rate": 0.35
}
```

### Response Field Specifications
| Field | Type | Domain / Values | Description | Database Target Column |
|---|---|---|---|---|
| `transaction_id` | `int` | `> 0` | Primary key of the scored transaction. | `Transaction.TransactionID` |
| `fraud_probability` | `float` | `[0.0000, 1.0000]` | Model output probability of fraud (rounded to 4 decimal places). | `Transaction.FraudScore` |
| `prediction` | `string` | `'LEGITIMATE'`, `'FRAUDULENT'` | Binary classification based on threshold **0.21**. | `Transaction.FraudPrediction` |
| `model_version` | `string` | `'rf_v1.0'` | Identifier of the model artifact used for scoring. | Audit metadata |
| `risk_status` | `string` | `'LOW'`, `'MEDIUM'`, `'HIGH'` | Categorical operational risk band. | `Transaction.RiskStatus` |
| `merchant_risk_rate` | `float` | `[0.0000, 1.0000]` | Precomputed historical risk of the merchant (or global fallback). | Feature audit |

---

## 3. Threshold vs. Risk Band Separation

To decouple model decision calibration from bank operational workflows:

### 3.1 Binary Prediction Cutoff
- **Decision Threshold:** **`0.2100`**
  - $\text{Probability} \ge 0.2100 \implies \text{prediction} = \text{'FRAUDULENT'}$
  - $\text{Probability} < 0.2100 \implies \text{prediction} = \text{'LEGITIMATE'}$

### 3.2 Operational Risk Bands
Risk bands drive alerting and analyst queues without altering the binary classifier:
- **`LOW`**: $\text{fraud\_probability} < 0.10$  
  *(Transaction cleared; no alert raised).*
- **`MEDIUM`**: $0.10 \le \text{fraud\_probability} < 0.21$  
  *(Heightened risk; classified as Legitimate by threshold, but flagged for passive surveillance or secondary rules).*
- **`HIGH`**: $\text{fraud\_probability} \ge 0.21$  
  *(Classified as Fraudulent; triggers automated insertion into `Fraud_Alert` table with `ReviewStatus = 'OPEN'`).*

---

## 4. Input Requirements: Raw Transaction Record

To score a transaction, Person 1's backend extractor must provide the following columns (queried via SQL join):

```sql
SELECT
    t.TransactionID,
    t.TransactionTimestamp,
    t.Amount,
    t.SenderAccountNumber,
    t.ReceiverAccountNumber,
    t.ReceiverUPIID,
    tt.TypeName AS TransactionTypeName,
    t.MerchantID,
    m.Category AS MerchantCategory,
    t.DeviceID,
    t.IPAddress,
    t.Location,
    t.CardReferenceToken,
    sa.CustomerID AS SenderCustomerID,
    sat.TypeName AS SenderAccountType,
    sa.CreatedAt AS SenderAccountCreatedAt
FROM `Transaction` t
JOIN TransactionType tt ON tt.TransactionTypeID = t.TransactionTypeID
JOIN Account sa ON sa.AccountNumber = t.SenderAccountNumber
JOIN AccountType sat ON sat.AccountTypeID = sa.AccountTypeID
LEFT JOIN Merchant m ON m.MerchantID = t.MerchantID;
```

---

## 5. Complete Model Feature Contract (30 Features)

The Scikit-learn Pipeline expects an ordered input DataFrame containing exactly the following 30 columns:

### 5.1 Common Features (Columns 1–13)
| # | Feature Name | Input Type | Description / Generation Rule | Null / Missing Strategy |
|---|---|---|---|---|
| 1 | `amount` | `float` | Raw `Amount`. Must be $> 0$. | Required. |
| 2 | `amount_log` | `float` | $\log(1 + \text{amount})$. | Computed. |
| 3 | `amount_zscore_sender` | `float` | $\frac{\text{amount} - \mu_{\text{prior}}}{\sigma_{\text{prior}}}$ across sender's prior transactions. | Impute $0.0$ if no prior transactions. |
| 4 | `hour_of_day` | `int` | Hour from `TransactionTimestamp` ($0–23$). | Extracted. |
| 5 | `day_of_week` | `int` | Day of week from `TransactionTimestamp` ($0=\text{Mon}, 6=\text{Sun}$). | Extracted. |
| 6 | `is_night` | `int` | $1$ if `hour_of_day` $\in \{0,1,2,3,4,5\}$, else $0$. | Computed. |
| 7 | `is_festival_day` | `int` | $1$ if date matches Indian festival calendar, else $0$. | Config lookup. |
| 8 | `sender_account_age_days` | `int` | Days between `Account.CreatedAt` and `TransactionTimestamp`. | Computed ($\ge 0$). |
| 9 | `has_sender_history` | `int` | $1$ if sender has $\ge 1$ prior transactions, else $0$. | Computed. |
| 10 | `sender_txn_count_10m` | `int` | Count of sender's transactions in prior 10 minutes. | Computed (excludes current row). |
| 11 | `sender_txn_count_60m` | `int` | Count of sender's transactions in prior 60 minutes. | Computed (excludes current row). |
| 12 | `sender_txn_count_1440m` | `int` | Count of sender's transactions in prior 24 hours. | Computed (excludes current row). |
| 13 | `sender_amount_sum_60m` | `float` | Sum of sender's transaction amounts in prior 60 minutes. | Computed (excludes current row). |

### 5.2 P2P/UPI-Specific Features (Columns 14–16)
| # | Feature Name | Input Type | Description / Generation Rule | Value for CNP Transactions |
|---|---|---|---|---|
| 14 | `is_new_receiver` | `int` | $1$ if first time sender pays this receiver account or UPI ID. | Set to `0`. |
| 15 | `sender_fanout_60m` | `float` | Count of distinct receivers paid in prior 60 minutes. | Set to `0.0`. |
| 16 | `sender_fanout_1440m` | `float` | Count of distinct receivers paid in prior 24 hours. | Set to `0.0`. |

### 5.3 CNP/E-Commerce Features (Columns 17–27)
| # | Feature Name | Input Type | Description / Generation Rule | Value for P2P Transactions |
|---|---|---|---|---|
| 17 | `is_high_risk_category` | `int` | $1$ if `MerchantCategory` $\in \{\text{Gaming, Digital Goods, Jewellery, Electronics}\}$. | Set to `0`. |
| 18 | `is_new_merchant_for_customer` | `int` | $1$ if first time customer shops with merchant. | Set to `0`. |
| 19 | `has_device_id` | `int` | $1$ if `DeviceID` is not NULL, else $0$. | Set to `0`. |
| 20 | `has_ip_address` | `int` | $1$ if `IPAddress` is not NULL, else $0$. | Set to `0`. |
| 21 | `has_location` | `int` | $1$ if `Location` is not NULL, else $0$. | Set to `0`. |
| 22 | `has_card_token` | `int` | $1$ if `CardReferenceToken` is not NULL, else $0$. | Set to `0`. |
| 23 | `is_merchant_missing` | `int` | $1$ if `MerchantID` is NULL, else $0$. | Set to `0`. |
| 24 | `device_changed_for_account` | `int` | $1$ if `DeviceID` differs from sender's prior device. | Set to `0`. |
| 25 | `location_changed_for_account` | `int` | $1$ if `Location` differs from sender's prior location. | Set to `0`. |
| 26 | `has_device_history` | `int` | $1$ if sender has prior device/location history, else $0$. | Set to `0`. |
| 27 | `merchant_risk_rate` | `float` | Looked up via `MerchantRiskEncoder.transform()`. | Falls back to global rate (`0.0306`). |

### 5.4 Categorical Features (Columns 28–30)
| # | Feature Name | Domain Values | Imputation if Missing |
|---|---|---|---|
| 28 | `sender_account_type` | `'Savings'`, `'Current'` | `'MISSING'` |
| 29 | `receiver_shape` | `'account_only'`, `'account_and_upi'`, `'external_upi_only'`, `'NOT_APPLICABLE'` | `'MISSING'` |
| 30 | `merchant_category` | Category string (e.g. `'Electronics'`), or `'NOT_APPLICABLE'` | `'MISSING'` |

---

## 6. Preprocessing & Artifact Loading Protocol

In Phase 2, Person 1's inference code will execute the following standard sequence:

```python
import joblib
from ml.features import MerchantRiskEncoder, build_features

# 1. Load persisted artifacts once during service startup
pipeline = joblib.load("ml/models/random_forest_full_disposable_33070.joblib")
merchant_encoder = MerchantRiskEncoder.load("ml/models/merchant_risk_encoder_disposable_33070.json")

# 2. Extract raw transaction rows from MySQL into DataFrame (df_raw)

# 3. Transform features
df_features = build_features(df_raw)
df_features["merchant_risk_rate"] = merchant_encoder.transform(df_features, is_train=False)

# 4. Predict probabilities
feature_cols = [
    # 27 numeric features + 3 categorical features in exact contract order
    "amount", "amount_log", "amount_zscore_sender", "hour_of_day", "day_of_week",
    "is_night", "is_festival_day", "sender_account_age_days", "has_sender_history",
    "sender_txn_count_10m", "sender_txn_count_60m", "sender_txn_count_1440m",
    "sender_amount_sum_60m", "is_new_receiver", "sender_fanout_60m",
    "sender_fanout_1440m", "is_high_risk_category", "is_new_merchant_for_customer",
    "has_device_id", "has_ip_address", "has_location", "has_card_token",
    "is_merchant_missing", "device_changed_for_account", "location_changed_for_account",
    "has_device_history", "merchant_risk_rate", "sender_account_type",
    "receiver_shape", "merchant_category"
]

probabilities = pipeline.predict_proba(df_features[feature_cols])[:, 1]
```
