# Phase 3 Feature Dictionary (design only — nothing implemented yet)

Companion to `docs/PHASE3_ML_DESIGN.md`. Every feature below is defined
against the schema in `docs/DATABASE_DESIGN.md` / `database/schema.sql`. The
"Leakage note" column states explicitly why the feature is safe to use at
the moment a transaction is created, since that is the project's single
biggest ML risk (see `docs/PROJECT_HANDOVER.md` Section 6).

Legend for **Applies to**: `ALL` = every transaction, `P2P` = `P2P_UPI` rows
only, `CNP` = `CNP_ECOM` rows only.

---

## 1. Excluded columns (never features)

| Column / file | Reason excluded |
|---|---|
| `Account.Balance` | Post-event ledger state; reflects the outcome of transactions including the one being scored. |
| `data_generation/output/opening_balances.csv` | Ledger-replay artifact of the generator; same post-event problem as `Account.Balance`. |
| `Transaction.Status` | Can be a *consequence* of a fraud event (`REVERSED`/`FAILED`), not a cause; known only after processing. |
| `Transaction.FraudScore` / `FraudPrediction` / `RiskStatus` | Target-derived — these are what Phase 3/4 produce, always `NULL`/`NOT_SCORED` for an unscored row. |
| `Fraud_Alert.*`, `Investigation.*` | Exist only as a *result* of a fraud decision (currently 0 rows by design). |
| `labels.csv: Scenario`, `labels.csv: Pattern` | Dataset-generation ground truth, never observable by a real scorer. Used only to build `IsFraud` and for post-hoc error analysis. |
| `TransactionID`, `CustomerID`, `AccountNumber`, `MerchantID` | Join keys only — not predictive signal, dropped before fitting to avoid ID-overfitting. |

## 2. Common features (ALL transactions)

