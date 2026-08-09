# Analysis report

> **Illustrative — synthetic data.** Generated for demonstration. No Careem data is used and no figure here describes a real business.

**Scope** Careem Quik — UAE dark-store network  ·  2025-01-01 to 2026-06-30 (546 days)  ·  currency AED
**Data quality gate** WARN  ·  8 issue(s), 5 repair(s) applied

## Scorecard

| KPI | Actual | Target | Status |
|---|---:|---:|---|
| Fill rate | 90.5% | 97.0% | below target |
| Waste rate | 3.6% | 2.0% | above target |
| Supplier OTIF | 90.9% | 95.0% | below target |
| Delivery p50 (min) | 20.2 | 20.0 | above target |
| Order cancel rate | 3.2% | 2.5% | above target |
| Fleet utilisation | 86.7% | 85.0% | on target |
| Inventory turns (annual) | 60.3 | 45.0 | on target |

## Where the value goes

Annualised, starting from AED 7.45m of gross margin.

| Item | Annualised | Type |
|---|---:|---|
| Gross margin | AED 7.45m | positive |
| Lost margin — unavailability | AED -1.03m | leak |
| Waste — expiry write-off | AED -524k | leak |
| Cancelled-order cost | AED -119k | leak |
| Supplier short-shipment cost | AED -164k | leak |
| Inventory holding cost | AED -71k | leak |
| Fleet cost | AED -3.16m | cost |
| Net contribution | AED 2.37m | net |

## Findings (7 material of 12 detected)

Total annualised leakage, root causes only (symptoms excluded to avoid double counting): **AED 983k**

### CAD-01 — Availability swings 16pp across the week — Thursday 96.4% down to Monday 80.2% — because orders are reviewed Monday and Wednesday but demand peaks Friday and Saturday

- **Impact** AED 478k/yr (range AED 354k – AED 598k)
- **Confidence** 97% — two-proportion z-test; statistical 0.95, sample 1.00 (n=1,817,480), data quality 0.95
- **Type** service / leak · root cause
- **Explains** SVC-01
- **Method** Day-of-week fill rate profile against the replenishment review calendar and the demand profile; two-proportion z-test on best vs worst day
- **How the number was derived** For every weekday below the weekly mean fill rate, the share of lost margin that would have been recovered at the best day's fill rate (96.4%), summed, penalised and annualised.
- **Evidence**
    - Best day: Thursday 96.4%
    - Worst day: Monday 80.2%
    - Replenishment reviewed on: Monday, Wednesday
    - Demand peaks on: Friday, Saturday
    - Weekend demand vs review-day demand: 1.33 x (vs order quantities are sized on review-day demand)
    - Spread: 0.16 (vs materiality threshold 4pp) [n=1,817,480]

### LOT-01 — 266 store-SKU lines have a case pack holding more days of stock than the product's own shelf life — 65% of network write-off, AED 204k a year that no store can prevent by ordering better

- **Impact** AED 204k/yr (range AED 119k – AED 289k)
- **Confidence** 87% — deterministic ratio test; statistical 0.95, sample 0.74 (n=266), data quality 0.95
- **Type** procurement / leak · root cause
- **Explains** WST-01, WST-02, WST-03, WST-04
- **Method** Case pack divided by observed daily velocity, compared against shelf life, at store-SKU grain; write-off attributed to lines where a single minimum lot cannot be sold within its own shelf life AND the line still turns at least 0.5 units/day. The velocity floor keeps this separate from the assortment finding, so the same write-off is not claimed twice
- **How the number was derived** AED 509,386 of write-off over the period sits on lines where one case pack exceeds the full shelf life at observed velocity. 60% of that is treated as addressable by re-specifying pack size; the balance is demand volatility a smaller pack would not have caught. Annualised.
- **Evidence**
    - Store-SKU lines affected: 266 (vs of 1,350 stocked lines, all selling at or above 0.5 units/day)
    - Share of network write-off: 0.65
    - Categories affected: Fresh Produce, Bakery, Ready Meals, Dairy & Eggs (vs all short shelf life)
    - Median days of cover per case: 9.4 days (vs median shelf life 5 days)
    - Largest contributing supplier: Modern Bakehouse (vs AED 201,785 of write-off across 22 lines)
    - Write-off value on affected lines: 509,386 AED

### SVC-01 — Network fill rate is 90.5% against a 97% target — closing the gap is worth AED 0.71m a year

