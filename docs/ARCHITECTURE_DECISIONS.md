# Architecture Decisions

Design assumptions and tradeoffs recorded during Phase 1, in the order raised by
`Banking_Synopsis.pdf`, `Banking_ER_Notes.docx`, `Banking_Requirements.docx` and
`Banking_Fraud_Detection_DFD.pdf`. None of these conflict across the four documents.

## A. Fraud alerts: one per transaction
Decision: `Fraud_Alert.TransactionID` is `UNIQUE`.
Reasoning: the ER notes draw the Transaction-to-Fraud_Alert cardinality as 1:0..1 and
explicitly recommend this unless the team decides otherwise. The requirements doc
repeats the same conditional ("if only one alert is permitted..., make TransactionID
unique"). No document asks for repeat/multiple alerts per transaction.
Assumption: at most one alert per transaction. If re-scoring should be able to raise a
new alert on the same transaction later, this would need to change to a non-unique FK
plus an `AlertStatus` to distinguish active from superseded alerts — not needed for
Phase 1.

## B. Investigation participation is optional
Decision: `Investigation` rows are created only when an investigation actually starts;
no trigger or constraint forces one to exist for every alert.
Reasoning: both the ER notes and requirements doc explicitly flag this as a point the
team must decide, and both lean toward allowing an alert to remain un-investigated.
This is enforced naturally by Investigation being a separate table with no NOT NULL
backlink from Fraud_Alert.

## C. Account references
Decision: `Transaction.SenderAccountNumber` and `Transaction.ReceiverAccountNumber`
both reference `Account(AccountNumber)` via foreign keys with `ON UPDATE RESTRICT ON
DELETE RESTRICT`.
Reasoning: this is explicit in the ER notes' "Suggested Foreign-Key References"
section. RESTRICT (rather than CASCADE) prevents silently deleting or renumbering
transaction history if an account row is ever removed or its AccountNumber changed —
appropriate for an auditable financial record (NFR-10): once a transaction references
an account, that reference must stay exactly as recorded.

This is also a hard MySQL requirement, not just a style choice: these two columns are
also covered by `chk_txn_sender_receiver_distinct` (decision below), and MySQL 8.0
(error 3823) forbids a column referenced by a CHECK constraint from also carrying a
foreign-key referential action other than RESTRICT/NO ACTION — `ON UPDATE CASCADE`
on either FK fails table creation outright. Every other foreign key in the schema
(Account.CustomerID/AccountTypeID, Transaction.TransactionTypeID/MerchantID,
Fraud_Alert.TransactionID, Investigation.AlertID) references a column with no CHECK
constraint on it, so those are unaffected and keep `ON UPDATE CASCADE`.

## D. Nullable fields
Decision: `ReceiverAccountNumber`, `ReceiverUPIID` and `MerchantID` are nullable.
Reasoning: directly required by the DFD's stated rules ("ReceiverAccountNumber /
ReceiverUPIID may be NULL when not applicable. MerchantID may be NULL for P2P/UPI.")
and by FR-06/FR-07. CNP-specific fields (DeviceID, IPAddress, Location,
CardReferenceToken) are nullable. Only CardReferenceToken is category-restricted
(CNP only); DeviceID, IPAddress and Location are general ML metadata for any row.

## E. Transaction types as master records
Decision: `AccountType` and `TransactionType` are master tables with surrogate
AUTO_INCREMENT IDs and a UNIQUE `TypeName`, seeded by `master_data.sql`.
Reasoning: required by FR-03/FR-04 and the synopsis ("classified through AccountType",
"use TransactionType to distinguish"). Avoids hardcoded magic IDs in application code
by letting it look up IDs by name.

## F. Fraud prediction fields exist before scoring
Decision: `Transaction.FraudScore` and `FraudPrediction` are nullable with no default
value; `RiskStatus` is NOT NULL with `DEFAULT 'NOT_SCORED'`.
Reasoning: the synopsis and DFD both describe scoring as a step that happens after a
transaction is recorded ("2.0 Record & Retrieve Transactions" feeds "3.0 Extract
Features & Predict Fraud", which then stores "score, prediction and status"). A
transaction must be insertable before any model exists or has run.
Range constraint: `CHECK (FraudScore IS NULL OR FraudScore BETWEEN 0 AND 1)` — treats
the score as a probability.

## G. Status fields kept separate
Decision: four distinct status-like fields are never merged:
- `Transaction.Status` — operational outcome (PENDING/SUCCESS/FAILED/REVERSED)
- `Transaction.FraudPrediction` / `Transaction.RiskStatus` — model output
- `Fraud_Alert.ReviewStatus` — analyst review of the alert
- `Investigation.ResolutionStatus` / `Investigation.Outcome` — investigation progress
  and conclusion
Reasoning: these represent different processes owned by different actors (payment
processing vs. ML scoring vs. fraud review vs. investigation), matching the DFD's
separate processes 2.0-5.0. Merging them would force invalid combinations (e.g. a
"FAILED" payment showing a fraud review status) and complicate querying each process
independently (FR-18 reporting, NFR-01).

## H. Monetary data types
Decision: `Account.Balance` and `Transaction.Amount` are `DECIMAL(15,2)`; `FraudScore`
and `RiskScoreAtAlert` are `DECIMAL(5,4)`. No `FLOAT`/`DOUBLE` is used anywhere.
Reasoning: explicit instruction and standard practice — binary floating point cannot
represent currency exactly, and comparisons/CHECK constraints over FLOAT are unsafe.

## I. Added CHECK constraints and inline indexes
Decision: three CHECKs were added after review. `chk_txn_scoring_consistent` stops a
half-scored row (score without prediction, or a risk level on an unscored row).
`chk_txn_card_token_not_pan` strips every non-alphanumeric character from
`CardReferenceToken` and rejects 12 or more consecutive digits (NFR-03), so separators,
`tok_<PAN>` and fullwidth digits cannot hide a card number; tradeoff: a legitimate token
with 12+ digits in a row is rejected too. It is a guard, not proof a token is safe. `chk_investigation_resolution` ties `ResolutionStatus`,
`ResolutionDate` and `Outcome` together (RESOLVED needs a date and a non-PENDING
outcome; any other status needs no date). None of these columns carry a CASCADE or SET
NULL foreign-key action, so error 3823 does not apply.
Indexes are declared inline in each `CREATE TABLE` (same names as before) because MySQL
has no `CREATE INDEX IF NOT EXISTS`, so standalone statements broke re-runs. They also
cannot be dropped separately while a foreign key needs them (error 1553).

## Additional assumptions made (not explicit in source documents)

1. **`Account.Balance >= 0` CHECK constraint.** No document mentions overdrafts, so
   Phase 1 assumes non-negative balances for both Savings and Current accounts. If the
   team wants Current-account overdraft, relax or scope this constraint later.
2. **`AccountNumber` is a surrogate `BIGINT UNSIGNED AUTO_INCREMENT`**, seeded to start
   at `100000000001` purely for a bank-like appearance. It is not a checksum-validated
   real-world account number format, which is out of scope for an academic prototype.
3. **Sender/receiver distinctness CHECK** (`ReceiverAccountNumber <> SenderAccountNumber`
   when both are present) — a reasonable data-integrity rule not explicitly stated in
   the source documents but consistent with FR-17 ("validate ... allowed values").
4. **No trigger-based alert generation in Phase 1.** The synopsis describes "a database
   trigger will flag high-risk records and create alerts" as part of the overall system,
   but that depends on a scoring threshold and ML output that do not exist yet. Writing
   that trigger now would hardcode an arbitrary threshold ahead of the ML work in a
   later phase. Phase 1 only provides the schema `Fraud_Alert` is inserted into, by
   application code or a trigger, once Phase 2+ defines the threshold.
5. **CNP vs. P2P field consistency is enforced by triggers (user decision, FR-17), not a
   CHECK.** A CHECK cannot look up `TransactionType` by name without hardcoding an ID,
   so `trg_txn_category_bi`/`trg_txn_category_bu` call `sp_validate_transaction_category`,
   which resolves the type by `TypeName`. Rules: P2P_UPI needs a receiver account or UPI
   ID and no MerchantID or CardReferenceToken; CNP_ECOM allows no receiver account or UPI
   ID and MerchantID stays optional. DeviceID, IPAddress and Location are general ML
   metadata and are not restricted by category. A blank or whitespace-only UPI ID does
   not count as a receiver. A type row with an unexpected TypeName is rejected (so rules
   are never silently skipped); a type ID with no row is left to the FK (1452).
   `IF NOT EXISTS` will not replace an already-created procedure, so
   `upgrade_existing_schema.sql` (non-destructive, stops if stored rows violate the new
   constraints) is the single upgrade path for older databases. Cost: needs MySQL 8.0.29+ for `IF NOT EXISTS`, and a trigger adds a lookup per
   write (acceptable at this scale).
6. **`Transaction` is backtick-quoted everywhere it appears as a table identifier.**
   `TRANSACTION` is a non-reserved word in MySQL 8.0 and should work unquoted, but it
   was quoted defensively since the scripts could not be execution-tested against the
   project's MySQL server in this session (see `PHASE_TRACKER.md`).

## Unresolved / left to the team

- Whether Current accounts should support overdraft (would change the Balance CHECK).
- The exact fraud-score threshold and whether alert creation is a trigger vs.
  application logic (Phase 2+ decision, once a model exists).
- Whether a closed/reversed transaction should still be eligible for an alert.
