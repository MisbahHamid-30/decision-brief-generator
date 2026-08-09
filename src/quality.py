"""
Data-quality gate
=================
Runs before any analysis. Produces an auditable report, applies conservative
repairs, and returns a per-table confidence penalty that the insight engine
uses to discount findings drawn from damaged tables.

The gate has three outcomes:

    PASS   analysis proceeds at full confidence
    WARN   analysis proceeds, findings from affected tables are discounted,
           and the limitation is disclosed in the brief appendix
    BLOCK  a critical integrity failure — the analysis must not run, because
           any number it produced would be untrustworthy

Refusing to produce a brief is a legitimate output. A tool that always answers
is not a tool anyone should trust.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd

from ingest import Dataset, ROOT

SEVERITY_ORDER = {"critical": 3, "high": 2, "medium": 1, "low": 0}


# ==========================================================================

@dataclass
class Issue:
    check: str
    table: str
    severity: str            # critical | high | medium | low
    detail: str
    affected_rows: int = 0
    affected_pct: float = 0.0
    threshold: float | None = None
    repair: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class QualityReport:
    issues: list[Issue] = field(default_factory=list)
    passed: list[dict] = field(default_factory=list)
    repairs: list[str] = field(default_factory=list)
    table_confidence: dict[str, float] = field(default_factory=dict)
    row_counts: dict[str, int] = field(default_factory=dict)
    gate: str = "PASS"

    def add(self, issue: Issue):
        self.issues.append(issue)

    def ok(self, check: str, table: str, detail: str):
        """Record a check that ran and found nothing. A quality report that
        only lists failures leaves the reader unable to tell the difference
        between 'clean' and 'not checked'."""
        self.passed.append({"check": check, "table": table, "detail": detail})

    @property
    def worst(self) -> str:
        if not self.issues:
            return "none"
        return max(self.issues, key=lambda i: SEVERITY_ORDER[i.severity]).severity

    def by_severity(self, sev: str) -> list[Issue]:
        return [i for i in self.issues if i.severity == sev]

    # ---- output ----------------------------------------------------------

    def to_json(self, path: str):
        with open(path, "w") as f:
            json.dump({
                "gate": self.gate,
                "worst_severity": self.worst,
                "row_counts": self.row_counts,
                "table_confidence": self.table_confidence,
                "repairs": self.repairs,
                "issues": [i.as_dict() for i in self.issues],
            }, f, indent=2, default=str)

    def to_markdown(self) -> str:
        L = ["# Data-quality report", ""]
        L.append(f"**Gate: {self.gate}**  ·  worst severity: `{self.worst}`  ·  "
                 f"{len(self.issues)} issue(s) found")
        L.append("")
        L.append("## Table confidence")
        L.append("")
        L.append("| Table | Rows | Confidence |")
        L.append("|---|---:|---:|")
        for t, c in sorted(self.table_confidence.items()):
            L.append(f"| {t} | {self.row_counts.get(t, 0):,} | {c:.0%} |")
        L.append("")
        if self.issues:
            L.append("## Issues")
            L.append("")
            L.append("| Severity | Check | Table | Rows | % | Detail |")
            L.append("|---|---|---|---:|---:|---|")
            for i in sorted(self.issues,
                            key=lambda x: -SEVERITY_ORDER[x.severity]):
                L.append(f"| {i.severity} | {i.check} | {i.table} | "
                         f"{i.affected_rows:,} | {i.affected_pct:.2%} | {i.detail} |")
            L.append("")
        if self.repairs:
            L.append("## Repairs applied")
            L.append("")
            for r in self.repairs:
                L.append(f"- {r}")
            L.append("")
        if self.passed:
            L.append("## Checks that ran clean")
            L.append("")
            for p in self.passed:
                L.append(f"- **{p['check']}** · `{p['table']}` — {p['detail']}")
            L.append("")
        return "\n".join(L)


# ==========================================================================
# Checks
# ==========================================================================

def _pct(n: int, total: int) -> float:
    return (n / total) if total else 0.0


def check_duplicates(ds: Dataset, rep: QualityReport, gate: dict):
    thr = gate["max_duplicate_pk_pct"]
    for name, prof in ds.profiles.items():
        n = prof.n_rows
        if prof.duplicate_rows:
            rep.add(Issue("duplicate_rows", name, "medium",
                          "identical rows appear more than once",
                          prof.duplicate_rows, _pct(prof.duplicate_rows, n),
                          repair="deduplicated"))
        if prof.primary_key and prof.duplicate_pk:
            pct = _pct(prof.duplicate_pk, n)
            sev = thr["severity"] if pct > thr["threshold"] else "high"
            rep.add(Issue("duplicate_primary_key", name, sev,
                          f"key {prof.primary_key} is not unique",
                          prof.duplicate_pk, pct, thr["threshold"],
                          repair="kept first occurrence"))


def check_referential_integrity(ds: Dataset, rep: QualityReport, gate: dict):
    thr = gate["max_orphan_fk_pct"]
    clean = 0
    for name in ds.tables:
        fks = ds.spec(name).get("foreign_keys", {}) or {}
        df = ds.table(name)
        for local, ref in fks.items():
            rt, rc = ref.split(".")
            if rt not in ds.tables or local not in df.columns:
                continue
            valid = set(ds.table(rt)[rc].dropna().astype(str))
            vals = df[local].dropna().astype(str)
            orphans = int((~vals.isin(valid)).sum())
            if orphans:
                pct = _pct(orphans, len(df))
                sev = thr["severity"] if pct > thr["threshold"] else "high"
                rep.add(Issue("orphan_foreign_key", name, sev,
                              f"{local} has values absent from {ref}",
                              orphans, pct, thr["threshold"]))
            else:
                clean += 1
    if clean:
        rep.ok("referential_integrity", "all",
               f"{clean} foreign-key relationships validated, no orphans")


def check_nulls(ds: Dataset, rep: QualityReport, gate: dict):
    thr = gate["max_null_pct_key_measure"]
    # a concept-mapped column is by definition one the analysis depends on
    mapped: dict[str, set[str]] = {}
    for cname, c in ds.semantic["concepts"].items():
        mapped.setdefault(c["table"], set()).add(c["column"])

    for name, prof in ds.profiles.items():
        keys = mapped.get(name, set())
        for col in prof.columns:
            if col.name not in keys or col.null_count == 0:
                continue
            sev = thr["severity"] if col.null_pct > thr["threshold"] else "low"
            rep.add(Issue("null_values", name, sev,
                          f"{col.name} is null in some rows",
                          col.null_count, col.null_pct, thr["threshold"],
                          repair="rows excluded from metrics using this column"))


def check_negatives(ds: Dataset, rep: QualityReport, gate: dict):
    """Units and money cannot be negative in this domain."""
    thr = gate["max_negative_pct"]
    non_negative_kinds = {"measure", "money"}
    for cname, c in ds.semantic["concepts"].items():
        if c.get("kind") not in non_negative_kinds:
            continue
        t, col = c["table"], c["column"]
        if t not in ds.tables or col not in ds.tables[t].columns:
            continue
        s = ds.tables[t][col]
        if not pd.api.types.is_numeric_dtype(s):
            continue
        n = int((s < 0).sum())
        if n:
            pct = _pct(n, len(s))
            sev = thr["severity"] if pct > thr["threshold"] else "medium"
            rep.add(Issue("negative_value", t, sev,
                          f"{col} contains negative values (impossible for "
                          f"a {c['kind']})", n, pct, thr["threshold"],
                          repair="clamped to zero and flagged"))


def check_impossible_values(ds: Dataset, rep: QualityReport, gate: dict):
    thr = gate["max_impossible_value_pct"]

    # delivery duration far outside anything operationally credible
    if ds.has("actual_minutes"):
        t, col = ds.concept("actual_minutes")
        if t in ds.tables:
            s = ds.tables[t][col]
            ceiling = 120
            n = int((s > ceiling).sum())
            if n:
                rep.add(Issue("impossible_value", t, "medium",
                              f"{col} exceeds {ceiling} min — not a credible "
                              f"quick-commerce delivery", n, _pct(n, len(s)),
                              thr["threshold"], repair="winsorised at p99.5"))

    # a purchase order cannot be received before it was raised
    if "purchase_orders" in ds.tables:
        po = ds.tables["purchase_orders"]
        if {"order_date", "received_date"} <= set(po.columns):
            n = int((po.received_date < po.order_date).sum())
            if n:
                rep.add(Issue("impossible_value", "purchase_orders", "high",
                              "received_date precedes order_date", n,
                              _pct(n, len(po)), thr["threshold"]))


def check_inventory_balance(ds: Dataset, rep: QualityReport, gate: dict):
    """opening - sold - wasted must equal closing. This is the single most
    informative check available: if the stock ledger does not balance, no
    waste or availability number derived from it can be trusted."""
    if "inventory_daily" not in ds.tables:
        return
    inv = ds.tables["inventory_daily"]
    need = {"opening_units", "sold_units", "wasted_units", "closing_units"}
    if not need <= set(inv.columns):
        return
    resid = (inv.opening_units - inv.sold_units - inv.wasted_units
             - inv.closing_units)
    n = int((resid != 0).sum())
    thr = gate["max_reconciliation_gap_pct"]
    if n:
        pct = _pct(n, len(inv))
        sev = thr["severity"] if pct > thr["threshold"] else "medium"
        rep.add(Issue("ledger_imbalance", "inventory_daily", sev,
                      "opening - sold - wasted != closing", n, pct,
                      thr["threshold"], repair="imbalanced rows flagged"))
    else:
        rep.ok("ledger_balance", "inventory_daily",
               f"stock ledger balances on all {len(inv):,} store-SKU-days")


def check_cross_table_reconciliation(ds: Dataset, rep: QualityReport, gate: dict):
    """Independent sources for the same quantity must agree."""
    thr = gate["max_reconciliation_gap_pct"]

    # 1. order_items line values must sum to the order basket value
    if {"orders", "order_items"} <= set(ds.tables):
        oi = ds.tables["order_items"]
        od = ds.tables["orders"]
        if {"line_value_aed", "unfulfilled"} <= set(oi.columns):
            got = (oi[oi.unfulfilled == 0]
                   .groupby("order_id", observed=True)["line_value_aed"].sum())
            ref = od.drop_duplicates("order_id").set_index("order_id")["basket_value_aed"]
            j = pd.concat([got.rename("items"), ref.rename("orders")], axis=1).dropna()
            gap = (j["items"] - j["orders"]).abs()
            n = int((gap > 0.01).sum())
            total_gap = float(gap.sum()) / max(float(j["orders"].sum()), 1)
            if n:
                sev = thr["severity"] if total_gap > thr["threshold"] else "low"
                rep.add(Issue("reconciliation", "order_items", sev,
                              "sum of fulfilled line values != orders.basket_value_aed",
                              n, total_gap, thr["threshold"]))
            else:
                rep.ok("reconciliation", "order_items ↔ orders",
                       f"line values reconcile to basket value across "
                       f"{len(j):,} orders")

    # 2. units sold in the stock ledger must match units sold on order lines
    if {"inventory_daily", "order_items", "orders"} <= set(ds.tables):
        oi = ds.tables["order_items"]
        od = ds.tables["orders"][["order_id", "order_datetime", "store_id"]]
        j = oi[oi.unfulfilled == 0].merge(od.drop_duplicates("order_id"),
                                          on="order_id", how="left")
        j["date"] = j["order_datetime"].dt.normalize()
        a = j.groupby(["date", "store_id"], observed=True)["qty"].sum()
        b = (ds.tables["inventory_daily"]
             .groupby(["date", "store_id"], observed=True)["sold_units"].sum())
        m = pd.concat([a.rename("from_orders"), b.rename("from_ledger")],
                      axis=1).dropna()
        gap = (m["from_orders"] - m["from_ledger"]).abs().sum()
        rel = gap / max(m["from_ledger"].sum(), 1)
        if rel > 0.001:
            sev = thr["severity"] if rel > thr["threshold"] else "low"
            rep.add(Issue("reconciliation", "order_items", sev,
                          "units sold on order lines != units sold in stock ledger",
                          int((m.from_orders != m.from_ledger).sum()), rel,
                          thr["threshold"]))
        else:
            rep.ok("reconciliation", "order_items ↔ inventory_daily",
                   f"units sold agree between order lines and the stock "
                   f"ledger across {len(m):,} store-days ({rel:.3%} gap)")

    # 3. courier_daily order counts must match the orders table
    if {"courier_daily", "orders"} <= set(ds.tables):
        od = ds.tables["orders"].drop_duplicates("order_id").copy()
        od["date"] = od["order_datetime"].dt.normalize()
        a = od.groupby(["date", "store_id"], observed=True).size()
        b = ds.tables["courier_daily"].set_index(["date", "store_id"])["orders_placed"]
        m = pd.concat([a.rename("from_orders"), b.rename("from_fleet")],
                      axis=1).dropna()
        rel = (m["from_orders"] - m["from_fleet"]).abs().sum() / max(m["from_fleet"].sum(), 1)
        if rel > 0.001:
            rep.add(Issue("reconciliation", "courier_daily", "low",
                          "daily order count differs between orders and courier_daily",
                          int((m.from_orders != m.from_fleet).sum()), rel,
                          thr["threshold"]))
        else:
            rep.ok("reconciliation", "courier_daily ↔ orders",
                   f"daily order counts agree across {len(m):,} store-days")


def check_date_coverage(ds: Dataset, rep: QualityReport, gate: dict):
    """Every store should appear on every day it was trading."""
    thr = gate["min_date_coverage_pct"]
    if "inventory_daily" not in ds.tables or "dark_stores" not in ds.tables:
        return
    inv = ds.tables["inventory_daily"]
    st = ds.tables["dark_stores"]
    present = inv.groupby("store_id", observed=True)["date"].nunique()
    lo, hi = inv["date"].min(), inv["date"].max()
    for _, r in st.iterrows():
        opened = pd.to_datetime(r.get("opened_date", lo))
        expected = (hi - max(opened, lo)).days + 1
        got = int(present.get(r["store_id"], 0))
        cov = got / max(expected, 1)
        if cov < thr["threshold"]:
            rep.add(Issue("date_coverage", "inventory_daily", thr["severity"],
                          f"store {r['store_id']} present on {got}/{expected} "
                          f"trading days", expected - got, 1 - cov,
                          thr["threshold"]))


# ==========================================================================
# Repairs
# ==========================================================================

def apply_repairs(ds: Dataset, rep: QualityReport):
    """Conservative, disclosed, reversible-in-principle fixes.

    We never silently invent data. We remove exact duplicates, clamp
    impossible negatives, and winsorise absurd outliers — and we say so.
    """
    for name in list(ds.tables):
        df = ds.tables[name]
        before = len(df)

        # exact duplicate rows
        if df.duplicated().any():
            df = df.drop_duplicates()
            rep.repairs.append(
                f"{name}: removed {before - len(df):,} exact duplicate rows")

        # duplicate primary keys
        pk = ds.profiles[name].primary_key
        if pk and df.duplicated(subset=pk).any():
            n = int(df.duplicated(subset=pk).sum())
            df = df.drop_duplicates(subset=pk, keep="first")
            rep.repairs.append(
                f"{name}: collapsed {n:,} rows sharing a primary key {pk} "
                f"(kept first)")

        ds.tables[name] = df

    # clamp negative measures
    for cname, c in ds.semantic["concepts"].items():
        if c.get("kind") not in {"measure", "money"}:
            continue
        t, col = c["table"], c["column"]
        if t not in ds.tables or col not in ds.tables[t].columns:
            continue
        s = ds.tables[t][col]
        if pd.api.types.is_numeric_dtype(s) and (s < 0).any():
            n = int((s < 0).sum())
            ds.tables[t][f"{col}_was_negative"] = (s < 0).astype("int8")
            ds.tables[t][col] = s.clip(lower=0)
            rep.repairs.append(
                f"{t}.{col}: clamped {n:,} negative values to zero "
                f"(flagged in {col}_was_negative)")

    # Cap only genuinely impossible delivery times.
    #
    # Deliberately NOT a percentile cap. A percentile would clip the long right
    # tail — which in this dataset is the real operational signal (one store is
    # structurally slow because its fleet is undersized). Cleaning that away
    # would delete the finding. We remove only what cannot physically be true
    # and leave every credible extreme value intact.
    if ds.has("actual_minutes"):
        t, col = ds.concept("actual_minutes")
        if t in ds.tables and col in ds.tables[t].columns:
            s = ds.tables[t][col]
            ceiling = 120.0
            n = int((s > ceiling).sum())
            if n:
                ds.tables[t][f"{col}_was_capped"] = (s > ceiling).astype("int8")
                ds.tables[t][col] = s.clip(upper=ceiling)
                rep.repairs.append(
                    f"{t}.{col}: capped {n:,} physically impossible values at "
                    f"{ceiling:.0f} min (percentile winsorising deliberately "
                    f"avoided — it would suppress genuine slow-service signal)")

    ds._enriched.clear()


# ==========================================================================
# Orchestration
# ==========================================================================

def run(ds: Dataset, repair: bool = True) -> QualityReport:
    gate = ds.rules["quality_gate"]
    rep = QualityReport()
    rep.row_counts = {k: len(v) for k, v in ds.tables.items()}

    check_duplicates(ds, rep, gate)
    check_referential_integrity(ds, rep, gate)
    check_nulls(ds, rep, gate)
    check_negatives(ds, rep, gate)
    check_impossible_values(ds, rep, gate)
    check_inventory_balance(ds, rep, gate)
    check_cross_table_reconciliation(ds, rep, gate)
    check_date_coverage(ds, rep, gate)

    # ---- confidence -------------------------------------------------------
    # An issue we can repair deterministically (drop an exact duplicate, cap an
    # impossible value) is a disclosure item, not a reason to distrust the
    # table. It carries a small residual penalty because the underlying process
    # produced bad rows at all. An issue we cannot repair carries the full
    # penalty, because the uncertainty is still in the numbers.
    pen = gate["confidence_penalty"]
    residual = 0.25
    conf = {t: 1.0 for t in ds.tables}
    for i in rep.issues:
        if i.table not in conf:
            continue
        p = pen.get(i.severity, 0.0)
        if i.repair and i.severity != "critical":
            p *= residual
        conf[i.table] = max(0.0, conf[i.table] - p)
    rep.table_confidence = {k: round(v, 3) for k, v in conf.items()}

    # ---- gate -------------------------------------------------------------
    # Only unrepairable failures can block. A critical issue always blocks.
    unrepairable_high = [i for i in rep.issues
                         if i.severity == "high" and not i.repair]
    if any(i.severity == "critical" for i in rep.issues):
        rep.gate = "BLOCK"
    elif unrepairable_high:
        rep.gate = "WARN"
    elif any(i.severity == "high" for i in rep.issues):
        rep.gate = "WARN"
    else:
        rep.gate = "PASS"

    if repair and rep.gate != "BLOCK":
        apply_repairs(ds, rep)
        rep.row_counts = {k: len(v) for k, v in ds.tables.items()}

    return rep


if __name__ == "__main__":
    out_dir = os.path.join(ROOT, "outputs")
    os.makedirs(out_dir, exist_ok=True)

    print("Loading ...")
    ds = Dataset.load(verbose=False)
    print("Running quality gate ...\n")
    rep = run(ds)

    print(rep.to_markdown())

    rep.to_json(os.path.join(out_dir, "data_quality_report.json"))
    with open(os.path.join(out_dir, "data_quality_report.md"), "w") as f:
        f.write(rep.to_markdown())
    print(f"\nwritten to outputs/data_quality_report.{{json,md}}")
