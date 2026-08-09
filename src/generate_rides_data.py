"""
Second dataset — Careem Rides marketplace (UAE)
===============================================
Deliberately a different business from the dark-store data: a two-sided
marketplace with no inventory, no suppliers, no shelf life and no purchase
orders. Its unit of work is a trip, its constraint is captain supply against
rider demand in a given zone at a given hour, and its failure modes are
unfulfilled requests, cancellations and captain churn.

The point of this dataset is to test a claim: that everything in the pipeline
except the detectors is domain-agnostic. If that claim is true, this data should
flow through ingestion, the quality gate, ranking, recommendation economics and
all three renderers unchanged.

Period : 2025-07-01 .. 2026-06-30 (365 days, hourly grain on supply/demand)
Output : data/careem_rides/

PLANTED SIGNALS — the pipeline must find these unaided.

  R1  Dubai Airport, 06:00-09:00. Requests far exceed available captains and
      surge runs high, but captain supply does not respond to it. A second
      misdiagnosis trap: the intuitive read is "raise surge", and surge is
      already elevated and not working. The constraint is captain positioning,
      not price.

  R2  Captains who complete fewer than 20 trips in their first week churn
      within 30 days at roughly three times the rate of those who clear it.
      An activation problem, not a pay problem.

  R3  In zones where the promised ETA is set aggressively below what the zone
      can actually deliver, rider cancellations spike — while actual ETAs are
      normal. The promise causes the cancellation, not the wait.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

SEED = 20260803
rng = np.random.default_rng(SEED)

START = pd.Timestamp("2025-07-01")
END = pd.Timestamp("2026-06-30")
DATES = pd.date_range(START, END, freq="D")
HOURS = pd.date_range(START, END + pd.Timedelta(hours=23), freq="h")
N_HOURS = len(HOURS)

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "careem_rides")

AED_PER_USD = 3.6725

# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------

CITY_SPEC = [
    ("DXB", "Dubai", "2012-07-01", 3_600_000),
    ("AUH", "Abu Dhabi", "2013-03-01", 1_500_000),
    ("SHJ", "Sharjah", "2014-09-01", 1_800_000),
]

# zone_id, city, name, type, area_km2, demand_weight, eta_base, promise_gap
#   promise_gap: minutes the promised ETA is set BELOW what the zone can
#   realistically deliver. Positive numbers are over-promising -> signal R3.
ZONE_SPEC = [
    ("Z01", "DXB", "Dubai Airport",      "airport",     12.0, 2.30, 7.5,  0.0),
    ("Z02", "DXB", "Downtown",           "business",     9.0, 1.85, 6.2,  0.0),
    ("Z03", "DXB", "Marina",             "residential", 11.0, 1.70, 6.8,  0.0),
    ("Z04", "DXB", "Business Bay",       "business",     8.0, 1.55, 6.0,  4.5),   # R3
    ("Z05", "DXB", "Deira",              "retail",      14.0, 1.35, 8.1,  0.0),
    ("Z06", "DXB", "JLT",                "residential", 7.0,  1.20, 6.6,  0.0),
    ("Z07", "AUH", "Abu Dhabi Airport",  "airport",     15.0, 1.10, 8.8,  0.0),
    ("Z08", "AUH", "Corniche",           "business",    10.0, 1.05, 7.2,  0.0),
    ("Z09", "AUH", "Al Reem",            "residential",  8.0, 0.90, 7.0,  0.0),
    ("Z10", "AUH", "Khalifa City",       "residential", 16.0, 0.70, 9.4,  0.0),
    ("Z11", "AUH", "Yas Island",         "retail",      12.0, 0.75, 8.6,  3.8),   # R3
    ("Z12", "SHJ", "Al Nahda",           "residential",  9.0, 1.15, 7.6,  0.0),
    ("Z13", "SHJ", "Al Majaz",           "retail",       7.0, 0.95, 7.4,  0.0),
    ("Z14", "SHJ", "Industrial Area",    "business",    18.0, 0.65, 9.8,  0.0),
    ("Z15", "SHJ", "University City",    "residential", 11.0, 0.60, 8.2,  0.0),
]

VEHICLE = ["Go", "Go Plus", "Business", "Max"]
VEHICLE_P = [0.52, 0.26, 0.15, 0.07]
FARE_BASE = {"Go": 11.0, "Go Plus": 15.5, "Business": 26.0, "Max": 22.0}
FARE_PER_KM = {"Go": 1.85, "Go Plus": 2.35, "Business": 3.60, "Max": 3.10}

# Hour-of-day demand shape by zone type. Airport peaks early; business zones
# peak at commute hours; residential peaks in the evening.
HOUR_PROFILE = {
    "airport": np.array([
        .022,.018,.014,.012,.014,.028,.062,.078,.074,.052,.042,.038,
        .036,.034,.036,.040,.046,.052,.056,.058,.054,.048,.040,.030]),
    "business": np.array([
        .008,.005,.004,.003,.005,.014,.038,.070,.078,.052,.040,.042,
        .050,.046,.040,.044,.058,.082,.076,.052,.038,.028,.018,.012]),
    "residential": np.array([
        .012,.008,.006,.004,.005,.012,.030,.050,.048,.038,.034,.036,
        .042,.040,.038,.044,.056,.070,.078,.074,.062,.048,.032,.020]),
    "retail": np.array([
        .010,.007,.005,.004,.004,.008,.018,.032,.038,.042,.048,.054,
        .058,.054,.050,.054,.062,.072,.080,.076,.064,.048,.030,.018]),
}

DOW_MULT = np.array([0.94, 0.93, 0.96, 1.02, 1.22, 1.26, 1.06])   # Mon..Sun


def build_cities() -> pd.DataFrame:
    df = pd.DataFrame(CITY_SPEC, columns=["city_id", "city_name",
                                          "launch_date", "population"])
    df["launch_date"] = pd.to_datetime(df["launch_date"])
    return df


def build_zones() -> pd.DataFrame:
    return pd.DataFrame(ZONE_SPEC, columns=[
        "zone_id", "city_id", "zone_name", "zone_type", "area_km2",
        "_demand_weight", "_eta_base", "_promise_gap"])


# --------------------------------------------------------------------------
# Captains
# --------------------------------------------------------------------------

def build_captains(n: int = 2600) -> pd.DataFrame:
    city_ids = rng.choice(["DXB", "AUH", "SHJ"], size=n, p=[0.52, 0.26, 0.22])
    # joiners spread across the period, weighted to the earlier months
    offsets = (rng.beta(1.6, 2.4, size=n) * (len(DATES) - 40)).astype(int)
    joined = START + pd.to_timedelta(offsets, unit="D")

    # R2: first-week activation. Some captains never get going, and that is
    # what predicts churn — not their earnings.
    first_week_trips = rng.negative_binomial(3.0, 0.13, size=n)
    activated = first_week_trips >= 20

    # base 30-day churn hazard, tripled for the non-activated
    p_churn = np.where(activated, 0.085, 0.085 * 3.1)
    churned = rng.random(n) < p_churn
    days_to_churn = np.where(churned,
                             rng.integers(7, 31, size=n), -1)
    churn_date = pd.Series(pd.NaT, index=range(n))
    churn_date[churned] = (joined[churned]
                           + pd.to_timedelta(days_to_churn[churned], unit="D"))

    df = pd.DataFrame({
        "captain_id": [f"CPT{i:05d}" for i in range(1, n + 1)],
        "city_id": city_ids,
        "joined_date": joined,
        "vehicle_class": rng.choice(VEHICLE, size=n, p=VEHICLE_P),
        "first_week_trips": first_week_trips,
        "status": np.where(churned, "churned", "active"),
        "churn_date": pd.to_datetime(churn_date.values),
    })
    df.loc[df.churn_date > END, ["status", "churn_date"]] = ["active", pd.NaT]
    return df


# --------------------------------------------------------------------------
# Hourly supply and demand
# --------------------------------------------------------------------------

R1_ZONE = "Z01"          # Dubai Airport
R1_HOURS = {6, 7, 8}     # the morning window where supply does not respond


def build_supply_demand(zones: pd.DataFrame) -> pd.DataFrame:
    hour_of_day = HOURS.hour.to_numpy()
    dow = HOURS.dayofweek.to_numpy()
    doy = HOURS.dayofyear.to_numpy()
    t = np.arange(N_HOURS)

    trend = 1.0 + 0.00004 * t
    season = 1.0 + 0.08 * np.sin(2 * np.pi * (doy - 60) / 365.25)

    frames = []
    for _, z in zones.iterrows():
        prof = HOUR_PROFILE[z.zone_type][hour_of_day]
        # Calibrated so the network runs ~900 requests/day, giving a dataset
        # of roughly 330k trips. A real network of this footprint would run
        # far more; the shape is what matters here, not the absolute volume.
        base = z._demand_weight * 52.0            # requests per zone per day
        mu = base * prof * DOW_MULT[dow] * trend * season
        requests = rng.poisson(np.maximum(mu, 0.05))

        # Captain supply. Normally it tracks demand with a lag and some noise.
        # In the airport morning window it is structurally capped — captains
        # cannot reposition into the queue fast enough, and no amount of surge
        # changes that. This is signal R1.
        supply_ratio = rng.normal(1.02, 0.10, size=N_HOURS)
        capped = (z.zone_id == R1_ZONE) & np.isin(hour_of_day, list(R1_HOURS))
        supply_ratio = np.where(capped,
                                rng.normal(0.55, 0.05, size=N_HOURS),
                                supply_ratio)
        capacity = np.maximum(1, (requests * supply_ratio)).astype(int)
        active_captains = np.maximum(1, (capacity / 2.4)).astype(int)

        completed = np.minimum(requests, capacity)
        unfulfilled = requests - completed

        # Surge responds to the imbalance — including in the airport window,
        # where it climbs and achieves nothing.
        pressure = requests / np.maximum(capacity, 1)
        surge = np.clip(1.0 + 0.72 * (pressure - 1.0), 1.0, 3.0)
        surge = np.round(surge * rng.normal(1.0, 0.02, size=N_HOURS), 2)

        # Actual ETA rises with pressure.
        eta_actual = z._eta_base * np.clip(pressure, 0.75, 3.0) ** 0.55
        eta_actual = np.round(eta_actual * rng.normal(1.0, 0.08, size=N_HOURS), 1)

        # Promised ETA. Most zones promise honestly; two promise aggressively.
        eta_promised = np.round(
            np.maximum(2.0, z._eta_base - z._promise_gap)
            * rng.normal(1.0, 0.03, size=N_HOURS), 1)

        frames.append(pd.DataFrame({
            "datetime": HOURS,
            "zone_id": z.zone_id,
            "requests": requests,
            "completed": completed,
            "unfulfilled": unfulfilled,
            "active_captains": active_captains,
            "avg_eta_promised_min": eta_promised,
            "avg_eta_actual_min": eta_actual,
            "avg_surge": surge,
        }))

    sd = pd.concat(frames, ignore_index=True)
    return sd


# --------------------------------------------------------------------------
# Trips, exploded from completed demand
# --------------------------------------------------------------------------

def build_trips(sd: pd.DataFrame, zones: pd.DataFrame,
                captains: pd.DataFrame) -> pd.DataFrame:
    z = zones.set_index("zone_id")
    live = sd[sd.completed > 0].reset_index(drop=True)

    n = live.completed.to_numpy()
    total = int(n.sum())
    idx = np.repeat(np.arange(len(live)), n)

    zone = live.zone_id.to_numpy()[idx]
    dt = live.datetime.to_numpy()[idx]
    surge = live.avg_surge.to_numpy()[idx]
    eta_p = live.avg_eta_promised_min.to_numpy()[idx]
    eta_a = live.avg_eta_actual_min.to_numpy()[idx]

    # per-trip jitter around the hourly averages
    eta_promised = np.round(eta_p * rng.normal(1.0, 0.10, total), 1)
    eta_actual = np.round(eta_a * rng.normal(1.0, 0.16, total), 1)

    vclass = rng.choice(VEHICLE, size=total, p=VEHICLE_P)
    distance = np.round(np.clip(rng.gamma(2.6, 3.1, total), 0.8, 48.0), 2)
    duration = np.round(distance * rng.normal(2.6, 0.45, total)
                        + rng.normal(3.5, 1.2, total), 1)
    duration = np.clip(duration, 3.0, 180.0)

    base = np.array([FARE_BASE[v] for v in vclass])
    perkm = np.array([FARE_PER_KM[v] for v in vclass])
    fare = np.round((base + perkm * distance) * surge, 2)

    # R3: the rider cancels when the wait overshoots what was promised. It is
    # the gap that drives the decision, not the absolute wait.
    overshoot = np.maximum(eta_actual - eta_promised, 0)
    p_cancel = np.clip(0.018 + 0.020 * overshoot, 0.0, 0.62)
    cancelled = rng.random(total) < p_cancel
    status = np.where(cancelled, "cancelled_rider", "completed")

    rating = np.where(
        cancelled, np.nan,
        np.round(np.clip(rng.normal(4.72, 0.32, total)
                         - 0.045 * overshoot, 1.0, 5.0), 1))

    city = z.loc[zone, "city_id"].to_numpy()

    # assign a captain from the same city who had joined by then
    cap_by_city = {c: captains[captains.city_id == c].captain_id.to_numpy()
                   for c in captains.city_id.unique()}
    captain = np.empty(total, dtype=object)
    for c, ids in cap_by_city.items():
        m = city == c
        captain[m] = rng.choice(ids, size=int(m.sum()))

    dropoff = rng.choice(zones.zone_id.to_numpy(), size=total)

    return pd.DataFrame({
        "trip_id": [f"TRP{i:07d}" for i in range(1, total + 1)],
        "requested_at": dt,
        "city_id": city,
        "pickup_zone": zone,
        "dropoff_zone": dropoff,
        "captain_id": captain,
        "vehicle_class": vclass,
        "status": status,
        "fare_aed": np.where(cancelled, 0.0, fare),
        "distance_km": np.where(cancelled, 0.0, distance),
        "duration_min": np.where(cancelled, 0.0, duration),
        "eta_promised_min": eta_promised,
        "eta_actual_min": eta_actual,
        "surge_multiplier": surge,
        "rider_rating": rating,
    })


# --------------------------------------------------------------------------
# Captain weekly activity
# --------------------------------------------------------------------------

def build_captain_weekly(trips: pd.DataFrame,
                         captains: pd.DataFrame) -> pd.DataFrame:
    t = trips[trips.status == "completed"].copy()
    t["week_start"] = (pd.to_datetime(t.requested_at)
                       .dt.to_period("W-MON").dt.start_time)

    g = t.groupby(["captain_id", "week_start"], observed=True).agg(
        trips=("trip_id", "count"),
        earnings_aed=("fare_aed", "sum"),
        avg_distance_km=("distance_km", "mean"),
    ).reset_index()

    g["online_hours"] = np.round(
        g.trips * rng.normal(0.62, 0.09, len(g)) + rng.normal(3.0, 1.1, len(g)), 1)
    g["online_hours"] = g.online_hours.clip(lower=0.5)
    g["earnings_per_hour_aed"] = np.round(
        g.earnings_aed / g.online_hours.replace(0, np.nan), 2)
    g["acceptance_rate"] = np.round(
        np.clip(rng.normal(0.83, 0.09, len(g)), 0.25, 1.0), 3)

    meta = captains.set_index("captain_id")
    g["joined_date"] = g.captain_id.map(meta.joined_date)
    g["weeks_tenure"] = ((g.week_start - g.joined_date).dt.days // 7).clip(lower=0)
    g["is_first_week"] = (g.weeks_tenure == 0).astype(int)
    g["churned"] = g.captain_id.map(meta.status).eq("churned").astype(int)
    return g.drop(columns=["joined_date"])


# --------------------------------------------------------------------------
# Deliberate data-quality defects
# --------------------------------------------------------------------------

def inject_defects(trips: pd.DataFrame, sd: pd.DataFrame):
    dup = trips.sample(frac=0.003, random_state=5)
    trips = pd.concat([trips, dup], ignore_index=True)

    idx = trips.sample(frac=0.005, random_state=9).index
    trips.loc[idx, "eta_actual_min"] = np.nan

    idx = trips.sample(n=35, random_state=11).index
    trips.loc[idx, "duration_min"] = rng.uniform(400, 900, size=len(idx)).round(1)

    idx = sd.sample(frac=0.002, random_state=13).index
    sd.loc[idx, "active_captains"] = -rng.integers(1, 4, size=len(idx))
    return trips, sd


# --------------------------------------------------------------------------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Building reference tables ...")
    cities = build_cities()
    zones = build_zones()
    captains = build_captains()
    print(f"  {len(cities)} cities | {len(zones)} zones | {len(captains):,} captains "
          f"| {N_HOURS:,} hours")

    print("Simulating hourly supply and demand ...")
    sd = build_supply_demand(zones)
    print(f"  {len(sd):,} zone-hours | {sd.requests.sum():,} requests | "
          f"{sd.unfulfilled.sum():,} unfulfilled")

    print("Exploding completed demand into trips ...")
    trips = build_trips(sd, zones, captains)
    print(f"  {len(trips):,} trips "
          f"({(trips.status=='cancelled_rider').mean():.1%} cancelled)")

    print("Building captain weekly activity ...")
    cw = build_captain_weekly(trips, captains)
    print(f"  {len(cw):,} captain-weeks")

    print("Injecting data-quality defects ...")
    trips, sd = inject_defects(trips, sd)

    zones_out = zones.drop(columns=[c for c in zones.columns if c.startswith("_")])

    print(f"Writing to {OUT_DIR} ...")
    cities.to_csv(f"{OUT_DIR}/cities.csv", index=False)
    zones_out.to_csv(f"{OUT_DIR}/zones.csv", index=False)
    captains.to_csv(f"{OUT_DIR}/captains.csv", index=False)
    trips.to_csv(f"{OUT_DIR}/trips.csv", index=False)
    sd.to_csv(f"{OUT_DIR}/supply_demand_hourly.csv", index=False)
    cw.to_csv(f"{OUT_DIR}/captain_weekly.csv", index=False)

    for f in sorted(os.listdir(OUT_DIR)):
        p = os.path.join(OUT_DIR, f)
        print(f"  {f:28s} {os.path.getsize(p)/1e6:8.1f} MB")
    print("Done.")


if __name__ == "__main__":
    main()
