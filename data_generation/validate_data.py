#!/usr/bin/env python3
"""Offline validator for the generated Phase 2 files. Never connects to a database.

Reads database/seed_data.sql plus labels.csv, opening_balances.csv, manifest.json and
validate_seed_data.sql, prints PASS/FAIL per check, and exits non-zero if anything fails.
It checks the data itself (counts, ledger, formats), the labels against the behaviour each
pattern should show, and the structure of the SQL script (guard, read-only step, one
transaction, no destructive statements).
"""
import argparse
import collections
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import config as C
from generate_data import (allocate, expected_checks, money, ts_str,
                           DEFAULT_OUT, DEFAULT_SQL, DEFAULT_VALIDATE_SQL)

RESULTS = []
SHARE = 0.9          # behaviour checks: at least this share of rows or clusters must behave
ROW_MIN = 30         # row-share checks need this many rows (the last group of a pattern is trimmed)
MIN_ROWS = 5         # share-based checks are skipped for patterns with fewer rows than this


def check(name, ok, detail=""):
    RESULTS.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


# ---------------------------------------------------------------- parsing
class Raw(str):
    """An unquoted SQL token such as 12.50 or @tt_p2p."""


def parse_row(line):
    body = line[1:line.rindex(")")]
    vals, i, n = [], 0, len(body)
    while i < n:
        if body[i] == "'":
            j, buf = i + 1, []
            while True:
                if body[j] == "'":
                    if j + 1 < n and body[j + 1] == "'":
                        buf.append("'")
                        j += 2
                        continue
                    break
                buf.append(body[j])
                j += 1
            vals.append("".join(buf))
            i = j + 1
        else:
            j = body.find(",", i)
            j = n if j < 0 else j
            tok = body[i:j].strip()
            vals.append(None if tok == "NULL" else Raw(tok))
            i = j
        while i < n and body[i] in ", ":
            i += 1
    return vals


def load_tables(path):
    tables, cols, cur = {}, {}, None
    sizes = [0]
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            m = re.match(r"INSERT INTO `?(\w+)`? \((.*)\) VALUES$", line)
            if m:
                cur = m.group(1)
                sizes.append(0)
                cols[cur] = [c.strip() for c in m.group(2).split(",")]
                tables.setdefault(cur, [])
            elif line.startswith("(") and cur:
                tables[cur].append(dict(zip(cols[cur], parse_row(line))))
                sizes[-1] += 1
            elif line.strip() and not line.startswith("--"):
                cur = None if line.startswith(("COMMIT", "START", "SET", "USE", "CALL", "DROP", "CREATE")) else cur
    tables["_max_batch"] = max(sizes)
    return tables


def cents(text):
    whole, _, frac = str(text).partition(".")
    return int(whole) * 100 + int((frac + "00")[:2])


def when(text):
    return datetime.fromisoformat(text)


def sha_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def clusters(rows, gap_minutes):
    """Split time-sorted rows (each with .ts) into runs where neighbours are within the gap."""
    out, cur = [], []
    for r in sorted(rows, key=lambda r: (r.ts, r.id)):
        if cur and r.ts - cur[-1].ts > timedelta(minutes=gap_minutes):
            out.append(cur)
            cur = []
        cur.append(r)
    if cur:
        out.append(cur)
    return out


def share_ok(name, good, total, detail="", min_total=MIN_ROWS):
    """PASS when at least SHARE of the items behave. Skipped (INFO) when there are too few."""
    if total < min_total:
        print(f"INFO  {name}: skipped, only {total} rows")
    else:
        # the last group of a pattern is trimmed to hit the exact quota, so one miss is allowed
        check(name, good / total >= SHARE or (total <= 20 and good >= total - 1), f"{good}/{total} {detail}".strip())


