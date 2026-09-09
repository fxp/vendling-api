# Legacy routes — the original surface (fallback when /ucp/v1 is not deployed)

Base `https://vendling.xiaopingfeng.com`. `A` = `/agents/vendling-agent/route-01`.
All need `Authorization: Bearer <VENDLING_AUTH_TOKEN>` unless marked public.
Bodies are JSON. Success = 2xx. Failure = `{error}` (agent routes) or
`{status:"ERROR", reason, raw?}` (youbao routes). Source: `src/index.ts`,
`src/adapters/youbao/routes.ts`, `src/agent.ts`.

## 友宝 adapters (`/api/youbao/*`)

| Route | What | Request | Response |
|---|---|---|---|
| `GET /api/youbao/ping` | Are both 友宝 credential pairs working | — | `{ok, wholesale:{status}, device:{status}}`; 502 if either fails |
| `GET /api/youbao/selftest` | Crypto vectors in the runtime | — | `{ok, checks[]}` |
| `GET /api/youbao/inventory?vmId=` | Live products in one machine (`youbao-vm`) | query `vmId` (8 digits) | `{status:"OK", vmId, count, items[]}`; item = `{productId, productName, productCode(EAN-13 69码), priceCny, priceFen, stock, imageUrl}` |
| `GET /api/youbao/catalog?keyword=&limit=` | Supplier SKU list (`youbao-wholesale`); keyword is client-side substring | `limit` default 20 | `{status, count, factoryId, factoryAddress, products[]}`; product = `{productId, productName, unitPrice(yuan, derived), boxPrice(yuan), boxSize, spec, stock, imageUrl, category}` |
| `GET /api/youbao/orders?vmId=&start=&end=&tradeStatus=` | Sales ledger. `start`/`end` = `YYYY-MM-DD HH:mm:ss` **Beijing time**. Page 1 (100) only | `vmId` optional filter | `{status, count, total, pages, records[]}`; record = `{outOrderNo, tradeStatus, tradeStatusLabel, innerCode, nodeName, totalFeeCny, createTime, goods[]}`; goods = `{goodsId, goodsPriceFen, goodsPriceCny, costFen, costCny, orderStatus}` (0 unpaid, 1 paid, 2 refunded, 3 refund failed, 4 cancelled). `costFen` equals price on this account — ignore it |
| `POST /api/youbao/price` | **Real price change on a live machine** | `{vmId, productPrices:[{productId, priceFen}], confirm:true}` | `{status:"OK", vmId, count}`; 400 without boolean `confirm:true`; 409 kill switch; 503 rules unreadable; 502 友宝 error |
| `POST /api/youbao/order` | **Real wholesale purchase order** | `{poId, items:[{productId, productNum, unit:1\|2, deliveryCharge?}], contactOverride:{contactName, contactPhone, address} \| {pickupType:2, pullTime, factoryId?}, confirm:true}` | `{status:"OK", poId, outTradeNo, externalOrderId}`; same gates as price |
| `POST /api/youbao/restock-recommend` | Hint to 友宝's own ops team; no money; kill switch applies | `{vmId, wholesaleNo, products:[{productId(number), productCount, recommendReason(≤100)}]}` | `{status:"OK", vmId, wholesaleNo, count}` |

`unit`: `1` = box, `2` = each. `productId` here is the raw vendor number (no namespace).

## Agent state and rules (`A/...`)

| Route | What | Notes |
|---|---|---|
| `GET A/state` | Full `VendlingState`: `machines[]`, `products[]` (`{id, name, price, cost?}`), `slots[]` (`{id, machineId, productId, stock, capacity?, locked}`), `sales[]`, `votes[]`, `rules`, `decisionLog[]`, `restockRuns[]`, `lastLetter` | Big. Prefer specific routes when they exist |
| `GET A/rules` / `PATCH A/rules` | Guardrails: `priceCapPerItem`, `spendingLimitPerRun`, `availableHours`, `hardNoGos[]`, `killSwitchEngaged`, `simulationEnabled`, `probationUntil` | PATCH takes a partial object, validated against a whitelist; every change is logged and broadcast |
| `GET A/letter?format=text` | Owner letter (daily review) | JSON or text |
| `GET A/schedules` | Scheduled loops | |
| `GET A/export` | Full export | No import route exists |
| `GET A/memory?scope=qr:<vmId>\|feishu:<chatId>` | Conversation history + notes | |
| `GET A/interactions` | Every chat turn (audit) | |
| `GET A/tools?channel=customer_qr\|admin_dashboard\|feishu_dm&role=admin\|user` | Which tools a channel can see | |

## Machines (locations)