- **Impact** AED 708k/yr (range AED 524k – AED 1.03m)
- **Confidence** 97% — deterministic aggregation; statistical 0.95, sample 1.00 (n=1,817,480), data quality 0.95
- **Type** service / leak · symptom of SUP-01, SUP-02, CAD-01
- **Method** Fill rate vs declared target; recoverable share of lost margin
- **How the number was derived** Lost margin over the period was AED 1,145,305. 68% of that is attributable to running below the 97% target. Multiplied by the declared stockout penalty of 1.35 and annualised (x0.668).
- **Evidence**
    - Fill rate: 0.9 (vs target 97%) [n=1,817,480]
    - Units of demand unserved: 172863 units
    - Store-SKU-days with a stockout: 0.08 (vs share of all store-SKU-days) [n=737,100]
    - Worst store-category: Business Bay / Meat & Poultry (vs fill 75.2%)

### SUP-01 — Gulf Fresh Produce is the network's least reliable supplier — OTIF 76% against a 95% target, costing about AED 191k a year

- **Impact** AED 191k/yr (range AED 70k – AED 249k)
- **Confidence** 98% — Welch t-test changepoint; statistical 0.95, sample 1.00 (n=20,093), data quality 1.00
- **Type** procurement / leak · root cause
- **Explains** SVC-01
- **Method** OTIF and lead-time CV against target; binary-segmentation changepoint on the monthly lead-time series
- **How the number was derived** Short-shipment cost AED 104,842 over the period (annualised AED 70,087), plus AED 121,217 of annualised lost margin in Fresh Produce attributable to this supplier's categories running 15.2% below the fill rate of categories it does not supply.
- **Evidence**
    - OTIF: 0.76 (vs target 95%) [n=20,093]
    - On-time rate: 0.84
    - In-full rate: 0.87
    - Lead time: 2.39 days (vs promised 2)
    - Lead-time variability (CV): 0.41 (vs peer median 0.09)
    - Units short-shipped: 9050 units

### AST-01 — The slowest 82 of 215 SKUs earn 5.0% of revenue but occupy 26% of shelf slots and account for 35% of write-off

- **Impact** AED 154k/yr (range AED 0 – AED 354k)
- **Confidence** 93% — deterministic ranking; statistical 0.95, sample 0.88 (n=215), data quality 0.95
- **Type** assortment / opportunity · root cause
- **Method** Revenue-ranked ABC; slot and waste cost attribution to the tail
- **How the number was derived** 348 slots at AED 41.0/month = AED 171,216/yr, plus AED 183,159/yr of tail waste, less 50% of the AED 401,724/yr margin these lines earn (assumes half the demand migrates to remaining range).
- **Evidence**
    - Tail SKUs: 82 SKUs (vs of 215 stocked)
    - Share of revenue: 0.05
    - Share of slots: 0.26
    - Share of waste cost: 0.35
    - Tail margin earned: 401,724 AED/yr

### FLT-01 — Al Nahda delivers in 30 min against a network median of 20 and cancels 8.5% of orders — the constraint is fleet capacity, not stock

- **Impact** AED 98k/yr (range AED 31k – AED 137k)
- **Confidence** 94% — two-proportion z-test vs peers; statistical 0.95, sample 1.00 (n=66,862), data quality 0.88
- **Type** fleet / leak · root cause
- **Method** Joint test: service breach AND capacity breach AND inventory health within peer range. The inventory test is what distinguishes a fleet constraint from a stock constraint.
- **How the number was derived** 3,986 cancellations above the 2.5% target, each costing AED 11.5 to serve and forgoing AED 25.2 of basket margin. Annualised.
- **Evidence**
    - Delivery p50: 30.5 min (vs network median 19.5) [n=66,862]
    - Delivery p90: 46.4 min
    - Cancellation rate: 0.08 (vs target 2.5%) [n=66,862]
    - Fleet utilisation: 1.25 (vs network median 81%)
    - Days above 100% utilisation: 0.99 (vs share of trading days)
    - Fill rate: 0.91 (vs network median 90.6% — the stock was on the shelf, so this is not a stock problem)
    - Waste rate: 0.03 (vs network median 3.1% — inventory is not being mismanaged here either)

### SEA-01 — A 51% demand peak runs 2025-03-05 to 2025-04-01 with 40% of orders after 20:00 (vs 25% normally) — fill rate holds at only 91.1% through it