| Feature | Source | Definition | Leakage note |
|---|---|---|---|
| `amount` | `Transaction.Amount` | Raw transaction amount. | Known at transaction creation. |
| `amount_log` | derived | `log1p(Amount)` | Same source; monotonic transform only. |
| `amount_zscore_sender` | derived | `(Amount - mean) / std` of the sender's *prior* transaction amounts (expanding window, current row excluded). | Uses only transactions with an earlier `TransactionTimestamp` for this `SenderAccountNumber`. First transaction for an account has no prior history → imputed as 0 (neutral) with a companion `has_sender_history` flag. |
| `hour_of_day` | `Transaction.TransactionTimestamp` | 0–23. | Known at creation. |
| `is_night` | derived | 1 if hour in `{0,1,2,3,4,5}` (matches generator's `NIGHT_HOURS`). | Known at creation. |
| `day_of_week` | derived | 0–6. | Known at creation. |
| `is_festival_day` | derived | 1 if the transaction date is in a fixed festival-date list (matches generator's `FESTIVAL_DAYS`); maintained as project config, not learned from the data. | Known at creation (calendar fact, not data-derived). |
| `account_type` | `Account.AccountTypeID` → `AccountType.TypeName` | `Savings` / `Current`, one-hot encoded. | Static account attribute, known before the transaction. |
| `account_age_days` | `Account.CreatedAt` | `TransactionTimestamp - Account.CreatedAt`, in days. | `CreatedAt` predates the transaction by construction. |
| `account_status` | `Account.AccountStatus` | `ACTIVE`/`DORMANT`/`FROZEN`/`CLOSED` at account level, one-hot encoded. | Static attribute as of now; in production this should be read as of the transaction time if it can change, but it is not a function of this transaction's outcome. |
| `sender_txn_count_10m` / `_60m` / `_1440m` | derived | Count of the sender's transactions in the trailing 10/60/1440 minutes, current row excluded. | Strictly prior timestamps only (`groupby('SenderAccountNumber').shift`/rolling on sorted frame). |
| `sender_amount_sum_60m` | derived | Sum of sender's transaction amounts in the trailing 60 minutes, current row excluded. | Same as above. |
| `has_sender_history` | derived | 1 if the sender has ≥1 prior transaction, else 0. | Structural flag from the same prior-only aggregation. |

## 3. P2P/UPI-specific features (`Applies to: P2P`)

| Feature | Source | Definition | Leakage note |
|---|---|---|---|
| `receiver_shape` | `Transaction.ReceiverAccountNumber`, `ReceiverUPIID` | Categorical: `account_only` / `account_and_upi` / `external_upi_only` (mirrors generator's `P2P_RECEIVER_MIX`, but this is a real routing signal available at transaction time, not a generator artifact). | Both columns are populated when the transaction is created. |
| `is_new_receiver` | derived | 1 if this is the first transaction from this sender to this receiver (account number or UPI ID), using prior transactions only. | Prior-only lookup, same rule as Section 2. |
| `sender_fanout_60m` / `_1440m` | derived | Count of *distinct* receivers the sender has paid in the trailing 60/1440 minutes, current row excluded. Targets the `fan_out` fraud pattern directly. | Prior-only aggregation. |

## 4. CNP/e-commerce-specific features (`Applies to: CNP`)

| Feature | Source | Definition | Leakage note |
|---|---|---|---|
| `merchant_category` | `Merchant.Category` | One-hot encoded (`Electronics`, `Gaming`, `Jewellery`, etc.). | Static merchant attribute, known at transaction time. |
| `is_high_risk_category` | derived | 1 if `merchant_category` in `{Gaming, Digital Goods, Jewellery, Electronics}` (matches generator's `HIGH_RISK_CATEGORIES`; used because it's legitimate standing metadata about the merchant). | Static, no post-event leakage. **Dataset-construction caveat** (not a leakage bug): confirmed in the generator and in `validate_data.py`'s own output that every `merchant_anomaly` fraud row (72/600) is in a high-risk category by construction — see `docs/PHASE3_ML_DESIGN.md`, "Known synthetic-dataset caveat." Report that pattern's recall as a property of this dataset, not a generalizable claim. |
| `merchant_risk_rate` | derived | Fraud rate among this merchant's transactions, computed **from the training split only** and looked up (never recomputed per-row from the full dataset) for validation/test rows. A merchant unseen in training falls back to the global training fraud rate. | Fit-on-train, apply-to-val/test — the standard safeguard against target leakage for any rate/frequency encoding. |
| `is_new_merchant_for_customer` | derived | 1 if this is the first transaction this customer has made with this merchant, using prior transactions only. Targets `merchant_anomaly` / `new_merchant_trial`. | Prior-only lookup. |
| `has_device_id`, `has_ip_address`, `has_location`, `has_card_token` | `Transaction.DeviceID` / `IPAddress` / `Location` / `CardReferenceToken` | 1 if the field is non-null. Targets `card_testing` (null card token is CNP-only by schema design) and general missingness patterns from `CNP_FIELD_NULL_RATE`. | Known at transaction creation; null itself is a point-in-time fact, not a post-event one. |
| `is_merchant_missing` | `Transaction.MerchantID` | 1 if null (documented edge case, `CNP_MERCHANT_NULL_RATE`). | Known at creation. |
| `device_changed_for_account` | derived | 1 if `DeviceID` differs from the sending account's most recent non-null prior `DeviceID`. Targets `device_geo_change`. | Prior-only lookup; first transaction (no prior device) imputed as 0 with a `has_device_history` flag. |
| `location_changed_for_account` | derived | Same construction as `device_changed_for_account`, using `Location`. | Prior-only lookup. |

## 5. Target

| Field | Source | Notes |
|---|---|---|
| `IsFraud` | `labels.csv` | Binary target, merged in pandas on `TransactionID`. Never read from any `Transaction` table column — the schema deliberately has no label column (per `handoff.md`). |

## 6. Dropped-but-retained-for-analysis columns

`Scenario` and `Pattern` from `labels.csv` are kept alongside predictions in
a separate analysis frame (never concatenated into the feature matrix passed
to `fit`/`predict`) so that per-pattern recall can be reported — e.g. "the
model catches 95% of `velocity_burst` but only 60% of `card_testing`" — a
far more useful breakdown for an academic report than a single aggregate
recall number, and the only place `Pattern`/`Scenario` are allowed to appear
in the ML code path.
