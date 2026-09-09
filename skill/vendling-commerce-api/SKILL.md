---
name: vendling-commerce-api
description: >
  Integrate with the Vendling Commerce API — the UCP-aligned interface of the vendling-core
  vending-route agent at vendling.xiaopingfeng.com (supplier SKU catalog, machine inventory,
  wholesale purchase orders, sales ledger, live price changes, replenishment plans/runs,
  approvals, event stream; upstream is 友宝 Ubox). Use this skill whenever an agent or user
  wants to read or act on a Vendling machine or its supply chain: "查库存", "看流水", "补货",
  "下采购单", "改价", "审批", "订阅事件", "接 Vendling", "UCP 售货机", "vendling-core API",
  "友宝 SKU", "sku_id", or any mention of vendling.xiaopingfeng.com — even if they don't say
  "API". Also use it when writing code or another skill that talks to Vendling.
---

# Vendling Commerce API · integration skill

You are integrating with a **real, live vending route**: two machines in an office building,
real money at the supplier, real prices on real screens. The API has guardrails in code;
this skill tells you how to work with them, not around them.

Docs (human + machine): https://vendling.dev/ (mirror: https://xiaopingfeng.com/apps/vendling/api/)

- Guide (Chinese, the normative spec): `/apps/vendling/api/` · raw markdown `commerce-api.md`
- API reference (OpenAPI 3.1): `/apps/vendling/api/reference` · raw `openapi.yaml`
- Agent index: `/apps/vendling/api/llms.txt` · full text `llms-full.txt`

## 0. Two route surfaces — read this first

| Surface | Base | Status |
|---|---|---|
| **Standard routes** (UCP-shaped, preferred) | `https://vendling.xiaopingfeng.com/ucp/v1/*` + `GET /.well-known/ucp` | implemented in `src/ucp/`; live once deployed |
| **Legacy routes** (the original surface) | `/api/youbao/*` and `/agents/vendling-agent/route-01/*` | live, stays available |

Decide once per session which surface answers: `curl -fsS $B/.well-known/ucp`. A profile
means the standard routes are live — use them (the recipes below). A 404 means only the
legacy routes are deployed — use `references/current-routes.md` and the `legacy` commands
of `scripts/vendling_client.py`. The two map 1:1 (`references/ucp-endpoints.md`). Never
fabricate a response for a route that doesn't answer.

Why prefer the standard routes: they are the only ones with the price-cap and budget
guardrails wired in, they return a `ucp` envelope with machine-readable `messages[]`, and
every id is a namespaced `sku_id`, so the same string works across catalog, checkout,
orders and replenishment.

Staging (`vendling-core-staging.fxp007.workers.dev`) has **no 友宝 credentials** and runs on mock
data: safe for trying write paths, useless for real numbers.

## 1. Auth

Every route except the customer surface needs the operator token:

```
Authorization: Bearer $VENDLING_AUTH_TOKEN
```

One token, full access (no scopes). Ask the user for it; never guess it, never log it,
never put it in a URL. `401` = wrong/missing token; `503` = the deployment has no token
configured at all (fail-closed by design).

