# Project Handoff — Decision Brief Generator (Careem)

**Last updated:** 2026-08-02
**Owner:** Tulaib (misbahamid30@gmail.com)
**Status:** **COMPLETE, and portability-tested on a second domain.**
Supply chain 26/26, rides 10/10. See `PORTABILITY.md` for what broke and what it cost.
Submission pack prepared — see `SUBMISSION.md` for the three Careem deliverables
and exact publishing steps. Two placeholder URLs in `README.md` still need the
real GitHub Pages and Google Drive links pasted in.

**Two profiles:** `careem_quik` (supply chain) and `careem_rides` (marketplace).
```
python src/build_outputs.py                                          # supply chain
python src/build_outputs.py --profile careem_rides --out outputs_rides
python src/verify_outputs.py    # 26/26      python src/verify_rides.py   # 10/10
```

**Run everything:** `python src/build_outputs.py` — analysis, charts and all three
deliverables. See `RUNNING.md` for full setup and troubleshooting.
**Dependencies:** `pip install -r requirements.txt`; `npm install` (optional, only
for .docx/.pptx). The builder locates `node_modules` automatically — project-local
first, then global npm root, then `/tmp`. Degrades gracefully if Node is absent.

**Run the pipeline:** `python3 src/run_analysis.py` from the project root.
**Data lives in** `data/careem_quik/` (note: `data/dummy/` is a superseded earlier
generation the OS would not let me overwrite — safe to delete manually).
**Workspace:** `C:\Users\misba\Desktop\Decision Brief Generator`

---

## 1. Resume prompt (paste this into a new chat)

> I'm continuing a project called **Decision Brief Generator**. The working folder is
> `C:\Users\misba\Desktop\Decision Brief Generator`. Read `Project-Handoff.md` and `TASKS.md`
> in that folder first — they contain the full context, all decisions made so far, the
> architecture, and where we left off.
>
> Rules for this project, carry them forward:
> 1. Guide me through each part — don't build everything silently. Propose, get sign-off, then build.
> 2. Always ask me for any files you need to see rather than assuming.
> 3. Always tell me which tools, apps, integrations or connectors would help.
> 4. Keep `Project-Handoff.md` current after every meaningful step, including this resume prompt.
> 5. Keep `TASKS.md` current — every task, its status, and what it produced.
>
> Tell me what the next step is and confirm you have everything you need.

---

## 2. What we're building

A tool that turns **raw business data into expert-level summaries and data-backed recommended
action plans**. Not a chart generator — a decision instrument. The output answers: *what happened,
why, how confident are we, what should we do, what will it be worth, and what does it cost.*

### Context
- Built as a **portfolio / showcase project** for a **Supply Chain Director** role at **Careem**.
- Data is **synthetic (dummy)** — the point is to demonstrate the tool's capability, not to
  report real Careem numbers. Every output must be visibly labelled as illustrative.
- Business line: most likely **Careem Food / Quik** (grocery + food delivery supply chain).
- Audience for the generated briefs: **executive / leadership**. Decision-first, rigour underneath.

---

## 3. Decisions locked in

| # | Decision | Choice | Date |
|---|----------|--------|------|
| D1 | Form factor | Claude skill + Python pipeline. Analysis in clean Python, narrative by Claude. Portable to a standalone app later. | 2026-08-02 |
| D2 | Data source | CSV / Excel files dropped into the project folder | 2026-08-02 |
| D3 | Domain | Careem — Food / Quik supply chain | 2026-08-02 |
| D4 | Audience | Executive / leadership | 2026-08-02 |
| D5 | Outputs | Three: Word/PDF exec brief, interactive HTML dashboard, PowerPoint deck | 2026-08-02 |
| D6 | Data realism | Synthetic data with deliberately planted signals, so we can verify the tool actually finds them | 2026-08-02 |
| D7 | Market | **UAE only** — Dubai, Abu Dhabi, Sharjah. 12 dark stores. | 2026-08-02 |
| D8 | Period | Jan 2025 – Jun 2026, daily grain. Chosen so seasonality (2 Ramadans, summer) is demonstrable. | 2026-08-02 |
| D9 | Currency | AED default, USD toggle at 3.6725 peg | 2026-08-02 |
| D10 | Palette | Careem brand green/teal | 2026-08-02 |
| D11 | Scenario | **Careem Quik** dark-store grocery network — densest supply-chain surface in the business | 2026-08-02 |
| D12 | Data origin | Self-created synthetic. Rejected Kaggle: no public dataset matches quick-commerce dark stores, and self-created data lets us plant verifiable signals. Company brief explicitly permits self-created data. | 2026-08-02 |

### Open questions
- **Q5. (blocking-ish)** The user quoted a line from a company assessment brief:
  *"Use any public or dummy data (e.g. Kaggle, data.gov, or self-created), if required. Avoid
  using any confidential information."* — **the full brief has not been shared yet.** It likely
  specifies the actual business question, deliverable format, and time limit. Ask for it.
- **Q6.** Is there a submission deadline?

---

## 4. Architecture

