#!/usr/bin/env python3
"""Generate synthetic seed data for the banking fraud database (Phase 2).

Never connects to a database. Writes four files:
  database/seed_data.sql                      SQL to load (see docs/PHASE2_DATA_GENERATION.md)
  data_generation/output/labels.csv           ground truth (the schema has no label column)
  data_generation/output/opening_balances.csv opening/closing balance per account
  data_generation/output/manifest.json        counts and file checksums

Same arguments always give byte-identical files: one random.Random(seed), a fixed
date window, and no current time anywhere.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import random
import string
import zlib
import sys
from datetime import datetime, time, timedelta
from itertools import accumulate
from types import SimpleNamespace

import config as C

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SQL = os.path.join(ROOT, "database", "seed_data.sql")
DEFAULT_OUT = os.path.join(ROOT, "data_generation", "output")
DEFAULT_VALIDATE_SQL = os.path.join(ROOT, "database", "validate_seed_data.sql")
LAST_MOMENT = datetime.combine(C.WINDOW_END + timedelta(days=1), time(0, 0))


# ---------------------------------------------------------------- small helpers
def money(cents):
    return f"{cents // 100}.{cents % 100:02d}"


def ts_str(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def q(value):
    """SQL string literal. Data is plain ASCII, so only quotes need escaping."""
    if value is None:
        return "NULL"
    if "\\" in value or not value.isascii():
        raise ValueError("unexpected character in generated string: " + value)
    return "'" + value.replace("'", "''") + "'"


def slug(text):
    return "".join(ch for ch in text.lower() if ch.isalnum())


def rand_day(rng, lo, hi):
    return lo + timedelta(days=rng.randint(0, (hi - lo).days))


def at(rng, day, hour):
    return datetime.combine(day, time(hour, rng.randrange(60), rng.randrange(60)))


def clip_cents(rupees):
    return max(100, min(C.AMOUNT_CAP * 100, int(round(rupees * 100))))


def allocate(total, weights):
    """Split total over names by weight (largest remainder). weights: dict."""
    s = sum(weights.values())
    raw = {n: total * w / s for n, w in weights.items()}
    out = {n: int(v) for n, v in raw.items()}
    left = total - sum(out.values())
    for n in sorted(raw, key=lambda n: (-(raw[n] - out[n]), n))[:left]:
        out[n] += 1
    return out


def new_device(rng):
    return "dev_%012x" % rng.getrandbits(48)


def new_ip(rng):
    return rng.choice(C.IP_PREFIXES) + str(rng.randint(1, 254))


def new_token(rng):
    return "tok_" + "".join(rng.choice(string.ascii_lowercase) for _ in range(16))


def new_ext_upi(rng):
    return f"{rng.choice(C.UPI_WORDS)}{rng.randint(100, 9999)}@{C.UPI_DOMAIN}"


def city_text(city):
    return f"{city[0]}, {city[1]}"


# ---------------------------------------------------------------- people and merchants
def build_customers(rng, n):
    rows = []
    for cid in range(1, n + 1):
        first, last = rng.choice(C.FIRST_NAMES), rng.choice(C.LAST_NAMES)
        dob = C.DOB_MIN + timedelta(days=rng.randrange((C.DOB_MAX - C.DOB_MIN).days + 1))
        lo, hi = C.CUSTOMER_EARLY_RANGE if rng.random() < C.CUSTOMER_EARLY_SHARE else C.CUSTOMER_LATE_RANGE
        created = datetime.combine(rand_day(rng, lo, hi), time(0, 0)) + timedelta(seconds=rng.randrange(86400))
        city = rng.choice(C.CITIES)
        rows.append(SimpleNamespace(
            id=cid, first=first, last=last, dob=dob, created=created,
            email=f"{slug(first)}.{slug(last)}{cid}@{C.EMAIL_DOMAIN}",
            phone=f"{C.PHONE_PREFIX}{(cid * 7919) % 10**8:08d}",
            address=f"{rng.randint(1, 200)} {rng.choice(C.STREETS)}, {city_text(city)}"))
    return rows


def build_accounts(rng, customers, n):
    statuses = [s for s, _ in C.ACCOUNT_STATUS_MIX]
    status_w = [w for _, w in C.ACCOUNT_STATUS_MIX]
    latest = datetime.combine(C.ACCOUNT_LATEST_OPEN, time(23, 59, 59))
    accts = []
    for i in range(n):
        cust = customers[i] if i < len(customers) else rng.choice(customers)
        delay = C.FIRST_ACCOUNT_DELAY_DAYS if i < len(customers) else C.EXTRA_ACCOUNT_DELAY_DAYS
        created = min(cust.created + timedelta(days=rng.randint(*delay), seconds=rng.randrange(86400)), latest)
        atype = "Current" if rng.random() < C.CURRENT_ACCOUNT_SHARE else "Savings"
        status = rng.choices(statuses, weights=status_w)[0]
        if i < 2:                       # tiny runs still need accounts that can transact
            status = "ACTIVE"
        opening = int(round(rng.lognormvariate(math.log(C.OPENING_BALANCE_MEDIAN[atype]), C.OPENING_BALANCE_SIGMA) * 100))
        accts.append(SimpleNamespace(
            idx=i, number=C.FIRST_ACCOUNT_NUMBER + i, cust=cust, type=atype, status=status,
            created=created, opening=opening, balance=opening,
            start_day=max(C.WINDOW_START, created.date() + timedelta(days=1))))
    return accts


def build_profiles(rng, accts, n_merchants):
    """Give every account habits: devices, IPs, card, city, contacts, favourite merchants."""
    active = [a for a in accts if a.status == "ACTIVE"]
    for a in accts:
        a.scale = C.TYPICAL_AMOUNT_MEDIAN[a.type] * rng.lognormvariate(0, C.TYPICAL_AMOUNT_SIGMA)
        # Opening balance never depends on later transactions or labels: a random level, but
        # at least a fixed multiple of the account's usual transaction size.
        a.opening = max(a.opening, int(round(a.scale * C.OPENING_BUFFER_MULT * 100)))
        a.balance = a.opening
        a.city = city_text(rng.choice(C.CITIES))
        a.devices = [new_device(rng) for _ in range(rng.randint(1, 2))]
        a.ips = [new_ip(rng) for _ in range(rng.randint(1, 2))]
        a.token = new_token(rng)
        a.merchants = rng.sample(range(n_merchants), min(n_merchants, rng.randint(3, 6)))
        others = [b.idx for b in active if b.idx != a.idx]
        a.contacts_int = rng.sample(others, min(len(others), rng.randint(2, 5)))
        a.contacts_ext = [new_ext_upi(rng) for _ in range(rng.randint(1, 3))]
    return active


def build_merchants(rng, n):
    cats = list(C.MERCHANT_CATEGORIES)
    names_seen, rows = set(), []
    for mid in range(1, n + 1):
        cat = rng.choice(cats)
        factor, nouns = C.MERCHANT_CATEGORIES[cat]
        name = f"{rng.choice(C.MERCHANT_PREFIXES)} {rng.choice(nouns)}"
        if name in names_seen:
            name = f"{name} {mid}"
        names_seen.add(name)
        site = None if rng.random() < C.MERCHANT_WEBSITE_NULL_RATE else f"https://www.{slug(name)}.example"
        rows.append(SimpleNamespace(id=mid, name=name, category=cat, factor=factor,
                                    location=city_text(rng.choice(C.CITIES)), website=site))
    return rows


# ---------------------------------------------------------------- transaction events
class Generator:
    def __init__(self, rng, accts, active, merchants):
        self.rng, self.accts, self.active, self.merchants = rng, accts, active, merchants
        self.cum_hours = list(accumulate(C.HOUR_WEIGHTS))
        self.events, self.buf, self.cycles, self.seq = [], [], {}, 0
        self.risky = [m.id - 1 for m in merchants if m.category in C.HIGH_RISK_CATEGORIES]
        self.cities = [city_text(c) for c in C.CITIES]
        self.mix = C.P2P_RECEIVER_MIX

    # ---- building blocks
    def hour(self):
        return self.rng.choices(range(24), cum_weights=self.cum_hours)[0]

    def group_hour(self):
        if self.rng.random() < C.NIGHT_NOISE:
            return self.rng.choice(C.NIGHT_HOURS)
        return self.hour()

    def amt(self, a, lo, hi, factor=1.0):
        return clip_cents(a.scale * factor * self.rng.uniform(lo, hi))

    def noisy_amt(self, a, factor=1.0):
        return clip_cents(a.scale * factor * self.rng.lognormvariate(0, C.AMOUNT_NOISE_SIGMA))

    def start(self, key, span_days, current_only=False):
        """Next account (round robin over a shuffled list, so groups spread out) and a start day."""
        if key not in self.cycles:
            pool = [a for a in self.active if a.type == "Current"] if current_only else []
            pool = list(pool or self.active)
            self.rng.shuffle(pool)
            self.cycles[key] = [pool, 0]
        pool, pos = self.cycles[key]
        last = C.WINDOW_END - timedelta(days=span_days)
        for _ in range(len(pool)):
            a = pool[pos % len(pool)]
            pos += 1
            if a.start_day <= last:
                self.cycles[key][1] = pos
                return a, rand_day(self.rng, a.start_day, last)
        self.cycles[key][1] = pos
        return None

    def add(self, ts, a, cat, cents, scen, pat, recv=None, upi=None, merchant=None,
            device=None, ip=None, loc=None, token=None):
        self.buf.append(dict(ts=ts, sender=a, cat=cat, cents=cents, scen=scen, pat=pat, recv=recv,
                             upi=upi, merchant=merchant, device=device, ip=ip, loc=loc, token=token))

    def home(self, a):
        r = self.rng
        return dict(device=r.choice(a.devices), ip=r.choice(a.ips), loc=a.city, token=a.token)

    def away(self, a, new_dev=True):
        r = self.rng
        city = r.choice([c for c in self.cities if c != a.city])
        ip = new_ip(r)
        while ip in a.ips:
            ip = new_ip(r)
        return dict(device=new_device(r) if new_dev else r.choice(a.devices), ip=ip, loc=city, token=a.token)

    def fav_merchant(self, a):
        r = self.rng
        return r.choice(a.merchants) if r.random() < 0.85 else r.randrange(len(self.merchants))

    def new_merchant(self, a, pool=None):
        pool = [m for m in (pool or range(len(self.merchants))) if m not in a.merchants]
        return self.rng.choice(pool) if pool else self.rng.randrange(len(self.merchants))

    def receiver(self, a, ts, used=None, fresh=False):
        """(receiver account index or None, UPI id or None) for a P2P row."""
        r = self.rng
        for _ in range(6):
            mode = r.choices(("acct", "both", "ext"), weights=self.mix)[0]
            recv = upi = None
            if mode != "ext":
                if not fresh and a.contacts_int and r.random() < 0.8:
                    b = r.choice(a.contacts_int)
                else:
                    b = r.choice(self.active).idx
                if b == a.idx or self.accts[b].created >= ts:
                    continue
                recv = b
                if mode == "both":
                    upi = f"u{self.accts[b].number}@{C.UPI_DOMAIN}"
            else:
                upi = r.choice(a.contacts_ext) if (not fresh and r.random() < 0.8) else new_ext_upi(r)
            key = ("a", recv) if recv is not None else ("u", upi)
            if used is not None:
                if key in used:
                    continue
                used.add(key)
            return recv, upi
        return None, new_ext_upi(r)

    def p2p(self, ts, a, cents, scen, pat, used=None, fresh=False):
        recv, upi = self.receiver(a, ts, used, fresh)
        self.add(ts, a, "P2P", cents, scen, pat, recv=recv, upi=upi)

    def cnp(self, ts, a, cents, scen, pat, merchant, fields):
        self.add(ts, a, "CNP", cents, scen, pat, merchant=merchant, **fields)

    # ---- fraud patterns and their legitimate look-alikes (one function each)
    def large(self, scen, pat, frac, floor, p2p_share):
        got = self.start(pat, 1)
        if not got:
            return
        a, day = got
        t = at(self.rng, day, self.group_hour())
        for _ in range(1 if self.rng.random() < 0.7 else 2):
            cents = clip_cents(max(floor, a.opening / 100 * self.rng.uniform(*frac)))
            if self.rng.random() < p2p_share:
                self.p2p(t, a, cents, scen, pat)
            else:
                self.cnp(t, a, cents, scen, pat, self.fav_merchant(a), self.home(a))
            t += timedelta(minutes=self.rng.randint(5, 120))

    def high_amount(self, scen, pat):
        self.large(scen, pat, (0.15, 0.55), 20000, 0.5)

    def large_planned_purchase(self, scen, pat):
        self.large(scen, pat, (0.10, 0.50), 15000, 0.3)

    def velocity_burst(self, scen, pat):
        got = self.start(pat, 1)
        if not got:
            return
        r = self.rng
        a, day = got
        t = at(r, day, self.group_hour())
        fields = self.away(a, True) if r.random() < 0.5 else self.home(a)
        ms = [r.randrange(len(self.merchants)) for _ in range(r.randint(1, 3))]
        for _ in range(r.randint(5, 12)):
            m = r.choice(ms)
            self.cnp(t, a, self.amt(a, 0.5, 3, self.merchants[m].factor), scen, pat, m, fields)
            t += timedelta(seconds=r.randint(5, 120))

    def festival_burst(self, scen, pat):
        got = self.start(pat, 1)
        if not got:
            return
        r = self.rng
        a, _ = got
        days = [d for d in C.FESTIVAL_DAYS if d >= a.start_day]
        day = r.choice(days) if days else rand_day(r, a.start_day, C.WINDOW_END - timedelta(days=1))
        t = at(r, day, r.randint(10, 21))
        fields = self.home(a)
        for _ in range(r.randint(4, 11)):
            m = self.fav_merchant(a)
            self.cnp(t, a, self.amt(a, 0.4, 2.5, self.merchants[m].factor), scen, pat, m, fields)
            t += timedelta(seconds=r.randint(15, 300))

    def night_events(self, scen, pat, lo, hi):
        got = self.start(pat, 1)
        if not got:
            return
        r = self.rng
        a, day = got
        midnight = datetime.combine(day, time(0, 0))
        window = 3600 * len(C.NIGHT_HOURS)          # every row stays inside the night hours
        for sec in sorted(r.randrange(window) for _ in range(r.randint(1, 3))):
            t = midnight + timedelta(seconds=sec)
            if r.random() < 0.5:
                self.p2p(t, a, self.amt(a, lo, hi), scen, pat)
            else:
                m = self.fav_merchant(a)
                fields = self.home(a) if r.random() < 0.7 else self.away(a, True)
                self.cnp(t, a, self.amt(a, lo, hi, self.merchants[m].factor), scen, pat, m, fields)

    def odd_hour(self, scen, pat):
        self.night_events(scen, pat, 1.5, 6)

    def night_shift(self, scen, pat):
        self.night_events(scen, pat, 0.5, 2.5)

    def many_receivers(self, scen, pat, current_only, lo, hi, round_prob):
        got = self.start(pat, 1, current_only)
        if not got:
            return
        r = self.rng
        a, day = got
        t = at(r, day, self.group_hour())
        used = set()
        step = r.randint(2, 18)
        for _ in range(r.randint(6, 14)):
            cents = self.amt(a, lo, hi)
            if r.random() < round_prob and cents >= 10000:     # only some rows are round
                cents = cents // 10000 * 10000
            self.p2p(t, a, cents, scen, pat, used, fresh=True)
            t += timedelta(minutes=r.randint(1, step))

    def fan_out(self, scen, pat):
        self.many_receivers(scen, pat, False, 0.6, 2.5, C.FAN_OUT_ROUND_SHARE)

    def business_payouts(self, scen, pat):
        self.many_receivers(scen, pat, True, 1, 6, C.PAYOUT_ROUND_SHARE)

    def merchant_events(self, scen, pat, risky, lo, hi, count):
        got = self.start(pat, 1)
        if not got:
            return
        r = self.rng
        a, day = got
        t = at(r, day, self.group_hour())
        fields = self.home(a) if r.random() < 0.8 else self.away(a, True)
        for _ in range(r.randint(*count)):
            m = self.new_merchant(a, self.risky if risky else None)
            self.cnp(t, a, self.amt(a, lo, hi, self.merchants[m].factor), scen, pat, m, fields)
            t += timedelta(minutes=r.randint(3, 90))

    def merchant_anomaly(self, scen, pat):
        self.merchant_events(scen, pat, True, 3, 10, (1, 3))

    def new_merchant_trial(self, scen, pat):
        self.merchant_events(scen, pat, False, 1.5, 6, (1, 2))

    def card_testing(self, scen, pat):
        """Small probe charges (Rs 1-30), then one larger final charge."""
        got = self.start(pat, 1)
        if not got:
            return
        r = self.rng
        a, day = got
        t = at(r, day, self.group_hour())
        fields = self.home(a) if r.random() < 0.5 else self.away(a, True)
        m = r.randrange(len(self.merchants))
        same = r.uniform(1, 30) if r.random() < 0.3 else None
        for _ in range(r.randint(4, 9)):
            if r.random() < 0.3:
                m = r.randrange(len(self.merchants))
            self.cnp(t, a, clip_cents(same if same else r.uniform(1, 30)), scen, pat, m, fields)
            t += timedelta(seconds=r.randint(20, 240))
        t += timedelta(seconds=r.randint(30, 300))
        self.cnp(t, a, clip_cents(max(500, a.scale * r.uniform(2, 8))), scen, pat, m, fields)

    def small_recurring_payments(self, scen, pat):
        """Subscriptions (same small amount every 6-24 h) or a run of small taps (parking, transit)."""
        got = self.start(pat, 10)
        if not got:
            return
        r = self.rng
        a, day = got
        t = at(r, day, self.group_hour())
        fields, m = self.home(a), self.fav_merchant(a)
        if r.random() < 0.35:
            for _ in range(r.randint(3, 6)):
                self.cnp(t, a, clip_cents(r.uniform(5, 30)), scen, pat, m, fields)
                t += timedelta(minutes=r.randint(2, 8))
            return
        rupees = r.choice([19, 29, 49, 99, 149, 199, 299, 499, 649])
        gap = r.choice([6, 12, 24])
        for _ in range(r.randint(5, 10)):
            self.cnp(t, a, clip_cents(rupees), scen, pat, m, fields)
            t += timedelta(hours=gap, minutes=r.randint(-5, 5))

    def device_geo_change(self, scen, pat):
        self.away_events(scen, pat, 0.75, 2, 8, (1, 4), 120)

    def travel_purchase(self, scen, pat):
        self.away_events(scen, pat, 0.15, 1.5, 6, (1, 5), 2000)

    def away_events(self, scen, pat, new_dev_prob, lo, hi, count, max_gap_min):
        got = self.start(pat, 3)
        if not got:
            return
        r = self.rng
        a, day = got
        t = at(r, day, self.group_hour())
        fields = self.away(a, r.random() < new_dev_prob)
        for _ in range(r.randint(*count)):
            m = self.fav_merchant(a) if r.random() < 0.5 else r.randrange(len(self.merchants))
            self.cnp(t, a, self.amt(a, lo, hi, self.merchants[m].factor), scen, pat, m, fields)
            t += timedelta(minutes=r.randint(10, max_gap_min))

    # ---- drivers
    def run_groups(self, scen, quotas):
        """Make groups until each pattern has exactly its quota of rows (last group trimmed)."""
        short = 0
        for pat, quota in quotas.items():
            make, got, fails = getattr(self, pat), 0, 0
            while got < quota and fails < 200:
                self.buf = []
                make(scen, pat)
                if not self.buf or max(e["ts"] for e in self.buf) >= LAST_MOMENT:
                    fails += 1              # empty, or it would spill past 2025-12-31
                    continue
                need = quota - got
                take = self.buf[:need]
                if pat == "card_testing" and 2 <= need < len(self.buf):
                    take = self.buf[:need - 1] + self.buf[-1:]      # keep the final big charge
                self.events.extend(take)
                got += len(take)
            short += quota - got
        return short

    def run_normal(self, count, p_p2p):
        r = self.rng
        weights = [r.lognormvariate(0, 0.7) * ((C.WINDOW_END - a.start_day).days + 1) / 365 for a in self.active]
        cum = list(accumulate(weights))
        for _ in range(count):
            a = r.choices(self.active, cum_weights=cum)[0]
            t = at(r, rand_day(r, a.start_day, C.WINDOW_END), self.hour())
            self.buf = []
            small = r.random() < C.SMALL_PAYMENT_SHARE      # everyday tiny payments (Rs 1-30)
            rounded = r.random() < C.NORMAL_ROUND_SHARE
            if r.random() < p_p2p:
                cents = self.noisy_amt(a)
                if small:
                    cents = clip_cents(r.uniform(1, 30))
                elif rounded and cents >= 10000:
                    cents = cents // 10000 * 10000
                self.p2p(t, a, cents, "normal", "normal")
            else:
                m = self.fav_merchant(a)
                cents = self.noisy_amt(a, self.merchants[m].factor)
                if small:
                    cents = clip_cents(r.uniform(1, 30))
                elif rounded and cents >= 10000:
                    cents = cents // 10000 * 10000
                self.cnp(t, a, cents, "normal", "normal", m, self.home(a))
            self.events.extend(self.buf)


def build_transactions(rng, accts, active, merchants, total):
    gen = Generator(rng, accts, active, merchants)
    n_fraud, n_edge = round(total * C.FRAUD_RATE), round(total * C.EDGE_RATE)
    weights = {p[0]: p[2] for p in C.PATTERN_PAIRS}
    short = gen.run_groups("fraud", allocate(n_fraud, weights))
    edge_weights = {p[1]: p[2] for p in C.PATTERN_PAIRS}
    short += gen.run_groups("legit_edge", allocate(n_edge, edge_weights))
    special_p2p = sum(1 for e in gen.events if e["cat"] == "P2P")
    n_normal = total - len(gen.events)
    p_p2p = min(1.0, max(0.0, (round(total * C.P2P_SHARE) - special_p2p) / max(1, n_normal)))
    gen.run_normal(n_normal, p_p2p)

    events = gen.events
    for i, e in enumerate(events):
        e["seq"] = i
    events.sort(key=lambda e: (e["ts"], e["seq"]))
    status_names = [s for s, _ in C.STATUS_PROBS]
    status_cum = list(accumulate(w for _, w in C.STATUS_PROBS))
    for i, e in enumerate(events, 1):
        e["id"] = i
        if e["cat"] == "CNP":     # a few documented gaps, same rate for every label
            if rng.random() < C.CNP_MERCHANT_NULL_RATE:
                e["merchant"] = None
            for f in ("device", "ip", "loc", "token"):
                if rng.random() < C.CNP_FIELD_NULL_RATE:
                    e[f] = None
        e["created"] = e["ts"] + timedelta(seconds=rng.randint(0, 5))
        status = rng.choices(status_names, cum_weights=status_cum)[0]   # same odds for every label
        s = e["sender"]
        if status == "SUCCESS":
            if s.balance >= e["cents"]:       # only real shortage changes the draw
                s.balance -= e["cents"]
                if e["recv"] is not None:
                    accts[e["recv"]].balance += e["cents"]
            else:
                status = "FAILED"
        e["status"] = status
    return events, short


# ---------------------------------------------------------------- output files
def insert_block(table, columns, rows):
    lines = []
    for start in range(0, len(rows), C.BATCH_SIZE):
        chunk = rows[start:start + C.BATCH_SIZE]
        lines.append(f"INSERT INTO {table} ({', '.join(columns)}) VALUES")
        lines.extend(row + ("," if j < len(chunk) - 1 else ";") for j, row in enumerate(chunk))
        lines.append("")
    return lines


GUARD = """-- Guard helper. It SIGNALs (changing no data) unless the six data tables are empty and the
-- four master rows exist, and it is dropped right after the check. The session is made
-- read-only before the helper runs and only the helper's success path makes it writable
-- again, so a refused session cannot insert anything, even with mysql --force or in
-- Workbench. If a run is refused: in Workbench use Query > Reconnect to Server before
-- anything else; the empty helper left behind is removed by the next run.
SET @old_sql_notes = @@sql_notes, sql_notes = 0;
DROP PROCEDURE IF EXISTS sp_seed_guard;
SET sql_notes = @old_sql_notes;
DELIMITER $$
CREATE PROCEDURE sp_seed_guard()
BEGIN
    IF EXISTS (SELECT 1 FROM Customer) OR EXISTS (SELECT 1 FROM Account)
       OR EXISTS (SELECT 1 FROM Merchant) OR EXISTS (SELECT 1 FROM `Transaction`)
       OR EXISTS (SELECT 1 FROM Fraud_Alert) OR EXISTS (SELECT 1 FROM Investigation) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Seed refused: a target table already has rows. Nothing was changed.';
    END IF;
    IF (SELECT COUNT(*) FROM AccountType WHERE TypeName IN ('Savings', 'Current')) <> 2
       OR (SELECT COUNT(*) FROM TransactionType WHERE TypeName IN ('P2P_UPI', 'CNP_ECOM')) <> 2 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Seed refused: master data (Savings, Current, P2P_UPI, CNP_ECOM) is missing. Run master_data.sql first.';
    END IF;
    COMMIT;
    SET SESSION transaction_read_only = 0;
