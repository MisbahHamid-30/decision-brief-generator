"""
Output verification — phase 8
=============================
Checks the brief against reality, deliberately without using any of the
pipeline's own code. Every figure below is recomputed straight from the CSVs
with independent pandas, then compared to what the brief claims.

Verifying an analysis by calling the same engine that produced it proves only
that the engine is deterministic. The point of this file is to be a second
opinion, so it re-derives rather than re-reads.

Four families of check:

  A. Ground truth   — were all six planted signals surfaced as findings?
  B. Arithmetic     — do the recommendation economics actually add up?
  C. Recomputation  — do the headline numbers match a fresh calculation?
  D. Integrity      — no double counting, no orphan claims, files exist

    python3 src/verify_outputs.py
"""

from __future__ import annotations

import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "careem_quik")
OUT = os.path.join(ROOT, "outputs")

results: list[tuple[str, str, bool, str]] = []


def check(family: str, name: str, passed: bool, detail: str = ""):
    results.append((family, name, passed, detail))
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail else ""))


def close(a: float, b: float, tol: float = 0.01) -> bool:
    """Within a relative tolerance."""
    if b == 0:
        return abs(a) < 1e-9
    return abs(a - b) / abs(b) <= tol


# ==========================================================================

def load_raw():
    inv = pd.read_csv(f"{DATA}/inventory_daily.csv", parse_dates=["date"])
    po = pd.read_csv(f"{DATA}/purchase_orders.csv",
                     parse_dates=["order_date", "promised_date", "received_date"])
    od = pd.read_csv(f"{DATA}/orders.csv", parse_dates=["order_datetime"])
    sk = pd.read_csv(f"{DATA}/skus.csv")
    st = pd.read_csv(f"{DATA}/dark_stores.csv")
    cd = pd.read_csv(f"{DATA}/courier_daily.csv", parse_dates=["date"])
    asm = pd.read_csv(f"{DATA}/assortment.csv")

    # The pipeline removes exact duplicates and caps impossible delivery times
    # before analysing. Reproduce those two repairs here so the comparison is
    # like-for-like — anything else would be comparing different populations.
    od = od.drop_duplicates()
    od = od.drop_duplicates(subset=["order_id"], keep="first")
    od["actual_minutes"] = od["actual_minutes"].clip(upper=120.0)
    return inv, po, od, sk, st, cd, asm


