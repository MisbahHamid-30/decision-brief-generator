"""
Generic KPI machinery
=====================
Everything a KPI engine needs that has nothing to do with any particular
business: period arithmetic, annualisation, currency, data-quality confidence,
and — the two that mattered most — a **config-driven scorecard and waterfall**.

Why this file exists
--------------------
The first version of this project claimed the pipeline was domain-agnostic
except for the detectors. Testing that claim against a second, genuinely
different dataset showed it was false: the KPI engine named
`inventory_daily`, `purchase_orders` and `courier_daily` directly, and the
scorecard and margin waterfall were hardcoded lists of supply-chain metrics.

A domain engine now supplies one thing — a `network` dict of metric keys — and
everything generic is derived from it plus configuration. What each domain must
still write is its own metrics and its own detectors, which is the irreducible
part: "fill rate" means nothing to a ride-hailing marketplace, and "unfulfilled
request rate" means nothing to a warehouse.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DAYS_PER_YEAR = 365.0


class BaseKPI:
    """Domain-independent half of a KPI engine.

    Subclasses must:
      * call `super().__init__(ds, quality_report)`
      * set `self._date_series` to the primary fact table's date column
        (or call `_set_period_from`)
      * implement the `network` property, returning a flat dict of metrics
    """

    def __init__(self, ds, quality_report=None):
        self.ds = ds
        self.rules = ds.rules
        self.q = quality_report
        self.costs = self.rules.get("costs", {})
        self.targets = self.rules.get("targets", {})
        self.dq = (quality_report.table_confidence if quality_report is not None
                   else {t: 1.0 for t in ds.tables})
        self.date_min = None
        self.date_max = None
        self.n_days = 1
        self.annualise = 1.0

    # ---- period ----------------------------------------------------------

    def _set_period_from(self, dates: pd.Series):
        self.date_min, self.date_max = dates.min(), dates.max()
        self.n_days = int((self.date_max - self.date_min).days) + 1
        self.annualise = DAYS_PER_YEAR / max(self.n_days, 1)

    @property
    def period(self) -> tuple[str, str]:
        return str(self.date_min.date()), str(self.date_max.date())

    # ---- money -----------------------------------------------------------

    def annualised(self, period_value: float) -> float:
        """Scale a value observed over the data period to a yearly figure.

        Not for annually recurring events — one occurrence of those already is
        the annual figure, and scaling it understates the finding.
        """
        return float(period_value * self.annualise)

    def to_usd(self, aed: float) -> float:
        return aed / self.ds.semantic["dataset"]["fx"]["USD"]

    # ---- confidence ------------------------------------------------------

    def table_confidence(self, *tables: str) -> float:
        return min([self.dq.get(t, 1.0) for t in tables] or [1.0])

    # ---- aggregation helper ---------------------------------------------

    @staticmethod
    def agg(df: pd.DataFrame, by, fn) -> pd.DataFrame:
        return (df.groupby(by, observed=True)
                  .apply(fn, include_groups=False)
                  .reset_index())

    # ---- config-driven scorecard ----------------------------------------

    def scorecard(self) -> pd.DataFrame:
        """Build the scorecard from `business_rules.yaml`.

        Each entry names a metric key from `self.network` and a target key from
        `targets`. No metric names appear in this file, which is what makes it
        reusable.
        """
        spec = self.rules.get("scorecard", [])
        n = self.network
        rows = []
        for s in spec:
            actual = n.get(s["metric"])
            if actual is None:
                continue
            tgt = self.targets.get(s.get("target", s["metric"]), {})
            target = tgt.get("target")
            if target is None:
                continue
            rows.append({
                "kpi": s["label"],
                "actual": float(actual) * float(s.get("scale", 1.0)),
                "target": float(target),
                "direction": tgt.get("direction", "higher_better"),
                "fmt": s.get("fmt", "num"),
            })
        df = pd.DataFrame(rows)
        if df.empty:
            return df

        def status(r):
            if r.direction == "higher_better":
                return "on_target" if r.actual >= r.target else "below"
            if r.direction == "lower_better":
                return "on_target" if r.actual <= r.target else "above"
            return "on_target" if abs(r.actual - r.target) < 0.1 else "off_band"

        df["status"] = df.apply(status, axis=1)
        df["gap"] = df.actual - df.target
        return df

    # ---- config-driven value waterfall ----------------------------------

    def margin_waterfall(self) -> pd.DataFrame:
        """Build the value waterfall from `business_rules.yaml`.

        Starts from a base metric and subtracts each declared item. Works for
        any domain that can name a top-line value and the things eroding it.
        """
        spec = self.rules.get("waterfall")
        n = self.network
        if not spec:
            return pd.DataFrame(columns=["item", "aed", "kind", "aed_annualised"])

        rows = []
        base = spec["base"]
        base_val = float(n.get(base["metric"], 0.0))
        rows.append((base["label"], base_val, "positive"))

        for item in spec.get("items", []):
            v = n.get(item["metric"])
            if v is None:
                continue
            rows.append((item["label"], -abs(float(v)), item.get("kind", "leak")))

        df = pd.DataFrame(rows, columns=["item", "aed", "kind"])
        df["aed_annualised"] = df.aed * (
            1.0 if spec.get("already_annual") else self.annualise)
        total = df.aed.sum()
        df.loc[len(df)] = [spec.get("net_label", "Net contribution"), total, "net",
                           total * (1.0 if spec.get("already_annual") else self.annualise)]
        return df

    # ---- interface -------------------------------------------------------

    @property
    def network(self) -> dict:
        raise NotImplementedError(
            "A domain KPI engine must expose a flat dict of network metrics")
