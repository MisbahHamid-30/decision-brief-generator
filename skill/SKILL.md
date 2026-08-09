---
name: decision-brief
description: "Turn a folder of raw operational data (CSV/Excel) into an executive decision brief with quantified findings, root-cause analysis and costed recommendations. Use when someone has business data and needs to know what is going wrong, what it is worth, and what to do about it — not just what the numbers are. Produces a Word brief, an interactive HTML dashboard and a PowerPoint deck from one analysis. Triggers: 'analyse this data and tell me what to do', 'decision brief', 'what's driving X', 'where are we losing money', 'turn this into a board paper', 'find the problems in this dataset'. Do NOT use for one-off metric lookups, chart requests, or exploratory data questions — this builds a decision instrument, which is heavier than those need."
---

# Decision Brief Generator

Turns raw operational data into an expert-level summary and a costed action plan.

The distinction this skill exists to hold: a dashboard reports numbers, a decision
brief tells someone what to do and what it is worth. The difference is not
presentation — it is that every claim carries evidence, every recommendation
carries the cost of acting, and the analysis is allowed to conclude that the
obvious answer is wrong.

## Pipeline

```
data/*.csv
  → ingest      load, profile, compact, join facts to dimensions
  → quality     8 check families; PASS / WARN / BLOCK
  → KPI engine  every metric once, at every grain
  → detectors   findings with evidence, method, confidence
  → ranking     materiality × confidence × actionability; root-cause linking
  → recommend   actions with owner, cost, payback, success metric
  → render      Word · HTML dashboard · PowerPoint
```

Run it:

```bash
python3 src/run_analysis.py     # analysis only → findings.json, analysis_report.md
python3 src/build_outputs.py    # everything    → .docx, .html, .pptx, charts
python3 src/verify_signals.py   # acceptance test against known ground truth
```

Node dependencies for the document renderers:

```bash
cd /tmp && npm install docx pptxgenjs
```

## Pointing it at a different dataset

Two config files carry everything domain-specific. No analysis code changes.

**`config/semantic_map.yaml`** binds raw columns to business concepts. Analysis
code never names a raw column — it asks for a concept (`sold_units`, `revenue`,
`city`) and the map resolves it. Declare:

- `tables` — file, role (`fact` / `dimension` / `bridge`), primary key or grain,
  date column, foreign keys
- `concepts` — concept name → `{table, column, kind}`. `kind` drives behaviour:
  `measure` and `money` are checked for impossible negatives, `date` is parsed,
  `dimension` is used for segmentation
- `derived` — formulas the KPI engine evaluates

**`config/business_rules.yaml`** carries judgement:

- `targets` — what good looks like, with `direction` (`higher_better`,
  `lower_better`, `band`)
- `costs` — how an operational failure converts to money. Every assumption here
  ends up disclosed in the brief appendix, so write the reasoning in the `_note`
  fields
- `quality_gate` — thresholds and severities; `critical` blocks the analysis
- `materiality` — the floor below which a finding is recorded but not surfaced
- `recommendations` — capture rates, cost assumptions, valid owners, payback window

If the new domain needs a detector that does not exist, add it to
`src/analysis/detectors.py` and register it in `ALL_DETECTORS`. A detector takes
`(ds, k, rules)` and returns `list[Finding]`.

## Rules the pipeline enforces

These are the parts that make the output trustworthy. Do not relax them to make
a brief look stronger.

**1. Every claim carries its evidence.** A `Finding` holds the numbers that
produced it, the method that derived them, and the confidence in both. If a
sentence in the brief has no Finding behind it, it does not get written.

**2. Refusing to answer is a valid outcome.** The quality gate can return
`BLOCK`, and then no brief is produced. A tool that always answers is not one
anyone should trust.

**3. Confidence is a geometric mean of three components** — statistical strength,
sample adequacy, source-table quality. Geometric so that one weak component
drags the result down and no strong component can rescue it.

**4. Capture rates are never 100%.** A finding worth AED 500k does not become a
AED 500k recommendation. Some part of every leak is structural.

**5. The cost of acting is netted off, and a recommendation may reject itself.**
Knowing the obvious fix does not pay is worth as much as knowing which one does.

**6. Root causes are reported, symptoms are not.** `link_root_causes()` connects
findings so the same money is not counted twice under two owners.

**7. Below the confidence threshold, an action becomes "investigate".**
Recommending action on weak evidence is how analysis loses credibility with the
people who have to execute it.

**8. State what the data cannot support.** The appendix limitations section is
required, not optional. It is usually the most credible page in the document.

## Traps this pipeline is built to avoid

Worth knowing, because they are easy to reintroduce.

**Cleaning that deletes the finding.** Winsorising outliers at a percentile is
standard practice and was actively wrong here — the long right tail of delivery
times *was* the signal. Cap at a physical impossibility instead, and leave every
credible extreme alone.

**Unit conversions that silently suppress findings.** An annually recurring event
is already an annual figure; applying a `365 / period_days` factor to it
understates it and can push a real finding below the materiality floor.

**Two detectors billing for one problem.** Overlapping detectors each attaching a
full price tag inflates the total. Gate them against each other explicitly — the
lot-size detector carries a velocity floor precisely so it cannot claim the
assortment tail's write-off.

**Reporting one cause as many symptoms.** Waste appearing in six stores is one
finding at market level, not six at store level. Raise findings at the coarsest
grain that still explains them.

**Diagnosing from symptoms alone.** Slow service and cancellations look identical
whether the cause is empty shelves or too few riders. The distinguishing test is
whether the stock was there. Always look for the measurement that *rules out*
the intuitive explanation.

## Output structure

The brief is decision-first:

| § | Section | Purpose |
|---|---------|---------|
| 1 | The decision | The ask, before any analysis |
| 2 | Executive summary | Top findings, one line each, with magnitude and confidence |
| 3 | Where the margin goes | Waterfall from gross margin to net |
| 4 | What is going wrong | Top root causes with full evidence chains |
| 5 | Recommended actions | Owner, cost, net value, payback, risk, success metric |
| 6 | Considered and not recommended | What was analysed and rejected, with the arithmetic |
| 7 | What we would measure | Leading indicators and review cadence |
| 8 | Appendix | Method, data quality, assumptions, limitations |

Charts are titled with the answer, not the variables. "Availability drains across
the weekend" rather than "Fill rate by day of week" — the second makes the reader
do work the analysis should already have done.

## Verification

`src/verify_signals.py` is the acceptance test. For the bundled demo dataset it
confirms six deliberately planted signals are recovered, including one designed
as a misdiagnosis trap. When adapting to a new domain, write the equivalent: a
known truth the pipeline must find unaided. Without it, "the analysis found five
problems" is unfalsifiable.

## Files

```
config/semantic_map.yaml     column → concept binding
config/business_rules.yaml   targets, costs, gates, materiality
src/ingest.py                loading, profiling, semantic access
src/quality.py               the gate
src/findings.py              Finding, Evidence, confidence, ranking
src/analysis/kpi.py          KPI engine
src/analysis/detectors.py    the detectors
src/recommend.py             actions and their economics
src/render/                  charts, dashboard, docx, pptx
src/run_analysis.py          analysis runner
src/build_outputs.py         full build
src/verify_signals.py        acceptance test
```
