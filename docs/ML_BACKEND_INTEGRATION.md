# Machine Learning Backend Integration Guide

**Project:** Banking Transaction and Fraud Detection System  
**Roles:** Person 2 (ML Developer) $\longrightarrow$ Person 1 (Backend & Database Developer)  
**Status:** Ready for Integration  
**Date:** 2026-11-24  

---

## 1. Overview

This document specifies the exact programmatic interface for Person 1 to score transactions, generate risk predictions, and optionally extract explainability attributions using the Phase 2 inference module (`ml/predict.py`).

Person 1's backend services can import and invoke these functions directly in Python without modifying any machine learning code or loading raw training scripts.

---

## 2. Quick Start & Public Functions

```python
from ml.predict import predict_transaction, predict_batch
from ml.model_explainer import explain_transaction
```

### 2.1 Function Signatures

```python
def predict_transaction(
    transaction: dict | pd.Series | pd.DataFrame,
    explain: bool = False,
    historical_context: pd.DataFrame | list[dict] | None = None,
    predictor: FraudPredictor | None = None,
) -> dict[str, Any]:
    ...

def predict_batch(
    transactions: pd.DataFrame | list[dict],
    explain: bool = False,
    historical_context: pd.DataFrame | list[dict] | None = None,
    errors: Literal["raise", "coerce"] = "raise",
    predictor: FraudPredictor | None = None,
) -> list[dict[str, Any]]:
    ...
```

---

## 3. Standardized Output Schema

Every scored transaction produces a dictionary strictly complying with Person 1's backend contract:

```json
{
  "transaction_id": 10001,
  "fraud_probability": 0.8700,
  "prediction": "FRAUDULENT",
  "model_version": "rf_v1.0",
  "risk_status": "HIGH",
  "merchant_risk_rate": 0.3500
}
```

### Output Field Mapping for MySQL Write-Back
| Key | Python Type | Domain | Target DB Column | Write-Back Logic |
|---|---|---|---|---|
| `transaction_id` | `int` | $\ge 1$ | `Transaction.TransactionID` | Primary Key lookup |
| `fraud_probability` | `float` | `[0.0000, 1.0000]` | `Transaction.FraudScore` | Stored as `DECIMAL(5,4)` |
| `prediction` | `str` | `'LEGITIMATE'`, `'FRAUDULENT'` | `Transaction.FraudPrediction` | Classification at threshold `0.21` |
| `model_version` | `str` | `'rf_v1.0'` | Audit log / metadata | Model provenance tracking |
| `risk_status` | `str` | `'LOW'`, `'MEDIUM'`, `'HIGH'` | `Transaction.RiskStatus` | Operational risk band |
| `merchant_risk_rate` | `float` | `[0.0000, 1.0000]` | Feature audit / metrics | Precomputed training risk rate |
| `explanation` *(optional)* | `dict` | Schema below | `Fraud_Alert.Notes` / UI | Present only if `explain=True` |

### Optional Explanation Payload (when `explain=True`)
```json
{
  "explanation": {
    "top_reasons": [
      {
        "feature": "is_night",
        "contribution": 0.0946,
        "direction": "INCREASES_RISK"
      },
      {
        "feature": "sender_amount_sum_60m",
        "contribution": 0.0812,
        "direction": "INCREASES_RISK"
      },
      {
        "feature": "sender_account_age_days",
        "contribution": -0.0769,
        "direction": "DECREASES_RISK"
      }
    ],
    "base_value": 0.5000,
    "fraud_probability": 0.8700
  }
}
```

---

## 4. Input Schemas

The prediction engine accepts two input formats:

### Format A: Raw Transaction Record (from SQL Query)
When Person 1 queries new unscored transactions from MySQL, provide the following dictionary or DataFrame:

```python
raw_transaction = {
    "TransactionID": 10001,
    "TransactionTimestamp": "2026-11-20 23:15:00",
    "Amount": 45000.0,
    "SenderAccountNumber": 1000000001,
    "ReceiverAccountNumber": 1000000042,
    "ReceiverUPIID": None,
    "TransactionTypeName": "P2P_UPI",
    "MerchantID": None,
    "MerchantCategory": None,
    "DeviceID": "DEV-9901",
    "IPAddress": "192.168.1.1",
    "Location": "Mumbai",
    "CardReferenceToken": None,
    "SenderCustomerID": 501,
    "SenderAccountType": "Savings",
    "SenderAccountCreatedAt": "2025-01-10 10:00:00"
}
```

