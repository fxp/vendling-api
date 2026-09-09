#!/usr/bin/env python3
"""Build https://vendling.dev from this repo.

  python3 scripts/build.py                       → dist/   the portal: home + /api/
  python3 scripts/build.py --mirror --out DIR    → DIR     the /api/ pages only, with relative links,
                                                           for a mirror under another host
  python3 scripts/build.py --project-docs PATH   also render PATH's README.md + docs/*.md under
                                                 /docs/ (PATH = a local vendling-core checkout;
                                                 maintainer-only, that repo is private)

Canonical URLs always point at vendling.dev. Requires python-markdown. No network.
"""
from __future__ import annotations

import argparse
import html
import re
import shutil
import zipfile
from datetime import date
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "spec" / "commerce-api.md"
OPENAPI = ROOT / "openapi" / "vendling-commerce.openapi.yaml"
SKILL = ROOT / "skill" / "vendling-commerce-api"
AGENT_SETUP = ROOT / "agent-setup" / "prompt.md"

SCALAR_VERSION = "1.68.0"  # pinned; bump deliberately
CANONICAL = "https://vendling.dev/"
API_BASE = CANONICAL + "api/"
DOCS_REPO = "https://github.com/fxp/vendling-api"
CORE_REPO = "https://github.com/fxp/vendling-core"  # private
BUILT = date.today().isoformat()

# Rendered under /docs/<slug>/ only with --project-docs (paths relative to that checkout).
PROJECT_DOCS: list[tuple[str, str, str]] = [
    ("readme", "README.md", "项目总览：四个循环、护栏、推理、记忆、运行方式"),
    ("routes", "docs/api.md", "按场景组织的现有路由清单（旧接口面）"),
    ("event-system", "docs/event-system.md", "事件系统接入指南：Event 与 Decision 的区别、写入、实时流"),
    ("face-split", "docs/face-split.md", "顾客界面拆成独立 Worker 的原因、桥接契约与安全边界"),
    ("scenarios", "docs/scenarios.md", "按场景运营：两台真机 14 天真实数据得出的结论"),
    ("agent-framework-requirements", "docs/agent-framework-requirements.md", "Agent 框架需求与架构决策汇总"),
    ("face-data-interfaces", "docs/face/DATA-INTERFACES.md", "顾客界面的数据接口"),
    ("face-persona", "docs/face/VM-07-persona.md", "顾客界面人格设定 VM-07"),
    ("face-devlog", "docs/face/DEVLOG.md", "顾客界面开发日志"),
]

