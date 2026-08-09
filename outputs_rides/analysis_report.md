# Analysis report

> **Illustrative — synthetic data.** Generated for demonstration. No Careem data is used and no figure here describes a real business.

**Scope** Careem Rides — UAE marketplace  ·  2025-07-01 to 2026-06-30 (365 days)  ·  currency AED
**Data quality gate** WARN  ·  5 issue(s), 3 repair(s) applied

## Scorecard

| KPI | Actual | Target | Status |
|---|---:|---:|---|
| Fulfilment rate | 89.3% | 95.0% | below target |
| Rider cancel rate | 4.5% | 3.0% | above target |
| ETA p50 (min) | 7.6 | 7.0 | above target |
| ETA promise gap (min) | 0.9 | 1.0 | on target |
| Captain 30-day churn | 18.0% | 10.0% | above target |
| Captain activation | 45.0% | 55.0% | below target |
| Average surge | 1.1 | 1.1 | on target |

## Where the value goes

Annualised, starting from AED 2.67m of net revenue.

| Item | Annualised | Type |
|---|---:|---|
| Net revenue | AED 2.67m | positive |
| Lost revenue — unfulfilled requests | AED -418k | leak |
| Lost revenue — rider cancellations | AED -229k | leak |
| Captain replacement cost | AED -196k | leak |
| Surge subsidy above baseline | AED -165k | cost |
| Net contribution | AED 1.66m | net |

## Findings (4 material of 4 detected)

Total annualised leakage, root causes only (symptoms excluded to avoid double counting): **AED 214k**

### FUL-01 — The network fulfils 89.3% of requests against a 95% target — the shortfall is worth AED 0.22m a year

- **Impact** AED 223k/yr (range AED 178k – AED 418k)
- **Confidence** 98% — deterministic aggregation; statistical 0.95, sample 1.00 (n=385,712), data quality 0.97
- **Type** service / leak · symptom of SPL-01
- **Method** Fulfilment rate vs declared target; recoverable share of unserved demand
- **How the number was derived** 41,236 requests went unserved. 53% of those are attributable to running below target. Valued at the average fare of AED 36.86 × a 22% take rate × the declared 1.25 demand-suppression multiplier, then annualised.
- **Evidence**
    - Fulfilment rate: 0.89 (vs target 95%) [n=385,712]
    - Requests unserved: 41236 requests
    - Worst zone: Dubai Airport (vs 83.1% fulfilment)
    - Average fare: 36.86 AED

### CAP-01 — Captains who do not clear 20 trips in their first week churn at 26% against 8% for those who do — 3.3× the rate, and 55% of joiners fall in that group

- **Impact** AED 110k/yr (range AED 66k – AED 158k)
- **Confidence** 98% — chi-square test; statistical 0.95, sample 0.99 (n=2,600), data quality 1.00
- **Type** supply / leak · root cause
- **Method** Cohort split on first-week trips against 30-day churn; chi-square test of independence
- **How the number was derived** 1,431 captains failed to activate. Had they churned at the activated rate of 7.9% rather than 26.2%, 262 fewer would have left. Valued at the declared AED 420 replacement cost and annualised.
- **Evidence**
    - Churn — did not activate: 0.26 (vs target 10%) [n=1,431]
    - Churn — activated: 0.08 [n=1,169]
    - Share of joiners not activating: 0.55 [n=2,600]
    - Captains lost above the activated rate: 262 captains
    - Replacement cost: 420 AED each (vs declared assumption)

### SPL-01 — Dubai Airport loses 50% of demand between 06:00–09:00 while surge sits at 1.76× — supply is not responding to price

- **Impact** AED 59k/yr (range AED 47k – AED 76k)
- **Confidence** 94% — Pearson elasticity test; statistical 0.95, sample 0.90 (n=11,586), data quality 0.97
- **Type** supply / leak · root cause
- **Explains** FUL-01
- **Method** Zone-hour blocks with high unfulfilled demand AND elevated surge; Pearson correlation between daily surge and daily captain supply inside the window. A near-zero correlation is what distinguishes a positioning constraint from a pricing one.
- **How the number was derived** 5,772 unserved requests in this window over the period, valued at average fare × take rate × the demand-suppression multiplier, annualised.
- **Evidence**
    - Unfulfilled rate in window: 0.5 (vs 7.8% in the same zone outside it) [n=11,586]
    - Surge in window: 1.76 × (vs 1.09× outside it)
    - Captains per request: 0.17 (vs network 0.443)
    - Correlation of captain supply with surge: -0.45 (vs negative — supply falls as surge rises here, so raising it further is counterproductive) [n=365]
    - Average wait in window: 11.14 min (vs 7.9 min outside it)

### ETA-01 — Business Bay, Yas Island promise arrival 4.3 min sooner than they deliver, and cancel 11% of trips against 4% elsewhere — the estimate causes the cancellation, not the wait

- **Impact** AED 45k/yr (range AED 32k – AED 59k)
- **Confidence** 95% — correlation comparison; statistical 0.95, sample 1.00 (n=344,476), data quality 0.90
- **Type** service / leak · root cause
- **Method** Zone-level Pearson correlation of cancellation rate against the promise gap and against absolute wait, compared. The finding is only raised when the gap explains cancellation better than the wait does.
- **How the number was derived** 3,104 cancellations above the 3.7% baseline of zones that promise honestly. Each forgoes average-fare net revenue plus AED 6.5 of dispatch cost. Annualised.
- **Evidence**
    - Cancel rate in affected zones: 0.11 (vs 3.7% where the promise is honest) [n=44,739]
    - Promise gap: 4.26 min (vs tolerance 2.5 min)
    - Actual wait in affected zones: 7.66 min (vs network 7.6 min — these zones are NOT unusually slow)
    - Correlation: cancellation vs promise gap: 1 [n=15]
    - Correlation: cancellation vs absolute wait: -0.03 (vs weaker — so it is the gap that drives the decision) [n=15]

