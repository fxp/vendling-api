#!/usr/bin/env python3
"""Client + CLI for the Vendling Commerce API (UCP-shaped /ucp/v1 routes).
Standard library only.

Reads:
  VENDLING_BASE_URL   default https://vendling.xiaopingfeng.com
  VENDLING_AUTH_TOKEN operator token (required for everything but discovery)
  VENDLING_USER_AGENT optional; a descriptive UA is required on *.workers.dev

Money-moving / live-price calls refuse to run unless you pass --confirm,
which is what sends the JSON boolean `confirm: true` the server requires.
The string "true" is rejected server-side on purpose.

Namespaces are <vendor>-supply / <vendor>-machine and are discovered at
runtime (`namespaces`); the docs use the placeholder vendor `acme`.

Examples:
  python3 vendling_client.py discover
  python3 vendling_client.py namespaces
  python3 vendling_client.py locations
  python3 vendling_client.py inventory --vm 12345678                # default machine namespace
  python3 vendling_client.py catalog --keyword 乌龙 --limit 10        # default supply namespace
  python3 vendling_client.py sku acme-machine:8837
  python3 vendling_client.py resolve acme-machine:8837 --to acme-supply
  python3 vendling_client.py orders --vm 12345678 --from 2026-09-09T00:00:00+08:00 --to 2026-09-09T23:59:59+08:00
  python3 vendling_client.py plan
  python3 vendling_client.py approvals
  python3 vendling_client.py checkout --po po_20260909_001 --item acme-supply:10023x2:box --item acme-supply:10088x6 \
      --contact 张三 --phone 138... --address "..."
  python3 vendling_client.py complete --po po_20260909_001 --confirm
  python3 vendling_client.py price --vm 12345678 --item acme-machine:8837=650 --confirm
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("VENDLING_BASE_URL", "https://vendling.xiaopingfeng.com").rstrip("/")
UCP = "/ucp/v1"
TOKEN = os.environ.get("VENDLING_AUTH_TOKEN", "")
USER_AGENT = os.environ.get("VENDLING_USER_AGENT", "vendling-commerce-api-skill/2.0 (+https://vendling.dev/)")


class VendlingError(RuntimeError):
    def __init__(self, status: int, body):
        super().__init__(f"HTTP {status}: {json.dumps(body, ensure_ascii=False)[:600]}")
        self.status = status
        self.body = body


def _request(method: str, path: str, body=None, query=None, auth=True):
    url = BASE + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v not in (None, "")})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("user-agent", USER_AGENT)
    if auth:
        if not TOKEN:
            raise VendlingError(0, {"error": "VENDLING_AUTH_TOKEN is not set"})
        req.add_header("authorization", f"Bearer {TOKEN}")
    req.add_header("accept", "application/json")
    if data is not None:
        req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            raw, status = res.read(), res.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = {"raw": raw.decode(errors="replace")[:500]}
    return status, parsed


def call(method: str, path: str, body=None, query=None, auth=True):
    status, parsed = _request(method, path, body, query, auth)
    if status >= 400:
        raise VendlingError(status, parsed)
    return parsed


def ucp(method: str, path: str, body=None, query=None):
    """A standard route; business outcomes (200 + messages[]) are returned as-is."""
    return call(method, UCP + path, body, query)


_defaults: dict | None = None


def defaults() -> dict:
    """The default machine/supply namespaces, from GET /namespaces (cached)."""
    global _defaults
    if _defaults is None:
        _defaults = ucp("GET", "/namespaces").get("defaults", {})
    return _defaults


# ── discovery ─────────────────────────────────────────────────────────────
def discover():
    return call("GET", "/.well-known/ucp", auth=False)


def namespaces():
    return ucp("GET", "/namespaces")


# ── read ──────────────────────────────────────────────────────────────────
def locations(items: list[str] | None = None):
    return ucp("POST", "/locations/search", {**({"filters": {"items": [{"id": i} for i in items]}} if items else {})})


def inventory(vm_id: str, namespace: str | None = None):
    return ucp("POST", "/catalog/search", {"filters": {"namespace": namespace or defaults()["machine"], "location": vm_id}, "pagination": {"limit": 100}})


def catalog(keyword: str | None = None, limit: int = 20, namespace: str | None = None):
    return ucp("POST", "/catalog/search", {"query": keyword, "filters": {"namespace": namespace or defaults()["supply"]}, "pagination": {"limit": limit}})


def lookup(ids: list[str], location: str | None = None):
    return ucp("POST", "/catalog/lookup", {"ids": ids, **({"filters": {"location": location}} if location else {})})


def sku(sku_id: str, location: str | None = None):
    return ucp("GET", f"/skus/{urllib.parse.quote(sku_id, safe='')}", query={"location": location})


def resolve(ids: list[str], to_namespace: str | None = None):
    return ucp("POST", "/skus/resolve", {"ids": ids, "to_namespace": to_namespace or defaults()["supply"]})


def set_aliases(sku_id: str, aliases: list[str], source: str = "manual"):
    return ucp("PUT", f"/skus/{urllib.parse.quote(sku_id, safe='')}/aliases", {"aliases": [{"sku_id": a, "source": source} for a in aliases]})


def orders(start: str, end: str, vm_id: str | None = None, trade_status: str = "settled"):
    """start/end are RFC 3339 (+08:00)."""
    return ucp("GET", "/orders", query={"kind": "sale", "location": vm_id, "from": start, "to": end, "trade_status": trade_status, "limit": 100})


def order(order_id: str):
    return ucp("GET", f"/orders/{urllib.parse.quote(order_id, safe='')}")


def plan():
    return ucp("GET", "/replenishment/plan")


def runs(status: str | None = None):
    return ucp("GET", "/replenishment/runs", query={"status": status})


def events(limit: int = 50, location: str | None = None):
    return ucp("GET", "/events", query={"limit": limit, "location": location})


def approvals(status: str = "pending"):
    return ucp("GET", "/approvals", query={"status": status})


# ── write (no money) ──────────────────────────────────────────────────────
def append_event(kind: str, summary: str, reasoning: str, location: str | None = None):
    return ucp("POST", "/events", {"kind": kind, "summary": summary, "reasoning": reasoning, **({"location": location} if location else {})})


def resolve_approval(decision_id: str, approved: bool):
    return ucp("POST", f"/approvals/{urllib.parse.quote(decision_id, safe='')}", {"approved": approved})


def register_location(vm_id: str, name: str, profile: dict | None = None):
    return ucp("PUT", f"/locations/{vm_id}", {"name": name, **({"profile": profile} if profile else {})})


def sync(sales_window_days: int | None = None):
    return ucp("POST", "/locations/sync", {**({"sales_window_days": sales_window_days} if sales_window_days else {})})


def build_run():
    return ucp("POST", "/replenishment/runs")


def place_run(run_id: str):
    return ucp("POST", f"/replenishment/runs/{run_id}/place")


def receive_run(run_id: str, delivered: list[dict], note: str | None = None):
    return ucp("POST", f"/replenishment/runs/{run_id}/receive", {"delivered": delivered, **({"note": note} if note else {})})


def restock_recommend(vm_id: str, reference: str, lines: list[dict]):
    """lines = [{"sku_id": "acme-machine:8837", "quantity": 12, "reason": "..."}]"""
    return ucp("POST", f"/locations/{vm_id}/restock-recommendations", {"reference": reference, "line_items": [{"item": {"id": l["sku_id"]}, "quantity": l["quantity"], "reason": l["reason"]} for l in lines]})


# ── checkout (money) ──────────────────────────────────────────────────────
def create_checkout(po_id: str | None, lines: list[dict], shipping: dict | None = None, pickup_slot: str | None = None):
    """lines = [{"sku_id": "acme-supply:10023", "quantity": 2, "unit": "BX"|"EA"}].
    Creates the session only; nothing is spent until complete_checkout()."""
    body = {
        **({"id": po_id} if po_id else {}),
        "line_items": [{"item": {"id": l["sku_id"]}, "quantity": l["quantity"], **({"quantity_unit": {"unit": l["unit"]}} if l.get("unit", "EA") != "EA" else {})} for l in lines],
    }
    if shipping:
        body["fulfillment"] = {"methods": [{"type": "shipping", "destinations": [{"type": "shipping_address", **shipping}]}]}
    elif pickup_slot:
        body["fulfillment"] = {"methods": [{"type": "pickup", "groups": [{"selected_option_id": pickup_slot}]}]}
    return ucp("POST", "/checkout-sessions", body)


def get_checkout(po_id: str):
    return ucp("GET", f"/checkout-sessions/{urllib.parse.quote(po_id, safe='')}")


def complete_checkout(po_id: str, confirm: bool = False):
    """Real purchase order; costs money."""
    if confirm is not True:
        raise VendlingError(0, {"error": "refusing: complete_checkout needs confirm=True after the user approved this exact order"})
    return ucp("POST", f"/checkout-sessions/{urllib.parse.quote(po_id, safe='')}/complete", {"confirm": True})


# ── price (live) ──────────────────────────────────────────────────────────
def update_price(vm_id: str, prices: list[dict], confirm: bool = False):
    """prices = [{"sku_id": "acme-machine:8837", "amount": 650}] (fen). Real customer-facing write."""
    if confirm is not True:
        raise VendlingError(0, {"error": "refusing: update_price needs confirm=True after the user approved this exact change"})
    return ucp("PUT", f"/locations/{vm_id}/prices", {"prices": [{"item": {"id": p["sku_id"]}, "price": {"amount": p["amount"], "currency": "CNY"}} for p in prices], "confirm": True})


# ── CLI ───────────────────────────────────────────────────────────────────
def _with_ns(raw: str, role: str) -> str:
    return raw if ":" in raw else f"{defaults()[role]}:{raw}"


def _parse_line(spec: str) -> dict:
    """'acme-supply:10023x2:box' -> {sku_id, quantity: 2, unit: 'BX'}; ':each' or omitted -> EA."""
    unit = "EA"
    parts = spec.rsplit(":", 1)
    if len(parts) == 2 and parts[1].lower() in ("box", "bx", "each", "ea"):
        spec, unit = parts[0], ("BX" if parts[1].lower() in ("box", "bx") else "EA")
    sku_id, _, qty = spec.partition("x")
    return {"sku_id": _with_ns(sku_id, "supply"), "quantity": int(qty or 1), "unit": unit}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover")
    sub.add_parser("namespaces")
    sp = sub.add_parser("locations"); sp.add_argument("--has", action="append", help="machine sku_id that must be in stock")
    sp = sub.add_parser("inventory"); sp.add_argument("--vm", required=True); sp.add_argument("--namespace")
    sp = sub.add_parser("catalog"); sp.add_argument("--keyword"); sp.add_argument("--limit", type=int, default=20); sp.add_argument("--namespace")
    sp = sub.add_parser("lookup"); sp.add_argument("ids", nargs="+"); sp.add_argument("--vm")
    sp = sub.add_parser("sku"); sp.add_argument("sku_id"); sp.add_argument("--vm")
    sp = sub.add_parser("resolve"); sp.add_argument("ids", nargs="+"); sp.add_argument("--to")
    sp = sub.add_parser("alias"); sp.add_argument("sku_id"); sp.add_argument("--is", dest="aliases", action="append", required=True); sp.add_argument("--source", default="manual")
    sp = sub.add_parser("orders"); sp.add_argument("--vm"); sp.add_argument("--from", dest="start", required=True); sp.add_argument("--to", dest="end", required=True); sp.add_argument("--trade-status", default="settled")
    sp = sub.add_parser("order"); sp.add_argument("order_id")
    sub.add_parser("plan")
    sp = sub.add_parser("runs"); sp.add_argument("--status")
    sp = sub.add_parser("events"); sp.add_argument("--limit", type=int, default=50); sp.add_argument("--vm")
    sp = sub.add_parser("approvals"); sp.add_argument("--status", default="pending")
    sp = sub.add_parser("resolve-approval"); sp.add_argument("--decision", required=True); g = sp.add_mutually_exclusive_group(required=True); g.add_argument("--approve", action="store_true"); g.add_argument("--reject", action="store_true")
    sp = sub.add_parser("event"); sp.add_argument("--kind", required=True); sp.add_argument("--summary", required=True); sp.add_argument("--reasoning", required=True); sp.add_argument("--vm")
    sp = sub.add_parser("register"); sp.add_argument("--vm", required=True); sp.add_argument("--name", required=True); sp.add_argument("--profile", help="JSON object")
    sp = sub.add_parser("sync"); sp.add_argument("--days", type=int)
    sub.add_parser("build-run")
    sp = sub.add_parser("place"); sp.add_argument("--run", required=True)
    sp = sub.add_parser("receive"); sp.add_argument("--run", required=True); sp.add_argument("--slot", action="append", required=True, help="slotId=qty"); sp.add_argument("--note")
    sp = sub.add_parser("recommend"); sp.add_argument("--vm", required=True); sp.add_argument("--ref", required=True); sp.add_argument("--item", action="append", required=True, help="sku_id=qty=reason")
    sp = sub.add_parser("checkout"); sp.add_argument("--po"); sp.add_argument("--item", action="append", required=True, help="sku_idxQTY[:box|:each]")
    sp.add_argument("--contact"); sp.add_argument("--phone"); sp.add_argument("--address"); sp.add_argument("--pickup-slot", help="options[].id from a previous response")
    sp = sub.add_parser("get-checkout"); sp.add_argument("--po", required=True)
    sp = sub.add_parser("complete"); sp.add_argument("--po", required=True); sp.add_argument("--confirm", action="store_true")
    sp = sub.add_parser("price"); sp.add_argument("--vm", required=True); sp.add_argument("--item", action="append", required=True, help="sku_id=priceFen"); sp.add_argument("--confirm", action="store_true")
    a = p.parse_args(argv)

    try:
        if a.cmd == "discover": out = discover()
        elif a.cmd == "namespaces": out = namespaces()
        elif a.cmd == "locations": out = locations(a.has)
        elif a.cmd == "inventory": out = inventory(a.vm, a.namespace)
        elif a.cmd == "catalog": out = catalog(a.keyword, a.limit, a.namespace)
        elif a.cmd == "lookup": out = lookup(a.ids, a.vm)
        elif a.cmd == "sku": out = sku(a.sku_id, a.vm)
        elif a.cmd == "resolve": out = resolve(a.ids, a.to)
        elif a.cmd == "alias": out = set_aliases(a.sku_id, a.aliases, a.source)
        elif a.cmd == "orders": out = orders(a.start, a.end, a.vm, a.trade_status)
        elif a.cmd == "order": out = order(a.order_id)
        elif a.cmd == "plan": out = plan()
        elif a.cmd == "runs": out = runs(a.status)
        elif a.cmd == "events": out = events(a.limit, a.vm)
        elif a.cmd == "approvals": out = approvals(a.status)
        elif a.cmd == "resolve-approval": out = resolve_approval(a.decision, bool(a.approve))
        elif a.cmd == "event": out = append_event(a.kind, a.summary, a.reasoning, a.vm)
        elif a.cmd == "register": out = register_location(a.vm, a.name, json.loads(a.profile) if a.profile else None)
        elif a.cmd == "sync": out = sync(a.days)
        elif a.cmd == "build-run": out = build_run()
        elif a.cmd == "place": out = place_run(a.run)
        elif a.cmd == "receive": out = receive_run(a.run, [{"slot_id": s.split("=")[0], "quantity": int(s.split("=")[1])} for s in a.slot], a.note)
        elif a.cmd == "recommend":
            lines = []
            for it in a.item:
                sid, qty, reason = it.split("=", 2)
                lines.append({"sku_id": _with_ns(sid, "machine"), "quantity": int(qty), "reason": reason})
            out = restock_recommend(a.vm, a.ref, lines)
        elif a.cmd == "checkout":
            shipping = {"street_address": a.address, "first_name": a.contact, "phone_number": a.phone} if a.address else None
            out = create_checkout(a.po, [_parse_line(i) for i in a.item], shipping, a.pickup_slot)
        elif a.cmd == "get-checkout": out = get_checkout(a.po)
        elif a.cmd == "complete": out = complete_checkout(a.po, confirm=a.confirm)
        elif a.cmd == "price":
            prices = [{"sku_id": _with_ns(i.split("=")[0], "machine"), "amount": int(i.split("=")[1])} for i in a.item]
            out = update_price(a.vm, prices, confirm=a.confirm)
        else:
            p.error("unknown command")
    except VendlingError as e:
        print(json.dumps({"error": str(e), "status": e.status, "body": e.body}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
