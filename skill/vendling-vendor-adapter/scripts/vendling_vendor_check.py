#!/usr/bin/env python3
"""Conformance checker for the Vendling HTTP adapter contract (spec appendix A.6).

Read-only by default: it calls GET /inventory, GET /ledger, GET /catalog (and, with --ref,
GET /restock/{ref} or GET /orders/{ref}). It never posts prices, restock requests or orders.
Stdlib only.

    python3 vendling_vendor_check.py --base https://api.acme.example/vendling --token "$T" \
        --namespace acme-machine --location 12345678 --check-auth --supports pricing,replenishment.recommend

    python3 vendling_vendor_check.py --base … --token "$T" --namespace acme-supply --check-auth

Exit code 0 = no FAIL (warnings allowed), 1 = at least one FAIL, 2 = could not run.
Prints a report and, at the end, the registration entry for VENDLING_HTTP_VENDORS.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

NAMESPACE_RE = re.compile(r"^([a-z][a-z0-9]*)-(supply|machine)$")
LINE_STATUSES = {"paid", "unpaid", "refunded", "refund_failed", "cancelled"}
STATES = {"in_progress", "pending_review", "settled", "payment_failed", "refunded", "cancelled"}
RESTOCK_STATES = {"received", "in_transit", "completed", "cancelled"}
ORDER_STATES = {"ordered", "arrived", "cancelled"}
MS_FLOOR = 10**11  # anything below this is seconds (or nonsense)


class Report:
    def __init__(self):
        self.rows: list[tuple[str, str, str]] = []

    def add(self, level: str, where: str, msg: str):
        self.rows.append((level, where, msg))

    ok = lambda self, w, m: self.add("PASS", w, m)  # noqa: E731
    warn = lambda self, w, m: self.add("WARN", w, m)  # noqa: E731
    fail = lambda self, w, m: self.add("FAIL", w, m)  # noqa: E731

    def failed(self) -> bool:
        return any(l == "FAIL" for l, _, _ in self.rows)

    def dump(self):
        width = max((len(w) for _, w, _ in self.rows), default=10)
        for level, where, msg in self.rows:
            print(f"{level:4}  {where:<{width}}  {msg}")
        n = {k: sum(1 for l, _, _ in self.rows if l == k) for k in ("PASS", "WARN", "FAIL")}
        print(f"\n{n['PASS']} pass · {n['WARN']} warn · {n['FAIL']} fail")


def call(base: str, path: str, token: str | None, query: dict | None = None, timeout: float = 15.0):
    url = base.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    req = urllib.request.Request(url, headers={"accept": "application/json", "user-agent": "vendling-vendor-check/1", **({"authorization": f"Bearer {token}"} if token else {})})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            status, raw = res.status, res.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except Exception as e:  # noqa: BLE001
        return None, None, str(e), time.time() - t0
    try:
        body = json.loads(raw.decode("utf-8")) if raw else None
    except (ValueError, UnicodeDecodeError):
        body = None
    return status, body, None, time.time() - t0


def is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def check_ms(rep: Report, where: str, v, required: bool):
    if v is None:
        if required:
            rep.warn(where, "is null (allowed, but Vendling then cannot place this record in time)")
        return
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        rep.fail(where, f"must be epoch milliseconds or null, got {v!r}")
    elif v < MS_FLOOR:
        rep.fail(where, f"{v} looks like seconds, not milliseconds (×1000)")


def check_fen(rep: Report, where: str, v, required=True):
    if v is None and not required:
        return
    if not is_int(v):
        rep.fail(where, f"must be an integer number of fen, got {v!r}" + (" (a float means yuan — multiply by 100)" if isinstance(v, float) else ""))
    elif 0 < v < 30:
        rep.warn(where, f"{v} fen is ¥{v/100:.2f} — is this yuan by mistake?")


def check_envelope(rep: Report, where: str, status, body, err) -> dict | None:
    if err:
        rep.fail(where, f"unreachable: {err}")
        return None
    if body is None or not isinstance(body, dict):
        rep.fail(where, f"HTTP {status}: body is not a JSON object")
        return None
    if body.get("ok") is not True:
        rep.fail(where, f"HTTP {status}: ok is not true (reason: {body.get('reason')!r})")
        return None
    if status != 200:
        rep.warn(where, f"ok:true with HTTP {status} — use 200 for success")
    return body


def check_inventory(rep: Report, base, token, location):
    where = "GET /inventory"
    status, body, err, dt = call(base, "/inventory", token, {"locationId": location})
    body = check_envelope(rep, where, status, body, err)
    if body is None:
        return
    items = body.get("items")
    if not isinstance(items, list):
        rep.fail(where, "items must be an array")
        return
    rep.ok(where, f"{len(items)} item(s) in {dt*1000:.0f} ms")
    if not items:
        rep.warn(where, "no items — is the locationId right? Vendling treats an empty machine as truth")
    skus = set()
    slots = set()
    no_barcode = 0
    for i, it in enumerate(items):
        w = f"items[{i}]"
        if not isinstance(it, dict):
            rep.fail(w, "must be an object")
            continue
        sku = it.get("vendorSku")
        if not (isinstance(sku, str) and sku) and not is_int(sku):
            rep.fail(w + ".vendorSku", "required (string or number)")
        else:
            skus.add(str(sku))
        if not isinstance(it.get("title"), str) or not it.get("title"):
            rep.fail(w + ".title", "required string")
        check_fen(rep, w + ".priceFen", it.get("priceFen"))
        if not is_int(it.get("stock")) or it.get("stock") < 0:
            rep.fail(w + ".stock", f"must be a non-negative integer, got {it.get('stock')!r}")
        if not it.get("barcode"):
            no_barcode += 1
        elif not re.fullmatch(r"\d{8,14}", str(it["barcode"])):
            rep.warn(w + ".barcode", f"{it['barcode']!r} is not an EAN/UPC-looking code")
        if it.get("slotId"):
            slots.add(str(it["slotId"]))
    if len(skus) < len(items):
        rep.warn(where, f"{len(items) - len(skus)} duplicate vendorSku(s): the same product in several slots needs slotId to tell them apart")
    if no_barcode:
        rep.warn(where, f"{no_barcode}/{len(items)} items have no barcode — without it the operator must map every product to a supplier sku by hand")
    if items and not slots:
        rep.warn(where, "no slotId on any item — fine for one-product-per-place machines, required for layered cabinets")


def check_ledger(rep: Report, base, token, from_ms, to_ms):
    where = "GET /ledger"
    status, body, err, dt = call(base, "/ledger", token, {"fromMs": from_ms, "toMs": to_ms, "page": 1, "size": 100})
    body = check_envelope(rep, where, status, body, err)
    if body is None:
        return
    for k in ("page", "pages", "total"):
        if not is_int(body.get(k)):
            rep.fail(where + f".{k}", f"must be an integer, got {body.get(k)!r}")
    records = body.get("records")
    if not isinstance(records, list):
        rep.fail(where + ".records", "must be an array")
        return
    rep.ok(where, f"{len(records)} record(s) of {body.get('total')} in {dt*1000:.0f} ms")
    if not records:
        rep.warn(where, "no records in the window — widen --from/--to or check the machine sold something; shapes below could not be verified")
    has_state = has_updated = 0
    for i, r in enumerate(records):
        w = f"records[{i}]"
        if not isinstance(r, dict):
            rep.fail(w, "must be an object")
            continue
        if not (isinstance(r.get("orderNo"), str) and r["orderNo"]):
            rep.fail(w + ".orderNo", "required non-empty string")
        if not isinstance(r.get("status"), str):
            rep.fail(w + ".status", "required string (your raw status)")
        if not (isinstance(r.get("locationId"), str) and r["locationId"]):
            rep.fail(w + ".locationId", "required non-empty string")
        check_fen(rep, w + ".totalFen", r.get("totalFen"))
        check_ms(rep, w + ".createdAt", r.get("createdAt"), True)
        for k in ("takenAt", "settledAt", "updatedAt"):
            if k in r:
                check_ms(rep, w + f".{k}", r.get(k), False)
        if r.get("state") is not None:
            has_state += 1
            if r["state"] not in STATES:
                rep.fail(w + ".state", f"{r['state']!r} is not one of {sorted(STATES)}")
        if r.get("updatedAt") is not None:
            has_updated += 1
        if "finalized" in r and not isinstance(r["finalized"], bool):
            rep.fail(w + ".finalized", "must be a boolean")
        for pk in ("memberId", "member_id", "userId", "user_id", "phone", "mobile", "faceId", "openid"):
            if pk in r:
                rep.fail(w + f".{pk}", "customer identity must not be sent")
        lines = r.get("lines")
        if not isinstance(lines, list):
            rep.fail(w + ".lines", "must be an array")
            continue
        if not lines:
            # A real account returns line-less orders: a session that opened
            # and has not resolved, or one that closed with nothing taken.
            # They are not sales and they are not malformed — but they are
            # dangerous, because a caller is invited to derive state from the
            # lines ("all paid -> settled") and [].every() is vacuously true.
            # So the only hard requirement is that such a record SAYS what it
            # is; a settled order with nothing in it really is malformed.
            if r.get("state") == "settled" or not r.get("state"):
                rep.fail(w + ".lines", "empty: a record with no lines must carry a non-settled `state` (in_progress / cancelled / …), or a caller deriving state from the lines books it as a settled sale")
            continue
        for j, l in enumerate(lines):
            lw = f"{w}.lines[{j}]"
            if not isinstance(l, dict):
                rep.fail(lw, "must be an object")
                continue
            if not (isinstance(l.get("vendorSku"), str) and l["vendorSku"]) and not is_int(l.get("vendorSku")):
                rep.fail(lw + ".vendorSku", "required")
            check_fen(rep, lw + ".priceFen", l.get("priceFen"))
            if l.get("status") not in LINE_STATUSES:
                rep.fail(lw + ".status", f"{l.get('status')!r} must be one of {sorted(LINE_STATUSES)}")
            if "costFen" not in l:
                rep.fail(lw + ".costFen", "required (use null when there is no real cost)")
            elif l["costFen"] is not None:
                check_fen(rep, lw + ".costFen", l["costFen"])
                if l["costFen"] == l.get("priceFen"):
                    rep.warn(lw + ".costFen", "equals priceFen — a cost that is just the price carries no information; send null")
    if records and not has_state:
        rep.warn(where, "no record carries `state` — Vendling will derive it from line statuses; open-door cabinets must send it")
    if records and not has_updated:
        rep.warn(where, "no record carries `updatedAt` — late settlements, reviews and refunds cannot be polled (see by=updated)")
    # by=updated support
    status, body2, err, _ = call(base, "/ledger", token, {"fromMs": from_ms, "toMs": to_ms, "page": 1, "size": 1, "by": "updated"})
    if err or body2 is None:
        rep.warn(where + "?by=updated", "not answered — acceptable only for pay-then-dispense machines")
    elif body2.get("ok") is True:
        rep.ok(where + "?by=updated", "supported")
    else:
        rep.warn(where + "?by=updated", f"refused ({body2.get('reason')!r}) — acceptable only for pay-then-dispense machines")
    # pagination honoured?
    status, body3, err, _ = call(base, "/ledger", token, {"fromMs": from_ms, "toMs": to_ms, "page": 1, "size": 1})
    if body3 and body3.get("ok") is True and isinstance(body3.get("records"), list) and len(body3["records"]) > 1:
        rep.fail(where + "?size=1", f"returned {len(body3['records'])} records for size=1 — page/size must be honoured")


def check_catalog(rep: Report, base, token):
    where = "GET /catalog"
    status, body, err, dt = call(base, "/catalog", token)
    body = check_envelope(rep, where, status, body, err)
    if body is None:
        return
    products = body.get("products")
    if not isinstance(products, list):
        rep.fail(where + ".products", "must be an array")
        return
    rep.ok(where, f"{len(products)} product(s) in {dt*1000:.0f} ms")
    if not isinstance(body.get("sites", []), list):
        rep.fail(where + ".sites", "must be an array when present")
    for i, p in enumerate(products):
        w = f"products[{i}]"
        if not isinstance(p, dict):
            rep.fail(w, "must be an object")
            continue
        if not (isinstance(p.get("vendorSku"), str) and p["vendorSku"]) and not is_int(p.get("vendorSku")):
            rep.fail(w + ".vendorSku", "required")
        if not isinstance(p.get("title"), str) or not p["title"]:
            rep.fail(w + ".title", "required string")
        ps = p.get("packSize")
        if not is_int(ps) or ps < 1:
            rep.fail(w + ".packSize", f"must be an integer ≥ 1, got {ps!r}")
        check_fen(rep, w + ".eachPriceFen", p.get("eachPriceFen"))
        if is_int(ps) and ps > 1:
            check_fen(rep, w + ".packPriceFen", p.get("packPriceFen"))
            if is_int(p.get("packPriceFen")) and is_int(p.get("eachPriceFen")) and abs(p["packPriceFen"] / ps - p["eachPriceFen"]) > 1 and not p.get("eachPriceDerived"):
                rep.warn(w + ".eachPriceFen", f"{p['eachPriceFen']} ≠ packPriceFen/packSize ({p['packPriceFen']/ps:.0f}); fine if the unit price is really quoted, else set eachPriceDerived")
        if not is_int(p.get("stock")) or p["stock"] < 0:
            rep.fail(w + ".stock", "must be a non-negative integer")


def check_status_endpoint(rep: Report, base, token, path, states, where):
    status, body, err, dt = call(base, path, token)
    body = check_envelope(rep, where, status, body, err)
    if body is None:
        return
    if body.get("state") not in states:
        rep.fail(where + ".state", f"{body.get('state')!r} must be one of {sorted(states)}")
    else:
        rep.ok(where, f"state {body['state']} in {dt*1000:.0f} ms")


def check_auth(rep: Report, base, token, path, query):
    where = f"auth on {path}"
    status, body, err, _ = call(base, path, "definitely-wrong-" + (token or "x")[:4], query)
    if err:
        rep.fail(where, f"unreachable: {err}")
    elif status in (401, 403):
        rep.ok(where, f"wrong token → HTTP {status}")
    elif isinstance(body, dict) and body.get("ok") is False:
        rep.warn(where, f"wrong token → HTTP {status} with ok:false; prefer 401/403 so it is recorded as an auth failure")
    else:
        rep.fail(where, f"wrong token → HTTP {status} with a normal body: a rotated token would look like an empty vendor")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="vendor base URL, e.g. https://api.acme.example/vendling")
    ap.add_argument("--token", default=None)
    ap.add_argument("--namespace", required=True, help="<vendor>-machine or <vendor>-supply (decides which endpoints are checked)")
    ap.add_argument("--location", help="a machine id for GET /inventory (machine role)")
    ap.add_argument("--from", dest="from_ms", type=int, help="ledger window start, epoch ms (default: 7 days ago)")
    ap.add_argument("--to", dest="to_ms", type=int, help="ledger window end, epoch ms (default: now)")
    ap.add_argument("--ref", help="an existing restock ref (machine) or order ref (supply) to check the status endpoint")
    ap.add_argument("--check-auth", action="store_true", help="also verify that a wrong token is refused with 401/403")
    ap.add_argument("--supports", default="", help="optional capabilities you serve, comma-separated: pricing, replenishment.recommend, replenishment.order")
    ap.add_argument("--shares-sku-space-with", default="", metavar="NAMESPACE",
                    help="the SAME vendor's other-role namespace, when both roles use one product id space "
                         "(a platform that runs the machines and also sells the goods). Goes into the registration JSON.")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    a = ap.parse_args(argv)

    m = NAMESPACE_RE.match(a.namespace)
    if not m:
        print("namespace must be <vendor>-machine or <vendor>-supply", file=sys.stderr)
        return 2
    role = m.group(2)
    rep = Report()
    now = int(time.time() * 1000)
    from_ms = a.from_ms or now - 7 * 24 * 3600 * 1000
    to_ms = a.to_ms or now

    if role == "machine":
        if not a.location:
            print("--location <machine id> is required for a machine namespace", file=sys.stderr)
            return 2
        check_inventory(rep, a.base, a.token, a.location)
        check_ledger(rep, a.base, a.token, from_ms, to_ms)
        if a.ref:
            check_status_endpoint(rep, a.base, a.token, f"/restock/{urllib.parse.quote(a.ref, safe='')}", RESTOCK_STATES, "GET /restock/{ref}")
        if a.check_auth:
            check_auth(rep, a.base, a.token, "/inventory", {"locationId": a.location})
    else:
        check_catalog(rep, a.base, a.token)
        if a.ref:
            check_status_endpoint(rep, a.base, a.token, f"/orders/{urllib.parse.quote(a.ref, safe='')}", ORDER_STATES, "GET /orders/{ref}")
        if a.check_auth:
            check_auth(rep, a.base, a.token, "/catalog", None)

    caps = [c.strip() for c in a.supports.split(",") if c.strip()]
    bad = [c for c in caps if c not in ("pricing", "replenishment.recommend", "replenishment.order")]
    if bad:
        rep.fail("--supports", f"unknown capabilities {bad}; allowed: pricing, replenishment.recommend, replenishment.order")
    if role == "supply" and caps:
        rep.warn("--supports", "supply namespaces have no optional capabilities; ignored")
        caps = []
    entry = {"namespace": a.namespace, "baseUrl": a.base.rstrip("/"), "token": a.token or "<token>", **({"capabilities": caps} if caps else {})}
    if a.shares_sku_space_with:
        entry["sharesSkuSpaceWith"] = a.shares_sku_space_with

    if a.json:
        print(json.dumps({"rows": [{"level": l, "where": w, "message": m} for l, w, m in rep.rows], "failed": rep.failed(), "registration": entry}, ensure_ascii=False, indent=2))
    else:
        rep.dump()
        print("\nRegistration entry for VENDLING_HTTP_VENDORS (send the token out of band):")
        print(json.dumps([entry], ensure_ascii=False, indent=2))
        print("\nNot checked (they have side effects): POST /prices, POST /restock, POST /orders. Test those against a staging base URL only.")
        if not a.shares_sku_space_with:
            print("If this vendor runs the machines AND sells the goods with ONE product id space for both,\n"
                  "re-run with --shares-sku-space-with <the other namespace>. Without it the operator has to\n"
                  "confirm every product by hand, and a supplier that publishes no barcodes cannot be bridged at all.")
    return 1 if rep.failed() else 0


if __name__ == "__main__":
    sys.exit(main())
