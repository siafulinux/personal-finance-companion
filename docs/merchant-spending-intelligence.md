# Merchant spending intelligence

Spending patterns, grouped by merchant, with the evidence attached and a hard floor on how
little history may be used. Everything here is deterministic arithmetic (sums, medians,
month counts) — no model, no inference from a single receipt.

Source: `backend/app/services/merchant_intelligence.py`. Endpoints:
`GET /api/v1/insights/merchants`, `POST /api/v1/insights/merchants/dismiss`,
`POST /api/v1/insights/merchants/restore`, plus the personal insight list at
`GET /api/v1/insights/personal`.

## Merchant grouping

Purchases (`tx_type = purchase`, `status = posted`) are grouped by
`normalize_merchant(merchant or description)` from `app/matching/normalize.py`, so
`KROGER #123`, `Kroger Store` and `KROGER` are one merchant. Category names come from the
user's own categories and are never changed by this module.

## The history floor

```
MIN_MONTHS = 3          distinct calendar months inside the window
MIN_TRANSACTIONS = 5    posted purchases at that merchant
WINDOW_DAYS = 90        current window (prior window = the 90 days before it)
```

`has_enough_history` is true only when **both** hold, and `confidence` follows:

| Condition | Confidence |
| --- | --- |
| ≥ 6 months and ≥ 12 purchases | `high` |
| ≥ 3 months and ≥ 5 purchases | `medium` |
| anything less | `low` |

Below the floor the merchant row is still returned with its totals, but the module emits
**no** behavioural finding, and `store_guidance()` reports
`"typical_spend": "not enough history"` instead of a number.

## Per-merchant profile

`GET /api/v1/insights/merchants?days=90` returns, per merchant: `merchant_key`, display name,
dominant `category_id`/`category_name`, `transaction_count`, `total`, `average`, `largest`,
`last_purchase`, `months_observed`, `prior_total`, `change_percent`, `has_enough_history`,
`confidence`, `window_days`. The response also states `minimum_history` and a note explaining
the floor, so a client cannot present a thin profile as a pattern.

## Findings

Each finding carries `key`, `type`, `severity`, `merchant`, `title`, `message`, `confidence`
and a structured `evidence` object with the actual figures.

| Type | Fires when | Severity |
| --- | --- | --- |
| `merchant_spending_increase` | Window total is ≥ 25% above the prior window **and** ≥ $50, with enough history. | medium |
| `repeated_small_purchases` | ≥ 8 purchases, average ≤ $20, total ≥ $60. | low |
| `merchant_budget_pressure` | The merchant's dominant category is over budget this month and this merchant accounts for ≥ 20% of the month's spending in it. | high |
| `unusual_purchase` | A single purchase ≥ 2.5× the merchant's own median, with ≥ 4 purchases at that merchant. | low |

Severity is a display hint; `confidence` is the evidence statement, and the two are
deliberately separate.

## Dismissal

`dismiss(key)` stores an `insight_dismissals` row per user, keyed by a stable string (for
example `merchant-grew:kroger`, `merchant-budget-pressure:kroger:2026-11`). A dismissed
finding does not reappear on the next reload, `restore(key)` brings it back, and the key
never contains another user's data. Nothing in this module edits a transaction or a
user-confirmed category.

## Location-aware use

`store_guidance()` (in `app/services/recommendations.py`) reuses the same profile with a
180-day window to produce the numbers behind a Shopping Check prompt: Safe-to-Spend, the
category remainder, the store's own remaining budget, the typical visit size, what is due
within a week, and a `suggested_limit` = the smallest of those figures. Its `facts` block
reports `"unknown"` / `"not enough history"` where data is missing rather than filling gaps.

## Assistant and recommendations

The recommendation engine turns findings into structured items (`kind: "merchant"`,
`kind: "category"`) with `facts`, `confidence` and a period. The assistant may explain them;
it never invents a merchant total, and it cannot dismiss a finding on the user's behalf.

## Web and Android

- **Web:** Insights page — merchant profiles with history badges, findings with their
  evidence, and dismiss/restore. `web/src/pages/InsightsPage.tsx`.
- **Android:** Shopping Intelligence screen shows the same findings through
  `FinanceRepository.merchantInsights()`; the dashboard's Shopping Check prompt uses
  `store_guidance()` output.

## Related

- [Location-aware Shopping Check](location-aware-shopping-check.md)
- [Safe-to-Spend calculation](safe-to-spend-calculation.md)