CSS = """
:root{--bg:#fbfaf7;--fg:#1c1b18;--fg-dim:#4a4741;--fg-mute:#8a857b;--line:#e6e1d6;--code-bg:#f2efe7;--accent:#b8452b;--accent-soft:#f6e6e1;--side:#f5f2eb;--w:78ch}
@media(prefers-color-scheme:dark){:root{--bg:#0f0e0c;--fg:#ecebe6;--fg-dim:#bdb9b0;--fg-mute:#7f7b72;--line:#2a2823;--code-bg:#1a1916;--accent:#e2745a;--accent-soft:#2b1a15;--side:#141310}}
html[data-mode=dark]{--bg:#0f0e0c;--fg:#ecebe6;--fg-dim:#bdb9b0;--fg-mute:#7f7b72;--line:#2a2823;--code-bg:#1a1916;--accent:#e2745a;--accent-soft:#2b1a15;--side:#141310}
html[data-mode=light]{--bg:#fbfaf7;--fg:#1c1b18;--fg-dim:#4a4741;--fg-mute:#8a857b;--line:#e6e1d6;--code-bg:#f2efe7;--accent:#b8452b;--accent-soft:#f6e6e1;--side:#f5f2eb}
*{box-sizing:border-box}html,body{margin:0;padding:0}
body{background:var(--bg);color:var(--fg-dim);font:16px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Noto Sans SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.top{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.top-row{max-width:1320px;margin:0 auto;padding:10px 20px;display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.crumb{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--fg-mute)}
.crumb a{color:var(--fg-mute)}.crumb strong{color:var(--fg);font-weight:500}.crumb span{opacity:.5;margin:0 6px}
.tabs{display:flex;gap:4px;margin-left:auto;flex-wrap:wrap}
.tabs a{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;letter-spacing:.04em;padding:5px 10px;border:1px solid transparent;border-radius:6px;color:var(--fg-dim)}
.tabs a:hover{border-color:var(--line);text-decoration:none}.tabs a.on{background:var(--accent-soft);color:var(--accent);border-color:transparent}
.mode{font-family:ui-monospace,Menlo,monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--fg-mute);background:transparent;border:1px solid var(--line);padding:4px 9px;cursor:pointer;border-radius:6px}
.wrap{max-width:1320px;margin:0 auto;display:grid;grid-template-columns:280px minmax(0,1fr);gap:0}
.wrap.single{display:block}
aside{position:sticky;top:49px;align-self:start;max-height:calc(100vh - 49px);overflow:auto;padding:22px 16px 40px 20px;border-right:1px solid var(--line);background:var(--side);font-size:13px;line-height:1.5}
aside .toc>ul{list-style:none;margin:0;padding:0}aside .toc ul ul{list-style:none;margin:2px 0 6px 12px;padding:0;border-left:1px solid var(--line)}
aside .toc li{margin:0}aside .toc a{display:block;color:var(--fg-dim);padding:3px 8px;border-radius:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
aside .toc>ul>li>a{font-weight:600;color:var(--fg);margin-top:8px}aside .toc a:hover{background:var(--accent-soft);text-decoration:none}aside .toc a.here{color:var(--accent)}
aside .toc ul ul ul{display:none}
main{padding:28px 44px 90px;min-width:0}
article{max-width:var(--w)}
article.wide{max-width:none}
h1{font-size:34px;line-height:1.2;letter-spacing:-.01em;color:var(--fg);margin:8px 0 12px;font-weight:650}
h2{font-size:24px;color:var(--fg);margin:56px 0 12px;padding-top:14px;border-top:1px solid var(--line);font-weight:650;scroll-margin-top:70px}
h3{font-size:18px;color:var(--fg);margin:34px 0 8px;font-weight:650;scroll-margin-top:70px}
h4{font-size:15px;color:var(--fg);margin:24px 0 6px;font-weight:650}
p{margin:10px 0}li{margin:3px 0}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.86em;background:var(--code-bg);padding:1px 5px;border-radius:4px;color:var(--fg)}
pre{background:var(--code-bg);border:1px solid var(--line);border-radius:8px;padding:14px 16px;overflow:auto;font-size:13px;line-height:1.55;margin:12px 0}
pre code{background:none;padding:0;font-size:inherit;color:var(--fg)}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px;display:block;overflow-x:auto;max-width:100%}
th,td{border:1px solid var(--line);padding:7px 10px;vertical-align:top;text-align:left;line-height:1.5}th{background:var(--side);color:var(--fg);font-weight:600;white-space:nowrap}
tr:nth-child(even) td{background:color-mix(in srgb,var(--side) 55%,transparent)}
blockquote{border-left:3px solid var(--accent);background:var(--accent-soft);margin:14px 0;padding:8px 16px;border-radius:0 8px 8px 0;color:var(--fg-dim)}blockquote p{margin:6px 0}
hr{border:0;border-top:1px solid var(--line);margin:32px 0}
strong{color:var(--fg)}
img{max-width:100%;height:auto}
.meta{font-family:ui-monospace,Menlo,monospace;font-size:11px;letter-spacing:.1em;color:var(--fg-mute);text-transform:uppercase;margin-bottom:6px}
.foot{margin-top:70px;border-top:1px solid var(--line);padding:22px 0 0;font-family:ui-monospace,Menlo,monospace;font-size:11px;letter-spacing:.08em;color:var(--fg-mute)}
.dl{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}
.dl a{border:1px solid var(--line);border-radius:8px;padding:8px 12px;font-size:13px;color:var(--fg)}
.dl a:hover{border-color:var(--accent);text-decoration:none;color:var(--accent)}
.headerlink{opacity:0;margin-left:6px;font-weight:400;color:var(--fg-mute)}h2:hover .headerlink,h3:hover .headerlink{opacity:1}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;margin:18px 0 8px}
.card{display:block;border:1px solid var(--line);border-radius:10px;padding:16px 18px;color:var(--fg-dim);background:var(--side)}
.card:hover{border-color:var(--accent);text-decoration:none}.card b{display:block;color:var(--fg);font-size:16px;margin-bottom:4px}.card small{color:var(--fg-mute)}
.hero{padding:40px 0 10px}.hero h1{font-size:44px;margin:0 0 10px}.hero p{font-size:18px;max-width:70ch}
.doclist{list-style:none;padding:0;margin:8px 0 0}.doclist li{border-bottom:1px solid var(--line);padding:12px 0}.doclist li a{font-weight:600;color:var(--fg)}.doclist li small{display:block;color:var(--fg-mute)}
@media(max-width:900px){.wrap{grid-template-columns:1fr}aside{position:static;max-height:none;border-right:0;border-bottom:1px solid var(--line)}main{padding:20px 18px 60px}h1{font-size:28px}.hero h1{font-size:32px}}
"""