- **Impact** AED 84k/yr (range AED 62k – AED 109k)
- **Confidence** 92% — STL decomposition; statistical 0.95, sample 0.93 (n=545), data quality 0.88
- **Type** demand / opportunity · root cause
- **Method** STL decomposition (period 7, robust); trend-adjusted rolling peak detection; daypart mix comparison
- **How the number was derived** Lost margin inside the peak window of AED 61,952, with the stockout penalty applied. Not scaled by the annualisation factor: the window recurs once a year, so a single occurrence already is the annual figure. This is the cost of not planning for a demand shape that is known in advance.
- **Evidence**
    - Peak window: 2025-03-05 to 2025-04-01
    - Volume lift: 0.51 (vs vs prior 8 weeks) [n=28,533]
    - Orders after 20:00: 0.4 (vs normally 25%)
    - Fill rate in window: 0.91 (vs network 90.5%)
    - Weekly seasonal strength: 0.94 (vs STL decomposition) [n=545]
    - Trend strength: 0.92 (vs STL decomposition) [n=545]

## Recommended actions

**6 actions recommended**, together worth AED 727k/yr net of the cost of doing them, against AED 103k of one-off investment.

| # | Action | Owner | Horizon | Effort | Net/yr | Payback | Confidence |
|---|---|---|---|---|---:|---:|---:|
| R1 | Re-time replenishment review and forecast forward, not backward | Demand Planning Lead | 0-30 days | medium | AED 311k | 1.0 mo | 97% |
| R2 | Re-specify case packs on short-shelf-life lines | Procurement Lead | 1-3 months | high | AED 111k | immediate | 87% |
| R4 | Rationalise the slow-moving tail and reallocate the slots | Category Manager | 1-3 months | medium | AED 107k | 2.5 mo | 93% |
| R3 | Put Gulf Fresh Produce on a formal performance plan and dual-source | Procurement Lead | 1-3 months | medium | AED 83k | immediate | 98% |
| R5a | Re-time captain shifts at Al Nahda to the demand peak | Fleet Operations Manager | 0-30 days | low | AED 73k | 2.5 mo | 94% |
| R6 | Build a Ramadan operating playbook | Supply Chain Director | 3-12 months | medium | AED 42k | 11.5 mo | 92% |

### R1 · Re-time replenishment review and forecast forward, not backward

**Owner** Demand Planning Lead  ·  **Horizon** 0-30 days  ·  **Effort** medium  ·  **Addresses** CAD-01, SVC-01

Two changes to the same process. First, move the replenishment review off Monday, Wednesday so that at least one review lands within 48 hours of the Friday and Saturday peak. Second — and this is the larger of the two — size order quantities against forecast demand over the full cover period rather than against the demand rate observed on the review day itself. Review days are currently the quietest days of the week, so every order is sized to a demand level the following weekend will exceed by 133%.

| | Annualised |
|---|---:|
| Benefit (after capture rate) | AED 311k |
| Range | AED 161k – AED 389k |
| Ongoing cost | AED 0 |
| One-off cost | AED 25k |
| **Net** | **AED 311k** |

**Why** This is the largest single recoverable item and the cheapest to act on, because it is a scheduling decision rather than a capital or contractual one.

**Risk** Ordering to a forward forecast raises average stock, so waste will rise on short-shelf-life lines unless the safety-stock factor is reduced at the same time. Sequence this after, or alongside, the pack-size work.

**Success metric** Weekly fill-rate spread (best day minus worst day) below 5pp within two months; Monday fill rate above 92%  ·  reviewed weekly

**Depends on** Supplier agreement to alternative order windows; Forecast available at store-SKU-day grain

**Assumptions**
- Capture rate 65% — a re-timed review recovers most but not all of the weekly swing; some of it is supplier lead-time noise that no calendar fixes.
- One-off cost AED 25,000 for system configuration, supplier renegotiation of order windows, and planner training.

### R2 · Re-specify case packs on short-shelf-life lines

**Owner** Procurement Lead  ·  **Horizon** 1-3 months  ·  **Effort** high  ·  **Addresses** LOT-01, WST-01, WST-02, WST-03, WST-04

Renegotiate minimum order quantity on the store-SKU lines where a single case cannot be sold within the product's shelf life. Target a pack size giving no more than 50% of shelf life in cover at current velocity. Open with Modern Bakehouse, which accounts for the largest share of the affected write-off. Where a supplier will not break the pack, the alternative is cross-docking a single delivery across two or three stores rather than forcing full cases into each.

| | Annualised |
|---|---:|
| Benefit (after capture rate) | AED 123k |
| Range | AED 72k – AED 174k |
| Ongoing cost | AED 12k |
| One-off cost | AED 0 |
| **Net** | **AED 111k** |

**Why** The write-off on these lines is not an execution failure. No amount of store discipline recovers it, because the stock is guaranteed to expire from the moment it is ordered. It is a single procurement decision with a single owner.

**Risk** Suppliers will price smaller lots higher, and may resist on handling grounds. If the achieved premium exceeds 1.5% the case weakens quickly — this should be re-tested against actual quoted terms before committing.

