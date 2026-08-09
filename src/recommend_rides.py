"""
Recommendation templates — rides marketplace
============================================
Turning a finding into an action requires knowing the business. These four
templates are the rides equivalent of the supply-chain set; they share the
generic economics in `recommend.py` (capture rates, netting off the cost of
acting, payback, stance) and nothing else.
"""

from __future__ import annotations

from recommend import Recommendation, _finalise


def rec_supply_positioning(f, ds, k, rules) -> Recommendation:
    cfg = rules["recommendations"]
    ca = cfg["cost_assumptions"]
    cap = cfg["capture_rate"]["supply_repositioning"]
    d = f.detail
    zone = f.entities[0]
    zname = ds.table("zones").set_index("zone_id").loc[zone, "zone_name"]
    window = d.get("window_label", "the peak window")
    corr = d.get("surge_supply_corr", 0.0)
    unserved = d.get("unserved_requests", 0)

    benefit = f.magnitude_aed * cap
    # A repositioning incentive is paid per trip actually recovered.
    recovered = unserved * cap
    annual_cost = k.annualised(
        recovered * ca["repositioning_incentive_per_trip_aed"])

    r = Recommendation(
        id="R1",
        title=f"Guarantee captain supply into {zname} during {window}",
        action=(
            f"Stop treating this as a pricing problem. Surge in this window "
            f"already averages {f.evidence[1].value:.2f}× and captain supply "
            f"correlates with it at {corr:+.2f} — effectively not at all, so "
            f"raising the multiplier further buys nothing but a worse rider "
            f"experience. Instead, commit supply directly: a standing "
            f"pre-positioning incentive paid to captains who are inside the "
            f"zone before the window opens, plus a queue slot guarantee so "
            f"they are not penalised for waiting. Pilot in this one zone-hour "
            f"block before extending it."),
        owner="Supply Growth Lead",
        horizon="immediate",
        effort="medium",
        finding_ids=[f.id] + f.explains,
        benefit_aed=benefit,
        benefit_low=(f.magnitude_low or f.magnitude_aed) * cap * 0.7,
        benefit_high=(f.magnitude_high or f.magnitude_aed) * cap,
        one_off_cost_aed=0.0,
        annual_cost_aed=annual_cost,
        confidence=f.confidence,
        risk=("A guaranteed incentive can be gamed — captains idling in-zone "
              "without accepting trips. Pay it on completed trips inside the "
              "window, not on presence. There is also a risk of pulling supply "
              "out of adjacent zones; monitor their fulfilment while piloting."),
        dependencies=["Zone geofence and queue configuration",
                      "Captain communications"],
        success_metric=(f"Unfulfilled rate in {zname} during {window} below 10% "
                        f"within six weeks, with no fulfilment deterioration in "
                        f"adjacent zones"),
        review_cadence="weekly",
        assumptions=[
            f"Capture rate {cap:.0%} — pre-positioning recovers much of the "
            f"unserved demand but not all; some riders will have gone elsewhere "
            f"before supply arrives.",
            f"Incentive of AED {ca['repositioning_incentive_per_trip_aed']} per "
            f"recovered trip. Should be re-tested against actual captain "
            f"response in the pilot.",
        ],
        rationale=(
            "This is the largest single recoverable block of demand in the "
            "network, and the intuitive fix — more surge — is already running "
            "and demonstrably not working."),
    )
    return _finalise(r, rules)