```
raw files (CSV/XLSX)
        │
        ▼
┌───────────────────┐
│ 1. INGEST         │  load, type-infer, profile, dedupe
│                   │  → data_quality_report.json  (gates everything downstream)
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 2. SEMANTIC LAYER │  config maps columns → business concepts
│                   │  (date, city, dark_store, sku, category, qty, cost,
│                   │   revenue, supplier, lead_time, stockout_flag, waste)
│                   │  + business rules: targets, thresholds, cost assumptions
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 3. ANALYSIS       │  trend & seasonality · variance decomposition ·
│    ENGINE         │  anomaly detection · Pareto/ABC · segment contribution ·
│                   │  supply-chain KPIs · driver correlation
│                   │  → findings[] each with evidence, magnitude, confidence
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 4. INSIGHT        │  score findings: materiality × confidence × actionability
│    RANKING        │  dedupe overlapping findings, keep the root cause
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 5. RECOMMENDATION │  finding → action, with owner, effort, expected impact
│    ENGINE         │  range, risk, dependencies, how to measure success
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ 6. RENDER         │  brief.docx / brief.pdf · dashboard.html · deck.pptx
│                   │  all from one insight payload → numbers can never disagree
└───────────────────┘
```

**Design principle:** every sentence in the brief carries a traceable number, and every number
traces back to a row in the source data. No unsupported assertions.

### Supply-chain KPIs the engine will compute
Fill rate · OTIF (on-time in-full) · stockout rate & lost-sales estimate · days of cover ·
inventory turns · wastage / shrink rate · supplier lead-time mean and variance ·
forecast error (MAPE/bias) · perfect-order rate · cost-to-serve per order · courier
utilisation and drop density.

---

## 5. Folder structure (target)

```
Decision Brief Generator/
├─ Project-Handoff.md          ← this file
├─ TASKS.md                    ← task register
├─ ARCHITECTURE.md             ← detailed design
├─ data/
│  ├─ raw/                     ← input CSV/XLSX
│  └─ dummy/                   ← generated synthetic Careem dataset
├─ config/
│  ├─ semantic_map.yaml        ← column → business concept mapping
│  └─ business_rules.yaml      ← targets, thresholds, cost assumptions
├─ src/
│  ├─ ingest.py
│  ├─ quality.py
│  ├─ analysis/
│  ├─ insights.py
│  ├─ recommend.py
│  └─ render/
├─ outputs/                    ← generated briefs, dashboards, decks
└─ skill/
   └─ SKILL.md                 ← the reusable Claude skill wrapper
```

---

## 6. Tools, apps and integrations

### Already available in this environment
| Tool | Use |
|------|-----|
| Python sandbox (pandas, numpy, scipy, statsmodels) | The whole analysis engine |
| `docx` / `pdf` / `pptx` / `xlsx` skills | Output rendering |
| Google Drive connector | If you want inputs/outputs synced to Drive |
| Gmail + Google Calendar connectors | Emailing briefs, scheduling recurring runs |
| Scheduled tasks | Run the brief automatically each Monday |
| Live artifacts | Persist the dashboard so it refreshes on open |
| Canva connector | Polishing the deck visually if you want it presentation-grade |

### Worth adding (optional, not blocking)
| Tool | Why |
|------|-----|
| A database connector (Postgres/Snowflake/BigQuery) | Only if you later want live data instead of CSVs |
| Power BI / Tableau | Only if the target audience already lives there — our HTML dashboard covers the showcase need |

**Nothing needs to be purchased or installed to complete this project.** Everything above that
matters is already connected.

---

## 7. What I need from you

1. **The full text of the company assessment brief** (see Q5). This is the highest-value
   missing input — it may define the exact question to answer and the deliverable expected.
2. **Sign-off on `ARCHITECTURE.md`** before Phase 2 build starts.

**No connectors or files are needed.** All data is self-generated. Confirmed 2026-08-02.

---

## 8. Progress log

