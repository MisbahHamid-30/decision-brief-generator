"""
Signal verification harness
===========================
Confirms the six planted signals described in ARCHITECTURE.md §3 are actually
present in the generated dataset, and prints the ground-truth values.

This is the Phase 8 acceptance test. The analysis engine, run blind on the same
data, must independently surface these — including getting S5 right (the
misdiagnosis trap, where the symptom looks like inventory but the cause is fleet).

Usage:  python3 src/verify_signals.py
"""

from __future__ import annotations

import os
import pandas as pd

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "careem_quik")


def load():
    inv = pd.read_csv(f"{D}/inventory_daily.csv", parse_dates=["date"])
    po = pd.read_csv(f"{D}/purchase_orders.csv",
                     parse_dates=["order_date", "promised_date", "received_date"])
    sk = pd.read_csv(f"{D}/skus.csv")
    st = pd.read_csv(f"{D}/dark_stores.csv")
    cd = pd.read_csv(f"{D}/courier_daily.csv", parse_dates=["date"])
    od = pd.read_csv(f"{D}/orders.csv", parse_dates=["order_datetime"])
    inv = (inv.merge(sk[["sku_id", "category", "supplier_id",
                         "unit_price_aed", "unit_cost_aed"]], on="sku_id")
              .merge(st[["store_id", "store_name", "city"]], on="store_id"))
    return inv, po, sk, st, cd, od


def fill_rate(g):
    got = g["sold_units"].sum()
    return got / max(got + g["lost_demand_units"].sum(), 1)


