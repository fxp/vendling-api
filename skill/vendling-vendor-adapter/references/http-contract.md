# The HTTP adapter contract (spec appendix A.6)

Base URL: anything you choose, e.g. `https://api.acme.example/vendling`. Every request from
Vendling carries `Authorization: Bearer <token>`, `Accept: application/json` and
`User-Agent: vendling-http-adapter/1`. Timeout is 15 s per call.

## Envelope and errors

- Success: a JSON object with `"ok": true` plus the fields listed per endpoint.
- Failure: `{ "ok": false, "reason": "human-readable cause" }` — on any HTTP status.
  `401` / `403` are recorded as **authentication failures**; anything else as an upstream error.
  An HTTP 200 with `ok: false` is fine and preferred over inventing an empty result.
- Unknown extra fields are ignored. Field names are camelCase exactly as below.
- Money: integer **fen** (¥6.00 = `600`). Time: epoch **milliseconds** or `null`.

## Role `machine`

### `GET {base}/inventory?locationId=<machine id>`

```json
{ "ok": true, "items": [
  { "vendorSku": "8837", "title": "红牛 250ml", "barcode": "6920202888888", "priceFen": 600, "stock": 4,
    "slotId": "L2-3", "imageUrl": "https://…/8837.jpg" }
] }
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `vendorSku` | string or number | yes | your stable product id, same across machines |
| `title` | string | yes | display name |
| `priceFen` | integer | yes | current selling price in this machine |
| `stock` | integer | yes | units on the shelf now |
| `barcode` | string | strongly recommended | EAN-13; the bridge to purchasable goods |
| `slotId` | string | recommended | lane number, or layer / layer+position; without it one product may appear in only one place |
| `imageUrl` | string | no | |

### `GET {base}/ledger?fromMs=&toMs=&page=&size=&settledOnly=&by=`

Account-wide sales, one record per order, newest first or oldest first (either), paginated.

```json
{ "ok": true, "page": 1, "pages": 3, "total": 240, "records": [
  { "orderNo": "2026091013001234", "status": "PAID", "statusLabel": "已支付", "state": "settled",
    "locationId": "12345678", "locationName": "某写字楼 11F", "totalFen": 600,
    "createdAt": 1757480412000, "createdAtRaw": "2026-09-10 13:00:12",
    "takenAt": 1757480412000, "settledAt": 1757480414000, "updatedAt": 1757480414000, "finalized": true,
    "lines": [ { "vendorSku": "8837", "priceFen": 600, "costFen": null, "status": "paid" } ] }
] }
```

| Query | Meaning |
|---|---|
| `fromMs`, `toMs` | window, epoch ms, inclusive |
| `page`, `size` | 1-based page, page size (Vendling uses 100) |
| `settledOnly` | `true` → only settled orders |
| `by` | `taken` (default) or `updated`: which timestamp the window applies to. Return `{ok:false, reason:"unsupported"}` if you cannot filter by update time |

| Field | Type | Required | Notes |
|---|---|---|---|
| `orderNo` | string | yes | unique, stable |
| `status`, `statusLabel` | string | yes / no | your raw status and its label |
| `state` | enum | recommended | `in_progress` \| `pending_review` \| `settled` \| `payment_failed` \| `refunded` \| `cancelled` |
| `locationId` | string | yes | machine id |
| `totalFen` | integer | yes | amount actually charged |
| `createdAt` | ms or null | yes | order creation |
| `takenAt` | ms or null | recommended | when goods left the machine (dispense / door close) |
| `settledAt`, `updatedAt` | ms or null | recommended | payment success / last change |
| `finalized` | boolean | recommended | nothing can change any more |
| `lines[].vendorSku`, `priceFen`, `status` | | yes | `status` ∈ `paid` \| `unpaid` \| `refunded` \| `refund_failed` \| `cancelled` |
| `lines[].costFen` | integer or null | yes (may be null) | only a real cost that differs from the price |

Spiral vending machines: `createdAt = takenAt = settledAt`, `finalized: true`, `state: "settled"`.
Open-door / vision cabinets: the order exists from door close; walk `in_progress → pending_review → settled | payment_failed`, bump `updatedAt` on every change, and support `by=updated`.

### `POST {base}/prices` — capability `pricing`

Request `{ "locationId": "12345678", "lines": [ { "vendorSku": "8837", "priceFen": 650 } ] }` →
`{ "ok": true, "count": 1 }`. This changes what the customer pays; it must be atomic per line and refuse unknown skus.

### `POST {base}/restock` — capability `replenishment.recommend` / `replenishment.order`

Request `{ "locationId": "12345678", "ref": "rs-20260910-1", "binding": false,
"lines": [ { "vendorSku": "8837", "quantity": 12, "reason": "sold out twice this week" } ] }` →
`{ "ok": true, "count": 1, "externalRef": "RS-9" }`.

- `binding: false` — a recommendation for your field team; `reason` present.
- `binding: true` — an order you execute and report on; return your own `externalRef`.
- `ref` is idempotent: the same `ref` must not create a second request.
- Refuse a form you do not offer with `{ "ok": false, "reason": "unsupported: …" }`.

### `GET {base}/restock/{ref}`

`{ "ok": true, "state": "completed", "delivered": [ { "vendorSku": "8837", "quantity": 12 } ], "completedAt": 1757500000000, "rawStatus": "DONE" }`
with `state` ∈ `received` \| `in_transit` \| `completed` \| `cancelled`. `delivered[]` is what actually went in.

## Role `supply`

### `GET {base}/catalog?keyword=`

```json
{ "ok": true, "products": [
  { "vendorSku": "10023", "title": "乌龙茶 500ml", "spec": "500ml×15", "category": "饮料", "imageUrl": "…",
    "packSize": 15, "packPriceFen": 5700, "eachPriceFen": 380, "eachPriceDerived": true, "stock": 40 }
], "sites": [ { "id": "w1", "name": "北仓", "address": "…" } ] }
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `vendorSku`, `title` | | yes | |
| `packSize` | integer ≥ 1 | yes | units per box; `1` = sold by the piece only |
| `packPriceFen` | integer | yes if `packSize > 1` | box price |
| `eachPriceFen` | integer | yes | price per single unit; if you only quote the box, send `round(packPriceFen / packSize)` and `eachPriceDerived: true` |
| `stock` | integer | yes | |
| `sites[]` | | no | pickup points / warehouses for `fulfillment.method = "pickup"` |
| `spec`, `category`, `imageUrl` | | no | put the EAN in `spec` or title if you have one |

