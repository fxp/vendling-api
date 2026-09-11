#!/usr/bin/env python3
"""Reference implementation of the Vendling HTTP adapter contract (spec appendix A.6).

Serves BOTH roles under one base URL with in-memory sample data, so a vendor can see the exact
shapes, point the conformance checker at it, or copy it as a starting point. Stdlib only.

    python3 mock_vendor.py --port 8790 --token demo
    python3 vendling_vendor_check.py --base http://127.0.0.1:8790 --token demo --location M1 --check-auth

Endpoints: GET /inventory, GET /ledger, POST /prices, POST /restock, GET /restock/{ref},
           GET /catalog, POST /orders, GET /orders/{ref}
"""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

NOW = int(time.time() * 1000)
H = 3600 * 1000

MACHINES = {
    "M1": [
        {"vendorSku": "8837", "title": "红牛 250ml", "barcode": "6920202888888", "priceFen": 600, "stock": 4, "slotId": "L1-1"},
        {"vendorSku": "1", "title": "可口可乐 330ml", "barcode": "6928804011166", "priceFen": 300, "stock": 9, "slotId": "L1-2"},
        {"vendorSku": "10", "title": "乌龙茶 500ml", "barcode": "6901234567890", "priceFen": 450, "stock": 0, "slotId": "L2-1"},
    ],
    "M2": [
        {"vendorSku": "8837", "title": "红牛 250ml", "barcode": "6920202888888", "priceFen": 650, "stock": 7, "slotId": "L1-1"},
    ],
}

# One settled spiral-machine order, one open-door cabinet order still being recognised,
# one refund after settlement — enough to exercise the six states and `by=updated`.
LEDGER = [
    {"orderNo": "S-1001", "status": "PAID", "statusLabel": "已支付", "state": "settled", "locationId": "M1", "locationName": "Mock 11F",
     "totalFen": 600, "createdAt": NOW - 2 * H, "createdAtRaw": "", "takenAt": NOW - 2 * H, "settledAt": NOW - 2 * H, "updatedAt": NOW - 2 * H, "finalized": True,
     "lines": [{"vendorSku": "8837", "priceFen": 600, "costFen": None, "status": "paid"}]},
    {"orderNo": "S-1002", "status": "RECOGNIZING", "statusLabel": "识别中", "state": "in_progress", "locationId": "M2", "locationName": "Mock 10F",
     "totalFen": 0, "createdAt": NOW - 20 * 60 * 1000, "createdAtRaw": "", "takenAt": NOW - 20 * 60 * 1000, "settledAt": None, "updatedAt": NOW - 15 * 60 * 1000, "finalized": False,
     "lines": [{"vendorSku": "8837", "priceFen": 650, "costFen": 380, "status": "unpaid"}]},
    {"orderNo": "S-0990", "status": "REFUNDED", "statusLabel": "已退款", "state": "refunded", "locationId": "M1", "locationName": "Mock 11F",
     "totalFen": 0, "createdAt": NOW - 30 * H, "createdAtRaw": "", "takenAt": NOW - 30 * H, "settledAt": NOW - 30 * H, "updatedAt": NOW - 1 * H, "finalized": True,
     "lines": [{"vendorSku": "1", "priceFen": 300, "costFen": None, "status": "refunded"}]},
]

CATALOG = [
    {"vendorSku": "10023", "title": "乌龙茶 500ml", "spec": "500ml×15 6901234567890", "category": "饮料", "packSize": 15, "packPriceFen": 5700, "eachPriceFen": 380, "eachPriceDerived": True, "stock": 40},
    {"vendorSku": "10088", "title": "红牛 250ml", "spec": "250ml×24 6920202888888", "category": "饮料", "packSize": 24, "packPriceFen": 11040, "eachPriceFen": 460, "eachPriceDerived": False, "stock": 12},
    {"vendorSku": "10100", "title": "口香糖", "spec": "单个", "category": "零食", "packSize": 1, "packPriceFen": 250, "eachPriceFen": 250, "eachPriceDerived": False, "stock": 300},
]
SITES = [{"id": "w1", "name": "北仓", "address": "某物流园 3 号库"}]

RESTOCKS: dict[str, dict] = {}
ORDERS: dict[str, dict] = {}


