"""
Decision Brief Generator — synthetic dataset generator
======================================================
Scenario : Careem Quik dark-store grocery network, UAE
Period   : 2025-01-01 .. 2026-06-30 (546 days, daily grain)
Output   : 9 related CSVs in data/careem_quik/

This produces ILLUSTRATIVE SYNTHETIC DATA. No Careem data is used.

The dataset deliberately contains six planted signals (see ARCHITECTURE.md §3).
They are produced by the simulation mechanics, not stamped on afterwards — so
the causal chain a reader would trace is actually present in the rows.

  S1  Supplier SUP01 lead-time mean and variance degrade from Feb-2026,
      plus short-shipments. Produces fresh-produce stockouts concentrated
      in the two highest-velocity Dubai stores.
  S2  SUP02 dairy case-packs are large relative to Abu Dhabi store velocity,
      so the order-up-to policy is forced to over-order -> expiry waste.
  S3  SKU velocity is lognormal, giving a genuine long tail that consumes
      slot capacity and waste out of proportion to its revenue.
  S4  Replenishment is received Mon/Wed only, so cover troughs on the
      Fri/Sat UAE weekend demand peak -> service failures cluster there.
  S5  DS07 Al Nahda has healthy inventory but a structurally undersized
      captain fleet -> long delivery times and customer cancellations.
      (Misdiagnosis trap: the symptom looks like a stock problem.)
  S6  Ramadan shifts volume, daypart and category mix in both 2025 and 2026.

Author: built for the Decision Brief Generator project.
"""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# 0. Configuration
# --------------------------------------------------------------------------

SEED = 20260802
rng = np.random.default_rng(SEED)

START = pd.Timestamp("2025-01-01")
END = pd.Timestamp("2026-06-30")
DATES = pd.date_range(START, END, freq="D")
N_DAYS = len(DATES)

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "careem_quik")

# UAE working week is Mon-Fri; weekend is Sat-Sun with Friday a half day.
# Grocery demand therefore peaks Friday evening through Saturday.
DOW_MULT = {0: 0.93, 1: 0.92, 2: 0.96, 3: 1.02, 4: 1.24, 5: 1.28, 6: 1.05}

# Replenishment is *received* on these weekdays only  -> planted signal S4
REPLEN_DOW = {0, 2}  # Monday, Wednesday

# Ramadan and Eid windows (approximate, sufficient for seasonality demo)
RAMADAN = [
    (pd.Timestamp("2025-03-01"), pd.Timestamp("2025-03-29")),
    (pd.Timestamp("2026-02-17"), pd.Timestamp("2026-03-19")),
]
EID = [
    (pd.Timestamp("2025-03-30"), pd.Timestamp("2025-04-01")),
    (pd.Timestamp("2026-03-20"), pd.Timestamp("2026-03-22")),
]

AED_PER_USD = 3.6725


# --------------------------------------------------------------------------
# 1. Dark stores
# --------------------------------------------------------------------------

STORE_SPEC = [
    # id,    name,             city,        area,            sqm, opened,       catchment, rent,  staff, capt_ratio
    ("DS01", "Dubai Marina",   "Dubai",     "Marina",        320, "2023-05-15", 62000, 78000, 14, 0.0678),
    ("DS02", "JLT",            "Dubai",     "Jumeirah Lakes",280, "2023-08-01", 55000, 66000, 12, 0.0672),
    ("DS03", "Business Bay",   "Dubai",     "Business Bay",  350, "2023-03-10", 71000, 88000, 16, 0.0695),
    ("DS04", "Al Barsha",      "Dubai",     "Al Barsha",     300, "2024-02-01", 48000, 58000, 11, 0.0684),
    ("DS05", "Al Reem Island", "Abu Dhabi", "Al Reem",       290, "2023-11-01", 41000, 52000, 11, 0.0690),
    ("DS06", "Khalifa City",   "Abu Dhabi", "Khalifa City",  260, "2024-06-15", 33000, 41000,  9, 0.0702),
    # DS07's captain ratio is deliberately ~35% below peer level -> signal S5
    ("DS07", "Al Nahda",       "Sharjah",   "Al Nahda",      270, "2024-01-20", 58000, 38000, 10, 0.0445),
    ("DS08", "Al Majaz",       "Sharjah",   "Al Majaz",      240, "2024-09-01", 44000, 33000,  9, 0.0686),
]


