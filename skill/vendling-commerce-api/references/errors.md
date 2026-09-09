# Errors

Business outcomes come back as HTTP 200 with `ucp.status: "error"` and `messages[]`; protocol
errors use HTTP status codes. Always read `messages[]` before the data.

| code | severity | HTTP | when |
|---|---|---|---|
| `missing` | recoverable | 400 | required field absent (`path` points at it) |
| `invalid` | recoverable | 400 | wrong type/range; unregistered namespace; `quantity_unit` not in `sale_units` |
| `not_found` | unrecoverable | 404 | |
| `unauthorized` | unrecoverable | 401 | wrong/missing token, or the upstream rejected its credentials |
| `out_of_stock` / `item_unavailable` | recoverable | 200 | |
| `request_too_large` | recoverable | 400 | > 50 ids |
| `namespace_mismatch` | recoverable | 400 | mixed supply namespaces in one checkout, or a foreign role sent to an endpoint |
| `namespace_unsupported` | unrecoverable | 400 | registered namespace without a live adapter |
| `unresolved_sku` | recoverable | 200 | a run line has no confirmed purchasable alias |
| `hard_no_go` | unrecoverable | 200 | a line matches `rules.hardNoGos`; session stays `incomplete` |
| `approval_rejected` / `expired` | unrecoverable | 200 | session became `canceled` |
| `confirmation_required` | requires_buyer_review | 400 | `confirm` not boolean `true` |
| `approval_required` | requires_buyer_review | 200 | guardrail created a pending decision; `actions["com.xiaopingfeng.vendling.approval"][].id` |
| `kill_switch_engaged` | requires_buyer_review | 409 | |
| `guard_unverifiable` | unrecoverable | 503 | rules unreadable → refuse |
| `supplier_rejected` / `upstream_unreachable` | unrecoverable | 502 | upstream said no; `content` has its message |
| `already_placed` / `already_delivered` / `simulation_disabled` | unrecoverable | 409 | |

Warnings (`type: "warning"`, non-blocking): `price_estimated` (each price derived from the box
price), `location_unverified` (machine id never seen in the ledger — may be a typo),
`history_truncated` (ledger paging hit the cap), `hours_unknown`, `sync_problem`, `same_namespace`.

Not the API: `403` with Cloudflare error 1010 means `*.workers.dev` rejected the default
`Python-urllib` User-Agent. Send a descriptive UA.

## How to react

- `requires_buyer_review` → stop and show the user; don't retry.
- `recoverable` → fix the request once; if it recurs, report.
- `502` → report the upstream message verbatim; never retry a money-moving call without the
  user (the PO id is idempotent upstream, but the user must decide).
- An empty ledger with no error means no sales; an auth failure is a `401`, never an empty list.
