# Data-quality report

**Gate: WARN**  ·  worst severity: `high`  ·  5 issue(s) found

## Table confidence

| Table | Rows | Confidence |
|---|---:|---:|
| captain_weekly | 123,322 | 100% |
| captains | 2,600 | 100% |
| cities | 3 | 100% |
| supply_demand_hourly | 131,400 | 98% |
| trips | 344,476 | 90% |
| zones | 15 | 100% |

## Issues

| Severity | Check | Table | Rows | % | Detail |
|---|---|---|---:|---:|---|
| high | duplicate_primary_key | trips | 1,033 | 0.30% | key ['trip_id'] is not unique |
| medium | duplicate_rows | trips | 1,022 | 0.30% | identical rows appear more than once |
| medium | negative_value | supply_demand_hourly | 263 | 0.20% | active_captains contains negative values (impossible for a measure) |
| low | null_values | trips | 1,728 | 0.50% | eta_actual_min is null in some rows |
| low | null_values | trips | 15,681 | 4.54% | rider_rating is null in some rows |

## Repairs applied

- trips: removed 1,022 exact duplicate rows
- trips: collapsed 11 rows sharing a primary key ['trip_id'] (kept first)
- supply_demand_hourly.active_captains: clamped 263 negative values to zero (flagged in active_captains_was_negative)

## Checks that ran clean

- **referential_integrity** · `all` — 7 foreign-key relationships validated, no orphans
