# sku_id, namespaces, sale units, aliases

## sku_id

`sku_id = "<namespace>:<vendor_sku>"` — one string, used identically by catalog, inventory,
checkout, orders, pricing, replenishment. `namespace` matches `[a-z][a-z0-9-]*`;
`vendor_sku` is opaque (no colon, no whitespace) and is never parsed. Compare as exact
strings. Two ids in different namespaces are never equal, even for the same physical good.

| namespace | issuer | used for | current-route field |
|---|---|---|---|
| `youbao-wholesale` | 友宝批发 `product_id` | supplier catalog, purchase orders | `/api/youbao/catalog` `productId`, `/api/youbao/order` `items[].productId` |
| `youbao-vm` | 友宝货柜 `productId` | machine inventory, sales lines, price changes, restock plan/runs, restock recommendations | `/api/youbao/inventory` `productId`, `/api/youbao/orders` `goods[].goodsId`, `/api/youbao/price` `productId`, `state.slots[].productId` |
| `yuanqi` | 元气 (direct supply) | supplier catalog, purchase orders | reserved — no adapter |

Rules:
1. An adapter only accepts its own namespace (`namespace_mismatch` otherwise).
2. A checkout session holds one purchasing namespace; one PO goes to one vendor.
3. Packaging is not part of the id. Box vs each is `quantity_unit` on the line.

Slot id: `<vmId>-<vendor_sku>` with the `youbao-vm` number (e.g. `12345678-8837`). It is
a stand-in for "this product in this machine", not a physical lane.

## Sale units (`sale_units[]`, extension)

A supplier variant advertises the units it can be bought in:

```json
"price": { "amount": 380, "currency": "CNY" },
"quantity_unit": { "unit": "EA", "display_text": "瓶", "increment": 1 },
"sale_units": [
  { "unit": "EA", "display_text": "瓶", "increment": 1, "price": { "amount": 380, "currency": "CNY" }, "price_derived": true },
  { "unit": "BX", "display_text": "箱", "contains": 15, "increment": 1, "price": { "amount": 5700, "currency": "CNY" } }
]
```

- `unit` uses UN/ECE Rec 20 codes: `EA` each, `BX` box. `contains` = how many `EA` in one.
- `variants[].price` is always the **each** price and `quantity_unit` is always `EA`, so a
  client that ignores `sale_units` still orders single units correctly.
- On a checkout line, `quantity_unit` omitted = each; `{unit:"BX"}` = boxes; `quantity`
  counts that unit; `item.price` echoed on the line is the price of that unit.
- Current route: `unit: 2` = each, `unit: 1` = box, `productNum` = count of that unit.
- 友宝 publishes the box price only. The each price is box ÷ contains (`price_derived`);
  settlement follows the supplier statement. Say "换算价" when you quote it.

## Aliases (`aliases[]`, SKU registry)

The same physical good in other namespaces:

```json
"aliases": [{ "sku_id": "youbao-wholesale:10088", "source": "manual", "confirmed_at": "2026-09-01T10:00:00+08:00" }]
```

- `source`: `barcode` (both sides carry an EAN), `manual` (operator confirmed),
  `suggested` (name similarity, unconfirmed). Only `barcode` and `manual` may be used to
  place an order; `resolve` never returns `suggested`.
- Aliases are symmetric.
- Reality today: machine inventory carries the EAN (`productCode`), the wholesale catalog
  fields do not, so 友宝-to-友宝 matching is manual. **No registry route exists yet**; if you
  need to go from a machine product to a supplier SKU now, ask the user to confirm the
  match and record it in your own notes, and say plainly that it's a manual mapping.

## Money and time

- Standard: integer fen + `"currency": "CNY"`. Current routes mix yuan floats and fen
  integers; the field name says which (`priceFen`, `boxPrice`, `totalFeeCny`, `goodsPriceFen`).
- Standard: RFC 3339 with `+08:00`. 友宝 in and out: `YYYY-MM-DD HH:mm:ss` Beijing local,
  no offset. Never build a 友宝 window with `toISOString()` (8-hour shift).
