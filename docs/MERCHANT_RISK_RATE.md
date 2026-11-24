# Merchant Risk Rate Audit & Specification

**Project:** Banking Transaction and Fraud Detection System  
**Role:** Person 2 – Machine Learning Developer  
**Date:** 2026-11-24  
**Module:** `ml/features.py` (`MerchantRiskEncoder`, `add_merchant_risk_rate`)  
**Artifact:** `ml/models/merchant_risk_encoder_disposable_33070.json`

---

## 1. Executive Summary & Audit Purpose

The `merchant_risk_rate` feature encodes historical merchant fraud propensity for Card-Not-Present (CNP) transactions. In a machine learning fraud detection pipeline, target encoding (using label statistics as a feature) is susceptible to **catastrophic target leakage** if not structured with strict partition boundaries and leave-one-out safeguards.

This audit evaluates the current implementation, verifies mathematical leak-free guarantees, and provides a serializable transformer (`MerchantRiskEncoder`) so that Person 1's inference pipeline can score new transactions without access to ground-truth fraud labels.

---

## 2. Source Data & Mathematical Definition

### 2.1 Source Attributes
- `MerchantID`: Foreign key referencing `Merchant.MerchantID` (present for ~98% of CNP transactions; NULL for P2P transactions and ~2% CNP edge cases).
- `IsFraud`: Ground-truth binary label from `data_generation/output/labels.csv` (strictly training split only).
- `TransactionTimestamp`: Used to assign the chronological split.

### 2.2 Mathematical Formulation

1. **Global Base Rate ($\bar{y}_{\text{global}}$):**
   $$\bar{y}_{\text{global}} = \frac{1}{|D_{\text{train}}|} \sum_{i \in D_{\text{train}}} y_i \approx 0.030585 \quad (3.06\%)$$

2. **Merchant Historical Aggregate on Training Split:**
   For each merchant $m$, with count $N_m = \sum_{i \in D_{\text{train}}} \mathbb{I}(m_i = m)$ and fraud sum $S_m = \sum_{i \in D_{\text{train}}, m_i = m} y_i$:
   - If $N_m > 0$: $\hat{r}_m = \frac{S_m}{N_m}$
   - If $N_m = 0$ (unseen merchant): $\hat{r}_m = \bar{y}_{\text{global}}$

3. **Training Split – Leave-One-Out (LOO) Transformation:**
   To prevent self-leakage (a transaction's own label predicting itself):
   $$\text{LOO}_i = \begin{cases} 
   \frac{S_{m_i} - y_i}{N_{m_i} - 1} & \text{if } N_{m_i} > 1 \\ 
   \bar{y}_{\text{global}} & \text{if } N_{m_i} \le 1 \text{ or } m_i \text{ is NULL} 
   \end{cases}$$

4. **Validation, Test, and Live Inference Transformation:**
   For any evaluation or live inference record $j$:
   $$r_j = \begin{cases} 
   \hat{r}_{m_j} & \text{if } m_j \text{ was observed in training} \\ 
   \bar{y}_{\text{global}} & \text{if } m_j \text{ is unseen, missing, or P2P} 
   \end{cases}$$

---

## 3. Detailed Audit Findings

| Audit Question | Assessment | Verification Evidence |
|---|---|---|
| **Source Data Used** | `MerchantID` and `IsFraud` from the training split. | Verified in `ml/features.py:add_merchant_risk_rate`. |
| **Uses Fraud Labels?** | **Yes, but strictly training labels.** No validation/test labels are used. | `train_mask = (split == "train").to_numpy()` isolates training data. |
| **Aggregation Level** | Merchant-specific (`groupby("MerchantID")`). | Evaluated across 60 distinct merchants in the synthetic dataset. |
| **Smoothing Applied?** | Empirical ratio $\frac{S_m}{N_m}$ without Laplacian additive smoothing. | Safe because sample sizes per merchant in train range from 50 to 120 transactions ($N_m \gg 1$). |
| **Missing Merchants Handled?** | Handled. P2P rows and NULL `MerchantID` rows assign $\bar{y}_{\text{global}}$. | Verified by `.fillna(global_rate)`. |
| **Target Leakage Risk?** | **Zero leakage.** | LOO prevents self-leakage on train; test/val splits use frozen train mapping. |
| **Inference Reusability?** | **Previously Defective / Missing Artifact.** | The original function did not persist `plain_rate` or `global_rate`, preventing offline inference. |

---

## 4. Empirical Distribution of Merchant Risk (Training Split)

- **Total Merchants:** 60 merchants
- **Global Training Fraud Rate:** `0.030585` (3.06%)
- **Highest Risk Merchants:**
  - `MerchantID 11`: $N = 82, \text{Fraud} = 15 \implies 18.29\%$
  - `MerchantID 52`: $N = 115, \text{Fraud} = 20 \implies 17.39\%$
  - `MerchantID 18`: $N = 72, \text{Fraud} = 10 \implies 13.89\%$
  - `MerchantID 34`: $N = 66, \text{Fraud} = 8 \implies 12.12\%$
  - `MerchantID 36`: $N = 81, \text{Fraud} = 9 \implies 11.11\%$
- **Lowest Risk Merchants:**
  - `MerchantID 8`: $N = 71, \text{Fraud} = 0 \implies 0.00\%$
  - `MerchantID 19`: $N = 92, \text{Fraud} = 0 \implies 0.00\%$
  - `MerchantID 10`: $N = 101, \text{Fraud} = 1 \implies 0.99\%$
  - `MerchantID 1`: $N = 98, \text{Fraud} = 1 \implies 1.02\%$
  - `MerchantID 9`: $N = 85, \text{Fraud} = 1 \implies 1.18\%$

---

## 5. Reusable & Serializable Architecture: `MerchantRiskEncoder`

To support standalone production inference (Person 1's backend in Phase 2), `ml/features.py` is equipped with `MerchantRiskEncoder`.

### Interface Specification
```python
class MerchantRiskEncoder:
    def fit(self, train_df: pd.DataFrame, merchant_col="MerchantID", target_col="IsFraud") -> "MerchantRiskEncoder"
    def transform(self, df: pd.DataFrame, is_train: bool = False, merchant_col="MerchantID", target_col="IsFraud") -> pd.Series
    def to_dict(self) -> dict
    def save(self, filepath: str | Path) -> None
    @classmethod
    def load(cls, filepath: str | Path) -> "MerchantRiskEncoder"
```

### Artifact Schema (`merchant_risk_encoder_disposable_33070.json`)
```json
{
  "global_rate": 0.03058542413381123,
  "fallback_rate": 0.03058542413381123,
  "merchant_rates": {
    "1": 0.01020408163265306,
    "2": 0.03488372093023256,
    "...": "..."
  },
  "merchant_counts": {
    "1": 98,
    "2": 86,
    "...": "..."
  },
  "is_fitted": true
}
```

---

## 6. Integration Contract for Person 1 (Live Inference)

At live inference time:
1. Load model: `pipeline = joblib.load('ml/models/random_forest_full_disposable_33070.joblib')`.
2. Load merchant encoder: `encoder = MerchantRiskEncoder.load('ml/models/merchant_risk_encoder_disposable_33070.json')`.
3. Compute features: `features_df = build_features(new_txn_df)`.
4. Apply merchant risk: `features_df['merchant_risk_rate'] = encoder.transform(features_df, is_train=False)`.
5. Predict: `probability = pipeline.predict_proba(features_df[feature_columns])[:, 1]`.
