---
name: vendling-commerce-api
description: >
  Integrate with the Vendling Commerce API — the UCP-aligned (Universal Commerce Protocol)
  interface of Vendling, an AI agent that runs a real vending route: supplier SKU catalog,
  machine inventory, wholesale purchase orders, sales ledger, live price changes,
  replenishment plans/runs, approvals, event stream. Use this skill whenever an agent or
  user wants to read or act on a Vendling machine or its supply chain: "查库存", "看流水",
  "补货", "下采购单", "改价", "审批", "订阅事件", "接 Vendling", "UCP 售货机", "vendling API",
  "sku_id", or any mention of vendling.dev / vendling.xiaopingfeng.com — even if they don't
  say "API". Also use it when writing code or another skill that talks to Vendling.
---

# Vendling Commerce API · integration skill

You are integrating with a **real, live vending route**: real money at the supplier, real
prices on real screens. The API has guardrails in code; this skill tells you how to work
with them, not around them.

Docs: https://vendling.dev/ (guide, OpenAPI, this skill, one-line agent setup).
Machine-readable index: https://vendling.dev/api/llms.txt.

## 0. Orientation

| What | Where |
|---|---|
| Base URL (production) | `https://vendling.xiaopingfeng.com/ucp/v1` |
| Discovery | `GET https://vendling.xiaopingfeng.com/.well-known/ucp` (public) |
| Staging (mock data, no supplier credentials — nothing can spend money) | `https://vendling-core-staging.fxp007.workers.dev/ucp/v1` |
| Reference | https://vendling.dev/api/reference |

Every response carries a `ucp` envelope; read `messages[]` before the data
(`references/errors.md`). If `/.well-known/ucp` returns 404 the standard routes aren't
deployed on that host — say so; never fabricate a response.

## 1. Auth

```
Authorization: Bearer $VENDLING_AUTH_TOKEN
User-Agent: my-agent/1.0
```

One token, full access. Ask the user for it; never guess it, never log it, never put it
in a URL. `401` = wrong/missing token; `503` = the deployment has no token configured
(fail-closed). Cloudflare answers the default `Python-urllib` User-Agent on `*.workers.dev`
with HTTP 403 error 1010 — send a descriptive UA; that 403 is not an auth failure.

## 2. Identity and units — the rules that prevent wrong orders

- **`sku_id = <vendor>-<role>:<vendor_sku>`** is the single product identity everywhere.
  `role` is `supply` (what a supplier sells: catalog, purchase orders) or `machine` (what
  is inside a machine: inventory, sales, prices, restock). The live namespaces come from
  `GET /namespaces` — never hardcode a vendor; the docs use the placeholder `acme`.
- A machine sku and a supply sku are **never the same id**, even for the same physical
  product. The bridge is an alias (`GET /skus/{id}`, `POST /skus/resolve`); only
  `barcode`/`manual` aliases may be used to order. If nothing resolves, ask the user to
  confirm the match — don't guess.
- **Ordering by single unit is the default.** A checkout line without `quantity_unit` is
  `EA`; `{"unit":"BX"}` orders boxes (`contains` = box size, published in the variant's
  `sale_units[]`). When the supplier only quotes the box, the each price is derived
  (`price_derived`) — say "换算价" when you quote it.
- **Money is integer fen + `CNY`**; times are RFC 3339 with `+08:00`.

## 3. Safety rules (non-negotiable)

1. **Two actions spend real money or change a live price**: `POST /checkout-sessions/{id}/complete`
   and `PUT /locations/{id}/prices`. Both require the JSON boolean `confirm: true` (the
   string `"true"` is rejected). Only send it when the user has explicitly asked, in this
   conversation, for *that* order or *that* price. Show them the payload first.
2. `approval_required` means an owner must approve (in their chat tool or via
   `POST /approvals/{id}`); do not approve on your own initiative.
3. `kill_switch_engaged` (409) freezes every write. Don't retry in a loop; report it.
4. Read-only calls are always fine, including under the kill switch.

## 4. Recipes

Set `U=https://vendling.xiaopingfeng.com/ucp/v1`, `H='authorization: Bearer '"$VENDLING_AUTH_TOKEN"`,
`J='content-type: application/json'`. Or use `scripts/vendling_client.py` (stdlib only), which wraps all of these.

**Discover** — which vendors/namespaces exist, which is the default
```bash
curl -s https://vendling.xiaopingfeng.com/.well-known/ucp | jq '.ucp.capabilities["com.xiaopingfeng.vendling.sku"][0].config'
curl -s -H "$H" $U/namespaces
```

**Machines** (locations)
```bash
curl -s -X POST -H "$H" -H "$J" $U/locations/search -d '{}'
curl -s -X POST -H "$H" -H "$J" $U/locations/search -d '{"filters":{"items":[{"id":"acme-machine:8837"}]}}'   # who has it in stock
```

**What is inside a machine** (a `machine` namespace + location)
```bash
curl -s -X POST -H "$H" -H "$J" $U/catalog/search -d '{"filters":{"namespace":"acme-machine","location":"12345678"}}'
# variants[0]: id (sku_id), sku (EAN), price{amount fen}, inventory{stock, slot_id, locked}, aliases[]
```