## Recommended actions

**2 actions recommended**, together worth AED 49k/yr net of the cost of doing them, against AED 30k of one-off investment.

| # | Action | Owner | Horizon | Effort | Net/yr | Payback | Confidence |
|---|---|---|---|---|---:|---:|---:|
| R3 | Recalibrate the ETA model in the zones that over-promise | Rider Experience Lead | 1-3 months | low | AED 36k | 9.9 mo | 95% |
| R1 | Guarantee captain supply into Dubai Airport during 06:00–09:00 | Supply Growth Lead | 0-30 days | medium | AED 13k | immediate | 94% |

### R3 · Recalibrate the ETA model in the zones that over-promise

**Owner** Rider Experience Lead  ·  **Horizon** 1-3 months  ·  **Effort** low  ·  **Addresses** ETA-01

Re-fit the arrival estimate for Business Bay, Yas Island against observed pickup times rather than optimistic routing. These zones are not slow — their actual waits sit near the network median. They are promising times they cannot hit, and riders cancel on the gap. Widen the displayed estimate to a range, and hold the model to a calibration target rather than a headline-number target.

| | Annualised |
|---|---:|
| Benefit (after capture rate) | AED 36k |
| Range | AED 25k – AED 47k |
| Ongoing cost | AED 0 |
| One-off cost | AED 30k |
| **Net** | **AED 36k** |

**Why** The cheapest kind of problem to fix: the operation is performing adequately and only the promise is wrong.

**Risk** An honest, longer ETA may suppress requests at the point of quote — trading cancellations for lost bookings. The net effect is an empirical question and this should ship as an A/B test, not a global change.

**Success metric** Cancellation rate in the affected zones within 1pp of the network baseline, with request volume unchanged  ·  reviewed weekly

**Depends on** ETA model ownership; Experiment framework

**Assumptions**
- Capture rate 80% — the highest in this set, because the mechanism is direct and the fix is entirely within our control.
- Model rework cost AED 30,000.
- Assumes riders cancel on the gap rather than on the absolute wait. That is what the correlation comparison shows in this data, and it is the load-bearing claim behind the recommendation.

### R1 · Guarantee captain supply into Dubai Airport during 06:00–09:00

**Owner** Supply Growth Lead  ·  **Horizon** 0-30 days  ·  **Effort** medium  ·  **Addresses** SPL-01, FUL-01

Stop treating this as a pricing problem. Surge in this window already averages 1.76× and captain supply correlates with it at -0.45 — effectively not at all, so raising the multiplier further buys nothing but a worse rider experience. Instead, commit supply directly: a standing pre-positioning incentive paid to captains who are inside the zone before the window opens, plus a queue slot guarantee so they are not penalised for waiting. Pilot in this one zone-hour block before extending it.

| | Annualised |
|---|---:|
| Benefit (after capture rate) | AED 32k |
| Range | AED 18k – AED 42k |
| Ongoing cost | AED 19k |
| One-off cost | AED 0 |
| **Net** | **AED 13k** |

**Why** This is the largest single recoverable block of demand in the network, and the intuitive fix — more surge — is already running and demonstrably not working.

**Risk** A guaranteed incentive can be gamed — captains idling in-zone without accepting trips. Pay it on completed trips inside the window, not on presence. There is also a risk of pulling supply out of adjacent zones; monitor their fulfilment while piloting.

**Success metric** Unfulfilled rate in Dubai Airport during 06:00–09:00 below 10% within six weeks, with no fulfilment deterioration in adjacent zones  ·  reviewed weekly

**Depends on** Zone geofence and queue configuration; Captain communications

**Assumptions**
- Capture rate 55% — pre-positioning recovers much of the unserved demand but not all; some riders will have gone elsewhere before supply arrives.
- Incentive of AED 6.0 per recovered trip. Should be re-tested against actual captain response in the pilot.

### R2 · Build a first-week activation programme for new captains — INVESTIGATE, do not act yet

**Owner** Captain Experience Lead  ·  **Horizon** 1-3 months  ·  **Effort** medium  ·  **Addresses** CAP-01

Treat the first week as the retention decision it is. Three components: a guaranteed-earnings floor for the first 20 trips so a slow start is not a financial one; assignment priority for new captains during their first week so they get volume; and a check-in at day 3 for anyone below 8 trips. The trigger is trip count, not earnings — trip count is what predicts churn in this data, and it is visible days earlier.

| | Annualised |
|---|---:|
| Benefit (after capture rate) | AED 66k |
| Range | AED 40k – AED 94k |
| Ongoing cost | AED 0 |
| One-off cost | AED 85k |
| **Net** | **AED 66k** |

**Why** Supply is the binding constraint across this network, and this is the cheapest supply available — captains already recruited, already onboarded, and lost in their first month.

**Risk** The association between first-week trips and churn is not proof of causation — captains who were always going to leave may simply drive less in week one. A holdout group in the pilot would settle it, and is worth the delay.

**Success metric** Activation rate above 55% and 30-day churn among new joiners below 15% within one quarter  ·  reviewed weekly

**Depends on** Dispatch priority capability; Earnings guarantee approval

**Assumptions**
- Capture rate 60% — an activation programme moves some of the non-activating group, not all of it.
- Programme cost AED 85,000 — design, earnings guarantee funding and the dispatch change.
- Replacement cost per captain is a declared assumption, not a measured figure. It drives the whole benefit and should be validated against actual recruitment spend.

### Considered and not recommended

- **R2 Build a first-week activation programme for new captains** — investigate. Benefit AED 66k/yr against cost AED 0/yr, net AED 66k/yr.
