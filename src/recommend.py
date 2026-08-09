"""
Recommendation engine
=====================
Turns findings into actions a named person could start on Monday.

Three rules that most tooling of this kind breaks:

1. **Capture rate is never 100%.** A finding worth AED 500k does not become a
   AED 500k recommendation. Some part of every leak is structural. The capture
   rate is declared in config and applied explicitly.

2. **Acting costs money, and the cost is netted off.** A recommendation whose
   cost exceeds its benefit is reported as such rather than quietly dropped —
   knowing an obvious fix does not pay is worth as much as knowing one does.

3. **Confidence governs stance.** Below the configured threshold an item is
   framed as "investigate", not "act". Recommending action on weak evidence is
   how analysis loses its credibility with the people who have to execute it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd


# ==========================================================================

@dataclass
class Recommendation:
    id: str
    title: str
    action: str                       # what to actually do, concretely
    owner: str
    horizon: str                      # immediate | near_term | structural
    effort: str                       # low | medium | high
    finding_ids: list[str] = field(default_factory=list)

    benefit_aed: float = 0.0          # annualised, after capture rate
    benefit_low: float = 0.0
    benefit_high: float = 0.0
    one_off_cost_aed: float = 0.0
    annual_cost_aed: float = 0.0
    net_annual_aed: float = 0.0
    payback_months: float | None = None

    stance: str = "act"               # act | investigate | reject
    confidence: float = 0.5
    risk: str = ""
    dependencies: list[str] = field(default_factory=list)
    success_metric: str = ""
    review_cadence: str = "monthly"
    assumptions: list[str] = field(default_factory=list)
    rationale: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class RecommendationSet:
    def __init__(self, items: list[Recommendation] | None = None):
        self.items = items or []

    def add(self, r: Recommendation | None):
        if r is not None:
            self.items.append(r)

    def __len__(self):
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    def ranked(self) -> list[Recommendation]:
        order = {"act": 0, "investigate": 1, "reject": 2}
        return sorted(self.items,
                      key=lambda r: (order.get(r.stance, 3), -r.net_annual_aed))

    def total_net_benefit(self) -> float:
        return sum(r.net_annual_aed for r in self.items if r.stance == "act")

    def total_investment(self) -> float:
        return sum(r.one_off_cost_aed for r in self.items if r.stance == "act")

    def table(self) -> pd.DataFrame:
        rows = []
        for r in self.ranked():
            rows.append({
                "id": r.id,
                "stance": r.stance,
                "owner": r.owner,
                "horizon": r.horizon,
                "effort": r.effort,
                "benefit/yr": round(r.benefit_aed),
                "cost/yr": round(r.annual_cost_aed),
                "one-off": round(r.one_off_cost_aed),
                "net/yr": round(r.net_annual_aed),
                "payback_mo": (None if r.payback_months is None
                               else round(r.payback_months, 1)),
                "conf": r.confidence,
                "title": r.title[:70],
            })
        return pd.DataFrame(rows)


# ==========================================================================
# shared costing
# ==========================================================================

def _finalise(r: Recommendation, rules: dict) -> Recommendation:
    """Net the costs, compute payback, and set the stance honestly."""
    r.net_annual_aed = r.benefit_aed - r.annual_cost_aed

    if r.net_annual_aed > 0 and r.one_off_cost_aed > 0:
        r.payback_months = 12 * r.one_off_cost_aed / r.net_annual_aed
    elif r.net_annual_aed > 0:
        r.payback_months = 0.0
    else:
        r.payback_months = None

    cfg = rules["recommendations"]
    threshold = cfg["act_confidence_threshold"]
    max_payback = cfg["max_payback_months"]

    if r.net_annual_aed <= 0:
        r.stance = "reject"
    elif r.confidence < threshold:
        r.stance = "investigate"
    elif r.payback_months is not None and r.payback_months > max_payback:
        r.stance = "investigate"
    else:
        r.stance = "act"
    return r


# ==========================================================================
# templates — one per finding class
# ==========================================================================

def rec_cadence(f, ds, k, rules) -> Recommendation:
    cfg = rules["recommendations"]
    cost = rules["costs"]
    cap = cfg["capture_rate"]["cadence_change"]
    d = f.detail
    review = ", ".join(d.get("review_days", []))
    peak = " and ".join(d.get("peak_days", []))

    benefit = f.magnitude_aed * cap
    one_off = cfg["cost_assumptions"]["process_change_cost_aed"]

    r = Recommendation(
        id="R1",
        title="Re-time replenishment review and forecast forward, not backward",
        action=(
            f"Two changes to the same process. First, move the replenishment "
            f"review off {review} so that at least one review lands within 48 "
            f"hours of the {peak} peak. Second — and this is the larger of the "
            f"two — size order quantities against forecast demand over the full "
            f"cover period rather than against the demand rate observed on the "
            f"review day itself. Review days are currently the quietest days of "
            f"the week, so every order is sized to a demand level the following "
            f"weekend will exceed by "
            f"{f.evidence[4].value:.0%}." if len(f.evidence) > 4 else
            f"Move the replenishment review off {review} and size orders against "
            f"forecast demand over the cover period rather than review-day demand."),
        owner="Demand Planning Lead",
        horizon="immediate",
        effort="medium",
        finding_ids=[f.id] + f.explains,
        benefit_aed=benefit,
        benefit_low=(f.magnitude_low or f.magnitude_aed) * cap * 0.7,
        benefit_high=(f.magnitude_high or f.magnitude_aed) * cap,
        one_off_cost_aed=one_off,
        annual_cost_aed=0.0,
        confidence=f.confidence,
        risk=("Ordering to a forward forecast raises average stock, so waste "
              "will rise on short-shelf-life lines unless the safety-stock "
              "factor is reduced at the same time. Sequence this after, or "
              "alongside, the pack-size work."),
        dependencies=["Supplier agreement to alternative order windows",
                      "Forecast available at store-SKU-day grain"],
        success_metric=("Weekly fill-rate spread (best day minus worst day) "
                        "below 5pp within two months; Monday fill rate above 92%"),
        review_cadence="weekly",
        assumptions=[
            f"Capture rate {cap:.0%} — a re-timed review recovers most but not "
            f"all of the weekly swing; some of it is supplier lead-time noise "
            f"that no calendar fixes.",
            f"One-off cost AED {one_off:,.0f} for system configuration, supplier "
            f"renegotiation of order windows, and planner training.",
        ],
        rationale=(
            "This is the largest single recoverable item and the cheapest to "
            "act on, because it is a scheduling decision rather than a capital "
            "or contractual one."),
    )
    return _finalise(r, rules)


def rec_pack_size(f, ds, k, rules) -> Recommendation:
    cfg = rules["recommendations"]
    ca = cfg["cost_assumptions"]
    cap = cfg["capture_rate"]["pack_resize"]
    d = f.detail

    n_lines = len(d.get("worst_lines", [])) or 0
    by_sup = d.get("by_supplier", [])
    top = by_sup[0] if by_sup else {}
    sup_name = ds.table("suppliers").set_index("supplier_id").get(
        "supplier_name", pd.Series()).to_dict().get(top.get("supplier_id"), "the "
                                                    "largest contributing supplier")

    # Cost: smaller lots carry a unit-cost premium on the affected purchase value.
    skus = ds.table("skus").set_index("sku_id")
    affected_skus = {w["sku_id"] for w in d.get("worst_lines", [])}
    po = k.po
    affected_value = float(po[po.sku_id.isin(affected_skus)].po_value_aed.sum())
    annual_cost = k.annualised(affected_value) * ca["pack_resize_unit_cost_premium_pct"]

    benefit = f.magnitude_aed * cap

    r = Recommendation(
        id="R2",
        title="Re-specify case packs on short-shelf-life lines",
        action=(
            f"Renegotiate minimum order quantity on the store-SKU lines where a "
            f"single case cannot be sold within the product's shelf life. Target "
            f"a pack size giving no more than 50% of shelf life in cover at "
            f"current velocity. Open with {sup_name}, which accounts for the "
            f"largest share of the affected write-off. Where a supplier will not "
            f"break the pack, the alternative is cross-docking a single delivery "
            f"across two or three stores rather than forcing full cases into each."),
        owner="Procurement Lead",
        horizon="near_term",
        effort="high",
        finding_ids=[f.id] + f.explains,
        benefit_aed=benefit,
        benefit_low=(f.magnitude_low or f.magnitude_aed) * cap,
        benefit_high=(f.magnitude_high or f.magnitude_aed) * cap,
        one_off_cost_aed=0.0,
        annual_cost_aed=annual_cost,
        confidence=f.confidence,
        risk=("Suppliers will price smaller lots higher, and may resist on "
              "handling grounds. If the achieved premium exceeds "
              f"{ca['pack_resize_unit_cost_premium_pct']:.1%} the case weakens "
              f"quickly — this should be re-tested against actual quoted terms "
              f"before committing."),
        dependencies=["Supplier contract review", "Store-level cross-dock capability"],
        success_metric=("Waste rate on affected lines below 4% within one "
                        "quarter; no fill-rate deterioration on the same lines"),
        review_cadence="monthly",
        assumptions=[
            f"Capture rate {cap:.0%} — a right-sized pack removes the guaranteed "
            f"expiry but not waste caused by demand volatility.",
            f"Unit-cost premium of {ca['pack_resize_unit_cost_premium_pct']:.1%} "
            f"on AED {k.annualised(affected_value):,.0f} of annual purchase value "
            f"on affected lines. THIS IS THE WEAKEST ASSUMPTION IN THE ANALYSIS "
            f"— it is a placeholder until suppliers quote.",
        ],
        rationale=(
            "The write-off on these lines is not an execution failure. No amount "
            "of store discipline recovers it, because the stock is guaranteed to "
            "expire from the moment it is ordered. It is a single procurement "
            "decision with a single owner."),
    )
    return _finalise(r, rules)


def rec_supplier(f, ds, k, rules) -> Recommendation:
    cfg = rules["recommendations"]
    ca = cfg["cost_assumptions"]
    cap = cfg["capture_rate"]["supplier_remediation"]
    d = f.detail
    sup_id = f.entities[0]
    sup = ds.table("suppliers").set_index("supplier_id").loc[sup_id]
    cp = d.get("changepoint_month")
    narrative = d.get("narrative", "")

    po = k.po
    spend = k.annualised(float(po[po.supplier_id == sup_id].po_value_aed.sum()))
    annual_cost = spend * 0.4 * ca["dual_source_premium_pct"]   # dual-source 40% of volume
    benefit = f.magnitude_aed * cap

    r = Recommendation(
        id="R3",
        title=f"Put {sup['supplier_name']} on a formal performance plan and dual-source",
        action=(
            f"Three steps. (1) Raise a supplier performance plan with a contractual "
            f"OTIF floor and weekly reporting"
            + (f"; the degradation is recent and datable — {narrative.lower()}"
               if narrative else "") +
            f" (2) Dual-source roughly 40% of volume on the highest-velocity lines "
            f"this supplier covers, to cap exposure while the plan runs. "
            f"(3) Until on-time performance recovers, raise the safety-stock factor "
            f"on affected lines to absorb the observed lead-time variability of "
            f"{sup['promised_lead_time_days']:.0f}-day promise against "
            f"{f.evidence[3].value:.2f}-day actual."),
        owner="Procurement Lead",
        horizon="near_term",
        effort="medium",
        finding_ids=[f.id],
        benefit_aed=benefit,
        benefit_low=(f.magnitude_low or f.magnitude_aed) * cap,
        benefit_high=(f.magnitude_high or f.magnitude_aed) * cap,
        one_off_cost_aed=0.0,
        annual_cost_aed=annual_cost,
        confidence=f.confidence,
        risk=("Dual-sourcing fresh produce splits volume and may weaken terms "
              "with both suppliers. Temporary safety-stock uplift raises waste "
              "on a short-shelf-life category — this is a deliberate trade of "
              "waste for availability and should be time-boxed."),
        dependencies=["Alternative supplier qualification", "Contract amendment"],
        success_metric=(f"OTIF above {rules['targets']['otif']['floor']:.0%} within "
                        f"one quarter; lead-time CV below "
                        f"{rules['targets']['supplier_lead_time_cv']['ceiling']:.2f}"),
        review_cadence="weekly",
        assumptions=[
            f"Capture rate {cap:.0%} — supplier remediation is slow and partial; "
            f"a plan rarely restores full performance inside a year.",
            f"Dual-source premium {ca['dual_source_premium_pct']:.1%} on 40% of "
            f"AED {spend:,.0f} annual spend with this supplier.",
        ],
        rationale=(
            "This is a datable change in a single supplier's behaviour, not a "
            "gradual drift, which makes it both diagnosable and negotiable."),
    )
    return _finalise(r, rules)


def rec_assortment(f, ds, k, rules) -> Recommendation:
    cfg = rules["recommendations"]
    ca = cfg["cost_assumptions"]
    cap = cfg["capture_rate"]["assortment_rationalisation"]
    d = f.detail
    slots = d.get("tail_slots", 0)
    n_tail = len(d.get("tail", []))

    benefit = f.magnitude_aed * cap
    one_off = slots * ca["delist_cost_per_slot_aed"]

    r = Recommendation(
        id="R4",
        title="Rationalise the slow-moving tail and reallocate the slots",
        action=(
            f"Delist the slowest-moving lines across {slots:,} store-SKU slots, "
            f"protecting any line that is a known basket-builder or a "
            f"category-completeness requirement. Reallocate freed slots to the "
            f"top revenue decile, where availability is currently the binding "
            f"constraint. Run it market by market rather than network-wide so "
            f"the demand-migration assumption can be tested on the first market "
            f"before the rest follow."),
        owner="Category Manager",
        horizon="near_term",
        effort="medium",
        finding_ids=[f.id],
        benefit_aed=benefit,
        benefit_low=(f.magnitude_low or f.magnitude_aed) * cap,
        benefit_high=(f.magnitude_high or f.magnitude_aed) * cap,
        one_off_cost_aed=one_off,
        annual_cost_aed=0.0,
        confidence=f.confidence,
        risk=("Range perception. Customers do not experience a delist as an "
              "efficiency gain, and quick-commerce baskets are sensitive to "
              "one-missing-item abandonment. The 50% demand-migration "
              "assumption behind the benefit is unverified and is the number "
              "most likely to be wrong."),
        dependencies=["Category review", "Basket-affinity analysis before cutting"],
        success_metric=("Slot productivity (revenue per slot) up 10% within two "
                        "quarters with no fall in basket size or order frequency"),
        review_cadence="monthly",
        assumptions=[
            f"Capture rate {cap:.0%} of the modelled slot and waste saving.",
            f"Half the demand on delisted lines migrates to remaining range. "
            f"Unverified — a basket-affinity analysis should precede execution.",
            f"Range reset costs AED {ca['delist_cost_per_slot_aed']}/slot.",
        ],
        rationale=(
            "The tail consumes slot capacity and write-off out of all proportion "
            "to what it earns, and those slots are the same constraint limiting "
            "availability on the lines that do sell."),
    )
    return _finalise(r, rules)


def rec_fleet(f, ds, k, rules) -> list[Recommendation]:
    """Two costed options, because the obvious one does not pay.

    Sizing the fleet to the utilisation target costs more than the
    cancellations it prevents. Re-timing existing shifts to the peak does not.
    Presenting both, with the arithmetic, is more useful than presenting the
    one that happens to work.
    """
    cfg = rules["recommendations"]
    ca = cfg["cost_assumptions"]
    costs = rules["costs"]
    d = f.detail
    store_id = f.entities[0]
    store = ds.table("dark_stores").set_index("store_id").loc[store_id]

    shortfall = d.get("captains_shortfall_per_day", 0.0)
    headcount_cost = shortfall * costs["captain_shift_cost_aed"] * 365

    # how concentrated is this store's demand?
    od = k.orders
    mine = od[od.store_id == store_id]
    peak_hours = mine.hour.value_counts().nlargest(4).index.tolist()
    peak_share = float(mine.hour.isin(peak_hours).mean())
    peak_delivery = float(mine[mine.hour.isin(peak_hours)].actual_minutes.mean())
    off_delivery = float(mine[~mine.hour.isin(peak_hours)].actual_minutes.mean())

    out = []

    # ---- option A: re-time shifts ---------------------------------------
    capA = cfg["capture_rate"]["fleet_scheduling"]
    rA = Recommendation(
        id="R5a",
        title=f"Re-time captain shifts at {store['store_name']} to the demand peak",
        action=(
            f"{peak_share:.0%} of this store's orders fall in four hours "
            f"({', '.join(f'{h:02d}:00' for h in sorted(peak_hours))}), and "
            f"delivery time in those hours averages {peak_delivery:.0f} min "
            f"against {off_delivery:.0f} min outside them. Rebuild the shift "
            f"pattern so captain hours track that curve, before adding any "
            f"headcount. This is a rostering change, not a hiring decision."),
        owner="Fleet Operations Manager",
        horizon="immediate",
        effort="low",
        finding_ids=[f.id],
        benefit_aed=f.magnitude_aed * capA,
        benefit_low=f.magnitude_aed * capA * 0.6,
        benefit_high=f.magnitude_aed * capA * 1.2,
        one_off_cost_aed=ca["shift_reschedule_cost_aed"],
        annual_cost_aed=0.0,
        confidence=f.confidence,
        risk=("Captain availability may not be elastic to the required hours, "
              "and late-evening shifts may need a pay differential that is not "
              "costed here."),
        dependencies=["Captain supply at peak hours", "Rostering system change"],
        success_metric=(f"Delivery p50 at {store['store_name']} below 25 min and "
                        f"cancellation rate below "
                        f"{rules['targets']['order_cancel_rate']['ceiling']:.1%} "
                        f"within six weeks"),
        review_cadence="weekly",
        assumptions=[
            f"Capture rate {capA:.0%} — re-timing addresses the peak-hour "
            f"constraint but not total daily capacity.",
            f"Rescheduling cost AED {ca['shift_reschedule_cost_aed']:,.0f}, "
            f"no incremental headcount.",
        ],
        rationale=(
            "Do this first because it is cheap and reversible, and because it "
            "tests whether the constraint is genuinely total capacity or merely "
            "its distribution across the day."),
    )
    out.append(_finalise(rA, rules))

    # ---- option B: add headcount ----------------------------------------
    capB = cfg["capture_rate"]["fleet_headcount"]
    rB = Recommendation(
        id="R5b",
        title=f"Add {shortfall:.1f} captain shifts/day at {store['store_name']}",
        action=(
            f"Increase the fleet at {store['store_name']} by roughly "
            f"{shortfall:.1f} captain-shifts per day to bring utilisation from "
            f"{d.get('avg_orders', 0) / max(d.get('avg_captains', 1) * costs['deliveries_per_captain_shift'], 1):.0%} "
            f"down to the {rules['targets']['fleet_utilisation']['target']:.0%} "
            f"target."),
        owner="Fleet Operations Manager",
        horizon="near_term",
        effort="medium",
        finding_ids=[f.id],
        benefit_aed=f.magnitude_aed * capB,
        benefit_low=f.magnitude_aed * capB * 0.7,
        benefit_high=f.magnitude_aed * capB * 1.2,
        one_off_cost_aed=0.0,
        annual_cost_aed=headcount_cost,
        confidence=f.confidence,
        risk="Adds fixed cost that is hard to reverse if demand softens.",
        dependencies=["Captain recruitment in Sharjah"],
        success_metric=f"Fleet utilisation between 65% and 95% on 90% of days",
        review_cadence="monthly",
        assumptions=[
            f"Capture rate {capB:.0%} — sizing to target utilisation removes "
            f"most capacity-driven cancellations.",
            f"{shortfall:.1f} shifts/day at AED "
            f"{costs['captain_shift_cost_aed']:,.0f} = AED {headcount_cost:,.0f}/yr.",
        ],
        rationale=(
            "Presented for completeness and because it is the intuitive answer. "
            "On these numbers it does not pay: the cost of the capacity exceeds "
            "the value of the cancellations it would prevent. Worth revisiting "
            "only if the rostering change fails, or if the lost lifetime value "
            "of repeatedly failed customers is judged materially higher than "
            "the single-order margin used here."),
    )
    out.append(_finalise(rB, rules))
    return out


def rec_seasonal(f, ds, k, rules) -> Recommendation:
    cfg = rules["recommendations"]
    ca = cfg["cost_assumptions"]
    cap = cfg["capture_rate"]["seasonal_playbook"]
    d = f.detail
    lift = d.get("lift", 0)
    night_in = d.get("night_share_in", 0)
    night_out = d.get("night_share_out", 0)

    benefit = f.magnitude_aed * cap
    one_off = ca["seasonal_playbook_cost_aed"]

    r = Recommendation(
        id="R6",
        title="Build a Ramadan operating playbook",
        action=(
            f"Codify the peak as a planned event rather than an annual surprise. "
            f"Volume rises {lift:.0%} and the daypart mix inverts — "
            f"{night_in:.0%} of orders fall after 20:00 against {night_out:.0%} "
            f"normally. The playbook needs three things: a demand uplift applied "
            f"at category level in the forecast, a replenishment window moved to "
            f"late night so shelves are full when demand arrives, and captain "
            f"shifts weighted to the post-Iftar window. Lock it four weeks before "
            f"the window opens."),
        owner="Supply Chain Director",
        horizon="structural",
        effort="medium",
        finding_ids=[f.id],
        benefit_aed=benefit,
        benefit_low=(f.magnitude_low or f.magnitude_aed) * cap * 0.6,
        benefit_high=(f.magnitude_high or f.magnitude_aed) * cap * 1.3,
        one_off_cost_aed=one_off,
        annual_cost_aed=0.0,
        confidence=f.confidence,
        risk=("The window moves roughly eleven days earlier each year, so a "
              "playbook tied to calendar dates rather than the lunar date will "
              "drift. Two observed cycles is a thin basis for a category-level "
              "uplift factor."),
        dependencies=["Category-level demand model", "Supplier late-window delivery"],
        success_metric=("Fill rate inside the peak window within 2pp of the "
                        "annual average, versus the current shortfall"),
        review_cadence="annual, with a post-event review",
        assumptions=[
            f"Capture rate {cap:.0%} — planning improves availability but a "
            f"{lift:.0%} surge will not be fully absorbed in the first year.",
            f"Playbook development cost AED {one_off:,.0f}.",
            "Based on two observed cycles. Treat the uplift factor as "
            "provisional and re-fit after the next one.",
        ],
        rationale=(
            "This is the only finding in the set that is fully predictable in "
            "advance, which makes it the cheapest kind of problem to solve."),
    )
    return _finalise(r, rules)


# ==========================================================================

SUPPLY_CHAIN_TEMPLATES = {
    "CAD": rec_cadence,
    "LOT": rec_pack_size,
    "SUP": rec_supplier,
    "AST": rec_assortment,
    "FLT": rec_fleet,
    "SEA": rec_seasonal,
}

# Backwards-compatible alias.
TEMPLATES = SUPPLY_CHAIN_TEMPLATES


def get_templates(ds) -> dict:
    """Recommendation templates for the dataset's domain.

    The templates are domain-specific — turning a finding into "renegotiate the
    case pack with this supplier" requires knowing what a case pack is. Keying
    them on finding-ID prefix alone was a latent bug: two domains both used the
    prefix `SUP` (supplier, and supply), so loading a second dataset silently
    routed its findings into supply-chain templates and crashed on a missing
    config key.
    """
    domain = ds.semantic["dataset"].get("domain", "supply_chain")
    if domain == "rides":
        import recommend_rides
        return recommend_rides.TEMPLATES
    return SUPPLY_CHAIN_TEMPLATES


def build(fs, ds, k, rules) -> RecommendationSet:
    """One recommendation per material root-cause finding.

    Symptoms do not get their own action — they are addressed by fixing what
    causes them. Generating a recommendation per finding is how a brief ends
    up asking for twelve things when the business can do three.
    """
    rs = RecommendationSet()
    seen: set[str] = set()
    templates = get_templates(ds)

    for f in fs.ranked(rules):
        if not f.is_material(rules):
            continue
        if f.caused_by:                       # a symptom — its cause carries the action
            continue
        prefix = f.id.split("-")[0]
        if prefix in seen or prefix not in templates:
            continue
        seen.add(prefix)
        try:
            result = templates[prefix](f, ds, k, rules)
        except Exception as e:
            import traceback
            print(f"  ! recommendation for {f.id} failed: {e}")
            traceback.print_exc()
            continue
        if isinstance(result, list):
            for r in result:
                rs.add(r)
        else:
            rs.add(result)
    return rs