def build_stores() -> pd.DataFrame:
    df = pd.DataFrame(STORE_SPEC, columns=[
        "store_id", "store_name", "city", "area", "sqm", "opened_date",
        "catchment_pop", "rent_aed_month", "staff_count", "_captain_ratio",
    ])
    df["opened_date"] = pd.to_datetime(df["opened_date"])
    # Order capacity scales with catchment, damped, plus a store-quality factor.
    df["_demand_base"] = (df["catchment_pop"] / 50000.0) ** 0.85
    df["_demand_base"] *= [1.05, 0.98, 1.12, 0.95, 0.92, 0.86, 1.02, 0.88]
    df["slot_capacity"] = (df["sqm"] * 0.62).round().astype(int)
    return df


# --------------------------------------------------------------------------
# 2. Suppliers
# --------------------------------------------------------------------------

SUPPLIER_SPEC = [
    # id,     name,                        focus,              lead, terms, min_order, base_otif
    ("SUP01", "Gulf Fresh Produce",        "Fresh Produce",       2, 14,  3000, 0.97),
    ("SUP02", "Emirates Dairy Co",         "Dairy & Eggs",        2, 21,  2500, 0.98),
    ("SUP03", "Al Ain Poultry & Meats",    "Meat & Poultry",      3, 30,  4000, 0.96),
    ("SUP04", "Modern Bakehouse",          "Bakery",              1,  7,  1200, 0.99),
    ("SUP05", "Gulf Beverage Distribution","Beverages",           4, 45,  6000, 0.97),
    ("SUP06", "Nova Pantry Trading",       "Pantry & Snacks",     6, 60,  8000, 0.95),
    ("SUP07", "Arctic Frozen Logistics",   "Frozen",              5, 45,  5000, 0.94),
    ("SUP08", "HomeCare Distributors",     "Home & Personal Care",7, 60,  7000, 0.96),
]


def build_suppliers() -> pd.DataFrame:
    return pd.DataFrame(SUPPLIER_SPEC, columns=[
        "supplier_id", "supplier_name", "category_focus",
        "promised_lead_time_days", "payment_terms_days",
        "min_order_aed", "_base_otif",
    ])


# --------------------------------------------------------------------------
# 3. SKUs
# --------------------------------------------------------------------------

@dataclass
class CatSpec:
    name: str
    supplier: str
    temp: str
    shelf_lo: int
    shelf_hi: int
    price_lo: float
    price_hi: float
    margin_lo: float
    margin_hi: float
    n_skus: int
    case_lo: int
    case_hi: int
    ramadan_lift: float


CATEGORIES = [
    CatSpec("Fresh Produce",        "SUP01", "chilled",  4,   8,  3.5,  28.0, 0.20, 0.30, 34,  6, 12, 1.20),
    CatSpec("Dairy & Eggs",         "SUP02", "chilled", 10,  24,  5.0,  32.0, 0.18, 0.26, 28, 12, 24, 1.35),
    CatSpec("Meat & Poultry",       "SUP03", "chilled",  5,  12, 12.0,  75.0, 0.22, 0.32, 20,  4,  8, 1.30),
    CatSpec("Bakery",               "SUP04", "ambient",  3,   6,  4.0,  22.0, 0.28, 0.40, 18,  6, 10, 1.15),
    CatSpec("Beverages",            "SUP05", "ambient",180, 400,  2.5,  35.0, 0.20, 0.30, 30, 12, 24, 1.45),
    CatSpec("Snacks & Confectionery","SUP06","ambient",120, 300,  3.0,  30.0, 0.26, 0.38, 26, 12, 24, 1.25),
    CatSpec("Pantry Staples",       "SUP06", "ambient",180, 540,  4.5,  60.0, 0.22, 0.34, 26,  6, 12, 1.40),
    CatSpec("Frozen Foods",         "SUP07", "frozen", 180, 365,  9.0,  55.0, 0.24, 0.34, 20,  6, 12, 1.10),
    CatSpec("Ready Meals",          "SUP04", "chilled",  2,   5, 14.0,  42.0, 0.30, 0.42, 14,  4,  8, 0.80),
    CatSpec("Home & Cleaning",      "SUP08", "ambient",540, 900,  6.0,  48.0, 0.28, 0.40, 20,  6, 12, 1.05),
    CatSpec("Personal Care",        "SUP08", "ambient",540, 900,  8.0,  65.0, 0.32, 0.45, 18,  6, 12, 1.00),
    CatSpec("Baby & Kids",          "SUP08", "ambient",270, 540, 12.0,  90.0, 0.20, 0.30, 12,  6, 12, 1.00),
]

