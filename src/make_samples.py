"""
Sample extracts for the repository
==================================
The full datasets are ~174 MB, which is too large to sit in a Git repository
sensibly. But a reviewer should be able to see the actual shape of the data
without installing Python or downloading anything.

This writes a small, seeded, random sample of every table to `data/samples/`.
Dimension tables are copied whole — they are tiny and are what make the fact
tables readable.

**These samples are for inspection, not analysis.** A 2,000-row random slice of
a 737,100-row table will not reproduce any finding in the brief; the planted
signals live in patterns across the whole series. Regenerate the full data with
the generator scripts to run the pipeline.

    python3 src/make_samples.py
"""

from __future__ import annotations

import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "samples")
SEED = 7
N = 2000

PROFILES = {
    "careem_quik": {
        # copied whole — small, and they make the fact tables legible
        "whole": ["dark_stores.csv", "suppliers.csv", "skus.csv", "assortment.csv"],
        "sampled": ["inventory_daily.csv", "purchase_orders.csv", "orders.csv",
                    "order_items.csv", "courier_daily.csv"],
    },
    "careem_rides": {
        "whole": ["cities.csv", "zones.csv"],
        "sampled": ["captains.csv", "trips.csv", "supply_demand_hourly.csv",
                    "captain_weekly.csv"],
    },
}


def main():
    for profile, spec in PROFILES.items():
        src = os.path.join(ROOT, "data", profile)
        dst = os.path.join(OUT, profile)
        if not os.path.isdir(src):
            print(f"  ! {profile}: no data folder — run the generator first")
            continue
        os.makedirs(dst, exist_ok=True)

        for f in spec["whole"]:
            p = os.path.join(src, f)
            if not os.path.exists(p):
                continue
            df = pd.read_csv(p)
            df.to_csv(os.path.join(dst, f), index=False)
            print(f"  {profile}/{f:26s} {len(df):>8,} rows (complete)")

        for f in spec["sampled"]:
            p = os.path.join(src, f)
            if not os.path.exists(p):
                continue
            df = pd.read_csv(p)
            s = df.sample(n=min(N, len(df)), random_state=SEED)
            # keep the natural ordering so the file reads sensibly
            s = s.sort_index()
            s.to_csv(os.path.join(dst, f), index=False)
            print(f"  {profile}/{f:26s} {len(s):>8,} of {len(df):,} rows (sample)")

    readme = os.path.join(OUT, "README.md")
    with open(readme, "w") as fh:
        fh.write(SAMPLE_README)
    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _, fs in os.walk(OUT) for f in fs)
    print(f"\n  total {total/1e6:.1f} MB written to data/samples/")


SAMPLE_README = """# Sample data

Small extracts of both datasets, committed so the structure can be inspected in
the browser without downloading anything or running any code.

| Profile | Contents |
|---|---|
| `careem_quik/` | Dark-store grocery supply chain. Dimension tables complete; fact tables are a seeded 2,000-row random sample of each. |
| `careem_rides/` | Ride-hailing marketplace. Same treatment. |

## These are for inspection, not analysis

A 2,000-row random slice of a 737,100-row table will not reproduce any finding
in the brief. The planted signals are patterns across whole series — a supplier
degrading from a particular month, a churn difference between cohorts, a
correlation across zones. Sampling destroys all of that by design.

To run the pipeline you need the full data, which is reproducible exactly from
seeded scripts:

```bash
python src/generate_dummy_data.py      # supply chain → data/careem_quik/
python src/generate_rides_data.py      # marketplace  → data/careem_rides/
```

Column-by-column documentation, including the ground truth the analysis is
measured against, is in [`../DATA_DICTIONARY.md`](../DATA_DICTIONARY.md) and
[`../DATA_DICTIONARY_RIDES.md`](../DATA_DICTIONARY_RIDES.md).

Regenerate these samples with `python src/make_samples.py`.
"""


if __name__ == "__main__":
    main()
