# Portability test — what happened when I pointed it at a second domain

The first version of this README claimed the pipeline was domain-agnostic
except for the detectors. That claim was **wrong**, and this document is what
testing it produced.

The test: build a second dataset from a genuinely different business — a
two-sided ride-hailing marketplace with no inventory, no suppliers, no shelf
life and no purchase orders — and see how much of the pipeline survives.

**Result: it took six code changes to make the claim true, and one part of the
claim is still false and now stated as such.**

---

## What broke

| # | What failed | Why it mattered |
|---|---|---|
| 1 | `KPIEngine` named `inventory_daily`, `purchase_orders`, `courier_daily` directly — 20 references | The engine could not be instantiated on any other data |
| 2 | The scorecard and value waterfall were hardcoded Python lists of supply-chain metrics | A marketplace has no "gross margin" or "fill rate" row |
| 3 | Date parsing guessed from column-name suffixes (`*_date`, `*_datetime`) | The rides timestamps were called `requested_at` and `week_start`, loaded as strings, and the pipeline failed several layers downstream with an error pointing nowhere near the cause |
| 4 | Recommendation templates were keyed on finding-ID prefix alone | Both domains used the prefix `SUP` — supplier, and supply. Rides findings were silently routed into supply-chain templates and crashed on a missing config key |
| 5 | The payload builder and report writer referenced `gross_margin_aed` by name | Neither could produce output for a domain without that metric |
| 6 | The deck's narrative slides contained hardcoded prose about stores, deliveries and fill rate | The rides deck rendered a supply-chain story over marketplace data, with a blank space where a chart should have been |

Defect 4 is the one worth dwelling on. It did not throw where the mistake was.
It threw in a config lookup three files away, and the traceback pointed at
`recommend.py` rather than at the naming collision that caused it. A prefix
registry keyed on a two-domain namespace was always going to collide; it just
needed a second domain to prove it.

---

## What was changed

- **`src/analysis/kpi_base.py`** — new. Holds the genuinely generic machinery:
  period arithmetic, annualisation, currency, data-quality confidence, and a
  **config-driven scorecard and waterfall**. A domain engine now supplies one
  thing — a flat `network` dict of metrics — and everything generic derives
  from that plus configuration.
- **`src/analysis/registry.py`** — new. Maps the `domain` declared in a
  profile's semantic map to its KPI engine, detectors and charts.
- **`config/<profile>/`** — configs are now per-profile rather than global.
  A domain is a folder, not a code change.
- **`src/ingest.py`** — date columns are taken from the semantic map's
  declarations first, with the name heuristic kept only as a fallback.
- **`src/findings.py`** — `Evidence` gained a `role` field. `role="rules_out"`
  marks the evidence that eliminates the intuitive explanation, so renderers
  can find it structurally instead of by scanning prose for the word "not".

---

## What is still domain-specific, and always will be

| Layer | Portable? |
|---|---|
| Ingestion, profiling, joins | Yes |
| Data-quality gate | Yes |
| Finding / Evidence / confidence model | Yes |
| Insight ranking and root-cause linking | Yes |
| Recommendation economics — capture rates, netting, payback, stance | Yes |
| Scorecard and value waterfall | Yes, via config |
| Word brief, dashboard, deck structure | Yes |
| **KPI definitions** | **No — each domain writes its own** |
| **Detectors** | **No** |
| **Recommendation templates** | **No** |
| **Domain-specific charts** | **No** (2 of 6 are shared) |

This is the irreducible part. "Fill rate" means nothing to a marketplace and
"unfulfilled request rate" means nothing to a warehouse. Turning a finding into
"renegotiate the case pack with this supplier" requires knowing what a case pack
is. Any tool claiming otherwise is either trivial or lying.

Adding a domain costs roughly: one KPI class, one detector module, one
recommendation template module, one chart module, two config files, and an
acceptance test. For rides that came to about 1,100 lines — against roughly
3,400 lines of pipeline reused unchanged.

---

## Did it actually work?

Three signals were planted in the rides data. The pipeline found all three
without being told they existed.

```
R1  Airport morning supply constraint
    unfulfilled 49.8% in window vs 7.8% outside it
    surge 1.76x vs 1.09x
    correlation of captain supply with surge: -0.45
    → SPL-01, raised as a supply finding, not a pricing one

R2  First-week activation vs churn
    churn 26.2% (not activated) vs 7.9% (activated) = 3.3x
    → CAP-01

R3  ETA over-promise
    corr(cancellation, promise gap)   = +0.997
    corr(cancellation, absolute wait) = -0.030
    → ETA-01, attributed to the promise rather than the wait

10/10 checks passed
```

**The second misdiagnosis trap held.** The airport zone loses half its morning
demand and surge is already running at 1.76×. The intuitive response is to raise
the price. The correlation between captain supply and surge in that window is
**−0.45** — supply falls as surge rises. The detector reports it as a
positioning constraint and says so on the face of the deck.

The wording of that evidence line is generated from the number rather than
assumed: below −0.2 it reads "negative — supply falls as surge rises here, so
raising it further is counterproductive"; near zero it reads "price-inelastic";
above +0.2 it says the pricing hypothesis may hold after all. An earlier version
hardcoded "near zero", which would have described a −0.45 correlation
incorrectly.

The supply-chain profile still passes **26/26** after the refactor, with
identical numbers — the same AED 727,005 net benefit as before.

---

## One more thing the test caught

After adding the `role` field, the supply-chain verification dropped to 25/26.
The failing check was looking for the literal string `"NOT a stock problem"` in
the evidence comparator, and I had reworded that sentence.

The check was testing the prose, not the reasoning. It now tests for
`role == "rules_out"`. A test coupled to wording tells you the wording changed —
which is not what anyone wants to know.

---

## Running it

```bash
python src/generate_rides_data.py                                    # build the data
python src/build_outputs.py --profile careem_rides --out outputs_rides
python src/verify_rides.py                                           # 10/10
```
