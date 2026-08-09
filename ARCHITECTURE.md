# Architecture & Scenario Design — Decision Brief Generator

**Version:** 0.1 (draft, awaiting sign-off)
**Date:** 2026-08-02

---

## 1. The scenario

**Careem Quik — UAE dark-store network.** Quick-commerce grocery: a network of small
fulfilment stores holding fast-moving grocery SKUs, replenished by suppliers, picked in-store,
delivered by captains in 15–30 minutes.

This is chosen deliberately. It is the single most supply-chain-dense part of Careem's business:
inventory, suppliers, lead times, perishability, forecasting, network design and last-mile all
sit in one operation. A Supply Chain Director owns most of it.

**Scope:** UAE only — Dubai, Abu Dhabi, Sharjah. 12 dark stores.
**Period:** Jan 2025 – Jun 2026 (18 months, daily grain).
**Currency:** AED primary, USD toggle at 3.6725 fixed peg.

### The decisions the tool must be able to inform

1. Where is the network leaking margin, and how much?
2. Are stockouts a **forecasting** problem or a **supplier reliability** problem? (Different fix, different owner.)
3. Which SKUs earn their slot, and which should be delisted?
4. Which dark stores underperform — and is the cause location, assortment, inventory, or fleet?
5. What is our wastage exposure and what drives it?
6. Where should safety stock sit, and how much?

A tool that can only answer #1 is a dashboard. Answering #2 and #4 correctly is what makes it a
decision instrument — because both contain a **misdiagnosis trap**.

---

## 2. Data model (self-created synthetic)

Eight related tables. Relational, not a single flat file — because real supply chain analysis
requires joins, and a tool that only handles one flat CSV isn't credible.

| Table | Grain | Key fields |
|-------|-------|------------|
| `dark_stores.csv` | 1 row per store | store_id, name, city, area, sqm, opened_date, catchment_pop, rent_aed_month, staff_count |
| `skus.csv` | 1 row per SKU | sku_id, name, category, subcategory, brand, unit_cost_aed, unit_price_aed, shelf_life_days, storage_temp, supplier_id, case_pack, moq |
| `suppliers.csv` | 1 row per supplier | supplier_id, name, category_focus, payment_terms_days, promised_lead_time_days, min_order_aed |
| `orders.csv` | 1 row per customer order | order_id, datetime, store_id, customer_id, basket_aed, items, promised_min, actual_min, status |
| `order_items.csv` | 1 row per order line | order_id, sku_id, qty, unit_price_aed, unit_cost_aed, substituted, unfulfilled |
| `inventory_daily.csv` | store × SKU × day | date, store_id, sku_id, opening, receipts, sold, wasted, closing, stockout_flag |
| `purchase_orders.csv` | 1 row per PO line | po_id, supplier_id, store_id, sku_id, order_date, promised_date, received_date, qty_ordered, qty_received, unit_cost_aed |
| `courier_daily.csv` | store × day | date, store_id, active_captains, orders_delivered, avg_delivery_min, utilisation_pct, fleet_cost_aed |

Approx. volume: ~450k order lines, ~2.6M inventory-day rows (12 stores × 400 SKUs × 548 days).
Large enough to be real work, small enough to run fast.

---

## 3. Planted signals — the verification contract

The dataset will contain six deliberately engineered truths. The tool must find them
**without being told**. This is what turns the showcase from "look at my charts" into
"look, it found the thing."

| ID | Planted truth | What it tests |
|----|---------------|---------------|
| **S1** | Supplier *Gulf Fresh Produce* (SUP01) degrades from Feb-2026: lead time 2.10d → 3.30d, standard deviation 0.52 → 1.38, PO fill 96.9% → 85.3%. Fresh-produce stockout-days rise 16.5% → 26.8% while every other category stays flat (5.9% → 6.5%) | Can it separate **supply reliability** from **demand forecast error**? |
| **S2** | Abu Dhabi chilled dairy waste runs 16.1% vs 2.2% in Dubai and 3.5% network-wide — caused by SUP02 case packs (10–17 units) exceeding what low local velocity can absorb within shelf life | Can it trace waste to a **procurement constraint** rather than blaming store ops? |
| **S3** | Bottom 40% of active SKUs = 5.5% of revenue but 42.5% of waste cost (AED 313k) | Pareto / ABC reasoning and a delist recommendation |
| **S4** | Replenishment is reviewed Mon/Wed and sized against *that day's* demand rate, so the Fri–Sat weekend peak is never in the forecast the order is built from. Fill rate runs 96.4% Fri → 80.2% Mon | Can it connect a **planning cadence** to a **service failure**? |
| **S5** | Sharjah Al Nahda (DS07): delivery 31.8 min vs 20.2 peer, cancellations 8.8% vs 2.5% — but fill rate 90.7% (best in network) and waste 2.5% (near-lowest). Fleet utilisation 127% vs 81% peer | **Misdiagnosis trap.** A naive tool blames stock. The correct answer is fleet capacity. |
| **S6** | Ramadan 2026 lifts volume +42% and shifts the 20:00–02:00 share from 24.7% to 41.7% | Seasonality vs trend decomposition |

