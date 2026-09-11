---
name: vendling-vendor-adapter
description: >
  Connect a vending-machine platform or a goods supplier to Vendling WITHOUT writing code in
  Vendling: expose the adapter contract as eight small HTTPS endpoints (spec appendix A.6),
  check them with the bundled conformance script, and hand the operator one registration JSON.
  Use this skill whenever a machine maker, cabinet/smart-fridge platform, wholesale platform or
  supplier asks to "接入 Vendling", "做 Vendling 适配器", "对接售货机运营方", "按 A.6 出接口",
  "字段对照", "HTTP 适配器", "VENDLING_HTTP_VENDORS", "conformance", or hands over an API field
  list to map — and when an operator wants to check a partner's endpoints before registering
  them. Not for calling Vendling's own /ucp/v1 API (that is the vendling-commerce-api skill).
---

# Vendling vendor adapter · zero-code onboarding

You are helping a **machine platform** (runs cabinets / vending machines) or a **supplier**
(sells goods) plug into Vendling, an AI agent that operates real vending machines. Vendling
never calls a vendor's native API. It calls a fixed contract — eight JSON-over-HTTPS
endpoints — and the vendor serves that contract in front of whatever they already have.
Your job: map their data onto the contract, get the endpoints up, prove they conform, and
produce the one-line registration the operator needs.

Spec: https://vendling.dev/api/ (appendix A.6 is the HTTP contract, A.1–A.3 the field rules).
Machine-readable: https://vendling.dev/api/llms-full.txt.

## 0. Which role, which endpoints

| Role | Namespace | Required | Optional (declare as `capabilities`) |
|---|---|---|---|
| `machine` — runs the machines | `<vendor>-machine` | `GET /inventory`, `GET /ledger` | `POST /prices` (`pricing`), `POST /restock` + `GET /restock/{ref}` (`replenishment.recommend` and/or `replenishment.order`) |
| `supply` — sells goods | `<vendor>-supply` | `GET /catalog`, `POST /orders`, `GET /orders/{ref}` | — |

One vendor can serve both roles under two namespaces (a platform that also supplies the goods).
`<vendor>` is a short lowercase slug the operator agrees on; the docs use `acme`.

## 1. The rules that break integrations (read before mapping)

- **Money is integer fen.** `priceFen: 600` is ¥6.00. A float, or a number that is clearly yuan,
  fails conformance.
- **Time is epoch milliseconds** (`1757400000000`), `null` when unknown. Seconds are wrong by 1000×.
- **Never look like an empty machine when something is wrong.** Errors are
  `{ "ok": false, "reason": "…" }` on any status; auth failures are HTTP `401`/`403`.
- **`vendorSku` is your own stable product id**, unique across all your machines. Vendling
  prefixes it with the namespace (`acme-machine:8837`) and never parses it.
- **Barcodes (EAN) matter**: they are the only automatic bridge between what is in a machine and
  what a supplier sells. Send `barcode` on inventory items and (via `spec`/title) on catalog rows.
- **A ledger record is one order**, lines inside; only lines with `status: "paid"` count as
  sales. Open-door / vision cabinets: send `state`, `takenAt`, `settledAt`, `updatedAt`,
  `finalized` and support `by=updated` (see `references/http-contract.md` §Ledger).
- **`costFen` only when it is a real cost** that differs from the price; otherwise `null`.
- **Customer identity never crosses**: no member ids, phone numbers or face ids in any payload.

## 2. Workflow

1. **Map fields.** Take the vendor's existing API or field list and fill the worksheet in
   `references/mapping-worksheet.md`. Every "required" row must have a source; every gap is a
   question back to the vendor, not a guess.
2. **Serve the endpoints.** Any stack. `scripts/mock_vendor.py` is a complete reference server
   (stdlib Python) — run it to see exact request/response shapes, or copy it as a starting point.
3. **Check conformance** against the real base URL (read-only by default — it never posts prices,
   restocks or orders):
   ```bash
   python3 scripts/vendling_vendor_check.py --base https://api.acme.example/vendling --token "$VENDOR_TOKEN" \
     --namespace acme-machine --location 12345678 --check-auth --supports pricing,replenishment.recommend
   ```
   Fix every FAIL; read every WARN (they are the mistakes that cost money later).
4. **Hand over the registration.** The checker prints the entry for the operator's
   `VENDLING_HTTP_VENDORS` secret:
   ```json
   [{ "namespace": "acme-machine", "baseUrl": "https://api.acme.example/vendling", "token": "…", "capabilities": ["pricing", "replenishment.recommend"] }]
   ```
   Send the token out of band. The operator registers it; nothing is deployed.
5. **Verify from the Vendling side** (operator, or you with the operator's token):
   `GET /ucp/v1/namespaces` lists the namespace as `live`, then
   `POST /ucp/v1/catalog/search {"filters":{"namespace":"acme-machine","location":"<machine id>"}}`
   returns your items with prices and barcodes (supply: `{"filters":{"namespace":"acme-supply"}}` returns
   your catalog with `sale_units`). A `namespace_unsupported` answer means the registration JSON is
   malformed (namespace must be `<vendor>-<role>`, baseUrl must be http(s)) or the capability was not
   declared. Note: the route's own hourly sync and sales ledger follow the operator's default machine
   namespace; switching a route to a new platform is an operator-side change.

## 3. Safety

- `POST /orders` (supply) places a **real** purchase; `POST /prices` changes a **real** price.
  The checker never calls them. If you must test them, do it against a staging base URL the vendor
  provides, never against production with a real machine id.
- Tokens: keep them out of URLs, logs and chat transcripts. One token per vendor, revocable.
- Rate: Vendling reads inventory hourly per machine and the ledger every 5 minutes (last 3 hours,
  paginated at 100). Size limits and caching are the vendor's call; `page`/`size` must be honoured.

## 4. Files

| Need | File |
|---|---|
| Exact endpoint shapes, field tables, error rules, registration | `references/http-contract.md` |
| Worksheet to map an existing API / field list onto the contract | `references/mapping-worksheet.md` |
| Conformance checker (stdlib Python; read-only) | `scripts/vendling_vendor_check.py` |
| Reference server implementing all eight endpoints (stdlib Python) | `scripts/mock_vendor.py` |