#### Historical Context for Single Real-Time Transactions:
`build_features()` calculates rolling aggregations (e.g., `sender_txn_count_60m`, `amount_zscore_sender`, `device_changed_for_account`).
- For **batch scoring** (`predict_batch`), pass the transactions sorted chronologically. Rolling aggregates are computed across the batch.
- For **single real-time scoring** (`predict_transaction`), pass the sender's preceding transactions in the `historical_context` parameter (e.g., transactions from the past 24 hours):
  ```python
  result = predict_transaction(current_raw_txn, historical_context=sender_recent_txns)
  ```

### Format B: Precomputed Features
If Person 1 extracts or precomputes the 30 features, pass them directly. Missing `merchant_risk_rate` is populated automatically from the persisted encoder:
```python
feature_dict = {
    "TransactionID": 10001,
    "amount": 45000.0,
    "amount_log": 10.7144,
    "amount_zscore_sender": 2.85,
    "hour_of_day": 23,
    "day_of_week": 4,
    "is_night": 1,
    "is_festival_day": 0,
    "sender_account_age_days": 314,
    "has_sender_history": 1,
    "sender_txn_count_10m": 3,
    "sender_txn_count_60m": 5,
    "sender_txn_count_1440m": 7,
    "sender_amount_sum_60m": 82000.0,
    "is_new_receiver": 1,
    "sender_fanout_60m": 4.0,
    "sender_fanout_1440m": 6.0,
    "is_high_risk_category": 0,
    "is_new_merchant_for_customer": 0,
    "has_device_id": 1,
    "has_ip_address": 1,
    "has_location": 1,
    "has_card_token": 0,
    "is_merchant_missing": 1,
    "device_changed_for_account": 1,
    "location_changed_for_account": 1,
    "has_device_history": 1,
    "sender_account_type": "Savings",
    "receiver_shape": "account_only",
    "merchant_category": "NOT_APPLICABLE",
}
result = predict_transaction(feature_dict)
```

---

## 5. Thresholds & Risk Status Rules

### 5.1 Binary Decision Threshold
- Cutoff: **`0.2100`**
- `fraud_probability >= 0.2100` $\implies$ `'FRAUDULENT'`
- `fraud_probability < 0.2100` $\implies$ `'LEGITIMATE'`

### 5.2 Operational Risk Status Mapping
- **`LOW`**: `0.00 <= fraud_probability < 0.10`  
  *Action:* Normal processing. No alert created.
- **`MEDIUM`**: `0.10 <= fraud_probability < 0.21`  
  *Action:* Passive monitoring / elevated caution. Classified as legitimate by binary cutoff.
- **`HIGH`**: `0.21 <= fraud_probability <= 1.00`  
  *Action:* Triggers insertion into `Fraud_Alert` table with `ReviewStatus = 'OPEN'`.

---

## 6. Error Handling & Batch Resilience

In `predict_batch()`:
- `errors="raise"` (default): Fails immediately if any transaction fails validation or type casting. Recommended for staging/development.
- `errors="coerce"`: Catches per-row exceptions and returns an error record:
  ```json
  {
    "transaction_id": 10042,
    "error": "Missing required field Amount",
    "status": "FAILED"
  }
  ```
  Ensures that a single corrupted record in a 10,000-row batch does not abort the scoring pipeline.

---

## 7. Performance Guidelines

1. **Singleton Caching:** `predict_transaction` and `predict_batch` use an internal singleton `FraudPredictor` by default. Model weights and encoders are loaded into memory once and reused across all requests.
2. **Selective Explainability:** Leave `explain=False` during batch write-back jobs to achieve $> 5,000 \text{ txns/sec}$. Set `explain=True` only when generating analyst notes for `HIGH` risk alerts or displaying cards in Streamlit.