BRANDS = ["Al Rawabi", "Almarai", "Emirates Select", "Nadec", "Freshly", "Oasis",
          "Gulf Gold", "Marina", "Desert Bloom", "Quik Value", "Sunrise", "Zafran"]


def build_skus() -> pd.DataFrame:
    rows, n = [], 0
    for cat in CATEGORIES:
        for i in range(cat.n_skus):
            n += 1
            sku_id = f"SKU{n:04d}"
            price = round(float(rng.uniform(cat.price_lo, cat.price_hi)), 2)
            margin = float(rng.uniform(cat.margin_lo, cat.margin_hi))
            cost = round(price * (1 - margin), 2)
            shelf = int(rng.integers(cat.shelf_lo, cat.shelf_hi + 1))
            case_pack = int(rng.integers(cat.case_lo, cat.case_hi + 1))

            # Velocity: lognormal -> genuine long tail (planted signal S3)
            velocity = float(rng.lognormal(mean=1.15, sigma=1.05))

            rows.append({
                "sku_id": sku_id,
                "sku_name": f"{rng.choice(BRANDS)} {cat.name.split(' &')[0]} Item {i+1:02d}",
                "category": cat.name,
                "storage_temp": cat.temp,
                "supplier_id": cat.supplier,
                "unit_price_aed": price,
                "unit_cost_aed": cost,
                "gross_margin_pct": round(margin * 100, 1),
                "shelf_life_days": shelf,
                "case_pack": case_pack,
                "_velocity": velocity,
                "_ramadan_lift": cat.ramadan_lift,
            })
    df = pd.DataFrame(rows)

    # S2: Emirates Dairy ships in large case packs. Where store velocity is low
    # (Abu Dhabi), even a single case exceeds what the shelf life can absorb, so
    # the reorder policy is structurally forced into waste.
    dairy = df["supplier_id"].eq("SUP02")
    df.loc[dairy, "case_pack"] = rng.integers(10, 18, size=int(dairy.sum()))
    return df


# --------------------------------------------------------------------------
# 4. Assortment (which store carries which SKU)
# --------------------------------------------------------------------------

def build_assortment(stores: pd.DataFrame, skus: pd.DataFrame) -> pd.DataFrame:
    """Bigger stores carry more of the tail; every store carries the head."""
    ranked = skus.sort_values("_velocity", ascending=False).reset_index(drop=True)
    rows = []
    for _, st in stores.iterrows():
        cap = int(st["slot_capacity"])
        keep = ranked.head(min(cap, len(ranked)))["sku_id"].tolist()
        # drop a few mid-tail lines at random so assortments are not identical
        drop = set(rng.choice(keep[60:], size=max(0, int(len(keep) * 0.06)),
                              replace=False)) if len(keep) > 80 else set()
        for s in keep:
            if s not in drop:
                rows.append({"store_id": st["store_id"], "sku_id": s})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# 5. Time-varying demand multipliers
# --------------------------------------------------------------------------

def in_window(ts: pd.Timestamp, windows) -> bool:
    return any(lo <= ts <= hi for lo, hi in windows)