**Success metric** Waste rate on affected lines below 4% within one quarter; no fill-rate deterioration on the same lines  ·  reviewed monthly

**Depends on** Supplier contract review; Store-level cross-dock capability

**Assumptions**
- Capture rate 60% — a right-sized pack removes the guaranteed expiry but not waste caused by demand volatility.
- Unit-cost premium of 1.5% on AED 803,936 of annual purchase value on affected lines. THIS IS THE WEAKEST ASSUMPTION IN THE ANALYSIS — it is a placeholder until suppliers quote.

### R4 · Rationalise the slow-moving tail and reallocate the slots

**Owner** Category Manager  ·  **Horizon** 1-3 months  ·  **Effort** medium  ·  **Addresses** AST-01

Delist the slowest-moving lines across 348 store-SKU slots, protecting any line that is a known basket-builder or a category-completeness requirement. Reallocate freed slots to the top revenue decile, where availability is currently the binding constraint. Run it market by market rather than network-wide so the demand-migration assumption can be tested on the first market before the rest follow.

| | Annualised |
|---|---:|
| Benefit (after capture rate) | AED 107k |
| Range | AED 107k – AED 248k |
| Ongoing cost | AED 0 |
| One-off cost | AED 23k |
| **Net** | **AED 107k** |

**Why** The tail consumes slot capacity and write-off out of all proportion to what it earns, and those slots are the same constraint limiting availability on the lines that do sell.

**Risk** Range perception. Customers do not experience a delist as an efficiency gain, and quick-commerce baskets are sensitive to one-missing-item abandonment. The 50% demand-migration assumption behind the benefit is unverified and is the number most likely to be wrong.

**Success metric** Slot productivity (revenue per slot) up 10% within two quarters with no fall in basket size or order frequency  ·  reviewed monthly

**Depends on** Category review; Basket-affinity analysis before cutting

**Assumptions**
- Capture rate 70% of the modelled slot and waste saving.
- Half the demand on delisted lines migrates to remaining range. Unverified — a basket-affinity analysis should precede execution.
- Range reset costs AED 65/slot.

### R3 · Put Gulf Fresh Produce on a formal performance plan and dual-source

**Owner** Procurement Lead  ·  **Horizon** 1-3 months  ·  **Effort** medium  ·  **Addresses** SUP-01

Three steps. (1) Raise a supplier performance plan with a contractual OTIF floor and weekly reporting; the degradation is recent and datable — performance changed in 2026-02: lead time moved from 2.05 to 3.23 days and its standard deviation from 0.28 to 1.48. (2) Dual-source roughly 40% of volume on the highest-velocity lines this supplier covers, to cap exposure while the plan runs. (3) Until on-time performance recovers, raise the safety-stock factor on affected lines to absorb the observed lead-time variability of 2-day promise against 2.39-day actual.

| | Annualised |
|---|---:|
| Benefit (after capture rate) | AED 105k |
| Range | AED 39k – AED 137k |
| Ongoing cost | AED 22k |
| One-off cost | AED 0 |
| **Net** | **AED 83k** |

**Why** This is a datable change in a single supplier's behaviour, not a gradual drift, which makes it both diagnosable and negotiable.

**Risk** Dual-sourcing fresh produce splits volume and may weaken terms with both suppliers. Temporary safety-stock uplift raises waste on a short-shelf-life category — this is a deliberate trade of waste for availability and should be time-boxed.

**Success metric** OTIF above 90% within one quarter; lead-time CV below 0.35  ·  reviewed weekly

**Depends on** Alternative supplier qualification; Contract amendment

**Assumptions**
- Capture rate 55% — supplier remediation is slow and partial; a plan rarely restores full performance inside a year.
- Dual-source premium 3.0% on 40% of AED 1,854,658 annual spend with this supplier.

### R5a · Re-time captain shifts at Al Nahda to the demand peak

**Owner** Fleet Operations Manager  ·  **Horizon** 0-30 days  ·  **Effort** low  ·  **Addresses** FLT-01

35% of this store's orders fall in four hours (18:00, 19:00, 20:00, 21:00), and delivery time in those hours averages 35 min against 30 min outside them. Rebuild the shift pattern so captain hours track that curve, before adding any headcount. This is a rostering change, not a hiring decision.

| | Annualised |
|---|---:|
| Benefit (after capture rate) | AED 73k |
| Range | AED 44k – AED 88k |
| Ongoing cost | AED 0 |
| One-off cost | AED 15k |
| **Net** | **AED 73k** |

**Why** Do this first because it is cheap and reversible, and because it tests whether the constraint is genuinely total capacity or merely its distribution across the day.

