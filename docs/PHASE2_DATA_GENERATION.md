# Phase 2: Synthetic Data Generation

Status: built and tested on a throwaway MySQL 8.0.46 instance (port 33070). **Not loaded
into the user's real database.** Not tested in MySQL Workbench itself.

## What was produced
| File | Role |
|---|---|
| `data_generation/config.py` | All counts, rates, ranges, name pools |
| `data_generation/generate_data.py` | Generator (seeded, offline, stdlib only) |
| `data_generation/validate_data.py` | Offline validator of the generated files |
| `database/seed_data.sql` | Generated load script (about 4.1 MB, 21,500 lines) |
| `database/validate_seed_data.sql` | Read-only PASS/FAIL checks on the loaded database. **Generated** together with the seed (it embeds this dataset's exact counts, totals and fingerprints), so regenerate both together |
| `data_generation/output/labels.csv`, `opening_balances.csv`, `manifest.json` | Ground truth, ledger opening/closing balances, counts and checksums |

## Assumptions
- Currency is rupees; all amounts are `DECIMAL(15,2)`. Money is integer paise inside the generator.
- Fixed window 2025-01-01 to 2025-12-31. The generator never reads the clock, so the same
  arguments give byte-identical files (checked on Python 3.11, 3.12, 3.14 and several
  `PYTHONHASHSEED` values).
- The schema has no ground-truth column and `FraudPrediction` is model output, so all rows
  are unscored (`NOT_SCORED`, NULL score, NULL prediction). Truth is only in `labels.csv`.
  No `Fraud_Alert` or `Investigation` rows (those come from later phases).
- All identities are synthetic: names from small pools, `@example.com` emails, phones
  `00000` + 8 digits, fictional addresses, merchants with `.example` websites, UPI IDs ending
  `@synthupi`, IPs only from RFC 5737 ranges, devices `dev_<hex>`, card tokens
  `tok_<lowercase letters>`. No card numbers or CVV.
- Master rows are looked up by `TypeName` in the SQL (`@at_savings` etc.), never by ID.
- P2P rows leave DeviceID, IPAddress, Location, CardReferenceToken and MerchantID NULL
  (CNP-specific in the brief). No blank strings are ever stored; missing means NULL.
- About 2% of CNP rows have no merchant (a documented edge case) and about 5% of each CNP
  device/IP/location/token value is NULL. The same rate applies to every label.
- `--accounts` must be at least `--customers` (every customer gets an account); bad values
  get a clear error.

## Design
- **Ledger.** Rows are processed in time order from opening balances. SUCCESS debits the
  sender and credits an internal receiver; CNP and external-UPI payments only debit. If
  the sender cannot cover it the row becomes FAILED. PENDING, FAILED and REVERSED have no
  balance effect. `Account.Balance` is the closing balance and reconciles with
  `opening_balances.csv`. Only ACTIVE accounts transact, only after `CreatedAt`; customers
  are created before their accounts; all customers are 18+ when created.
- **Opening balances** use no future information and no labels: a random level per account
  (lognormal by account type) of at least 300 times the account's typical amount.
- **Status is label-independent** (90% SUCCESS, 5% FAILED, 3% PENDING, 2% REVERSED); only a
  real shortage changes it.
- **Fraud and look-alikes.** Each pattern has a legitimate look-alike, and the two overlap:

| Fraud pattern | What it does | Legitimate look-alike |
|---|---|---|
| high_amount | 1-2 large payments (15-55% of opening balance) | large_planned_purchase (10-50%) |
| velocity_burst | 5-12 CNP rows in minutes | festival_burst (4-11 rows on festival days) |
| odd_hour | 1-3 rows between 00:00 and 05:59 | night_shift |
| fan_out | 6-14 different recipients within hours | business_payouts (Current accounts) |
| merchant_anomaly | high-risk merchant new to the sender | new_merchant_trial |
| card_testing | 4-9 probes of Rs 1-30, then one larger final charge | small_recurring_payments (subscriptions and small tap runs) |
| device_geo_change | new device, IP and city | travel_purchase (new city and IP, usually same device) |

  Everyday Rs 1-30 payments (6% of normal rows) and Rs 100-rounded amounts (15% of normal,
  30% of fan_out, 50% of business_payouts) keep "small amount" and "round amount" from
  identifying a label. Fraud groups use round-robin shuffled accounts across the year.
  Every group is rejected and redrawn if it would run past 2025-12-31.

## Record counts (default arguments, seed 42)
Customer 500, Account 800, Merchant 60, Transaction 20,000, Fraud_Alert 0, Investigation 0.

| Scenario | Rows |
|---|---|
| normal | 18,400 |
| legit_edge | 1,000 (5%) |
| fraud | 600 (3%) |

| Fraud pattern | Rows | Look-alike | Rows |
|---|---|---|---|
| high_amount | 108 | large_planned_purchase | 180 |
| velocity_burst | 102 | festival_burst | 170 |
| odd_hour | 90 | night_shift | 150 |
| fan_out | 90 | business_payouts | 150 |
| merchant_anomaly | 72 | new_merchant_trial | 120 |
| card_testing | 72 | small_recurring_payments | 120 |
| device_geo_change | 66 | travel_purchase | 110 |

Categories: P2P_UPI 12,024 (60.1%), CNP_ECOM 7,976. Statuses: SUCCESS 17,985, FAILED 1,001,
PENDING 609, REVERSED 405.

## Leakage measurements (seed 42; scratch script, not part of the project)
- **FAILED rate** (insufficient funds is the only label-linked cause): fraud 4.0%, legit
  5.0%, legit_edge 5.3%. A small difference remains (by pattern it ranges 0-9%); it is not
  zero, so do not treat status as clean.
- **Best single rule (F1):** 4+ rows by one sender within 30 minutes: precision 0.44, recall
  0.42. Amount >= 50,000: precision 0.33 (recall 0.22). Night hour: precision 0.24.
  Amount <= Rs 30: precision 0.05. Rounded amount >= Rs 1,000: precision 0.01.
- **Best two-feature rules:** "new location OR 6+ rows in 60 min" F1 0.48 (precision 0.43,
  recall 0.56). Highest-precision combos reach precision 1.0 but only at recall 0.095
  (six or more rapid rows from one sender that are all tiny): the card-testing signature
  is findable, as it should be in a real dataset. "3 small payments in 20 minutes" alone:
  precision 0.76, recall 0.10.
- **Closing vs opening balance** (account level, "has a fraud row"): closing < 0.5 x opening
  flags 67 accounts at precision 0.57 against a 0.24 base rate. **`Account.Balance` is a
  closing balance and `opening_balances.csv` is ledger bookkeeping; both contain post-event
  information. They must be excluded from future ML features.** The same applies to
  `Transaction.Status` as a feature for fraud, and to labels.csv itself.

## Offline validator (`validate_data.py`, 74 checks for seed 42)
Exact row counts and exact scenario/pattern counts (only a manifest-declared shortfall on
tiny runs is allowed), 1:1 labels, ledger replay, formats, adults, window, plus pattern
behaviour (velocity window, night hours, distinct fan-out recipients, Current-account
payouts, card-testing escalation, device/location change, high-risk merchants), and SQL
envelope checks (guard, read-only step, START TRANSACTION, COMMIT, no destructive
statements, FK insert order). It also checks that `validate_seed_data.sql` carries this
dataset's exact totals. Simple-rule precision is reported and must stay below 0.90.

## Guard design
`seed_data.sql` runs a helper procedure `sp_seed_guard` that SIGNALs (error 1644) unless the
six data tables are empty and the four master rows exist. Before the helper runs the script
sets `transaction_read_only = 1`; only the helper's success path sets it back to 0. So a
refused session cannot insert anything, even with `mysql --force`. Then one `START
TRANSACTION`, all inserts, one `COMMIT`. The script also turns on `STRICT_ALL_TABLES` for the
load and restores the old `sql_mode` afterwards. A refused run leaves the empty helper
behind (it cannot be dropped in a read-only session); the next run removes it first.
**In Workbench, after a refused or failed run use Query > Reconnect to Server before doing
anything else** (the session stays read-only or inside an open transaction).

## Reproduce
From the project root (Python 3):
```
python data_generation/generate_data.py --force   # regenerates seed_data.sql, validate_seed_data.sql and output/
python data_generation/validate_data.py           # expect 74/74 checks passed
```
Try other settings without touching the project files:
```
python data_generation/generate_data.py --seed 7 --customers 100 --accounts 150 --merchants 20 --transactions 2000 --sql-out %TEMP%/s.sql --out-dir %TEMP%/o --validate-sql-out %TEMP%/v.sql
python data_generation/validate_data.py --sql %TEMP%/s.sql --out-dir %TEMP%/o --validate-sql %TEMP%/v.sql
```

## Test results (disposable instance, 127.0.0.1:33070)
1. Default generation: all five files identical across Python 3.11, 3.12, 3.14 with
   `PYTHONHASHSEED` 0, 123 and 99999 (9 runs, one hash set, equal to the project files).
2. Offline validator: seed 42 74/74. Seeds 1-100 at default size: 100/100 validate (no minors, nothing outside 2025). 100 small runs (2-41 customers, 2-70 accounts, 1-9 merchants, 40-2,539 transactions): 100/100 validate. The first round of this loop found over-strict thresholds (device change share, small-run tolerances), which were corrected and rerun.
3. Fresh Phase 1 install then seed: no errors or warnings, 1.7 s. `validate_seed_data.sql`:
   55 rows, all PASS. `verification.sql` 92/92, `rollback_check` PASS, counts unchanged.
4. `mysql --force` on the populated database: 46 errors, all refused or read-only, counts and
   CHECKSUM TABLE unchanged. With one existing row in each of Customer, Merchant, Account,
   Transaction, Fraud_Alert, Investigation (each alone): 0 rows inserted every time.
5. Master IDs reversed with gaps (Current 40, Savings 77, CNP_ECOM 200, P2P_UPI 305), with
   `autocommit=0` and `sql_mode=''`: loaded, every row mapped to the right TypeName,
   validator all PASS. An invalid last row (missing sender account, or bad enum) in that
   same session mode: error, 0 rows. A load killed mid-transaction (1,046 uncommitted rows
   seen): 0 rows afterwards.
6. `validate_seed_data.sql` mutations all FAIL on the matching checks: one transaction only,
   500-row partial load, deleted rows, balance +0.01, a FAILED row flipped to SUCCESS,
   tab-only address, whitespace-only location, `TOK_ABC`, IP `192.0.2.999`, IP `192.0.2.0`,
   `https://shop.com/x.example`, an email with a real domain.
7. Offline validator mutations (with the manifest re-hashed) all exit 1: shuffled labels,
   9% of fraud relabelled normal, 9% of fraud rows deleted, guard CALL removed, whole guard
   removed, COMMIT replaced by ROLLBACK, read-only step removed, an added DELETE, card_testing
   and odd_hour labels moved to other rows.
8. Loading with cmd.exe `mysql < seed_data.sql` exit 0 (500 customers, 20,000 transactions);
   a second run refused with exit 1. Service MySQL80 Running and port 3306
   listening (checked only, never connected).

## Unresolved (held for the user's decision)
Phase 1 `schema.sql` line 263: the UPI blank check in the trigger has a gap. The generator
never emits blank strings, and `validate_seed_data.sql` rejects them, but the schema itself
is unchanged.

## What the user must do (MySQL Workbench)
Do this only after Phase 1 passes on your own database (see "What the user must do next"
in `docs/PHASE_TRACKER.md`: `verification.sql` failed = 0 and `rollback_check` PASS).
1. Connect to your server in Workbench. `Customer`, `Account`, `Merchant`,
   `Transaction`, `Fraud_Alert` and `Investigation` must all be empty.
2. File > Run SQL Script..., pick `database\seed_data.sql`, click Run. It takes a few seconds.
   If it stops with an error, use Query > Reconnect to Server, then report the message.
3. File > Open SQL Script..., open `database\validate_seed_data.sql`, click the lightning
   bolt. Every row should say PASS, including the last row, SUMMARY.
4. Report the SUMMARY row and the row counts (500 / 800 / 60 / 20,000).
To start over you must empty the tables yourself; the project scripts never delete data.