def build_calendar() -> pd.DataFrame:
    cal = pd.DataFrame({"date": DATES})
    cal["dow"] = cal["date"].dt.dayofweek
    cal["dow_mult"] = cal["dow"].map(DOW_MULT)

    t = np.arange(N_DAYS)
    cal["trend"] = 1.0 + 0.00055 * t                      # ~1.7%/month growth
    cal["summer"] = 1.0 + 0.10 * np.sin(
        2 * np.pi * (cal["date"].dt.dayofyear - 100) / 365.25)

    cal["is_ramadan"] = cal["date"].apply(lambda d: in_window(d, RAMADAN))
    cal["is_eid"] = cal["date"].apply(lambda d: in_window(d, EID))
    cal["ramadan_mult"] = np.where(cal["is_ramadan"], 1.12, 1.0)
    cal["ramadan_mult"] *= np.where(cal["is_eid"], 1.34, 1.0)
    cal["is_replen_day"] = cal["dow"].isin(REPLEN_DOW)
    return cal


# --------------------------------------------------------------------------
# 6. Supplier lead-time / fill behaviour  (planted signal S1)
# --------------------------------------------------------------------------

S1_ONSET = pd.Timestamp("2026-02-01")


def supplier_performance(supplier_id: str, order_date: pd.Timestamp,
                         promised_lead: int, base_otif: float):
    """Return (actual_lead_days, fill_ratio).

    A supplier normally hits the promised date and ships complete; when it
    misses, it misses by whole days and shorts the line. Modelling it as
    "usually perfect, occasionally bad" rather than "always slightly off" is
    what makes OTIF a meaningful metric — a continuous jitter around the
    promise would score near-zero OTIF while nothing was actually wrong.
    """
    if supplier_id == "SUP01" and order_date >= S1_ONSET:
        on_time = rng.random() < 0.52
        lead = promised_lead if on_time else promised_lead + int(rng.integers(1, 5))
        in_full = rng.random() < 0.58
        fill = 1.0 if in_full else float(np.clip(rng.normal(0.72, 0.14), 0.35, 0.99))
    else:
        on_time = rng.random() < base_otif
        lead = promised_lead if on_time else promised_lead + int(rng.integers(1, 3))
        in_full = rng.random() < base_otif
        fill = 1.0 if in_full else float(np.clip(rng.normal(0.88, 0.08), 0.55, 0.99))
    return max(1, lead), fill


# --------------------------------------------------------------------------
# 7. Core simulation: inventory, purchase orders, sales, waste
# --------------------------------------------------------------------------