| Date | What happened |
|------|---------------|
| 2026-08-02 | Project kicked off. Requirements gathered via structured questions. Decisions D1–D6 locked. Architecture drafted. Task register created (9 phases). |
| 2026-08-02 | Q1–Q4 answered → D7–D12. `ARCHITECTURE.md` written: Careem Quik dark-store scenario, 8-table data model, 6 planted signals, pipeline, exec-brief format, Careem palette. Phase 1 complete. |
| 2026-08-02 | **Phase 2 complete.** `src/generate_dummy_data.py` written and calibrated over three passes. Dataset generated: 483,134 orders (~111/store/day), 1.62M order lines, 737,100 inventory rows, 123k PO lines — 125 MB across 9 CSVs in `data/dummy/`. `data/DATA_DICTIONARY.md` documents every column plus ground truth. `src/verify_signals.py` is the acceptance test — **6/6 planted signals verified present**. |
| 2026-08-03 | **Portability tested on a second domain — the claim was wrong and is now fixed and documented.** Built `careem_rides`: a two-sided marketplace (344k trips, 131k zone-hours, 2,600 captains) with no inventory, suppliers or shelf life. Six code changes were needed: (1) `KPIEngine` named supply-chain tables in 20 places → split into `kpi_base.py` + per-domain engines; (2) scorecard and waterfall were hardcoded lists → now config-driven; (3) date parsing guessed from name suffixes and silently failed on `requested_at` → now reads the semantic map's declarations; (4) recommendation templates keyed on finding-ID prefix collided (`SUP` = supplier and supply) and crashed three files from the cause → domain-scoped registry; (5) payload builder and report writer referenced `gross_margin_aed` by name; (6) deck narrative slides carried hardcoded supply-chain prose → now built from the tagged finding's own evidence. Added `Evidence.role="rules_out"` so renderers find the ruling-out evidence structurally rather than by scanning prose. **Rides: 10/10 checks, all 3 planted signals recovered including a second misdiagnosis trap (surge at 1.76× with supply correlating −0.45). Supply chain: still 26/26, identical numbers.** Full write-up in `PORTABILITY.md`. Config moved to `config/<profile>/`; both runners take `--profile`. |
| 2026-08-02 | **Phases 7 and 8 complete — project finished.** `skill/SKILL.md` makes the pipeline reusable: adaptation guide for `semantic_map.yaml` / `business_rules.yaml`, the eight rules the pipeline enforces, and the five traps it is built to avoid. `README.md` written. `src/verify_outputs.py` verifies the brief **without using any pipeline code** — it recomputes every headline figure straight from the CSVs with independent pandas, on the grounds that verifying an analysis by calling the same engine only proves the engine is deterministic. **26/26 checks passed**: ground truth 7/7 (all six planted signals surfaced, including the misdiagnosis trap correctly attributed to fleet), arithmetic 5/5, recomputation 7/7 (fill rate, waste, OTIF, delivery p50, cancel rate, and two figures quoted inside headlines all match to 4dp), integrity 7/7. Notable: excluding symptoms from the leakage total prevents **AED 781k of double counting**. |
| 2026-08-02 | **Phase 6 complete.** `src/render/` — theme, 8 matplotlib charts, self-contained HTML dashboard, `brief_docx.js` (13-page Word brief), `deck_pptx.js` (10-slide deck). `src/build_outputs.py` orchestrates. All three read one payload so figures cannot diverge. Visual QA caught four real defects, all fixed: waterfall drawing doubled bars; a chart title overclaimed ("best availability" when a peer was marginally higher); two slides had large dead space; and — the significant one — a `bullet()` helper wrapped already-built TextRuns in another TextRun, silently blanking **every appendix bullet** in the Word brief. That defect is invisible in code and only shows up on render, which is why the visual QA step is not optional. pptx validation PASSED. |
| 2026-08-02 | **Phase 5 complete.** `src/recommend.py` — 7 recommendations from 6 root-cause findings, each with owner, horizon, effort, capture-rate-adjusted benefit, costed downside, payback and success metric. Net AED 727k/yr on AED 103k one-off. Three design points: capture rates are declared in config and never 100%; the cost of acting is netted off so a recommendation can reject itself (R5b does — AED 111k cost against AED 83k benefit); confidence below 0.65 downgrades an item from "act" to "investigate". Found and fixed a real annualisation bug — Ramadan is an annually recurring window, so applying the 365/period factor understated it by a third and had silently pushed it below the materiality floor. |
| 2026-08-02 | **Phase 4 complete.** `src/findings.py` (Finding/Evidence objects, confidence model, ranking, root-cause linking), `src/analysis/kpi.py` (KPI engine at 10 grains, margin waterfall, scorecard), `src/analysis/detectors.py` (8 detectors), `src/run_analysis.py` (runner). Result: 12 findings, 6 material, AED 983k/yr of un-double-counted leakage. **All 6 planted signals independently recovered** — S1→SUP-01, S2→WST-01+LOT-01, S3→AST-01, S4→CAD-01, S5→FLT-01, S6→SEA-01. Four calibration corrections made: (a) two generator bugs fixed — supplier timing modelled as "usually perfect, occasionally bad" rather than continuous jitter (OTIF 43%→91%), and fleet economics corrected (AED 24.7→9.78 per order); (b) cadence detector reads the *review* calendar not receipt dates, which is what actually sizes the order; (c) waste findings roll up to market level when the pattern spans multiple stores; (d) lot-size detector gated at 0.5 units/day velocity so it cannot double-count the assortment tail. |
| 2026-08-02 | **Phase 3 complete.** Semantic layer (`config/semantic_map.yaml`, 39 concepts) and business rules (`config/business_rules.yaml` — targets, cost assumptions, quality gate, materiality floors) written. `src/ingest.py` loads/profiles/compacts all 9 tables and auto-joins facts to dimensions. `src/quality.py` runs 8 check families and emits a gated report. Result: all 4 injected defects caught, 12 FK relationships and 3 cross-table reconciliations clean, gate = **WARN**, table confidence 88–100%. Two design corrections made during build: (a) percentile winsorising replaced with a hard physical ceiling, because p99.5 clipping destroyed the DS07 slow-service signal — verified DS07 mean delivery unchanged at 31.81 min post-repair; (b) confidence penalties now discount deterministically-repaired issues to 25% residual rather than treating them as ongoing uncertainty. Next: Phase 4 analysis engine. |
