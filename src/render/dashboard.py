"""
Interactive HTML dashboard
==========================
Self-contained: charts are embedded as base64 so the file can be emailed and
still work. Filters and drill-downs are plain JS, no build step, no CDN.
"""

from __future__ import annotations

import base64
import json
import os

from .theme import PALETTE, fmt_aed


def _b64(path: str) -> str:
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def write_dashboard(p: dict, out_path: str) -> str:
    m = p["meta"]
    h = p["headline"]
    imgs = {k: _b64(v) for k, v in p["charts"].items() if os.path.exists(v)}

    findings = p["findings"]
    recs = p["recommendations"]
    scorecard = p["scorecard"]
    quality = p["quality"]

    def pct(v):
        return f"{v:.1%}" if isinstance(v, (int, float)) else v

    # ---- scorecard cards -------------------------------------------------
    cards = []
    for s in scorecard:
        good = s["status"] == "on_target"
        f = (lambda v: f"{v:.1%}") if s["fmt"] == "pct" else (lambda v: f"{v:,.1f}")
        cards.append(f"""
        <div class="kpi {'ok' if good else 'bad'}">
          <div class="kpi-label">{s['kpi']}</div>
          <div class="kpi-value">{f(s['actual'])}</div>
          <div class="kpi-target">target {f(s['target'])}</div>
        </div>""")

    # ---- findings --------------------------------------------------------
    fcards = []
    for f in findings:
        ev = "".join(f"<li>{e['label']}: <b>{_render_val(e['value'])}</b>"
                     + (f" <span class='cmp'>vs {e['comparator']}</span>" if e.get("comparator") else "")
                     + "</li>" for e in f["evidence"])
        root = ("root cause" if not f["caused_by"]
                else "symptom of " + ", ".join(f["caused_by"]))
        fcards.append(f"""
        <div class="card finding" data-cat="{f['category']}">
          <div class="card-head">
            <span class="pill pill-{f['direction']}">{f['direction']}</span>
            <span class="pill pill-cat">{f['category']}</span>
            <span class="pill pill-root">{root}</span>
            <span class="amount">{fmt_aed(f['magnitude_aed'])}/yr</span>
          </div>
          <h3>{f['headline']}</h3>
          <div class="conf">
            <div class="bar"><span style="width:{f['confidence']*100:.0f}%"></span></div>
            <small>{f['confidence']:.0%} confidence</small>
          </div>
          <details>
            <summary>Evidence and method</summary>
            <ul class="ev">{ev}</ul>
            <p class="meta"><b>Method.</b> {f['method']}</p>
            <p class="meta"><b>How the number was derived.</b> {f['magnitude_basis']}</p>
          </details>
        </div>""")

    # ---- recommendations -------------------------------------------------
    rrows = []
    for r in recs:
        pb = ("immediate" if not r["payback_months"]
              else f"{r['payback_months']:.1f} mo")
        rrows.append(f"""
        <tr class="stance-{r['stance']}">
          <td><b>{r['id']}</b></td>
          <td>{r['title']}<div class="sub">{r['owner']} · {r['effort']} effort</div></td>
          <td class="num">{fmt_aed(r['benefit_aed'])}</td>
          <td class="num">{fmt_aed(r['annual_cost_aed'] + r['one_off_cost_aed'])}</td>
          <td class="num strong">{fmt_aed(r['net_annual_aed'])}</td>
          <td class="num">{pb}</td>
          <td><span class="pill pill-{r['stance']}">{r['stance']}</span></td>
        </tr>""")

    # ---- quality ---------------------------------------------------------
    qrows = "".join(
        f"<tr><td>{i['severity']}</td><td>{i['check']}</td><td>{i['table']}</td>"
        f"<td class='num'>{i['affected_rows']:,}</td>"
        f"<td class='num'>{i['affected_pct']:.2%}</td><td>{i['detail']}</td></tr>"
        for i in quality["issues"])
    qclean = "".join(f"<li><b>{c['check']}</b> · {c['table']} — {c['detail']}</li>"
                     for c in quality["clean"])
    qrep = "".join(f"<li>{r}</li>" for r in quality["repairs"])

    chart_block = lambda key, cap: (
        f"<figure><img src='{imgs[key]}' alt='{cap}'><figcaption>{cap}</figcaption></figure>"
        if key in imgs else "")

    banner = ("<div class='synthetic'>Illustrative — synthetic data. "
              "No Careem data is used and no figure here describes a real "
              "business.</div>" if m["synthetic"] else "")

    html = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{m['title']} — {m['subtitle']}</title>