Phase 8 verification is simply: did it find all six, and did it get S5 right?
`src/verify_signals.py` is the acceptance test and prints the ground truth above.

---

## 4. Pipeline

```
data/raw/*.csv
      │
      ▼
[1] INGEST ──────────► profiles schema, infers types, validates joins,
                       flags nulls / dupes / outliers / referential breaks
                       → data_quality_report.json
      │
      ▼
[2] SEMANTIC LAYER ──► config/semantic_map.yaml binds columns to concepts
                       config/business_rules.yaml holds targets & assumptions
                       (fill-rate target, waste target, cost of a stockout,
                        holding cost %, service-level target)
      │
      ▼
[3] ANALYSIS ────────► seven analyzers, each emits Finding objects
      │                 · descriptive & trend      · seasonality decomposition
      │                 · variance decomposition   · anomaly detection
      │                 · Pareto / ABC-XYZ         · segment contribution
      │                 · driver / correlation
      │
      ▼
[4] KPI ENGINE ──────► fill rate · OTIF · stockout rate & lost sales ·
                       days of cover · inventory turns · wastage % ·
                       supplier lead-time mean/σ · forecast MAPE & bias ·
                       perfect-order rate · cost-to-serve · courier utilisation
      │
      ▼
[5] INSIGHT RANKING ─► score = materiality × confidence × actionability
                       collapse overlapping findings to the root cause
      │
      ▼
[6] RECOMMENDATION ──► each surviving finding → action with
                       owner · effort · expected impact (range) · payback ·
                       risk · dependencies · success metric
      │
      ▼
[7] RENDER ──────────► brief.docx + brief.pdf · dashboard.html · deck.pptx
                       all from ONE payload, so numbers cannot disagree
```

### The Finding object (the spine of the whole tool)

```python
Finding(
    id, headline, category,
    magnitude_aed,          # what it's worth
    direction,              # leak / opportunity
    evidence=[...],         # the exact rows/aggregates behind it
    method,                 # how it was derived
    confidence,             # statistical + data-quality adjusted
    entities,               # which stores / SKUs / suppliers
    root_cause,             # linked upstream Finding, if any
)
```

Every sentence in the final brief is generated from a Finding. Nothing is asserted that
isn't backed by one. That constraint is what makes the output expert-level rather than
plausible-sounding.

---

## 5. Exec brief format (proposed)

Five to six pages. Decision-first. Structure:

| § | Section | Length | Content |
|---|---------|--------|---------|
| 1 | Cover | — | Title, period, scope, **"Illustrative — synthetic data"** label |
| 2 | The decision | ⅓ p | Situation in 3 lines · the number at stake · what's being asked of the reader |
| 3 | Executive summary | 1 p | Top 5 findings — one line each, with magnitude and confidence |
| 4 | Where the margin goes | 1 p | Waterfall: gross margin → stockout loss → wastage → cost-to-serve → net |
| 5 | Root cause | 1–1½ p | Top 3 issues, each with the evidence chain, not just the conclusion |
| 6 | Recommended actions | 1 p | Table: action · owner · effort · impact AED range · payback · risk · confidence |
| 7 | What we'd measure | ⅓ p | Leading indicators, review cadence, kill criteria |
| 8 | Appendix | 1–2 p | Method, data quality, assumptions, limitations, what we could NOT conclude |

§8 matters more than it looks. Stating what the data *cannot* support is the clearest signal
of analytical maturity — and it is what most candidate submissions leave out.

**Dashboard** mirrors §3–§6 interactively. **Deck** is §2, §3, §5, §6 at 10 slides.

---

## 6. Visual identity

Careem brand palette:

| Token | Hex | Use |
|-------|-----|-----|
| Careem Green | `#0FA958` | Primary, positive metrics |
| Deep Green | `#046A38` | Headers, emphasis |
| Ink | `#1A1A1A` | Body text |
| Slate | `#5C6B73` | Secondary text, axes |
| Alert Red | `#D64545` | Losses, breaches |
| Amber | `#E8A33D` | Watch items |
| Mist | `#F4F6F5` | Backgrounds, table banding |

Typography: a clean grotesque (Inter / Source Sans) — Careem's own typeface isn't licensable
for this, and using a lookalike is the correct call for a portfolio piece.

---

## 7. Build order

| Phase | Deliverable | Est. |
|-------|-------------|------|
| 2 | Synthetic dataset generator + 8 CSVs | 1 session |
| 3 | Ingest + data-quality layer | 1 session |
| 4 | Analysis engine + KPI engine | 2 sessions |
| 5 | Insight ranking + recommendation engine | 1 session |
| 6 | Three renderers | 2 sessions |
| 7 | Skill wrapper + README | ½ session |
| 8 | Verification against planted signals | ½ session |

---

## 8. Rejected alternatives

- **Using a real Kaggle dataset.** Rejected: no public dataset matches a quick-commerce
  dark-store supply chain, and we lose the ability to plant verifiable signals. Self-created
  data is explicitly permitted by the brief.
- **LLM-only analysis (no Python).** Rejected: numbers must be reproducible and auditable.
  Python computes, Claude narrates. Never the reverse.
- **One flat CSV.** Rejected: real supply chain questions require joins across orders,
  inventory and POs. A single-table tool would not survive scrutiny.