def simulate(stores, skus, suppliers, assortment, cal):
    sku_ix = skus.set_index("sku_id")
    sup_ix = suppliers.set_index("supplier_id")
    store_ix = stores.set_index("store_id")

    dates = cal["date"].to_numpy()
    dow_mult = cal["dow_mult"].to_numpy()
    trend = cal["trend"].to_numpy()
    summer = cal["summer"].to_numpy()
    ram_mult = cal["ramadan_mult"].to_numpy()
    is_ram = cal["is_ramadan"].to_numpy()
    is_replen = cal["is_replen_day"].to_numpy()

    inv_rows, po_rows = [], []
    po_counter = 0

    groups = assortment.groupby("store_id")["sku_id"].apply(list).to_dict()

    for store_id, sku_list in groups.items():
        st = store_ix.loc[store_id]
        store_base = st["_demand_base"]
        opened = st["opened_date"]
        city = st["city"]

        for sku_id in sku_list:
            sk = sku_ix.loc[sku_id]
            sup = sup_ix.loc[sk["supplier_id"]]
            shelf = int(sk["shelf_life_days"])
            case_pack = int(sk["case_pack"])
            unit_cost = float(sk["unit_cost_aed"])
            promised_lead = int(sup["promised_lead_time_days"])
            base_otif = float(sup["_base_otif"])

            # Store-level category skew. Abu Dhabi dairy runs slow, which is
            # what makes the large SUP02 case pack bite (planted signal S2).
            cat_skew = 1.0
            if sk["category"] == "Dairy & Eggs" and city == "Abu Dhabi":
                cat_skew = 0.72
            if sk["category"] == "Fresh Produce" and city == "Dubai":
                cat_skew = 1.18
            if sk["category"] == "Ready Meals" and city == "Dubai":
                cat_skew = 1.22

            # 0.24 calibrates the network to ~120-160 orders/store/day, which is
            # the realistic operating range for a dark store of this footprint.
            base_daily = sk["_velocity"] * store_base * cat_skew * 0.24
            if base_daily < 0.05:
                continue  # not worth stocking anywhere

            # inventory state: FEFO batches of (expiry_index, qty)
            batches: deque = deque()
            inbound: dict[int, int] = {}   # day_index -> qty arriving
            on_order = 0

            for d in range(N_DAYS):
                ts = pd.Timestamp(dates[d])
                if ts < opened:
                    continue

                # ---- receive ------------------------------------------------
                receipts = inbound.pop(d, 0)
                if receipts:
                    on_order = max(0, on_order - receipts)
                    batches.append([d + shelf, receipts])

                opening = sum(b[1] for b in batches)

                # ---- demand -------------------------------------------------
                ram_cat = sk["_ramadan_lift"] if is_ram[d] else 1.0
                mu = (base_daily * dow_mult[d] * trend[d] * summer[d]
                      * ram_mult[d] * ram_cat)
                demand = int(rng.poisson(max(mu, 0.01)))

                # ---- sell (FEFO) --------------------------------------------
                sold, need = 0, demand
                while need > 0 and batches:
                    b = batches[0]
                    take = min(b[1], need)
                    b[1] -= take
                    sold += take
                    need -= take
                    if b[1] == 0:
                        batches.popleft()
                lost = demand - sold

                # ---- expire -------------------------------------------------
                wasted = 0
                while batches and batches[0][0] <= d:
                    wasted += batches[0][1]
                    batches.popleft()

                closing = sum(b[1] for b in batches)

                # ---- replenish (order-up-to, review Mon/Wed only) ------------
                ordered_qty = 0
                if is_replen[d]:
                    # Order-up-to level. Note the target is built from *today's*
                    # demand rate on a Mon/Wed review day — which is exactly the
                    # planning flaw behind signal S4: the Fri-Sat peak is never
                    # in the forecast the order is sized against.
                    cover_days = promised_lead + 4.0
                    safety = 1.45 if sk["storage_temp"] == "ambient" else 1.30
                    # A planner will not deliberately hold much more than the
                    # remaining shelf life; this caps sane ordering.
                    shelf_cap = mu * min(shelf * 0.7, 45)
                    target = min(mu * cover_days * safety, shelf_cap)
                    position = closing + on_order
                    gap = target - position
                    # Case-pack rounding still forces a minimum lot. Where a
                    # single case exceeds what shelf life can absorb, waste is
                    # unavoidable — this is the S2 mechanism.
                    if gap > 0 and position < shelf_cap:
                        cases = max(1, int(np.ceil(gap / case_pack)))
                        ordered_qty = cases * case_pack
                        lead, fill = supplier_performance(
                            sk["supplier_id"], ts, promised_lead, base_otif)
                        received_qty = int(round(ordered_qty * fill))
                        arrive = d + lead
                        if arrive < N_DAYS:
                            inbound[arrive] = inbound.get(arrive, 0) + received_qty
                            on_order += received_qty
                        po_counter += 1
                        po_rows.append((
                            f"PO{po_counter:07d}", sk["supplier_id"], store_id, sku_id,
                            ts, ts + pd.Timedelta(days=promised_lead),
                            ts + pd.Timedelta(days=lead),
                            ordered_qty, received_qty,
                            round(unit_cost, 2), round(ordered_qty * unit_cost, 2),
                        ))

                inv_rows.append((
                    ts, store_id, sku_id, opening, receipts, sold, wasted,
                    closing, lost, int(lost > 0), ordered_qty,
                ))

    inventory = pd.DataFrame(inv_rows, columns=[
        "date", "store_id", "sku_id", "opening_units", "received_units",
        "sold_units", "wasted_units", "closing_units", "lost_demand_units",
        "stockout_flag", "ordered_units",
    ])
    pos = pd.DataFrame(po_rows, columns=[
        "po_id", "supplier_id", "store_id", "sku_id", "order_date",
        "promised_date", "received_date", "qty_ordered", "qty_received",
        "unit_cost_aed", "po_value_aed",
    ])
    return inventory, pos


# --------------------------------------------------------------------------
# 8. Orders and order lines, reconstructed from realised sales
# --------------------------------------------------------------------------

