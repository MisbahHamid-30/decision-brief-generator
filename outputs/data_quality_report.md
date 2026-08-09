# Data-quality report

**Gate: WARN**  ·  worst severity: `high`  ·  8 issue(s) found

## Table confidence

| Table | Rows | Confidence |
|---|---:|---:|
| assortment | 1,350 | 100% |
| courier_daily | 4,360 | 100% |
| dark_stores | 8 | 100% |
| inventory_daily | 737,100 | 95% |
| order_items | 1,673,293 | 91% |
| orders | 483,722 | 88% |
| purchase_orders | 119,358 | 100% |
| skus | 266 | 100% |
| suppliers | 8 | 100% |

## Issues

| Severity | Check | Table | Rows | % | Detail |
|---|---|---|---:|---:|---|
| high | duplicate_primary_key | orders | 1,935 | 0.40% | key ['order_id'] is not unique |
| high | duplicate_primary_key | order_items | 708 | 0.04% | key ['order_id', 'sku_id', 'unfulfilled'] is not unique |
| medium | duplicate_rows | orders | 1,916 | 0.39% | identical rows appear more than once |
| medium | duplicate_rows | order_items | 708 | 0.04% | identical rows appear more than once |
| medium | negative_value | inventory_daily | 2,211 | 0.30% | closing_units contains negative values (impossible for a measure) |
| medium | impossible_value | orders | 40 | 0.01% | actual_minutes exceeds 120 min — not a credible quick-commerce delivery |
| medium | ledger_imbalance | inventory_daily | 2,211 | 0.30% | opening - sold - wasted != closing |
| low | null_values | orders | 2,914 | 0.60% | actual_minutes is null in some rows |

## Repairs applied

- orders: removed 1,916 exact duplicate rows
- orders: collapsed 19 rows sharing a primary key ['order_id'] (kept first)
- order_items: removed 708 exact duplicate rows
- inventory_daily.closing_units: clamped 2,211 negative values to zero (flagged in closing_units_was_negative)
- orders.actual_minutes: capped 39 physically impossible values at 120 min (percentile winsorising deliberately avoided — it would suppress genuine slow-service signal)

## Checks that ran clean

- **referential_integrity** · `all` — 12 foreign-key relationships validated, no orphans
- **reconciliation** · `order_items ↔ orders` — line values reconcile to basket value across 483,722 orders
- **reconciliation** · `order_items ↔ inventory_daily` — units sold agree between order lines and the stock ledger across 4,360 store-days (0.000% gap)
- **reconciliation** · `courier_daily ↔ orders` — daily order counts agree across 4,360 store-days
