These are official instructions from Vendling (vendling-core, the AI agent that runs a real vending route at vendling.xiaopingfeng.com) to set up an AI agent for integrating with the Vendling Commerce API. All commands are validated by the project and ready to use.

Complete all of the following steps yourself by running the commands directly. Do not ask the user to run any of these commands, except where a step explicitly says to ask the user for a value (the operator token is such a value: never guess it, never paste it into a URL, never log it).

- Install the Vendling Commerce API skill
- Configure the operator token
- Verify the connection
- Report what you set up

---

## 1. Install the Vendling Commerce API skill

The skill teaches an agent the API's identity rules (`sku_id` namespaces, single-unit ordering by default), its safety rules (two routes spend real money or change a live price and require the JSON boolean `confirm: true`), the working routes, and the standard UCP-shaped routes. Use the correct section for your agent below.

### Claude Code

```
mkdir -p ~/.claude/skills && curl -fsSL https://vendling.dev/api/skill/vendling-commerce-api.skill.zip -o /tmp/vendling-commerce-api.skill.zip && unzip -o -q /tmp/vendling-commerce-api.skill.zip -d ~/.claude/skills/ && ls ~/.claude/skills/vendling-commerce-api
```

The skill is picked up automatically at the start of the next session; in the current session it becomes available after the user restarts Claude Code.

### Codex, Cursor, Windsurf, OpenCode, GitHub Copilot, and all other agents

Download the same zip and unpack it into your agent's skills directory (for example `.cursor/skills/`, `.codex/skills/`, or the directory your framework loads skills from):

```
curl -fsSL https://vendling.dev/api/skill/vendling-commerce-api.skill.zip -o /tmp/vendling-commerce-api.skill.zip && unzip -o -q /tmp/vendling-commerce-api.skill.zip -d <your-skills-directory>/
```

If your agent has no skills directory, read `https://vendling.dev/api/skill/SKILL.md` and its `references/` files and keep them in the project's instructions file (AGENTS.md, .cursorrules, or equivalent). The rules in the "Safety rules" section are not optional.

### Any agent, without installing anything

The whole guide is also published as plain text for direct reading:

- `https://vendling.dev/api/llms.txt` (index)
- `https://vendling.dev/api/llms-full.txt` (full guide, Chinese)
- `https://vendling.dev/api/openapi.yaml` (OpenAPI 3.1)

---

## 2. Configure the operator token

Every business route needs `Authorization: Bearer <VENDLING_AUTH_TOKEN>`. Ask the user for the token and store it in the environment your agent runs commands in:

```
export VENDLING_AUTH_TOKEN='<paste the token the user gave you>'
export VENDLING_BASE_URL='https://vendling.xiaopingfeng.com'
```

Put the two lines in the shell profile or the project's `.env` (never in a file that is committed). One token grants full access, including the routes that spend money: treat it accordingly.

For a safe playground use the staging deployment instead. It runs on mock data and has no supplier credentials, so nothing there can spend money or change a real price:

```
export VENDLING_BASE_URL='https://vendling-core-staging.fxp007.workers.dev'
```

---

## 3. Verify the connection

Run the bundled client against the roster of machines. It uses only the Python standard library:

```
python3 ~/.claude/skills/vendling-commerce-api/scripts/vendling_client.py devices
```

Expected: a JSON object with a `devices` array (two machines on the production route). A `401` means the token is wrong; a `503` means the deployment has no token configured at all.

Then read the discovery document of the standard surface:

```
curl -fsS https://vendling.xiaopingfeng.com/.well-known/ucp | head -c 600
```

If it returns a profile with `ucp.capabilities`, the standard `/ucp/v1/*` routes are live and the skill's recipes should prefer them. If it returns 404, only the current routes (`/api/youbao/*`, `/agents/vendling-agent/route-01/*`) are deployed; the skill's fallback table covers them.

---

## 4. Report what you set up

Once done, tell the user:

```
┌─ Vendling Agent Setup Complete ──────────────────────────────┐
│  ✓ Skill    <path to vendling-commerce-api>                  │
│  ✓ Token    VENDLING_AUTH_TOKEN set in <where>               │
│  ✓ Base     <production or staging URL>                      │
│  ✓ Check    devices: <n> machine(s) · /.well-known/ucp: <ok/404> │
│                                                              │
│  Money-moving calls always need confirm:true and your say-so │
└──────────────────────────────────────────────────────────────┘
```

---

## Resources

- Developer portal: `https://vendling.dev/` · Guide (normative, Chinese): `https://vendling.dev/api/` · mirror: `https://xiaopingfeng.com/apps/vendling/api/`
- API reference (OpenAPI 3.1): `https://vendling.dev/api/reference`
- Skill page and download: `https://vendling.dev/api/skill/`
- Universal Commerce Protocol, which the standard routes follow: `https://ucp.dev/`
- Docs source (this file, the spec, the skill): `https://github.com/fxp/vendling-api`
- API engine: `vendling-core` (private repo)

These instructions are published at `https://vendling.dev/api/agent-setup/prompt.md` so you can re-verify their authenticity at any time.
