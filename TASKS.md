# Task Register — Decision Brief Generator

**Legend:** ⬜ pending · 🟦 in progress · ✅ done · ⛔ blocked

| # | Phase | Task | Status | Output | Notes |
|---|-------|------|--------|--------|-------|
| 1 | 0 | Project setup and handoff scaffolding | ✅ | `Project-Handoff.md`, `TASKS.md` | Done 2026-08-02 |
| 2 | 1 | Architecture and scenario design | ✅ | `ARCHITECTURE.md` | Scenario, data model, 6 planted signals, pipeline, brief format, palette. Done 2026-08-02 |
| 3 | 2 | Build dummy Careem supply chain dataset | ✅ | `src/generate_dummy_data.py`, `data/dummy/*.csv` (125 MB), `data/DATA_DICTIONARY.md`, `src/verify_signals.py` | 483k orders, 1.62M lines, 737k inventory rows. **6/6 planted signals verified.** Done 2026-08-02 |
| 4 | 3 | Ingestion + data-quality layer | ✅ | `config/semantic_map.yaml`, `config/business_rules.yaml`, `src/ingest.py`, `src/quality.py`, `outputs/data_quality_report.{json,md}` | 39 concepts mapped, 12 FK relationships validated, 8 issues found, all 4 injected defects caught, 3 reconciliation checks clean. Gate = WARN. Done 2026-08-02 |
| 5 | 4 | Analysis engine | ✅ | `src/findings.py`, `src/analysis/kpi.py`, `src/analysis/detectors.py`, `src/run_analysis.py`, `outputs/findings.json`, `outputs/analysis_report.md` | 8 detectors, 12 findings, 6 material, all 6 planted signals recovered. Done 2026-08-02 |
| 6 | 5 | Insight ranking + recommendation engine | ✅ | `src/recommend.py`, action plan in `outputs/analysis_report.md` + `findings.json` | 7 recommendations, 6 to act on, AED 727k/yr net on AED 103k one-off. R5b self-rejects on negative net. Done 2026-08-02 |
| 7 | 6 | Output renderers (DOCX/PDF, HTML, PPTX) | ✅ | `src/render/{theme,charts,dashboard}.py`, `src/render/{brief_docx,deck_pptx}.js`, `src/build_outputs.py`, `outputs/Decision-Brief.{docx,pptx}`, `outputs/dashboard.html` | 8 charts, 13-page brief, 10-slide deck, self-contained dashboard. All from one payload. pptx validation PASSED. Done 2026-08-02 |
| 8 | 7 | Wrap as reusable Claude skill | ✅ | `skill/SKILL.md`, `README.md` | Skill definition with adaptation guide, enforced rules, and the five traps the pipeline avoids. Done 2026-08-02 |
| 9 | 8 | End-to-end run and verification | ✅ | `src/verify_outputs.py`, `outputs/verification_report.txt`, `outputs/verification_signals.txt` | **26/26 checks passed.** Ground truth 7/7, arithmetic 5/5, recomputation 7/7, integrity 7/7. Done 2026-08-02 |

---

## Project complete

All 9 tasks closed 2026-08-02. Entry points:

```bash
python3 src/build_outputs.py     # full build → .docx, .pptx, .html, charts
python3 src/run_analysis.py      # analysis only
python3 src/verify_signals.py    # planted-signal acceptance test (6/6)
python3 src/verify_outputs.py    # independent verification (26/26)
```

### Possible next steps, if wanted

- Sensitivity analysis on the two soft assumptions (supplier pack premium, demand migration)
- A PDF export of the Word brief
- Live artifact so the dashboard refreshes on open
- A second dataset to prove the semantic layer really is portable

---

## Decision log

| # | Decision | Choice | Date |
|---|----------|--------|------|
| D1 | Form factor | Claude skill + Python pipeline | 2026-08-02 |
| D2 | Data source | CSV / Excel uploads | 2026-08-02 |
| D3 | Domain | Careem — Food / Quik supply chain | 2026-08-02 |
| D4 | Audience | Executive / leadership | 2026-08-02 |
| D5 | Outputs | Word/PDF brief + HTML dashboard + PPTX deck | 2026-08-02 |
| D6 | Data realism | Synthetic with planted signals for verification | 2026-08-02 |

## Open questions awaiting answer

| # | Question | Status |
|---|----------|--------|
| Q1 | Markets | ✅ UAE only — Dubai, Abu Dhabi, Sharjah |
| Q2 | Time window | ✅ Jan 2025 – Jun 2026, daily |
| Q3 | Currency | ✅ AED default, USD toggle |
| Q4 | Palette | ✅ Careem brand |
| Q5 | **Full company assessment brief text** | ⛔ **Outstanding — highest value missing input** |
| Q6 | Submission deadline | ⛔ Outstanding |

## Additions to build (added 2026-08-02)

- D7–D12 recorded in `Project-Handoff.md`
- Six planted signals specified in `ARCHITECTURE.md` §3 — these form the Phase 8 verification contract
- Exec brief format specified in `ARCHITECTURE.md` §5
