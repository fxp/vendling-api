# Standard (UCP-shaped) endpoints and the mapping to current routes

Spec: https://vendling.dev/api/ (guide) · `openapi.yaml` (reference).
Base: `https://vendling.xiaopingfeng.com/ucp/v1`, implemented by `src/ucp/` in
vendling-core (private). Check `GET /.well-known/ucp`: a profile means it is deployed. The "legacy"
column is the original route, still served alongside.

Envelope on every standard response: `{"ucp": {"version": "2026-08-25", "status": "success|error", "capabilities": {...}}, ...}`.
Errors: `messages[]` with `code`, `severity`, `path`, `content`. Amounts: integer fen + `"CNY"`.
Times: RFC 3339 with `+08:00`.

| Capability | Standard | Legacy | Notes |
|---|---|---|---|
| Discovery | `GET /.well-known/ucp` | — | public, no token |
| `dev.ucp.shopping.catalog.search` | `POST /catalog/search {filters:{namespace:"youbao-wholesale", …}, query}` | `GET /api/youbao/catalog?keyword=` | |
| same, machine inventory | `POST /catalog/search {filters:{namespace:"youbao-vm", location}}` | `GET /api/youbao/inventory?vmId=` | `filters.location` required |
| `dev.ucp.shopping.catalog.lookup` | `POST /catalog/lookup {ids}` / `POST /catalog/product {id}` | — | ids dispatched by namespace prefix |
| `com.xiaopingfeng.vendling.sku` | `GET /skus/{sku_id}`, `POST /skus/resolve {ids, to_namespace}`, `PUT /skus/{sku_id}/aliases` | — | aliases stored in the agent; only barcode/manual sources resolve |
| `dev.ucp.common.location.search/lookup` | `POST /locations/search {filters:{items:[{id}]}}`, `POST /locations/lookup {ids}` | `GET A/state`, `GET A/machines/<id>/profile` | `hours` filter not applied (no data) |
| location management (ext.) | `PUT /locations/{id} {name, profile}`, `DELETE /locations/{id}`, `POST /locations/sync` | `POST A/sync/youbao`, `PATCH A/machines/<id>/profile`, `DELETE A/sync/devices/<id>` | |
| `dev.ucp.shopping.checkout` (+fulfillment) | `POST /checkout-sessions` → `GET/PUT /checkout-sessions/{id}` → `POST …/complete {confirm:true}` / `…/cancel` | `POST /api/youbao/order {…, confirm:true}` | standard route adds budget/probation/hard-no-go guards; legacy has none |
| `dev.ucp.shopping.order` purchase | `GET /orders/{po_id}` | — | |
| `dev.ucp.shopping.order` sales (ext. list) | `GET /orders?kind=sale&location=&from=&to=&cursor=` | `GET /api/youbao/orders?vmId=&start=&end=` | standard route walks pages when filtering by location |
| `com.xiaopingfeng.vendling.pricing` | `PUT /locations/{id}/prices {prices:[{item:{id:"youbao-vm:…"}, price:{amount,currency}}], confirm:true}` | `POST /api/youbao/price` | standard route enforces `priceCapPerItem` via approval; legacy does not |
| `com.xiaopingfeng.vendling.replenishment` | `GET /replenishment/plan`, `GET/POST /replenishment/runs`, `POST /replenishment/runs/{id}/place`, `…/receive`, `GET /replenishment/score`, `POST /locations/{id}/restock-recommendations` | `GET A/restock/plan`, `POST A/run/restock`, `POST A/restock/place-order`, `POST A/restock/receive`, `GET A/restock/score`, `POST /api/youbao/restock-recommend` | place still goes to the simulated supplier; unresolved lines are warnings |
| `com.xiaopingfeng.vendling.approval` | `GET /approvals?status=pending`, `POST /approvals/{id} {approved, resolver?}` | `state.decisionLog` filter, `POST A/resolve-decision` | approving a parked price change executes it |
| `com.xiaopingfeng.vendling.events` | `GET/POST /events`, `WS /events/stream` | `GET/POST A/events`, `WS /agents/vendling-agent/route-01` | `/events/stream` only returns `websocket_url` |
| Order webhook (business → platform) | `POST <platform webhook_url>` with full Order | — (poll + event stream instead) | not implemented |

## Checkout status machine (standard)

`incomplete` → `requires_escalation` (needs an owner's approval: over budget, probation,
hard no-go) → `ready_for_complete` → `complete_in_progress` → `completed` (has `order`)
| `canceled`. Kill switch is not a state: `complete` is rejected with
`kill_switch_engaged`, the session stays as it was.

## Order shape (standard, both purchase and sale)

`{id, label?, kind:"purchase"|"sale", checkout_id, permalink_url, currency, line_items[]{id, item{id, title, price, quantity_unit?}, quantity{original,total,fulfilled}, totals[], status}, fulfillment{expectations[], events[]}, adjustments[], totals[]}`
plus extension fields: sale → `location`, `location_name`, `trade_status`; purchase →
`supplier_status{code, description, mapped}`, `logistics[]`.

友宝 `orderStatus` on a sale line: 1 paid → `fulfilled`; 0 → `processing`; 2 refunded →
`removed` + `refund` adjustment; 3 → `fulfilled` + failed refund adjustment; 4 → `removed`
+ `cancellation`.
