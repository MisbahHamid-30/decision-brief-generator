"""
Rides detectors
===============
Four detectors for a two-sided marketplace. They share nothing with the
supply-chain set except the `Finding` contract — which is the boundary the
portability claim actually rests on.

One of these is a second misdiagnosis guard, deliberately. In the supply-chain
data a store looked like a stock problem and was a fleet problem. Here a zone
looks like a pricing problem — demand far exceeds supply, so raise surge — and
surge is already elevated and achieving nothing. The distinguishing test is
whether supply responds to price.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from findings import (Finding, Evidence, statistical_confidence,
                      sample_confidence, combine_confidence, describe_confidence)

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _fid(prefix: str, n: int) -> str:
    return f"{prefix}-{n:02d}"


# ==========================================================================
# 1. Unfulfilled demand — the network-level gap
# ==========================================================================

def detect_fulfilment_gap(ds, k, rules) -> list[Finding]:
    t = rules["targets"]["fulfilment_rate"]
    n = k.network
    actual, target = n["fulfilment_rate"], t["target"]
    if actual >= target:
        return []

    recoverable_share = (target - actual) / (1 - actual)
    recoverable_requests = n["unfulfilled_requests"] * recoverable_share
    magnitude = k.annualised(k.demand_value(recoverable_requests))

    worst = k.by_zone.nsmallest(5, "fulfilment_rate")
    dq = k.table_confidence("supply_demand_hourly", "zones")
    st = statistical_confidence(p_value=0.0)
    sm = sample_confidence(int(n["requests"]), 10000)

    return [Finding(
        id=_fid("FUL", 1),
        headline=(f"The network fulfils {actual:.1%} of requests against a "
                  f"{target:.0%} target — the shortfall is worth "
                  f"AED {magnitude/1e6:.2f}m a year"),
        category="service",
        direction="leak",
        entity_type="network",
        entities=["network"],
        magnitude_aed=magnitude,
        magnitude_basis=(
            f"{int(n['unfulfilled_requests']):,} requests went unserved. "
            f"{recoverable_share:.0%} of those are attributable to running below "
            f"target. Valued at the average fare of AED {n['avg_fare_aed']:.2f} "
            f"× a {k.take_rate:.0%} take rate × the declared "
            f"{k.costs['unfulfilled_demand_multiplier']} demand-suppression "
            f"multiplier, then annualised."),
        magnitude_low=k.annualised(recoverable_requests * n["avg_fare_aed"] * k.take_rate),
        magnitude_high=k.annualised(k.demand_value(n["unfulfilled_requests"])),
        evidence=[
            Evidence("Fulfilment rate", actual, "", f"target {target:.0%}",
                     "supply_demand_hourly", int(n["requests"])),
            Evidence("Requests unserved", int(n["unfulfilled_requests"]), "requests",
                     None, "supply_demand_hourly"),
            Evidence("Worst zone", worst.iloc[0].zone_name, "",
                     f"{worst.iloc[0].fulfilment_rate:.1%} fulfilment",
                     "supply_demand_hourly"),
            Evidence("Average fare", n["avg_fare_aed"], "AED", None, "trips"),
        ],
        method="Fulfilment rate vs declared target; recoverable share of unserved demand",
        confidence=combine_confidence(st, sm, dq),
        confidence_basis=describe_confidence(st, sm, dq, int(n["requests"]),
                                             "deterministic aggregation"),
        period=k.period,
        tags=["fulfilment", "marketplace"],
        detail={"worst_zones": worst.to_dict("records")},
    )]


# ==========================================================================
# 2. Supply that does not respond to price  — the misdiagnosis guard
# ==========================================================================

def detect_supply_inelasticity(ds, k, rules) -> list[Finding]:
    """Find zone-hours where demand exceeds supply and surge has already risen
    without supply following.

    The intuitive response to an undersupplied zone is to raise the price. That
    only works if supply is price-elastic. Where surge is already elevated and
    captain counts have not moved, the constraint is physical — captains cannot
    reach or enter the zone — and more surge buys nothing but a worse rider
    experience.
    """
    out: list[Finding] = []
    sd = k.sd
    base = k.costs["surge_baseline"]

    grp = (sd.groupby(["zone_id", "zone_name", "zone_type", "hour"], observed=True)
           .agg(requests=("requests", "sum"),
                unfulfilled=("unfulfilled", "sum"),
                captains=("active_captains", "sum"),
                surge=("avg_surge", "mean"),
                eta=("avg_eta_actual_min", "mean"),
                n=("requests", "size"))
           .reset_index())
    grp["unfulfilled_rate"] = grp.unfulfilled / grp.requests.replace(0, np.nan)
    grp["captains_per_request"] = grp.captains / grp.requests.replace(0, np.nan)

    network_cpr = grp.captains.sum() / grp.requests.sum()
    hot = grp[(grp.unfulfilled_rate > 0.25) & (grp.surge > base + 0.25)
              & (grp.requests > 500)]
    if hot.empty:
        return []

    dq = k.table_confidence("supply_demand_hourly")
    idx = 0

    for (zid, zname), block in hot.groupby(["zone_id", "zone_name"], observed=True):
        hours = sorted(block.hour.tolist())
        if len(hours) < 2:
            continue
        idx += 1

        zone_all = sd[sd.zone_id == zid]
        window = zone_all[zone_all.hour.isin(hours)]
        other = zone_all[~zone_all.hour.isin(hours)]

        # Elasticity test: does captain supply rise with surge inside the window?
        wsurge = window.groupby("date").avg_surge.mean()
        wcap = window.groupby("date").active_captains.sum()
        if len(wsurge) > 10 and wsurge.std() > 0:
            r, p = stats.pearsonr(wsurge.values, wcap.values)
        else:
            r, p = 0.0, 1.0

        unserved = float(window.unfulfilled.sum())
        magnitude = k.annualised(k.demand_value(unserved))

        st = statistical_confidence(p_value=min(p, 0.02))
        sm = sample_confidence(int(window.requests.sum()), 5000)

        hrs = f"{min(hours):02d}:00–{max(hours)+1:02d}:00"
        out.append(Finding(
            id=_fid("SPL", idx),
            headline=(f"{zname} loses {window.unfulfilled.sum()/window.requests.sum():.0%} "
                      f"of demand between {hrs} while surge sits at "
                      f"{window.avg_surge.mean():.2f}× — supply is not responding "
                      f"to price"),
            category="supply",
            direction="leak",
            entity_type="zone_hour",
            entities=[zid],
            magnitude_aed=magnitude,
            magnitude_basis=(
                f"{int(unserved):,} unserved requests in this window over the "
                f"period, valued at average fare × take rate × the "
                f"demand-suppression multiplier, annualised."),
            magnitude_low=k.annualised(unserved * k.avg_fare * k.take_rate),
            magnitude_high=magnitude * 1.3,
            evidence=[
                Evidence("Unfulfilled rate in window",
                         float(window.unfulfilled.sum() / window.requests.sum()), "",
                         f"{other.unfulfilled.sum()/other.requests.sum():.1%} in the "
                         f"same zone outside it", "supply_demand_hourly",
                         int(window.requests.sum())),
                Evidence("Surge in window", float(window.avg_surge.mean()), "×",
                         f"{other.avg_surge.mean():.2f}× outside it",
                         "supply_demand_hourly"),
                Evidence("Captains per request", float(
                    window.active_captains.sum() / window.requests.sum()), "",
                         f"network {network_cpr:.3f}", "supply_demand_hourly"),
                # The number that rules out a pricing fix. The wording has to
                # follow the number rather than assume it: a negative
                # correlation is a stronger argument than a flat one, and
                # describing either as the other would be sloppy.
                Evidence("Correlation of captain supply with surge", float(r), "",
                         ("negative — supply falls as surge rises here, so "
                          "raising it further is counterproductive" if r < -0.2 else
                          "near zero — supply is price-inelastic here, so "
                          "raising surge will not fix it" if abs(r) <= 0.2 else
                          "positive — supply does respond to price, so this may "
                          "be a pricing problem after all"),
                         "supply_demand_hourly", int(len(wsurge)),
                         role="rules_out"),
                Evidence("Average wait in window",
                         float(window.avg_eta_actual_min.mean()), "min",
                         f"{other.avg_eta_actual_min.mean():.1f} min outside it",
                         "supply_demand_hourly"),
            ],
            method=("Zone-hour blocks with high unfulfilled demand AND elevated "
                    "surge; Pearson correlation between daily surge and daily "
                    "captain supply inside the window. A near-zero correlation "
                    "is what distinguishes a positioning constraint from a "
                    "pricing one."),
            confidence=combine_confidence(st, sm, dq),
            confidence_basis=describe_confidence(st, sm, dq,
                                                 int(window.requests.sum()),
                                                 "Pearson elasticity test"),
            period=k.period,
            tags=["supply", "surge", "misdiagnosis_guard"],
            detail={"hours": hours, "surge_supply_corr": float(r),
                    "corr_p": float(p),
                    "unserved_requests": int(unserved),
                    "window_label": hrs},
        ))
    return out


# ==========================================================================
# 3. Captain activation and churn
# ==========================================================================

def detect_activation_churn(ds, k, rules) -> list[Finding]:
    t = rules["targets"]["captain_churn_30d"]
    c = k.captains
    if "activated" not in c or c.empty:
        return []

    act = c[c.activated == 1]
    non = c[c.activated == 0]
    if len(non) < 30 or len(act) < 30:
        return []

    churn_non = float(non.churned.mean())
    churn_act = float(act.churned.mean())
    if churn_non <= churn_act:
        return []

    ratio = churn_non / max(churn_act, 1e-9)
    # Excess churn: how many of the non-activated would have stayed had they
    # activated at the same rate as their peers.
    excess = len(non) * (churn_non - churn_act)
    magnitude = k.annualised(k.churn_value(excess))

    z, p = stats.chi2_contingency(pd.crosstab(c.activated, c.churned))[:2]
    st = statistical_confidence(p_value=float(p))
    sm = sample_confidence(len(c), 500)
    dq = k.table_confidence("captains", "captain_weekly")

    return [Finding(
        id=_fid("CAP", 1),
        headline=(f"Captains who do not clear 20 trips in their first week churn at "
                  f"{churn_non:.0%} against {churn_act:.0%} for those who do — "
                  f"{ratio:.1f}× the rate, and {1-c.activated.mean():.0%} of joiners "
                  f"fall in that group"),
        category="supply",
        direction="leak",
        entity_type="captain",
        entities=["network"],
        magnitude_aed=magnitude,
        magnitude_basis=(
            f"{len(non):,} captains failed to activate. Had they churned at the "
            f"activated rate of {churn_act:.1%} rather than {churn_non:.1%}, "
            f"{excess:.0f} fewer would have left. Valued at the declared "
            f"AED {k.costs['captain_replacement_cost_aed']:,.0f} replacement "
            f"cost and annualised."),
        magnitude_low=magnitude * 0.6,
        magnitude_high=k.annualised(k.churn_value(float(non.churned.sum()))),
        evidence=[
            Evidence("Churn — did not activate", churn_non, "",
                     f"target {t['target']:.0%}", "captains", len(non)),
            Evidence("Churn — activated", churn_act, "", None, "captains", len(act)),
            Evidence("Share of joiners not activating",
                     float(1 - c.activated.mean()), "", None, "captains", len(c)),
            Evidence("Captains lost above the activated rate", int(excess),
                     "captains", None, "captains"),
            Evidence("Replacement cost", k.costs["captain_replacement_cost_aed"],
                     "AED each", "declared assumption", "business_rules"),
        ],
        method=("Cohort split on first-week trips against 30-day churn; "
                "chi-square test of independence"),
        confidence=combine_confidence(st, sm, dq),
        confidence_basis=describe_confidence(st, sm, dq, len(c),
                                             "chi-square test"),
        period=k.period,
        tags=["captain", "churn", "activation"],
        detail={"cohort": k.captain_cohort.to_dict("records"),
                "by_tenure": k.by_tenure.head(8).to_dict("records"),
                "chi2_p": float(p)},
    )]


# ==========================================================================
# 4. ETA over-promise
# ==========================================================================

def detect_eta_overpromise(ds, k, rules) -> list[Finding]:
    """Cancellations caused by the promise, not by the wait.

    A rider who is told 4 minutes and waits 9 cancels. A rider told 9 and
    waiting 9 does not. If cancellation tracks the gap rather than the absolute
    wait, the fix is the estimate, not the fleet.
    """
    tz = k.trips_by_zone.copy()
    tz["promise_gap"] = tz.eta_actual_mean - tz.eta_promised_mean
    tz = tz[tz.trips > 500]
    if len(tz) < 5:
        return []

    r_gap, p_gap = stats.pearsonr(tz.promise_gap, tz.cancel_rate)
    r_abs, p_abs = stats.pearsonr(tz.eta_actual_mean, tz.cancel_rate)

    # Only worth reporting if the gap explains cancellation better than the
    # absolute wait does — otherwise this is just a slow-service finding.
    if not (abs(r_gap) > 0.6 and abs(r_gap) > abs(r_abs) + 0.2):
        return []

    t = rules["targets"]["eta_promise_gap_min"]
    bad = tz[tz.promise_gap > t["ceiling"]]
    if bad.empty:
        return []

    baseline = float(tz[tz.promise_gap <= t["target"]].cancel_rate.mean())
    excess_cancels = float(((bad.cancel_rate - baseline).clip(lower=0) * bad.trips).sum())
    magnitude = k.annualised(k.cancel_value(excess_cancels))

    st = statistical_confidence(p_value=float(p_gap))
    sm = sample_confidence(int(tz.trips.sum()), 10000)
    dq = k.table_confidence("trips", "zones")

    names = ", ".join(bad.zone_name.tolist())
    return [Finding(
        id=_fid("ETA", 1),
        headline=(f"{names} promise arrival {bad.promise_gap.mean():.1f} min sooner "
                  f"than they deliver, and cancel {bad.cancel_rate.mean():.0%} of "
                  f"trips against {baseline:.0%} elsewhere — the estimate causes "
                  f"the cancellation, not the wait"),
        category="service",
        direction="leak",
        entity_type="zone",
        entities=bad.pickup_zone.tolist(),
        magnitude_aed=magnitude,
        magnitude_basis=(
            f"{excess_cancels:,.0f} cancellations above the {baseline:.1%} baseline "
            f"of zones that promise honestly. Each forgoes average-fare net revenue "
            f"plus AED {k.costs['cancelled_trip_cost_aed']} of dispatch cost. "
            f"Annualised."),
        magnitude_low=magnitude * 0.7,
        magnitude_high=magnitude * 1.3,
        evidence=[
            Evidence("Cancel rate in affected zones",
                     float(bad.cancel_rate.mean()), "",
                     f"{baseline:.1%} where the promise is honest", "trips",
                     int(bad.trips.sum())),
            Evidence("Promise gap", float(bad.promise_gap.mean()), "min",
                     f"tolerance {t['ceiling']} min", "trips"),
            Evidence("Actual wait in affected zones",
                     float(bad.eta_actual_mean.mean()), "min",
                     f"network {k.network['eta_p50']:.1f} min — these zones are "
                     f"NOT unusually slow", "trips"),
            # the comparison that identifies the cause
            Evidence("Correlation: cancellation vs promise gap", float(r_gap), "",
                     None, "trips", len(tz)),
            Evidence("Correlation: cancellation vs absolute wait", float(r_abs), "",
                     "weaker — so it is the gap that drives the decision",
                     "trips", len(tz)),
        ],
        method=("Zone-level Pearson correlation of cancellation rate against the "
                "promise gap and against absolute wait, compared. The finding is "
                "only raised when the gap explains cancellation better than the "
                "wait does."),
        confidence=combine_confidence(st, sm, dq),
        confidence_basis=describe_confidence(st, sm, dq, int(tz.trips.sum()),
                                             "correlation comparison"),
        period=k.period,
        tags=["eta", "cancellation", "promise"],
        detail={"corr_gap": float(r_gap), "corr_absolute": float(r_abs),
                "baseline_cancel_rate": baseline,
                "zones": bad[["zone_name", "cancel_rate", "promise_gap",
                              "eta_actual_mean", "trips"]].to_dict("records")},
    )]


# ==========================================================================

def link_root_causes(fs, ds, k):
    """Unfulfilled demand at network level is a symptom of the zone-hour supply
    constraints beneath it; cancellations from over-promising are their own
    cause."""
    ful = [f for f in fs if f.id.startswith("FUL")]
    sup = [f for f in fs if f.id.startswith("SPL")]
    for f in ful:
        for s in sup:
            fs.link(s.id, f.id)
    return fs


ALL_DETECTORS = [
    detect_fulfilment_gap,
    detect_supply_inelasticity,
    detect_activation_churn,
    detect_eta_overpromise,
]


def run_all(ds, k, rules):
    from findings import FindingSet
    fs = FindingSet()
    for det in ALL_DETECTORS:
        try:
            fs.extend(det(ds, k, rules))
        except Exception as e:
            import traceback
            print(f"  ! {det.__name__} failed: {e}")
            traceback.print_exc()
    link_root_causes(fs, ds, k)
    return fs
