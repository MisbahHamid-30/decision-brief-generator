"""
Analysis runner — phases 1 to 4 of the pipeline
===============================================
    ingest -> quality gate -> KPI engine -> detectors -> findings

Writes `outputs/findings.json` and `outputs/analysis_report.md`, which the
recommendation engine and the renderers consume.

    python3 src/run_analysis.py
"""

from __future__ import annotations

import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

from ingest import Dataset, ROOT, DEFAULT_PROFILE
import quality
import recommend
from analysis import registry

OUT = os.path.join(ROOT, "outputs")


def fmt_aed(v: float) -> str:
    if abs(v) >= 1e6:
        return f"AED {v/1e6:,.2f}m"
    if abs(v) >= 1e3:
        return f"AED {v/1e3:,.0f}k"
    return f"AED {v:,.0f}"


def build_report(ds, k, rep, fs, rs) -> str:
    rules = ds.rules
    n = k.network
    L: list[str] = []
    A = L.append

    A("# Analysis report")
    A("")
    if ds.is_synthetic:
        A("> **Illustrative — synthetic data.** Generated for demonstration. "
          "No Careem data is used and no figure here describes a real business.")
        A("")
    A(f"**Scope** {ds.semantic['dataset']['name']}  ·  "
      f"{n['period_start']} to {n['period_end']} ({n['days']} days)  ·  "
      f"currency {ds.currency}")
    A(f"**Data quality gate** {rep.gate}  ·  {len(rep.issues)} issue(s), "
      f"{len(rep.repairs)} repair(s) applied")
    A("")

    # ---- scorecard -------------------------------------------------------
    A("## Scorecard")
    A("")
    sc = k.scorecard()
    A("| KPI | Actual | Target | Status |")
    A("|---|---:|---:|---|")
    for _, r in sc.iterrows():
        f = (lambda v: f"{v:.1%}") if r.fmt == "pct" else (lambda v: f"{v:,.1f}")
        mark = {"on_target": "on target", "below": "below target",
                "above": "above target", "off_band": "outside band"}[r.status]
        A(f"| {r.kpi} | {f(r.actual)} | {f(r.target)} | {mark} |")
    A("")

    # ---- waterfall -------------------------------------------------------
    # Both the section title and the top line come from the waterfall config,
    # so this works for any domain. Hardcoding `gross_margin_aed` here was a
    # portability bug — a marketplace has no gross margin line.
    wf = k.margin_waterfall()
    A("## Where the value goes")
    A("")
    if not wf.empty:
        base = wf.iloc[0]
        A(f"Annualised, starting from {fmt_aed(base.aed_annualised)} of "
          f"{base['item'].lower()}.")
        A("")
        A("| Item | Annualised | Type |")
        A("|---|---:|---|")
        for _, r in wf.iterrows():
            A(f"| {r['item']} | {fmt_aed(r.aed_annualised)} | {r.kind} |")
    A("")

    # ---- findings --------------------------------------------------------
    material = fs.material(rules)
    A(f"## Findings ({len(material)} material of {len(fs)} detected)")
    A("")
    A(f"Total annualised leakage, root causes only (symptoms excluded to avoid "
      f"double counting): **{fmt_aed(fs.total_leak_aed())}**")
    A("")

    for f in fs.ranked(rules):
        if not f.is_material(rules):
            continue
        root = "root cause" if not f.caused_by else f"symptom of {', '.join(f.caused_by)}"
        A(f"### {f.id} — {f.headline}")
        A("")
        A(f"- **Impact** {fmt_aed(f.magnitude_aed)}/yr"
          + (f" (range {fmt_aed(f.magnitude_low)} – {fmt_aed(f.magnitude_high)})"
             if f.magnitude_low is not None else ""))
        A(f"- **Confidence** {f.confidence:.0%} — {f.confidence_basis}")
        A(f"- **Type** {f.category} / {f.direction} · {root}")
        if f.explains:
            A(f"- **Explains** {', '.join(f.explains)}")
        A(f"- **Method** {f.method}")
        A(f"- **How the number was derived** {f.magnitude_basis}")
        A("- **Evidence**")
        for e in f.evidence_lines():
            A(f"    - {e}")
        A("")

    # ---- recommended actions ---------------------------------------------
    A("## Recommended actions")
    A("")
    act = [r for r in rs.ranked() if r.stance == "act"]
    other = [r for r in rs.ranked() if r.stance != "act"]
    A(f"**{len(act)} actions recommended**, together worth "
      f"{fmt_aed(rs.total_net_benefit())}/yr net of the cost of doing them, "
      f"against {fmt_aed(rs.total_investment())} of one-off investment.")
    A("")
    A("| # | Action | Owner | Horizon | Effort | Net/yr | Payback | Confidence |")
    A("|---|---|---|---|---|---:|---:|---:|")
    for r in act:
        pb = ("immediate" if not r.payback_months
              else f"{r.payback_months:.1f} mo")
        A(f"| {r.id} | {r.title} | {r.owner} | "
          f"{rules['recommendations']['horizon_buckets'].get(r.horizon, r.horizon)} | "
          f"{r.effort} | {fmt_aed(r.net_annual_aed)} | {pb} | {r.confidence:.0%} |")
    A("")

    for r in rs.ranked():
        flag = {"act": "", "investigate": " — INVESTIGATE, do not act yet",
                "reject": " — NOT RECOMMENDED"}[r.stance]
        A(f"### {r.id} · {r.title}{flag}")
        A("")
        A(f"**Owner** {r.owner}  ·  **Horizon** "
          f"{rules['recommendations']['horizon_buckets'].get(r.horizon, r.horizon)}"
          f"  ·  **Effort** {r.effort}  ·  **Addresses** {', '.join(r.finding_ids)}")
        A("")
        A(r.action)
        A("")
        A("| | Annualised |")
        A("|---|---:|")
        A(f"| Benefit (after capture rate) | {fmt_aed(r.benefit_aed)} |")
        A(f"| Range | {fmt_aed(r.benefit_low)} – {fmt_aed(r.benefit_high)} |")
        A(f"| Ongoing cost | {fmt_aed(r.annual_cost_aed)} |")
        A(f"| One-off cost | {fmt_aed(r.one_off_cost_aed)} |")
        A(f"| **Net** | **{fmt_aed(r.net_annual_aed)}** |")
        A("")
        A(f"**Why** {r.rationale}")
        A("")
        A(f"**Risk** {r.risk}")
        A("")
        A(f"**Success metric** {r.success_metric}  ·  reviewed {r.review_cadence}")
        A("")
        if r.dependencies:
            A(f"**Depends on** {'; '.join(r.dependencies)}")
            A("")
        A("**Assumptions**")
        for a in r.assumptions:
            A(f"- {a}")
        A("")

    if other:
        A("### Considered and not recommended")
        A("")
        for r in other:
            A(f"- **{r.id} {r.title}** — {r.stance}. "
              f"Benefit {fmt_aed(r.benefit_aed)}/yr against cost "
              f"{fmt_aed(r.annual_cost_aed)}/yr, net "
              f"{fmt_aed(r.net_annual_aed)}/yr.")
        A("")

    # ---- not material ----------------------------------------------------
    minor = [f for f in fs.ranked(rules) if not f.is_material(rules)]
    if minor:
        A("## Detected but below the materiality floor")
        A("")
        A(f"These cleared statistical tests but fall under the "
          f"{fmt_aed(rules['materiality']['min_annualised_impact_aed'])}/yr "
          f"threshold for executive attention. Recorded so the reader can see "
          f"what was considered and set aside.")
        A("")
        A("| ID | Impact/yr | Finding |")
        A("|---|---:|---|")
        for f in minor:
            A(f"| {f.id} | {fmt_aed(f.magnitude_aed)} | {f.headline} |")
        A("")

    return "\n".join(L)