**What a supplier sells** (a `supply` namespace)
```bash
curl -s -X POST -H "$H" -H "$J" $U/catalog/search -d '{"query":"乌龙","filters":{"namespace":"acme-supply"},"pagination":{"limit":20}}'
# variants[0].sale_units: EA (each) and BX (box, contains = box size)
curl -s -X POST -H "$H" -H "$J" $U/catalog/lookup -d '{"ids":["acme-supply:10023","acme-machine:8837"],"filters":{"location":"12345678"}}'
```

**Machine product → purchasable sku**
```bash
curl -s -H "$H" $U/skus/acme-machine:8837                                       # aliases + purchasable_from
curl -s -X POST -H "$H" -H "$J" $U/skus/resolve -d '{"ids":["acme-machine:8837"],"to_namespace":"acme-supply"}'
curl -s -X PUT -H "$H" -H "$J" $U/skus/acme-machine:8837/aliases -d '{"aliases":[{"sku_id":"acme-supply:10088"}]}'   # only after the user confirmed
```

**Sales ledger** (account-wide upstream; `location` filters)
```bash
curl -s -H "$H" "$U/orders?kind=sale&location=12345678&from=2026-09-09T00:00:00%2B08:00&to=2026-09-09T23:59:59%2B08:00"
curl -s -H "$H" $U/orders/po_20260909_001                                       # a purchase order: supplier_status + logistics
```

**Replenishment**
```bash
curl -s -H "$H" $U/replenishment/plan                                           # lead_time.source measured|stated
curl -s -X POST -H "$H" $U/replenishment/runs                                   # build a run (may create an approval)
curl -s -X POST -H "$H" $U/replenishment/runs/run-1757404800000/place
curl -s -X POST -H "$H" -H "$J" $U/replenishment/runs/run-…/receive -d '{"delivered":[{"slot_id":"12345678-8837","quantity":12}]}'
```

**Place a real purchase order** (money!) — build, show the user, complete only after they confirmed
```bash
curl -s -X POST -H "$H" -H "$J" $U/checkout-sessions -d '{
  "id": "po_20260909_001",
  "line_items": [{"item":{"id":"acme-supply:10023"},"quantity":2,"quantity_unit":{"unit":"BX"}},
                 {"item":{"id":"acme-supply:10088"},"quantity":6}],
  "fulfillment": {"methods":[{"type":"shipping","destinations":[{"street_address":"…","first_name":"张三","phone_number":"138…"}]}]}}'
# status: incomplete (fix messages[]) | requires_escalation (owner approval) | ready_for_complete
curl -s -X POST -H "$H" -H "$J" $U/checkout-sessions/po_20260909_001/complete -d '{"confirm":true}'
# completed → order{id,label,permalink_url}; 502 supplier_rejected leaves it ready to retry
```

**Change a live price** (customer-facing!) — same confirmation discipline
```bash
curl -s -X PUT -H "$H" -H "$J" $U/locations/12345678/prices -d '{"prices":[{"item":{"id":"acme-machine:8837"},"price":{"amount":650,"currency":"CNY"}}],"confirm":true}'
# over the price cap → approval_required (nothing changed yet); approved → executed
```

**Approvals and events**
```bash
curl -s -H "$H" "$U/approvals?status=pending"
curl -s -X POST -H "$H" -H "$J" $U/approvals/dec-… -d '{"approved":true}'          # only when the user says so
curl -s -H "$H" "$U/events?limit=50&location=12345678"
curl -s -X POST -H "$H" -H "$J" $U/events -d '{"kind":"my_agent","summary":"…","reasoning":"…","location":"12345678"}'
```

**Register / sync machines**
```bash
curl -s -X PUT -H "$H" -H "$J" $U/locations/12345678 -d '{"name":"某写字楼 11F","profile":{"city":"北京","placement":"indoor","venueType":"office"}}'
curl -s -X POST -H "$H" -H "$J" $U/locations/sync -d '{"sales_window_days":30}'
```

## 5. Reading responses

- `messages[]`: `type:"error"` with `severity:"requires_buyer_review"` → stop and show the
  user; `recoverable` → fix the request once; `unrecoverable` → report. Warnings never block.
- `502 supplier_rejected` carries the upstream message verbatim; never retry a money-moving
  call without the user (the PO id is idempotent upstream, but the user decides).
- `GET /replenishment/plan` says whether lead time is `measured` or `stated` and whether a
  demand rate is `measured`. Repeat that qualifier when you report numbers.
- Cost/margin are never in catalog responses; `cost_is_estimated` on a run means exactly that.

## 6. Where to read more

| Need | File |
|---|---|
| Every endpoint, request/response fields | `references/ucp-endpoints.md` |
| sku_id namespaces, sale units, aliases | `references/ids-and-units.md` |
| Error codes, severities, HTTP status | `references/errors.md` |
| Ready-made client / CLI | `scripts/vendling_client.py` (`python3 vendling_client.py --help`) |

The full spec is https://vendling.dev/api/ (source: https://github.com/fxp/vendling-api).