END$$
DELIMITER ;
SET SESSION transaction_read_only = 1;
CALL sp_seed_guard();
DROP PROCEDURE sp_seed_guard;
"""


def render_sql(args, customers, accts, merchants, events):
    out = [
        "-- Synthetic seed data for banking_fraud_detection (Phase 2). All data is fictional.",
        f"-- Generated by data_generation/generate_data.py --seed {args.seed} --customers {args.customers}"
        f" --accounts {args.accounts} --merchants {args.merchants} --transactions {args.transactions}",
        "-- Runs only on an empty database; see docs/PHASE2_DATA_GENERATION.md.",
        "-- If this script stops with an error in MySQL Workbench, run ROLLBACK; before anything else.",
        "",
        "USE banking_fraud_detection;",
        GUARD,
        "-- Master rows are looked up by name, never by hard-coded ID.",
        "SET @at_savings = (SELECT AccountTypeID FROM AccountType WHERE TypeName = 'Savings');",
        "SET @at_current = (SELECT AccountTypeID FROM AccountType WHERE TypeName = 'Current');",
        "SET @tt_p2p = (SELECT TransactionTypeID FROM TransactionType WHERE TypeName = 'P2P_UPI');",
        "SET @tt_cnp = (SELECT TransactionTypeID FROM TransactionType WHERE TypeName = 'CNP_ECOM');",
        "-- Strict mode makes bad data an error (so the whole load rolls back); the old mode is restored after COMMIT.",
        "SET @old_sql_mode = @@sql_mode;",
        "SET SESSION sql_mode = CONCAT_WS(',', @@sql_mode, 'STRICT_ALL_TABLES');",
        "",
        "START TRANSACTION;",
        "",
    ]
    out += insert_block("Customer",
        ["CustomerID", "FirstName", "LastName", "DateOfBirth", "Email", "Phone", "Address", "CreatedAt"],
        [f"({c.id}, {q(c.first)}, {q(c.last)}, '{c.dob}', {q(c.email)}, {q(c.phone)}, {q(c.address)}, "
         f"'{ts_str(c.created)}')" for c in customers])
    out += insert_block("Merchant",
        ["MerchantID", "MerchantName", "Category", "Location", "Website"],
        [f"({m.id}, {q(m.name)}, {q(m.category)}, {q(m.location)}, {q(m.website)})" for m in merchants])
    out += insert_block("Account",
        ["AccountNumber", "CustomerID", "AccountTypeID", "Balance", "AccountStatus", "CreatedAt"],
        [f"({a.number}, {a.cust.id}, {'@at_current' if a.type == 'Current' else '@at_savings'}, "
         f"{money(a.balance)}, '{a.status}', '{ts_str(a.created)}')" for a in accts])
    rows = []
    for e in events:
        recv = accts[e["recv"]].number if e["recv"] is not None else None
        merchant = merchants[e["merchant"]].id if e["merchant"] is not None else None
        rows.append(
            f"({e['id']}, '{ts_str(e['ts'])}', {money(e['cents'])}, '{e['status']}', {e['sender'].number}, "
            f"{'NULL' if recv is None else recv}, {q(e['upi'])}, {'@tt_p2p' if e['cat'] == 'P2P' else '@tt_cnp'}, "
            f"{'NULL' if merchant is None else merchant}, {q(e['device'])}, {q(e['ip'])}, {q(e['loc'])}, "
            f"{q(e['token'])}, NULL, NULL, 'NOT_SCORED', '{ts_str(e['created'])}')")
    out += insert_block("`Transaction`",
        ["TransactionID", "TransactionTimestamp", "Amount", "Status", "SenderAccountNumber",
         "ReceiverAccountNumber", "ReceiverUPIID", "TransactionTypeID", "MerchantID", "DeviceID",
         "IPAddress", "Location", "CardReferenceToken", "FraudScore", "FraudPrediction", "RiskStatus",
         "CreatedAt"], rows)
    out += ["COMMIT;", "SET SESSION sql_mode = @old_sql_mode;", ""]
    return "\n".join(out)


VALIDATE_HEAD = r"""-- Phase 2 check of the loaded synthetic data. READ-ONLY: it only runs one SELECT.
-- GENERATED by data_generation/generate_data.py together with seed_data.sql (do not edit by hand).
-- Run after database/seed_data.sql. Works in MySQL Workbench and the mysql CLI.
-- Output: one result set. Every row is a check with bad_rows (0 is good) and PASS/FAIL.
-- The last row (SUMMARY) says FAIL if any check failed. Rows 1-4 and 100+ compare against the exact
-- row counts, balance total, status totals and content fingerprints of the generated dataset, so
-- a partial load, deleted rows, an edited balance or a changed status all FAIL.
USE banking_fraud_detection;

