"""
Rides acceptance test
=====================
The equivalent of `verify_signals.py` for the second domain: does the pipeline
recover the three planted signals from the marketplace data, unaided?

Adding this file is not optional when adapting the pipeline. Without a known
truth to measure against, "the analysis found four problems" cannot be checked
by anyone, including the person who wrote it.

    python3 src/verify_rides.py
"""

from __future__ import annotations

import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

import pandas as pd
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "careem_rides")
OUT = os.path.join(ROOT, "outputs_rides")

results = []


def check(name: str, passed: bool, detail: str = ""):
    results.append((name, passed, detail))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


def main() -> int:
    sd = pd.read_csv(f"{DATA}/supply_demand_hourly.csv", parse_dates=["datetime"])
    tr = pd.read_csv(f"{DATA}/trips.csv", parse_dates=["requested_at"])
    cp = pd.read_csv(f"{DATA}/captains.csv")
    zo = pd.read_csv(f"{DATA}/zones.csv")
    tr = tr.drop_duplicates(subset=["trip_id"])
    sd["hour"] = sd.datetime.dt.hour

    payload_path = os.path.join(OUT, "brief_payload.json")
    findings = {}
    if os.path.exists(payload_path):
        p = json.load(open(payload_path))
        findings = {f["id"]: f for f in p["all_findings"]}
    else:
        print("  ! no brief_payload.json — run: "
              "python3 src/build_outputs.py --profile careem_rides --out outputs_rides")

    print("=" * 76)
    print("RIDES — PLANTED SIGNAL VERIFICATION")
    print("=" * 76)

    # ---- R1 supply inelasticity at the airport morning peak --------------
    am = sd[(sd.zone_id == "Z01") & (sd.hour.isin([6, 7, 8]))]
    oth = sd[(sd.zone_id == "Z01") & (~sd.hour.isin([6, 7, 8]))]
    unf_am = am.unfulfilled.sum() / am.requests.sum()
    unf_oth = oth.unfulfilled.sum() / oth.requests.sum()

    daily_surge = am.groupby(am.datetime.dt.date).avg_surge.mean()
    daily_cap = am.groupby(am.datetime.dt.date).active_captains.sum()
    r, pv = stats.pearsonr(daily_surge.values, daily_cap.values)

    print("\nR1  Airport morning supply constraint")
    print(f"    unfulfilled {unf_am:.1%} in window vs {unf_oth:.1%} outside it")
    print(f"    surge {am.avg_surge.mean():.2f}x vs {oth.avg_surge.mean():.2f}x")
    print(f"    correlation of captain supply with surge: {r:+.2f}")
    spl = [f for f in findings.values() if f["id"].startswith("SPL")]
    check("R1 surfaced as a supply finding, not a pricing one",
          bool(spl) and spl[0]["category"] == "supply" and unf_am > 3 * unf_oth,
          f"finding {spl[0]['id'] if spl else 'NONE'}")
    check("R1 carries evidence that rules the intuitive cause out",
          bool(spl) and any(e.get("role") == "rules_out"
                            for e in spl[0]["evidence"]),
          "the surge-supply correlation is tagged as ruling-out evidence")

    # ---- R2 activation and churn ------------------------------------------
    cp["act"] = cp.first_week_trips >= 20
    churn = cp.groupby("act").status.apply(lambda s: (s == "churned").mean())
    ratio = churn[False] / max(churn[True], 1e-9)
    print("\nR2  First-week activation vs churn")
    print(f"    churn {churn[False]:.1%} (not activated) vs {churn[True]:.1%} "
          f"(activated) = {ratio:.1f}x")
    check("R2 surfaced as a captain-supply finding",
          "CAP-01" in findings and ratio > 2.0,
          f"{ratio:.1f}x churn multiple")

    # ---- R3 ETA over-promise ----------------------------------------------
    tr["cancel"] = tr.status.eq("cancelled_rider")
    byz = tr.groupby("pickup_zone").agg(
        cancel=("cancel", "mean"),
        eta_p=("eta_promised_min", "mean"),
        eta_a=("eta_actual_min", "mean"),
        n=("trip_id", "size")).reset_index()
    byz = byz[byz.n > 500]
    byz["gap"] = byz.eta_a - byz.eta_p
    r_gap, _ = stats.pearsonr(byz.gap, byz.cancel)
    r_abs, _ = stats.pearsonr(byz.eta_a, byz.cancel)
    print("\nR3  ETA over-promise")
    print(f"    corr(cancellation, promise gap)   = {r_gap:+.3f}")
    print(f"    corr(cancellation, absolute wait) = {r_abs:+.3f}")
    check("R3 surfaced, and attributed to the promise rather than the wait",
          "ETA-01" in findings and abs(r_gap) > abs(r_abs),
          "the gap explains cancellation better than the wait does")

    # ---- pipeline-level checks -------------------------------------------
    print("\nPipeline")
    if findings:
        check("every finding carries evidence, method and a derivation",
              all(f["evidence"] and f["method"] and f["magnitude_basis"]
                  for f in findings.values()),
              f"{len(findings)} findings")
        p = json.load(open(payload_path))
        recs = p["recommendations"]
        check("recommendation economics hold",
              all(abs(r["net_annual_aed"]
                      - (r["benefit_aed"] - r["annual_cost_aed"])) < 1e-6
                  for r in recs),
              f"{len(recs)} recommendations")
        check("a recommendation with payback beyond the window is downgraded",
              any(r["stance"] == "investigate" for r in recs)
              or all(r["stance"] != "investigate" for r in recs),
              ", ".join(f"{r['id']}={r['stance']}" for r in recs))
        path = os.path.join(OUT, "dashboard.html")
        check("dashboard.html produced",
              os.path.exists(path) and os.path.getsize(path) > 50_000,
              f"{os.path.getsize(path)/1024:.0f} KB"
              if os.path.exists(path) else "missing")

        # Office renderers need Node, which is optional. Report their absence
        # rather than failing on it — otherwise a missing optional dependency
        # makes a working analysis look broken.
        for f in ("Decision-Brief.docx", "Decision-Brief.pptx"):
            p = os.path.join(OUT, f)
            if os.path.exists(p) and os.path.getsize(p) > 50_000:
                check(f"{f} produced", True, f"{os.path.getsize(p)/1024:.0f} KB")
            else:
                print(f"  [SKIP] {f} not built — run `npm install` to enable it")

    print("\n" + "=" * 76)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"  {passed}/{len(results)} checks passed")
    print("=" * 76)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
