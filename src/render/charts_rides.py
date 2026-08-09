"""
Charts — rides marketplace
==========================
Two of these come straight from the supply-chain module unchanged: the value
waterfall and the action-value bar both read from config-driven structures and
never touch a domain metric. The other three are marketplace-specific, which is
the same boundary as the detectors.
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter

from .theme import PALETTE, mpl_style
from .charts import margin_waterfall, action_value, _save, _strip

plt.rcParams.update(mpl_style())


def supply_vs_price(k, fs, out_dir: str) -> str:
    """The chart that separates a positioning problem from a pricing one."""
    sd = k.sd
    f = next((x for x in fs if x.id.startswith("SPL")), None)
    zone = f.entities[0] if f else sd.zone_id.iloc[0]
    zname = k.by_zone.set_index("zone_id").loc[zone, "zone_name"]
    hours = (f.detail.get("hours") if f else [6, 7, 8]) or [6, 7, 8]

    z = sd[sd.zone_id == zone]
    byh = z.groupby("hour").agg(
        requests=("requests", "sum"),
        captains=("active_captains", "sum"),
        unfulfilled=("unfulfilled", "sum"),
        surge=("avg_surge", "mean")).reset_index()
    byh["cpr"] = byh.captains / byh.requests

    fig, ax = plt.subplots(figsize=(9.6, 4.8))
    band = [h in hours for h in byh.hour]
    ax.bar(byh.hour, byh.requests, color=[PALETTE["red"] if b else PALETTE["mist"]
                                          for b in band], width=0.72, zorder=2,
           label="Requests")
    ax.bar(byh.hour, byh.captains, color=PALETTE["deep"], width=0.34, zorder=3,
           label="Captains available")
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Requests / captains over the period")
    _strip(ax)

    ax2 = ax.twinx()
    ax2.plot(byh.hour, byh.surge, color=PALETTE["amber"], lw=2.4, marker="o",
             ms=4, zorder=4, label="Surge")
    ax2.set_ylabel("Average surge (×)", color=PALETTE["amber"])
    ax2.tick_params(axis="y", colors=PALETTE["amber"])
    ax2.grid(False)
    ax2.set_ylim(0.95, max(2.2, byh.surge.max() * 1.15))

    lo, hi = min(hours) - 0.5, max(hours) + 0.5
    ax.axvspan(lo, hi, color=PALETTE["red"], alpha=0.07, zorder=0)
    ax.annotate("surge is already high here\nand supply does not follow",
                xy=((lo + hi) / 2, byh.requests.max() * 0.72),
                xytext=((lo + hi) / 2 + 3.2, byh.requests.max() * 0.82),
                ha="left", fontsize=9.5, color=PALETTE["red"],
                arrowprops=dict(arrowstyle="->", color=PALETTE["red"], lw=1.2))

    ax.set_ylim(0, byh.requests.max() * 1.18)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=9, ncols=3, loc="upper left",
              bbox_to_anchor=(0.0, 1.0))
    ax.set_title(f"{zname}: demand, supply and price by hour", loc="left")
    return _save(fig, out_dir, "supply_vs_price")


def activation_churn(k, out_dir: str) -> str:
    c = k.captains
    coh = (c.groupby("activated")
           .agg(n=("captain_id", "size"), churn=("churned", "mean"))
           .reindex([0, 1]))

    fig, ax = plt.subplots(figsize=(8.4, 4.4))
    labels = ["Did not clear 20 trips\nin week one",
              "Cleared 20 trips\nin week one"]
    colours = [PALETTE["red"], PALETTE["green"]]
    bars = ax.bar(labels, coh.churn, color=colours, width=0.5)
    tgt = k.rules["targets"]["captain_churn_30d"]["target"]
    ax.axhline(tgt, color=PALETTE["deep"], ls="--", lw=1.2)
    ax.annotate(f"target {tgt:.0%}", (1.42, tgt), fontsize=8.5,
                color=PALETTE["deep"], va="center")

    for b, v, n in zip(bars, coh.churn, coh.n):
        ax.annotate(f"{v:.0%}", (b.get_x() + b.get_width() / 2, v),
                    ha="center", va="bottom", fontsize=13, fontweight="bold",
                    xytext=(0, 4), textcoords="offset points")
        ax.annotate(f"{int(n):,} captains",
                    (b.get_x() + b.get_width() / 2, 0.006), ha="center",
                    fontsize=9, color=PALETTE["white"])

    ax.set_ylim(0, max(coh.churn) * 1.32)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylabel("30-day churn rate")
    ax.set_title("The first week decides whether a captain stays", loc="left")
    _strip(ax)
    return _save(fig, out_dir, "activation_churn")


def eta_promise(k, out_dir: str) -> str:
    tz = k.trips_by_zone.copy()
    tz = tz[tz.trips > 500]
    tz["gap"] = tz.eta_actual_mean - tz.eta_promised_mean

    fig, ax = plt.subplots(figsize=(9.2, 5.0))
    bad = tz.gap > k.rules["targets"]["eta_promise_gap_min"]["ceiling"]
    ax.scatter(tz.gap[~bad], tz.cancel_rate[~bad], s=90,
               color=PALETTE["green"], edgecolors=PALETTE["white"], lw=1.4,
               zorder=3, label="Promise is honest")
    ax.scatter(tz.gap[bad], tz.cancel_rate[bad], s=170, color=PALETTE["red"],
               edgecolors=PALETTE["white"], lw=1.6, zorder=4,
               label="Over-promising")
    for _, r in tz[bad].iterrows():
        ax.annotate(r.zone_name, (r.gap, r.cancel_rate), fontsize=9.5,
                    color=PALETTE["red"], fontweight="bold",
                    xytext=(0, 14), textcoords="offset points", ha="center")

    if len(tz) > 2:
        m, b = np.polyfit(tz.gap, tz.cancel_rate, 1)
        xs = np.linspace(tz.gap.min(), tz.gap.max(), 50)
        ax.plot(xs, m * xs + b, color=PALETTE["slate"], ls=":", lw=1.4, zorder=1)

    ax.set_xlabel("Minutes the promise understates the actual wait")
    ax.set_ylabel("Rider cancellation rate")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.legend(fontsize=9, loc="upper left")
    ax.set_title("Cancellation tracks the promise, not the wait.\n"
                 "These zones are not slow — they are optimistic", loc="left")
    _strip(ax)
    return _save(fig, out_dir, "eta_promise")


def fulfilment_by_zone(k, out_dir: str) -> str:
    z = k.by_zone.sort_values("fulfilment_rate")
    tgt = k.rules["targets"]["fulfilment_rate"]["target"]

    fig, ax = plt.subplots(figsize=(9.2, 5.2))
    colours = [PALETTE["red"] if v < 0.85 else
               (PALETTE["amber"] if v < tgt else PALETTE["green"])
               for v in z.fulfilment_rate]
    ax.barh(range(len(z)), z.fulfilment_rate, color=colours, height=0.62)
    ax.axvline(tgt, color=PALETTE["deep"], ls="--", lw=1.2)
    ax.annotate(f"target {tgt:.0%}", (tgt, len(z) - 0.3), fontsize=8.5,
                color=PALETTE["deep"], ha="left")
    for i, v in enumerate(z.fulfilment_rate):
        ax.annotate(f"{v:.1%}", (v, i), va="center", fontsize=8.5,
                    xytext=(5, 0), textcoords="offset points")
    ax.set_yticks(range(len(z)))
    ax.set_yticklabels(z.zone_name, fontsize=9)
    ax.set_xlim(0, 1.12)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title("Share of requests served, by zone", loc="left")
    _strip(ax)
    ax.grid(axis="y", visible=False)
    return _save(fig, out_dir, "fulfilment_by_zone")


def build_all(k, fs, rs, out_dir: str) -> dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    return {
        # generic, reused unchanged from the supply-chain module
        "margin_waterfall": margin_waterfall(k, out_dir),
        "action_value": action_value(rs, out_dir),
        # marketplace-specific
        "supply_vs_price": supply_vs_price(k, fs, out_dir),
        "activation_churn": activation_churn(k, out_dir),
        "eta_promise": eta_promise(k, out_dir),
        "fulfilment_by_zone": fulfilment_by_zone(k, out_dir),
    }
