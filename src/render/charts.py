"""
Charts
======
Every chart here answers one question and is titled with the answer, not with
the variable names. A chart captioned "Fill rate by day of week" makes the
reader do the work; "Availability collapses into Monday" has already done it.
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, PercentFormatter

from .theme import PALETTE, mpl_style, fmt_aed

plt.rcParams.update(mpl_style())

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _save(fig, out_dir: str, name: str) -> str:
    path = os.path.join(out_dir, f"{name}.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def _wrap(label: str, width: int = 15) -> str:
    """Wrap an axis label onto as many short lines as it needs."""
    words, lines, cur = label.replace(" — ", " ").split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def _strip(ax, x=True):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if x:
        ax.spines["bottom"].set_color(PALETTE["line"])
    ax.spines["left"].set_visible(False)


# ==========================================================================

def margin_waterfall(k, out_dir: str) -> str:
    df = k.margin_waterfall()
    items = df[df.kind != "net"]
    net = df[df.kind == "net"].iloc[0]

    labels = list(items["item"]) + ["Net contribution"]
    vals = list(items.aed_annualised) + [net.aed_annualised]

    fig, ax = plt.subplots(figsize=(10.5, 5.4))
    running = 0.0
    for i, (lab, v) in enumerate(zip(labels, vals)):
        is_first = i == 0
        is_net = lab == "Net contribution"

        if is_first:
            bottom, height, colour = 0.0, v, PALETTE["green"]
            running = v
        elif is_net:
            bottom, height, colour = 0.0, v, PALETTE["deep"]
        else:
            # v is negative: the bar hangs from the running total down to it
            bottom, height = running + v, -v
            colour = PALETTE["slate"] if lab.startswith("Fleet") else PALETTE["red"]
            running += v

        ax.bar(i, height, bottom=bottom, color=colour, width=0.6, zorder=3)

        # connector to the next bar
        if not is_net and i < len(labels) - 1:
            ax.plot([i + 0.3, i + 0.7], [running, running],
                    color=PALETTE["line"], lw=1, zorder=1)

        top = bottom + height
        ax.annotate(fmt_aed(v), (i, top), ha="center", va="bottom",
                    fontsize=8.5, color=PALETTE["ink"],
                    xytext=(0, 4), textcoords="offset points", zorder=4)

    ax.axhline(0, color=PALETTE["ink"], lw=1)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels([_wrap(l) for l in labels], fontsize=8.5)
    ax.set_ylim(0, max(vals[0], running) * 1.16)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v/1e6:,.1f}m"))
    ax.set_ylabel("AED, annualised")
    ax.set_title("Gross margin, and everything the supply chain gives back")
    _strip(ax)
    return _save(fig, out_dir, "margin_waterfall")


def fill_rate_by_dow(k, out_dir: str) -> str:
    dow = k.by_dow.sort_values("dow")
    target = k.rules["targets"]["fill_rate"]["target"]
    reviews = k.inv.groupby("dow", observed=True).ordered_units.sum()
    review_days = set(reviews[reviews > reviews.max() * 0.20].index)

    fig, ax = plt.subplots(figsize=(9, 4.4))
    colours = [PALETTE["red"] if v < 0.88 else
               (PALETTE["amber"] if v < target else PALETTE["green"])
               for v in dow.fill_rate]
    bars = ax.bar(range(7), dow.fill_rate, color=colours, width=0.66)
    ax.axhline(target, color=PALETTE["deep"], ls="--", lw=1.2)
    ax.annotate(f"target {target:.0%}", (6.45, target), fontsize=8.5,
                color=PALETTE["deep"], va="center")

    for i, (b, v) in enumerate(zip(bars, dow.fill_rate)):
        ax.annotate(f"{v:.1%}", (b.get_x() + b.get_width() / 2, v),
                    ha="center", va="bottom", fontsize=9,
                    xytext=(0, 3), textcoords="offset points")
        if i in review_days:
            ax.annotate("review", (b.get_x() + b.get_width() / 2, 0.755),
                        ha="center", fontsize=8, color=PALETTE["white"],
                        bbox=dict(boxstyle="round,pad=0.28",
                                  fc=PALETTE["slate"], ec="none"))

    ax.set_xticks(range(7))
    ax.set_xticklabels(DAYS)
    ax.set_ylim(0.72, 1.0)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title("Availability drains across the weekend and bottoms out on Monday")
    _strip(ax)
    return _save(fig, out_dir, "fill_rate_by_dow")


def supplier_reliability(k, out_dir: str) -> str:
    s = k.by_supplier.sort_values("otif")
    target = k.rules["targets"]["otif"]["target"]

    fig, ax = plt.subplots(figsize=(9, 4.6))
    colours = [PALETTE["red"] if v < 0.85 else
               (PALETTE["amber"] if v < target else PALETTE["green"])
               for v in s.otif]
    ax.barh(range(len(s)), s.otif, color=colours, height=0.62)
    ax.axvline(target, color=PALETTE["deep"], ls="--", lw=1.2)
    ax.annotate(f"target {target:.0%}", (target, len(s) - 0.35),
                fontsize=8.5, color=PALETTE["deep"], ha="left")

    for i, (v, cv) in enumerate(zip(s.otif, s.lead_time_cv)):
        ax.annotate(f"{v:.0%}   (lead-time CV {cv:.2f})", (v, i),
                    va="center", fontsize=8.5, color=PALETTE["ink"],
                    xytext=(5, 0), textcoords="offset points")

    ax.set_yticks(range(len(s)))
    ax.set_yticklabels(s.supplier_name, fontsize=9)
    ax.set_xlim(0, 1.28)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_title("One supplier sits far outside the pack on both reliability measures")
    _strip(ax)
    ax.grid(axis="y", visible=False)
    return _save(fig, out_dir, "supplier_reliability")


def store_diagnosis(k, out_dir: str) -> str:
    """The chart that separates a fleet problem from a stock problem."""
    svc = k.service_by_store.set_index("store_id")
    inv = k.by_store.set_index("store_id")
    fleet = k.fleet_by_store.set_index("store_id")
    df = svc.join(inv[["fill_rate"]]).join(fleet[["utilisation_pct"]])

    fig, ax = plt.subplots(figsize=(9.4, 5.2))
    sizes = (fleet.utilisation_pct / fleet.utilisation_pct.min()) ** 3 * 60

    df = df.sort_values("fill_rate").reset_index()
    # alternate label placement so neighbouring points do not collide
    for i, r in df.iterrows():
        bad = r.utilisation_pct > 95
        ax.scatter(r.fill_rate, r.delivery_p50, s=sizes.get(r.store_id, 80),
                   color=PALETTE["red"] if bad else PALETTE["green"],
                   alpha=0.85, edgecolors=PALETTE["white"], linewidths=1.5,
                   zorder=3)
        dy = 16 if bad else (-20 if i % 2 == 0 else 12)
        ax.annotate(r.store_name, (r.fill_rate, r.delivery_p50),
                    xytext=(0, dy), textcoords="offset points",
                    ha="center", fontsize=9,
                    color=PALETTE["red"] if bad else PALETTE["ink"],
                    fontweight="bold" if bad else "normal", zorder=4)

    ceiling = k.rules["targets"]["delivery_minutes_p50"]["ceiling"]
    lo = df.fill_rate.min() - 0.012
    hi = df.fill_rate.max() + 0.012
    ax.axhline(ceiling, color=PALETTE["slate"], ls=":", lw=1)
    ax.annotate("delivery ceiling", (lo, ceiling), fontsize=8,
                color=PALETTE["slate"], va="bottom", ha="left")

    # headroom so the outlier's label does not collide with the title
    ax.set_xlim(lo, hi)
    ax.set_ylim(df.delivery_p50.min() - 2.0, df.delivery_p50.max() + 3.4)
    ax.set_xlabel("Fill rate  →  was the stock on the shelf?")
    ax.set_ylabel("Median delivery time (min)")
    ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=1))
    ax.set_title("Availability is near-identical across every store.\n"
                 "Service is not — and the outlier is one of the best stocked",
                 loc="left")
    ax.annotate("bubble size = fleet utilisation", (0.99, 0.02),
                xycoords="axes fraction", ha="right", fontsize=8,
                color=PALETTE["slate"])
    _strip(ax)
    return _save(fig, out_dir, "store_diagnosis")


def pareto(k, out_dir: str) -> str:
    sku = k.by_sku.sort_values("revenue_aed", ascending=False).reset_index(drop=True)
    cum = sku.revenue_aed.cumsum() / sku.revenue_aed.sum()
    cut = int((cum <= 0.95).sum())

    fig, ax = plt.subplots(figsize=(9, 4.4))
    x = np.arange(1, len(sku) + 1)
    ax.fill_between(x, cum, color=PALETTE["green"], alpha=0.18)
    ax.plot(x, cum, color=PALETTE["deep"], lw=2)
    ax.axvline(cut, color=PALETTE["red"], ls="--", lw=1.2)
    ax.axhline(0.95, color=PALETTE["slate"], ls=":", lw=1)

    ax.annotate(f"{len(sku) - cut} SKUs beyond this line\n"
                f"add the last 5% of revenue",
                (cut + 4, 0.62), fontsize=9, color=PALETTE["red"])
    ax.set_xlim(1, len(sku))
    ax.set_ylim(0, 1.02)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_xlabel("SKUs, ranked by revenue")
    ax.set_ylabel("Cumulative share of revenue")
    ax.set_title("The range has a long tail that earns almost nothing")
    _strip(ax)
    return _save(fig, out_dir, "pareto")


def waste_by_market(k, out_dir: str) -> str:
    cc = k.by_city_category.copy()
    top = (cc.groupby("category", observed=True).waste_cost_aed.sum()
           .nlargest(6).index)
    cc = cc[cc.category.isin(top)]
    piv = cc.pivot_table(index="category", columns="city",
                         values="waste_rate", aggfunc="first").loc[top]

    piv = piv.dropna(how="all")
    ceiling = k.rules["targets"]["waste_rate"]["ceiling"]

    # One fixed colour per market so the legend means something. Severity is
    # carried by height against the tolerance line and by a red outline —
    # recolouring bars by value would contradict the legend.
    city_colour = {c: col for c, col in zip(
        piv.columns, [PALETTE["deep"], PALETTE["green"], PALETTE["slate"]])}

    fig, ax = plt.subplots(figsize=(9.6, 4.8))
    n = len(piv.columns)
    width = 0.74 / n
    for i, city in enumerate(piv.columns):
        pos = np.arange(len(piv)) + (i - (n - 1) / 2) * width
        vals = piv[city].fillna(0).values
        edges = [PALETTE["red"] if v > 3 * ceiling else "none" for v in vals]
        ax.bar(pos, vals, width=width, label=city, color=city_colour[city],
               edgecolor=edges, linewidth=1.8, zorder=3)

    ax.axhline(ceiling, color=PALETTE["red"], ls="--", lw=1.2, zorder=2)
    ax.annotate(f"tolerance {ceiling:.0%}", (len(piv) - 0.45, ceiling),
                fontsize=8.5, color=PALETTE["red"], va="bottom", ha="right")
    ax.set_xticks(range(len(piv)))
    ax.set_xticklabels([c.replace(" & ", " &\n") for c in piv.index], fontsize=9)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylabel("Write-off as a share of units received")
    ax.set_title("Write-off concentrates in particular market-category pairs.\n"
                 "Red outline marks more than three times tolerance", loc="left")
    ax.legend(fontsize=9, ncols=3, loc="upper right")
    _strip(ax)
    return _save(fig, out_dir, "waste_by_market")


def demand_shape(k, fs, out_dir: str) -> str:
    d = k.service_daily.set_index("date")["orders"]
    roll = d.rolling(7, center=True).mean()

    sea = fs.by_id("SEA-01")
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(d.index, d.values, color=PALETTE["line"], lw=0.8)
    ax.plot(roll.index, roll.values, color=PALETTE["deep"], lw=2)

    if sea:
        s = pd.Timestamp(sea.detail["peak_start"])
        e = pd.Timestamp(sea.detail["peak_end"])
        ax.axvspan(s, e, color=PALETTE["amber"], alpha=0.22)
        ax.annotate(f"+{sea.detail['lift']:.0%} demand,\n"
                    f"{sea.detail['night_share_in']:.0%} of orders after 20:00",
                    (e, d.max() * 0.97), fontsize=9, color=PALETTE["ink"],
                    xytext=(10, -6), textcoords="offset points", va="top")
        # the same window a year later, to show it recurs
        try:
            s2, e2 = s + pd.Timedelta(days=354), e + pd.Timedelta(days=354)
            if s2 < d.index.max():
                ax.axvspan(s2, e2, color=PALETTE["amber"], alpha=0.22)
        except Exception:
            pass

    ax.set_ylabel("Orders per day")
    ax.set_title("Demand is not flat, and the largest swing is on a known calendar")
    _strip(ax)
    return _save(fig, out_dir, "demand_shape")


def action_value(rs, out_dir: str) -> str:
    items = [r for r in rs.ranked()]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    y = np.arange(len(items))
    colours = [PALETTE["green"] if r.stance == "act" else
               (PALETTE["amber"] if r.stance == "investigate" else PALETTE["red"])
               for r in items]
    ax.barh(y, [r.net_annual_aed for r in items], color=colours, height=0.6)
    ax.axvline(0, color=PALETTE["ink"], lw=1)
    for i, r in enumerate(items):
        v = r.net_annual_aed
        ax.annotate(fmt_aed(v), (v, i), va="center",
                    ha="left" if v >= 0 else "right", fontsize=8.5,
                    xytext=(5 if v >= 0 else -5, 0), textcoords="offset points")
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r.id}  {r.title[:44]}" for r in items], fontsize=8.5)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v/1e3:,.0f}k"))
    ax.set_xlabel("Net annual value, after the cost of acting (AED)")
    ax.set_title("One of these costs more than it saves", loc="left")
    _strip(ax)
    ax.grid(axis="y", visible=False)
    return _save(fig, out_dir, "action_value")


# ==========================================================================

def build_all(k, fs, rs, out_dir: str) -> dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    charts = {
        "margin_waterfall": margin_waterfall(k, out_dir),
        "fill_rate_by_dow": fill_rate_by_dow(k, out_dir),
        "supplier_reliability": supplier_reliability(k, out_dir),
        "store_diagnosis": store_diagnosis(k, out_dir),
        "pareto": pareto(k, out_dir),
        "waste_by_market": waste_by_market(k, out_dir),
        "demand_shape": demand_shape(k, fs, out_dir),
        "action_value": action_value(rs, out_dir),
    }
    return charts
