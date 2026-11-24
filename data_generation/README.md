# data_generation

Creates synthetic seed data for the banking fraud database (Phase 2). Python standard
library only. Nothing here connects to a database. Full details, results and the
Workbench steps: `docs/PHASE2_DATA_GENERATION.md`.

| File | Purpose |
|---|---|
| `config.py` | Every count, rate, range and name pool |
| `generate_data.py` | Writes `database/seed_data.sql`, `database/validate_seed_data.sql` and the files in `output/` |
| `validate_data.py` | Checks the generated files offline; exits 1 on any failure |
| `output/labels.csv` | Ground truth: `TransactionID, IsFraud, Scenario, Pattern` |
| `output/opening_balances.csv` | `AccountNumber, OpeningBalance, ClosingBalance` |
| `output/manifest.json` | Counts and SHA-256 of each file (no timestamps) |

## Commands (run from the project root)

```
python data_generation/generate_data.py --force     # defaults: seed 42, 500/800/60/20000 (--force replaces the project files)
python data_generation/validate_data.py             # offline check, exit code 1 on failure
```

Try other settings without touching the project files (the seed 7 example validates):

```
python data_generation/generate_data.py --seed 7 --customers 100 --accounts 150 --merchants 20 --transactions 2000 --sql-out %TEMP%/s.sql --out-dir %TEMP%/o --validate-sql-out %TEMP%/v.sql
python data_generation/validate_data.py --sql %TEMP%/s.sql --out-dir %TEMP%/o --validate-sql %TEMP%/v.sql
```

Options: `--seed`, `--customers`, `--accounts` (at least `--customers`), `--merchants`,
`--transactions`, `--force` (overwrite existing output), plus `--sql-out`, `--out-dir` and
`--validate-sql-out` to write somewhere else. The same arguments always give byte-identical
files. Existing output is never replaced without `--force`. Set `PYTHONDONTWRITEBYTECODE=1`
to avoid creating `__pycache__`.

`database/validate_seed_data.sql` is generated with the seed (it holds this dataset's exact
counts, totals and fingerprints), so always regenerate both together.

## Why labels live in a CSV
The approved schema has no ground-truth column and `FraudPrediction` is reserved for
model output, so every transaction is loaded unscored (`NOT_SCORED`). The truth is kept
in `labels.csv` for later phases. No `Fraud_Alert` or `Investigation` rows are generated.

## Do not use as ML features
`Account.Balance` is a closing balance and `opening_balances.csv` is ledger bookkeeping; both
contain information from after the transactions. Exclude them (and `labels.csv` itself) from
future feature sets.