def main(profile: str = DEFAULT_PROFILE, out_dir: str | None = None):
    out = out_dir or OUT
    os.makedirs(out, exist_ok=True)
    globals()["OUT"] = out

    print(f"1/5  loading profile '{profile}' ...")
    ds = Dataset.load(verbose=False, profile=profile)

    print("2/5  data-quality gate ...")
    rep = quality.run(ds)
    print(f"     gate={rep.gate}  issues={len(rep.issues)}  repairs={len(rep.repairs)}")
    if rep.gate == "BLOCK":
        print("\nBLOCKED — the data cannot support an analysis. No brief produced.")
        rep.to_json(os.path.join(out, "data_quality_report.json"))
        return 1

    print("3/5  KPI engine ...")
    k = registry.get_kpi_engine(ds, rep)

    print("4/5  detectors ...")
    fs = registry.run_detectors(ds, k, ds.rules)
    material = fs.material(ds.rules)
    print(f"     {len(fs)} findings, {len(material)} material, "
          f"{len(fs.roots(ds.rules))} root causes")

    print("5/5  recommendations ...")
    rs = recommend.build(fs, ds, k, ds.rules)
    n_act = sum(1 for r in rs if r.stance == "act")
    print(f"     {len(rs)} recommendations, {n_act} to act on, "
          f"net AED {rs.total_net_benefit():,.0f}/yr")

    # ---- persist ---------------------------------------------------------
    rep.to_json(os.path.join(out, "data_quality_report.json"))
    with open(os.path.join(out, "data_quality_report.md"), "w") as f:
        f.write(rep.to_markdown())

    payload = {
        "dataset": ds.semantic["dataset"],
        "period": [k.network["period_start"], k.network["period_end"]],
        "quality_gate": rep.gate,
        "network_kpis": {kk: (None if pd.isna(vv) else vv) if isinstance(vv, float) else vv
                         for kk, vv in k.network.items()},
        "scorecard": k.scorecard().to_dict("records"),
        "margin_waterfall": k.margin_waterfall().to_dict("records"),
        "total_leak_aed": fs.total_leak_aed(),
        "findings": fs.as_list(),
        "recommendations": [r.as_dict() for r in rs.ranked()],
        "net_annual_benefit_aed": rs.total_net_benefit(),
        "one_off_investment_aed": rs.total_investment(),
        "data_quality": {
            "gate": rep.gate,
            "table_confidence": rep.table_confidence,
            "issues": [i.as_dict() for i in rep.issues],
            "repairs": rep.repairs,
            "checks_clean": rep.passed,
        },
    }
    with open(os.path.join(out, "findings.json"), "w") as f:
        json.dump(payload, f, indent=2, default=str)

    with open(os.path.join(out, "analysis_report.md"), "w") as f:
        f.write(build_report(ds, k, rep, fs, rs))

    print("\nwritten:")
    for p in ["findings.json", "analysis_report.md",
              "data_quality_report.md", "data_quality_report.json"]:
        print(f"  {os.path.relpath(os.path.join(out, p), ROOT)}")
    print()
    print(fs.summary_table(ds.rules).to_string(index=False))
    print()
    print(rs.table().to_string(index=False))
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Run the analysis for one profile.")
    ap.add_argument("--profile", default=DEFAULT_PROFILE,
                    help="config/<profile>/ and data/<profile>/")
    ap.add_argument("--out", default=None, help="output directory")
    a = ap.parse_args()
    raise SystemExit(main(a.profile, a.out))
