# Database Design

Banking Transaction and Fraud Detection System — MySQL 8.x, InnoDB, utf8mb4.
Source scripts: `database/schema.sql`, `database/master_data.sql`, `database/verification.sql`.

## Entity-relationship summary

```
Customer (1) ---- owns ---- (N) Account (N) ---- has_type ---- (1) AccountType
                                  |  \
                                  |   \__ receives (1:N, nullable FK)
                                sends (1:N)
                                  |
                                  v
                              Transaction (N) ---- has_type ---- (1) TransactionType
                                  |        \
                                  |         \__ processed_by (N:1, nullable FK)
                                  |                  Merchant
                                  v
                            Fraud_Alert (0..1 per Transaction, UNIQUE FK)
                                  |
                                  v
                            Investigation (0..1 per Alert, UNIQUE FK)
```

## Tables

### Customer
| Column | Type | Constraints |
|---|---|---|
| CustomerID | INT UNSIGNED | PK, AUTO_INCREMENT |
| FirstName | VARCHAR(50) | NOT NULL |
| LastName | VARCHAR(50) | NOT NULL |
| DateOfBirth | DATE | NOT NULL |
| Email | VARCHAR(100) | NOT NULL, UNIQUE |
| Phone | VARCHAR(15) | NOT NULL, UNIQUE |
| Address | VARCHAR(255) | NULL |
| CreatedAt | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP |

### AccountType (master)
| Column | Type | Constraints |
|---|---|---|
| AccountTypeID | INT UNSIGNED | PK, AUTO_INCREMENT |
| TypeName | VARCHAR(30) | NOT NULL, UNIQUE |
| Description | VARCHAR(255) | NULL |

Seed rows: `Savings`, `Current`.

### Account
| Column | Type | Constraints |
|---|---|---|
| AccountNumber | BIGINT UNSIGNED | PK, AUTO_INCREMENT (seeded from 100000000001) |
| CustomerID | INT UNSIGNED | NOT NULL, FK -> Customer.CustomerID |
| AccountTypeID | INT UNSIGNED | NOT NULL, FK -> AccountType.AccountTypeID |
| Balance | DECIMAL(15,2) | NOT NULL, DEFAULT 0.00, CHECK (Balance >= 0) |
| AccountStatus | ENUM('ACTIVE','DORMANT','FROZEN','CLOSED') | NOT NULL, DEFAULT 'ACTIVE' |
| CreatedAt | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP |

Indexes: CustomerID, AccountTypeID.

### TransactionType (master)
| Column | Type | Constraints |
|---|---|---|
| TransactionTypeID | INT UNSIGNED | PK, AUTO_INCREMENT |
| TypeName | VARCHAR(30) | NOT NULL, UNIQUE |
| Description | VARCHAR(255) | NULL |

Seed rows: `P2P_UPI`, `CNP_ECOM`.

### Merchant
| Column | Type | Constraints |
|---|---|---|
| MerchantID | INT UNSIGNED | PK, AUTO_INCREMENT |
| MerchantName | VARCHAR(100) | NOT NULL |
| Category | VARCHAR(50) | NULL |
| Location | VARCHAR(150) | NULL |
| Website | VARCHAR(150) | NULL |

### Transaction
One common table for both P2P/UPI and CNP/e-commerce transactions.

| Column | Type | Constraints |
|---|---|---|
| TransactionID | BIGINT UNSIGNED | PK, AUTO_INCREMENT |
| TransactionTimestamp | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP |
| Amount | DECIMAL(15,2) | NOT NULL, CHECK (Amount > 0) |
| Status | ENUM('PENDING','SUCCESS','FAILED','REVERSED') | NOT NULL, DEFAULT 'PENDING' |
| SenderAccountNumber | BIGINT UNSIGNED | NOT NULL, FK -> Account.AccountNumber |
| ReceiverAccountNumber | BIGINT UNSIGNED | NULL, FK -> Account.AccountNumber |
| ReceiverUPIID | VARCHAR(100) | NULL |
| TransactionTypeID | INT UNSIGNED | NOT NULL, FK -> TransactionType.TransactionTypeID |
| MerchantID | INT UNSIGNED | NULL, FK -> Merchant.MerchantID |
| DeviceID | VARCHAR(100) | NULL (general ML context metadata, allowed for any category) |
| IPAddress | VARCHAR(45) | NULL (general ML context metadata, allowed for any category) |
| Location | VARCHAR(150) | NULL (general ML context metadata, allowed for any category) |
| CardReferenceToken | VARCHAR(100) | NULL (CNP only; tokenized, never a real card/CVV) |
| FraudScore | DECIMAL(5,4) | NULL, CHECK (0 <= FraudScore <= 1) when present |
| FraudPrediction | ENUM('LEGITIMATE','FRAUDULENT') | NULL |
| RiskStatus | ENUM('NOT_SCORED','LOW','MEDIUM','HIGH') | NOT NULL, DEFAULT 'NOT_SCORED' |
| CreatedAt | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP |

Additional constraints:
- `chk_txn_sender_receiver_distinct`: `ReceiverAccountNumber` must differ from `SenderAccountNumber` when present.
- `chk_txn_scoring_consistent`: either `FraudScore`, `FraudPrediction` NULL and `RiskStatus` = 'NOT_SCORED', or `FraudScore` and `FraudPrediction` both set and `RiskStatus` <> 'NOT_SCORED'.
- `chk_txn_card_token_not_pan` (NFR-03): `CardReferenceToken` is NULL or, after removing every non-alphanumeric character, contains no run of 12 or more digits. This rejects separators of any kind (spaces, hyphens, dots, slashes, underscores, tabs, NBSP), a `tok_` prefix on a PAN, and fullwidth digits; `tok_4f9a2c` passes. Tradeoff: a legitimate token with 12+ consecutive digits is also rejected.

Triggers (FR-17), `trg_txn_category_bi` (BEFORE INSERT) and `trg_txn_category_bu` (BEFORE UPDATE), both call the procedure `sp_validate_transaction_category`, which looks the type up by `TypeName` and raises SQLSTATE 45000 (errno 1644):
- `P2P_UPI`: needs `ReceiverAccountNumber` or a non-blank `ReceiverUPIID` (empty or whitespace-only does not count); `MerchantID` and `CardReferenceToken` must be NULL.
- `CNP_ECOM`: `ReceiverAccountNumber` and `ReceiverUPIID` must be NULL; `MerchantID` is optional.
- A type row that exists under any other `TypeName` is rejected with the same error; a `TransactionTypeID` with no row is left to the foreign key (error 1452).
`database/upgrade_existing_schema.sql` adds missing CHECKs and indexes to databases created from older definitions (IF NOT EXISTS never alters existing tables).
They need MySQL 8.0.29+ (`IF NOT EXISTS`) and are created without dropping anything.

Indexes: SenderAccountNumber, ReceiverAccountNumber, TransactionTypeID, MerchantID, TransactionTimestamp, RiskStatus, Status.

### Fraud_Alert
| Column | Type | Constraints |
|---|---|---|
| AlertID | INT UNSIGNED | PK, AUTO_INCREMENT |
| TransactionID | BIGINT UNSIGNED | NOT NULL, UNIQUE, FK -> Transaction.TransactionID |
| AlertDate | DATETIME | NOT NULL, DEFAULT CURRENT_TIMESTAMP |
| RiskScoreAtAlert | DECIMAL(5,4) | NULL, CHECK (0 <= value <= 1) when present |
| AlertReason | VARCHAR(255) | NULL |
| ReviewStatus | ENUM('OPEN','UNDER_REVIEW','FALSE_POSITIVE','CONFIRMED_FRAUD','CLOSED') | NOT NULL, DEFAULT 'OPEN' |

`UNIQUE(TransactionID)` enforces at most one alert per transaction (1:0..1 from Transaction).

Indexes: `idx_alert_reviewstatus` (ReviewStatus), plus the unique index on TransactionID.

### Investigation
| Column | Type | Constraints |
|---|---|---|
| InvestigationID | INT UNSIGNED | PK, AUTO_INCREMENT |
| AlertID | INT UNSIGNED | NOT NULL, UNIQUE, FK -> Fraud_Alert.AlertID |
| InvestigatorName | VARCHAR(100) | NOT NULL |
| StartDate | DATE | NOT NULL |
| ResolutionDate | DATE | NULL, CHECK (ResolutionDate >= StartDate) when present |
| Notes | TEXT | NULL |
| Outcome | ENUM('PENDING','CONFIRMED_FRAUD','FALSE_POSITIVE','INCONCLUSIVE') | NOT NULL, DEFAULT 'PENDING' |
| ResolutionStatus | ENUM('OPEN','IN_PROGRESS','RESOLVED') | NOT NULL, DEFAULT 'OPEN' |

`chk_investigation_resolution`: `ResolutionStatus` = 'RESOLVED' requires a non-NULL `ResolutionDate` and `Outcome` <> 'PENDING'; any other status requires `ResolutionDate` NULL.

`UNIQUE(AlertID)` enforces the 1:1 cardinality drawn in the ER diagram. An Investigation row is created only when an investigation actually starts, so an alert may legitimately have zero investigation rows.

## Relationship/cardinality reference

| Relationship | Cardinality | Enforced by |
|---|---|---|
| Customer OWNS Account | 1:N | Account.CustomerID FK |
| Account HAS_TYPE AccountType | N:1 | Account.AccountTypeID FK |
| Account SENDS Transaction | 1:N | Transaction.SenderAccountNumber FK |
| Account RECEIVES Transaction | 1:N (optional) | Transaction.ReceiverAccountNumber FK (nullable) |
| Transaction HAS_TYPE TransactionType | N:1 | Transaction.TransactionTypeID FK |
| Merchant PROCESSES Transaction | 1:N (optional) | Transaction.MerchantID FK (nullable) |
| Transaction TRIGGERS Fraud_Alert | 1:0..1 | Fraud_Alert.TransactionID FK + UNIQUE |
| Fraud_Alert LEADS_TO Investigation | 1:0..1 | Investigation.AlertID FK + UNIQUE |

See `docs/ARCHITECTURE_DECISIONS.md` for the reasoning behind each constraint choice.