def hour_distribution(is_ramadan: bool) -> np.ndarray:
    """Order arrival by hour of day. Ramadan shifts volume post-Iftar."""
    base = np.array([
        0.006,0.003,0.002,0.002,0.002,0.004,0.010,0.020,0.032,0.040,0.046,0.052,
        0.058,0.055,0.048,0.046,0.052,0.062,0.078,0.090,0.086,0.068,0.042,0.024])
    if is_ramadan:
        base = np.array([
            0.030,0.026,0.014,0.006,0.004,0.004,0.005,0.008,0.012,0.018,0.022,0.026,
            0.030,0.030,0.034,0.044,0.060,0.062,0.052,0.086,0.104,0.088,0.070,0.050])
    return base / base.sum()


def build_orders(inventory: pd.DataFrame, skus: pd.DataFrame,
                 stores: pd.DataFrame, cal: pd.DataFrame):
    """Allocate each store-day's realised unit sales into customer baskets.

    Building orders *from* realised sales (rather than independently) guarantees
    that order_items reconciles exactly to inventory movement — which matters,
    because the analysis engine will cross-check the two.

    Fully vectorised per store-day: string SKU ids are replaced by integer codes
    and baskets are formed with a single np.unique over a packed key.
    """
    sku_codes = pd.Index(skus["sku_id"])
    n_sku = len(sku_codes)
    price_arr = skus["unit_price_aed"].to_numpy(np.float64)
    cost_arr = skus["unit_cost_aed"].to_numpy(np.float64)

    ram_days = set(cal.loc[cal["is_ramadan"], "date"])
    p_normal = hour_distribution(False)
    p_ramadan = hour_distribution(True)

    # DS07's fleet is undersized, so its delivery times are longer and its
    # cancellation rate structurally higher (planted signal S5).
    store_speed = {"DS01": 1.00, "DS02": 1.02, "DS03": 0.97, "DS04": 1.05,
                   "DS05": 1.03, "DS06": 1.08, "DS07": 1.62, "DS08": 1.06}
    cancel_rate = {"DS01": 0.021, "DS02": 0.023, "DS03": 0.019, "DS04": 0.026,
                   "DS05": 0.024, "DS06": 0.028, "DS07": 0.071, "DS08": 0.027}

    inv = inventory[(inventory["sold_units"] > 0) |
                    (inventory["lost_demand_units"] > 0)]
    inv = inv.assign(_sku=sku_codes.get_indexer(inv["sku_id"]))

    # accumulators (numpy chunks, concatenated once at the end)
    o_day, o_sec, o_store, o_items, o_val, o_cogs, o_dur, o_cancel = \
        [], [], [], [], [], [], [], []
    i_order, i_sku, i_qty, i_unf = [], [], [], []
    order_base = 0

    for (date, store_id), g in inv.groupby(["date", "store_id"], sort=False):
        sold = g["sold_units"].to_numpy(np.int64)
        lost = g["lost_demand_units"].to_numpy(np.int64)
        codes = g["_sku"].to_numpy(np.int64)

        total = int(sold.sum())
        if total == 0:
            continue

        pool = np.repeat(codes, sold)
        rng.shuffle(pool)

        n_orders = max(1, min(total, int(round(total / 3.4))))
        if n_orders > 1:
            cuts = np.sort(rng.choice(total - 1, size=n_orders - 1,
                                      replace=False)) + 1
            sizes = np.diff(np.concatenate(([0], cuts, [total])))
        else:
            sizes = np.array([total], dtype=np.int64)

        unit_order = np.repeat(np.arange(n_orders), sizes)

        # collapse duplicate SKUs within a basket
        packed = unit_order * n_sku + pool
        uniq, qty = np.unique(packed, return_counts=True)
        li_order = (uniq // n_sku).astype(np.int32)
        li_sku = (uniq % n_sku).astype(np.int16)

        i_order.append(li_order + order_base)
        i_sku.append(li_sku)
        i_qty.append(qty.astype(np.int16))
        i_unf.append(np.zeros(len(uniq), np.int8))

        # unfulfilled demand lines, attached to random orders that day
        n_lost = int(lost.sum())
        if n_lost:
            lost_pool = np.repeat(codes, lost)
            keep = rng.random(n_lost) < 0.45
            lost_pool = lost_pool[keep]
            if lost_pool.size:
                i_order.append(rng.integers(0, n_orders, lost_pool.size)
                               .astype(np.int32) + order_base)
                i_sku.append(lost_pool.astype(np.int16))
                i_qty.append(np.ones(lost_pool.size, np.int16))
                i_unf.append(np.ones(lost_pool.size, np.int8))

        # order-level aggregates
        val = np.bincount(unit_order, weights=price_arr[pool], minlength=n_orders)
        cog = np.bincount(unit_order, weights=cost_arr[pool], minlength=n_orders)

        p = p_ramadan if date in ram_days else p_normal
        hours = rng.choice(24, size=n_orders, p=p)
        mins = rng.integers(0, 60, size=n_orders)

        peak = np.where(np.isin(hours, (18, 19, 20, 21)), 1.18, 1.0)
        dur = rng.gamma(9.0, 2.05, size=n_orders) * store_speed[store_id] * peak
        crate = cancel_rate[store_id] * np.where(dur > 35, 1.6, 1.0)
        cancelled = rng.random(n_orders) < crate

        o_day.append(np.full(n_orders, np.datetime64(date, "s")))
        o_sec.append((hours * 3600 + mins * 60).astype(np.int64))
        o_store.append(np.full(n_orders, store_id, dtype=object))
        o_items.append(sizes.astype(np.int16))
        o_val.append(val)
        o_cogs.append(cog)
        o_dur.append(dur)
        o_cancel.append(cancelled)

        order_base += n_orders

    n = order_base
    order_ids = np.array([f"ORD{i:07d}" for i in range(1, n + 1)], dtype=object)

    orders = pd.DataFrame({
        "order_id": order_ids,
        "order_datetime": np.concatenate(o_day) +
                          np.concatenate(o_sec).astype("timedelta64[s]"),
        "store_id": np.concatenate(o_store),
        "items_count": np.concatenate(o_items),
        "basket_value_aed": np.concatenate(o_val).round(2),
        "basket_cogs_aed": np.concatenate(o_cogs).round(2),
        "promised_minutes": 20,
        "actual_minutes": np.concatenate(o_dur).round(1),
        "status": np.where(np.concatenate(o_cancel),
                           "cancelled_customer", "delivered"),
    })

    ii_order = np.concatenate(i_order)
    ii_sku = np.concatenate(i_sku)
    ii_qty = np.concatenate(i_qty)
    ii_unf = np.concatenate(i_unf)
    order = np.argsort(ii_order, kind="stable")
    ii_order, ii_sku, ii_qty, ii_unf = (ii_order[order], ii_sku[order],
                                        ii_qty[order], ii_unf[order])

    # unit_cost is master data, not a transaction attribute — it lives in
    # skus.csv and is joined in. Keeping the fact table normalised.
    up = price_arr[ii_sku]
    items = pd.DataFrame({
        "order_id": order_ids[ii_order],
        "sku_id": sku_codes.to_numpy()[ii_sku],
        "qty": ii_qty,
        "unit_price_aed": up,
        "line_value_aed": (up * ii_qty).round(2),
        "unfulfilled": ii_unf,
    })
    return orders, items


# --------------------------------------------------------------------------
# 9. Courier / fleet daily  (planted signal S5 lives here)
# --------------------------------------------------------------------------

def build_courier_daily(orders: pd.DataFrame, stores: pd.DataFrame) -> pd.DataFrame:
    o = orders.copy()
    o["date"] = o["order_datetime"].dt.normalize()
    agg = o.groupby(["date", "store_id"]).agg(
        orders_placed=("order_id", "count"),
        orders_delivered=("status", lambda s: int((s == "delivered").sum())),
        avg_delivery_min=("actual_minutes", "mean"),
    ).reset_index()

    ratio = stores.set_index("store_id")["_captain_ratio"].to_dict()
    agg["active_captains"] = np.maximum(
        3, (agg["orders_placed"] * agg["store_id"].map(ratio)
            * rng.normal(1.0, 0.06, len(agg))).round()).astype(int)

    # A captain runs roughly 3 drops an hour over a 6-hour shift.
    agg["capacity_orders"] = (agg["active_captains"] * 18).astype(int)
    agg["utilisation_pct"] = (agg["orders_placed"] / agg["capacity_orders"] * 100).round(1)
    agg["fleet_cost_aed"] = (agg["active_captains"] * 120
                             + agg["orders_delivered"] * 2.0).round(2)
    agg["avg_delivery_min"] = agg["avg_delivery_min"].round(1)
    return agg[["date", "store_id", "active_captains", "orders_placed",
                "orders_delivered", "avg_delivery_min", "capacity_orders",
                "utilisation_pct", "fleet_cost_aed"]]


# --------------------------------------------------------------------------
# 10. Deliberate data-quality defects (so the QC layer has work to do)
# --------------------------------------------------------------------------

def inject_defects(orders: pd.DataFrame, items: pd.DataFrame,
                   inventory: pd.DataFrame):
    # a) ~0.4% duplicated order rows
    dup = orders.sample(frac=0.004, random_state=7)
    orders = pd.concat([orders, dup], ignore_index=True)

    # b) ~0.6% missing actual_minutes
    idx = orders.sample(frac=0.006, random_state=11).index
    orders.loc[idx, "actual_minutes"] = np.nan

    # c) a handful of impossible delivery times
    idx = orders.sample(n=40, random_state=13).index
    orders.loc[idx, "actual_minutes"] = rng.uniform(180, 400, size=len(idx)).round(1)

    # d) ~0.3% of inventory rows with a negative closing balance
    idx = inventory.sample(frac=0.003, random_state=17).index
    inventory.loc[idx, "closing_units"] = -rng.integers(1, 5, size=len(idx))

    return orders, items, inventory


# --------------------------------------------------------------------------
# 11. Main
# --------------------------------------------------------------------------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Building reference tables ...")
    stores = build_stores()
    suppliers = build_suppliers()
    skus = build_skus()
    assortment = build_assortment(stores, skus)
    cal = build_calendar()
    print(f"  {len(stores)} stores | {len(skus)} SKUs | "
          f"{len(assortment):,} store-SKU pairs | {N_DAYS} days")

    print("Simulating inventory, replenishment and waste ...")
    inventory, pos = simulate(stores, skus, suppliers, assortment, cal)
    print(f"  inventory rows: {len(inventory):,} | purchase order lines: {len(pos):,}")

    print("Reconstructing customer orders from realised sales ...")
    orders, items = build_orders(inventory, skus, stores, cal)
    print(f"  orders: {len(orders):,} | order lines: {len(items):,}")

    print("Building fleet table ...")
    courier = build_courier_daily(orders, stores)

    print("Injecting data-quality defects ...")
    orders, items, inventory = inject_defects(orders, items, inventory)

    # strip internal helper columns before writing
    stores_out = stores.drop(columns=[c for c in stores.columns if c.startswith("_")])
    skus_out = skus.drop(columns=[c for c in skus.columns if c.startswith("_")])
    sup_out = suppliers.drop(columns=[c for c in suppliers.columns if c.startswith("_")])

    print(f"Writing to {OUT_DIR} ...")
    stores_out.to_csv(f"{OUT_DIR}/dark_stores.csv", index=False)
    sup_out.to_csv(f"{OUT_DIR}/suppliers.csv", index=False)
    skus_out.to_csv(f"{OUT_DIR}/skus.csv", index=False)
    assortment.to_csv(f"{OUT_DIR}/assortment.csv", index=False)
    inventory.to_csv(f"{OUT_DIR}/inventory_daily.csv", index=False)
    pos.to_csv(f"{OUT_DIR}/purchase_orders.csv", index=False)
    orders.to_csv(f"{OUT_DIR}/orders.csv", index=False)
    items.to_csv(f"{OUT_DIR}/order_items.csv", index=False)
    courier.to_csv(f"{OUT_DIR}/courier_daily.csv", index=False)

    for f in sorted(os.listdir(OUT_DIR)):
        p = os.path.join(OUT_DIR, f)
        print(f"  {f:26s} {os.path.getsize(p)/1e6:8.1f} MB")
    print("Done.")


if __name__ == "__main__":
    main()