MODE_JS = """
(function(){var k='vendling.docs.mode',h=document.documentElement,b=document.querySelector('[data-mode]');
function cur(){return h.getAttribute('data-mode')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light')}
function set(m){h.setAttribute('data-mode',m);localStorage.setItem(k,m);if(b)b.textContent=m==='dark'?'◐ 浅色':'◑ 暗色'}
var s=localStorage.getItem(k);if(s)set(s);else if(b)b.textContent=cur()==='dark'?'◐ 浅色':'◑ 暗色';
if(b)b.addEventListener('click',function(){set(cur()==='dark'?'light':'dark')});
var links=[].slice.call(document.querySelectorAll('aside .toc a'));var heads=links.map(function(a){return document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1)))}).filter(Boolean);
function mark(){var y=window.scrollY+90,best=null;heads.forEach(function(el){if(el.offsetTop<=y)best=el});links.forEach(function(a){a.classList.toggle('here',!!best&&decodeURIComponent(a.getAttribute('href').slice(1))===best.id)});
var on=document.querySelector('aside .toc a.here');if(on){var r=on.getBoundingClientRect(),s=on.closest('aside');if(r.top<60||r.bottom>innerHeight-40)on.scrollIntoView({block:'center'})}}
addEventListener('scroll',mark,{passive:true});mark();})();
"""


def slugify(value: str, separator: str) -> str:
    """GitHub-style slugs so the markdown's own #anchors keep working."""
    value = value.strip().lower()
    value = re.sub(r"[`*]", "", value)
    value = re.sub(r"[^\w\s一-鿿-]", "", value)
    return re.sub(r"\s", separator, value)


class Site:
    """portal = vendling.dev (absolute paths, home, optional /docs/);
    mirror = the /api/ pages only, relative links, for another host."""

    def __init__(self, portal: bool, out: Path, with_docs: bool):
        self.portal = portal
        self.out = out
        self.with_docs = with_docs
        self.api_out = out / "api" if portal else out

    def api_href(self, rel: str, from_dir: str = "") -> str:
        if self.portal:
            return "/api/" + rel
        prefix = "../" if from_dir else ""
        return prefix + rel if rel else (prefix or "./")

    def crumbs(self, section: str) -> str:
        if self.portal:
            return '<a href="/">Vendling</a><span>/</span><a href="/">Developers</a><span>/</span><strong>%s</strong>' % html.escape(section)
        return '<a href="/">小平的IO</a><span>/</span><a href="/apps/">Apps</a><span>/</span><a href="/apps/vendling/">Vendling</a><span>/</span><strong>%s</strong>' % html.escape(section)


def head(site: Site, title: str, description: str, active: str, canonical: str, from_dir: str = "", extra_css: str = "", section: str = "API") -> str:
    tabs = [("", "指南 Guide", "index"), ("reference", "API Reference", "reference"), ("openapi.yaml", "OpenAPI", ""), ("llms.txt", "llms.txt", ""), ("skill/", "Agent Skill", "skill")]
    if site.portal:
        tabs = [("/", "首页", "home"), *[(site.api_href(rel), label, key) for rel, label, key in tabs]]
        if site.with_docs:
            tabs.append(("/docs/", "项目文档", "docs"))
    else:
        tabs = [(site.api_href(rel, from_dir), label, key) for rel, label, key in tabs]
    tab_html = "".join(f'<a href="{href}" class="{"on" if key == active and key else ""}">{label}</a>' for href, label, key in tabs)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="canonical" href="{canonical}">
<style>{CSS}{extra_css}</style>
</head>
<body>
<header class="top"><div class="top-row">
  <nav class="crumb" aria-label="面包屑">{site.crumbs(section)}</nav>
  <div class="tabs">{tab_html}</div>
  <button class="mode" data-mode aria-label="切换浅色/暗色">◑ 暗色</button>
