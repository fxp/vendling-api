# Vendling Commerce API — 标准接口文档（UCP 对齐）

版本 `2026-09-10` · 对齐 [Universal Commerce Protocol](https://ucp.dev) 稳定版 `2026-08-25`
· 机器可读版：[`openapi.yaml`](openapi.yaml) · [API Reference](reference) · [Agent Skill](skill/)

这份文档定义 Vendling（自主经营售货机线路的 AI 智能体）对外的商品类接口：供货方的 SKU 目录与采购下单、
机器平台的库存 / 交易流水 / 改价 / 补货推荐，以及本系统自己的补货计划、审批、事件。UCP 有对应概念的地方
（目录、结账、订单、门店位置、履约）沿用 UCP 的字段名与状态机；UCP 没有覆盖的售货机运营语义以 UCP 允许的
**扩展**方式定义，不改动标准部分。

**本文只讲协议，不讲任何具体厂商。** 机器平台与供货方通过**适配器**接入（附录 A），每个适配器登记一个
命名空间；调用方在运行时从 `GET /ucp/v1/namespaces` 拿到实际存在的命名空间。文中示例统一用占位厂商
`acme`：`acme-supply` 是供货方，`acme-machine` 是机器平台。

标记约定：**[有]** 已实现（`/ucp/v1/*`）；**[缺]** 规范已定义、尚未实现。

---

## 0. 目录

1. [对齐原则](#1-对齐原则)
2. [角色与方向](#2-角色与方向)：§2.1 最小接入集（先看这个）
3. [通用约定](#3-通用约定)：信封、鉴权、头、金额、时间、SKU 命名空间、分页、错误
4. [发现档案 `/.well-known/ucp`](#4-发现档案-well-knownucp)
5. [目录 Catalog](#5-目录-catalog)：供货方 SKU 清单、机器库存、SKU 注册表
6. [位置 Location](#6-位置-location)：机器即门店
7. [结账 Checkout](#7-结账-checkout)：向供货方下采购单
8. [订单 Order](#8-订单-order)：采购单状态、机器交易流水
9. [扩展：定价 Pricing](#9-扩展定价-pricing)
10. [扩展：补货 Replenishment](#10-扩展补货-replenishment)
11. [扩展：审批 Approval](#11-扩展审批-approval)
12. [扩展：事件 Events 与订单 Webhook](#12-扩展事件-events-与订单-webhook)
13. [护栏与安全](#13-护栏与安全)
- 附录 A [设备与供货方适配器契约](#附录-a-设备与供货方适配器契约)
- 附录 B [能力 × 设备类型矩阵](#附录-b-能力--设备类型矩阵)

---

## 1. 对齐原则

| 维度 | UCP 的做法 | 本规范的做法 |
|---|---|---|
| 能力命名 | 反向域名 `{authority}.{service}.{capability}`，如 `dev.ucp.shopping.checkout` | 标准能力原样用 `dev.ucp.*`；本项目扩展用 `com.xiaopingfeng.vendling.*` |
| 版本 | 日期版本 `YYYY-MM-DD`，schema 自描述 | `ucp.version` = `2026-08-25`；扩展版本 `2026-09-10`；破坏性变更换日期 |
| 发现 | 商家在 `/.well-known/ucp` 发布档案；平台在 `UCP-Agent` 头里给出自己的档案 URL | 同上，见 §4；命名空间注册表也在档案里 |
| 响应信封 | 每个响应带 `ucp: {version, status, capabilities}`；错误走 `messages[]` | 同上，见 §3.1 |
| 金额 | 整数、货币最小单位、显式 `currency` | 全部用**分**、`"currency": "CNY"`；上游的任何单位在适配器里统一 |
| 字段命名 | `snake_case`，JSON Schema 2020-12 | 同上 |
| 传输 | REST 为核心 | REST；MCP 绑定由 Agent skill 的工具对应 |
| 目录 → 结账 → 订单 | 目录返回的 `variants[].id` 直接作为结账的 `line_items[].item.id` | 同上，且这个 ID 在所有接口里都是同一个 `sku_id`（§3.6） |
| 履约 | `dev.ucp.shopping.fulfillment`：`methods[]` 的 `shipping` / `pickup` | 供货方配送或自提；自提时段做成可选的 `options[]` |
| 销售单位 | `quantity_unit`（sale basis），缺省 `each` | 同一 SKU 可按个（`EA`，缺省）或按箱（`BX`）下单，箱规在 `sale_units[]` 里公布 |
| 人工介入 | `status: requires_escalation` + `continue_url`，`severity: requires_buyer_review` | 花钱 / 改价的人工审批用这一套表达，审批本身是扩展 §11 |

UCP 明确允许的扩展点，本规范都只用这些：`metadata` 对象、自定义 `fulfillment.methods[].type`、开放的
`fulfillment.events[].type` / `adjustments[].type`、自由的 `messages[].code`、`actions` 映射、
以 `extends` 声明的扩展能力、能力条目上的 `config`。

---

## 2. 角色与方向

UCP 只定义两个角色：**Platform**（消费能力的一方）和 **Business**（暴露能力的一方）。Vendling 同时扮演两个角色：

```
                ┌──────────── 上游：Vendling 是 Platform ──────────────┐
                │                                                       │
   供货方 <vendor>-supply   ◄── catalog / checkout / order status ──  Vendling
   （Business：卖货给我们）      §5.1          §7          §8.1            │
                                                                       │
   机器平台 <vendor>-machine ◄── inventory / ledger / prices / recommend ┤
   （Business：运营机器）        §5.2      §8.2     §9       §10.3        │
                                                                       │
                ┌──────────── 下游：Vendling 是 Business ─────────────┤
                │                                                       │
   运营者 / 其他 Agent / 顾客界面  ────────────────────────────────────►│
   （Platform）    §6 位置  §5 目录  §8 订单  §10 补货  §11 审批  §12 事件
```

上游不必讲 UCP：每个厂商一个**适配器**（附录 A），把它翻译成本规范的形状。下游调用方只看本规范，
永远不会碰到厂商自己的字段。

### 2.1 最小接入集（核心 API）

本规范一共 34 个操作，一条线路日常运转只依赖其中 13 个。它们要么是 Vendling 自己的定时循环每天在调的能力，
要么是仅有的两个会动真钱、改真价的动作。先接这些；其余的（Lookup、别名注册表、结账会话的查改撤、采购单状态、
行程的下单与收货、预测评分、补货推荐……）都是便利接口，按需再接。API Reference 里这 13 个操作带 **核心** 徽标。

| ★ | 操作 | 能力 | 为什么必需 | Vendling 自己怎么用 |
|---|---|---|---|---|
| ★ | `GET /.well-known/ucp` | §4 发现 | 一切从这里开始：版本、能力、命名空间 | 外部 Agent 的入口 |
| ★ | `GET /namespaces` | §5.4 SKU 注册表 | 不知道命名空间就拼不出 `sku_id` | 同上 |
| ★ | `POST /locations/search` | §6 位置 | 有哪些机器 | 仪表盘的机器名册 |
| ★ | `POST /catalog/search` | §5.1 / §5.2 目录 | `machine` 命名空间 = 机器里有什么、什么价；`supply` 命名空间 = 供货方卖什么、什么价 | 每小时同步读库存；每天刷新一次批发成本 |
| ★ | `GET /orders?kind=sale` | §8.2 订单 | 交易流水，需求测算的唯一数据源 | 每小时同步 + 每 5 分钟轮询订单事件 |
| ★ | `POST /locations/sync` | §6 位置 | 把库存和流水拉进线路状态，补货计划以此为准 | 每小时定时任务、仪表盘"同步"按钮 |
| ★ | `GET /replenishment/plan` | §10.1 补货 | 每个货道的日销量、余量天数、建议动作 | 每天一次的 curate + restock 循环 |
| ★ | `POST /checkout-sessions` → `POST …/complete` | §7 结账 | 唯一会向供货方花真钱的路径 | 运营者或 Agent 触发；定时循环不会自己下单 |
| ★ | `PUT /locations/{id}/prices` | §9 定价 | 唯一会改机器真实售价的路径 | 运营者或 Agent 触发；超价格上限转审批 |
| ★ | `GET /approvals` · `POST /approvals/{id}` | §11 审批 | 人在回路：超预算、超价格上限的动作停在这里 | 群聊里的审批卡片、仪表盘 |
| ★ | `GET /events` | §12 事件 | 每个决定、每笔交易、每次报错的审计线 | 仪表盘实时流、每周给店主的信 |

不在表里但值得知道的两点：`POST /events` 是顾客界面写"想要什么"意图的通道，属于内部桥接而非接入必需；
`POST /replenishment/runs/{id}/place` 今天只把行程交给模拟供货方，真实采购走 §7。

---

## 3. 通用约定

### 3.1 响应信封

```json
{
  "ucp": {
    "version": "2026-08-25",
    "status": "success",
    "capabilities": {
      "dev.ucp.shopping.catalog.search": [{ "version": "2026-08-25" }],
      "com.xiaopingfeng.vendling.inventory": [{ "version": "2026-09-10" }]
    }
  },
  "products": [ ... ]
}
```

`ucp.capabilities` 列出本响应实际启用的能力（含扩展），调用方据此知道哪些扩展字段有效。

### 3.2 鉴权

| 场景 | 方式 | 说明 |
|---|---|---|
| 调用本规范的任何端点 | `Authorization: Bearer <VENDLING_AUTH_TOKEN>` | UCP 允许 API key。一把 token 全权，没有按调用方的 scope |
| 平台自我标识 | `UCP-Agent: profile="https://<platform>/.well-known/ucp"` | UCP 要求平台每个请求都带；当前记录、不校验 |
| 上游厂商 | 适配器内部处理（签名、密钥） | 凭证只在部署环境里；没有凭证的部署（staging）结构上无法花钱 |

发送一个有意义的 `User-Agent`。Cloudflare 会对默认的 `Python-urllib` UA 返回 403（错误 1010），那不是鉴权失败。

### 3.3 请求头

| 头 | 必需 | 说明 |
|---|---|---|
| `Content-Type: application/json` | 写操作 | |
| `UCP-Agent` | 平台请求 | 见 §3.2 |
| `Idempotency-Key` | 写操作应带 | 结账 / 采购单用 checkout `id` 兼作供货方的订单参考号，天然幂等；其余写操作 **[缺]** 尚未实现幂等存储 |

### 3.4 金额 `Price` / `Total`

```json
{ "amount": 550, "currency": "CNY" }
{ "type": "subtotal", "amount": 6600 }
```

- `amount` 恒为**整数、分**。`Total.amount` 是有符号的，退款等调整为负数。
- `totals[]` 类型用到 `subtotal`、`fulfillment`（配送费）、`total`。
- **成本**只在可靠时给出：适配器若发现上游报的"成本"与售价相同，视为未知（`null`），下游一律标"估算"，不冒充。

### 3.5 时间

对外一律 RFC 3339 带时区偏移，如 `"2026-09-09T14:03:00+08:00"`。上游厂商的时间格式与时区由适配器换算；
位置的营业时间按 UCP 用本地民用时间 + `timezone: "Asia/Shanghai"`。

### 3.6 SKU 标识与命名空间

一件商品在**所有**接口里只有一个标识：`sku_id`。

```
sku_id = "<namespace>:<vendor_sku>"
namespace = "<vendor>-<role>"      role ∈ supply | machine
```

- `vendor`：适配器登记的厂商标识（`[a-z][a-z0-9]*`）。`role`：`supply` 供货方，`machine` 机器平台。
- `vendor_sku`：厂商自己的编号，**原样保留、不解析**（不能含冒号和空白）。
- 整串是唯一身份，按精确字符串比较。不同命名空间的两个 `sku_id` 永远不相等，哪怕物理上是同一件货；跨命名空间的"同一件货"靠 §5.4 的**别名**表达。
- 实际存在哪些命名空间由运行时给出：`GET /ucp/v1/namespaces`（§5.4）或 `/.well-known/ucp` 里 `com.xiaopingfeng.vendling.sku` 能力的 `config.namespaces`。每条带 `vendor`、`role`、`status`（`live` / `planned`）、`capabilities`。

三条硬规则：

1. **适配器只认自己的命名空间。** 把 `acme-supply:…` 传给机器侧接口返回 `400 namespace_mismatch`。
2. **一张采购单只能有一个供货方命名空间。** 一张 PO 只发给一个供货方。
3. **包装不进 ID。** 整箱还是单个是下单时的计量单位（§7.1 `quantity_unit`）。缺省按个。

其余标识符：

| 对象 | 格式 |
|---|---|
| 位置（机器）`Location.id` | 机器平台的机器编号 |
| 货道 `slot_id` | `<location>-<vendor_sku>`（机器平台没有货道概念时的替身） |
| 采购结账 / 采购单 `Checkout.id` = `Order.id` | `po_<yyyymmdd>_<seq>` 或调用方给定的 PO 号；供货方回的订单号放在 `Order.label` |
| 机器交易 `Order.id` | 机器平台的交易流水号 |
| 补货行程 `ReplenishmentRun.id` | `run-<epoch ms>` |
| 决策 / 审批 `Approval.id` | `dec-<epoch ms>-<n>` |
| 事件 `Event.id` | `evt-<epoch ms>-<n>` |

### 3.7 分页

游标分页：请求 `pagination: {cursor, limit}`，响应 `pagination: {cursor, has_next_page, total_count}`。`limit` 缺省 20。

### 3.8 错误模型

**协议层错误**用 HTTP 状态码 + 信封；**业务结果**按 UCP 约定用 HTTP `200` + `messages[]`，实体照常返回，
调用方**必须**先看 `messages` 再用数据。

```json
{
  "ucp": { "version": "2026-08-25", "status": "error" },
  "messages": [
    { "type": "error", "code": "kill_switch_engaged", "severity": "requires_buyer_review", "path": "$",
      "content": "kill switch is engaged — real writes are frozen" }
  ],
  "continue_url": "https://vendling.xiaopingfeng.com/"
}
```

| `code` | severity | HTTP | 触发 |
|---|---|---|---|
| `missing` / `invalid` | recoverable | 400 | 必填缺失 / 类型范围不对，`path` 指向字段 |
| `not_found` | unrecoverable | 404 | |
| `unauthorized` | unrecoverable | 401 | token 错误；或上游拒绝凭证 |
| `out_of_stock` / `item_unavailable` | recoverable | 200 | UCP 标准 |
| `request_too_large` | recoverable | 400 | 批量超过 50 个 ID |
| `namespace_mismatch` | recoverable | 400 | 结账里混了多个供货方；或把别的命名空间的 ID 传给了只认自己的接口 |
| `namespace_unsupported` | unrecoverable | 400 | 命名空间已登记但没有 live 适配器 |
| `unresolved_sku` | recoverable | 200 | 机内 SKU 没有已确认的可采购别名 |
| `hard_no_go` | unrecoverable | 200 | 行项目命中 `rules.hardNoGos`；会话停在 `incomplete` |
| `approval_rejected` / `expired` | unrecoverable | 200 | 会话变为 `canceled` |
| `confirmation_required` | requires_buyer_review | 400 | 花钱 / 改价请求没带字面量 `confirm: true` |
| `approval_required` | requires_buyer_review | 200 | 护栏生成了待审批决策，`actions` 里给出 id |
| `kill_switch_engaged` | requires_buyer_review | 409 | 紧急停机开着 |
| `guard_unverifiable` | unrecoverable | 503 | 读不到护栏规则，**拒绝**执行 |
| `supplier_rejected` / `upstream_unreachable` | unrecoverable | 502 | 上游拒绝或不可达，`content` 带原文 |
| `already_placed` / `already_delivered` / `simulation_disabled` | unrecoverable | 409 | |

警告（`type: "warning"`，不阻塞）：`price_estimated`（单价由箱价换算）、`location_unverified`（机器号在流水里从未出现）、
`history_truncated`、`hours_unknown`、`same_namespace`、`sync_problem`。程序只认 `code`。

---

## 4. 发现档案 `/.well-known/ucp`

**[有]** 公开、无需 token。`endpoint` 指向标准基址 `https://vendling.xiaopingfeng.com/ucp/v1`。
节选（完整档案以线上为准）：

```json
{
  "ucp": {
    "version": "2026-08-25",
    "services": {
      "dev.ucp.shopping": [{ "version": "2026-08-25", "transport": "rest", "endpoint": "https://vendling.xiaopingfeng.com/ucp/v1", "spec": "…", "schema": "…" }]
    },
    "capabilities": {
      "dev.ucp.shopping.catalog.search": [{ "version": "2026-08-25", "spec": "…", "schema": "…" }],
      "dev.ucp.shopping.checkout":       [{ "version": "2026-08-25", "spec": "…", "schema": "…" }],
      "dev.ucp.shopping.fulfillment":    [{ "version": "2026-08-25", "extends": "dev.ucp.shopping.checkout" }],
      "dev.ucp.shopping.order":          [{ "version": "2026-08-25" }],
      "dev.ucp.common.location.search":  [{ "version": "2026-08-25" }],
      "com.xiaopingfeng.vendling.sku": [{
        "version": "2026-09-10",
        "extends": ["dev.ucp.shopping.catalog.search", "dev.ucp.shopping.catalog.lookup", "dev.ucp.shopping.checkout", "dev.ucp.shopping.order"],
        "config": {
          "namespaces": [
            { "namespace": "acme-supply",  "vendor": "acme", "role": "supply",  "status": "live", "capabilities": ["dev.ucp.shopping.catalog.search", "dev.ucp.shopping.checkout", "dev.ucp.shopping.order"] },
            { "namespace": "acme-machine", "vendor": "acme", "role": "machine", "status": "live", "capabilities": ["com.xiaopingfeng.vendling.inventory", "com.xiaopingfeng.vendling.pricing", "com.xiaopingfeng.vendling.replenishment"] }
          ],
          "defaults": { "machine": "acme-machine", "supply": "acme-supply" }
        }
      }],
      "com.xiaopingfeng.vendling.inventory":     [{ "version": "2026-09-10", "extends": ["dev.ucp.shopping.catalog.search", "dev.ucp.shopping.catalog.lookup"] }],
      "com.xiaopingfeng.vendling.location":      [{ "version": "2026-09-10", "extends": ["dev.ucp.common.location.search", "dev.ucp.common.location.lookup"] }],
      "com.xiaopingfeng.vendling.approval":      [{ "version": "2026-09-10", "extends": "dev.ucp.shopping.checkout" }],
      "com.xiaopingfeng.vendling.order":         [{ "version": "2026-09-10", "extends": "dev.ucp.shopping.order" }],
      "com.xiaopingfeng.vendling.pricing":       [{ "version": "2026-09-10" }],
      "com.xiaopingfeng.vendling.replenishment": [{ "version": "2026-09-10" }],
      "com.xiaopingfeng.vendling.events":        [{ "version": "2026-09-10" }]
    },
    "payment_handlers": {
      "com.xiaopingfeng.vendling.on_account": [{ "id": "supplier_account", "version": "2026-09-10" }]
    }
  },
  "keys": []
}
```

`payment_handlers` 只有一个：**账户挂账**。采购按供货方账户记账，下单不经过支付凭证，所以结账的
`payment.instruments[]` 只有 `type: "on_account"`，没有 `credential`。`keys` 为空：现在不做 RFC 9421 签名。

---

## 5. 目录 Catalog

能力：`dev.ucp.shopping.catalog.search`、`dev.ucp.shopping.catalog.lookup`
· 扩展：`com.xiaopingfeng.vendling.inventory`（机器库存视图）、`com.xiaopingfeng.vendling.sku`（销售单位、别名、SKU 注册表）

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| Search Catalog | `POST` | `/catalog/search` | `filters.namespace` 选数据源；缺省是默认供货方 |
| Batch Lookup | `POST` | `/catalog/lookup` | 按 `sku_id` 批量取，最多 50 个，可跨命名空间 |
| Get Product | `POST` | `/catalog/product` | 单品全量详情 |
| 命名空间注册表（扩展） | `GET` | `/namespaces` | 运行时存在的命名空间与缺省值 |
| SKU 注册表（扩展） | `GET` / `POST` / `PUT` | `/skus/{sku_id}`、`/skus/resolve`、`/skus/{sku_id}/aliases` | 见 §5.4 |

同一套端点，`filters.namespace` 的**角色**决定查哪种源：

| 角色 | 回答的问题 | 附加条件 |
|---|---|---|
| `supply` | 供货方能卖给我们什么：SKU 清单、箱规、箱价 / 单价、供货方库存 | — |
| `machine` | 某台机器现在有什么：机内商品、零售价、余量 | 必须给 `filters.location` |

### 5.1 供货方 SKU 清单（`<vendor>-supply`）
<!-- profiles: supply -->

```http
POST /catalog/search
{ "query": "乌龙", "filters": { "namespace": "acme-supply", "categories": ["饮料"] }, "pagination": { "limit": 20 } }
```

一个供货方商品 = 一个 `Product` + 一个 `Variant`。**整箱 / 单个不是两个变体**，是同一个变体的两种销售单位
（`sale_units[]`），下单时用 `quantity_unit` 选。缺省单位是 `EA`（个）：按个下单是基础情况，按箱是可选项。

```json
{
  "ucp": { "version": "2026-08-25", "status": "success" },
  "products": [
    {
      "id": "acme-supply:10023",
      "title": "乌龙茶 500ml",
      "description": { "plain": "500ml*15瓶/箱" },
      "categories": [{ "value": "饮料", "taxonomy": "merchant" }],
      "price_range": { "min": { "amount": 380, "currency": "CNY" }, "max": { "amount": 380, "currency": "CNY" } },
      "variants": [
        {
          "id": "acme-supply:10023",
          "title": "乌龙茶 500ml",
          "price": { "amount": 380, "currency": "CNY" },
          "quantity_unit": { "unit": "EA", "display_text": "个", "increment": 1 },
          "sale_units": [
            { "unit": "EA", "display_text": "个", "increment": 1, "price": { "amount": 380, "currency": "CNY" }, "price_derived": true },
            { "unit": "BX", "display_text": "箱", "contains": 15, "increment": 1, "price": { "amount": 5700, "currency": "CNY" } }
          ],
          "unit_price": { "amount": 380, "currency": "CNY", "measure": { "value": 15, "unit": "EA" }, "reference": { "value": 1, "unit": "EA" } },
          "availability": { "available": true, "status": "in_stock" },
          "aliases": [],
          "metadata": { "vendor_sku": "10023", "spec": "500ml*15瓶/箱", "supplier_stock": 120 }
        }
      ],
      "metadata": { "sites": [{ "id": "site:2021", "address": "…" }] }
    }
  ],
  "pagination": { "has_next_page": false, "total_count": 1 }
}
```

`sale_units[]`（扩展）：

| 字段 | 说明 |
|---|---|
| `unit` | UN/ECE Rec 20 单位码：`EA` 个、`BX` 箱。与 UCP `quantity_unit.unit` 同一词表 |
| `contains` | 该单位含多少个 `EA`；`EA` 自身省略。适配器报 `packSize = 1` 时没有 `BX` |
| `increment` | 起订倍数，UCP 原字段 |
| `price` | 该单位一件的价格 |
| `price_derived` | 价格是换算出来的（适配器只拿到箱价时，单价 = 箱价 ÷ 箱规）。实际结算以供货方对账为准 |

`variants[].price` 恒为 **`EA` 单位的价格**，`quantity_unit` 恒为 `EA`：不认识 `sale_units` 的 UCP 标准客户端也能正确按个下单。
`metadata.sites[]` 是供货方的提货点（附录 A `SupplySite`），自提时用作目的地 ID。

### 5.2 机器库存（`<vendor>-machine`）— 扩展 `com.xiaopingfeng.vendling.inventory`
<!-- profiles: machine -->

```http
POST /catalog/search
{ "filters": { "namespace": "acme-machine", "location": "12345678" } }
```

```json
{
  "products": [
    {
      "id": "acme-machine:8837",
      "title": "红牛 250ml",
      "price_range": { "min": { "amount": 600, "currency": "CNY" }, "max": { "amount": 600, "currency": "CNY" } },
      "variants": [
        {
          "id": "acme-machine:8837",
          "sku": "6920202888883",
          "barcodes": [{ "type": "EAN", "value": "6920202888883" }],
          "title": "红牛 250ml",
          "price": { "amount": 600, "currency": "CNY" },
          "availability": { "available": true, "status": "in_stock" },
          "inventory": { "location": "12345678", "slot_id": "12345678-8837", "stock": 7, "capacity": null, "locked": false },
          "aliases": [{ "sku_id": "acme-supply:10088", "source": "manual", "confirmed_at": "2026-09-01T10:00:00+08:00" }]
        }
      ]
    }
  ]
}
```

| 字段 | 位置 | 说明 |
|---|---|---|
| `filters.namespace` | 请求 | 一个 `machine` 角色的命名空间 |
| `filters.location` | 请求 | 机器 ID，必填 |
| `variants[].inventory.slot_id` | 响应 | `<location>-<vendor_sku>` |
| `variants[].inventory.capacity` | 响应 | 货道容量。只有运营者现场数过或从历史最高库存推出时才有值，否则 `null`，不默认 |
| `variants[].inventory.locked` | 响应 | 运营者锁定的货道，选品循环不得触碰 |
| `variants[].aliases[]` | 响应 | 其他命名空间里的同一件货，见 §5.4。这是从"机器缺货"走到"向谁采购"的唯一桥 |

**已知陷阱**：有的机器平台对**不存在的机器号也返回成功**。适配层用账户级交易流水做交叉检查：一个在同步窗口内
没有任何流水的机器号会在 `messages[]` 里得到 `type: "warning"`、`code: "location_unverified"`。

### 5.3 Lookup

```http
POST /catalog/lookup
{ "ids": ["acme-supply:10023", "acme-machine:8837"], "filters": { "location": "12345678" } }
```

命名空间就在 ID 里，一次请求可以跨命名空间，按前缀分发（`machine` 角色的 ID 需要 `filters.location`）。
ID 去重；每个变体带 `inputs[]`（`exact` / `featured`）；超过 50 个 ID 返回 `400 request_too_large`。

### 5.4 命名空间与 SKU 注册表 — 扩展 `com.xiaopingfeng.vendling.sku`
<!-- profiles: supply,machine,adapter -->

```http
GET /namespaces
```

```json
{
  "namespaces": [
    { "namespace": "acme-supply",  "vendor": "acme", "role": "supply",  "status": "live",    "capabilities": ["…"] },
    { "namespace": "acme-machine", "vendor": "acme", "role": "machine", "status": "live",    "capabilities": ["…"] },
    { "namespace": "beta-supply",  "vendor": "beta", "role": "supply",  "status": "planned", "capabilities": [] }
  ],
  "defaults": { "machine": "acme-machine", "supply": "acme-supply" }
}
```

补货闭环要从"机器里 `acme-machine:8837` 快空了"走到"向 `acme-supply:10088` 采购"，这一步跨命名空间，靠别名：

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| 取一个 SKU | `GET` | `/skus/{sku_id}?location=` | 身份、条码、别名、可采购来源（含 `sale_units`） |
| 解析 | `POST` | `/skus/resolve` `{ids, to_namespace}` | 把一批 `sku_id` 解析到目标命名空间 |
| 记别名 | `PUT` | `/skus/{sku_id}/aliases` `{aliases:[{sku_id, source?}]}` | 人工确认两个号是同一件货 |

```json
{ "resolved": [{ "from": "acme-machine:8837", "to": "acme-supply:10088" }], "unresolved": ["acme-machine:9120"] }
```

别名规则：`source` ∈ `barcode`（两边都有 EAN 时自动建立）、`manual`（运营者确认）、`suggested`（按名称相似度提出）。
**只有 `barcode` 和 `manual` 参与下单**。别名是对称的。`unresolved` 不是错误，但带着未解析的行去 §10.2 下单会得到 `unresolved_sku`。

---

## 6. 位置 Location
<!-- profiles: machine -->

能力：`dev.ucp.common.location.search`、`dev.ucp.common.location.lookup` · 扩展：`com.xiaopingfeng.vendling.location`

UCP 的 Location 是"地图上找得到的实体"。一台售货机正是：有地址、有营业时段、可以按"这里现在有没有某件商品"筛选。

| 操作 | 方法 | 端点 |
|---|---|---|
| Search Locations | `POST` | `/locations/search` `{query?, filters:{items?:[{id}], amenities?, hours?}}` |
| Lookup Locations | `POST` | `/locations/lookup` `{ids}` |
| 注册 / 更新一台机器（扩展） | `PUT` | `/locations/{id}` `{name, profile?}` |
| 移除一台机器（扩展） | `DELETE` | `/locations/{id}` |
| 立即同步遥测（扩展） | `POST` | `/locations/sync` `{sales_window_days?}` |

```json
{
  "id": "12345678",
  "name": "某写字楼 11F",
  "address": { "street_address": "…", "extended_address": "11F 电梯厅", "address_locality": "北京市", "address_country": "CN" },
  "timezone": "Asia/Shanghai",
  "amenities": { "com.xiaopingfeng.vendling.qr_chat": { "description": "扫码可与机器对话、点单、报修" } },
  "online": true,
  "venue_name": "某写字楼11层",
  "venue_type": "office",
  "placement": "indoor",
  "profile_complete": true,
  "missing": []
}
```

- `hours[]` 未记录时**省略**：UCP 规定"缺 = 未知"而非"关门"；带 `filters.hours` 的搜索会附 `hours_unknown` 警告。
- `filters.items[]` 用 `machine` 角色的 `sku_id`，只返回该商品 `stock > 0` 的机器。按 UCP 语义这是临时性信号，不是保留。
- `PUT /locations/{id}` 注册后每小时自动同步；同步是整体替换机器 / 商品 / 货道 / 销售，但保留运营者的货道锁。`sales_window_days` 不得小于补货策略的观察期（21 天）。
- `DELETE` 清掉档案、周边信息、遥测；**保留**事件与对话历史。

---

## 7. 结账 Checkout
<!-- profiles: supply -->

能力：`dev.ucp.shopping.checkout` + `dev.ucp.shopping.fulfillment` · 扩展：`com.xiaopingfeng.vendling.approval`、`com.xiaopingfeng.vendling.sku`

这是"**下单进货**"：向一个供货方下一张真实的、花真钱的采购单。UCP 的结账会话模型把它拆成
"建单 → 补齐信息 → 审批 → 提交"几步，每一步都有明确状态，钱只在最后一步动。

| 操作 | 方法 | 端点 |
|---|---|---|
| Create Checkout | `POST` | `/checkout-sessions` |
| Get Checkout | `GET` | `/checkout-sessions/{id}` |
| Update Checkout | `PUT` | `/checkout-sessions/{id}` |
| Complete Checkout | `POST` | `/checkout-sessions/{id}/complete` |
| Cancel Checkout | `POST` | `/checkout-sessions/{id}/cancel` |

### 7.1 建单

```http
POST /checkout-sessions
Idempotency-Key: po_20260909_001
{
  "id": "po_20260909_001",
  "line_items": [
    { "item": { "id": "acme-supply:10023" }, "quantity": 2, "quantity_unit": { "unit": "BX" } },
    { "item": { "id": "acme-supply:10088" }, "quantity": 6 }
  ],
  "fulfillment": {
    "methods": [{ "type": "shipping", "line_item_ids": ["*"],
      "destinations": [{ "type": "shipping_address", "street_address": "…", "address_locality": "北京市", "address_country": "CN", "first_name": "张三", "phone_number": "13800000000" }] }]
  }
}
```

- `id` 可选。给了就用作 PO 号（兼作供货方的订单参考号），没给由服务端生成。
- `line_items[].item.id` 必须来自 **`supply` 角色**的命名空间。`machine` 角色的 ID 不能直接下单，先经 §5.4 `resolve`。
- **一张单一个命名空间**：所有行的前缀必须相同，否则 `400 namespace_mismatch`。会话的 `vendor` 由第一行决定，建单后不可变。
- **按个下单是缺省**：`quantity_unit` 省略即 `{ "unit": "EA" }`。要按箱写 `{ "unit": "BX" }`，`quantity` 是箱数。`unit` 必须在该变体的 `sale_units[]` 里，否则 `400 invalid`。
- 履约二选一：
  - `shipping`：目的地必须有 `street_address` + `first_name`（联系人）+ `phone_number`，缺一建单时返回 `missing`。
  - `pickup`：目的地由服务端从供货方的提货点枚举（`site:<id>`），平台用 `selected_destination_id` 选点、`groups[].selected_option_id` 选自提时段（服务端生成未来 7 天的时段选项）。

### 7.2 会话实体

```json
{
  "ucp": { "version": "2026-08-25", "status": "success",
           "payment_handlers": { "com.xiaopingfeng.vendling.on_account": [{ "id": "supplier_account", "version": "2026-09-10" }] } },
  "id": "po_20260909_001",
  "status": "requires_escalation",
  "currency": "CNY",
  "vendor": "acme-supply",
  "line_items": [
    { "id": "li_1", "item": { "id": "acme-supply:10023", "title": "乌龙茶 500ml", "price": 5700, "quantity_unit": { "unit": "BX", "display_text": "箱", "contains": 15 } },
      "quantity": 2, "totals": [{ "type": "subtotal", "amount": 11400 }, { "type": "total", "amount": 11400 }] },
    { "id": "li_2", "item": { "id": "acme-supply:10088", "title": "红牛 250ml", "price": 480, "quantity_unit": { "unit": "EA", "display_text": "个" } },
      "quantity": 6, "totals": [{ "type": "subtotal", "amount": 2880 }, { "type": "total", "amount": 2880 }] }
  ],
  "fulfillment": { "methods": [{ "id": "fm_shipping", "type": "shipping", "line_item_ids": ["li_1", "li_2"],
    "destinations": [{ "type": "shipping_address", "id": "dest_1", "street_address": "…", "first_name": "张三", "phone_number": "138…" }],
    "selected_destination_id": "dest_1",
    "groups": [{ "id": "grp_1", "line_item_ids": ["li_1", "li_2"], "options": [{ "id": "opt_std", "title": "供货方配送", "totals": [{ "type": "total", "amount": 0 }] }], "selected_option_id": "opt_std" }] }] },
  "totals": [{ "type": "subtotal", "amount": 14280 }, { "type": "fulfillment", "amount": 0 }, { "type": "total", "amount": 14280 }],
  "payment": { "instruments": [{ "id": "instr_account", "handler_id": "supplier_account", "type": "on_account", "selected": true, "display": { "account": "on file" } }] },
  "messages": [
    { "type": "warning", "code": "price_estimated", "path": "$.line_items[1]", "content": "单价由箱价换算，实际以供货方对账为准" },
    { "type": "error", "code": "approval_required", "severity": "requires_buyer_review", "path": "$", "content": "estimated cost 142.80 exceeds run budget 100.00 — needs owner approval" }
  ],
  "actions": { "com.xiaopingfeng.vendling.approval": [{ "id": "dec-1757400000000-3" }] },
  "links": [{ "type": "documentation", "url": "https://vendling.dev/api/" }],
  "continue_url": "https://vendling.xiaopingfeng.com/tasks",
  "expires_at": "2026-09-10T14:03:00+08:00"
}
```

- `item.price` 是**所选单位**一件的价格（箱行是箱价，个行是单价），行 `totals` = `price × quantity`。
- 服务端回显 `item.quantity_unit`（UCP 要求非 `each` 的行必须带），并补上 `display_text` / `contains`。
- 按个下单的行会附 `price_estimated` 警告（供货方只公布箱价时，单价是换算的）。

### 7.3 状态机

| `status` | 含义 | 进入条件 | 出去 |
|---|---|---|---|
| `incomplete` | 信息不全 | 缺联系人 / 地址 / 自提时段；某行命中 `hardNoGos`（`hard_no_go`，永远过不去） | `PUT` 补齐 |
| `requires_escalation` | 要人批 | 预估金额 > `rules.spendingLimitPerRun`，或处于试用期 `probationUntil` | 运营者在 `continue_url` 或 §11 审批；批准 → `ready_for_complete`，驳回 → `canceled` |
| `ready_for_complete` | 可以提交 | 信息齐、护栏过（或已批） | `POST …/complete` |
| `complete_in_progress` | 已提交，等供货方 | 上游请求已发出、未回 | 由服务端推进 |
| `completed` | 已下单 | 供货方接单，返回订单号 | 终态；`order` 字段出现 |
| `canceled` | 作废 | 主动取消、审批驳回、`expires_at` 过期（24 小时） | 终态 |

**紧急停机**（`rules.killSwitchEngaged`）不是一个状态：任何时候 `complete` 都会被拒（`409 kill_switch_engaged`），会话本身不动。
读不到规则时 `503 guard_unverifiable`，**拒绝而非放行**。

### 7.4 提交

```http
POST /checkout-sessions/po_20260909_001/complete
{ "payment": { "instruments": [{ "id": "instr_account", "handler_id": "supplier_account", "type": "on_account" }] }, "confirm": true }
```

- `confirm` 是扩展字段，**必须是 JSON 布尔 `true`**。字符串 `"true"`、数字 `1` 一律 `400 confirmation_required`。
- 成功：`status: "completed"`，并带 `order: { "id": "po_…", "label": "<供货方订单号>", "permalink_url": "…/orders/po_…" }`。
- 供货方拒单：`502` + `supplier_rejected`，`status` 回到 `ready_for_complete`，`content` 带上游原文。重复提交已完成的会话返回同一个 `order`，不会再下一单。
- 每次提交无论成败都写一条事件到 §12 的事件流。花真钱的调用不能是黑箱。

### 7.5 会话 → 适配器

服务端把会话翻译成附录 A 的 `createOrder(ref, lines, fulfillment)`：`ref` = 会话 `id`；每行 `{vendor_sku, quantity, unit: "each" | "pack"}`
（`BX` → `pack`）；`fulfillment` 是 `{method:"shipping", contactName, contactPhone, address}` 或 `{method:"pickup", pickupAt, siteId?}`。
厂商自己的字段名不出现在本规范里。

---

## 8. 订单 Order

能力：`dev.ucp.shopping.order` · 扩展：`com.xiaopingfeng.vendling.order`（列表查询、位置 / 交易状态字段）

两类订单，同一个实体形状，用 `kind` 区分：

| `kind` | 谁是 Business | 数据来源 | ID |
|---|---|---|---|
| `purchase`（采购单） | 供货方 | 适配器 `orderStatus()` | PO 号（§7） |
| `sale`（机器交易） | 本系统 / 机器 | 适配器 `ledger()` | 机器平台的流水号 |

| 操作 | 方法 | 端点 |
|---|---|---|
| Get Order | `GET` | `/orders/{id}` |
| List Orders（扩展） | `GET` | `/orders?kind=sale&location=&from=&to=&trade_status=&cursor=&limit=` |
| Order Event Webhook | `POST` | 平台提供的 URL — **[缺]**，见 §12 |

### 8.1 采购单（`kind: purchase`）
<!-- profiles: supply -->

```json
{
  "id": "po_20260909_001",
  "label": "SUP-2026090912345",
  "kind": "purchase",
  "checkout_id": "po_20260909_001",
  "permalink_url": "https://vendling.xiaopingfeng.com/ucp/v1/orders/po_20260909_001",
  "currency": "CNY",
  "line_items": [
    { "id": "li_1", "item": { "id": "acme-supply:10023", "title": "…", "price": 5700, "quantity_unit": { "unit": "BX", "contains": 15 } },
      "quantity": { "original": 2, "total": 2, "fulfilled": 0 },
      "totals": [{ "type": "subtotal", "amount": 11400 }, { "type": "total", "amount": 11400 }], "status": "processing" }
  ],
  "fulfillment": {
    "expectations": [{ "id": "exp_1", "line_items": [{ "id": "li_1", "quantity": 2 }], "method_type": "shipping", "destination": { "street_address": "…", "address_country": "CN" }, "description": "待发货" }],
    "events": [{ "id": "fe_placed", "occurred_at": "2026-09-09T14:05:00+08:00", "type": "processing", "line_items": [{ "id": "li_1", "quantity": 2 }], "description": "已接单" }]
  },
  "adjustments": [],
  "totals": [{ "type": "subtotal", "amount": 14280 }, { "type": "fulfillment", "amount": 0 }, { "type": "total", "amount": 14280 }],
  "supplier_status": { "code": 2, "description": "待发货", "mapped": "ordered" },
  "logistics": []
}
```

适配器把供货方的状态归一为三态，UCP 视图由此推导：

| 适配器 `state` | 行 `status` | 追加的 `fulfillment.events[].type` |
|---|---|---|
| `ordered` | `processing` | `processing` |
| `arrived` | `fulfilled`（`fulfilled = total`） | `delivered` |
| `cancelled` | `removed`（`total = 0`） | `canceled`，并加 `adjustments[{type:"cancellation"}]` |

`supplier_status`（原始码 + 描述）和 `logistics[]`（原样透传）是扩展字段，供排障用。

### 8.2 机器交易（`kind: sale`）
<!-- profiles: machine -->

```http
GET /orders?kind=sale&location=12345678&from=2026-09-09T00:00:00%2B08:00&to=2026-09-09T23:59:59%2B08:00&limit=100
```

```json
{
  "orders": [
    {
      "id": "2026090913001234",
      "kind": "sale",
      "checkout_id": "2026090913001234",
      "permalink_url": "…/orders/2026090913001234",
      "currency": "CNY",
      "line_items": [
        { "id": "2026090913001234-8837", "item": { "id": "acme-machine:8837", "title": "红牛 250ml", "price": 600 },
          "quantity": { "original": 1, "total": 1, "fulfilled": 1 },
          "totals": [{ "type": "subtotal", "amount": 600 }, { "type": "total", "amount": 600 }], "status": "fulfilled" }
      ],
      "fulfillment": {
        "expectations": [{ "id": "exp_1", "line_items": [{ "id": "2026090913001234-8837", "quantity": 1 }], "method_type": "vending_dispense",
          "destination": { "extended_address": "某写字楼11层", "address_country": "CN" }, "description": "机器即时出货" }],
        "events": [{ "id": "fe_1", "occurred_at": "2026-09-09T13:00:12+08:00", "type": "dispensed", "line_items": [{ "id": "2026090913001234-8837", "quantity": 1 }] }]
      },
      "adjustments": [],
      "totals": [{ "type": "subtotal", "amount": 600 }, { "type": "total", "amount": 600 }],
      "location": "12345678",
      "location_name": "某写字楼11层",
      "trade_status": "SETTLED"
    }
  ],
  "pagination": { "cursor": "eyJwYWdlIjoyfQ", "has_next_page": true }
}
```

适配器把每条流水行归一为五种状态，UCP 视图由此推导：

| 适配器行 `status` | 行 `status` | `quantity` | `adjustments[]` |
|---|---|---|---|
| `paid` | `fulfilled` | `{1,1,1}` | — |
| `unpaid` | `processing` | `{1,1,0}` | — |
| `refunded` | `removed` | `{1,0,0}` | `{ type: "refund", status: "completed", totals: [{type:"total", amount: -price}] }` |
| `refund_failed` | `fulfilled` | `{1,1,1}` | `{ type: "refund", status: "failed" }` |
| `cancelled` | `removed` | `{1,0,0}` | `{ type: "cancellation", status: "completed" }` |

- **只有 `paid` 行进入销售统计**。列表缺省只取已结算交易（`trade_status=settled`），传 `trade_status=all` 取全部。
- 流水是**账户级**的：`location` 参数是服务端在全量结果上做的筛选，多机器线路上要跨机器完整翻页（上限 20 页，超过带 `history_truncated` 警告）。
- `trade_status` / `trade_status_label` 是机器平台的原始状态，扩展字段，供排障用。

---

## 9. 扩展：定价 Pricing
<!-- profiles: machine -->

能力：`com.xiaopingfeng.vendling.pricing`

改的是**真实机器上顾客看到的价格**。UCP 没有"商家改自己售价"的能力，所以这是纯扩展，但复用 UCP 的
`Price` 类型、`messages[]` 错误模型和 `requires_buyer_review` 审批语义。

```http
PUT /locations/12345678/prices
{ "prices": [{ "item": { "id": "acme-machine:8837" }, "price": { "amount": 650, "currency": "CNY" } }], "confirm": true }
```

```json
{ "location": "12345678", "updated": [{ "item": { "id": "acme-machine:8837" }, "price": { "amount": 650, "currency": "CNY" } }] }
```

1. `item.id` 必须来自一个 **`machine` 角色**的命名空间，且一次请求只能一个命名空间（`400 namespace_mismatch`）。
2. `price.amount` 正整数（分），`currency` 必须是 `CNY`。
3. `confirm` 必须是布尔 `true`（同 §7.4）。
4. 紧急停机时 `409 kill_switch_engaged`。
5. **价格上限护栏**：以机器上此刻的现价为基准，`|new − current| > rules.priceCapPerItem` 时**不执行**，返回 `200 approval_required` 并生成待审批决策（`kind: price_change`）。批准即执行（§11）；或批准后重发同一请求也会执行。
6. 无论成败写事件。

---

## 10. 扩展：补货 Replenishment
<!-- profiles: machine,supply -->

能力：`com.xiaopingfeng.vendling.replenishment`

| 对象 | 是什么 | 谁执行 | 花不花钱 |
|---|---|---|---|
| **计划 Plan** | 策略算出来的"每个货道现在该订多少" | 本系统，每日 | 否 |
| **行程 Run** | 一次出门要跑的机器、要带的货、预估成本；可下单、可收货 | 运营者 | 下单那一步花 |
| **补货推荐 Recommendation** | 给机器平台自家运维队伍的"往这台机器装什么"的提示 | 机器平台 | 否 |

| 操作 | 方法 | 端点 |
|---|---|---|
| 当前计划 | `GET` | `/replenishment/plan` |
| 列出 / 取一个行程 | `GET` | `/replenishment/runs?status=`、`/replenishment/runs/{id}` |
| 生成行程 | `POST` | `/replenishment/runs` |
| 下单 | `POST` | `/replenishment/runs/{id}/place` |
| 收货 | `POST` | `/replenishment/runs/{id}/receive` `{delivered:[{slot_id, quantity}], note?}` |
| 预测评分 | `GET` | `/replenishment/score?horizon_days=7` |
| 向机器平台推荐 | `POST` | `/locations/{id}/restock-recommendations` `{reference, line_items:[{item:{id}, quantity, reason}]}` |

### 10.1 计划

```json
{
  "strategy_version": "v2-weekshape",
  "params": { "window_days": 21, "cover_days": 7, "safety_days": 2, "min_order_qty": 3, "max_order_qty": 40 },
  "lead_time": { "days": 1.6, "source": "measured", "samples": 7 },
  "plans": [
    { "slot_id": "12345678-8837", "location": "12345678", "item": { "id": "acme-machine:8837", "title": "红牛 250ml" }, "stock": 7,
      "demand": { "daily_rate": 0.52, "naive_daily_rate": 0.48, "available_days": 19, "empty_days": 2, "closed_days": 0, "measured": true },
      "days_of_cover": 13.4, "stockout_at": "2026-09-22T00:00:00+08:00", "recommendation": { "action": "hold" } }
  ]
}
```

`lead_time.source` 是 `measured`（从历史行程实测）或 `stated`（样本不够，用参数），必须原样透出。`demand.measured = false` 表示需求率是从缺货期推断的。

### 10.2 行程（Run）

行程的形状**刻意贴近 UCP Order**：行项目、按机器分组的履约期望、追加式的履约事件、金额汇总。

| `status` | 条件 |
|---|---|
| `blocked` | 紧急停机时生成，`line_items` 为空。**和"没什么要补"不是一回事** |
| `nothing_to_do` | 没有货道需要补 |
| `pending_approval` / `rejected` / `approved` | 预估成本 > `spendingLimitPerRun` 时走审批 |
| `placed` / `delivered` | 已下单（`placed_at`）/ 已收货（`delivered_at`） |

- 行项目是机内 SKU（`machine` 角色）；每行带 `source`（经 §5.4 解析到的可采购 `sku_id` + 计量单位，缺省按个）。
- **下单** `place`：紧急停机 `409`；已下单 `409 already_placed`；待审批 `409 approval_required`。当前实现把行项目交给**模拟供货方**（响应带 `supplier: "simulated"`），未解析的行只是 `unresolved_sku` 警告；接真实供货方后，`place` 按 `source` 创建 §7 的结账会话（跨供货方时拆成多张），未解析的行升级为错误。
- **收货** `receive`：`quantity` 非负整数；有容量时封顶；已收货 `409 already_delivered`。
- 已下单未收货的行程覆盖的货道，在下一次计划里**跳过**，避免为同一批货付两次钱。
- `cost_is_estimated = true` 表示有行项目没有真实成本（用零售价 × 0.55 估的）；这个数字决定要不要审批，所以必须说明它是估的。

### 10.3 向机器平台的补货推荐

- `item.id` 必须是 `machine` 角色；`reference` 是机器平台要求的批次号；`reason` 超过 100 字截断。
- 不花钱、没有 `confirm`，但**受紧急停机约束**：它会推动别人去往机器里装货。

---

## 11. 扩展：审批 Approval

能力：`com.xiaopingfeng.vendling.approval`（extends `dev.ucp.shopping.checkout`）

| 操作 | 方法 | 端点 |
|---|---|---|
| 列出 | `GET` | `/approvals?status=pending&kind=` |
| 取一个 | `GET` | `/approvals/{id}` |
| 批 / 驳 | `POST` | `/approvals/{id}` `{ "approved": true, "resolver"?: { "channel", "chat_id", "sender_id" } }` |

```json
{ "id": "dec-1757404800000-1", "kind": "restock_plan", "at": "2026-09-09T04:00:00+08:00",
  "summary": "purchase order po_big: 1 line(s), ¥285.00 at acme-supply", "reasoning": "…",
  "subject": { "type": "checkout", "id": "po_big" }, "status": "pending", "approved": null }
```

- `kind` ∈ `swap | price_change | fault_flag | restock_plan | note`。`subject.type` ∈ `replenishment_run | checkout | price_change | slot`。
- 批准一个 `checkout` 让会话变成 `ready_for_complete`（提交仍是独立的显式调用）；批准一个 `price_change` **立即执行**改价。
- 带 `resolver` 的请求必须来自已注册的管理员，否则 `403`；已处理过的 `409`。每次处理写事件。

---

## 12. 扩展：事件 Events 与订单 Webhook

能力：`com.xiaopingfeng.vendling.events`

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| 读历史 | `GET` | `/events?limit=50&location=&kind=` | 最新在前；响应带 `websocket_url` |
| 写事件 | `POST` | `/events` `{kind, summary, reasoning, location?}` | 其他 Agent 的接入点；**不去重** |
| 实时流 | `WebSocket` | `websocket_url` | 连上先发 `event-history`（最近 50），之后每条 `event` |
| 订单 Webhook（UCP 标准） | `POST` | 平台在自己档案里给的 `webhook_url` | **[缺]** |

```json
{ "id": "evt-1757404812000-3", "occurred_at": "2026-09-09T13:00:12+08:00", "kind": "order",
  "summary": "order event: 2026090913001234 (交易成功) at 某写字楼11层 — 1 item(s), ¥6", "reasoning": "machine platform ledger poll", "location": "12345678" }
```

`kind` 是开放字符串。`occurred_at` 是**事情发生的时间**，不是入库时间。机器平台没有 webhook 时，订单事件由本系统
每 5 分钟轮询流水、去重后追加；要对接 UCP 平台的 Webhook，只需在同一处把 §8.2 的 Order 实体 `POST` 到对方 URL（头带 `Webhook-Id`、`Webhook-Timestamp`）。

---

## 13. 护栏与安全

| 操作 | `confirm: true` | 紧急停机 | 规则护栏 | 审批 | 记录 |
|---|---|---|---|---|---|
| §7 采购下单 complete | 必需 | 拒 | `spendingLimitPerRun`、`hardNoGos`、试用期 | `requires_escalation` | 事件 |
| §9 改价 | 必需 | 拒 | `priceCapPerItem` | `approval_required` | 事件 |
| §10.2 行程下单 place | — | 拒 | 同采购 | 决策必须已批 | 决策 + 事件 |
| §10.3 补货推荐 | — | 拒 | — | — | — |
| §6 名册增删 / 同步 | — | 不受影响 | — | — | 事件 |
| 读操作 | — | **不受影响** | — | — | — |

- 护栏**失败关闭**：读不到规则就拒绝（`503 guard_unverifiable`）。
- 模拟数据与真实数据不混：模拟购买默认关闭；平板模拟器的遥测标 `simulated = 1`。
- 顾客侧（扫码聊天界面）不在本规范内：它跑在另一个没有任何上游凭证的进程里，只能通过固定白名单的桥接读库存、写意图事件。
- 敏感字段：成本、利润只对运营者可见；目录响应**不含成本**，采购单的 `price` 是采购价。

---

## 附录 A. 设备与供货方适配器契约
<!-- profiles: adapter,supply,machine -->

Vendling 不直接依赖任何厂商接口。每个上游通过一个**适配器**接入，实现下面两个角色之一或两者；
系统其余部分只见到这里的形状。Vendling 自带一个参考实现（一个机器平台 + 一个供货方），其厂商细节不在公开文档中。

### A.1 通用约定

- 金额一律**整数分**；时间给 **epoch ms**（解析不了给 `null`，由调用方决定丢弃还是近似）。
- 上游出错**返回**而不是抛出：`{ ok: false, reason, unauthorized?, raw? }`。鉴权失败必须可辨认（`unauthorized: true`），不能看起来像空结果。
- 幂等：`createOrder(ref, …)` 的 `ref` 是调用方给的采购单号，重复调用不得产生第二张单。
- 适配器只认自己的命名空间；上游的分页、时区、签名全部在适配器内部消化。

### A.2 角色 `supply`（命名空间 `<vendor>-supply`）

| 方法 | 输入 | 输出 |
|---|---|---|
| `catalog({keyword?})` | 可选关键词 | `{ products: SupplyProduct[], sites: SupplySite[] }` |
| `createOrder(ref, lines, fulfillment)` | `lines: [{vendorSku, quantity, unit: "each" \| "pack"}]`；`fulfillment: {method:"shipping", contactName, contactPhone, address} \| {method:"pickup", pickupAt, siteId?}` | `{ externalRef }` 供货方订单号 |
| `orderStatus(ref)` | 采购单号 | `{ state: "ordered" \| "arrived" \| "cancelled", description, rawStatus, logistics[] }` |

```
SupplyProduct { vendorSku, title, spec?, category?, imageUrl?, packSize, packPriceFen, eachPriceFen, eachPriceDerived, stock }
SupplySite    { id, name?, address? }
```

`packSize = 1` 表示只按个卖（目录里不会出现 `BX`）。只拿得到箱价时 `eachPriceFen = round(packPriceFen / packSize)` 且 `eachPriceDerived = true`。

### A.3 角色 `machine`（命名空间 `<vendor>-machine`）

| 方法 | 输入 | 输出 |
|---|---|---|
| `inventory(locationId)` | 机器编号 | `MachineItem[]` |
| `ledger({fromMs, toMs, page?, size?, settledOnly?})` | 时间窗（账户级） | `{ records: LedgerRecord[], page, pages, total }` |
| `updatePrices(locationId, [{vendorSku, priceFen}])` | 真实改价 | `{ count }` |
| `restockRecommend(locationId, ref, [{vendorSku, quantity, reason}])` | 给平台运维的提示 | `{ count }` |

```
MachineItem  { vendorSku, title, barcode?, priceFen, stock, imageUrl? }
LedgerRecord { orderNo, status, statusLabel?, locationId, locationName?, totalFen, createdAt: ms|null, createdAtRaw, lines: LedgerLine[] }
LedgerLine   { vendorSku, priceFen, costFen: number|null, status: "paid"|"unpaid"|"refunded"|"refund_failed"|"cancelled" }
```

`costFen` 只在上游给出一个**不等于售价**的成本时才有值；等于售价的"成本"没有信息量，必须置 `null`。
流水是账户级的：适配器不做位置过滤，调用方按 `locationId` 分拣。

### A.4 注册与发现

适配器登记为 `{ namespace, vendor, role, status: "live" | "planned", capabilities[] }`。登记后 `GET /ucp/v1/namespaces`、
`/.well-known/ucp` 的 `com.xiaopingfeng.vendling.sku.config.namespaces` 自动带上；`planned` 的命名空间可以出现在 ID 里、
参与别名，但任何调用返回 `namespace_unsupported`。

### A.5 我的设备还没有适配器？

按 A.2 / A.3 实现对应角色即可，其余接口（目录、结账、订单、位置、改价、补货、审批、事件）不需要改动。
一台没有云平台的本地控制售货机，通常只需实现 `machine` 角色的 `inventory` 与 `ledger`（由本地网关维护），
`updatePrices` 与 `restockRecommend` 可以返回 `{ ok: false, reason: "unsupported" }`，对应能力就不会出现在它的 `capabilities[]` 里。

---

## 附录 B. 能力 × 设备类型矩阵

页面顶部的"我有什么"选择器按这张表折叠不相关的章节。无论哪种设备，先接 §2.1 的最小接入集。

| 章节 | 我运营机器（`machine`） | 我有供货 / 采购渠道（`supply`） | 我要接入新设备或供货方（`adapter`） |
|---|---|---|---|
| §3 通用约定、§4 发现档案 | ✓ | ✓ | ✓ |
| §5.1 供货方 SKU 清单 | | ✓ | |
| §5.2 机器库存 | ✓ | | |
| §5.3 Lookup | ✓ | ✓ | |
| §5.4 命名空间与 SKU 注册表 | ✓ | ✓ | ✓ |
| §6 位置 | ✓ | | |
| §7 结账 | | ✓ | |
| §8.1 采购单 | | ✓ | |
| §8.2 机器交易 | ✓ | | |
| §9 定价 | ✓ | | |
| §10 补货 | ✓ | ✓ | |
| §11 审批、§12 事件、§13 护栏 | ✓ | ✓ | ✓ |
| 附录 A 适配器契约 | ✓ | ✓ | ✓ |