Send a descriptive `User-Agent` (e.g. `my-agent/1.0`). Cloudflare answers the default
`Python-urllib/x.y` UA on `*.workers.dev` with HTTP 403 error 1010 ("browser signature
banned"); curl and the bundled client already pass. That 403 is not an auth failure.

## 2. Identity and units — the rules that prevent wrong orders

- **`sku_id = <namespace>:<vendor_sku>`** is the single product identity across every
  interface. Namespaces: `youbao-vm` (what is *inside a machine*: inventory, sales, price
  changes, restock), `youbao-wholesale` (what the supplier *sells*: catalog, purchase
  orders), `yuanqi` (reserved, no adapter). 友宝 has two because its machine platform and
  wholesale platform issue unrelated numbers — 红牛 is `youbao-vm:8837` in the machine and
  `youbao-wholesale:10088` at the supplier. **Never treat one as the other.**
- Standard routes take and return `sku_id` everywhere. Legacy routes still speak raw
  vendor numbers (`productId`, `product_id`): strip the namespace when calling them, add
  it back when reporting. Never mix the two spaces.
- **Ordering by single unit is the default.** A checkout line without `quantity_unit` is
  `EA` (个); `{"unit":"BX"}` orders boxes (`contains` = box size, published in the variant's
  `sale_units[]`). On the legacy order route this is `unit: 2` (each) vs `unit: 1` (box).
  Box price is what 友宝 publishes; each-price is derived (箱价 ÷ 箱规) — say so when quoting.
- **Money is integer fen + `CNY`** on the standard surface. Legacy routes are mixed:
  inventory `priceFen`, catalog `boxPrice`/`unitPrice` in yuan, orders `totalFeeCny` in
  yuan and `goodsPriceFen` in fen. Read the field name, don't assume.
- **Times from 友宝 are Beijing local with no offset.** The adapter already handles this;
  when you build a window yourself, send `YYYY-MM-DD HH:mm:ss` in Beijing time, never
  `toISOString()`.

## 3. Safety rules (non-negotiable)

1. **Two actions spend real money or change a live price**: completing a checkout
   (`POST /ucp/v1/checkout-sessions/{id}/complete`, legacy `POST /api/youbao/order`) and
   changing prices (`PUT /ucp/v1/locations/{id}/prices`, legacy `POST /api/youbao/price`).
   All require the JSON boolean `confirm: true` (the string `"true"` is rejected). Only
   send `confirm: true` when the user has explicitly asked, in this conversation, for
   *that* order or *that* price. Show them the payload first. The standard routes may
   answer `approval_required` instead of acting: that means an owner must approve in
   飞书 or via `POST /ucp/v1/approvals/{id}`; do not approve on your own initiative.
2. Kill switch (`rules.killSwitchEngaged`) freezes every write: you get `409`. Don't
   retry in a loop; report it. Never flip the switch off on your own initiative.
3. Decisions marked `requiresApproval` wait for a human (`POST .../resolve-decision`).
   Don't approve your own proposals unless the user tells you to.
4. `simulate/purchase` writes fake sales into real demand math; it is off by default.
   Leave it off on the production route.
5. Read-only calls are always fine, including under the kill switch.

## 4. Recipes (standard routes; legacy equivalents in references/current-routes.md)

Set `B=https://vendling.xiaopingfeng.com`, `U="$B/ucp/v1"`,
`H='authorization: Bearer '"$VENDLING_AUTH_TOKEN"`, `J='content-type: application/json'`.
Or use `scripts/vendling_client.py` (stdlib only), which wraps all of these and falls back
to the legacy routes when `/ucp/v1` is not deployed.

**Discover**
```bash
curl -s $B/.well-known/ucp | jq '.ucp.capabilities | keys'
```

**Which machines exist, are they online, what's around them**
```bash
curl -s -X POST -H "$H" -H "$J" $U/locations/search -d '{}'
curl -s -X POST -H "$H" -H "$J" $U/locations/search -d '{"filters":{"items":[{"id":"youbao-vm:8837"}]}}'   # who has 红牛 in stock
```

**What is inside a machine right now** (`youbao-vm`)
```bash
curl -s -X POST -H "$H" -H "$J" $U/catalog/search -d '{"filters":{"namespace":"youbao-vm","location":"12345678"}}'
# products[].variants[0]: id (sku_id), sku (EAN), price{amount fen}, inventory{stock, slot_id, locked}, aliases[]
```

**What the supplier sells** (`youbao-wholesale`)
```bash
curl -s -X POST -H "$H" -H "$J" $U/catalog/search -d '{"query":"乌龙","filters":{"namespace":"youbao-wholesale"},"pagination":{"limit":20}}'
# variants[0].sale_units: EA (each, price_derived) and BX (box, contains=箱规)
curl -s -X POST -H "$H" -H "$J" $U/catalog/lookup -d '{"ids":["youbao-wholesale:10023","youbao-vm:8837"],"filters":{"location":"12345678"}}'
```

**From a machine product to something purchasable**
```bash
curl -s -H "$H" $U/skus/youbao-vm:8837                                  # aliases + purchasable_from
curl -s -X POST -H "$H" -H "$J" $U/skus/resolve -d '{"ids":["youbao-vm:8837"],"to_namespace":"youbao-wholesale"}'
curl -s -X PUT -H "$H" -H "$J" $U/skus/youbao-vm:8837/aliases -d '{"aliases":[{"sku_id":"youbao-wholesale:10088"}]}'  # only after the user confirmed the match
```

**Sales ledger** (account-wide upstream; `location` filters)
```bash
curl -s -H "$H" "$U/orders?kind=sale&location=12345678&from=2026-09-09T00:00:00%2B08:00&to=2026-09-09T23:59:59%2B08:00"
# orders[]: line_items[].item.id = youbao-vm:<goodsId>, status fulfilled|removed, adjustments[] for refunds
curl -s -H "$H" $U/orders/po_20260909_001                                # a purchase order: supplier_status + logistics
```

**Replenishment**
```bash
curl -s -H "$H" $U/replenishment/plan                                    # per-slot demand; lead_time.source measured|stated
curl -s -X POST -H "$H" $U/replenishment/runs                            # build a run (may create an approval)
curl -s -H "$H" "$U/replenishment/runs?status=approved"
curl -s -X POST -H "$H" $U/replenishment/runs/run-1757404800000/place    # simulated supplier today
curl -s -X POST -H "$H" -H "$J" $U/replenishment/runs/run-…/receive -d '{"delivered":[{"slot_id":"12345678-8837","quantity":12}]}'
```

**Place a real wholesale order** (money!) — build the session, show it to the user, complete only after they confirmed
```bash
curl -s -X POST -H "$H" -H "$J" $U/checkout-sessions -d '{
  "id": "po_20260909_001",
  "line_items": [{"item":{"id":"youbao-wholesale:10023"},"quantity":2,"quantity_unit":{"unit":"BX"}},
                 {"item":{"id":"youbao-wholesale:10088"},"quantity":6}],
  "fulfillment": {"methods":[{"type":"shipping","destinations":[{"street_address":"…","first_name":"张三","phone_number":"138…"}]}]}}'
# status: incomplete (fix messages[]) | requires_escalation (owner approval; actions[...approval][0].id) | ready_for_complete
curl -s -X POST -H "$H" -H "$J" $U/checkout-sessions/po_20260909_001/complete -d '{"confirm":true}'
# completed → order{id,label(友宝 order_code),permalink_url}; 502 supplier_rejected leaves it ready to retry
```

**Change a live price** (customer-facing!) — same confirmation discipline
```bash
curl -s -X PUT -H "$H" -H "$J" $U/locations/12345678/prices -d '{"prices":[{"item":{"id":"youbao-vm:8837"},"price":{"amount":650,"currency":"CNY"}}],"confirm":true}'
# over rules.priceCapPerItem → approval_required (nothing changed yet); approved → executed
```

**Approvals**
```bash
curl -s -H "$H" "$U/approvals?status=pending"
curl -s -X POST -H "$H" -H "$J" $U/approvals/dec-… -d '{"approved":true}'   # only when the user says so
```

**Events** (the integration point for other agents)
```bash
curl -s -H "$H" "$U/events?limit=50&location=12345678"
curl -s -X POST -H "$H" -H "$J" $U/events -d '{"kind":"my_agent","summary":"…","reasoning":"…","location":"12345678"}'
# live: WebSocket wss://vendling.xiaopingfeng.com/agents/vendling-agent/route-01 (bearer or cookie)
```

**Register / sync machines**
```bash
curl -s -X PUT -H "$H" -H "$J" $U/locations/12345678 -d '{"name":"搜狐网络大厦 11F","profile":{"city":"北京","placement":"indoor","venueType":"office"}}'
curl -s -X POST -H "$H" -H "$J" $U/locations/sync -d '{"sales_window_days":30}'
```

## 5. Reading responses

- Standard routes: every response has a `ucp` envelope; read `messages[]` before the
  data. `type:"error"` with `severity:"requires_buyer_review"` means stop and show the
  user; `recoverable` means fix the request once. Codes: `references/errors.md`.
- Legacy routes: success is HTTP 2xx with a plain object; failures are `{error}` or
  `{status:"ERROR", reason}` with 4xx/5xx. `502` means 友宝 said no — the `reason` carries
  its message; don't retry blindly.
- `GET .../restock/plan` says whether lead time is `measured` or `stated` and whether a
  demand rate is `measured`. Repeat that qualifier when you report numbers.
- Cost/margin: only `viewCostPrice`-tier data has it, and it's `null` when unknown. Never
  invent a margin.

## 6. Where to read more

| Need | File |
|---|---|
| Every legacy route with request/response fields (fallback) | `references/current-routes.md` |
| Every standard endpoint and the legacy→standard mapping | `references/ucp-endpoints.md` |
| sku_id namespaces, sale units, aliases | `references/ids-and-units.md` |
| Error codes, severities, HTTP status | `references/errors.md` |
| Ready-made client / CLI, standard-first with legacy fallback | `scripts/vendling_client.py` (`python3 vendling_client.py --help`) |

The full spec, including the raw 友宝 upstream contract (signing, endpoints, pitfalls), is
`commerce-api.md` on the docs site (source: https://github.com/fxp/vendling-api). Read its
appendix A before touching the adapter code.