</div></header>
"""


FOOT = f'<div class="foot">Vendling · 文档源码 <a href="{DOCS_REPO}" rel="noopener">vendling-api</a> · <a href="{CANONICAL}">vendling.dev</a> · 镜像 <a href="https://xiaopingfeng.com/apps/vendling/api/">xiaopingfeng.com</a> · fxp007 · 2026</div>'


def render_md(text: str, toc_depth: str = "2-3") -> tuple[str, str]:
    md = markdown.Markdown(
        extensions=["toc", "tables", "fenced_code", "attr_list", "sane_lists"],
        extension_configs={"toc": {"slugify": slugify, "toc_depth": toc_depth, "permalink": "#", "permalink_title": "链接到此节"}},
    )
    body = md.convert(text)
    return body, md.toc


# ── /api/ ────────────────────────────────────────────────────────────────

def build_guide(site: Site) -> str:
    src = MD.read_text(encoding="utf-8")
    src = src.replace(
        "[`openapi/vendling-commerce.openapi.yaml`](openapi/vendling-commerce.openapi.yaml)",
        "[`openapi.yaml`](openapi.yaml) · [API Reference](reference) · [Agent Skill](skill/)",
    )
    # The spec links to vendling-core's other docs by file name; that repo is private.
    for name in ("api.md", "event-system.md", "face-split.md", "scenarios.md"):
        target = {"api.md": "/docs/routes/", "event-system.md": "/docs/event-system/", "face-split.md": "/docs/face-split/", "scenarios.md": "/docs/scenarios/"}[name]
        src = src.replace(f"]({name})", f"]({target if site.with_docs else CORE_REPO + '/blob/main/docs/' + name})")
    body, toc = render_md(src)
    setup = (
        '<h2 id="agent-setup">Agent 一键接入<a class="headerlink" href="#agent-setup">#</a></h2>'
        "<p>把下面这句话发给你的 Agent（Claude Code、Codex、Cursor、Windsurf、OpenCode 等），它会自己装好 skill、配好 token、验证连接：</p>"
        f"<pre><code>Fetch and execute the appropriate instructions to set me up for Vendling from {API_BASE}agent-setup/prompt.md</code></pre>"
        '<p>做法参考 <a href="https://developers.cloudflare.com/agent-setup/" rel="noopener">Cloudflare 的 agent setup</a>：一个 Agent 可读的 <a href="agent-setup/prompt.md">prompt.md</a>，'
        "写明要执行的命令、要向用户索要的值（只有 operator token）、验证步骤和完成后的汇报格式。</p>"
    )
    downloads = (
        setup + '<div class="dl">'
        '<a href="openapi.yaml" download>⬇ openapi.yaml</a>'
        '<a href="commerce-api.md" download>⬇ commerce-api.md</a>'
        '<a href="llms-full.txt">llms-full.txt</a>'
        '<a href="skill/vendling-commerce-api.skill.zip" download>⬇ Agent Skill (zip)</a>'
        f'<a href="{DOCS_REPO}" rel="noopener">GitHub ↗</a>'
        "</div>"
    )
    page = head(
        site,
        "Vendling Commerce API · 标准接口文档（UCP 对齐）",
        "Vendling 售货机智能体的商品类接口规范：供应商 SKU 目录、机器库存、采购结账、订单、改价、补货、审批、事件。按 Google UCP 对齐，含友宝上游接口原始形态。",
        "index",
        API_BASE,
    )
    page += f"""<div class="wrap">
<aside><div class="meta">目录</div>{toc}</aside>
<main><article>
<div class="meta">Vendling · API · 构建 {BUILT}</div>
{body}
{downloads}
{FOOT}
</article></main>
</div>
<script>{MODE_JS}</script>
</body></html>"""
    return page


def build_reference(site: Site) -> str:
    page = head(
        site,
        "Vendling Commerce API · Reference (OpenAPI 3.1)",
        "Vendling Commerce API 的 OpenAPI 参考：每个端点的请求、响应、schema。",
        "reference",
        API_BASE + "reference",
        extra_css=".wrap{display:block}main{padding:0}#app{min-height:80vh}",
    )
    page += f"""<div class="wrap"><main>
<div id="app"></div>
</main></div>
<script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference@{SCALAR_VERSION}/dist/browser/standalone.js" crossorigin="anonymous"></script>
<script>
(function(){{
  var cfg = {{ url: './openapi.yaml', theme: 'kepler', hideDarkModeToggle: false, defaultOpenAllTags: false,
               metaData: {{ title: 'Vendling Commerce API' }} }};
  var mode = localStorage.getItem('vendling.docs.mode');
  if (mode) cfg.darkMode = mode === 'dark';
  if (window.Scalar && Scalar.createApiReference) Scalar.createApiReference('#app', cfg);
  else document.getElementById('app').innerHTML = '<p style="padding:40px">API reference failed to load. Open <a href="openapi.yaml">openapi.yaml</a> directly.</p>';
}})();
{MODE_JS}
</script>
</body></html>"""
    return page


def build_skill_index(site: Site, files: list[Path], skill_out: Path) -> str:
    skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", skill_md, re.S)
    body_md = skill_md[fm.end():] if fm else skill_md
    desc = ""
    if fm:
        m = re.search(r"description:\s*>\s*\n((?:\s{2,}.*\n)+)", fm.group(1))
        if m:
            desc = " ".join(line.strip() for line in m.group(1).splitlines())
    body, toc = render_md(body_md)
    listing = "".join(f'<li><a href="{f.relative_to(skill_out).as_posix()}">{f.relative_to(skill_out).as_posix()}</a></li>' for f in files)
    guide_href = "/api/" if site.portal else site.api_href("", "skill/")
    ref_href = "/api/reference" if site.portal else site.api_href("reference", "skill/")
    page = head(site, "Vendling Commerce API · Agent Skill", desc[:300], "skill", API_BASE + "skill/", from_dir="skill/")
    page += f"""<div class="wrap">