# ---------------------------------------------------------------- envelope of the SQL script
FORBIDDEN = re.compile(r"\b(DROP\s+(TABLE|DATABASE|SCHEMA|VIEW|TRIGGER|INDEX)|TRUNCATE|DELETE|REPLACE|INSERT\s+IGNORE|"
                       r"ON\s+DUPLICATE|ALTER|UPDATE|ROLLBACK|GRANT|REVOKE)\b", re.I)


def check_envelope(text):
    lines = text.split("\n")
    code = [l for l in lines if not l.startswith(("--", "(")) and l.strip()]
    codetext = "\n".join(code)

    def pos(s, last=False):
        return text.rindex(s) if last else text.find(s)

    p_use, p_proc, p_ro, p_call = pos("USE banking_fraud_detection;"), pos("CREATE PROCEDURE sp_seed_guard()"), \
        pos("SET SESSION transaction_read_only = 1;"), pos("CALL sp_seed_guard();")
    p_start, p_commit = pos("START TRANSACTION;"), pos("COMMIT;", True)
    p_first = pos("INSERT INTO Customer")
    check("SQL: USE, guard helper, read-only step, CALL, START TRANSACTION, inserts, COMMIT in that order",
          0 <= p_use < p_proc < p_ro < p_call < p_start < p_first < p_commit)
    body = text[p_proc:text.find("END$$", p_proc)] if p_proc >= 0 else ""
    tables = ("Customer", "Account", "Merchant", "`Transaction`", "Fraud_Alert", "Investigation")
    check("SQL: guard checks all six tables, signals twice, and only then clears read-only",
          all(f"EXISTS (SELECT 1 FROM {t})" in body for t in tables) and body.count("SIGNAL SQLSTATE") == 2
          and body.rfind("SIGNAL SQLSTATE") < body.find("SET SESSION transaction_read_only = 0;")
          and all(n in body for n in ("'Savings'", "'Current'", "'P2P_UPI'", "'CNP_ECOM'")))
    check("SQL: guard helper dropped after the CALL", "DROP PROCEDURE sp_seed_guard;" in text
          and text.index("DROP PROCEDURE sp_seed_guard;") > p_call)
    check("SQL: exactly one START TRANSACTION and one COMMIT, no ROLLBACK",
          codetext.count("START TRANSACTION;") == 1 and "ROLLBACK" not in codetext
          and codetext[codetext.find("CALL sp_seed_guard();"):].count("COMMIT;") == 1)
    drops = re.findall(r"DROP\s+\w+[^;]*;", codetext, re.I)
    check("SQL: only DROP PROCEDURE [IF EXISTS] sp_seed_guard",
          all(re.fullmatch(r"DROP PROCEDURE (IF EXISTS )?sp_seed_guard;", d) for d in drops))
    bad = [m.group(0) for m in FORBIDDEN.finditer(re.sub(r"DROP PROCEDURE (IF EXISTS )?sp_seed_guard;", "", codetext))]
    check("SQL: no destructive or modifying statements outside INSERT", not bad, ", ".join(bad[:3]))
    order = [m.group(1) for m in re.finditer(r"^INSERT INTO `?(\w+)`? \(", text, re.M)]
    firsts = [order[0]] + [order[i] for i in range(1, len(order)) if order[i] != order[i - 1]]
    check("SQL: inserts in FK order Customer, Merchant, Account, Transaction", firsts == ["Customer", "Merchant", "Account", "Transaction"])
    check("SQL: master rows looked up by TypeName, never hard-coded",
          all(f"SET @{v} = (SELECT" in text for v in ("at_savings", "at_current", "tt_p2p", "tt_cnp"))
          and "'STRICT_ALL_TABLES'" in text and text.rstrip().endswith("SET SESSION sql_mode = @old_sql_mode;")
          and text.index("STRICT_ALL_TABLES") < p_start)


