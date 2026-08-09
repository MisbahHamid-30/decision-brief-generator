"""
Detectors — where findings come from
====================================
Each detector interrogates the KPI set for one class of problem and returns
Finding objects carrying their own evidence, method and confidence.

Two rules govern everything here:

1. A detector may only claim what it can evidence. Every Finding carries the
   numbers that produced it and the technique that derived them.

2. A detector must be willing to find nothing. Returning an empty list is a
   valid and frequent outcome. Tools that always find five problems are
   pattern-matching on the shape of a report, not on the data.

The hardest case in this module is `detect_fleet_constraint`, which exists to
prevent a specific mistake: a store with bad service and good inventory does
not have an inventory problem, however much the symptom resembles one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from findings import (Finding, Evidence, statistical_confidence,
                      sample_confidence, combine_confidence, describe_confidence)


# ==========================================================================
# helpers
# ==========================================================================

def _fid(prefix: str, n: int) -> str:
    return f"{prefix}-{n:02d}"


def changepoint(series: pd.Series, min_seg: int = 3):
    """Binary-segmentation changepoint on a short series.

    Scans every admissible split, returns the one maximising the Welch t
    statistic between the two segments. Returns (index, t, p) or None.
    Deliberately simple: on a 12-24 point monthly series, anything more
    elaborate would be fitting noise.
    """
    s = series.dropna()
    if len(s) < 2 * min_seg:
        return None
    best = None
    for i in range(min_seg, len(s) - min_seg + 1):
        a, b = s.iloc[:i], s.iloc[i:]
        if a.std() == 0 and b.std() == 0:
            continue
        t, p = stats.ttest_ind(a, b, equal_var=False)
        if best is None or abs(t) > abs(best[1]):
            best = (i, float(t), float(p))
    return best


def proportion_test(x1: float, n1: int, x2: float, n2: int):
    """Two-proportion z-test. Returns (z, p)."""
    if min(n1, n2) == 0:
        return 0.0, 1.0
    p1, p2 = x1 / n1, x2 / n2
    p = (x1 + x2) / (n1 + n2)
    se = np.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 1.0
    z = (p1 - p2) / se
    return float(z), float(2 * (1 - stats.norm.cdf(abs(z))))


# ==========================================================================
# 1. Service / availability
# ==========================================================================

def detect_service_gap(ds, k, rules) -> list[Finding]:
    t = rules["targets"]["fill_rate"]
    n = k.network
    actual, target = n["fill_rate"], t["target"]
    if actual >= target:
        return []

    # The share of lost demand that hitting target would recover.
    recoverable_share = (target - actual) / (1 - actual)
    lost_margin = n["lost_margin_aed"] * recoverable_share
    magnitude = k.annualised(k.stockout_cost(lost_margin))

    demand_units = k.inv.demand_units.sum()
    dq = k.table_confidence("inventory_daily", "skus")
    st = statistical_confidence(p_value=0.0)          # a gap this size is not noise
    sm = sample_confidence(int(demand_units), 10000)

    worst = (k.by_store_category
             .assign(gap=lambda d: target - d.fill_rate)
             .query("gap > 0 and lost_margin_aed > 0")
             .nlargest(8, "lost_margin_aed"))

    f = Finding(
        id=_fid("SVC", 1),
        headline=(f"Network fill rate is {actual:.1%} against a {target:.0%} target — "
                  f"closing the gap is worth AED {magnitude/1e6:.2f}m a year"),
        category="service",
        direction="leak",
        entity_type="network",
        entities=["network"],
        magnitude_aed=magnitude,
        magnitude_basis=(
            f"Lost margin over the period was AED {n['lost_margin_aed']:,.0f}. "
            f"{recoverable_share:.0%} of that is attributable to running below the "
            f"{target:.0%} target. Multiplied by the declared stockout penalty of "
            f"{k.costs['stockout_margin_multiplier']} and annualised "
            f"(x{k.annualise:.3f})."),
        magnitude_low=k.annualised(lost_margin),                 # margin only
        magnitude_high=k.annualised(k.stockout_cost(n["lost_margin_aed"])),
        evidence=[
            Evidence("Fill rate", actual, "", f"target {target:.0%}",
                     "inventory_daily", int(demand_units)),
            Evidence("Units of demand unserved", int(n["units_lost"]), "units",
                     None, "inventory_daily"),
            Evidence("Store-SKU-days with a stockout", n["stockout_day_rate"],
                     "", "share of all store-SKU-days", "inventory_daily",
                     len(k.inv)),
            Evidence("Worst store-category",
                     f"{worst.iloc[0].store_name} / {worst.iloc[0].category}",
                     "", f"fill {worst.iloc[0].fill_rate:.1%}", "inventory_daily"),
        ],
        method="Fill rate vs declared target; recoverable share of lost margin",
        confidence=combine_confidence(st, sm, dq),
        confidence_basis=describe_confidence(st, sm, dq, int(demand_units),
                                             "deterministic aggregation"),
        period=(n["period_start"], n["period_end"]),
        tags=["fill_rate", "availability"],
        detail={"worst_store_category": worst.to_dict("records")},
    )
    return [f]


# ==========================================================================
# 2. Supplier reliability
# ==========================================================================

def detect_supplier_reliability(ds, k, rules) -> list[Finding]:
    out: list[Finding] = []
    t_otif = rules["targets"]["otif"]
    t_cv = rules["targets"]["supplier_lead_time_cv"]
    sup = k.by_supplier.copy()
    peer_cv = sup.lead_time_cv.median()
    dq = k.table_confidence("purchase_orders", "suppliers")
    idx = 0

    for _, s in sup.iterrows():
        breaches = []
        if s.otif < t_otif["floor"]:
            breaches.append("otif")
        if s.lead_time_cv > t_cv["ceiling"]:
            breaches.append("variability")
        if not breaches:
            continue
        idx += 1

        # did this degrade, or has it always been like this?
        ms = (k.supplier_monthly[k.supplier_monthly.supplier_id == s.supplier_id]
              .sort_values("month"))
        cp = changepoint(ms.set_index("month")["lead_time_mean"])
        cp_text, cp_month, p_val = "", None, None
        if cp:
            i, tstat, p_val = cp
            cp_month = ms.iloc[i]["month"]
            before = ms.iloc[:i].lead_time_mean.mean()
            after = ms.iloc[i:].lead_time_mean.mean()
            sd_b = ms.iloc[:i].lead_time_sd.mean()
            sd_a = ms.iloc[i:].lead_time_sd.mean()
            if p_val < 0.05 and after > before:
                cp_text = (f" Performance changed in {cp_month}: lead time moved from "
                           f"{before:.2f} to {after:.2f} days and its standard deviation "
                           f"from {sd_b:.2f} to {sd_a:.2f}.")

        # money: short-shipment cost, plus lost margin in this supplier's
        # categories over and above the network baseline
        short_cost = k.annualised(s.short_cost_aed)
        cats = ds.table("skus").query("supplier_id == @s.supplier_id")["category"].unique()
        affected = k.inv[k.inv.category.isin(cats)]
        others = k.inv[~k.inv.category.isin(cats)]
        fr_a = affected.sold_units.sum() / max(
            affected.sold_units.sum() + affected.lost_units.sum(), 1)
        fr_o = others.sold_units.sum() / max(
            others.sold_units.sum() + others.lost_units.sum(), 1)
        excess_margin = 0.0
        if fr_a < fr_o and affected.lost_units.sum() > 0:
            excess_share = (fr_o - fr_a) / max(1 - fr_a, 1e-9)
            excess_margin = affected.lost_margin_aed.sum() * excess_share
        attributable = k.annualised(k.stockout_cost(excess_margin))
        magnitude = short_cost + attributable

        st = statistical_confidence(p_value=p_val if p_val is not None else 0.01)
        sm = sample_confidence(int(s.po_lines), 500)

        out.append(Finding(
            id=_fid("SUP", idx),
            headline=(f"{s.supplier_name} is the network's least reliable supplier — "
                      f"OTIF {s.otif:.0%} against a {t_otif['target']:.0%} target, "
                      f"costing about AED {magnitude/1e3:.0f}k a year"),
            category="procurement",
            direction="leak",
            entity_type="supplier",
            entities=[s.supplier_id],
            magnitude_aed=magnitude,
            magnitude_basis=(
                f"Short-shipment cost AED {s.short_cost_aed:,.0f} over the period "
                f"(annualised AED {short_cost:,.0f}), plus AED {attributable:,.0f} of "
                f"annualised lost margin in {', '.join(cats)} attributable to this "
                f"supplier's categories running {fr_o - fr_a:.1%} below the fill rate "
                f"of categories it does not supply."),
            magnitude_low=short_cost,
            magnitude_high=magnitude * 1.3,
            evidence=[
                Evidence("OTIF", s.otif, "", f"target {t_otif['target']:.0%}",
                         "purchase_orders", int(s.po_lines)),
                Evidence("On-time rate", s.on_time_rate, "", None, "purchase_orders"),
                Evidence("In-full rate", s.in_full_rate, "", None, "purchase_orders"),
                Evidence("Lead time", s.lead_time_mean, "days",
                         f"promised {s.promised_lead:.0f}", "purchase_orders"),
                Evidence("Lead-time variability (CV)", s.lead_time_cv, "",
                         f"peer median {peer_cv:.2f}", "purchase_orders"),
                Evidence("Units short-shipped", int(s.short_units), "units",
                         None, "purchase_orders"),
            ],
            method=("OTIF and lead-time CV against target; binary-segmentation "
                    "changepoint on the monthly lead-time series"),
            confidence=combine_confidence(st, sm, dq),
            confidence_basis=describe_confidence(st, sm, dq, int(s.po_lines),
                                                 "Welch t-test changepoint"),
            period=(k.network["period_start"], k.network["period_end"]),
            tags=["supplier", "otif"] + breaches,
            detail={
                "changepoint_month": cp_month,
                "changepoint_p": p_val,
                "narrative": cp_text.strip(),
                "categories": list(cats),
                "monthly": ms.to_dict("records"),
            },
        ))
    return out


# ==========================================================================
# 3. Waste concentration
# ==========================================================================

def detect_waste_concentration(ds, k, rules) -> list[Finding]:
    """Find where write-off concentrates, at the coarsest grain that still
    explains it.

    Reporting the same problem once per store is how a brief ends up with
    fifteen findings that are really one finding. If every store in a market
    shows the same category excess, the cause is upstream of any of them —
    so the finding is raised at market level with the stores as detail.
    """
    out: list[Finding] = []
    t = rules["targets"]["waste_rate"]
    skus = ds.table("skus")
    dq = k.table_confidence("inventory_daily", "skus")
    cat_norm = k.by_category.set_index("category")["waste_rate"].to_dict()

    def unit_cost(row):
        return (row.waste_cost_aed / row.units_wasted) if row.units_wasted else 0.0

    def case_pack_diagnostic(mask) -> tuple[float, float, float]:
        """How much of the write-off sits on lines where one case pack is more
        stock than the shelf life can absorb.

        Weighted by wasted units, not averaged across SKUs. An unweighted mean
        lets a long tail of fast-moving lines with sane pack sizes drown out
        the handful of slow lines actually generating the write-off — which is
        precisely the population the question is about.
        """
        sub = k.inv[mask]
        g = sub.groupby("sku_id", observed=True).agg(
            vel=("sold_units", "mean"), wasted=("wasted_units", "sum"))
        meta = skus.set_index("sku_id")
        common = g.index.intersection(meta.index)
        if len(common) == 0:
            return 0.0, np.nan, np.nan
        g = g.loc[common]
        dpc = meta.loc[common, "case_pack"] / g.vel.replace(0, np.nan)
        shelf = meta.loc[common, "shelf_life_days"]
        structural = (dpc / shelf) > 0.6
        w = g.wasted
        share = float(w[structural].sum() / w.sum()) if w.sum() else 0.0
        return (share,
                float(dpc[structural].median()) if structural.any() else float(dpc.median()),
                float(shelf[structural].median()) if structural.any() else float(shelf.median()))

    # ---- market x category ------------------------------------------------
    cc = k.by_city_category.copy()
    cc = cc[cc.units_received > 1000]
    cc["cat_norm"] = cc.category.map(cat_norm)
    cc["excess_rate"] = cc.waste_rate - cc.cat_norm
    cc["unit_cost"] = cc.apply(unit_cost, axis=1)
    cc["excess_cost"] = cc.excess_rate * cc.units_received * cc.unit_cost
    flagged_cc = cc[(cc.waste_rate > t["ceiling"]) &
                    (cc.waste_rate > 2 * cc.cat_norm) &
                    (cc.excess_cost > 0)].nlargest(4, "excess_cost")

    covered: set[tuple] = set()
    idx = 0

    for _, r in flagged_cc.iterrows():
        stores = k.by_store_category[
            (k.by_store_category.city == r.city) &
            (k.by_store_category.category == r.category)].copy()
        stores["cat_norm"] = r.cat_norm
        n_affected = int((stores.waste_rate > 2 * r.cat_norm).sum())
        if n_affected < 2 and len(stores) > 1:
            continue                      # a single-store problem, handle below
        idx += 1
        for s in stores.store_id:
            covered.add((s, r.category))

        mask = (k.inv.city == r.city) & (k.inv.category == r.category)
        structural, med_dpc, med_shelf = case_pack_diagnostic(mask)
        magnitude = k.annualised(float(r.excess_cost))
        z, p = proportion_test(r.units_wasted, r.units_received,
                               r.cat_norm * r.units_received, r.units_received)
        st = statistical_confidence(p_value=p)
        sm = sample_confidence(int(r.units_received), 2000)
        cause = ("procurement lot size" if structural > 0.4
                 else "ordering discipline or demand volatility")

        out.append(Finding(
            id=_fid("WST", idx),
            headline=(f"{r.city} writes off {r.waste_rate:.1%} of {r.category} against "
                      f"a network norm of {r.cat_norm:.1%} — AED {magnitude/1e3:.0f}k a "
                      f"year, and it is a lot-size problem, not a store problem"
                      if structural > 0.4 else
                      f"{r.city} writes off {r.waste_rate:.1%} of {r.category} against "
                      f"a network norm of {r.cat_norm:.1%} — AED {magnitude/1e3:.0f}k "
                      f"a year of avoidable write-off"),
            category="waste",
            direction="leak",
            entity_type="market_category",
            entities=[r.city, r.category],
            magnitude_aed=magnitude,
            magnitude_basis=(
                f"Excess waste rate of {r.excess_rate:.1%} over the network category "
                f"norm, applied to {int(r.units_received):,} units received at an "
                f"average unit cost of AED {r.unit_cost:.2f}, annualised."),
            magnitude_low=magnitude * 0.7,
            magnitude_high=k.annualised(float(r.waste_cost_aed)),
            evidence=[
                Evidence("Waste rate", r.waste_rate, "",
                         f"network norm {r.cat_norm:.1%}", "inventory_daily",
                         int(r.units_received)),
                Evidence("Units written off", int(r.units_wasted), "units",
                         None, "inventory_daily"),
                Evidence("Write-off value", r.waste_cost_aed, "AED", None,
                         "inventory_daily"),
                Evidence("Stores showing the same excess", n_affected, "",
                         f"of {len(stores)} in market", "inventory_daily"),
                Evidence("Range where one case exceeds 60% of shelf life",
                         structural, "",
                         f"median {med_dpc:.1f} days per case vs "
                         f"{med_shelf:.0f}-day shelf life", "skus"),
            ],
            method=("Market-category waste rate vs network norm, two-proportion "
                    "z-test; case-pack-to-velocity diagnostic against shelf life. "
                    "Raised at market level because the excess appears in "
                    f"{n_affected} of {len(stores)} stores, which rules out a "
                    "single-site execution cause."),
            confidence=combine_confidence(st, sm, dq),
            confidence_basis=describe_confidence(st, sm, dq, int(r.units_received),
                                                 "two-proportion z-test"),
            period=(k.network["period_start"], k.network["period_end"]),
            tags=["waste", "shrink", cause.replace(" ", "_")],
            detail={"structural_share": structural, "diagnosis": cause,
                    "median_days_per_case": med_dpc, "median_shelf_life": med_shelf,
                    "stores": stores[["store_name", "waste_rate", "units_received",
                                      "waste_cost_aed"]].to_dict("records")},
        ))

    # ---- single-store outliers not already explained -----------------------
    sc = k.by_store_category.copy()
    sc = sc[sc.units_received > 500]
    sc["cat_norm"] = sc.category.map(cat_norm)
    sc["excess_rate"] = sc.waste_rate - sc.cat_norm
    sc["unit_cost"] = sc.apply(unit_cost, axis=1)
    sc["excess_cost"] = sc.excess_rate * sc.units_received * sc.unit_cost
    sc = sc[~sc.apply(lambda r: (r.store_id, r.category) in covered, axis=1)]
    flagged = sc[(sc.waste_rate > t["ceiling"]) &
                 (sc.waste_rate > 2 * sc.cat_norm) &
                 (sc.excess_cost > 0)].nlargest(3, "excess_cost")

    for _, r in flagged.iterrows():
        idx += 1
        mask = (k.inv.store_id == r.store_id) & (k.inv.category == r.category)
        structural, med_dpc, med_shelf = case_pack_diagnostic(mask)
        magnitude = k.annualised(float(r.excess_cost))
        z, p = proportion_test(r.units_wasted, r.units_received,
                               r.cat_norm * r.units_received, r.units_received)
        st = statistical_confidence(p_value=p)
        sm = sample_confidence(int(r.units_received), 2000)
        cause = ("procurement lot size" if structural > 0.4
                 else "ordering discipline or demand volatility")

        out.append(Finding(
            id=_fid("WST", idx),
            headline=(f"{r.store_name} wastes {r.waste_rate:.1%} of {r.category} "
                      f"against a network norm of {r.cat_norm:.1%} — this store "
                      f"alone, AED {magnitude/1e3:.0f}k a year"),
            category="waste",
            direction="leak",
            entity_type="store_category",
            entities=[r.store_id, r.category],
            magnitude_aed=magnitude,
            magnitude_basis=(
                f"Excess waste rate of {r.excess_rate:.1%} over the network category "
                f"norm on {int(r.units_received):,} units received, annualised."),
            magnitude_low=magnitude * 0.7,
            magnitude_high=k.annualised(float(r.waste_cost_aed)),
            evidence=[
                Evidence("Waste rate", r.waste_rate, "",
                         f"network norm {r.cat_norm:.1%}", "inventory_daily",
                         int(r.units_received)),
                Evidence("Units written off", int(r.units_wasted), "units",
                         None, "inventory_daily"),
                Evidence("Write-off value", r.waste_cost_aed, "AED", None,
                         "inventory_daily"),
                Evidence("Range where one case exceeds 60% of shelf life",
                         structural, "", None, "skus"),
            ],
            method=("Store-category waste rate vs network norm, two-proportion "
                    "z-test; isolated to this site after ruling out a "
                    "market-wide pattern"),
            confidence=combine_confidence(st, sm, dq),
            confidence_basis=describe_confidence(st, sm, dq, int(r.units_received),
                                                 "two-proportion z-test"),
            period=(k.network["period_start"], k.network["period_end"]),
            tags=["waste", "shrink", "site_specific", cause.replace(" ", "_")],
            detail={"structural_share": structural, "diagnosis": cause,
                    "median_days_per_case": med_dpc, "median_shelf_life": med_shelf},
        ))
    return out


# ==========================================================================
# 3b. Lot size as a network-wide policy problem
# ==========================================================================

def detect_lot_size_policy(ds, k, rules) -> list[Finding]:
    """Aggregate the case-pack problem across the whole network.

    Individually, one market's dairy write-off is too small to reach an
    executive. But if the same mechanism — a minimum order quantity larger
    than the shelf life can absorb at local velocity — is producing write-off
    everywhere, that is one policy decision with one owner, and it is worth
    reporting as such. Splitting it by site would bury it under the
    materiality floor.
    """
    skus = ds.table("skus").set_index("sku_id")

    g = (k.inv.groupby(["store_id", "sku_id"], observed=True)
         .agg(vel=("sold_units", "mean"),
              wasted=("wasted_units", "sum"),
              waste_cost=("waste_cost_aed", "sum"),
              received=("received_units", "sum"))
         .reset_index())
    g = g[g.received > 0]
    if g.empty:
        return []

    g["case_pack"] = g.sku_id.map(skus.case_pack)
    g["shelf_life"] = g.sku_id.map(skus.shelf_life_days)
    g["supplier_id"] = g.sku_id.map(skus.supplier_id)
    g["days_per_case"] = g.case_pack / g.vel.replace(0, np.nan)
    g["cover_ratio"] = g.days_per_case / g.shelf_life

    # Two conditions, and the second matters as much as the first.
    #
    # (1) One case pack contains more days of stock than the product's entire
    #     shelf life. On those lines part of every delivery is guaranteed to
    #     expire unsold, however well the store is run.
    #
    # (2) The line still sells at a viable rate. Without this, the test drags
    #     in near-dead SKUs whose problem is that they are ranged at all — a
    #     delisting decision, not a pack-size decision. Those belong to the
    #     assortment finding, and counting them here would claim the same
    #     money twice under two different recommendations with two different
    #     owners.
    MIN_VELOCITY = 0.5              # units/day
    structural = g[(g.cover_ratio > 1.0) & (g.vel >= MIN_VELOCITY)]
    if structural.empty:
        return []

    waste_cost = float(structural.waste_cost.sum())
    share = waste_cost / max(float(g.waste_cost.sum()), 1e-9)
    if share < 0.10:
        return []

    # Recoverable: halving the pack on these lines brings cover back inside
    # shelf life for most. Assume 60% of the write-off is addressable — the
    # rest is demand volatility that a smaller pack would not have caught.
    magnitude = k.annualised(waste_cost * 0.60)

    by_sup = (structural.groupby("supplier_id", observed=True)
              .agg(waste_cost=("waste_cost", "sum"), lines=("sku_id", "nunique"))
              .sort_values("waste_cost", ascending=False))
    top_sup = by_sup.index[0]
    sup_name = ds.table("suppliers").set_index("supplier_id").loc[top_sup, "supplier_name"]

    dq = k.table_confidence("inventory_daily", "skus", "suppliers")
    st = statistical_confidence(p_value=0.0)
    sm = sample_confidence(len(structural), 200)

    return [Finding(
        id=_fid("LOT", 1),
        headline=(f"{len(structural):,} store-SKU lines have a case pack holding more "
                  f"days of stock than the product's own shelf life — {share:.0%} of "
                  f"network write-off, AED {magnitude/1e3:.0f}k a year that no store "
                  f"can prevent by ordering better"),
        category="procurement",
        direction="leak",
        entity_type="network",
        entities=[top_sup],
        magnitude_aed=magnitude,
        magnitude_basis=(
            f"AED {waste_cost:,.0f} of write-off over the period sits on lines where "
            f"one case pack exceeds the full shelf life at observed velocity. 60% of "
            f"that is treated as addressable by re-specifying pack size; the balance "
            f"is demand volatility a smaller pack would not have caught. Annualised."),
        magnitude_low=k.annualised(waste_cost * 0.35),
        magnitude_high=k.annualised(waste_cost * 0.85),
        evidence=[
            Evidence("Store-SKU lines affected", len(structural), "",
                     f"of {len(g):,} stocked lines, all selling at or above "
                     f"{MIN_VELOCITY} units/day", "inventory_daily"),
            Evidence("Share of network write-off", share, "", None,
                     "inventory_daily"),
            Evidence("Categories affected",
                     ", ".join(structural.sku_id.map(skus.category)
                               .value_counts().head(4).index), "",
                     "all short shelf life", "skus"),
            Evidence("Median days of cover per case",
                     float(structural.days_per_case.median()), "days",
                     f"median shelf life {structural.shelf_life.median():.0f} days",
                     "skus"),
            Evidence("Largest contributing supplier", sup_name, "",
                     f"AED {by_sup.iloc[0].waste_cost:,.0f} of write-off across "
                     f"{int(by_sup.iloc[0].lines)} lines", "suppliers"),
            Evidence("Write-off value on affected lines", waste_cost, "AED",
                     None, "inventory_daily"),
        ],
        method=("Case pack divided by observed daily velocity, compared against "
                "shelf life, at store-SKU grain; write-off attributed to lines "
                "where a single minimum lot cannot be sold within its own shelf "
                f"life AND the line still turns at least {MIN_VELOCITY} units/day. "
                "The velocity floor keeps this separate from the assortment "
                "finding, so the same write-off is not claimed twice"),
        confidence=combine_confidence(st, sm, dq),
        confidence_basis=describe_confidence(st, sm, dq, len(structural),
                                             "deterministic ratio test"),
        period=(k.network["period_start"], k.network["period_end"]),
        tags=["waste", "procurement", "moq", "case_pack"],
        detail={
            "by_supplier": by_sup.reset_index().to_dict("records"),
            "worst_lines": structural.nlargest(25, "waste_cost")[
                ["store_id", "sku_id", "case_pack", "shelf_life", "vel",
                 "days_per_case", "waste_cost"]].to_dict("records"),
        },
    )]


# ==========================================================================
# 4. Long tail / assortment
# ==========================================================================

def detect_long_tail(ds, k, rules) -> list[Finding]:
    sku = k.by_sku.sort_values("revenue_aed", ascending=False).copy()
    if sku.empty:
        return []
    sku["cum_rev_share"] = sku.revenue_aed.cumsum() / sku.revenue_aed.sum()

    # tail = SKUs beyond the point where 95% of revenue is already accounted for
    tail = sku[sku.cum_rev_share > 0.95]
    if len(tail) < 5:
        return []

    tail_ids = set(tail.sku_id)
    assort = ds.table("assortment")
    tail_slots = int(assort[assort.sku_id.isin(tail_ids)].shape[0])
    total_slots = len(assort)
    tail_rev_share = float(tail.revenue_aed.sum() / sku.revenue_aed.sum())
    tail_waste_share = float(tail.waste_cost_aed.sum() / max(sku.waste_cost_aed.sum(), 1))
    tail_slot_share = tail_slots / total_slots

    slot_cost = k.slot_cost_annual(tail_slots)
    waste_cost = k.annualised(float(tail.waste_cost_aed.sum()))
    tail_margin = k.annualised(float(tail.margin_aed.sum()))
    # Freeing a slot does not delete the demand — assume a conservative share
    # of tail margin is lost on delisting and net it off.
    recoverable = slot_cost + waste_cost - tail_margin * 0.5
    magnitude = max(recoverable, 0.0)

    dq = k.table_confidence("inventory_daily", "skus", "assortment")
    st = statistical_confidence(p_value=0.0)
    sm = sample_confidence(len(sku), 100)

    return [Finding(
        id=_fid("AST", 1),
        headline=(f"The slowest {len(tail)} of {len(sku)} SKUs earn {tail_rev_share:.1%} "
                  f"of revenue but occupy {tail_slot_share:.0%} of shelf slots and "
                  f"account for {tail_waste_share:.0%} of write-off"),
        category="assortment",
        direction="opportunity",
        entity_type="sku",
        entities=list(tail.sku_id.head(25)),
        magnitude_aed=magnitude,
        magnitude_basis=(
            f"{tail_slots:,} slots at AED {k.costs['slot_cost_aed_month']}/month "
            f"= AED {slot_cost:,.0f}/yr, plus AED {waste_cost:,.0f}/yr of tail waste, "
            f"less 50% of the AED {tail_margin:,.0f}/yr margin these lines earn "
            f"(assumes half the demand migrates to remaining range)."),
        magnitude_low=max(slot_cost + waste_cost - tail_margin, 0),
        magnitude_high=slot_cost + waste_cost,
        evidence=[
            Evidence("Tail SKUs", len(tail), "SKUs",
                     f"of {len(sku)} stocked", "skus"),
            Evidence("Share of revenue", tail_rev_share, "", None, "inventory_daily"),
            Evidence("Share of slots", tail_slot_share, "", None, "assortment"),
            Evidence("Share of waste cost", tail_waste_share, "", None,
                     "inventory_daily"),
            Evidence("Tail margin earned", tail_margin, "AED/yr", None,
                     "inventory_daily"),
        ],
        method="Revenue-ranked ABC; slot and waste cost attribution to the tail",
        confidence=combine_confidence(st, sm, dq),
        confidence_basis=describe_confidence(st, sm, dq, len(sku),
                                             "deterministic ranking"),
        period=(k.network["period_start"], k.network["period_end"]),
        tags=["assortment", "pareto", "delist"],
        detail={"tail": tail.head(40).to_dict("records"),
                "tail_slots": tail_slots, "total_slots": total_slots},
    )]


# ==========================================================================
# 5. Replenishment cadence vs demand shape
# ==========================================================================

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def detect_cadence_mismatch(ds, k, rules) -> list[Finding]:
    dow = k.by_dow.copy().sort_values("dow")
    if len(dow) < 7:
        return []

    # The planning cadence is when orders are *raised*, not when they land.
    # Receipts scatter across the week because lead times differ by supplier;
    # the review calendar is the thing that is actually controllable, and it is
    # what sizes the order.
    reviews = k.inv.groupby("dow", observed=True).ordered_units.sum()
    review_days = reviews[reviews > reviews.max() * 0.20].index.tolist()
    demand = k.inv.groupby("dow", observed=True).demand_units.sum()
    peak_days = sorted(demand.nlargest(2).index.tolist())

    best, worst = dow.fill_rate.max(), dow.fill_rate.min()
    spread = best - worst
    if spread < 0.04:
        return []

    worst_dow = int(dow.loc[dow.fill_rate.idxmin(), "dow"])
    best_dow = int(dow.loc[dow.fill_rate.idxmax(), "dow"])

    # Money: lost margin on days below the weekly mean fill rate, valued at the
    # margin that would have been earned had every day matched the best day.
    mean_fr = dow.fill_rate.mean()
    below = dow[dow.fill_rate < mean_fr]
    recoverable = 0.0
    for _, r in below.iterrows():
        share = (best - r.fill_rate) / max(1 - r.fill_rate, 1e-9)
        recoverable += r.lost_margin_aed * share
    magnitude = k.annualised(k.stockout_cost(recoverable))

    n = int(k.inv.demand_units.sum())
    z, p = proportion_test(
        dow.loc[dow.dow == worst_dow, "units_sold"].iloc[0],
        dow.loc[dow.dow == worst_dow, "units_sold"].iloc[0] + dow.loc[dow.dow == worst_dow, "units_lost"].iloc[0],
        dow.loc[dow.dow == best_dow, "units_sold"].iloc[0],
        dow.loc[dow.dow == best_dow, "units_sold"].iloc[0] + dow.loc[dow.dow == best_dow, "units_lost"].iloc[0])
    st = statistical_confidence(p_value=p)
    sm = sample_confidence(n, 10000)
    dq = k.table_confidence("inventory_daily")

    return [Finding(
        id=_fid("CAD", 1),
        headline=(f"Availability swings {spread:.0f}pp across the week — "
                  f"{DAYS[best_dow]} {best:.1%} down to {DAYS[worst_dow]} {worst:.1%} — "
                  f"because orders are reviewed "
                  f"{' and '.join(DAYS[d] for d in review_days)} but demand peaks "
                  f"{' and '.join(DAYS[d] for d in peak_days)}"
                  ).replace(f"{spread:.0f}pp", f"{spread*100:.0f}pp"),
        category="service",
        direction="leak",
        entity_type="daypart",
        entities=[DAYS[worst_dow]],
        magnitude_aed=magnitude,
        magnitude_basis=(
            f"For every weekday below the weekly mean fill rate, the share of lost "
            f"margin that would have been recovered at the best day's fill rate "
            f"({best:.1%}), summed, penalised and annualised."),
        magnitude_low=k.annualised(recoverable),
        magnitude_high=magnitude * 1.25,
        evidence=[
            Evidence("Best day", f"{DAYS[best_dow]} {best:.1%}", "", None,
                     "inventory_daily"),
            Evidence("Worst day", f"{DAYS[worst_dow]} {worst:.1%}", "", None,
                     "inventory_daily"),
            Evidence("Replenishment reviewed on",
                     ", ".join(DAYS[d] for d in review_days), "", None,
                     "inventory_daily"),
            Evidence("Demand peaks on", ", ".join(DAYS[d] for d in peak_days),
                     "", None, "inventory_daily"),
            Evidence("Weekend demand vs review-day demand",
                     float(demand[peak_days].mean() / demand[review_days].mean()),
                     "x", "order quantities are sized on review-day demand",
                     "inventory_daily"),
            Evidence("Spread", spread, "", "materiality threshold 4pp",
                     "inventory_daily", n),
        ],
        method="Day-of-week fill rate profile against the replenishment review "
               "calendar and the demand profile; two-proportion z-test on best "
               "vs worst day",
        confidence=combine_confidence(st, sm, dq),
        confidence_basis=describe_confidence(st, sm, dq, n, "two-proportion z-test"),
        period=(k.network["period_start"], k.network["period_end"]),
        tags=["cadence", "replenishment", "fill_rate"],
        detail={"by_dow": dow.to_dict("records"),
                "review_days": [DAYS[d] for d in review_days],
                "peak_days": [DAYS[d] for d in peak_days]},
    )]


# ==========================================================================
# 6. Fleet constraint  —  the misdiagnosis guard
# ==========================================================================

def detect_fleet_constraint(ds, k, rules) -> list[Finding]:
    """Separate last-mile capacity failures from inventory failures.

    A store can look broken for two entirely different reasons, and the
    symptoms overlap almost completely: slow deliveries, cancelled orders,
    unhappy customers. The distinguishing test is whether the goods were
    on the shelf. If they were, no inventory action will help, and
    recommending one wastes a quarter.
    """
    out: list[Finding] = []
    t_util = rules["targets"]["fleet_utilisation"]
    t_del = rules["targets"]["delivery_minutes_p50"]
    t_cancel = rules["targets"]["order_cancel_rate"]

    fleet = k.fleet_by_store.set_index("store_id")
    svc = k.service_by_store.set_index("store_id")
    inv = k.by_store.set_index("store_id")

    peer_fill = inv.fill_rate.median()
    peer_waste = inv.waste_rate.median()
    peer_del = svc.delivery_p50.median()
    peer_util = fleet.utilisation_pct.median()
    dq = k.table_confidence("courier_daily", "orders", "inventory_daily")
    idx = 0

    for sid in fleet.index:
        f_, s_, i_ = fleet.loc[sid], svc.loc[sid], inv.loc[sid]

        service_bad = (s_.delivery_p50 > t_del["ceiling"]
                       or s_.cancel_rate > t_cancel["ceiling"])
        capacity_bad = f_.utilisation_pct > t_util["ceiling"] * 100
        inventory_ok = (i_.fill_rate >= peer_fill * 0.98
                        and i_.waste_rate <= peer_waste * 1.2)

        if not (service_bad and capacity_bad):
            continue
        idx += 1

        # Money: cancelled-order cost plus the margin on baskets that never
        # completed, plus the cost of the capacity shortfall.
        excess_cancels = max(s_.cancel_rate - t_cancel["target"], 0) * s_.orders
        cancel_cost = excess_cancels * k.costs["cancelled_order_cost_aed"]
        lost_basket_margin = excess_cancels * (
            s_.margin_aed / max(s_.delivered, 1))
        magnitude = k.annualised(cancel_cost + lost_basket_margin)

        shortfall_orders = max(f_.avg_orders - f_.avg_orders / (f_.utilisation_pct / 100)
                               * (t_util["target"] * 100) / 100, 0)
        captains_needed = (f_.avg_orders / (t_util["target"]
                           * k.costs["deliveries_per_captain_shift"])) - f_.avg_captains

        z, p = proportion_test(
            s_.orders - s_.delivered, s_.orders,
            (svc.drop(sid).orders - svc.drop(sid).delivered).sum(),
            svc.drop(sid).orders.sum())
        st = statistical_confidence(p_value=p)
        sm = sample_confidence(int(s_.orders), 5000)

        verdict = ("fleet capacity" if inventory_ok else "mixed — inventory also weak")

        out.append(Finding(
            id=_fid("FLT", idx),
            headline=(f"{f_.store_name} delivers in {s_.delivery_p50:.0f} min against a "
                      f"network median of {peer_del:.0f} and cancels {s_.cancel_rate:.1%} "
                      f"of orders — the constraint is fleet capacity, not stock"),
            category="fleet",
            direction="leak",
            entity_type="store",
            entities=[sid],
            magnitude_aed=magnitude,
            magnitude_basis=(
                f"{excess_cancels:,.0f} cancellations above the {t_cancel['target']:.1%} "
                f"target, each costing AED {k.costs['cancelled_order_cost_aed']} to serve "
                f"and forgoing AED {s_.margin_aed / max(s_.delivered,1):,.1f} of basket "
                f"margin. Annualised."),
            magnitude_low=k.annualised(cancel_cost),
            magnitude_high=magnitude * 1.4,
            evidence=[
                Evidence("Delivery p50", s_.delivery_p50, "min",
                         f"network median {peer_del:.1f}", "orders", int(s_.orders)),
                Evidence("Delivery p90", s_.delivery_p90, "min", None, "orders"),
                Evidence("Cancellation rate", s_.cancel_rate, "",
                         f"target {t_cancel['target']:.1%}", "orders", int(s_.orders)),
                Evidence("Fleet utilisation", f_.utilisation_pct / 100, "",
                         f"network median {peer_util/100:.0%}", "courier_daily"),
                Evidence("Days above 100% utilisation", f_.days_over_100, "",
                         "share of trading days", "courier_daily"),
                # the two numbers that rule out an inventory explanation
                Evidence("Fill rate", i_.fill_rate, "",
                         f"network median {peer_fill:.1%} — the stock was on "
                         f"the shelf, so this is not a stock problem",
                         "inventory_daily", role="rules_out"),
                Evidence("Waste rate", i_.waste_rate, "",
                         f"network median {peer_waste:.1%} — inventory is not "
                         f"being mismanaged here either",
                         "inventory_daily", role="rules_out"),
            ],
            method=("Joint test: service breach AND capacity breach AND inventory "
                    "health within peer range. The inventory test is what "
                    "distinguishes a fleet constraint from a stock constraint."),
            confidence=combine_confidence(st, sm, dq),
            confidence_basis=describe_confidence(st, sm, dq, int(s_.orders),
                                                 "two-proportion z-test vs peers"),
            period=(k.network["period_start"], k.network["period_end"]),
            tags=["fleet", "capacity", "misdiagnosis_guard"],
            detail={
                "verdict": verdict,
                "inventory_ruled_out": bool(inventory_ok),
                "captains_shortfall_per_day": float(max(captains_needed, 0)),
                "avg_captains": float(f_.avg_captains),
                "avg_orders": float(f_.avg_orders),
                "cost_per_order_aed": float(f_.cost_per_order_aed),
            },
        ))
    return out


# ==========================================================================
# 7. Seasonality
# ==========================================================================

def detect_seasonality(ds, k, rules) -> list[Finding]:
    from statsmodels.tsa.seasonal import STL

    s = k.service_daily.set_index("date")["orders"].asfreq("D").interpolate()
    if len(s) < 150:
        return []
    stl = STL(s, period=7, robust=True).fit()
    seasonal_strength = max(0.0, 1 - stl.resid.var() / (stl.seasonal + stl.resid).var())
    trend_strength = max(0.0, 1 - stl.resid.var() / (stl.trend + stl.resid).var())

    # Find the largest sustained deviation from trend, rather than hard-coding
    # a religious or retail calendar. The window must sit far enough into the
    # series for a clean pre-period baseline to exist, otherwise the comparison
    # is against nothing.
    WINDOW, BASELINE, GAP = 28, 53, 7
    earliest = s.index[0] + pd.Timedelta(days=WINDOW + BASELINE + GAP)
    ratio = (s / stl.trend).rolling(WINDOW).mean()
    ratio = ratio[ratio.index >= earliest]
    if ratio.dropna().empty:
        return []

    peak_end = ratio.idxmax()
    peak_start = peak_end - pd.Timedelta(days=WINDOW - 1)
    window = s.loc[peak_start:peak_end]
    baseline = s.loc[peak_start - pd.Timedelta(days=BASELINE + GAP):
                     peak_start - pd.Timedelta(days=GAP)]
    if baseline.empty or baseline.mean() == 0:
        return []
    lift = window.mean() / baseline.mean() - 1

    od = k.orders
    in_win = od[(od.date >= peak_start) & (od.date <= peak_end)]
    out_win = od[(od.date >= peak_start - pd.Timedelta(days=BASELINE + GAP)) &
                 (od.date < peak_start - pd.Timedelta(days=GAP))]
    if in_win.empty or out_win.empty:
        return []
    night = [20, 21, 22, 23, 0, 1]
    night_in = in_win.hour.isin(night).mean()
    night_out = out_win.hour.isin(night).mean()

    if lift < 0.15:
        return []

    # Money framed as an opportunity: the fill-rate gap during the peak window,
    # which is when losing a sale costs most.
    #
    # NOTE ON ANNUALISATION. This window is an annually recurring event, not a
    # continuous rate. The standard annualisation factor (365/period_days)
    # would be wrong here — it scales a rate observed over the whole period up
    # or down to a year. A window that happens once a year is already an annual
    # figure. Applying the factor understated this finding by a third and
    # pushed it below the materiality floor, which is a good illustration of
    # how an innocuous-looking unit conversion can silently delete a finding.
    win_inv = k.inv[(k.inv.date >= peak_start) & (k.inv.date <= peak_end)]
    win_fill = win_inv.sold_units.sum() / max(
        win_inv.sold_units.sum() + win_inv.lost_units.sum(), 1)
    magnitude = k.stockout_cost(float(win_inv.lost_margin_aed.sum()))

    dq = k.table_confidence("orders", "inventory_daily")
    st = statistical_confidence(p_value=0.001)
    sm = sample_confidence(len(s), 200)

    return [Finding(
        id=_fid("SEA", 1),
        headline=(f"A {lift:.0%} demand peak runs {peak_start.date()} to {peak_end.date()} "
                  f"with {night_in:.0%} of orders after 20:00 (vs {night_out:.0%} normally) "
                  f"— fill rate holds at only {win_fill:.1%} through it"),
        category="demand",
        direction="opportunity",
        entity_type="network",
        entities=["network"],
        magnitude_aed=magnitude,
        magnitude_basis=(
            f"Lost margin inside the peak window of AED "
            f"{win_inv.lost_margin_aed.sum():,.0f}, with the stockout penalty applied. "
            f"Not scaled by the annualisation factor: the window recurs once a year, "
            f"so a single occurrence already is the annual figure. This is the cost "
            f"of not planning for a demand shape that is known in advance."),
        magnitude_low=float(win_inv.lost_margin_aed.sum()),
        magnitude_high=magnitude * 1.3,
        evidence=[
            Evidence("Peak window", f"{peak_start.date()} to {peak_end.date()}",
                     "", None, "orders"),
            Evidence("Volume lift", lift, "", "vs prior 8 weeks", "orders", len(in_win)),
            Evidence("Orders after 20:00", night_in, "",
                     f"normally {night_out:.0%}", "orders"),
            Evidence("Fill rate in window", win_fill, "",
                     f"network {k.network['fill_rate']:.1%}", "inventory_daily"),
            Evidence("Weekly seasonal strength", seasonal_strength, "",
                     "STL decomposition", "orders", len(s)),
            Evidence("Trend strength", trend_strength, "", "STL decomposition",
                     "orders", len(s)),
        ],
        method="STL decomposition (period 7, robust); trend-adjusted rolling peak "
               "detection; daypart mix comparison",
        confidence=combine_confidence(st, sm, dq),
        confidence_basis=describe_confidence(st, sm, dq, len(s), "STL decomposition"),
        period=(k.network["period_start"], k.network["period_end"]),
        tags=["seasonality", "ramadan", "daypart"],
        detail={"peak_start": str(peak_start.date()), "peak_end": str(peak_end.date()),
                "lift": float(lift), "night_share_in": float(night_in),
                "night_share_out": float(night_out),
                "seasonal_strength": float(seasonal_strength),
                "trend_strength": float(trend_strength)},
    )]


# ==========================================================================
# 8. Root-cause linking
# ==========================================================================

def link_root_causes(fs, ds, k):
    """Connect findings that explain each other, so the brief reports the
    cause once rather than the symptom five times."""
    svc = [f for f in fs if f.id.startswith("SVC")]
    sup = [f for f in fs if f.id.startswith("SUP")]
    cad = [f for f in fs if f.id.startswith("CAD")]
    wst = [f for f in fs if f.id.startswith("WST")]

    # Supplier unreliability and replenishment cadence both feed the network
    # availability gap — that gap is a symptom, not a cause.
    for s in svc:
        for u in sup:
            fs.link(u.id, s.id)
        for c in cad:
            fs.link(c.id, s.id)

    # Site-level waste that is driven by lot size is not a site problem — the
    # network-wide lot-size finding explains it, and reporting both as
    # independent leaks would double-count the same money.
    lot = [f for f in fs if f.id.startswith("LOT")]
    for w in wst:
        if w.detail.get("structural_share", 0) > 0.4:
            for l in lot:
                fs.link(l.id, w.id)
    return fs


# ==========================================================================

ALL_DETECTORS = [
    detect_service_gap,
    detect_supplier_reliability,
    detect_waste_concentration,
    detect_lot_size_policy,
    detect_long_tail,
    detect_cadence_mismatch,
    detect_fleet_constraint,
    detect_seasonality,
]


def run_all(ds, k, rules):
    from findings import FindingSet
    fs = FindingSet()
    for det in ALL_DETECTORS:
        try:
            fs.extend(det(ds, k, rules))
        except Exception as e:                       # a detector failing must not
            import traceback                          # take the whole brief down
            print(f"  ! {det.__name__} failed: {e}")
            traceback.print_exc()
    link_root_causes(fs, ds, k)
    return fs
