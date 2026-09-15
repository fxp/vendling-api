#!/usr/bin/env python3
"""Generate the A.6 wire types from contracts/adapter-a6.json.

  python3 scripts/gen_adapter_types.py --check           verify checked-in copies
  python3 scripts/gen_adapter_types.py --write PATH…     (re)write them

Why this exists
---------------
These shapes were written out by hand three times: vendling-core's
src/vendors/types.ts, each adapter's src/contract.ts, and this repo's prose.
One of the copies literally said "mirrors the other, which is the normative
copy" — which is an honest admission that nothing enforced it. Drift between
two copies of a wire contract is silent by construction: both sides compile,
both sides pass their own tests, and the disagreement only shows up as a
field that is quietly always undefined in production.

So the JSON next door is the source, and the TypeScript is output. Consumers
commit the generated file rather than generating at install time: a Worker
repo should not need this repo checked out, or a network, to build.

`--check` is what keeps it honest. Each consumer's test suite runs it, so a
hand-edit to a generated file fails there rather than in a vendor's
integration six weeks later.
"""

import argparse
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "contracts" / "adapter-a6.json"


def wrap(text: str, indent: str = " *  ", width: int = 72) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(indent + cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(indent + cur)
    return lines


def doc_block(text: str | None, pad: str = "") -> list[str]:
    if not text:
        return []
    body = wrap(text, f"{pad} *  ")
    if len(body) == 1:
        return [f"{pad}/** {body[0].strip()[3:].strip()} */"]
    return [f"{pad}/**"] + body + [f"{pad} */"]


def ts_type(spec: dict) -> str:
    t = spec["type"]
    if spec.get("list"):
        t = f"{t}[]" if " " not in t else f"({t})[]"
    if spec.get("nullable"):
        t = f"{t} | null"
    return t


def emit(contract: dict) -> str:
    out: list[str] = []
    out.append("// GENERATED FILE — DO NOT EDIT.")
    out.append("//")
    out.append(f"// Source: vendling-api/contracts/adapter-a6.json (version {contract['version']})")
    out.append("// Regenerate: python3 scripts/gen_adapter_types.py --write <path>")
    out.append("//")
    out += [f"// {line.strip()[3:].strip()}" for line in wrap(contract["description"], " *  ")]
    out.append("")

    for name, spec in contract["types"].items():
        out += doc_block(spec.get("doc"))
        if "enum" in spec:
            members = " | ".join(f'"{v}"' for v in spec["enum"])
            out.append(f"export type {name} = {members};")
            out.append("")
            continue
        out.append(f"export interface {name} {{")
        for field, fspec in spec["fields"].items():
            out += doc_block(fspec.get("doc"), "  ")
            opt = "?" if fspec.get("optional") else ""
            out.append(f"  {field}{opt}: {ts_type(fspec)};")
        out.append("}")
        out.append("")

    for name, spec in contract["unions"].items():
        out += doc_block(spec.get("doc"))
        variants = []
        for v in spec["variants"]:
            fields = " ".join(f"{k}: {t};" for k, t in v["fields"].items())
            variants.append(f'  | {{ method: "{v["method"]}"; {fields} }}')
        out.append(f"export type {name} =")
        out.append("\n".join(variants) + ";")
        out.append("")

    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", nargs="*", type=pathlib.Path, default=[])
    args = ap.parse_args()

    contract = json.loads(CONTRACT.read_text())
    generated = emit(contract)
    digest = hashlib.sha256(generated.encode()).hexdigest()[:16]

    targets = args.write or []
    if args.check:
        if not targets:
            print("--check needs at least one path", file=sys.stderr)
            return 2
        bad = []
        for t in targets:
            if not t.exists() or t.read_text() != generated:
                bad.append(str(t))
        if bad:
            print("out of date or hand-edited:\n  " + "\n  ".join(bad), file=sys.stderr)
            print(f"\nrun: python3 scripts/gen_adapter_types.py --write {' '.join(bad)}", file=sys.stderr)
            return 1
        print(f"ok ({len(targets)} file(s), sha256:{digest})")
        return 0

    for t in targets:
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(generated)
        print(f"wrote {t} ({len(generated.splitlines())} lines, sha256:{digest})")
    if not targets:
        sys.stdout.write(generated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