def main():
    inv, po, sk, st, cd, od = load()
    ok = []

    print("=" * 74)
    print("PLANTED SIGNAL VERIFICATION")
    print("=" * 74)

    # ---- S1 supplier reliability -------------------------------------------
    po["lead_days"] = (po.received_date - po.order_date).dt.days
    po["fill"] = po.qty_received / po.qty_ordered
    p = po[po.supplier_id == "SUP01"]
    pre, post = p[p.order_date < "2026-02-01"], p[p.order_date >= "2026-02-01"]
    fp = inv[inv.category == "Fresh Produce"]
    fp_pre = fp[(fp.date >= "2025-09-01") & (fp.date < "2026-02-01")].stockout_flag.mean()
    fp_post = fp[fp.date >= "2026-02-01"].stockout_flag.mean()
    oth = inv[inv.category != "Fresh Produce"]
    o_pre = oth[(oth.date >= "2025-09-01") & (oth.date < "2026-02-01")].stockout_flag.mean()
    o_post = oth[oth.date >= "2026-02-01"].stockout_flag.mean()
    print(f"\nS1  Supplier reliability — Gulf Fresh Produce (SUP01)")
    print(f"    lead time  {pre.lead_days.mean():.2f}d (sd {pre.lead_days.std():.2f}) "
          f"-> {post.lead_days.mean():.2f}d (sd {post.lead_days.std():.2f})")
    print(f"    PO fill    {pre.fill.mean():.1%} -> {post.fill.mean():.1%}")
    print(f"    Fresh Produce stockout-days {fp_pre:.1%} -> {fp_post:.1%}   "
          f"(all other categories {o_pre:.1%} -> {o_post:.1%})")
    print(f"    worst stores: "
          f"{fp[fp.date>='2026-02-01'].groupby('store_name').stockout_flag.mean().nlargest(3).round(3).to_dict()}")
    ok.append(("S1", post.lead_days.std() > 2 * pre.lead_days.std()
               and fp_post > fp_pre * 1.4))

    # ---- S2 case-pack driven waste -----------------------------------------
    dairy = inv[inv.category == "Dairy & Eggs"]
    by_city = dairy.groupby("city").apply(
        lambda g: g.wasted_units.sum() / max(g.received_units.sum(), 1),
        include_groups=False)
    net = inv.wasted_units.sum() / inv.received_units.sum()
    packs = sk[sk.supplier_id == "SUP02"].case_pack
    print(f"\nS2  Dairy waste concentration")
    print(f"    waste rate by city: {{{', '.join(f'{k}: {v:.1%}' for k, v in by_city.items())}}}")
    print(f"    network waste rate (all categories): {net:.1%}")
    print(f"    SUP02 case pack: {packs.min()}-{packs.max()} units")
    ok.append(("S2", by_city.get("Abu Dhabi", 0) > 3 * net))

    # ---- S3 long tail -------------------------------------------------------
    inv["revenue_aed"] = inv.sold_units * inv.unit_price_aed
    inv["waste_cost_aed"] = inv.wasted_units * inv.unit_cost_aed
    s = (inv.groupby("sku_id")
            .agg(rev=("revenue_aed", "sum"), waste=("waste_cost_aed", "sum"))
            .sort_values("rev", ascending=False))
    tail = s.iloc[int(len(s) * 0.6):]
    print(f"\nS3  Long tail")
    print(f"    bottom 40% of {len(s)} active SKUs -> {tail.rev.sum()/s.rev.sum():.1%} of revenue, "
          f"{tail.waste.sum()/s.waste.sum():.1%} of waste cost")
    print(f"    tail waste cost: AED {tail.waste.sum():,.0f}")
    ok.append(("S3", tail.rev.sum() / s.rev.sum() < 0.10
               and tail.waste.sum() / s.waste.sum() > 0.25))

    # ---- S4 replenishment cadence vs weekend peak ---------------------------
    inv["dow"] = inv.date.dt.dayofweek
    dow = inv.groupby("dow").apply(fill_rate, include_groups=False)
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    print(f"\nS4  Replenishment cadence vs demand peak")
    print("    fill rate by day: " +
          "  ".join(f"{n} {dow[i]:.1%}" for i, n in enumerate(names)))
    print(f"    network fill rate: {fill_rate(inv):.1%}   "
          f"(receipts land Mon/Wed only; Fri-Sat is the demand peak)")
    ok.append(("S4", dow[0] < dow[4] - 0.08))

    # ---- S5 misdiagnosis trap ----------------------------------------------
    od["delivered"] = od.status.eq("delivered")
    svc = od.groupby("store_id").agg(
        avg_delivery_min=("actual_minutes", "mean"),
        cancel_rate=("delivered", lambda s: 1 - s.mean()))
    inh = inv.groupby("store_id").apply(
        lambda g: pd.Series({"fill_rate": fill_rate(g),
                             "waste_pct": g.wasted_units.sum() / g.received_units.sum()}),
        include_groups=False)
    util = cd.groupby("store_id").utilisation_pct.mean().rename("fleet_util_pct")
    tbl = (svc.join(inh).join(util)
              .join(st.set_index("store_id")[["store_name", "city"]]))
    print(f"\nS5  Misdiagnosis trap — DS07 Al Nahda")
    print(tbl[["store_name", "city", "avg_delivery_min", "cancel_rate",
               "fleet_util_pct", "fill_rate", "waste_pct"]].round(3).to_string())
    d7 = tbl.loc["DS07"]
    peers = tbl.drop("DS07")
    print(f"    -> DS07 delivery {d7.avg_delivery_min:.1f} min vs peer mean "
          f"{peers.avg_delivery_min.mean():.1f}; fleet utilisation "
          f"{d7.fleet_util_pct:.0f}% vs {peers.fleet_util_pct.mean():.0f}%")
    print(f"    -> but DS07 fill rate {d7.fill_rate:.1%} vs peer {peers.fill_rate.mean():.1%} "
          f"and waste {d7.waste_pct:.1%} vs peer {peers.waste_pct.mean():.1%}")
    print(f"    -> CORRECT DIAGNOSIS: fleet capacity, NOT inventory.")
    ok.append(("S5", d7.fleet_util_pct > 110 and d7.fill_rate >= peers.fill_rate.mean()))

    # ---- S6 Ramadan --------------------------------------------------------
    od["d"] = od.order_datetime.dt.normalize()
    od["h"] = od.order_datetime.dt.hour
    ram = od[(od.d >= "2026-02-17") & (od.d <= "2026-03-19")]
    base = od[(od.d >= "2026-01-05") & (od.d <= "2026-02-10")]
    night = [20, 21, 22, 23, 0, 1]
    lift = ram.groupby("d").size().mean() / base.groupby("d").size().mean() - 1
    print(f"\nS6  Ramadan seasonality (2026)")
    print(f"    orders/day {base.groupby('d').size().mean():.0f} -> "
          f"{ram.groupby('d').size().mean():.0f}  ({lift:+.0%})")
    print(f"    share of orders 20:00-01:59: {base.h.isin(night).mean():.1%} -> "
          f"{ram.h.isin(night).mean():.1%}")
    ok.append(("S6", lift > 0.20 and ram.h.isin(night).mean() > base.h.isin(night).mean() * 1.3))

    # ---- summary -----------------------------------------------------------
    print("\n" + "=" * 74)
    for sid, passed in ok:
        print(f"  {sid}  {'PASS' if passed else 'FAIL'}")
    print(f"  {sum(p for _, p in ok)}/{len(ok)} signals present")
    print("=" * 74)


if __name__ == "__main__":
    main()