`keyword` may be ignored (Vendling filters client-side); return the whole catalog then.

### `POST {base}/orders`

Request `{ "ref": "po_20260910_001", "lines": [ { "vendorSku": "10023", "quantity": 2, "unit": "pack" } ],
"fulfillment": { "method": "shipping", "contactName": "张三", "contactPhone": "138…", "address": "…" } }`
→ `{ "ok": true, "externalRef": "SUP-2026091012345" }`.

- `unit` ∈ `each` \| `pack`. `ref` is idempotent: same `ref` → same order, never a second one.
- `fulfillment.method` ∈ `shipping` (fields above) \| `pickup` (`pickupAt` RFC 3339, `siteId?`) \| `restock` (`locationId`: you load the machine yourself). Refuse methods you do not offer with `ok: false`.
- This spends real money. Reject anything you cannot fulfil instead of accepting and cancelling later.

### `GET {base}/orders/{ref}`

`{ "ok": true, "state": "arrived", "description": "已签收", "rawStatus": 3, "logistics": [ … ] }` with
`state` ∈ `ordered` \| `arrived` \| `cancelled`. `logistics[]` is passed through as-is.

## Registration (operator side)

```json
[
  { "namespace": "acme-machine", "vendor": "acme", "baseUrl": "https://api.acme.example/vendling",
    "token": "…", "capabilities": ["pricing", "replenishment.recommend"] },
  { "namespace": "acme-supply", "baseUrl": "https://api.acme.example/vendling", "token": "…" }
]
```

- `namespace` must be `<vendor>-machine` or `<vendor>-supply`; `vendor` defaults to the prefix.
- `capabilities` lists only the optional extensions you serve (`pricing`, `replenishment.recommend`,
  `replenishment.order`); the role's base capabilities are implied. Leave out what you don't serve —
  callers then get `namespace_unsupported` instead of a fake success.
- The operator stores it as the `VENDLING_HTTP_VENDORS` secret. It takes effect on the next request; no deploy.
