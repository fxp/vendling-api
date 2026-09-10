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
| `dev.ucp.shopping.order` | `GET /orders/{id}` · `GET /orders?kind=sale\|purchase&location=&from=&to=&trade_status=settled\|all\|<state>&updated_from=&updated_to=&cursor=&limit=` | sale ids are ledger numbers; purchase ids are PO ids. `from/to` filter on `taken_at`; `updated_from/to` on `updated_at` (poll with these for smart cabinets — [缺] today) |
| `com.xiaopingfeng.vendling.pricing` | `PUT /locations/{id}/prices {prices:[{item:{id}, price:{amount,currency}}], confirm:true}` | machine namespace; price cap → `approval_required` |
| `com.xiaopingfeng.vendling.replenishment` | `GET /replenishment/plan` · `GET/POST /replenishment/runs` · `GET /replenishment/runs/{id}` · `POST …/place` · `POST …/receive {delivered:[{slot_id, quantity}]}` · `GET /replenishment/score?horizon_days=` · `POST /locations/{id}/restock-recommendations {reference, line_items:[{item:{id}, quantity, reason}]}` | `place` routes by `fulfiller`: a supply checkout, the machine platform's own restock order (namespace declares `replenishment.order`), or the simulated supplier — only the last exists today |
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

## Partner view

Which operations reach whose system through the adapter layer (guide §2.2). Upstream partners never call
these routes themselves; they implement an adapter (`machine` or `supply` role) and the routes are translated
into its methods.

| Partner | Implements | Operations that end up in their system |
|---|---|---|
| Vending-machine maker / machine-management platform | `machine` adapter: `inventory`, `ledger`, `updatePrices`, `restockRecommend`; namespace `<vendor>-machine` | `POST /catalog/search|lookup|product` (machine ns), `POST /locations/sync`, `GET /orders?kind=sale`, `PUT /locations/{id}/prices`, `POST /locations/{id}/restock-recommendations`; barcodes in `MachineItem.barcode` feed `/skus/resolve` |
| Goods supplier / wholesale platform | `supply` adapter: `catalog`, `createOrder`, `orderStatus`; namespace `<vendor>-supply` | `POST /catalog/search|lookup|product` (supply ns), `POST /checkout-sessions` → `…/complete` (→ `createOrder`, shipping or pickup), `GET /orders/{id}` purchase (→ `orderStatus`); catalog barcodes + `packSize` drive aliases and EA/BX |
| Operator / agent developer | nothing upstream — calls the routes | the core set above, plus replenishment runs, approvals, events |

## Checkout status machine

`incomplete` → `requires_escalation` (owner approval: over budget, probation) → `ready_for_complete` →
`complete_in_progress` → `completed` (has `order`) | `canceled`. Kill switch is not a state: `complete`
is rejected with `kill_switch_engaged`, the session stays as it was.

## Order shape (purchase and sale)

`{id, label?, kind, checkout_id, permalink_url, currency, line_items[]{id, item{id, title, price, quantity_unit?}, quantity{original,total,fulfilled}, totals[], status}, fulfillment{expectations[], events[]}, adjustments[], totals[]}`
plus extension fields: sale → `location`, `location_name`, `trade_status` (`in_progress | pending_review | settled | payment_failed | refunded | cancelled`; only `settled` is a sale), `finalized`, `taken_at`, `settled_at`, `updated_at`, `trade_status_raw`, `trade_status_label`; purchase → `supplier_status{code, description, mapped}`, `logistics[]`.

Open-door smart cabinets create the order at door close and settle minutes to hours later after vision recognition and possibly manual review; until `finalized: true` the lines and amounts can change. Dedupe on `(id, updated_at)`, never on `id` alone. ([缺] the reference implementation returns the raw status and only `settled | all` today.)

Sale line statuses map from the adapter: `paid` → `fulfilled`; `unpaid` → `processing`; `refunded` → `removed` + refund
adjustment; `refund_failed` → `fulfilled` + failed refund; `cancelled` → `removed` + cancellation.
