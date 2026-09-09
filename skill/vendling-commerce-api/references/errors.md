# Errors

## Current routes

| Shape | Meaning |
|---|---|
| `401 {error}` | Missing/wrong operator token |
| `503 {error: "VENDLING_AUTH_TOKEN is not configured"}` | Deployment has no token; fail-closed |
| `400 {error}` / `400 {status:"ERROR", reason}` | Validation: missing field, `confirm` not boolean `true`, bad quantity |
| `404 {error}` | Unknown machine / run / decision / slot |
| `409 {error}` | State conflict: kill switch engaged, run already ordered/delivered, decision already resolved, simulation disabled, pending approval |
| `502 {status:"ERROR", reason, raw?}` | 友宝 rejected or failed (`code != 1` / `!= 200`); `reason` carries its `msg`. `签名错误` = rotated key, not "no data" |
| `503 {status:"ERROR", reason}` | Guardrail rules could not be read; write refused |
| `403` HTML/JSON from Cloudflare, error 1010 | Not the API: `*.workers.dev` rejects the default `Python-urllib` User-Agent. Send a descriptive UA |

## Standard routes (UCP envelope)

Business outcomes come back as HTTP 200 with `ucp.status: "error"` and `messages[]`;
protocol errors use HTTP status codes. Always read `messages[]` before the data.

| code | severity | HTTP | when |
|---|---|---|---|
| `missing` | recoverable | 400 | required field absent (`path` points at it) |
| `invalid` | recoverable | 400 | wrong type/range (quantity, price, quantity_unit not in sale_units) |
| `not_found` | unrecoverable | 404 | |
| `unauthorized` | unrecoverable | 401 | also wraps 友宝 `code 401` |
| `out_of_stock` / `item_unavailable` | recoverable | 200 | |
| `request_too_large` | recoverable | 400 | > 50 ids |
| `namespace_mismatch` | recoverable | 400 | mixed purchasing namespaces in one checkout, or a foreign namespace sent to an adapter |
| `namespace_unsupported` | unrecoverable | 400 | registered namespace without an adapter (`yuanqi`) |
| `hard_no_go` | unrecoverable | 200 | a line matches `rules.hardNoGos`; session stays `incomplete` forever |
| `approval_rejected` / `expired` | unrecoverable | 200 | session became `canceled` |
| `unresolved_sku` | recoverable | 200 | a run line has no confirmed purchasable alias; run not placed |
| `confirmation_required` | requires_buyer_review | 400 | `confirm` not boolean `true` |
| `approval_required` | requires_buyer_review | 200 | guardrail created a pending decision; `actions["com.xiaopingfeng.vendling.approval"][].id` |
| `kill_switch_engaged` | requires_buyer_review | 409 | |
| `guard_unverifiable` | unrecoverable | 503 | rules unreadable → refuse |
| `supplier_rejected` | unrecoverable | 502 | upstream said no; `content` has its message |
| `upstream_unreachable` | unrecoverable | 502 | |
| `already_placed` / `already_delivered` | unrecoverable | 409 | |
| `simulation_disabled` | unrecoverable | 409 | |

Warnings (`type: "warning"`, non-blocking): `price_estimated` (each price derived from box
price), `location_unverified` (machine id never seen in the ledger — may be a typo),
`history_truncated` (ledger paging hit the 20-page cap), `hours_unknown` (hours filter not
applied), `sync_problem` (sync error text), `unresolved_sku` (no purchasable alias; only a
warning while the supplier is simulated), `same_namespace` (alias within one namespace).

## How to react

- `requires_buyer_review` → stop and show the user; don't retry.
- `recoverable` → fix the request once; if it recurs, report.
- `502` from 友宝 → report the upstream message verbatim; never retry a money-moving call
  without the user (the PO id is idempotent upstream, but the user must decide).
- Silence is not success: an empty ledger with no error means no sales, but check
  `status`/`code` first — auth failures once looked exactly like a quiet day.