**Risk** Captain availability may not be elastic to the required hours, and late-evening shifts may need a pay differential that is not costed here.

**Success metric** Delivery p50 at Al Nahda below 25 min and cancellation rate below 4.0% within six weeks  ·  reviewed weekly

**Depends on** Captain supply at peak hours; Rostering system change

**Assumptions**
- Capture rate 75% — re-timing addresses the peak-hour constraint but not total daily capacity.
- Rescheduling cost AED 15,000, no incremental headcount.

### R6 · Build a Ramadan operating playbook

**Owner** Supply Chain Director  ·  **Horizon** 3-12 months  ·  **Effort** medium  ·  **Addresses** SEA-01

Codify the peak as a planned event rather than an annual surprise. Volume rises 51% and the daypart mix inverts — 40% of orders fall after 20:00 against 25% normally. The playbook needs three things: a demand uplift applied at category level in the forecast, a replenishment window moved to late night so shelves are full when demand arrives, and captain shifts weighted to the post-Iftar window. Lock it four weeks before the window opens.

| | Annualised |
|---|---:|
| Benefit (after capture rate) | AED 42k |
| Range | AED 19k – AED 71k |
| Ongoing cost | AED 0 |
| One-off cost | AED 40k |
| **Net** | **AED 42k** |

**Why** This is the only finding in the set that is fully predictable in advance, which makes it the cheapest kind of problem to solve.

**Risk** The window moves roughly eleven days earlier each year, so a playbook tied to calendar dates rather than the lunar date will drift. Two observed cycles is a thin basis for a category-level uplift factor.

**Success metric** Fill rate inside the peak window within 2pp of the annual average, versus the current shortfall  ·  reviewed annual, with a post-event review

**Depends on** Category-level demand model; Supplier late-window delivery

**Assumptions**
- Capture rate 50% — planning improves availability but a 51% surge will not be fully absorbed in the first year.
- Playbook development cost AED 40,000.
- Based on two observed cycles. Treat the uplift factor as provisional and re-fit after the next one.

### R5b · Add 2.5 captain shifts/day at Al Nahda — NOT RECOMMENDED

**Owner** Fleet Operations Manager  ·  **Horizon** 1-3 months  ·  **Effort** medium  ·  **Addresses** FLT-01

Increase the fleet at Al Nahda by roughly 2.5 captain-shifts per day to bring utilisation from 124% down to the 85% target.

| | Annualised |
|---|---:|
| Benefit (after capture rate) | AED 83k |
| Range | AED 58k – AED 100k |
| Ongoing cost | AED 111k |
| One-off cost | AED 0 |
| **Net** | **AED -28k** |

**Why** Presented for completeness and because it is the intuitive answer. On these numbers it does not pay: the cost of the capacity exceeds the value of the cancellations it would prevent. Worth revisiting only if the rostering change fails, or if the lost lifetime value of repeatedly failed customers is judged materially higher than the single-order margin used here.

**Risk** Adds fixed cost that is hard to reverse if demand softens.

**Success metric** Fleet utilisation between 65% and 95% on 90% of days  ·  reviewed monthly

**Depends on** Captain recruitment in Sharjah

**Assumptions**
- Capture rate 85% — sizing to target utilisation removes most capacity-driven cancellations.
- 2.5 shifts/day at AED 120 = AED 111,233/yr.

### Considered and not recommended

- **R5b Add 2.5 captain shifts/day at Al Nahda** — reject. Benefit AED 83k/yr against cost AED 111k/yr, net AED -28k/yr.

## Detected but below the materiality floor

These cleared statistical tests but fall under the AED 60k/yr threshold for executive attention. Recorded so the reader can see what was considered and set aside.

| ID | Impact/yr | Finding |
|---|---:|---|
| WST-01 | AED 27k | Abu Dhabi writes off 17.1% of Dairy & Eggs against a network norm of 4.8% — AED 27k a year, and it is a lot-size problem, not a store problem |
| WST-03 | AED 19k | Khalifa City wastes 25.8% of Fresh Produce against a network norm of 10.5% — this store alone, AED 19k a year |
| WST-02 | AED 17k | Abu Dhabi writes off 22.7% of Ready Meals against a network norm of 11.1% — AED 17k a year, and it is a lot-size problem, not a store problem |
| SUP-02 | AED 11k | Arctic Frozen Logistics is the network's least reliable supplier — OTIF 90% against a 95% target, costing about AED 11k a year |
| WST-04 | AED 11k | Khalifa City wastes 9.9% of Meat & Poultry against a network norm of 3.7% — this store alone, AED 11k a year |
