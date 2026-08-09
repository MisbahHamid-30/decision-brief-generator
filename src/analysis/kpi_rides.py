"""
Rides KPI engine
================
The marketplace equivalent of the supply-chain engine. Same base class, same
interface, entirely different metrics — which is the point.

Where the supply-chain engine asks "was the stock on the shelf", this asks
"was there a captain in the zone". Where that one converts write-off into
money, this converts unfulfilled requests and captain churn into money.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .kpi_base import BaseKPI


class RidesKPI(BaseKPI):

    def __init__(self, ds, quality_report=None):
        super().__init__(ds, quality_report)
        self._build_base()
        self._build_grains()

    # ------------------------------------------------------------------

    def _build_base(self):
        ds = self.ds

        sd = ds.enrich("supply_demand_hourly").copy()
        sd["date"] = sd.datetime.dt.normalize()
        sd["hour"] = sd.datetime.dt.hour
        sd["dow"] = sd.datetime.dt.dayofweek
        sd["month"] = sd.datetime.dt.to_period("M").astype(str)
        sd["pressure"] = sd.requests / sd.active_captains.replace(0, np.nan)
        self.sd = sd
        self._set_period_from(sd.date)

        tr = ds.enrich("trips").copy()
        tr["date"] = tr.requested_at.dt.normalize()
        tr["hour"] = tr.requested_at.dt.hour
        tr["dow"] = tr.requested_at.dt.dayofweek
        tr["month"] = tr.requested_at.dt.to_period("M").astype(str)
        tr["completed_flag"] = (tr.status == "completed").astype(int)
        tr["cancelled_flag"] = (tr.status == "cancelled_rider").astype(int)
        tr["eta_gap"] = tr.eta_actual_min - tr.eta_promised_min
        self.trips = tr

        self.captains = ds.table("captains").copy()
        self.captain_weekly = ds.enrich("captain_weekly").copy()

        self.take_rate = self.costs["take_rate"]
        self.avg_fare = float(tr.loc[tr.completed_flag == 1, "fare_aed"].mean())

    # ------------------------------------------------------------------

    @staticmethod
    def _zone_metrics(g: pd.DataFrame) -> pd.Series:
        req = g.requests.sum()
        comp = g.completed.sum()
        return pd.Series({
            "requests": req,
            "completed": comp,
            "unfulfilled": g.unfulfilled.sum(),
            "fulfilment_rate": comp / req if req else np.nan,
            "active_captains": g.active_captains.sum(),
            "captains_per_request": g.active_captains.sum() / req if req else np.nan,
            "surge_mean": g.avg_surge.mean(),
            "eta_actual_mean": g.avg_eta_actual_min.mean(),
            "eta_promised_mean": g.avg_eta_promised_min.mean(),
            "n_hours": len(g),
        })

    @staticmethod
    def _trip_metrics(g: pd.DataFrame) -> pd.Series:
        n = len(g)
        comp = g.completed_flag.sum()
        return pd.Series({
            "trips": n,
            "completed": comp,
            "cancelled": g.cancelled_flag.sum(),
            "cancel_rate": g.cancelled_flag.mean(),
            "gross_bookings_aed": g.fare_aed.sum(),
            "avg_fare_aed": g.loc[g.completed_flag == 1, "fare_aed"].mean(),
            "eta_promised_mean": g.eta_promised_min.mean(),
            "eta_actual_mean": g.eta_actual_min.mean(),
            "eta_gap_mean": g.eta_gap.mean(),
            "rating_mean": g.rider_rating.mean(),
        })

    def _build_grains(self):
        self.by_zone = self.agg(self.sd, ["zone_id", "zone_name", "zone_type",
                                          "city_id"], self._zone_metrics)
        self.by_zone_hour = self.agg(self.sd, ["zone_id", "zone_name", "hour"],
                                     self._zone_metrics)
        self.by_hour = self.agg(self.sd, ["hour"], self._zone_metrics)
        self.by_city = self.agg(self.sd, ["city_id"], self._zone_metrics)
        self.by_zone_type = self.agg(self.sd, ["zone_type"], self._zone_metrics)
        self.daily = self.agg(self.sd, ["date"], self._zone_metrics)

        self.trips_by_zone = self.agg(self.trips,
                                      ["pickup_zone", "zone_name", "zone_type"],
                                      self._trip_metrics)
        self.trips_by_hour = self.agg(self.trips, ["hour"], self._trip_metrics)
        self.trips_by_city = self.agg(self.trips, ["city_id"], self._trip_metrics)
        self.trips_daily = self.agg(self.trips, ["date"], self._trip_metrics)

        self._build_captains()

    def _build_captains(self):
        c = self.captains
        c["activated"] = (c.first_week_trips >= 20).astype(int)
        c["churned"] = (c.status == "churned").astype(int)
        self.captain_cohort = (c.groupby(["city_id", "activated"], observed=True)
                               .agg(captains=("captain_id", "count"),
                                    churn_rate=("churned", "mean"),
                                    first_week_trips=("first_week_trips", "mean"))
                               .reset_index())

        cw = self.captain_weekly
        cw["trips_per_hour"] = cw.trips / cw.online_hours.replace(0, np.nan)
        self.captain_weekly = cw
        self.by_tenure = (cw.groupby("weeks_tenure", observed=True)
                          .agg(captains=("captain_id", "nunique"),
                               trips=("trips", "mean"),
                               hours=("online_hours", "mean"),
                               earnings=("earnings_aed", "mean"),
                               trips_per_hour=("trips_per_hour", "mean"),
                               acceptance=("acceptance_rate", "mean"))
                          .reset_index())

    # ------------------------------------------------------------------

    @property
    def network(self) -> dict:
        sd, tr, c = self.sd, self.trips, self.captains
        req = float(sd.requests.sum())
        comp = float(sd.completed.sum())
        unf = float(sd.unfulfilled.sum())

        gross = float(tr.loc[tr.completed_flag == 1, "fare_aed"].sum())
        net_rev = gross * self.take_rate

        lost_unf = (unf * self.avg_fare * self.take_rate
                    * self.costs["unfulfilled_demand_multiplier"])
        n_cancel = float(tr.cancelled_flag.sum())
        lost_cancel = (n_cancel * self.avg_fare * self.take_rate
                       + n_cancel * self.costs["cancelled_trip_cost_aed"])
        churned = float(c.churned.sum())
        churn_cost = churned * self.costs["captain_replacement_cost_aed"]
        # Fare charged above the baseline multiplier. The rider pays it, so it
        # is not a platform cost — but it suppresses demand, so it belongs in
        # the waterfall as a drag on the top line rather than a leak.
        base_mult = self.costs["surge_baseline"]
        done = tr[tr.completed_flag == 1]
        surge_sub = float(
            (done.fare_aed * (1 - base_mult / done.surge_multiplier.clip(lower=base_mult))
             ).sum()) * self.take_rate

        return {
            "period_start": str(self.date_min.date()),
            "period_end": str(self.date_max.date()),
            "days": self.n_days,
            "annualisation_factor": round(self.annualise, 4),

            "requests": req,
            "completed_trips": comp,
            "unfulfilled_requests": unf,
            "fulfilment_rate": comp / req if req else np.nan,
            "rider_cancel_rate": float(tr.cancelled_flag.mean()),

            "gross_bookings_aed": gross,
            "net_revenue_aed": net_rev,
            "avg_fare_aed": self.avg_fare,
            "lost_revenue_unfulfilled_aed": lost_unf,
            "lost_revenue_cancel_aed": lost_cancel,
            "surge_subsidy_aed": surge_sub,

            "eta_p50": float(tr.eta_actual_min.median()),
            "eta_p90": float(tr.eta_actual_min.quantile(0.90)),
            "eta_gap_mean": float(tr.eta_gap.mean()),
            "surge_mean": float(sd.avg_surge.mean()),

            "captains": int(len(c)),
            "captain_churn_rate": float(c.churned.mean()),
            "captain_activation_rate": float(c.activated.mean()),
            "churn_replacement_cost_aed": churn_cost,
            "captain_utilisation": float(self.captain_weekly.trips_per_hour.mean()),

            "rider_rating_mean": float(tr.rider_rating.mean()),
        }

    # ------------------------------------------------------------------
    # Domain money conversion
    # ------------------------------------------------------------------

    def demand_value(self, n_requests: float) -> float:
        """Net revenue a block of unserved requests would have produced."""
        return float(n_requests * self.avg_fare * self.take_rate
                     * self.costs["unfulfilled_demand_multiplier"])

    def cancel_value(self, n_trips: float) -> float:
        return float(n_trips * (self.avg_fare * self.take_rate
                                + self.costs["cancelled_trip_cost_aed"]))

    def churn_value(self, n_captains: float) -> float:
        return float(n_captains * self.costs["captain_replacement_cost_aed"])