WITH checks AS (
    -- ---- other tables (Fraud_Alert / Investigation stay empty in Phase 2)
    SELECT 5 AS seq, 'rows: Fraud_Alert empty (Phase 2 only)' AS check_name, (SELECT COUNT(*) FROM Fraud_Alert) AS bad_rows
    UNION ALL SELECT 6, 'rows: Investigation empty (Phase 2 only)', (SELECT COUNT(*) FROM Investigation)

    -- ---- foreign keys (orphans)
    UNION ALL SELECT 10, 'fk: Account.CustomerID exists',
        (SELECT COUNT(*) FROM Account a LEFT JOIN Customer c ON c.CustomerID = a.CustomerID WHERE c.CustomerID IS NULL)
    UNION ALL SELECT 11, 'fk: Account.AccountTypeID exists',
        (SELECT COUNT(*) FROM Account a LEFT JOIN AccountType t ON t.AccountTypeID = a.AccountTypeID WHERE t.AccountTypeID IS NULL)
    UNION ALL SELECT 12, 'fk: Transaction sender exists',
        (SELECT COUNT(*) FROM `Transaction` x LEFT JOIN Account a ON a.AccountNumber = x.SenderAccountNumber WHERE a.AccountNumber IS NULL)
    UNION ALL SELECT 13, 'fk: Transaction receiver exists',
        (SELECT COUNT(*) FROM `Transaction` x LEFT JOIN Account a ON a.AccountNumber = x.ReceiverAccountNumber
          WHERE x.ReceiverAccountNumber IS NOT NULL AND a.AccountNumber IS NULL)
    UNION ALL SELECT 14, 'fk: Transaction type exists',
        (SELECT COUNT(*) FROM `Transaction` x LEFT JOIN TransactionType t ON t.TransactionTypeID = x.TransactionTypeID WHERE t.TransactionTypeID IS NULL)
    UNION ALL SELECT 15, 'fk: Transaction merchant exists',
        (SELECT COUNT(*) FROM `Transaction` x LEFT JOIN Merchant m ON m.MerchantID = x.MerchantID
          WHERE x.MerchantID IS NOT NULL AND m.MerchantID IS NULL)

    -- ---- duplicates
    UNION ALL SELECT 20, 'dup: Customer PK', (SELECT COUNT(*) - COUNT(DISTINCT CustomerID) FROM Customer)
    UNION ALL SELECT 21, 'dup: Customer Email', (SELECT COUNT(*) - COUNT(DISTINCT Email) FROM Customer)
    UNION ALL SELECT 22, 'dup: Customer Phone', (SELECT COUNT(*) - COUNT(DISTINCT Phone) FROM Customer)
    UNION ALL SELECT 23, 'dup: Account PK', (SELECT COUNT(*) - COUNT(DISTINCT AccountNumber) FROM Account)
    UNION ALL SELECT 24, 'dup: Merchant PK', (SELECT COUNT(*) - COUNT(DISTINCT MerchantID) FROM Merchant)
    UNION ALL SELECT 25, 'dup: Transaction PK', (SELECT COUNT(*) - COUNT(DISTINCT TransactionID) FROM `Transaction`)

    -- ---- required columns not NULL
    UNION ALL SELECT 30, 'null: Customer required columns',
        (SELECT COUNT(*) FROM Customer WHERE FirstName IS NULL OR LastName IS NULL OR DateOfBirth IS NULL
            OR Email IS NULL OR Phone IS NULL OR CreatedAt IS NULL)
    UNION ALL SELECT 31, 'null: Account required columns',
        (SELECT COUNT(*) FROM Account WHERE CustomerID IS NULL OR AccountTypeID IS NULL OR Balance IS NULL
            OR AccountStatus IS NULL OR CreatedAt IS NULL)
    UNION ALL SELECT 32, 'null: Merchant name',
        (SELECT COUNT(*) FROM Merchant WHERE MerchantName IS NULL)
    UNION ALL SELECT 33, 'null: Transaction required columns',
        (SELECT COUNT(*) FROM `Transaction` WHERE TransactionTimestamp IS NULL OR Amount IS NULL OR Status IS NULL
            OR SenderAccountNumber IS NULL OR TransactionTypeID IS NULL OR RiskStatus IS NULL OR CreatedAt IS NULL)

    -- ---- categories and per-category fields
    UNION ALL SELECT 40, 'category: only P2P_UPI or CNP_ECOM',
        (SELECT COUNT(*) FROM `Transaction` x JOIN TransactionType t ON t.TransactionTypeID = x.TransactionTypeID
          WHERE t.TypeName NOT IN ('P2P_UPI', 'CNP_ECOM'))
    UNION ALL SELECT 41, 'category: P2P has receiver account or UPI',
        (SELECT COUNT(*) FROM `Transaction` x JOIN TransactionType t ON t.TransactionTypeID = x.TransactionTypeID
          WHERE t.TypeName = 'P2P_UPI' AND x.ReceiverAccountNumber IS NULL
            AND (x.ReceiverUPIID IS NULL OR x.ReceiverUPIID REGEXP '^[[:space:]]*$'))
    UNION ALL SELECT 42, 'category: P2P has no merchant, token, device, IP, location',
        (SELECT COUNT(*) FROM `Transaction` x JOIN TransactionType t ON t.TransactionTypeID = x.TransactionTypeID
          WHERE t.TypeName = 'P2P_UPI' AND (x.MerchantID IS NOT NULL OR x.CardReferenceToken IS NOT NULL
             OR x.DeviceID IS NOT NULL OR x.IPAddress IS NOT NULL OR x.Location IS NOT NULL))
    UNION ALL SELECT 43, 'category: CNP has no receiver account or UPI',
        (SELECT COUNT(*) FROM `Transaction` x JOIN TransactionType t ON t.TransactionTypeID = x.TransactionTypeID
          WHERE t.TypeName = 'CNP_ECOM' AND (x.ReceiverAccountNumber IS NOT NULL OR x.ReceiverUPIID IS NOT NULL))

    -- ---- values
    UNION ALL SELECT 50, 'value: sender differs from receiver',
        (SELECT COUNT(*) FROM `Transaction` WHERE SenderAccountNumber = ReceiverAccountNumber)
    UNION ALL SELECT 51, 'value: Amount > 0', (SELECT COUNT(*) FROM `Transaction` WHERE Amount <= 0)
    UNION ALL SELECT 52, 'value: Balance >= 0', (SELECT COUNT(*) FROM Account WHERE Balance < 0)
    UNION ALL SELECT 53, 'value: customers are adults when created',
        (SELECT COUNT(*) FROM Customer WHERE TIMESTAMPDIFF(YEAR, DateOfBirth, CreatedAt) < 18)

    -- ---- blank strings (NULL is the only allowed empty value; tabs and spaces count as blank)
    UNION ALL SELECT 60, 'blank: Customer text columns',
        (SELECT COUNT(*) FROM Customer WHERE FirstName REGEXP '^[[:space:]]*$' OR LastName REGEXP '^[[:space:]]*$'
            OR Email REGEXP '^[[:space:]]*$' OR Phone REGEXP '^[[:space:]]*$' OR Address REGEXP '^[[:space:]]*$')
    UNION ALL SELECT 61, 'blank: Merchant text columns',
        (SELECT COUNT(*) FROM Merchant WHERE MerchantName REGEXP '^[[:space:]]*$' OR Category REGEXP '^[[:space:]]*$'
            OR Location REGEXP '^[[:space:]]*$' OR Website REGEXP '^[[:space:]]*$')
    UNION ALL SELECT 62, 'blank: Transaction text columns',
        (SELECT COUNT(*) FROM `Transaction` WHERE ReceiverUPIID REGEXP '^[[:space:]]*$' OR DeviceID REGEXP '^[[:space:]]*$'
            OR IPAddress REGEXP '^[[:space:]]*$' OR Location REGEXP '^[[:space:]]*$' OR CardReferenceToken REGEXP '^[[:space:]]*$')

    -- ---- timestamp ordering
    UNION ALL SELECT 70, 'time: account created after its customer',
        (SELECT COUNT(*) FROM Account a JOIN Customer c ON c.CustomerID = a.CustomerID WHERE a.CreatedAt < c.CreatedAt)
    UNION ALL SELECT 71, 'time: transaction after sender account was created',
        (SELECT COUNT(*) FROM `Transaction` x JOIN Account a ON a.AccountNumber = x.SenderAccountNumber
          WHERE x.TransactionTimestamp <= a.CreatedAt)
    UNION ALL SELECT 72, 'time: transaction after receiver account was created',
        (SELECT COUNT(*) FROM `Transaction` x JOIN Account a ON a.AccountNumber = x.ReceiverAccountNumber
          WHERE x.TransactionTimestamp <= a.CreatedAt)
    UNION ALL SELECT 73, 'time: CreatedAt not before TransactionTimestamp',
        (SELECT COUNT(*) FROM `Transaction` WHERE CreatedAt < TransactionTimestamp)
    UNION ALL SELECT 74, 'time: transactions inside 2025-01-01 to 2025-12-31',
        (SELECT COUNT(*) FROM `Transaction`
          WHERE TransactionTimestamp < '2025-01-01 00:00:00' OR TransactionTimestamp >= '2026-01-01 00:00:00')

    -- ---- scoring and account status
    UNION ALL SELECT 80, 'scoring: all rows unscored',
        (SELECT COUNT(*) FROM `Transaction`
          WHERE FraudScore IS NOT NULL OR FraudPrediction IS NOT NULL OR RiskStatus <> 'NOT_SCORED')
    UNION ALL SELECT 81, 'status: sender account is ACTIVE',
        (SELECT COUNT(*) FROM `Transaction` x JOIN Account a ON a.AccountNumber = x.SenderAccountNumber
          WHERE a.AccountStatus <> 'ACTIVE')
    UNION ALL SELECT 82, 'status: receiver account is ACTIVE',
        (SELECT COUNT(*) FROM `Transaction` x JOIN Account a ON a.AccountNumber = x.ReceiverAccountNumber
          WHERE a.AccountStatus <> 'ACTIVE')

    -- ---- synthetic-only values (REGEXP_LIKE with 'c' is case-sensitive)
    UNION ALL SELECT 90, 'synthetic: card token is tok_<lowercase letters> (no card-like digits)',
        (SELECT COUNT(*) FROM `Transaction`
          WHERE CardReferenceToken IS NOT NULL
            AND (NOT REGEXP_LIKE(CardReferenceToken, '^tok_[a-z]+$', 'c')
                 OR CardReferenceToken REGEXP '([0-9][^A-Za-z0-9]*){12}'))
    UNION ALL SELECT 91, 'synthetic: IP in RFC 5737 ranges with last octet 1-254',
        (SELECT COUNT(*) FROM `Transaction`
          WHERE IPAddress IS NOT NULL AND NOT REGEXP_LIKE(IPAddress,
            '^(192[.]0[.]2|198[.]51[.]100|203[.]0[.]113)[.]([1-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-4])$', 'c'))
    UNION ALL SELECT 92, 'synthetic: customer email is name@example.com',
        (SELECT COUNT(*) FROM Customer WHERE NOT REGEXP_LIKE(Email, '^[a-z0-9.]+@example[.]com$', 'c'))
    UNION ALL SELECT 93, 'synthetic: phone is 00000 plus 8 digits',
        (SELECT COUNT(*) FROM Customer WHERE NOT REGEXP_LIKE(Phone, '^00000[0-9]{8}$', 'c'))
    UNION ALL SELECT 94, 'synthetic: merchant website is https://www.<name>.example',
        (SELECT COUNT(*) FROM Merchant WHERE Website IS NOT NULL
            AND NOT REGEXP_LIKE(Website, '^https://www[.][a-z0-9]+[.]example$', 'c'))
    UNION ALL SELECT 95, 'synthetic: UPI ids are <name>@synthupi',
        (SELECT COUNT(*) FROM `Transaction` WHERE ReceiverUPIID IS NOT NULL
            AND NOT REGEXP_LIKE(ReceiverUPIID, '^[a-z0-9]+@synthupi$', 'c'))
    UNION ALL SELECT 96, 'synthetic: device ids are dev_<hex>',
        (SELECT COUNT(*) FROM `Transaction` WHERE DeviceID IS NOT NULL AND NOT REGEXP_LIKE(DeviceID, '^dev_[0-9a-f]+$', 'c'))
"""

VALIDATE_TAIL = r"""
)
SELECT seq, check_name, CAST(bad_rows AS SIGNED) AS bad_rows,
       IF(bad_rows = 0, 'PASS', 'FAIL') AS result
