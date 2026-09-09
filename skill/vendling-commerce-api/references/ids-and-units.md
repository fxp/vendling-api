# sku_id, namespaces, sale units, aliases

## sku_id

`sku_id = "<vendor>-<role>:<vendor_sku>"` — one string, used identically by catalog, inventory,
checkout, orders, pricing, replenishment. `role` is `supply` or `machine`; `vendor_sku` is opaque
(no colon, no whitespace) and never parsed. Compare as exact strings. Two ids in different
namespaces are never equal, even for the same physical good.

| role | issued by | used for |
|---|---|---|
| `supply` | a supplier's catalog | supplier catalog, purchase orders (checkout), purchase order status |
| `machine` | the platform that runs the machines | machine inventory, sales lines, price changes, restock plan/runs/recommendations |

Which vendors exist is a runtime fact: `GET /namespaces` (or the discovery document). Each entry
has `status: live | planned`; a `planned` namespace answers `namespace_unsupported`. The docs use
the placeholder vendor `acme` (`acme-supply`, `acme-machine`).

Rules:
1. An endpoint only accepts the role it serves (`namespace_mismatch` otherwise).
2. A checkout session holds one supply namespace; one PO goes to one vendor.
3. Packaging is not part of the id. Box vs each is `quantity_unit` on the line.

Slot id: `<location>-<vendor_sku>` (e.g. `12345678-8837`). A stand-in for "this product in this machine".

## Sale units (`sale_units[]`, extension)

```json
"price": { "amount": 380, "currency": "CNY" },
"quantity_unit": { "unit": "EA", "display_text": "个", "increment": 1 },
"sale_units": [
  { "unit": "EA", "display_text": "个", "increment": 1, "price": { "amount": 380, "currency": "CNY" }, "price_derived": true },
  { "unit": "BX", "display_text": "箱", "contains": 15, "increment": 1, "price": { "amount": 5700, "currency": "CNY" } }
]
```

- `unit` uses UN/ECE Rec 20 codes: `EA` each, `BX` box. `contains` = how many `EA` in one box.
- `variants[].price` is always the **each** price and `quantity_unit` is always `EA`, so a client
  that ignores `sale_units` still orders single units correctly.
- On a checkout line, `quantity_unit` omitted = each; `{unit:"BX"}` = boxes; `quantity` counts
  that unit; `item.price` echoed on the line is the price of that unit.
- `price_derived` means the supplier only quotes the box and the each price is box ÷ contains;
  settlement follows the supplier statement. Say "换算价" when you quote it.

## Aliases (`aliases[]`, SKU registry)

The same physical good in other namespaces:

```json
"aliases": [{ "sku_id": "acme-supply:10088", "source": "manual", "confirmed_at": "2026-09-01T10:00:00+08:00" }]
```

- `source`: `barcode` (both sides carry an EAN), `manual` (operator confirmed), `suggested`
  (name similarity, unconfirmed). Only `barcode` and `manual` may be used to place an order;
  `resolve` never returns `suggested`.
- Aliases are symmetric. Record them with `PUT /skus/{id}/aliases` only after the user confirmed the match.

## Money and time

- Integer fen + `"currency": "CNY"` everywhere. Never assume yuan.
- RFC 3339 with `+08:00`. Any vendor-side format is the adapter's problem, not yours.
