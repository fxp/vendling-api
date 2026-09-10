# Endpoints

Base: `https://vendling.xiaopingfeng.com/ucp/v1` (production), `https://vendling-core-staging.fxp007.workers.dev/ucp/v1` (staging, mock data).
Spec: https://vendling.dev/api/ · OpenAPI: https://vendling.dev/api/openapi.yaml.

Envelope on every response: `{"ucp": {"version": "2026-08-25", "status": "success|error", "capabilities": {...}}, ...}`.
Errors: `messages[]` with `code`, `severity`, `path`, `content`. Amounts: integer fen + `"CNY"`. Times: RFC 3339 `+08:00`.
Namespaces are `<vendor>-supply` / `<vendor>-machine`; the docs use the placeholder `acme`. Discover the real ones first.

| Capability | Method + path | Notes |
|---|---|---|
| Discovery | `GET /.well-known/ucp` (no token) | `capabilities["com.xiaopingfeng.vendling.sku"][0].config.namespaces` lists vendors |
| Namespaces (ext.) | `GET /namespaces` | `{namespaces:[{namespace, vendor, role, status, capabilities}], defaults:{machine, supply}}` |
| `dev.ucp.shopping.catalog.search` | `POST /catalog/search {query?, filters:{namespace, location?, categories?}, pagination?}` | supply namespace → supplier catalog with `sale_units[]`; machine namespace → that machine's inventory (`location` required) |
| `dev.ucp.shopping.catalog.lookup` | `POST /catalog/lookup {ids, filters:{location?}}` · `POST /catalog/product {id, filters?}` | ≤ 50 ids, may span namespaces |
| SKU registry (ext.) | `GET /skus/{sku_id}?location=` · `POST /skus/resolve {ids, to_namespace}` · `PUT /skus/{sku_id}/aliases {aliases:[{sku_id, source?}]}` | aliases are symmetric; only `barcode`/`manual` resolve |
| `dev.ucp.common.location.search/lookup` | `POST /locations/search {query?, filters:{items?:[{id}], amenities?, hours?}}` · `POST /locations/lookup {ids}` | `hours` filter not applied (no data) |
| Location management (ext.) | `PUT /locations/{id} {name, profile?}` · `DELETE /locations/{id}` · `POST /locations/sync {sales_window_days?}` | profile: city, address, placement, venueType, floor, spot |
| `dev.ucp.shopping.checkout` + fulfillment | `POST /checkout-sessions` → `GET/PUT /checkout-sessions/{id}` → `POST …/complete {confirm:true}` · `POST …/cancel` | supply namespace only, one vendor per session; budget/probation/hard-no-go guards |
| `dev.ucp.shopping.order` | `GET /orders/{id}` · `GET /orders?kind=sale\|purchase&location=&from=&to=&trade_status=settled\|all&cursor=&limit=` | sale ids are ledger numbers; purchase ids are PO ids |
| `com.xiaopingfeng.vendling.pricing` | `PUT /locations/{id}/prices {prices:[{item:{id}, price:{amount,currency}}], confirm:true}` | machine namespace; price cap → `approval_required` |
| `com.xiaopingfeng.vendling.replenishment` | `GET /replenishment/plan` · `GET/POST /replenishment/runs` · `GET /replenishment/runs/{id}` · `POST …/place` · `POST …/receive {delivered:[{slot_id, quantity}]}` · `GET /replenishment/score?horizon_days=` · `POST /locations/{id}/restock-recommendations {reference, line_items:[{item:{id}, quantity, reason}]}` | place goes to a simulated supplier today |
| `com.xiaopingfeng.vendling.approval` | `GET /approvals?status=pending\|approved\|rejected\|all&kind=` · `GET /approvals/{id}` · `POST /approvals/{id} {approved, resolver?}` | approving a parked price change executes it |
| `com.xiaopingfeng.vendling.events` | `GET /events?limit=&location=&kind=` · `POST /events {kind, summary, reasoning, location?}` · WebSocket at `websocket_url` | no dedup on POST |

## Core set (★)

The route runs day to day on these 13 operations; wire them first and treat the rest as convenience:

| ★ | Operation | Why it is essential | How Vendling itself exercises it |
|---|---|---|---|
| ★ | `GET /.well-known/ucp` | entry point: version, capabilities, namespaces | every external agent starts here |
| ★ | `GET /namespaces` | you cannot form a `sku_id` without it | same |
| ★ | `POST /locations/search` | which machines exist | dashboard roster |
| ★ | `POST /catalog/search` | machine ns = what is inside and at what price; supply ns = what can be bought | hourly telemetry sync (inventory); daily wholesale-cost refresh (supply catalog) |
| ★ | `GET /orders?kind=sale` | the ledger: the only demand signal | hourly sync + 5-minute order-event poll |
| ★ | `POST /locations/sync` | pulls inventory + ledger into route state; the plan is built from it | dashboard "sync" and the hourly task |
| ★ | `GET /replenishment/plan` | per-slot demand, days of cover, recommended action | daily 07:00 curate + restock loop |
| ★ | `POST /checkout-sessions` → `POST …/complete` | the only path that spends real money at a supplier | operator/agent initiated; loops never order on their own |
| ★ | `PUT /locations/{id}/prices` | the only path that changes a live price | operator/agent initiated; over the cap → approval |
| ★ | `GET /approvals` · `POST /approvals/{id}` | human in the loop for over-budget / over-cap actions | chat approval cards, dashboard |
| ★ | `GET /events` | audit line: every decision, sale, error | dashboard live feed, weekly letter |

## Checkout status machine

`incomplete` → `requires_escalation` (owner approval: over budget, probation) → `ready_for_complete` →
`complete_in_progress` → `completed` (has `order`) | `canceled`. Kill switch is not a state: `complete`
is rejected with `kill_switch_engaged`, the session stays as it was.

## Order shape (purchase and sale)

`{id, label?, kind, checkout_id, permalink_url, currency, line_items[]{id, item{id, title, price, quantity_unit?}, quantity{original,total,fulfilled}, totals[], status}, fulfillment{expectations[], events[]}, adjustments[], totals[]}`
plus extension fields: sale → `location`, `location_name`, `trade_status`; purchase → `supplier_status{code, description, mapped}`, `logistics[]`.

Sale line statuses map from the adapter: `paid` → `fulfilled`; `unpaid` → `processing`; `refunded` → `removed` + refund
adjustment; `refund_failed` → `fulfilled` + failed refund; `cancelled` → `removed` + cancellation.