| Route | What | Request |
|---|---|---|
| `GET A/sync/devices` | Roster of registered machines | — → `{devices:[{vmId, name}]}` |
| `POST A/sync/youbao` | Register devices and sync inventory + sales now (replaces machines/products/slots/sales; keeps rules, locks, decisions) | `{devices:[{vmId, name}], salesWindowDays?}` (≥ 21) → sync result with `errors[]` (a machine with no ledger entries is warned about — the id may be wrong) |
| `DELETE A/sync/devices/<vmId>` | Remove a machine; purges profile/context/telemetry, keeps events + chat | → `{removed, purged, devices}` |
| `GET A/machine/<vmId>` | `{id, name}` or 404 | |
| `GET/PATCH A/machines/<vmId>/profile` | Physical profile: `city, address, placement(indoor\|outdoor\|semi_outdoor), venueType(office\|gym\|hospital\|campus\|transit\|residential\|retail\|other), floor, spot, notes` | → `{profile, missing[]}` |
| `GET/POST/DELETE A/machines/<vmId>/context[/<id>]` | What is around the machine (`kind: company\|event\|poi\|note`, `text`, `expiresAt`) | Served to the customer face, so keep it true |
| `POST A/slots/lock` | Pin a slot so curate never swaps it | `{slotId, locked:boolean}` |
| `GET /api/kiosk-url/<vmId>` | Kiosk URL with the device key for the machine's tablet | |

## Replenishment

| Route | What | Request / Response |
|---|---|---|
| `GET A/restock/plan` | Per-slot demand and recommendation | `{strategyVersion, params, leadTime:{days, source:"measured"\|"stated", samples}, stockHistoryPoints, measuredSlots, plans[]}`; plan = `{demand:{slotId, machineId, productId, dailyRate, naiveDailyRate, availableDays, emptyDays, closedDays, measured}, daysOfCover, stockoutAt, recommendation:{action:"order"\|"hold"\|…, quantity?}, productName, stock}` |
| `POST A/run/restock` | Build a run from the plan; creates a `restock_plan` decision (needs approval when over budget) | → `{run, decision, plans, leadTime, blocked, hitl}` |
| `POST A/restock/place-order` | Hand a run to the supplier (**simulated supplier today**) | `{runId}` → `{runId, orderedAt, note, shipEtaSeconds}`; 409 kill switch / already ordered / pending approval |
| `POST A/restock/receive` | Confirm delivery; stock goes up (capped at capacity) | `{runId, delivered:[{slotId, quantity≥0}], supplierNote?}` → `{runId, deliveredAt, slots[]}` |
| `GET A/restock/score?horizonDays=7` | Forecast accuracy | `{horizonDays, totalForecasts, pending, reports, scores[]}` |
| `GET A/planogram/<vmId>` | Shelf-space report | |
| `POST A/assortment/<vmId>` | Drop/add proposals | |
| `POST A/run/<loop>` | Manual trigger: `watch`, `curate`, `restock`, `letter`, `order-events?lookbackHours=`, `selfTune`, `background` | |

`restockRuns[]` items: `{id, weekOf, stops[], items[]{slotId, machineId, productId, productName, quantity}, estimatedMinutes, estimatedCost, requiresApproval, decisionId?, orderedAt?, deliveredAt?, deliveredItems?}`.

## Approvals (decisions)

| Route | What | Request |
|---|---|---|
| pending list | filter `state.decisionLog` where `requiresApproval && approved === null` | — |
| `POST A/resolve-decision` | Approve / reject | `{decisionId, approved:boolean, senderId?, chatId?}`; with a 飞书 identity both must be registered admins (403 otherwise); 404 unknown; 409 already resolved or not approvable |

Decision: `{id, timestamp, kind: swap\|price_change\|fault_flag\|restock_plan\|note, summary, reasoning, machineId?, slotId?, requiresApproval, approved: null\|true\|false}`.

## Events

| Route | What | Request |
|---|---|---|
| `GET A/events?limit=50` | Newest first | → `{events[]}` |
| `POST A/events` | Append (no dedup) | `{kind, summary, reasoning, machineId?}` → the stored event `{id, timestamp, kind, summary, reasoning, machineId?}` |
| WebSocket `wss://…/agents/vendling-agent/route-01` | `event-history`, `event`, `history`, `decision`, `decision-updated` | authenticate with the session cookie or bearer |

Known kinds: `order`, `hitl_resolution`, `machine_alert`, `face_intent`, `acl_granted/revoked`, `kill_switch`, `rules_changed`, `slot_locked/unlocked`, `profile_updated`, `context_added/removed`, `machine_registered/dropped/removed/online/offline`, `sync_problem`, `youbao_note`, `youbao_price_change`, `sale` (simulated).

## Access control and channels

| Route | What |
|---|---|
| `GET A/acl` / `POST A/acl {platform:"feishu", kind:"chat"\|"customer_chat", externalId, role?}` / `DELETE A/acl/<id>` | Who may talk to the agent as admin/user/customer. `kind:"user"` no longer grants admin — register the person's p2p chat as `kind:"chat"` |
| `POST /webhooks/feishu` (public, signature-verified) | 飞书 events and card callbacks |
| `POST A/chat {machineId, text}` / `POST A/feishu-chat` | One reasoning turn (customer / 飞书) |

## Customer surface (public, separate Worker `vendling-face`)

`GET /m/<vmId>`, `POST /m/<vmId>/chat {text}`, `/face-api/<vmId>/*`. Read-only for
business data; nothing here can dispense, order, or change a price.
