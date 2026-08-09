# Sample data

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