<aside><div class="meta">Skill</div>{toc}</aside>
<main><article>
<div class="meta">Claude Code / Agent Skill · vendling-commerce-api</div>
<h1>Agent Skill：vendling-commerce-api</h1>
<p>给其他 Agent 用的接入 skill。把整个目录放到 <code>~/.claude/skills/vendling-commerce-api/</code>（或你的 agent 框架的 skills 目录）即可；
触发描述见 <code>SKILL.md</code> 的 frontmatter。更省事的办法：把 <a href="{guide_href}#agent-setup">一键接入</a> 那句话发给 Agent。源码在 <a href="{DOCS_REPO}/tree/main/skill/vendling-commerce-api">vendling-api</a>。</p>
<div class="dl"><a href="vendling-commerce-api.skill.zip" download>⬇ 下载 zip</a><a href="SKILL.md">SKILL.md</a><a href="{guide_href}">← 指南</a><a href="{ref_href}">API Reference</a></div>
<p class="meta" style="margin-top:22px">文件</p>
<ul>{listing}</ul>
<blockquote><p>安装：<code>unzip vendling-commerce-api.skill.zip -d ~/.claude/skills/</code>，然后在会话里提到 Vendling / 售货机库存 / 补货 / vendling.xiaopingfeng.com 即可触发。</p></blockquote>
<hr>
<p class="meta">SKILL.md（原文）</p>
{body}
{FOOT}
</article></main></div>
<script>{MODE_JS}</script>
</body></html>"""
    return page


def build_api_llms() -> str:
    return f"""# Vendling Commerce API

> UCP-aligned commerce interface of vendling-core, the AI agent that runs a real vending
> route (two 友宝 machines in Beijing). Supplier SKU catalog, machine inventory, wholesale
> purchase checkout, sales ledger, live price changes, replenishment, approvals, events.
> Spec version 2026-09-09, aligned with UCP 2026-08-25. Amounts are integer CNY fen;
> ids are `<namespace>:<vendor_sku>` (namespaces: youbao-wholesale, youbao-vm, yuanqi).

Standard routes live at `https://vendling.xiaopingfeng.com/ucp/v1/*` once deployed; check
`GET https://vendling.xiaopingfeng.com/.well-known/ucp`. Legacy routes
(`/api/youbao/*`, `/agents/vendling-agent/route-01/*`) stay available. Everything is
behind `Authorization: Bearer <VENDLING_AUTH_TOKEN>`. Two actions spend real money or
change a live price and require the JSON boolean `confirm: true`. Staging (mock data, no
supplier credentials): `https://vendling-core-staging.fxp007.workers.dev`.

## Docs

- [Guide (Chinese, normative)]({API_BASE}): capabilities, entities, status machines, guardrails, upstream 友宝 contract (appendix A), legacy→standard route mapping (appendix B)
- [Full guide as markdown]({API_BASE}llms-full.txt)
- [OpenAPI 3.1]({API_BASE}openapi.yaml) · [rendered reference]({API_BASE}reference)

## Agent setup and skill

- [Agent setup prompt]({API_BASE}agent-setup/prompt.md): one instruction that installs the skill, configures the token and verifies the connection
- [SKILL.md]({API_BASE}skill/SKILL.md): how to integrate safely, with recipes
- [current-routes.md]({API_BASE}skill/references/current-routes.md): every legacy route with request/response fields
- [ucp-endpoints.md]({API_BASE}skill/references/ucp-endpoints.md): standard endpoints and the mapping
- [ids-and-units.md]({API_BASE}skill/references/ids-and-units.md): sku_id namespaces, sale units (EA/BX), aliases
- [errors.md]({API_BASE}skill/references/errors.md)
- [vendling_client.py]({API_BASE}skill/scripts/vendling_client.py): stdlib Python client + CLI, standard-first with legacy fallback
- [zip]({API_BASE}skill/vendling-commerce-api.skill.zip)

## Related