# ---------------------------------------------------------------- checks
def main():
    p = argparse.ArgumentParser(description="Validate generated seed files offline.")
    p.add_argument("--sql", default=DEFAULT_SQL)
    p.add_argument("--out-dir", default=DEFAULT_OUT)
    p.add_argument("--validate-sql", default=DEFAULT_VALIDATE_SQL)
    args = p.parse_args()
    files = {"seed_data.sql": args.sql,
             "labels.csv": os.path.join(args.out_dir, "labels.csv"),
             "opening_balances.csv": os.path.join(args.out_dir, "opening_balances.csv"),
             "validate_seed_data.sql": args.validate_sql}
    manifest_path = os.path.join(args.out_dir, "manifest.json")
    missing = [x for x in list(files.values()) + [manifest_path] if not os.path.exists(x)]
    if missing:
        print("FAIL  files exist  [missing: " + ", ".join(missing) + "]")
        return 1
    with open(manifest_path, encoding="utf-8") as f:
        man = json.load(f)
    check("file checksums match manifest", all(sha_file(files[k]) == man["sha256"].get(k) for k in files))

    with open(args.sql, encoding="utf-8") as f:
        sql_text = f.read()
    check_envelope(sql_text)
    t = load_tables(args.sql)
    cust, acct, merch, txn = (t.get(k, []) for k in ("Customer", "Account", "Merchant", "Transaction"))
    T = len(txn)

    # ---- row counts (exact, against the arguments recorded in the manifest)
    a = man["arguments"]
    check("row counts equal the requested arguments",
          (len(cust), len(acct), len(merch), T) == (a["customers"], a["accounts"], a["merchants"], a["transactions"]),
          f"{len(cust)}/{len(acct)}/{len(merch)}/{T}")
    check("every customer has an account (accounts >= customers)", len(acct) >= len(cust))
    check("transaction IDs are 1..N with no gaps", [int(x["TransactionID"]) for x in txn] == list(range(1, T + 1)))
    check("insert batches are at most 500 rows", t["_max_batch"] <= C.BATCH_SIZE, f"max {t['_max_batch']}")

    # ---- customers
    check("customer emails unique, name@example.com, lowercase",
          len({c["Email"] for c in cust}) == len(cust)
          and all(re.fullmatch(r"[a-z0-9.]+@example\.com", c["Email"]) for c in cust))
    check("customer phones unique and 00000 plus 8 digits",
          len({c["Phone"] for c in cust}) == len(cust) and all(re.fullmatch(r"00000[0-9]{8}", c["Phone"]) for c in cust))
    cmap = {int(c["CustomerID"]): c for c in cust}

    def adult(c):
        dob, on = datetime.fromisoformat(c["DateOfBirth"]).date(), when(c["CreatedAt"]).date()
        return (on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))) >= 18
    minors = sum(1 for c in cust if not adult(c))
    check("customers are adults when created", minors == 0, f"{minors} minors")
    blank = sum(1 for rows in (cust, merch, txn) for r in rows for v in r.values()
                if isinstance(v, str) and not isinstance(v, Raw) and v.strip() == "")
    check("no blank strings anywhere", blank == 0, f"{blank} blank")

    # ---- accounts
    amap = {int(x["AccountNumber"]): x for x in acct}
    check("account numbers unique, start at 100000000001", len(amap) == len(acct) and min(amap) == C.FIRST_ACCOUNT_NUMBER)
    check("every account has an existing customer, created no earlier than the customer",
          all(int(x["CustomerID"]) in cmap and when(x["CreatedAt"]) >= when(cmap[int(x["CustomerID"])]["CreatedAt"])
              for x in acct))
    check("account balances non-negative", all(cents(x["Balance"]) >= 0 for x in acct))
    check("account status values valid",
          all(x["AccountStatus"] in ("ACTIVE", "DORMANT", "FROZEN", "CLOSED") for x in acct))
    mids = {int(m["MerchantID"]) for m in merch}
    mcat = {int(m["MerchantID"]): m["Category"] for m in merch}
    check("merchant websites are https://www.<name>.example or NULL",
          all(m["Website"] is None or re.fullmatch(r"https://www\.[a-z0-9]+\.example", m["Website"]) for m in merch))

    # ---- transactions: category rules and formats
    p2p = [x for x in txn if str(x["TransactionTypeID"]) == "@tt_p2p"]
    cnp = [x for x in txn if str(x["TransactionTypeID"]) == "@tt_cnp"]
    check("every row is P2P_UPI or CNP_ECOM", len(p2p) + len(cnp) == T)
    check("P2P rows: receiver account or UPI; no merchant, token, device, IP, location",
          all((x["ReceiverAccountNumber"] or x["ReceiverUPIID"]) and x["MerchantID"] is None
              and x["CardReferenceToken"] is None and x["DeviceID"] is None and x["IPAddress"] is None
              and x["Location"] is None for x in p2p))
    check("P2P_UPI receiver mix covers account only, account + UPI, UPI only",
          len({(x["ReceiverAccountNumber"] is not None, x["ReceiverUPIID"] is not None) for x in p2p}) == 3
          or T < 200)
    check("CNP rows: no receiver account or UPI", all(x["ReceiverAccountNumber"] is None and x["ReceiverUPIID"] is None for x in cnp))
    with_m = sum(1 for x in cnp if x["MerchantID"] is not None)
    check("CNP merchant present for about 98%", len(cnp) - with_m <= max(2, 0.05 * len(cnp)), f"{with_m}/{len(cnp)}")
    check("CNP merchants exist", all(x["MerchantID"] is None or int(x["MerchantID"]) in mids for x in cnp))
    ip_re = re.compile(r"(192\.0\.2|198\.51\.100|203\.0\.113)\.([1-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-4])")
    check("tokens are tok_<lowercase letters> (no card-like digits)",
          all(x["CardReferenceToken"] is None or re.fullmatch(r"tok_[a-z]+", x["CardReferenceToken"]) for x in txn))
    check("device IDs are dev_<hex>", all(x["DeviceID"] is None or re.fullmatch(r"dev_[0-9a-f]+", x["DeviceID"]) for x in txn))
    check("IPs only in RFC 5737 ranges with last octet 1-254",
          all(x["IPAddress"] is None or ip_re.fullmatch(x["IPAddress"]) for x in txn))
    check("UPI IDs are <name>@synthupi",
          all(x["ReceiverUPIID"] is None or re.fullmatch(r"[a-z0-9]+@" + C.UPI_DOMAIN, x["ReceiverUPIID"]) for x in txn))
    check("amounts positive", all(cents(x["Amount"]) > 0 for x in txn))
    check("statuses valid", all(x["Status"] in ("PENDING", "SUCCESS", "FAILED", "REVERSED") for x in txn))
    check("all rows unscored", all(x["FraudScore"] is None and x["FraudPrediction"] is None
                                   and x["RiskStatus"] == "NOT_SCORED" for x in txn))
    check("sender is not receiver, both exist",
          all(int(x["SenderAccountNumber"]) in amap and x["SenderAccountNumber"] != x["ReceiverAccountNumber"]
              and (x["ReceiverAccountNumber"] is None or int(x["ReceiverAccountNumber"]) in amap) for x in txn))
    lo = datetime.combine(C.WINDOW_START, datetime.min.time())
    hi = datetime.combine(C.WINDOW_END + timedelta(days=1), datetime.min.time())
    outside = sum(1 for x in txn if not lo <= when(x["TransactionTimestamp"]) < hi)
    check("timestamps inside the 2025 window", outside == 0, f"{outside} outside")
    check("rows are in time order", all(txn[i]["TransactionTimestamp"] <= txn[i + 1]["TransactionTimestamp"] for i in range(T - 1)))
    check("CreatedAt is not before TransactionTimestamp",
          all(when(x["CreatedAt"]) >= when(x["TransactionTimestamp"]) for x in txn))
    check("only ACTIVE accounts transact, only after they were created",
          all(amap[int(x["SenderAccountNumber"])]["AccountStatus"] == "ACTIVE"
              and when(amap[int(x["SenderAccountNumber"])]["CreatedAt"]) < when(x["TransactionTimestamp"])
              and (x["ReceiverAccountNumber"] is None
                   or (amap[int(x["ReceiverAccountNumber"])]["AccountStatus"] == "ACTIVE"
                       and when(amap[int(x["ReceiverAccountNumber"])]["CreatedAt"]) < when(x["TransactionTimestamp"])))
              for x in txn))
    shares = len(p2p) / T if T else 0
    tol = max(C.P2P_SHARE_TOLERANCE, 3 * (C.P2P_SHARE * (1 - C.P2P_SHARE) / max(T, 1)) ** 0.5)   # wider for small runs
    check("P2P share near target", abs(shares - C.P2P_SHARE) <= tol, f"{shares:.3f}")

    # ---- labels 1:1
    with open(files["labels.csv"], newline="", encoding="utf-8") as f:
        labels = list(csv.DictReader(f))
    ids = [int(r["TransactionID"]) for r in labels]
    one_to_one = sorted(ids) == list(range(1, T + 1)) and len(set(ids)) == len(ids)
    check("labels are 1:1 with transactions", one_to_one)
    if not one_to_one or [int(x["TransactionID"]) for x in txn] != list(range(1, T + 1)):
        print("Stopping: labels and transactions do not line up, so the remaining checks are skipped.")
        return 1
    lab = {int(r["TransactionID"]): r for r in labels}
    check("IsFraud matches Scenario", all((r["IsFraud"] == "1") == (r["Scenario"] == "fraud") for r in labels))
    check("pattern names valid for their scenario",
          all((r["Scenario"] == "normal" and r["Pattern"] == "normal")
              or (r["Scenario"] == "fraud" and r["Pattern"] in C.FRAUD_PATTERNS)
              or (r["Scenario"] == "legit_edge" and r["Pattern"] in C.EDGE_PATTERNS) for r in labels))

    # ---- exact scenario and pattern counts (a manifest shortfall is the only allowed slack)
    slack = man.get("pattern_shortfall", 0)
    n_fraud, n_edge = round(T * C.FRAUD_RATE), round(T * C.EDGE_RATE)
    got = {s: sum(1 for r in labels if r["Scenario"] == s) for s in ("fraud", "legit_edge")}
    check("fraud and legit_edge counts equal the configured rates (rounded)",
          n_fraud + n_edge - slack <= got["fraud"] + got["legit_edge"] <= n_fraud + n_edge
          and got["fraud"] <= n_fraud and got["legit_edge"] <= n_edge,
          f"fraud {got['fraud']} (want {n_fraud}), edge {got['legit_edge']} (want {n_edge}), slack {slack}")
    check("a shortfall is only accepted for tiny runs", slack == 0 or T < 1000, f"shortfall {slack}")
    bad, deficit = [], 0
    for idx, total in ((0, n_fraud), (1, n_edge)):
        want = allocate(total, {pp[idx]: pp[2] for pp in C.PATTERN_PAIRS})
        for pat, w in want.items():
            have = sum(1 for r in labels if r["Pattern"] == pat)
            deficit += w - have
            if have > w:
                bad.append(f"{pat}:{have}/{w}")
    check("pattern counts equal the configured allocation", not bad and 0 <= deficit <= slack, ", ".join(bad) + f" deficit {deficit}")

    # ---- per-row view used by the behaviour checks
    R = {}
    for x in txn:
        i = int(x["TransactionID"])
        R[i] = SimpleNamespace(
            id=i, ts=when(x["TransactionTimestamp"]), cents=cents(x["Amount"]), sender=int(x["SenderAccountNumber"]),
            recv=None if x["ReceiverAccountNumber"] is None else int(x["ReceiverAccountNumber"]), upi=x["ReceiverUPIID"],
            merchant=None if x["MerchantID"] is None else int(x["MerchantID"]), device=x["DeviceID"], ip=x["IPAddress"],
            loc=x["Location"], token=x["CardReferenceToken"], cat="P2P" if str(x["TransactionTypeID"]) == "@tt_p2p" else "CNP",
            pat=lab[i]["Pattern"], scen=lab[i]["Scenario"], status=x["Status"])
    by_pat = collections.defaultdict(list)
    for r in R.values():
        by_pat[r.pat].append(r)
    normal_by_sender = collections.defaultdict(list)
    for r in by_pat["normal"]:
        normal_by_sender[r.sender].append(r)
    active_current = any(x["AccountTypeID"] == "@at_current" and x["AccountStatus"] == "ACTIVE" for x in acct)

    # ---- pattern behaviour: the labels must describe what the rows actually do
    fraud_ids = [i for i, r in lab.items() if r["IsFraud"] == "1"]
    cnp_only = ("velocity_burst", "card_testing", "merchant_anomaly", "device_geo_change", "festival_burst",
                "new_merchant_trial", "small_recurring_payments", "travel_purchase")
    check("pattern category: burst/card/merchant/device patterns are CNP, fan-out/payouts are P2P",
          all(r.cat == "CNP" for pt in cnp_only for r in by_pat[pt])
          and all(r.cat == "P2P" for pt in ("fan_out", "business_payouts") for r in by_pat[pt]))
    check("odd_hour and night_shift rows are all inside the night hours",
          all(r.ts.hour in C.NIGHT_HOURS for pt in ("odd_hour", "night_shift") for r in by_pat[pt]))
    check("high_amount and large_planned_purchase rows are large (>= Rs 15,000)",
          all(r.cents >= 1500000 for pt in ("high_amount", "large_planned_purchase") for r in by_pat[pt]))
    for pt, mins in (("velocity_burst", 10), ("festival_burst", 30)):
        hit = 0
        for sender in sorted({r.sender for r in by_pat[pt]}):
            rows = sorted((r for r in by_pat[pt] if r.sender == sender), key=lambda r: r.ts)
            inside = set()
            for n in range(len(rows) - 3):
                if rows[n + 3].ts - rows[n].ts <= timedelta(minutes=mins):
                    inside.update(r.id for r in rows[n:n + 4])
            hit += len(inside)
        share_ok(f"{pt}: rows sit in a window of 4+ same-sender rows within {mins} minutes", hit, len(by_pat[pt]), min_total=ROW_MIN)
    for pt in ("fan_out", "business_payouts"):
        groups = []
        for s in sorted({r.sender for r in by_pat[pt]}):
            groups += clusters([r for r in by_pat[pt] if r.sender == s], 60)
        distinct = sum(1 for g in groups if len({(r.recv if r.recv is not None else r.upi) for r in g}) == len(g))
        share_ok(f"{pt}: every row of a run goes to a different recipient", distinct, len(groups))
        big = sum(1 for g in groups if len(g) >= 6)
        share_ok(f"{pt}: runs reach 6 or more recipients", big, len(groups))
    check("business_payouts come from Current accounts",
          not active_current or all(amap[r.sender]["AccountTypeID"] == "@at_current" for r in by_pat["business_payouts"]))
    groups = []
    for s in sorted({r.sender for r in by_pat["card_testing"]}):
        groups += [g for g in clusters([r for r in by_pat["card_testing"] if r.sender == s], 60) if len(g) >= 2]
    ok = sum(1 for g in groups if all(r.cents <= 3000 for r in g[:-1]) and g[-1].cents > max(r.cents for r in g[:-1])
             and g[-1].cents >= 50000)
    share_ok("card_testing: small probes (<= Rs 30) then one larger final charge", ok, len(groups))
    for pt in ("device_geo_change", "travel_purchase"):
        rows = [r for r in by_pat[pt] if r.sender in normal_by_sender and r.loc]
        homes = {s: {n.loc for n in rs if n.loc} for s, rs in normal_by_sender.items()}
        share_ok(f"{pt}: location differs from the sender's usual location",
                 sum(1 for r in rows if r.loc not in homes[r.sender]), len(rows), min_total=ROW_MIN)
        rows = [r for r in by_pat[pt] if r.sender in normal_by_sender and r.ip]
        ips = {s: {n.ip for n in rs if n.ip} for s, rs in normal_by_sender.items()}
        share_ok(f"{pt}: IP differs from the sender's usual IPs", sum(1 for r in rows if r.ip not in ips[r.sender]), len(rows), min_total=ROW_MIN)
    rows = [r for r in by_pat["device_geo_change"] if r.sender in normal_by_sender and r.device]
    devs = {s: {n.device for n in rs if n.device} for s, rs in normal_by_sender.items()}
    new_dev = sum(1 for r in rows if r.device not in devs[r.sender])
    if len(rows) >= ROW_MIN:
        check("device_geo_change: at least 30% of the rows use a device the sender never used", new_dev / len(rows) >= 0.3, f"{new_dev}/{len(rows)}")
    rows = [r for r in by_pat["merchant_anomaly"] if r.merchant is not None]
    risky = [m for m, c in mcat.items() if c in C.HIGH_RISK_CATEGORIES]
    if risky:
        share_ok("merchant_anomaly: merchant is in a high-risk category", sum(1 for r in rows if mcat[r.merchant] in C.HIGH_RISK_CATEGORIES), len(rows), min_total=ROW_MIN)
    seen = {s: {n.merchant for n in rs} for s, rs in normal_by_sender.items()}
    rows = [r for r in rows if r.sender in normal_by_sender]
    share_ok("merchant_anomaly: merchant is new to the sender", sum(1 for r in rows if r.merchant not in seen[r.sender]), len(rows), min_total=ROW_MIN)
    n_active = sum(1 for x in acct if x["AccountStatus"] == "ACTIVE")
    check("fraud spread over many accounts", len({R[i].sender for i in fraud_ids}) >= min(n_active, max(1, len(fraud_ids) // 12)),
          f"{len({R[i].sender for i in fraud_ids})} accounts")
    months = {R[i].ts.strftime("%Y-%m") for i in fraud_ids}
    check("fraud spread through the year", len(months) >= min(12, max(1, len(fraud_ids) // 20)), f"{len(months)} months")

    # ---- ledger reconciliation
    with open(files["opening_balances.csv"], newline="", encoding="utf-8") as f:
        ob = {int(r["AccountNumber"]): (cents(r["OpeningBalance"]), cents(r["ClosingBalance"])) for r in csv.DictReader(f)}
    check("opening_balances.csv covers every account", set(ob) == set(amap))
    run = {n: v[0] for n, v in ob.items()}
    negative = 0
    for r in sorted(R.values(), key=lambda r: r.id):
        if r.status != "SUCCESS":
            continue
        run[r.sender] -= r.cents
        negative += run[r.sender] < 0
        if r.recv is not None:
            run[r.recv] += r.cents
    check("ledger never goes negative", negative == 0, f"{negative} overdrafts")
    check("ledger replay equals Account.Balance and closing balance",
          all(run[n] == cents(amap[n]["Balance"]) == ob[n][1] for n in amap))

    # ---- status must not leak the label
    def fail_rate(ids_):
        return sum(1 for i in ids_ if R[i].status == "FAILED") / max(1, len(ids_))
    legit_ids = [i for i, r in lab.items() if r["IsFraud"] == "0"]
    print(f"INFO  FAILED share: fraud {fail_rate(fraud_ids):.3f} vs legit {fail_rate(legit_ids):.3f}")
    if len(fraud_ids) >= C.STATUS_GAP_MIN_ROWS:
        gaps = []
        for st in ("PENDING", "SUCCESS", "FAILED", "REVERSED"):
            fa = sum(1 for i in fraud_ids if R[i].status == st) / len(fraud_ids)
            lg = sum(1 for i in legit_ids if R[i].status == st) / len(legit_ids)
            gaps.append(abs(fa - lg))
        check("status shares similar for fraud and legit", max(gaps) <= C.STATUS_GAP_TOLERANCE, f"max gap {max(gaps):.3f}")

    # ---- simple rules must not identify fraud
    is_fraud = {i: lab[i]["IsFraud"] == "1" for i in lab}
    rules = {f"amount >= {C.SIMPLE_HIGH_AMOUNT}": {i for i, r in R.items() if r.cents >= C.SIMPLE_HIGH_AMOUNT * 100},
             "night hour (00-05)": {i for i, r in R.items() if r.ts.hour in C.NIGHT_HOURS},
             "amount <= 30 (card-testing probe)": {i for i, r in R.items() if r.cents <= 3000}}
    burst, by_sender = set(), collections.defaultdict(list)
    for r in R.values():
        by_sender[r.sender].append((r.ts, r.id))
    k, win = C.SIMPLE_BURST_COUNT, timedelta(minutes=C.SIMPLE_BURST_MINUTES)
    for rows in by_sender.values():
        rows.sort()
        for s in range(len(rows) - k + 1):
            if rows[s + k - 1][0] - rows[s][0] <= win:
                burst.update(i for _, i in rows[s:s + k])
    rules[f"burst ({k}+ txns in {C.SIMPLE_BURST_MINUTES} min)"] = burst
    rules["any of the four"] = set().union(*rules.values())
    total_fraud = max(1, len(fraud_ids))
    worst = 0.0
    for name, flagged in rules.items():
        tp = sum(1 for i in flagged if is_fraud[i])
        prec = tp / len(flagged) if flagged else 0.0
        worst = max(worst, prec)
        print(f"INFO  rule '{name}': flagged {len(flagged)}, precision {prec:.3f}, recall {tp / total_fraud:.3f}")
    if len(fraud_ids) >= C.STATUS_GAP_MIN_ROWS:
        check("no simple rule reaches the precision limit", worst < C.SIMPLE_RULE_MAX_PRECISION, f"worst {worst:.3f}")

    # ---- validate_seed_data.sql carries this dataset's exact expectations
    ns_c = [SimpleNamespace(id=int(c["CustomerID"]), email=c["Email"], phone=c["Phone"]) for c in cust]
    ns_a = [SimpleNamespace(number=int(x["AccountNumber"]), cust=SimpleNamespace(id=int(x["CustomerID"])),
                            balance=cents(x["Balance"]), status=x["AccountStatus"], created=when(x["CreatedAt"])) for x in acct]
    ns_m = [SimpleNamespace(id=int(m["MerchantID"]), name=m["MerchantName"]) for m in merch]
    by_num = {a_.number: n for n, a_ in enumerate(ns_a)}
    ns_e = [dict(id=r.id, ts=r.ts, cents=r.cents, status=r.status, sender=SimpleNamespace(number=r.sender),
                 recv=None if r.recv is None else by_num[r.recv], cat=r.cat) for r in sorted(R.values(), key=lambda r: r.id)]
    with open(files["validate_seed_data.sql"], encoding="utf-8") as f:
        vtext = f.read()
    wanted = expected_checks(ns_c, ns_a, ns_m, ns_e)
    check("validate_seed_data.sql holds this dataset's exact counts, balances, statuses and fingerprints",
          all(f"UNION ALL SELECT {seq}, '{name}', {expr}" in vtext for seq, name, expr in wanted))
    check("validate_seed_data.sql is read-only (one SELECT, no data changes)",
          not re.search(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|REPLACE|CREATE)\b", re.sub(r"--[^\n]*", "", vtext), re.I))

    failed = RESULTS.count(False)
    print(f"\n{len(RESULTS) - failed}/{len(RESULTS)} checks passed" + ("" if not failed else f", {failed} FAILED"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
