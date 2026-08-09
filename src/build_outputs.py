"""
Output builder — phase 6
========================
Runs the analysis, draws the charts, and renders all three deliverables from a
single payload:

    outputs/Decision-Brief.docx      executive brief
    outputs/dashboard.html           interactive dashboard
    outputs/Decision-Brief.pptx      leadership deck

One payload, three renderers. A number cannot differ between the document, the
dashboard and the deck, because none of them recompute anything.

    python3 src/build_outputs.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ingest import Dataset, ROOT, DEFAULT_PROFILE
import quality
import recommend
import run_analysis
from analysis import registry
from render.theme import fmt_aed
from render.dashboard import write_dashboard

OUT = os.path.join(ROOT, "outputs")
CHARTS = os.path.join(OUT, "charts")


def find_node_modules() -> str | None:
    """Locate docx/pptxgenjs, preferring a project-local install.

    Checked in order so the same code runs on Windows, macOS and Linux:
    a node_modules beside this project, then a global npm root, then the
    sandbox location used during development.
    """
    candidates = [
        os.path.join(ROOT, "node_modules"),
        os.environ.get("NODE_PATH", ""),
        "/tmp/node_modules",
    ]
    try:
        import subprocess as _sp
        g = _sp.run(["npm", "root", "-g"], capture_output=True, text=True,
                    shell=(os.name == "nt"))
        if g.returncode == 0:
            candidates.insert(1, g.stdout.strip())
    except Exception:
        pass

    for c in candidates:
        if c and os.path.isdir(os.path.join(c, "docx")):
            return c
    return None


def build_payload(ds, k, rep, fs, rs, chart_paths) -> dict:
    rules = ds.rules
    n = k.network
    material = [f for f in fs.ranked(rules) if f.is_material(rules)]

    # The top line comes from the waterfall config, not a named metric — a
    # marketplace has no "gross margin" row, and hardcoding one here meant the
    # payload builder only worked for the first domain.
    wf = k.margin_waterfall()
    top_line = float(wf.iloc[0].aed_annualised) if not wf.empty else 0.0
    top_label = str(wf.iloc[0]["item"]) if not wf.empty else "Top line"

    return {
        "meta": {
            "title": "Supply Chain Decision Brief",
            "subtitle": ds.semantic["dataset"]["name"],
            "period_start": n["period_start"],
            "period_end": n["period_end"],
            "days": n["days"],
            "currency": ds.currency,
            "fx_usd": ds.semantic["dataset"]["fx"]["USD"],
            "synthetic": ds.is_synthetic,
            "prepared_for": rules["meta"]["owner"],
            "quality_gate": rep.gate,
        },
        "headline": {
            "net_benefit": rs.total_net_benefit(),
            "investment": rs.total_investment(),
            "total_leak": fs.total_leak_aed(),
            "gross_margin": top_line,
            "top_line_label": top_label,
            "n_actions": sum(1 for r in rs if r.stance == "act"),
        },
        "scorecard": k.scorecard().to_dict("records"),
        "waterfall": wf.to_dict("records"),
        "findings": [f.as_dict() for f in material],
        "all_findings": [f.as_dict() for f in fs.ranked(rules)],
        "recommendations": [r.as_dict() for r in rs.ranked()],
        "quality": {
            "gate": rep.gate,
            "issues": [i.as_dict() for i in rep.issues],
            "repairs": rep.repairs,
            "clean": rep.passed,
            "confidence": rep.table_confidence,
            "rows": rep.row_counts,
        },
        "narrative": rules.get("narrative", {}),
        "assumptions": {
            "costs": rules["costs"],
            "capture_rate": rules["recommendations"]["capture_rate"],
            "cost_assumptions": rules["recommendations"]["cost_assumptions"],
            "materiality": rules["materiality"],
        },
        "charts": {kk: os.path.abspath(vv) for kk, vv in chart_paths.items()},
    }


def run_node(script: str, payload_path: str, out_path: str) -> bool:
    node_modules = find_node_modules()
    if node_modules is None:
        print(f"  ! skipped {os.path.basename(script)} — Node packages not found.")
        print(f"    Install them once, from the project folder:")
        print(f"        npm install docx pptxgenjs")
        print(f"    The dashboard and the analysis outputs are unaffected.")
        return False

    env = dict(os.environ, NODE_PATH=node_modules)
    try:
        r = subprocess.run(["node", script, payload_path, out_path],
                           capture_output=True, text=True, env=env,
                           shell=(os.name == "nt"))
    except FileNotFoundError:
        print(f"  ! skipped {os.path.basename(script)} — Node.js is not installed.")
        print(f"    Install Node 18+ from nodejs.org, then: npm install docx pptxgenjs")
        return False

    if r.returncode != 0:
        print(f"  ! {os.path.basename(script)} failed")
        print(r.stdout[-2500:])
        print(r.stderr[-2500:])
        return False
    print(r.stdout.strip())
    return True


def main(profile: str = DEFAULT_PROFILE, out_dir: str | None = None):
    out = out_dir or OUT
    charts_dir = os.path.join(out, "charts")
    os.makedirs(charts_dir, exist_ok=True)

    print(f"running analysis for profile '{profile}' ...")
    ds = Dataset.load(verbose=False, profile=profile)
    rep = quality.run(ds)
    if rep.gate == "BLOCK":
        print("BLOCKED by the data-quality gate — no brief produced.")
        return 1
    k = registry.get_kpi_engine(ds, rep)
    fs = registry.run_detectors(ds, k, ds.rules)
    rs = recommend.build(fs, ds, k, ds.rules)
    print(f"  {len(fs)} findings, {sum(1 for r in rs if r.stance=='act')} actions, "
          f"net {fmt_aed(rs.total_net_benefit())}/yr")

    print("drawing charts ...")
    chart_paths = registry.get_charts(ds).build_all(k, fs, rs, charts_dir)
    for name in chart_paths:
        print(f"  {name}.png")

    payload = build_payload(ds, k, rep, fs, rs, chart_paths)
    payload_path = os.path.join(out, "brief_payload.json")
    with open(payload_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    # Also write everything run_analysis.py produces. This used to be split, so
    # "build_outputs.py does everything" was false — it skipped the markdown
    # reports, and the verification script then failed on their absence for
    # anyone who followed the documented path.
    print("writing analysis reports ...")
    rep.to_json(os.path.join(out, "data_quality_report.json"))
    with open(os.path.join(out, "data_quality_report.md"), "w") as f:
        f.write(rep.to_markdown())
    with open(os.path.join(out, "analysis_report.md"), "w") as f:
        f.write(run_analysis.build_report(ds, k, rep, fs, rs))
    for name in ("data_quality_report.md", "analysis_report.md"):
        print(f"  {name}")

    print("rendering dashboard ...")
    dash = write_dashboard(payload, os.path.join(out, "dashboard.html"))
    print(f"  {dash}")

    # Keep the GitHub Pages copy in sync. Copying it by hand once meant the
    # published dashboard silently kept stale chart images after later rebuilds
    # — the numbers still matched, so nothing looked wrong.
    if profile == DEFAULT_PROFILE:
        pages = os.path.join(ROOT, "docs", "index.html")
        if os.path.isdir(os.path.dirname(pages)):
            shutil.copyfile(dash, pages)
            print(f"  docs/index.html (GitHub Pages copy)")

    here = os.path.dirname(os.path.abspath(__file__))
    print("rendering Word brief ...")
    run_node(os.path.join(here, "render", "brief_docx.js"), payload_path,
             os.path.join(out, "Decision-Brief.docx"))

    print("rendering deck ...")
    run_node(os.path.join(here, "render", "deck_pptx.js"), payload_path,
             os.path.join(out, "Decision-Brief.pptx"))

    print("\ndone.")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build all deliverables for a profile.")
    ap.add_argument("--profile", default=DEFAULT_PROFILE)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    raise SystemExit(main(a.profile, a.out))
