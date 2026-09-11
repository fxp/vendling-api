# Mapping worksheet — from your API to the contract

Fill one table per endpoint you will serve. "Source" is the field or call in the vendor's
existing system. A required row with no source is a blocker: ask the vendor, do not invent.

## Machine platform

### `GET /inventory?locationId=`

| Contract field | Required | Source in vendor system | Conversion | Status |
|---|---|---|---|---|
| `locationId` (query) | yes | cabinet / machine id | must be the same id the operator registers with `PUT /locations/{id}` | |
| `items[].vendorSku` | yes | product id | string; stable across machines | |
| `items[].title` | yes | product name | | |
| `items[].priceFen` | yes | current price | yuan × 100, integer — **missing in most first drafts** | |
| `items[].stock` | yes | quantity on shelf | | |
| `items[].barcode` | strongly recommended | EAN / 69 码 | | |
| `items[].slotId` | recommended | layer / lane / position | layer + position when a layer holds several products | |
| capacity per slot | nice to have | max per layer / lane | not in the contract yet; keep for later | |

### `GET /ledger`

| Contract field | Required | Source | Conversion | Status |
|---|---|---|---|---|
| query `fromMs`/`toMs`/`page`/`size` | yes | your order query | time window on `takenAt`; page size 100 | |
| query `by=updated` | recommended | query by last-update time | needed for orders that settle late | |
| `records[].orderNo` | yes | order number | | |
| `records[].locationId` | yes | cabinet id | | |
| `records[].totalFen` | yes | amount charged | fen, integer | |
| `records[].createdAt` / `takenAt` | yes | creation / door-close (or dispense) time | epoch ms | |
| `records[].settledAt` / `updatedAt` / `finalized` | recommended | payment time / last update / final flag | | |
| `records[].state` | recommended | order status | map to the six states (`references/http-contract.md`) | |
| `records[].lines[].vendorSku` / `priceFen` / `status` | yes | line product / unit price / line status | `paid` only for successfully charged lines; refunds → `refunded` | |
| `records[].lines[].costFen` | yes (nullable) | cost | `null` unless a real cost ≠ price | |
| member / customer identity | **must not be sent** | — | drop it | |

### `POST /prices` (optional, capability `pricing`)

| Contract | Source | Notes | Status |
|---|---|---|---|
| set price per sku per machine | remote price change API | if the platform cannot change prices remotely, do not serve this endpoint | |

### `POST /restock` and `GET /restock/{ref}` (optional)

| Contract | Source | Notes | Status |
|---|---|---|---|
| `binding: false` recommendation | field-team task / suggestion API | `reason` text | |
| `binding: true` order | restock order API | your order id as `externalRef`; status + delivered quantities + completion time on `GET /restock/{ref}` | |
| idempotent `ref` | your dedupe key | same `ref` never creates a second request | |

## Supplier

### `GET /catalog`

| Contract field | Required | Source | Conversion | Status |
|---|---|---|---|---|
| `products[].vendorSku` / `title` | yes | sku / name | | |
| `products[].packSize` | yes | units per box | `1` when sold by the piece | |
| `products[].packPriceFen` / `eachPriceFen` | yes | box / unit price | fen; derive the each price if only the box is quoted and set `eachPriceDerived: true` | |
| `products[].stock` | yes | available quantity | | |
| barcode | recommended | EAN | put in `spec` or title | |
| `sites[]` | no | warehouses / pickup points | | |

### `POST /orders` and `GET /orders/{ref}`

| Contract | Source | Notes | Status |
|---|---|---|---|
| idempotent `ref` | your order number mapping | same `ref` → same order | |
| `unit` each / pack | order line unit | | |
| `fulfillment.method` shipping / pickup / restock | delivery options | refuse what you do not offer | |
| `state` ordered / arrived / cancelled | order status | map your codes; keep the raw one in `rawStatus` | |

## Common

| Item | Status |
|---|---|
| Bearer token per vendor; 401/403 on a bad token | |
| `{ok:false, reason}` on every failure; never an empty list for an error | |
| All money in fen, all times in epoch ms (`scripts/vendling_vendor_check.py` flags seconds and yuan) | |
| Which optional capabilities to declare: `pricing`, `replenishment.recommend`, `replenishment.order` | |