def paginate(rows, page, size):
    pages = max(1, (len(rows) + size - 1) // size)
    start = (page - 1) * size
    return rows[start : start + size], pages


class Handler(BaseHTTPRequestHandler):
    token = "demo"

    def log_message(self, fmt, *args):  # quieter
        print("%s %s" % (self.command, self.path))

    def _send(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _auth(self) -> bool:
        ok = self.headers.get("authorization") == f"Bearer {self.token}"
        if not ok:
            self._send(401, {"ok": False, "reason": "bad or missing bearer token"})
        return ok

    def _body(self):
        n = int(self.headers.get("content-length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if not self._auth():
            return
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/inventory":
            items = MACHINES.get(q.get("locationId", ""))
            if items is None:
                return self._send(404, {"ok": False, "reason": f"unknown locationId {q.get('locationId')}"})
            return self._send(200, {"ok": True, "items": items})
        if u.path == "/ledger":
            try:
                lo, hi = int(q.get("fromMs", 0)), int(q.get("toMs", NOW + H))
                page, size = int(q.get("page", 1)), int(q.get("size", 100))
            except ValueError:
                return self._send(400, {"ok": False, "reason": "fromMs/toMs/page/size must be integers"})
            key = "updatedAt" if q.get("by") == "updated" else "takenAt"
            rows = [r for r in LEDGER if r.get(key) is not None and lo <= r[key] <= hi]
            if q.get("settledOnly") == "true":
                rows = [r for r in rows if r["state"] == "settled"]
            chunk, pages = paginate(rows, page, size)
            return self._send(200, {"ok": True, "page": page, "pages": pages, "total": len(rows), "records": chunk})
        if u.path.startswith("/restock/"):
            ref = u.path.split("/", 2)[2]
            r = RESTOCKS.get(ref)
            if not r:
                return self._send(404, {"ok": False, "reason": f"unknown restock ref {ref}"})
            return self._send(200, {"ok": True, "state": "completed", "delivered": [{"vendorSku": l["vendorSku"], "quantity": l["quantity"]} for l in r["lines"]], "completedAt": NOW, "rawStatus": "DONE"})
        if u.path == "/catalog":
            kw = q.get("keyword")
            rows = [p for p in CATALOG if not kw or kw in p["title"]]
            return self._send(200, {"ok": True, "products": rows, "sites": SITES})
        if u.path.startswith("/orders/"):
            ref = u.path.split("/", 2)[2]
            o = ORDERS.get(ref)
            if not o:
                return self._send(404, {"ok": False, "reason": f"unknown order ref {ref}"})
            return self._send(200, {"ok": True, "state": "ordered", "description": "已接单", "rawStatus": 2, "logistics": []})
        self._send(404, {"ok": False, "reason": "no such endpoint"})

    def do_POST(self):
        if not self._auth():
            return
        u = urlparse(self.path)
        try:
            body = self._body()
        except json.JSONDecodeError:
            return self._send(400, {"ok": False, "reason": "body must be JSON"})
        if u.path == "/prices":
            items = MACHINES.get(str(body.get("locationId")))
            if items is None:
                return self._send(404, {"ok": False, "reason": "unknown locationId"})
            n = 0
            for line in body.get("lines", []):
                for it in items:
                    if it["vendorSku"] == str(line.get("vendorSku")) and isinstance(line.get("priceFen"), int):
                        it["priceFen"] = line["priceFen"]
                        n += 1
            if n != len(body.get("lines", [])):
                return self._send(400, {"ok": False, "reason": "one or more skus are not in this machine"})
            return self._send(200, {"ok": True, "count": n})
        if u.path == "/restock":
            ref = str(body.get("ref") or "")
            if not ref or not body.get("lines"):
                return self._send(400, {"ok": False, "reason": "ref and lines are required"})
            if ref not in RESTOCKS:  # idempotent
                RESTOCKS[ref] = {"lines": body["lines"], "binding": bool(body.get("binding")), "externalRef": f"RS-{len(RESTOCKS) + 1}"}
            r = RESTOCKS[ref]
            out = {"ok": True, "count": len(r["lines"])}
            if r["binding"]:
                out["externalRef"] = r["externalRef"]
            return self._send(200, out)
        if u.path == "/orders":
            ref = str(body.get("ref") or "")
            f = body.get("fulfillment") or {}
            if not ref or not body.get("lines"):
                return self._send(400, {"ok": False, "reason": "ref and lines are required"})
            if f.get("method") not in ("shipping", "pickup"):
                return self._send(400, {"ok": False, "reason": f"unsupported fulfillment method {f.get('method')!r}; this supplier ships or hands over at a warehouse"})
            if ref not in ORDERS:  # idempotent: same ref, same order
                ORDERS[ref] = {"lines": body["lines"], "externalRef": f"SUP-{len(ORDERS) + 1001}"}
            return self._send(200, {"ok": True, "externalRef": ORDERS[ref]["externalRef"]})
        self._send(404, {"ok": False, "reason": "no such endpoint"})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--token", default="demo")
    a = ap.parse_args()
    Handler.token = a.token
    srv = ThreadingHTTPServer((a.bind, a.port), Handler)
    print(f"mock vendor on http://{a.bind}:{a.port} (token {a.token!r}); machines {list(MACHINES)}; Ctrl-C to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