def rec_activation(f, ds, k, rules) -> Recommendation:
    cfg = rules["recommendations"]
    ca = cfg["cost_assumptions"]
    cap = cfg["capture_rate"]["activation_programme"]

    benefit = f.magnitude_aed * cap
    one_off = ca["activation_programme_cost_aed"]

    r = Recommendation(
        id="R2",
        title="Build a first-week activation programme for new captains",
        action=(
            "Treat the first week as the retention decision it is. Three "
            "components: a guaranteed-earnings floor for the first 20 trips so "
            "a slow start is not a financial one; assignment priority for new "
            "captains during their first week so they get volume; and a "
            "check-in at day 3 for anyone below 8 trips. The trigger is trip "
            "count, not earnings — trip count is what predicts churn in this "
            "data, and it is visible days earlier."),
        owner="Captain Experience Lead",
        horizon="near_term",
        effort="medium",
        finding_ids=[f.id],
        benefit_aed=benefit,
        benefit_low=(f.magnitude_low or f.magnitude_aed) * cap,
        benefit_high=(f.magnitude_high or f.magnitude_aed) * cap,
        one_off_cost_aed=one_off,
        annual_cost_aed=0.0,
        confidence=f.confidence,
        risk=("The association between first-week trips and churn is not proof "
              "of causation — captains who were always going to leave may "
              "simply drive less in week one. A holdout group in the pilot "
              "would settle it, and is worth the delay."),
        dependencies=["Dispatch priority capability", "Earnings guarantee approval"],
        success_metric=("Activation rate above 55% and 30-day churn among new "
                        "joiners below 15% within one quarter"),
        review_cadence="weekly",
        assumptions=[
            f"Capture rate {cap:.0%} — an activation programme moves some of "
            f"the non-activating group, not all of it.",
            f"Programme cost AED {one_off:,.0f} — design, earnings guarantee "
            f"funding and the dispatch change.",
            "Replacement cost per captain is a declared assumption, not a "
            "measured figure. It drives the whole benefit and should be "
            "validated against actual recruitment spend.",
        ],
        rationale=(
            "Supply is the binding constraint across this network, and this is "
            "the cheapest supply available — captains already recruited, "
            "already onboarded, and lost in their first month."),
    )
    return _finalise(r, rules)


def rec_eta_recalibration(f, ds, k, rules) -> Recommendation:
    cfg = rules["recommendations"]
    ca = cfg["cost_assumptions"]
    cap = cfg["capture_rate"]["eta_recalibration"]
    d = f.detail
    zones = ", ".join(z["zone_name"] for z in d.get("zones", []))

    benefit = f.magnitude_aed * cap
    one_off = ca["eta_model_rework_cost_aed"]

    r = Recommendation(
        id="R3",
        title="Recalibrate the ETA model in the zones that over-promise",
        action=(
            f"Re-fit the arrival estimate for {zones} against observed pickup "
            f"times rather than optimistic routing. These zones are not slow — "
            f"their actual waits sit near the network median. They are "
            f"promising times they cannot hit, and riders cancel on the gap. "
            f"Widen the displayed estimate to a range, and hold the model to a "
            f"calibration target rather than a headline-number target."),
        owner="Rider Experience Lead",
        horizon="near_term",
        effort="low",
        finding_ids=[f.id],
        benefit_aed=benefit,
        benefit_low=(f.magnitude_low or f.magnitude_aed) * cap,
        benefit_high=(f.magnitude_high or f.magnitude_aed) * cap,
        one_off_cost_aed=one_off,
        annual_cost_aed=0.0,
        confidence=f.confidence,
        risk=("An honest, longer ETA may suppress requests at the point of "
              "quote — trading cancellations for lost bookings. The net effect "
              "is an empirical question and this should ship as an A/B test, "
              "not a global change."),
        dependencies=["ETA model ownership", "Experiment framework"],
        success_metric=("Cancellation rate in the affected zones within 1pp of "
                        "the network baseline, with request volume unchanged"),
        review_cadence="weekly",
        assumptions=[
            f"Capture rate {cap:.0%} — the highest in this set, because the "
            f"mechanism is direct and the fix is entirely within our control.",
            f"Model rework cost AED {one_off:,.0f}.",
            "Assumes riders cancel on the gap rather than on the absolute wait. "
            "That is what the correlation comparison shows in this data, and it "
            "is the load-bearing claim behind the recommendation.",
        ],
        rationale=(
            "The cheapest kind of problem to fix: the operation is performing "
            "adequately and only the promise is wrong."),
    )
    return _finalise(r, rules)


TEMPLATES = {
    "SPL": rec_supply_positioning,
    "CAP": rec_activation,
    "ETA": rec_eta_recalibration,
}
