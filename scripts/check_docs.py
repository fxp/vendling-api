#!/usr/bin/env python3
"""Consistency checker for the Vendling docs. Run: npm run lint:docs

The same facts are stated in several places on purpose — the guide is normative, the OpenAPI is
machine-readable, each skill must work offline from a zip. Duplication is fine; *drift* is not.
This script fails the build when the copies disagree.

  1  every endpoint named in the guide exists in the OpenAPI (and vice versa)
  2  the core operation set is identical in the guide, the OpenAPI badges and the skill
  3  every "N operations" claim matches the real count
  4  routes removed in a past version appear only in the change log
  5  no vendor name leaks into the public docs
  6  the A.6 HTTP contract, the vendor skill's reference and the mock server list the same endpoints
  7  the guide's endpoint index (§0.1) covers every operation
  8  every §section cross-reference resolves to a real heading
  9  partner badges in the OpenAPI match the partner table in §2.2
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "spec" / "commerce-api.md"
OPENAPI = ROOT / "openapi" / "vendling-commerce.openapi.yaml"
README = ROOT / "README.md"
C_SKILL = ROOT / "skill" / "vendling-commerce-api"
V_SKILL = ROOT / "skill" / "vendling-vendor-adapter"

PUBLISHED = [SPEC, OPENAPI, README, ROOT / "agent-setup" / "prompt.md", *sorted(C_SKILL.rglob("*.md")), *sorted(C_SKILL.rglob("*.py")), *sorted(V_SKILL.rglob("*.md")), *sorted(V_SKILL.rglob("*.py"))]
VENDOR_NAMES = re.compile(r"友宝|youbao|ubox|元气森林|yuanqi", re.I)
REMOVED_ROUTES = ["POST /catalog/product", "POST /locations/lookup", "POST /skus/resolve", "/restock-recommendations"]

problems: list[str] = []
notes: list[str] = []


def fail(check: str, msg: str):
    problems.append(f"{check}: {msg}")


def ok(check: str, msg: str):
    notes.append(f"{check}: {msg}")


def norm(ep: str) -> str:
    """One shape per operation: placeholder names, concrete ids and query strings all collapse,
    so `PUT /locations/12345678/prices` and `PUT /locations/{id}/prices` compare equal."""
    ep = re.sub(r"\?.*$", "", ep.strip()).rstrip("/")
    ep = re.sub(r"\{[^}]*\}", "{}", ep)
    ep = re.sub(r"/(?:\d{3,}|po_[\w]+|run-[\w]+|dec-[\w]+|[A-Za-z]*\d{6,}[\w]*)(?=/|$)", "/{}", ep)
    return re.sub(r"\s+", " ", ep)


# Matches `POST /catalog/search` in prose and `| `DELETE` | `/locations/{id}` |` in tables;
# a placeholder may contain anything, including spaces and Chinese.
METHOD_PATH = re.compile(r"`?\b(GET|POST|PUT|DELETE)`?[ ·|]*`?(…?/(?:\{[^}]*\}|[^`\s|、，。（）()])*)")


def endpoints_in(text: str, resolve=None) -> set[str]:
    """Every `METHOD /path` in prose, plus table rows that put the method and the path in
    adjacent code spans (`| Get Order | `GET` | `/orders/{id}` |`). A `…` prefix is resolved
    against the known operations by suffix."""
    out = set()
    for m in METHOD_PATH.finditer(text):
        path = m.group(2)
        if "{base}" in path:
            continue
        ep = norm(f"{m.group(1)} {path}")
        if ep.endswith(" ") or ep.split(" ", 1)[1] in ("", "/"):
            continue
        if ep.split(" ", 1)[1].startswith("…"):
            if resolve is None:
                continue
            tail = ep.split(" ", 1)[1].lstrip("…")
            hits = [k for k in resolve if k.startswith(m.group(1) + " ") and k.endswith(tail)]
            if len(hits) == 1:
                ep = hits[0]
            else:
                continue
        out.add(ep)
    return out


# ── sources ──────────────────────────────────────────────────────────────
spec = SPEC.read_text(encoding="utf-8")
api = OPENAPI.read_text(encoding="utf-8")
spec_body, _, changelog = spec.partition("## 附录 D")

api_ops: dict[str, str] = {}  # "POST /path" -> operationId
for pm in re.finditer(r"^  (/[^\n:]*):\n(.*?)(?=^  /|^components:)", api, re.S | re.M):
    path = pm.group(1)
    for vm in re.finditer(r"^    (get|post|put|delete):\n(.*?)(?=^    [a-z]+:|\Z)", pm.group(2), re.S | re.M):
        oid = re.search(r"operationId: (\w+)", vm.group(2))
        api_ops[norm(f"{vm.group(1).upper()} {path}")] = oid.group(1) if oid else "?"

badges: dict[str, set[str]] = {}
for m in re.finditer(r"operationId: (\w+)\n(\s+)x-badges:\n((?:\2  .*\n)+)", api):
    badges[m.group(1)] = set(re.findall(r"name: (\S+)", m.group(3)))
core_api = {oid for oid, b in badges.items() if "核心" in b}

# ── 1. endpoints named in the guide exist in the OpenAPI ─────────────────
spec_eps = {e for e in endpoints_in(spec_body, api_ops) if not e.split(" ", 1)[1].startswith("/ucp")}
unknown = sorted(e for e in spec_eps if e not in api_ops)
if unknown:
    fail("1", f"named in the guide but absent from the OpenAPI: {unknown}")
missing_from_spec = sorted(e for e in api_ops if e not in spec_eps)
if missing_from_spec:
    fail("1", f"in the OpenAPI but never named in the guide: {missing_from_spec}")
if not unknown and not missing_from_spec:
    ok("1", f"{len(api_ops)} operations, guide and OpenAPI agree")

# ── 2. the core set, three copies ────────────────────────────────────────
def table_endpoints(text: str) -> set[str]:
    return endpoints_in("\n".join(r for r in text.splitlines() if r.startswith("| ★")), api_ops)


core_spec = table_endpoints(re.search(r"### 2\.1.*?(?=\n### 2\.2)", spec_body, re.S).group(0))
endp_md = (C_SKILL / "references" / "ucp-endpoints.md").read_text(encoding="utf-8")
core_skill = table_endpoints(re.search(r"## Core set.*?(?=\n## )", endp_md, re.S).group(0))
core_api_eps = {e for e, oid in api_ops.items() if oid in core_api}
if core_spec != core_api_eps:
    fail("2", f"guide §2.1 vs OpenAPI 核心 badges differ: only in guide {sorted(core_spec - core_api_eps)}, only in OpenAPI {sorted(core_api_eps - core_spec)}")
if core_skill != core_api_eps:
    fail("2", f"skill Core set vs OpenAPI 核心 badges differ: only in skill {sorted(core_skill - core_api_eps)}, only in OpenAPI {sorted(core_api_eps - core_skill)}")
if core_spec == core_api_eps == core_skill:
    ok("2", f"core set identical in three places ({len(core_api_eps)} operations)")

# ── 3. "N operations" claims ─────────────────────────────────────────────
total = len(api_ops)
for path in (SPEC, OPENAPI, README, C_SKILL / "SKILL.md"):
    text = path.read_text(encoding="utf-8")
    for m in re.finditer(r"(?:一共 |of (?:the )?)(\d+) (?:个操作|operations)", text):
        if int(m.group(1)) != total:
            fail("3", f"{path.name} claims {m.group(1)} operations, there are {total}")
    for m in re.finditer(r"(\d+) of (?:the )?(\d+) operations", text):
        if int(m.group(1)) != len(core_api):
            fail("3", f"{path.name} claims {m.group(1)} core operations, badges mark {len(core_api)}")
if not [p for p in problems if p.startswith("3:")]:
    ok("3", f"operation counts agree ({len(core_api)} core of {total})")

# ── 4. removed routes only in the change log ─────────────────────────────
for route in REMOVED_ROUTES:
    hits = [p.relative_to(ROOT).as_posix() for p in PUBLISHED if route in p.read_text(encoding="utf-8") and not (p == SPEC and route not in spec_body)]
    if hits:
        fail("4", f"removed route {route!r} still referenced in {hits} (only the change log may mention it)")
if not [p for p in problems if p.startswith("4:")]:
    ok("4", f"{len(REMOVED_ROUTES)} removed routes appear only in the change log")

# ── 5. no vendor names ───────────────────────────────────────────────────
leaks = [p.relative_to(ROOT).as_posix() for p in PUBLISHED if VENDOR_NAMES.search(p.read_text(encoding="utf-8"))]
if leaks:
    fail("5", f"vendor name in public docs: {leaks}")
else:
    ok("5", f"{len(PUBLISHED)} published files, no vendor name")

# ── 6. the A.6 contract, three copies ────────────────────────────────────
a6 = re.search(r"### A\.6.*?(?=\n## 附录 B)", spec_body, re.S).group(0)
a6_eps = {norm(f"{m.group(1)} {m.group(2)}") for m in re.finditer(r"`(GET|POST) \{base\}(/[a-z{}/]+)", a6)}
contract = (V_SKILL / "references" / "http-contract.md").read_text(encoding="utf-8")
contract_eps = {norm(f"{m.group(1)} {m.group(2)}") for m in re.finditer(r"`(GET|POST) \{base\}(/[a-z{}/]+)", contract)}
mock = (V_SKILL / "scripts" / "mock_vendor.py").read_text(encoding="utf-8")
mock_paths = {re.sub(r"/$", "/{}", p) for p in re.findall(r'u\.path(?:\.startswith\(|\s*==\s*)"(/[a-z/]*)"', mock)}
a6_paths = {e.split(" ", 1)[1] for e in a6_eps}
if a6_eps != contract_eps:
    fail("6", f"A.6 vs the vendor skill's http-contract.md: only in A.6 {sorted(a6_eps - contract_eps)}, only in the skill {sorted(contract_eps - a6_eps)}")
if a6_paths != mock_paths:
    fail("6", f"A.6 vs mock_vendor.py routes: only in A.6 {sorted(a6_paths - mock_paths)}, only in the mock {sorted(mock_paths - a6_paths)}")
if a6_eps == contract_eps and a6_paths == mock_paths:
    ok("6", f"HTTP adapter contract identical in A.6, the skill reference and the mock server ({len(a6_eps)} endpoints)")

# ── 7. the endpoint index covers every operation ─────────────────────────
idx = re.search(r"### 0\.1.*?(?=\n### 0\.2)", spec_body, re.S)
if not idx:
    fail("7", "no endpoint index (§0.1) in the guide")
else:
    indexed = endpoints_in(idx.group(0), api_ops)
    gap = sorted(e for e in api_ops if e not in indexed)
    extra = sorted(e for e in indexed if e not in api_ops)
    if gap:
        fail("7", f"missing from the endpoint index: {gap}")
    if extra:
        fail("7", f"indexed but not an operation: {extra}")
    if not gap and not extra:
        ok("7", f"endpoint index covers all {len(api_ops)} operations")

# ── 8. section cross-references resolve ──────────────────────────────────
heads = {m.group(1).rstrip(".") for m in re.finditer(r"^#{2,4} (?:附录 )?([A-D0-9][0-9.]*)", spec, re.M)}
refs = {m.group(1).rstrip(".") for m in re.finditer(r"§([0-9A-D]+(?:\.[0-9]+)*)", spec)}
dangling = sorted(r for r in refs if r not in heads)
if dangling:
    fail("8", f"§{', §'.join(dangling)} referenced but no such section")
else:
    ok("8", f"{len(refs)} section cross-references all resolve")

# ── 9. partner badges vs the §2.2 table ──────────────────────────────────
partner_rows = re.search(r"### 2\.2.*?(?=\n### 2\.3)", spec_body, re.S).group(0)
for badge, column in (("售货机厂商", 3), ("商品供应商", 4)):
    badged = {e for e, oid in api_ops.items() if badge in badges.get(oid, ())}
    in_table = set()
    for row in partner_rows.splitlines():
        cells = [c.strip() for c in row.split("|")]
        if len(cells) < 6 or not cells[1].startswith("`"):
            continue
        if cells[column]:
            in_table |= endpoints_in(cells[1], api_ops)
    missing = sorted(b for b in badged if b not in in_table)
    if missing:
        fail("9", f"badged {badge} in the OpenAPI but absent from the §2.2 partner table: {missing}")
if not [p for p in problems if p.startswith("9:")]:
    ok("9", "partner badges are all covered by the §2.2 table")

# ── report ───────────────────────────────────────────────────────────────
for n in notes:
    print(f"  ok   {n}")
for p in problems:
    print(f"  FAIL {p}", file=sys.stderr)
print(f"\n{len(notes)} ok · {len(problems)} failed")
sys.exit(1 if problems else 0)