FROM checks
UNION ALL
SELECT 999, 'SUMMARY: checks failed', CAST(SUM(bad_rows <> 0) AS SIGNED),
       IF(SUM(bad_rows <> 0) = 0, 'PASS', 'FAIL')
FROM checks
ORDER BY seq;
"""


def fingerprint(strings):
    return sum(zlib.crc32(x.encode()) for x in strings)


def expected_checks(customers, accts, merchants, events):
    """(seq, name, SQL expression that is 0 when the loaded data matches this dataset)."""
    amount_total = money(sum(e["cents"] for e in events))
    txn_fp = fingerprint(
        "{}|{}|{}|{}|{}|{}".format(e["id"], ts_str(e["ts"]), money(e["cents"]), e["status"], e["sender"].number,
                                   "" if e["recv"] is None else accts[e["recv"]].number) for e in events)
    rows = [
        (1, "exact: Customer rows and content fingerprint",
         f"(SELECT (COUNT(*) <> {len(customers)}) + (COALESCE(SUM(CRC32(CONCAT(CustomerID, '|', Email, '|', Phone))), 0)"
         f" <> {fingerprint(f'{c.id}|{c.email}|{c.phone}' for c in customers)}) FROM Customer)"),
        (2, "exact: Account rows, balance total and content fingerprint",
         f"(SELECT (COUNT(*) <> {len(accts)}) + (COALESCE(SUM(Balance), 0) <> {money(sum(a.balance for a in accts))})"
         f" + (COALESCE(SUM(CRC32(CONCAT(AccountNumber, '|', CustomerID, '|', Balance, '|', AccountStatus, '|', CreatedAt))), 0)"
         f" <> {fingerprint(f'{a.number}|{a.cust.id}|{money(a.balance)}|{a.status}|{ts_str(a.created)}' for a in accts)}) FROM Account)"),
        (3, "exact: Merchant rows and content fingerprint",
         f"(SELECT (COUNT(*) <> {len(merchants)}) + (COALESCE(SUM(CRC32(CONCAT(MerchantID, '|', MerchantName))), 0)"
         f" <> {fingerprint(f'{m.id}|{m.name}' for m in merchants)}) FROM Merchant)"),
        (4, "exact: Transaction rows, amount total and content fingerprint",
         f"(SELECT (COUNT(*) <> {len(events)}) + (COALESCE(SUM(Amount), 0) <> {amount_total})"
         f" + (COALESCE(SUM(CRC32(CONCAT(TransactionID, '|', TransactionTimestamp, '|', Amount, '|', Status, '|',"
         f" SenderAccountNumber, '|', IFNULL(ReceiverAccountNumber, '')))), 0) <> {txn_fp}) FROM `Transaction`)"),
    ]
    for i, st in enumerate(("SUCCESS", "FAILED", "PENDING", "REVERSED")):
        sel = [e for e in events if e["status"] == st]
        rows.append((100 + i, f"exact: {st} transactions, count and amount total",
                     f"(SELECT (COUNT(*) <> {len(sel)}) + (COALESCE(SUM(Amount), 0) <> {money(sum(e['cents'] for e in sel))})"
                     f" FROM `Transaction` WHERE Status = '{st}')"))
    for i, (name, cat) in enumerate((("P2P_UPI", "P2P"), ("CNP_ECOM", "CNP"))):
        rows.append((110 + i, f"exact: {name} transaction count",
                     f"(SELECT COUNT(*) <> {sum(1 for e in events if e['cat'] == cat)} FROM `Transaction` x"
                     f" JOIN TransactionType t ON t.TransactionTypeID = x.TransactionTypeID WHERE t.TypeName = '{name}')"))
    return rows


def render_validate_sql(customers, accts, merchants, events):
    lines = [f"    UNION ALL SELECT {seq}, '{name}', {expr}" for seq, name, expr in expected_checks(customers, accts, merchants, events)]
    return VALIDATE_HEAD + "\n    -- ---- exact expectations for this dataset\n" + "\n".join(lines) + "\n" + VALIDATE_TAIL


def csv_text(header, rows):
    class Sink:
        def __init__(self):
            self.parts = []

        def write(self, s):
            self.parts.append(s)

    sink = Sink()
    w = csv.writer(sink, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return "".join(sink.parts)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def count_by(events, key):
    out = {}
    for e in events:
        out[key(e)] = out.get(key(e), 0) + 1
    return dict(sorted(out.items()))


def main():
    p = argparse.ArgumentParser(description="Generate synthetic seed data (no database connection).")
    p.add_argument("--seed", type=int, default=C.DEFAULT_SEED)
    p.add_argument("--customers", type=int, default=C.DEFAULT_CUSTOMERS)
    p.add_argument("--accounts", type=int, default=C.DEFAULT_ACCOUNTS)
    p.add_argument("--merchants", type=int, default=C.DEFAULT_MERCHANTS)
    p.add_argument("--transactions", type=int, default=C.DEFAULT_TRANSACTIONS)
    p.add_argument("--force", action="store_true", help="overwrite existing output files")
    p.add_argument("--sql-out", default=DEFAULT_SQL, help="path for seed_data.sql")
    p.add_argument("--out-dir", default=DEFAULT_OUT, help="folder for labels, balances and manifest")
    p.add_argument("--validate-sql-out", default=DEFAULT_VALIDATE_SQL, help="path for validate_seed_data.sql")
    args = p.parse_args()
    for name in ("customers", "accounts", "merchants", "transactions"):
        if getattr(args, name) < 1:
            p.error(f"--{name} must be at least 1 (got {getattr(args, name)})")
    if args.accounts < args.customers:
        p.error(f"--accounts ({args.accounts}) must be at least --customers ({args.customers}): "
                "every customer gets one account")
    if args.accounts < 2:
        p.error("--accounts must be at least 2 (transfers need two accounts)")
    if args.seed < 0:
        p.error("--seed must not be negative")

    paths = {"sql": args.sql_out,
             "labels": os.path.join(args.out_dir, "labels.csv"),
             "balances": os.path.join(args.out_dir, "opening_balances.csv"),
             "manifest": os.path.join(args.out_dir, "manifest.json"),
             "validate": args.validate_sql_out}
    existing = [x for x in paths.values() if os.path.exists(x)]
    if existing and not args.force:
        sys.exit("error: output exists (use --force to overwrite): " + ", ".join(existing))

    rng = random.Random(args.seed)
    customers = build_customers(rng, args.customers)
    accts = build_accounts(rng, customers, args.accounts)
    merchants = build_merchants(rng, args.merchants)
    active = build_profiles(rng, accts, args.merchants)
    events, short = build_transactions(rng, accts, active, merchants, args.transactions)

    sql = render_sql(args, customers, accts, merchants, events)
    labels = csv_text(["TransactionID", "IsFraud", "Scenario", "Pattern"],
                      [(e["id"], 1 if e["scen"] == "fraud" else 0, e["scen"], e["pat"]) for e in events])
    balances = csv_text(["AccountNumber", "OpeningBalance", "ClosingBalance"],
                        [(a.number, money(a.opening), money(a.balance)) for a in accts])
    validate_sql = render_validate_sql(customers, accts, merchants, events)
    manifest = {
        "seed": args.seed,
        "arguments": {"customers": args.customers, "accounts": args.accounts,
                      "merchants": args.merchants, "transactions": args.transactions},
        "window": [str(C.WINDOW_START), str(C.WINDOW_END)],
        "rows": {"Customer": len(customers), "Account": len(accts), "Merchant": len(merchants),
                 "Transaction": len(events), "Fraud_Alert": 0, "Investigation": 0},
        "scenario_counts": count_by(events, lambda e: e["scen"]),
        "pattern_counts": {f"{s}/{pt}": n for (s, pt), n in count_by(events, lambda e: (e["scen"], e["pat"])).items()},
        "category_counts": count_by(events, lambda e: e["cat"]),
        "status_counts": count_by(events, lambda e: e["status"]),
        "pattern_shortfall": short,
        "sha256": {"seed_data.sql": sha(sql), "labels.csv": sha(labels), "opening_balances.csv": sha(balances),
                   "validate_seed_data.sql": sha(validate_sql)},
    }
    texts = {"sql": sql, "labels": labels, "balances": balances,
             "validate": validate_sql,
             "manifest": json.dumps(manifest, indent=2, sort_keys=True) + "\n"}
    for key, path in paths.items():
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", newline="\n", encoding="utf-8") as f:
            f.write(texts[key])
    print(f"wrote {len(customers)} customers, {len(accts)} accounts, {len(merchants)} merchants, "
          f"{len(events)} transactions; fraud={manifest['scenario_counts'].get('fraud', 0)} "
          f"legit_edge={manifest['scenario_counts'].get('legit_edge', 0)}; sql={len(sql)} bytes")
    if short:
        print(f"note: {short} pattern rows could not be placed (tiny configuration)")


if __name__ == "__main__":
    main()