def main() -> int:
    for f in ("findings.json", "brief_payload.json"):
        if not os.path.exists(os.path.join(OUT, f)):
            print(f"missing {f} — run build_outputs.py first")
            return 1

    payload = json.load(open(os.path.join(OUT, "brief_payload.json")))
    findings = {f["id"]: f for f in payload["all_findings"]}
    recs = {r["id"]: r for r in payload["recommendations"]}
    net = payload["network_kpis"] if "network_kpis" in payload else None

    inv, po, od, sk, st, cd, asm = load_raw()
    inv = inv.merge(sk[["sku_id", "category", "supplier_id",
                        "unit_price_aed", "unit_cost_aed"]], on="sku_id")
    inv = inv.merge(st[["store_id", "store_name", "city"]], on="store_id")

    print("=" * 78)
    print("OUTPUT VERIFICATION")
    print("=" * 78)

    # ---------------------------------------------------------------- A
    print("\nA. Ground truth — was every planted signal surfaced?\n")

    # S1 supplier degradation -> a SUP finding naming SUP01
    sup_f = [f for f in findings.values()
             if f["id"].startswith("SUP") and "SUP01" in f["entities"]]
    po["lead"] = (po.received_date - po.order_date).dt.days
    p = po[po.supplier_id == "SUP01"]
    pre, post = p[p.order_date < "2026-02-01"], p[p.order_date >= "2026-02-01"]
    degraded = post.lead.std() > 2 * pre.lead.std()
    check("A", "S1 supplier reliability surfaced",
          bool(sup_f) and degraded,
          f"lead sd {pre.lead.std():.2f}→{post.lead.std():.2f}, "
          f"finding {sup_f[0]['id'] if sup_f else 'NONE'}")

    # S2 Abu Dhabi dairy waste -> a WST finding naming Abu Dhabi + Dairy
    d = inv[(inv.category == "Dairy & Eggs")]
    ad = d[d.city == "Abu Dhabi"]
    ad_rate = ad.wasted_units.sum() / ad.received_units.sum()
    net_rate = inv.wasted_units.sum() / inv.received_units.sum()
    wst_f = [f for f in findings.values()
             if f["id"].startswith("WST") and "Abu Dhabi" in f["entities"]
             and "Dairy & Eggs" in f["entities"]]
    check("A", "S2 Abu Dhabi dairy write-off surfaced",
          bool(wst_f) and ad_rate > 3 * net_rate,
          f"{ad_rate:.1%} vs network {net_rate:.1%}, "
          f"finding {wst_f[0]['id'] if wst_f else 'NONE'}")

    # S3 long tail -> AST finding
    inv["rev"] = inv.sold_units * inv.unit_price_aed
    s = inv.groupby("sku_id").rev.sum().sort_values(ascending=False)
    tail_share = s.iloc[int(len(s) * 0.6):].sum() / s.sum()
    check("A", "S3 long tail surfaced",
          "AST-01" in findings and tail_share < 0.10,
          f"bottom 40% of SKUs = {tail_share:.1%} of revenue")

    # S4 cadence -> CAD finding, Monday worst
    inv["dow"] = inv.date.dt.dayofweek
    fr = inv.groupby("dow").apply(
        lambda g: g.sold_units.sum() / (g.sold_units.sum() + g.lost_demand_units.sum()))
    check("A", "S4 replenishment cadence surfaced",
          "CAD-01" in findings and fr.idxmin() == 0 and (fr.max() - fr.min()) > 0.10,
          f"worst day = {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][fr.idxmin()]}, "
          f"spread {fr.max()-fr.min():.1%}")

    # S5 the trap -> FLT finding on DS07, and it must NOT be a waste/service one
    flt = [f for f in findings.values()
           if f["id"].startswith("FLT") and "DS07" in f["entities"]]
    ds7_fill = (inv[inv.store_id == "DS07"].sold_units.sum() /
                (inv[inv.store_id == "DS07"].sold_units.sum() +
                 inv[inv.store_id == "DS07"].lost_demand_units.sum()))
    peer_fill = (inv[inv.store_id != "DS07"].sold_units.sum() /
                 (inv[inv.store_id != "DS07"].sold_units.sum() +
                  inv[inv.store_id != "DS07"].lost_demand_units.sum()))
    check("A", "S5 misdiagnosis trap surfaced as a FLEET finding",
          bool(flt),
          f"finding {flt[0]['id'] if flt else 'NONE'}, category "
          f"{flt[0]['category'] if flt else '—'}")
    # Test the structural marker, not the prose. An earlier version of this
    # check matched the literal string "NOT a stock problem" in the comparator
    # text, and broke the moment that sentence was reworded — a test coupled to
    # wording tells you the wording changed, not whether the reasoning is sound.
    check("A", "S5 diagnosed correctly — inventory explicitly ruled out",
          bool(flt) and flt[0]["category"] == "fleet"
          and ds7_fill >= peer_fill
          and any(e.get("role") == "rules_out" for e in flt[0]["evidence"]),
          f"DS07 fill {ds7_fill:.1%} vs peers {peer_fill:.1%} — the store with the "
          f"worst service has the best availability")

    # S6 seasonality -> SEA finding
    od["d"] = od.order_datetime.dt.normalize()
    daily = od.groupby("d").size()
    ram = daily["2026-02-17":"2026-03-19"].mean()
    base = daily["2026-01-05":"2026-02-10"].mean()
    check("A", "S6 seasonality surfaced",
          "SEA-01" in findings and (ram / base - 1) > 0.20,
          f"peak window +{ram/base-1:.0%} vs baseline")

    # ---------------------------------------------------------------- B
    print("\nB. Arithmetic — do the recommendation economics hold?\n")

    ok_net = all(close(r["net_annual_aed"],
                       r["benefit_aed"] - r["annual_cost_aed"], 1e-6)
                 for r in recs.values())
    check("B", "net = benefit − ongoing cost, for every recommendation", ok_net)

    ok_pb = True
    for r in recs.values():
        if r["net_annual_aed"] > 0 and r["one_off_cost_aed"] > 0:
            expected = 12 * r["one_off_cost_aed"] / r["net_annual_aed"]
            if not close(r["payback_months"] or 0, expected, 1e-6):
                ok_pb = False
    check("B", "payback = 12 × one-off ÷ net annual", ok_pb)

    ok_stance = all(
        (r["stance"] == "reject") == (r["net_annual_aed"] <= 0)
        for r in recs.values())
    check("B", "anything with a negative net is marked 'reject'", ok_stance,
          "R5b: benefit " +
          f"{recs['R5b']['benefit_aed']:,.0f} vs cost {recs['R5b']['annual_cost_aed']:,.0f}"
          if "R5b" in recs else "")

    ok_capture = True
    for r in recs.values():
        src = [findings[i] for i in r["finding_ids"] if i in findings]
        if src and r["benefit_aed"] > max(f["magnitude_aed"] for f in src) + 1:
            ok_capture = False
    check("B", "no recommendation claims more than its finding is worth", ok_capture,
          "capture rates are all below 100%")

    total = payload["headline"]["net_benefit"]
    recomputed = sum(r["net_annual_aed"] for r in recs.values() if r["stance"] == "act")
    check("B", "headline net benefit equals the sum of accepted actions",
          close(total, recomputed, 1e-6), f"AED {total:,.0f}")

    # ---------------------------------------------------------------- C
    print("\nC. Recomputation — do the headline numbers survive a fresh calculation?\n")

    claimed = {s["kpi"]: s["actual"] for s in payload["scorecard"]}

    fill = inv.sold_units.sum() / (inv.sold_units.sum() + inv.lost_demand_units.sum())
    check("C", "fill rate", close(fill, claimed["Fill rate"], 0.005),
          f"recomputed {fill:.4f} vs brief {claimed['Fill rate']:.4f}")

    waste = inv.wasted_units.sum() / inv.received_units.sum()
    check("C", "waste rate", close(waste, claimed["Waste rate"], 0.005),
          f"recomputed {waste:.4f} vs brief {claimed['Waste rate']:.4f}")

    po["on_time"] = (po.received_date <= po.promised_date).astype(int)
    po["in_full"] = (po.qty_received >= po.qty_ordered).astype(int)
    otif = (po.on_time * po.in_full).mean()
    check("C", "supplier OTIF", close(otif, claimed["Supplier OTIF"], 0.005),
          f"recomputed {otif:.4f} vs brief {claimed['Supplier OTIF']:.4f}")

    p50 = od.actual_minutes.median()
    check("C", "delivery p50", close(p50, claimed["Delivery p50 (min)"], 0.01),
          f"recomputed {p50:.2f} vs brief {claimed['Delivery p50 (min)']:.2f}")

    cancel = 1 - (od.status == "delivered").mean()
    check("C", "order cancellation rate",
          close(cancel, claimed["Order cancel rate"], 0.01),
          f"recomputed {cancel:.4f} vs brief {claimed['Order cancel rate']:.4f}")

    # a figure quoted in a headline, not just the scorecard
    cad = findings.get("CAD-01", {})
    worst, best = fr.min(), fr.max()
    check("C", "CAD-01 quotes the correct best and worst weekday fill rates",
          f"{best:.1%}" in cad.get("headline", "") and
          f"{worst:.1%}" in cad.get("headline", ""),
          f"recomputed best {best:.1%}, worst {worst:.1%}")

    ds7 = od[od.store_id == "DS07"]
    flt_f = findings.get("FLT-01", {})
    ev = {e["label"]: e["value"] for e in flt_f.get("evidence", [])}
    check("C", "FLT-01 delivery and cancellation figures",
          close(float(ev.get("Delivery p50", 0)), ds7.actual_minutes.median(), 0.01)
          and close(float(ev.get("Cancellation rate", 0)),
                    1 - (ds7.status == "delivered").mean(), 0.02),
          f"recomputed p50 {ds7.actual_minutes.median():.1f} min, "
          f"cancels {1-(ds7.status=='delivered').mean():.1%}")

    # ---------------------------------------------------------------- D
    print("\nD. Integrity\n")

    roots = [f for f in findings.values()
             if f["direction"] == "leak" and not f["caused_by"]]
    leak_sum = sum(f["magnitude_aed"] for f in roots)
    check("D", "reported leakage counts root causes only, not symptoms",
          close(leak_sum, payload["headline"]["total_leak"], 1e-6),
          f"{len(roots)} roots, AED {leak_sum:,.0f}; "
          f"{len([f for f in findings.values() if f['caused_by']])} symptoms excluded")

    symptom_total = sum(f["magnitude_aed"] for f in findings.values()
                        if f["direction"] == "leak" and f["caused_by"])
    check("D", "excluding symptoms materially changes the total",
          symptom_total > 0,
          f"AED {symptom_total:,.0f} would have been double-counted")

    ok_ev = all(len(f["evidence"]) > 0 and f["method"] and f["magnitude_basis"]
                for f in findings.values())
    check("D", "every finding carries evidence, method and a derivation", ok_ev,
          f"{len(findings)} findings checked")

    ok_link = all(fid in findings for f in findings.values()
                  for fid in f["caused_by"] + f["explains"])
    check("D", "no finding references a link that does not exist", ok_link)

    ok_owner = all(r["owner"] in payload["assumptions"].get("owners", [r["owner"]])
                   or True for r in recs.values())
    ok_assum = all(len(r["assumptions"]) > 0 and r["risk"] and r["success_metric"]
                   for r in recs.values())
    check("D", "every recommendation states assumptions, risk and a success metric",
          ok_assum, f"{len(recs)} recommendations checked")

    deliverables = {
        "Decision-Brief.docx": 100_000,
        "Decision-Brief.pptx": 100_000,
        "dashboard.html": 50_000,
        "analysis_report.md": 5_000,
        "findings.json": 10_000,
        "data_quality_report.md": 500,
    }
    missing = [f for f, minsize in deliverables.items()
               if not os.path.exists(os.path.join(OUT, f))
               or os.path.getsize(os.path.join(OUT, f)) < minsize]
    check("D", "all deliverables exist and are non-trivial", not missing,
          "missing/short: " + ", ".join(missing) if missing
          else f"{len(deliverables)} files")

    check("D", "synthetic-data labelling is present in the payload",
          payload["meta"]["synthetic"] is True)

    # ---------------------------------------------------------------- summary
    print("\n" + "=" * 78)
    fams = {}
    for fam, _, ok, _ in results:
        fams.setdefault(fam, [0, 0])
        fams[fam][1] += 1
        fams[fam][0] += int(ok)
    names = {"A": "Ground truth", "B": "Arithmetic",
             "C": "Recomputation", "D": "Integrity"}
    for fam in sorted(fams):
        got, tot = fams[fam]
        print(f"  {fam}. {names[fam]:<16} {got}/{tot}")
    passed = sum(1 for _, _, ok, _ in results if ok)
    print(f"\n  TOTAL {passed}/{len(results)} checks passed")
    print("=" * 78)

    failures = [(f, n, d) for f, n, ok, d in results if not ok]
    if failures:
        print("\nFAILURES")
        for fam, n, d in failures:
            print(f"  {fam}: {n} — {d}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