<style>
:root {{
  --green:{PALETTE['green']}; --deep:{PALETTE['deep']}; --ink:{PALETTE['ink']};
  --slate:{PALETTE['slate']}; --red:{PALETTE['red']}; --amber:{PALETTE['amber']};
  --mist:{PALETTE['mist']}; --line:{PALETTE['line']};
}}
*{{box-sizing:border-box}}
body{{margin:0;font:15px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
     color:var(--ink);background:#fff}}
header{{background:var(--deep);color:#fff;padding:30px 40px}}
header h1{{margin:0 0 4px;font-size:26px;letter-spacing:-.2px}}
header .sub{{opacity:.85;font-size:14px}}
.synthetic{{background:var(--amber);color:#2b1d00;padding:9px 40px;font-size:13px;font-weight:600}}
main{{max-width:1180px;margin:0 auto;padding:26px 40px 70px}}
h2{{font-size:19px;margin:38px 0 14px;padding-bottom:8px;border-bottom:2px solid var(--line)}}
.big{{display:flex;gap:18px;flex-wrap:wrap;margin:22px 0}}
.big div{{flex:1;min-width:190px;background:var(--mist);border-radius:10px;padding:18px 20px}}
.big .v{{font-size:29px;font-weight:700;color:var(--deep);letter-spacing:-.5px}}
.big .l{{font-size:12px;color:var(--slate);text-transform:uppercase;letter-spacing:.6px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:12px}}
.kpi{{border:1px solid var(--line);border-radius:9px;padding:13px 15px}}
.kpi.bad{{background:#fdf3f3}}
.kpi.ok{{background:#f2fbf6}}
.kpi-label{{font-size:11.5px;color:var(--slate);text-transform:uppercase;letter-spacing:.5px}}
.kpi-value{{font-size:23px;font-weight:700;margin:3px 0}}
.kpi.bad .kpi-value{{color:var(--red)}} .kpi.ok .kpi-value{{color:var(--green)}}
.kpi-target{{font-size:11.5px;color:var(--slate)}}
figure{{margin:20px 0;padding:0}}
figure img{{width:100%;border:1px solid var(--line);border-radius:9px}}
figcaption{{font-size:12.5px;color:var(--slate);margin-top:7px}}
.card{{border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:12px 0}}
.card h3{{margin:9px 0 11px;font-size:16px;line-height:1.4;font-weight:600}}
.card-head{{display:flex;gap:7px;align-items:center;flex-wrap:wrap}}
.amount{{margin-left:auto;font-weight:700;color:var(--deep);font-size:16px}}
.pill{{font-size:11px;padding:2.5px 9px;border-radius:11px;background:var(--mist);
      color:var(--slate);text-transform:uppercase;letter-spacing:.4px;font-weight:600}}
.pill-leak{{background:#fdeaea;color:var(--red)}}
.pill-opportunity{{background:#eaf7f0;color:var(--green)}}
.pill-act{{background:#eaf7f0;color:var(--green)}}
.pill-reject{{background:#fdeaea;color:var(--red)}}
.pill-investigate{{background:#fdf4e6;color:#96660f}}
.conf{{display:flex;gap:10px;align-items:center;margin-bottom:6px}}
.bar{{flex:0 0 130px;height:6px;background:var(--line);border-radius:3px;overflow:hidden}}
.bar span{{display:block;height:100%;background:var(--green)}}
.conf small{{color:var(--slate);font-size:12px}}
details{{margin-top:8px}} summary{{cursor:pointer;color:var(--deep);font-size:13.5px;font-weight:600}}
ul.ev{{margin:10px 0;padding-left:19px;font-size:13.5px}} ul.ev li{{margin:3px 0}}
.cmp{{color:var(--slate)}}
p.meta{{font-size:13px;color:var(--slate);margin:7px 0}}
table{{width:100%;border-collapse:collapse;font-size:13.5px;margin:10px 0}}
th,td{{text-align:left;padding:9px 11px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{background:var(--mist);font-size:11.5px;text-transform:uppercase;letter-spacing:.5px;color:var(--slate)}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}}
td.strong{{font-weight:700}}
tr.stance-reject td{{opacity:.62}}
.sub{{font-size:12px;color:var(--slate);margin-top:2px}}
.filters{{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}}
.filters button{{border:1px solid var(--line);background:#fff;border-radius:16px;
  padding:5px 14px;font-size:13px;cursor:pointer;color:var(--slate)}}
.filters button.on{{background:var(--deep);color:#fff;border-color:var(--deep)}}
footer{{border-top:1px solid var(--line);margin-top:44px;padding-top:16px;
  font-size:12.5px;color:var(--slate)}}
</style></head><body>
<header>
  <h1>{m['title']}</h1>
  <div class="sub">{m['subtitle']} · {m['period_start']} to {m['period_end']}
   ({m['days']} days) · prepared for the {m['prepared_for']}</div>
</header>
{banner}
<main>

<div class="big">
  <div><div class="l">Recommended actions</div><div class="v">{h['n_actions']}</div></div>
  <div><div class="l">Net annual value</div><div class="v">{fmt_aed(h['net_benefit'])}</div></div>
  <div><div class="l">One-off investment</div><div class="v">{fmt_aed(h['investment'])}</div></div>
  <div><div class="l">Identified leakage</div><div class="v">{fmt_aed(h['total_leak'])}</div></div>
</div>

<h2>Scorecard</h2>
<div class="kpis">{''.join(cards)}</div>

<h2>Where the margin goes</h2>
{chart_block('margin_waterfall', 'Annualised. Fleet cost is shown as a cost of doing business, not a leak.')}

<h2>Findings</h2>
<div class="filters" id="filters">
  <button class="on" data-f="all">All</button>
  <button data-f="service">Service</button>
  <button data-f="procurement">Procurement</button>
  <button data-f="waste">Waste</button>
  <button data-f="assortment">Assortment</button>
  <button data-f="fleet">Fleet</button>
  <button data-f="demand">Demand</button>
</div>
<div id="findings">{''.join(fcards)}</div>

<h2>Diagnosis</h2>
{chart_block('store_diagnosis', 'Fill rate on the x-axis is what separates a fleet problem from a stock problem.')}
{chart_block('fill_rate_by_dow', 'Replenishment is reviewed on the two quietest days of the week.')}
{chart_block('supplier_reliability', 'On-time-in-full against target, with lead-time variability alongside.')}
{chart_block('waste_by_market', 'Write-off is concentrated, not spread.')}
{chart_block('pareto', 'Cumulative revenue by SKU rank.')}
{chart_block('demand_shape', 'Daily orders with the recurring peak window highlighted.')}

<h2>Recommended actions</h2>
{chart_block('action_value', 'Net of the cost of acting. Anything below zero is reported, not hidden.')}
<table>
  <thead><tr><th>#</th><th>Action</th><th>Benefit/yr</th><th>Cost</th>
  <th>Net/yr</th><th>Payback</th><th>Stance</th></tr></thead>
  <tbody>{''.join(rrows)}</tbody>
</table>

<h2>Data quality</h2>
<p>Gate: <b>{quality['gate']}</b>. {len(quality['issues'])} issue(s) found,
{len(quality['repairs'])} repair(s) applied before analysis.</p>
<table>
  <thead><tr><th>Severity</th><th>Check</th><th>Table</th><th>Rows</th>
  <th>%</th><th>Detail</th></tr></thead>
  <tbody>{qrows}</tbody>
</table>
<details><summary>Repairs applied</summary><ul>{qrep}</ul></details>
<details><summary>Checks that ran clean</summary><ul>{qclean}</ul></details>

<footer>
  Generated by the Decision Brief Generator. Every figure traces to a row in the
  source data; every recommendation carries its assumptions. Currency {m['currency']}
  (USD at {m['fx_usd']}).
</footer>
</main>
<script>
const btns=document.querySelectorAll('#filters button');
btns.forEach(b=>b.onclick=()=>{{
  btns.forEach(x=>x.classList.remove('on')); b.classList.add('on');
  const f=b.dataset.f;
  document.querySelectorAll('.finding').forEach(c=>{{
    c.style.display=(f==='all'||c.dataset.cat===f)?'':'none';
  }});
}});
</script>
</body></html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def _render_val(v):
    if isinstance(v, float):
        if 0 < abs(v) < 1:
            return f"{v:.1%}"
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    if isinstance(v, int):
        return f"{v:,}"
    return v