- [Portal index]({CANONICAL}llms.txt)
- [Docs source on GitHub]({DOCS_REPO})
- [UCP specification](https://ucp.dev/2026-08-25/specification/overview/)
- [Vendling project page](https://xiaopingfeng.com/apps/vendling/)
"""


def build_api(site: Site) -> None:
    out = site.api_out
    out.mkdir(parents=True, exist_ok=True)
    md_text = MD.read_text(encoding="utf-8")
    (out / "index.html").write_text(build_guide(site), encoding="utf-8")
    (out / "reference.html").write_text(build_reference(site), encoding="utf-8")
    shutil.copy(OPENAPI, out / "openapi.yaml")
    shutil.copy(MD, out / "commerce-api.md")
    (out / "llms.txt").write_text(build_api_llms(), encoding="utf-8")
    (out / "llms-full.txt").write_text(md_text, encoding="utf-8")
    (out / "agent-setup").mkdir(exist_ok=True)
    shutil.copy(AGENT_SETUP, out / "agent-setup" / "prompt.md")

    skill_out = out / "skill"
    shutil.copytree(SKILL, skill_out, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    files = sorted(p for p in skill_out.rglob("*") if p.is_file())
    zip_path = skill_out / "vendling-commerce-api.skill.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, arcname=f"vendling-commerce-api/{f.relative_to(skill_out).as_posix()}")
    (skill_out / "index.html").write_text(build_skill_index(site, files, skill_out), encoding="utf-8")


# ── /docs/ (optional, from a local vendling-core checkout) and home ───────

DOC_LINK_MAP = {
    "README.md": "/docs/readme/",
    "docs/api.md": "/docs/routes/", "api.md": "/docs/routes/",
    "docs/event-system.md": "/docs/event-system/", "event-system.md": "/docs/event-system/",
    "docs/face-split.md": "/docs/face-split/", "face-split.md": "/docs/face-split/",
    "docs/scenarios.md": "/docs/scenarios/", "scenarios.md": "/docs/scenarios/",
    "docs/agent-framework-requirements.md": "/docs/agent-framework-requirements/", "agent-framework-requirements.md": "/docs/agent-framework-requirements/",
    "docs/commerce-api.md": "/api/", "commerce-api.md": "/api/",
    "docs/face/DATA-INTERFACES.md": "/docs/face-data-interfaces/", "face/DATA-INTERFACES.md": "/docs/face-data-interfaces/", "DATA-INTERFACES.md": "/docs/face-data-interfaces/",
    "docs/face/VM-07-persona.md": "/docs/face-persona/", "face/VM-07-persona.md": "/docs/face-persona/", "VM-07-persona.md": "/docs/face-persona/",
    "docs/face/DEVLOG.md": "/docs/face-devlog/", "face/DEVLOG.md": "/docs/face-devlog/", "DEVLOG.md": "/docs/face-devlog/",
    "docs/architecture.html": "/docs/architecture.html", "architecture.html": "/docs/architecture.html",
}


def rewrite_doc_links(text: str, src_path: Path, core: Path) -> str:
    rel_dir = src_path.parent.relative_to(core).as_posix()

    def repl(m: re.Match) -> str:
        label, href = m.group(1), m.group(2)
        if href.startswith(("http://", "https://", "#", "mailto:")):
            return m.group(0)
        path, _, frag = href.partition("#")
        norm = path.lstrip("./")
        while norm.startswith("../"):
            norm = norm[3:]
        key = norm if norm in DOC_LINK_MAP else (f"{rel_dir}/{norm}" if rel_dir != "." else norm)
        if key in DOC_LINK_MAP or norm in DOC_LINK_MAP:
            target = DOC_LINK_MAP.get(key) or DOC_LINK_MAP[norm]
            return f"[{label}]({target}{'#' + frag if frag else ''})"
        repo_path = norm if rel_dir == "." or norm.startswith(("src/", "test/", "docs/", "skills/", "scripts/", "face-worker/", "public/")) else f"{rel_dir}/{norm}"
        return f"[{label}]({CORE_REPO}/blob/main/{repo_path}{'#' + frag if frag else ''})"

    return re.sub(r"\[([^\]]*)\]\(([^)\s]+)\)", repl, text)


def first_heading(text: str, fallback: str) -> str:
    m = re.search(r"^#\s+(.+)$", text, re.M)
    return re.sub(r"[`*]", "", m.group(1)).strip() if m else fallback


def build_docs(site: Site, core: Path) -> list[tuple[str, str, str]]:
    out = site.out
    entries: list[tuple[str, str, str]] = []
    for slug, rel, blurb in PROJECT_DOCS:
        src = core / rel
        if not src.exists():
            continue
        text = src.read_text(encoding="utf-8")
        title = first_heading(text, slug)
        entries.append((slug, title, blurb))
        body, toc = render_md(rewrite_doc_links(text, src, core))
        page = head(site, f"{title} · Vendling Developers", blurb, "docs", f"{CANONICAL}docs/{slug}/", section="Docs")
        page += f"""<div class="wrap">
<aside><div class="meta"><a href="/docs/">项目文档</a></div>{toc}</aside>
<main><article>
<div class="meta">{html.escape(rel)} · 构建 {BUILT}</div>
{body}
{FOOT}
</article></main>
</div>
<script>{MODE_JS}</script>
</body></html>"""
        d = out / "docs" / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(page, encoding="utf-8")
    arch = core / "docs" / "architecture.html"
    if arch.exists():
        text = arch.read_text(encoding="utf-8")
        for key, target in DOC_LINK_MAP.items():
            text = text.replace(f'href="{key}"', f'href="{target}"').replace(f'href="../{key}"', f'href="{target}"')
        (out / "docs").mkdir(parents=True, exist_ok=True)
        (out / "docs" / "architecture.html").write_text(text, encoding="utf-8")
    items = "".join(f'<li><a href="/docs/{s}/">{html.escape(t)}</a><small>{html.escape(b)}</small></li>' for s, t, b in entries)
    if arch.exists():
        items += '<li><a href="/docs/architecture.html">架构图</a><small>docs/architecture.html，交互式页面，原样提供</small></li>'
    page = head(site, "项目文档 · Vendling Developers", "vendling-core 仓库里的开发文档。", "docs", f"{CANONICAL}docs/", section="Docs")
    page += f"""<div class="wrap single"><main><article>
<div class="meta">Vendling · 项目文档 · 构建 {BUILT}</div>
<h1>项目文档</h1>
<p>vendling-core 仓库里的开发文档，按源文件渲染。接口相关的看 <a href="/api/">API 指南</a>。</p>
<ul class="doclist">{items}</ul>
{FOOT}
</article></main></div>
<script>{MODE_JS}</script>
</body></html>"""
    (out / "docs").mkdir(parents=True, exist_ok=True)
    (out / "docs" / "index.html").write_text(page, encoding="utf-8")
    return entries


def build_home(site: Site, entries: list[tuple[str, str, str]]) -> str:
    docs_card = '<a class="card" href="/docs/"><b>项目文档</b>README、事件系统、顾客界面拆分、场景运营、框架需求<small><br>vendling-core/docs/</small></a>' if site.with_docs else ""
    docs_section = ""
    if entries:
        docs = "".join(f'<li><a href="/docs/{slug}/">{html.escape(title)}</a><small>{html.escape(blurb)}</small></li>' for slug, title, blurb in entries[:5])
        docs_section = f'<h2 id="docs">项目文档</h2><ul class="doclist">{docs}</ul><p><a href="/docs/">全部文档 →</a></p>'
    page = head(site, "Vendling Developers", "Vendling 售货机智能体的开发者门户：UCP 对齐的商品类 API 规范与参考、Agent 接入 skill、一键接入。", "home", CANONICAL, section="Home")
    page += f"""<div class="wrap single"><main><article class="wide">
<div class="hero">
<div class="meta">vendling.dev · 构建 {BUILT}</div>
<h1>Vendling Developers</h1>
<p>Vendling 是一个自主经营真实售货机线路的 AI 智能体（北京，两台机器，生产运行中）。这里是给开发者和其他 Agent 的接入入口：按 Google UCP 对齐的商品类接口规范、OpenAPI 参考、接入 skill，以及一句话完成接入的 agent-setup。</p>
</div>
<div class="cards">
<a class="card" href="/api/"><b>API 指南</b>规范正文：目录、结账、订单、位置、改价、补货、审批、事件；友宝上游原始形态<small><br>spec/commerce-api.md</small></a>
<a class="card" href="/api/reference"><b>API Reference</b>OpenAPI 3.1，Scalar 渲染，每个端点的请求 / 响应 / schema<small><br>openapi.yaml</small></a>
<a class="card" href="/api/skill/"><b>Agent Skill</b>给 Claude Code 等 Agent 的接入 skill：ID 规则、安全规则、配方、Python 客户端<small><br>vendling-commerce-api</small></a>
<a class="card" href="/api/#agent-setup"><b>Agent 一键接入</b>一句话让 Agent 自己装好 skill、配好 token、验证连接<small><br>agent-setup/prompt.md</small></a>
{docs_card}
<a class="card" href="{DOCS_REPO}" rel="noopener"><b>文档源码 ↗</b>这个站的全部内容：规范、OpenAPI、skill、构建与部署<small><br>github.com/fxp/vendling-api</small></a>
</div>
<h2 id="quick">给 Agent 的三行</h2>
<pre><code>curl -s https://vendling.xiaopingfeng.com/.well-known/ucp        # 发现档案（标准路由部署后返回）
curl -s {CANONICAL}llms.txt                                # 全站索引
Fetch and execute the appropriate instructions to set me up for Vendling from {API_BASE}agent-setup/prompt.md</code></pre>
<h2 id="endpoints">部署地址</h2>
<table><thead><tr><th>环境</th><th>基址</th><th>说明</th></tr></thead><tbody>
<tr><td>生产</td><td><code>https://vendling.xiaopingfeng.com</code></td><td>真机、真钱；旧路由在线，标准路由 <code>/ucp/v1</code> 以 <code>/.well-known/ucp</code> 是否返回为准</td></tr>
<tr><td>Staging</td><td><code>https://vendling-core-staging.fxp007.workers.dev</code></td><td>mock 数据、无供应商凭证，标准路由已部署；token 向维护者索取</td></tr>
</tbody></table>
<p>API 由 <code>vendling-core</code>（Cloudflare Workers + Agents SDK，私有仓库）提供；本站只是文档。</p>
{docs_section}
{FOOT}
</article></main></div>
<script>{MODE_JS}</script>
</body></html>"""
    return page


def build_portal_llms(entries: list[tuple[str, str, str]]) -> str:
    docs = "\n".join(f"- [{title}]({CANONICAL}docs/{slug}/): {blurb}" for slug, title, blurb in entries)
    docs_block = f"\n## Project docs\n\n{docs}\n" if entries else ""
    return f"""# Vendling Developers

> Developer portal for the Vendling Commerce API — the UCP-aligned interface of an AI agent
> that runs a real vending route. Start with the API index below.

## API

- [API index]({API_BASE}llms.txt): guide, OpenAPI, skill, agent setup — read this first
- [Guide]({API_BASE}) · [full markdown]({API_BASE}llms-full.txt) · [OpenAPI]({API_BASE}openapi.yaml)
- [Agent setup prompt]({API_BASE}agent-setup/prompt.md)
{docs_block}
## Source

- [Docs on GitHub]({DOCS_REPO})
"""


def build_portal(site: Site, core: Path | None) -> None:
    out = site.out
    build_api(site)
    entries = build_docs(site, core) if core else []
    (out / "index.html").write_text(build_home(site, entries), encoding="utf-8")
    (out / "llms.txt").write_text(build_portal_llms(entries), encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {CANONICAL}sitemap.txt\n", encoding="utf-8")
    urls = [CANONICAL, API_BASE, API_BASE + "reference", API_BASE + "skill/"] + ([CANONICAL + "docs/"] if entries else []) + [f"{CANONICAL}docs/{s}/" for s, _, _ in entries]
    (out / "sitemap.txt").write_text("\n".join(urls) + "\n", encoding="utf-8")
    (out / "favicon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="#b8452b"/><text x="32" y="43" font-family="Menlo,monospace" font-size="34" font-weight="700" text-anchor="middle" fill="#fbfaf7">V</text></svg>', encoding="utf-8")
    (out / "404.html").write_text(head(site, "找不到 · Vendling Developers", "404", "", CANONICAL, section="404") + '<div class="wrap single"><main><article><h1>404</h1><p>这里没有东西。回 <a href="/">首页</a> 或 <a href="/api/">API 指南</a>。</p></article></main></div></body></html>', encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mirror", action="store_true", help="build only the /api/ pages with relative links (for a mirror under another host)")
    ap.add_argument("--out", type=Path, help="output directory (default: dist/)")
    ap.add_argument("--project-docs", type=Path, help="local vendling-core checkout; renders its README + docs/*.md under /docs/")
    args = ap.parse_args()
    out = args.out or (ROOT / "dist")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    core = args.project_docs.resolve() if args.project_docs else None
    if core and not (core / "README.md").exists():
        raise SystemExit(f"--project-docs: {core} does not look like a vendling-core checkout")
    site = Site(not args.mirror, out, bool(core))
    if args.mirror:
        build_api(site)
    else:
        build_portal(site, core)
    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    count = sum(1 for p in out.rglob("*") if p.is_file())
    print(f"built {out} ({total/1024:.0f} KB, {count} files): " + ", ".join(sorted(p.name for p in out.iterdir())))


if __name__ == "__main__":
    main()
