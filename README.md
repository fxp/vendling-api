# vendling-api

Developer documentation for the **Vendling Commerce API** — the UCP-aligned interface of
[Vendling](https://xiaopingfeng.com/apps/vendling/), an AI agent that runs a real vending route.
Published at **https://vendling.dev**.

| What | Where |
|---|---|
| The spec (Chinese, normative): capabilities, entities, status machines, guardrails, the vendor-neutral adapter contract, capability × device matrix | [`spec/commerce-api.md`](spec/commerce-api.md) → https://vendling.dev/api/ |
| OpenAPI 3.1 | [`openapi/vendling-commerce.openapi.yaml`](openapi/vendling-commerce.openapi.yaml) → https://vendling.dev/api/reference |
| Agent skill (Claude Code / any agent): identity rules, safety rules, recipes, stdlib Python client | [`skill/vendling-commerce-api/`](skill/vendling-commerce-api/) → https://vendling.dev/api/skill/ |
| One-line agent setup, Cloudflare-style | [`agent-setup/prompt.md`](agent-setup/prompt.md) → https://vendling.dev/api/agent-setup/prompt.md |
| Agent-readable index | https://vendling.dev/llms.txt · https://vendling.dev/api/llms.txt |

The API itself is served by the (private) `vendling-core` repo at `https://vendling.xiaopingfeng.com`
(`/ucp/v1/*` + `/.well-known/ucp`). Machines and suppliers plug in through vendor adapters; the public docs
never name a vendor and use the placeholder `acme`. The standard surface follows the
[Universal Commerce Protocol](https://ucp.dev) `2026-08-25` with `com.xiaopingfeng.vendling.*` extensions.

## Set an agent up in one line

```
Fetch and execute the appropriate instructions to set me up for Vendling from https://vendling.dev/api/agent-setup/prompt.md
```

## Build and deploy

```bash
pip install markdown && npm ci
npm run build           # → dist/  (python3 scripts/build.py)
npm run deploy          # build + wrangler deploy → https://vendling.dev
npm run lint:openapi    # Redocly
```

CI (`.github/workflows/deploy.yml`) does the same on every push to `main`, using the
`CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` repository secrets.

`python3 scripts/build.py --mirror --out DIR` builds the API pages with relative links for a
mirror under another host (the copy at `xiaopingfeng.com/apps/vendling/api/`).
`--project-docs /path/to/vendling-core` additionally renders that repo's README and `docs/*.md`
under `/docs/` for a local, maintainer-only build.

## Layout

```
spec/commerce-api.md                 the normative spec
openapi/vendling-commerce.openapi.yaml
skill/vendling-commerce-api/         SKILL.md, references/, scripts/vendling_client.py
agent-setup/prompt.md
scripts/build.py                     markdown → static site (python-markdown; Scalar for the reference)
wrangler.jsonc                       assets-only Worker "vendling-dev", custom domains vendling.dev + www
```

License: Apache-2.0.
