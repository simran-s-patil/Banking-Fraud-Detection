# Deployment Verification Checklist — Phase 1 + Phase 2 on the Real Database

**Purpose:** a single checklist the user runs through in MySQL Workbench on
`localhost:3306` to self-verify Phase 1 and Phase 2, and reports the results
back. No agent connects to `localhost:3306`, requests credentials, or runs
SQL against it — every value below is either produced by the user's own
Workbench run or copied from the disposable instance (`127.0.0.1:33070`) as
the known-good baseline to compare against.

**Current status: PENDING.** As of 2026-11-23, the user has not reported a
result for any item below. Nothing here is confirmed on the real database.
Do not treat Phase 1/2 as done based on the disposable-instance numbers —
those only prove the *scripts* are correct, not that they've run on
`localhost:3306`.

---

## 1. Schema verification (Phase 1)

Run `database/verification.sql` after `schema.sql` → `master_data.sql` →
`upgrade_existing_schema.sql` → **Query > Reconnect to Server** (exact
playbook: `docs/DATABASE_DEPLOYMENT_GUIDE.md`).

| Check | Expected (disposable-instance baseline, re-confirmed live 2026-11-23) | Your real-DB result |
|---|---|---|
| `total_tests` | 92 | ☐ PENDING |
| `passed` | 92 | ☐ PENDING |
| `failed` | 0 | ☐ PENDING |
| `rollback_check` | `PASS: nothing persisted` | ☐ PENDING |

If `failed` is anything but 0, or `rollback_check` doesn't say `PASS`, stop
and report the exact failing row — don't proceed to step 3.

## 2. Master data verification (Phase 1)

After `master_data.sql`:

| Table | Expected rows | Your result |
|---|---|---|
| `AccountType` | 2 (`Savings`, `Current`) | ☐ PENDING |
| `TransactionType` | 2 (`P2P_UPI`, `CNP_ECOM`) | ☐ PENDING |

(`upgrade_existing_schema.sql`'s own output should read `"Schema already
current: nothing changed."` on a fresh install — if it reports changes
instead, that's informational, not a failure, but worth mentioning.)

## 3. Synthetic data row counts (Phase 2)

After `database/seed_data.sql` (expect it to complete in 2–4 seconds):

| Table | Expected (seed 42, `manifest.json`) | Your result |
|---|---|---|
| `Customer` | 500 | ☐ PENDING |
| `Account` | 800 | ☐ PENDING |
| `Merchant` | 60 | ☐ PENDING |
| `Transaction` | 20,000 | ☐ PENDING |
| `Fraud_Alert` | 0 (by design — see `data_generation/README.md`) | ☐ PENDING |
| `Investigation` | 0 (by design) | ☐ PENDING |

Re-running `seed_data.sql` a second time on a non-empty database must be
**refused** with `ERROR 1644 (45000): Seed refused: a target table already
has rows. Nothing was changed.` — this is a guard working correctly, not a
bug. Don't try to force past it.

## 4. All 55 seed validation checks (Phase 2)

Run `database/validate_seed_data.sql`. Every one of the 55 result rows
(`seq` 1–96, plus the `seq=999` summary) must say `PASS` with `bad_rows = 0`.
This was re-confirmed live on the disposable instance on 2026-11-23 (55/55
PASS, exact CRC32 fingerprints matched) after rebuilding it from a clean
state — see `docs/PHASE_TRACKER.md`'s verification addendum for the full
trace of why that re-check mattered.

| | Expected | Your result |
|---|---|---|
| Rows reporting `PASS` | 55 / 55 | ☐ PENDING |
| `seq=999` summary (`checks failed`) | 0 | ☐ PENDING |

If anything fails, copy the exact `seq`, `check_name`, and `bad_rows` value
from the failing row(s) — that's precise enough to diagnose without needing
direct access to your database.

## 5. Consistency between the deployed MySQL dataset and the CSV/feature dataset used for Phase 3

Phase 3 (`ml/`) trained on data extracted from the **disposable instance**
(`127.0.0.1:33070`), cached at `ml/data/raw_features.csv`. That instance was
seeded from the exact same generator run (seed 42) as your real database
will be — same `database/seed_data.sql`, same `manifest.json` SHA-256
hashes. The check that proves your real database ends up holding the
*identical* dataset (not just the same row counts) is already built into
step 4: `validate_seed_data.sql` checks 1–4 and 100–111 compare exact CRC32
content fingerprints and amount totals, not just counts.

| | Expected | Your result |
|---|---|---|
| Checks 1–4 (`exact: ... content fingerprint`) | PASS | ☐ PENDING |
| Checks 100–111 (`exact: ... count and amount total`) | PASS | ☐ PENDING |

**If all of step 4 passes, step 5 is automatically satisfied** — there is no
separate file-comparison step needed; the fingerprint checks are the
consistency proof. If you want an extra, independent confirmation after
Phase 1/2 are signed off, the safe re-run procedure in `ml/README.md`
("Re-running against the real database") re-extracts from the real DB and
reports its own row counts/fraud rate for a second visual comparison against
this checklist's numbers — but it isn't required to close out steps 1–4.

---

## What to send back

For each of the 5 sections, either "PASS, matches the expected values" or
the exact failing row(s). Once all 5 are confirmed, Phase 1 and Phase 2 can
be marked DONE on the real database in `docs/PHASE_TRACKER.md`, and the
Phase 3 re-run procedure in `ml/README.md` can be used if you want the
models retrained on the real-database data specifically.
