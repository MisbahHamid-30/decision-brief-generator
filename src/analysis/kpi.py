"""
KPI engine
==========
Computes the supply-chain metric set once, at every grain the detectors need,
and converts operational failures into money using the declared assumptions in
`config/business_rules.yaml`.

Everything downstream reads from here. No detector recomputes a KPI, so the
brief, the dashboard and the deck cannot disagree with each other about what
the fill rate was.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .kpi_base import BaseKPI, DAYS_PER_YEAR


class KPIEngine(BaseKPI):
    """Supply-chain KPI engine.

    Everything here is specific to a stock-holding, supplier-fed operation.
    The generic machinery — period arithmetic, annualisation, confidence, and
    the config-driven scorecard and waterfall — lives in BaseKPI.
    """

    def __init__(self, ds, quality_report=None):
        super().__init__(ds, quality_report)
        self._build_base()
        self._build_grains()

    # ------------------------------------------------------------------
    # Base frames
    # ------------------------------------------------------------------

    def _build_base(self):
        ds = self.ds

        # --- inventory fact, enriched and monetised ---------------------
        inv = ds.enrich("inventory_daily").copy()
        inv["revenue_aed"] = inv.sold_units * inv.unit_price_aed
        inv["cogs_aed"] = inv.sold_units * inv.unit_cost_aed
        inv["margin_aed"] = inv.revenue_aed - inv.cogs_aed
        inv["waste_cost_aed"] = inv.wasted_units * inv.unit_cost_aed
        inv["lost_units"] = inv.lost_demand_units
        inv["lost_margin_aed"] = (inv.lost_demand_units
                                  * (inv.unit_price_aed - inv.unit_cost_aed))
        inv["demand_units"] = inv.sold_units + inv.lost_demand_units
        inv["stock_value_aed"] = inv.closing_units * inv.unit_cost_aed
        inv["dow"] = inv.date.dt.dayofweek
        inv["month"] = inv.date.dt.to_period("M").astype(str)
        self.inv = inv

        # --- period -----------------------------------------------------
        self._set_period_from(inv.date)

        # --- purchase orders --------------------------------------------
        po = ds.enrich("purchase_orders").copy()
        po["lead_days"] = (po.received_date - po.order_date).dt.days
        po["promised_lead_days"] = (po.promised_date - po.order_date).dt.days
        po["on_time"] = (po.received_date <= po.promised_date).astype(int)
        po["in_full"] = (po.qty_received >= po.qty_ordered).astype(int)
        po["otif"] = po.on_time * po.in_full
        po["fill_ratio"] = po.qty_received / po.qty_ordered.replace(0, np.nan)
        po["short_units"] = (po.qty_ordered - po.qty_received).clip(lower=0)
        po["short_cost_aed"] = po.short_units * po.unit_cost_aed
        po["month"] = po.order_date.dt.to_period("M").astype(str)
        self.po = po

        # --- orders / service -------------------------------------------
        od = ds.enrich("orders").copy()
        od["date"] = od.order_datetime.dt.normalize()
        od["hour"] = od.order_datetime.dt.hour
        od["dow"] = od.order_datetime.dt.dayofweek
        od["month"] = od.order_datetime.dt.to_period("M").astype(str)
        od["delivered"] = (od.status == "delivered").astype(int)
        od["late"] = (od.actual_minutes > od.promised_minutes).astype(int)
        self.orders = od

        # --- fleet -------------------------------------------------------
        self.fleet = ds.enrich("courier_daily").copy()

    # ------------------------------------------------------------------
    # Metric definitions
    # ------------------------------------------------------------------

    @staticmethod
    def _inv_metrics(g: pd.DataFrame) -> pd.Series:
        sold = g.sold_units.sum()
        lost = g.lost_units.sum()
        recv = g.received_units.sum()
        demand = sold + lost
        return pd.Series({
            "revenue_aed": g.revenue_aed.sum(),
            "cogs_aed": g.cogs_aed.sum(),
            "margin_aed": g.margin_aed.sum(),
            "units_sold": sold,
            "units_lost": lost,
            "units_received": recv,
            "units_wasted": g.wasted_units.sum(),
            "waste_cost_aed": g.waste_cost_aed.sum(),
            "lost_margin_aed": g.lost_margin_aed.sum(),
            "fill_rate": sold / demand if demand else np.nan,
            "waste_rate": g.wasted_units.sum() / recv if recv else np.nan,
            "stockout_day_rate": g.stockout_flag.mean(),
            "avg_stock_value_aed": g.stock_value_aed.mean(),
            "n_rows": len(g),
        })

    def _agg_inv(self, by) -> pd.DataFrame:
        out = (self.inv.groupby(by, observed=True)
               .apply(self._inv_metrics, include_groups=False)
               .reset_index())
        # days of cover and turns need a daily rate
        days = self.inv.groupby(by, observed=True)["date"].nunique().values
        daily_cogs = out.cogs_aed / np.maximum(days, 1)
        out["days_of_cover"] = out.avg_stock_value_aed / daily_cogs.replace(0, np.nan)
        out["inventory_turns_annual"] = (
            out.cogs_aed * self.annualise / out.avg_stock_value_aed.replace(0, np.nan))
        out["margin_pct"] = out.margin_aed / out.revenue_aed.replace(0, np.nan)
        return out

    # ------------------------------------------------------------------
    # Grains
    # ------------------------------------------------------------------

    def _build_grains(self):
        self.by_store = self._agg_inv(["store_id", "store_name", "city"])
        self.by_category = self._agg_inv(["category"])
        self.by_store_category = self._agg_inv(["store_id", "store_name", "city", "category"])
        self.by_supplier_cat = self._agg_inv(["supplier_id", "category"])
        self.by_sku = self._agg_inv(["sku_id", "category", "supplier_id"])
        self.by_dow = self._agg_inv(["dow"])
        self.by_month = self._agg_inv(["month"])
        self.by_city = self._agg_inv(["city"])
        self.by_city_category = self._agg_inv(["city", "category"])

        # daily network series (for trend / seasonality / anomaly work)
        self.daily = (self.inv.groupby("date", observed=True)
                      .apply(self._inv_metrics, include_groups=False)
                      .reset_index())

        self._build_supplier()
        self._build_service()
        self._build_fleet()

    def _build_supplier(self):
        po = self.po
        g = po.groupby(["supplier_id", "supplier_name"], observed=True)
        self.by_supplier = g.apply(lambda x: pd.Series({
            "po_lines": len(x),
            "po_value_aed": x.po_value_aed.sum(),
            "lead_time_mean": x.lead_days.mean(),
            "lead_time_sd": x.lead_days.std(),
            "lead_time_cv": x.lead_days.std() / max(x.lead_days.mean(), 1e-9),
            "promised_lead": x.promised_lead_days.mean(),
            "lead_time_gap": x.lead_days.mean() - x.promised_lead_days.mean(),
            "on_time_rate": x.on_time.mean(),
            "in_full_rate": x.in_full.mean(),
            "otif": x.otif.mean(),
            "fill_ratio": x.fill_ratio.mean(),
            "short_units": x.short_units.sum(),
            "short_cost_aed": x.short_cost_aed.sum(),
        }), include_groups=False).reset_index()

        self.supplier_monthly = po.groupby(
            ["supplier_id", "month"], observed=True).apply(lambda x: pd.Series({
                "lead_time_mean": x.lead_days.mean(),
                "lead_time_sd": x.lead_days.std(),
                "otif": x.otif.mean(),
                "fill_ratio": x.fill_ratio.mean(),
                "po_lines": len(x),
            }), include_groups=False).reset_index()

    def _build_service(self):
        od = self.orders
        cost_cancel = self.costs["cancelled_order_cost_aed"]

        def svc(x):
            n = len(x)
            cancels = n - x.delivered.sum()
            return pd.Series({
                "orders": n,
                "delivered": x.delivered.sum(),
                "cancel_rate": cancels / n if n else np.nan,
                "cancel_cost_aed": cancels * cost_cancel,
                "delivery_p50": x.actual_minutes.median(),
                "delivery_p90": x.actual_minutes.quantile(0.90),
                "late_rate": x.late.mean(),
                "revenue_aed": x.basket_value_aed.sum(),
                "margin_aed": (x.basket_value_aed - x.basket_cogs_aed).sum(),
                "avg_basket_aed": x.basket_value_aed.mean(),
            })

        self.service_by_store = (od.groupby(["store_id", "store_name", "city"],
                                            observed=True)
                                 .apply(svc, include_groups=False).reset_index())
        self.service_by_hour = od.groupby("hour", observed=True).apply(
            svc, include_groups=False).reset_index()
        self.service_daily = od.groupby("date", observed=True).apply(
            svc, include_groups=False).reset_index()
        self.service_by_month = od.groupby("month", observed=True).apply(
            svc, include_groups=False).reset_index()

    def _build_fleet(self):
        f = self.fleet
        g = f.groupby(["store_id", "store_name", "city"], observed=True)
        self.fleet_by_store = g.apply(lambda x: pd.Series({
            "avg_captains": x.active_captains.mean(),
            "avg_orders": x.orders_placed.mean(),
            "avg_delivery_min": x.avg_delivery_min.mean(),
            "utilisation_pct": x.utilisation_pct.mean(),
            "days_over_100": (x.utilisation_pct > 100).mean(),
            "fleet_cost_aed": x.fleet_cost_aed.sum(),
            "cost_per_order_aed": x.fleet_cost_aed.sum() / max(x.orders_delivered.sum(), 1),
        }), include_groups=False).reset_index()

    # ------------------------------------------------------------------
    # Network headline
    # ------------------------------------------------------------------

    @property
    def network(self) -> dict:
        inv, po, od = self.inv, self.po, self.orders
        sold, lost = inv.sold_units.sum(), inv.lost_units.sum()
        recv = inv.received_units.sum()
        rev = inv.revenue_aed.sum()
        margin = inv.margin_aed.sum()
        waste = inv.waste_cost_aed.sum()
        lost_margin = inv.lost_margin_aed.sum()
        cancels = len(od) - od.delivered.sum()
        holding = (inv.stock_value_aed.mean() * inv.groupby("date").ngroup().max()
                   if False else None)
        avg_stock_value = (inv.groupby("date", observed=True)
                           .stock_value_aed.sum().mean())

        return {
            "period_start": str(self.date_min.date()),
            "period_end": str(self.date_max.date()),
            "days": self.n_days,
            "annualisation_factor": round(self.annualise, 4),

            "revenue_aed": rev,
            "gross_margin_aed": margin,
            "gross_margin_pct": margin / rev if rev else np.nan,
            "orders": len(od),
            "avg_basket_aed": od.basket_value_aed.mean(),

            "fill_rate": sold / (sold + lost) if (sold + lost) else np.nan,
            "units_lost": lost,
            "lost_margin_aed": lost_margin,
            "stockout_day_rate": inv.stockout_flag.mean(),

            "waste_rate": inv.wasted_units.sum() / recv if recv else np.nan,
            "waste_cost_aed": waste,

            "otif": po.otif.mean(),
            "supplier_fill_ratio": po.fill_ratio.mean(),
            "po_value_aed": po.po_value_aed.sum(),

            "delivery_p50": od.actual_minutes.median(),
            "delivery_p90": od.actual_minutes.quantile(0.90),
            "cancel_rate": cancels / len(od) if len(od) else np.nan,
            "cancel_cost_aed": cancels * self.costs["cancelled_order_cost_aed"],
            "fleet_cost_aed": self.fleet.fleet_cost_aed.sum(),
            "fleet_utilisation_pct": self.fleet.utilisation_pct.mean(),

            "avg_stock_value_aed": avg_stock_value,
            "holding_cost_aed": avg_stock_value
                                * self.costs["inventory_holding_annual_pct"]
                                / self.annualise,
            # exposed so the config-driven waterfall can reference them
            "stockout_cost_aed": self.stockout_cost(lost_margin),
            "supplier_short_cost_aed": float(po.short_cost_aed.sum()),
            "fleet_utilisation_frac": self.fleet.utilisation_pct.mean() / 100.0,
            "inventory_turns_annual": (inv.cogs_aed.sum() * self.annualise
                                       / avg_stock_value if avg_stock_value else np.nan),
        }

    # ------------------------------------------------------------------
    # Domain money conversion
    # ------------------------------------------------------------------

    def stockout_cost(self, lost_margin_aed: float) -> float:
        """Lost margin plus the declared behavioural penalty."""
        return float(lost_margin_aed * self.costs["stockout_margin_multiplier"])

    def slot_cost_annual(self, n_slots: float) -> float:
        return float(n_slots * self.costs["slot_cost_aed_month"] * 12)

    # ------------------------------------------------------------------
    # scorecard() and margin_waterfall() are inherited from BaseKPI and driven
    # by the `scorecard` and `waterfall` blocks in business_rules.yaml. They
    # used to be hardcoded lists here, which is what made the "domain-agnostic"
    # claim false — a second dataset could not produce either without editing
    # this file.
