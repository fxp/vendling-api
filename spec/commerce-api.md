# Vendling Commerce API — 标准接口文档（UCP 对齐）

版本 `2026-09-09` · 对齐 [Universal Commerce Protocol](https://ucp.dev) 稳定版 `2026-08-25`
· 机器可读版：[`openapi/vendling-commerce.openapi.yaml`](openapi/vendling-commerce.openapi.yaml)

这份文档把 vendling-core **当前真实在用**的商品类接口——友宝批发的 SKU 清单与补货下单、
友宝货柜的库存 / 改价 / 交易流水 / 补货推荐，以及本系统自己的补货计划、审批、事件——
提取出来，按 Google 牵头的 UCP（Universal Commerce Protocol）的结构与命名重新归一，
形成一套稳定的对外接口。UCP 有对应概念的地方（目录、结账、订单、门店位置、履约）沿用
UCP 的字段名与状态机；UCP 没有覆盖的售货机运营语义（机器改价、货道库存、补货推荐、
人工审批、事件流）以 UCP 允许的**扩展**方式定义，不改动标准部分。

与既有文档的关系：[`api.md`](api.md) 是按场景组织的"现在有什么路由"清单；本文是
"这些接口**应该长什么样**"的规范，附带现有路由到标准端点的映射（附录 B）。
上游友宝接口的原始形态——签名、端点、字段、踩过的坑——完整记录在附录 A，
那是本规范的"事实来源"，所有字段映射都能回溯到它。

标记约定：**[有]** 已按本规范实现（`src/ucp/`，挂在 `/ucp/v1/*`）；**[有·旧壳]** 现有旧路由提供等价能力；
**[映射]** 现有代码有数据，还没有按本规范暴露；**[缺]** 现在没有。

> 2026-09-09 起 `/ucp/v1/*` 与 `/.well-known/ucp` 已在代码里实现（适配层 `src/ucp/`，测试 `test/ucp.test.ts`），
> 生产部署以 `GET https://vendling.xiaopingfeng.com/.well-known/ucp` 是否返回档案为准。

---

## 0. 目录

1. [对齐原则](#1-对齐原则)
2. [角色与方向](#2-角色与方向)
3. [通用约定](#3-通用约定)：信封、鉴权、头、金额、时间、SKU 命名空间、分页、错误
4. [发现档案 `/.well-known/ucp`](#4-发现档案-well-knownucp)
5. [目录 Catalog](#5-目录-catalog)：供应商 SKU 清单、机器库存、SKU 注册表
6. [位置 Location](#6-位置-location)：机器即门店
7. [结账 Checkout](#7-结账-checkout)：向友宝下补货采购单
8. [订单 Order](#8-订单-order)：采购单物流状态、机器交易流水
9. [扩展：定价 Pricing](#9-扩展定价-pricing)
10. [扩展：补货 Replenishment](#10-扩展补货-replenishment)
11. [扩展：审批 Approval](#11-扩展审批-approval)
12. [扩展：事件 Events 与订单 Webhook](#12-扩展事件-events-与订单-webhook)
13. [护栏与安全](#13-护栏与安全)
- 附录 A [上游友宝接口原始规范（按实际可用的写法）](#附录-a-上游友宝接口原始规范)
- 附录 B [现有路由 ↔ 标准端点映射](#附录-b-现有路由--标准端点映射)
- 附录 C [非商品类外部接口一览](#附录-c-非商品类外部接口一览)

---

## 1. 对齐原则

| 维度 | UCP 的做法 | 本规范的做法 |
|---|---|---|
| 能力命名 | 反向域名 `{authority}.{service}.{capability}`，如 `dev.ucp.shopping.checkout` | 标准能力原样用 `dev.ucp.*`；本项目扩展用 `com.xiaopingfeng.vendling.*`（authority = `vendling.xiaopingfeng.com`，按 UCP 的 authority binding 规则，扩展 schema 必须托管在该域名下） |
| 版本 | 日期版本 `YYYY-MM-DD`，schema 自描述 `name` + `version` | `ucp.version` = `2026-08-25`；扩展版本 `2026-09-09`；破坏性变更换日期，不改字段语义 |
| 发现 | 商家在 `/.well-known/ucp` 发布档案；平台在 `UCP-Agent` 头里给出自己的档案 URL | 同上，见 §4 |
| 响应信封 | 每个响应带 `ucp: {version, status, capabilities}`；错误走 `messages[]` | 同上，见 §3.1 |
| 金额 | 整数、货币最小单位、显式 `currency` | 全部用**分**、`"currency": "CNY"`；上游的元 / 分混用在适配层统一 |
| 字段命名 | `snake_case`，JSON Schema 2020-12 | 同上；现有 TypeScript 里的 `camelCase` 只存在于内部类型，不外露 |
| 传输 | REST 为核心，另有 MCP / A2A / Embedded 绑定 | 先 REST；MCP 绑定留给 `src/tools/catalog.ts` 的工具目录（工具名与本规范操作一一对应，见附录 B） |
| 目录 → 结账 → 订单 | 目录返回的 `variants[].id` 直接作为结账的 `line_items[].item.id`；结账完成得到 `order` | 同上，且这个 ID 在所有接口里都是同一个 `sku_id`（`<namespace>:<vendor_sku>`，§3.6）；多 vendor 靠命名空间隔开 |
| 履约 | `dev.ucp.shopping.fulfillment` 扩展：`methods[]` 的 `shipping` / `pickup` | 友宝的 `pick_up_type` 1 配送 / 2 自提 正好对应；自提时间做成可选的 `options[]` |
| 销售单位 | `quantity_unit`（sale basis）：`unit` / `scale` / `increment`，缺省 `each` | 同一 SKU 可按个（`EA`，缺省）或按箱（`BX`）下单，箱规在 `sale_units[]` 里公布；友宝的 `unit` 1 / 2 由此翻译 |
| 人工介入 | `status: requires_escalation` + `continue_url`，`severity: requires_buyer_review` | 花钱 / 改价的人工审批用这一套表达，审批本身是扩展 §11 |

UCP 明确允许的扩展点，本规范都只用这些：`metadata` 对象（product / variant）、
自定义 `fulfillment.methods[].type`、开放的 `fulfillment.events[].type` /
`adjustments[].type` 字符串、自由的 `messages[].code`、`actions` 映射、
以及以 `extends` 声明的扩展能力。

---

## 2. 角色与方向

UCP 只定义两个角色：**Platform**（消费能力的一方）和 **Business**（暴露能力的一方），
按能力流向而不是行业划分。vendling-core 同时扮演两个角色：

```
                 ┌──────────────── 上游：vendling-core 是 Platform ────────────────┐
                 │                                                                 │
   友宝批发 open.uboxol.com  ◄──── catalog.search / checkout / order ────  vendling-core
   （Business：供应商）              §5.1  SKU 清单      §7  下单进货    §8.1 物流状态
                                                                                 │
   友宝货柜 uboxapi.ubox.cn  ◄──── inventory / price / trade / recommend ──────────┤
   （Business：机器运营平台）        §5.2 库存  §9 改价  §8.2 流水  §10.3 补货推荐    │
                                                                                 │
                 ┌──────────────── 下游：vendling-core 是 Business ────────────────┤
                 │                                                                 │
   运营者 Dashboard / 飞书 Agent / 顾客界面 vendling-face / 其他 Agent  ───────────►│
   （Platform）        §6 位置  §5.2 目录  §8.2 订单  §10 补货  §11 审批  §12 事件
```

上游友宝不讲 UCP。`src/adapters/youbao/` 是把它翻译成本规范的适配层：本规范描述适配层
**对内**暴露的标准形态，附录 A 描述适配层**对外**实际调用的原始形态。下游调用方只看本规范。

---

## 3. 通用约定

### 3.1 响应信封

每个成功响应是一个 JSON 对象，带必需的 `ucp` 成员，其余成员是该操作的实体：

```json
{
  "ucp": {
    "version": "2026-08-25",
    "status": "success",
    "capabilities": {
      "dev.ucp.shopping.catalog.search": [{ "version": "2026-08-25" }],
      "com.xiaopingfeng.vendling.inventory": [{ "version": "2026-09-09" }]
    }
  },
  "products": [ ... ]
}
```

`ucp.capabilities` 列出本响应实际启用的能力（含扩展），调用方据此知道哪些扩展字段有效。

### 3.2 鉴权

| 场景 | 方式 | 说明 |
|---|---|---|
| 下游调用本规范的任何端点 | `Authorization: Bearer <VENDLING_AUTH_TOKEN>` 或会话 cookie `vendling_auth` | 与现有 operator token 一致（`src/auth.ts`）。UCP 允许 API key 作为鉴权机制。**一把 token 全权**，没有按调用方的 scope；这是已知状态，不是本规范新增的 |
| 平台自我标识 | `UCP-Agent: profile="https://<platform>/.well-known/ucp"` | UCP 要求平台每个请求都带。本系统当前**不校验**它，只记录进事件的 `reasoning`；机器对机器接入后再启用 RFC 9421 签名 |
| 上游友宝 | 见附录 A：批发是 RSA + AES + SHA-256 签名，货柜是 SHA-1 签名 | 密钥只在 Worker 环境变量里；staging 环境**没有**任何 `YOUBAO_*` 凭证，所以 staging 结构上无法花钱 |

### 3.3 请求头

| 头 | 必需 | 说明 |
|---|---|---|
| `Content-Type: application/json` | 写操作 | |
| `UCP-Agent` | 平台请求 | 见 §3.2 |
| `Idempotency-Key` | 写操作应带 | UCP 约定：服务端至少保存 24 小时，同 key 同 body 返回缓存结果，同 key 不同 body 返回 `409`。结账 / 采购单用 checkout `id` 兼作友宝的 `out_trade_no`，天然幂等；其余写操作 **[缺]** 尚未实现幂等存储 |
| `Accept-Language` | 可选 | 等价于 `context.language`；商品标题目前只有中文 |

### 3.4 金额 `Price` / `Total`

```json
{ "amount": 550, "currency": "CNY" }          // Price：5.50 元
{ "type": "subtotal", "amount": 6600 }          // Total：type 是开放字符串
```

- `amount` 恒为**整数、分**。UCP 的 `Total.amount` 是 `signed_amount`，退款等调整为负数。
- 井然有序的 `totals[]` 类型（UCP 熟知值）：`subtotal`、`discount`、`fulfillment`、`tax`、`fee`、`total`。本系统用到 `subtotal`、`fulfillment`（配送费）、`total`。
- 上游换算规则固定在适配层（见附录 A.3）：批发价"元/箱"字符串 → 分；货柜价 `productPrice` 已是分；流水 `totalFee` 是元浮点 → `Math.round(x * 100)`，`goodsPrice` / `cost` 是分。
- **成本**：友宝流水里的 `cost` 在本账号上恒等于售价（附录 A.2.3），适配层把它视为"未知"，对外一律不冒充成本。有真实成本的只有批发目录的 `price`。

### 3.5 时间

- 对外一律 RFC 3339 带时区偏移：`"2026-09-09T14:03:00+08:00"`。
- 友宝返回和接收的时间都是**无时区标记的北京时间**（`"2026-08-24 20:19:57.000"`），适配层用固定 `+08:00` 解析与格式化（`src/adapters/youbao/sync.ts` 的 `parseBeijingTime` / `formatBeijingTime`）。用 `toISOString()` 直接拼窗口会整体偏 8 小时，这个 bug 出过一次，是本条存在的原因。
- 位置的营业时间按 UCP 用本地民用时间 + `timezone: "Asia/Shanghai"`。

### 3.6 SKU 标识与命名空间

一件商品在本规范的**所有**接口里只有一个标识：`sku_id`。目录、库存、结账、订单、改价、
补货计划、补货推荐用的都是同一个字符串，不存在"目录里叫一个名、下单时换一个名"的情况。

```
sku_id = "<namespace>:<vendor_sku>"
```

- `namespace`：发号方，`[a-z][a-z0-9-]*`，在下面的注册表登记。一个 vendor 有几套互不相通的编号，就登记几个命名空间。
- `vendor_sku`：发号方自己的编号，**原样保留、不解析**（数字、字母、带点号都行；不能含冒号和空白）。
- 整串是唯一身份，按精确字符串比较。不同命名空间的两个 `sku_id` 永远不相等，哪怕物理上是同一件货。

| `namespace` | 发号方 | 出现在 | 编号形态 | 适配器 |
|---|---|---|---|---|
| `youbao-wholesale` | 友宝批发 `product_id` | 供应商目录、采购结账、采购单 | 数字串 | `adapters/youbao/wholesale.ts` **[有]** |
| `youbao-vm` | 友宝货柜 `productId` | 机器库存、交易流水、改价、补货计划 / 行程、补货推荐 | 数字串 | `adapters/youbao/device.ts` **[有]** |
| `yuanqi` | 元气（直供） | 供应商目录、采购结账、采购单 | 接入时定 | **[缺]**，预留 |

友宝占两个命名空间不是设计选择，是上游事实：批发平台和货柜平台各自发号，红牛在货柜里是
`8837`、在批发目录里是 `10088`，两边都没有对方的号。跨命名空间的"这是同一件货"靠 §5.4 的
**别名**表达，不靠猜。

三条硬规则：

1. **适配器只认自己的命名空间。** 货柜接口收到 `yuanqi:…` 返回 `400 namespace_mismatch`，不做转换。
2. **一张采购单只能有一个采购命名空间。** 结账会话里混入 `youbao-wholesale:` 和 `yuanqi:` 的行，`400 namespace_mismatch`，`path` 指向第一条不一致的行。一张 PO 只发给一个 vendor。
3. **包装不进 ID。** 整箱还是单个是下单时的计量单位（§7.1 `quantity_unit`），不是另一个 SKU。缺省按个。

其余标识符：

| 对象 | 格式 | 来源 |
|---|---|---|
| 位置（机器）`Location.id` | 友宝 `innerCode` / `vmId`，8 位数字字符串 | 设备名册 `synced_devices` |
| 货道 `slot_id` | `<vmId>-<vendor_sku>`（`youbao-vm` 的编号） | 友宝没有货道概念，这是"某机某品"的替身，不是物理货道号 |
| 采购结账 / 采购单 `Checkout.id` = `Order.id` | `po_<yyyymmdd>_<seq>` 或调用方给定的 PO 号 | 兼作友宝 `out_trade_no`；友宝回的 `order_code` 放在 `Order.label` |
| 机器交易 `Order.id` | 友宝 `outOrderNo` | 流水主键 |
| 补货行程 `ReplenishmentRun.id` | `run-<epoch ms>` | `RestockRun.id` |
| 决策 / 审批 `Approval.id` | `dec-<epoch ms>-<n>` | `Decision.id` |
| 事件 `Event.id` | `evt-<epoch ms>-<n>` | `VendlingEvent.id` |

### 3.7 分页

UCP 用游标：请求 `pagination: {cursor, limit}`，响应 `pagination: {cursor, has_next_page, total_count}`。
`limit` 缺省 20，是"请求的页大小"不是保证值。上游友宝批发目录一次返回全量、货柜流水用
`current` / `size` 页码；适配层把两者都翻译成不透明游标（内容是 base64 的 `{offset}` 或 `{page}`）。

### 3.8 错误模型

**协议层错误**（鉴权失败、路由不存在、上游不可达）用 HTTP 状态码 + 信封；**业务结果**
（缺货、需要审批、供应商拒单）按 UCP 约定用 HTTP `200` + `messages[]`，实体照常返回，
调用方**必须**先看 `messages` 再用数据。

```json
{
  "ucp": { "version": "2026-08-25", "status": "error" },
  "messages": [
    {
      "type": "error",
      "code": "kill_switch_engaged",
      "severity": "requires_buyer_review",
      "path": "$",
      "content": "kill switch is engaged — real 友宝 writes are frozen"
    }
  ],
  "continue_url": "https://vendling.xiaopingfeng.com/"
}
```

`severity` 取 UCP 的四个值：`recoverable`（调用方改一下请求就能过）、`requires_buyer_input`、
`requires_buyer_review`（要人看一眼 / 批一下）、`unrecoverable`。

| `code` | severity | HTTP | 触发 | 来源 |
|---|---|---|---|---|
| `missing` | recoverable | 400 | 必填字段缺失，`path` 指向字段 | UCP 标准 |
| `invalid` | recoverable | 400 | 类型 / 范围不对（如 `quantity` 非正整数、`price.amount` 非正整数） | UCP 标准 |
| `not_found` | unrecoverable | 404 | 位置 / 商品 / 结账 / 订单不存在 | UCP 标准 |
| `unauthorized` | unrecoverable | 401 | token 缺失或错误；或上游返回 `code=401 签名错误`（原文放 `content`） | UCP 标准 |
| `out_of_stock` | recoverable | 200 | 变体 `availability.available=false` | UCP 标准 |
| `item_unavailable` | recoverable | 200 | 变体已下架 / 不在该机器 | UCP 标准 |
| `request_too_large` | recoverable | 400 | 批量 lookup 超过 50 个 ID | UCP 标准 |
| `namespace_unsupported` | unrecoverable | 400 | 命名空间已登记但没有适配器（现在是 `yuanqi`） | 扩展 |
| `hard_no_go` | unrecoverable | 200 | 行项目命中 `rules.hardNoGos`，永不采购；会话停在 `incomplete` | 扩展 |
| `approval_rejected` / `expired` | unrecoverable | 200 | 审批被驳回 / 会话超过 24 小时；会话变为 `canceled` | 扩展 |
| `namespace_mismatch` | recoverable | 400 | 结账里混了多个采购命名空间；或把别的命名空间的 ID 传给了只认自己的适配器 | 扩展 |
| `unresolved_sku` | recoverable | 200 | 机内 SKU 没有已确认的可采购别名，行程不能下单 | 扩展 |
| `confirmation_required` | requires_buyer_review | 400 | 花钱 / 改价请求没带字面量 `confirm: true` | 扩展 |
| `approval_required` | requires_buyer_review | 200 | 超预算 / 超价格上限 / 试用期内，已生成待审批决策，`actions` 里给出 id | 扩展 |
| `kill_switch_engaged` | requires_buyer_review | 409 | 紧急停机开着 | 扩展 |
| `guard_unverifiable` | unrecoverable | 503 | 读不到护栏规则，**拒绝**执行而不是放行 | 扩展 |
| `supplier_rejected` | unrecoverable | 502 | 友宝 `code ≠ 1` / `≠ 200`，`content` 带原始 `msg` | 扩展 |
| `upstream_unreachable` | unrecoverable | 502 | 网络 / 非 JSON 响应 | 扩展 |
| `already_placed` / `already_delivered` | unrecoverable | 409 | 补货计划重复下单 / 重复收货 | 扩展 |
| `simulation_disabled` | unrecoverable | 409 | 模拟购买在真实线路上默认关闭 | 扩展 |

警告（`type: "warning"`，不阻塞）：`price_estimated`（单价由箱价换算）、`location_unverified`（机器号在流水里从未出现）、`history_truncated`（流水翻页到上限）、`hours_unknown`（营业时间未记录，`hours` 筛选未应用）、`same_namespace`（别名落在同一命名空间）、`sync_problem`（同步报错原文）、`unresolved_sku`（下单给模拟供应商时只是提示）。

所有 `messages[]` 里的 `content` 是给人看的；程序只认 `code`。

---

## 4. 发现档案 `/.well-known/ucp`

**[有]** 由 `src/ucp/profile.ts` 生成，公开、无需 token。`endpoint` 指向标准基址 `https://vendling.xiaopingfeng.com/ucp/v1`
（旧路由仍在 `/api/youbao/*` 和 `/agents/vendling-agent/route-01/*`，两套并存，映射见附录 B）：

```json
{
  "ucp": {
    "version": "2026-08-25",
    "services": {
      "dev.ucp.shopping": [
        {
          "version": "2026-08-25",
          "spec": "https://ucp.dev/2026-08-25/specification/overview/",
          "transport": "rest",
          "endpoint": "https://vendling.xiaopingfeng.com/ucp/v1",
          "schema": "https://ucp.dev/2026-08-25/services/shopping/rest.openapi.json"
        }
      ],
      "dev.ucp.common": [
        {
          "version": "2026-08-25",
          "spec": "https://ucp.dev/2026-08-25/specification/overview/",
          "transport": "rest",
          "endpoint": "https://vendling.xiaopingfeng.com/ucp/v1"
        }
      ]
    },
    "capabilities": {
      "dev.ucp.shopping.catalog.search": [{ "version": "2026-08-25", "spec": "https://ucp.dev/2026-08-25/specification/shopping/catalog/search", "schema": "https://ucp.dev/2026-08-25/schemas/shopping/catalog_search.json" }],
      "dev.ucp.shopping.catalog.lookup": [{ "version": "2026-08-25", "spec": "https://ucp.dev/2026-08-25/specification/shopping/catalog/lookup", "schema": "https://ucp.dev/2026-08-25/schemas/shopping/catalog_lookup.json" }],
      "dev.ucp.shopping.checkout":       [{ "version": "2026-08-25", "spec": "https://ucp.dev/2026-08-25/specification/shopping/checkout", "schema": "https://ucp.dev/2026-08-25/schemas/shopping/checkout.json" }],
      "dev.ucp.shopping.fulfillment":    [{ "version": "2026-08-25", "spec": "https://ucp.dev/2026-08-25/specification/shopping/extensions/fulfillment", "schema": "https://ucp.dev/2026-08-25/schemas/shopping/fulfillment.json", "extends": "dev.ucp.shopping.checkout" }],
      "dev.ucp.shopping.order":          [{ "version": "2026-08-25", "spec": "https://ucp.dev/2026-08-25/specification/shopping/order", "schema": "https://ucp.dev/2026-08-25/schemas/shopping/order.json" }],
      "dev.ucp.common.location.search":  [{ "version": "2026-08-25", "spec": "https://ucp.dev/2026-08-25/specification/common/location/search", "schema": "https://ucp.dev/2026-08-25/schemas/common/location_search.json" }],
      "dev.ucp.common.location.lookup":  [{ "version": "2026-08-25", "spec": "https://ucp.dev/2026-08-25/specification/common/location/lookup", "schema": "https://ucp.dev/2026-08-25/schemas/common/location_lookup.json" }],

      "com.xiaopingfeng.vendling.sku":           [{ "version": "2026-09-09", "spec": "https://vendling.xiaopingfeng.com/ucp/spec#sku",           "schema": "https://vendling.xiaopingfeng.com/ucp/schemas/sku.json",           "extends": ["dev.ucp.shopping.catalog.search", "dev.ucp.shopping.catalog.lookup", "dev.ucp.shopping.checkout", "dev.ucp.shopping.order"] }],
      "com.xiaopingfeng.vendling.inventory":     [{ "version": "2026-09-09", "spec": "https://vendling.xiaopingfeng.com/ucp/spec#inventory",     "schema": "https://vendling.xiaopingfeng.com/ucp/schemas/inventory.json",     "extends": ["dev.ucp.shopping.catalog.search", "dev.ucp.shopping.catalog.lookup"] }],
      "com.xiaopingfeng.vendling.location":      [{ "version": "2026-09-09", "spec": "https://vendling.xiaopingfeng.com/ucp/spec#location",      "schema": "https://vendling.xiaopingfeng.com/ucp/schemas/location.json",      "extends": ["dev.ucp.common.location.search", "dev.ucp.common.location.lookup"] }],
      "com.xiaopingfeng.vendling.approval":      [{ "version": "2026-09-09", "spec": "https://vendling.xiaopingfeng.com/ucp/spec#approval",      "schema": "https://vendling.xiaopingfeng.com/ucp/schemas/approval.json",      "extends": "dev.ucp.shopping.checkout" }],
      "com.xiaopingfeng.vendling.order":         [{ "version": "2026-09-09", "spec": "https://vendling.xiaopingfeng.com/ucp/spec#order",         "schema": "https://vendling.xiaopingfeng.com/ucp/schemas/order.json",         "extends": "dev.ucp.shopping.order" }],
      "com.xiaopingfeng.vendling.pricing":       [{ "version": "2026-09-09", "spec": "https://vendling.xiaopingfeng.com/ucp/spec#pricing",       "schema": "https://vendling.xiaopingfeng.com/ucp/schemas/pricing.json" }],
      "com.xiaopingfeng.vendling.replenishment": [{ "version": "2026-09-09", "spec": "https://vendling.xiaopingfeng.com/ucp/spec#replenishment", "schema": "https://vendling.xiaopingfeng.com/ucp/schemas/replenishment.json" }],
      "com.xiaopingfeng.vendling.events":        [{ "version": "2026-09-09", "spec": "https://vendling.xiaopingfeng.com/ucp/spec#events",        "schema": "https://vendling.xiaopingfeng.com/ucp/schemas/events.json" }]
    },
    "payment_handlers": {
      "com.xiaopingfeng.vendling.on_account": [
        { "id": "youbao_account", "version": "2026-09-09", "spec": "https://vendling.xiaopingfeng.com/ucp/spec#on-account", "schema": "https://vendling.xiaopingfeng.com/ucp/schemas/on_account.json" }
      ]
    }
  },
  "keys": []
}
```

`payment_handlers` 只有一个：**赊账 / 账户挂账**。友宝批发按客户编码 `customer_code`
记账，下单不经过任何支付凭证，所以结账的 `payment.instruments[]` 只有一种
`type: "on_account"`，没有 `credential`。这不是简化，是它真实的样子。`keys` 为空：
现在不做 RFC 9421 签名。

---

## 5. 目录 Catalog

能力：`dev.ucp.shopping.catalog.search`、`dev.ucp.shopping.catalog.lookup`
· 扩展：`com.xiaopingfeng.vendling.inventory`（机器库存视图）、`com.xiaopingfeng.vendling.sku`（销售单位、别名、SKU 注册表）

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| Search Catalog | `POST` | `/catalog/search` | 关键词 / 类目 / 价格筛选；`filters.namespace` 选数据源 |
| Batch Lookup | `POST` | `/catalog/lookup` | 按 `sku_id` 批量取，最多 50 个，可跨命名空间 |
| Get Product | `POST` | `/catalog/product` | 单品全量详情 |
| SKU 注册表（扩展） | `GET` / `POST` / `PUT` | `/skus/{sku_id}`、`/skus/resolve`、`/skus/{sku_id}/aliases` | 见 §5.4 |

同一套端点，`filters.namespace` 决定查哪个源：

| `filters.namespace` | 数据来源 | 回答的问题 | 附加条件 |
|---|---|---|---|
| `youbao-wholesale` | 友宝批发 `product-list/zp` | 供应商能卖给我们什么：SKU 清单、箱规、箱价 / 单价、供应商库存 | — |
| `youbao-vm` | 友宝货柜 `vm_product_inventory` | 某台机器现在有什么：机内商品、零售价、余量 | 必须给 `filters.location`（上游按机器查） |
| `yuanqi` | 元气 | 同 `youbao-wholesale` | **[缺]** |

返回的 `variants[].id` 就是 `sku_id`，可以直接放进结账的 `line_items[].item.id`（采购命名空间），
或改价、补货推荐的 `item.id`（`youbao-vm`）。

### 5.1 供应商 SKU 清单（`youbao-wholesale`）

```http
POST /catalog/search
{
  "query": "乌龙",
  "filters": { "namespace": "youbao-wholesale", "categories": ["饮料"] },
  "pagination": { "limit": 20 }
}
```

一个友宝批发商品 = 一个 `Product` + 一个 `Variant`。**整箱 / 单个不是两个变体**，是同一个变体的
两种销售单位（`sale_units[]`），下单时用 `quantity_unit` 选。缺省单位是 `EA`（个）：按个下单是
基础情况，按箱是可选项。

```json
{
  "ucp": { "version": "2026-08-25", "status": "success",
           "capabilities": { "dev.ucp.shopping.catalog.search": [{ "version": "2026-08-25" }],
                             "com.xiaopingfeng.vendling.sku": [{ "version": "2026-09-09" }] } },
  "products": [
    {
      "id": "youbao-wholesale:10023",
      "title": "三得利 乌龙茶 500ml",
      "description": { "plain": "500ml*15瓶/箱" },
      "categories": [{ "value": "饮料", "taxonomy": "merchant" }],
      "media": [{ "type": "image", "url": "https://.../10023.jpg" }],
      "price_range": { "min": { "amount": 380, "currency": "CNY" }, "max": { "amount": 380, "currency": "CNY" } },
      "variants": [
        {
          "id": "youbao-wholesale:10023",
          "title": "三得利 乌龙茶 500ml",
          "description": { "plain": "500ml*15瓶/箱" },
          "price": { "amount": 380, "currency": "CNY" },
          "quantity_unit": { "unit": "EA", "display_text": "瓶", "increment": 1 },
          "sale_units": [
            { "unit": "EA", "display_text": "瓶", "increment": 1,
              "price": { "amount": 380, "currency": "CNY" }, "price_derived": true },
            { "unit": "BX", "display_text": "箱", "contains": 15, "increment": 1,
              "price": { "amount": 5700, "currency": "CNY" } }
          ],
          "availability": { "available": true, "status": "in_stock" },
          "aliases": [],
          "metadata": { "vendor_sku": "10023", "spec": "500ml*15瓶/箱", "supplier_stock": 120 }
        }
      ],
      "metadata": { "factory_id": "2021", "factory_address": "…" }
    }
  ],
  "pagination": { "has_next_page": false, "total_count": 1 }
}
```

`sale_units[]`（扩展 `com.xiaopingfeng.vendling.sku`）：

| 字段 | 说明 |
|---|---|
| `unit` | UN/ECE Rec 20 单位码：`EA` 个、`BX` 箱。与 UCP `quantity_unit.unit` 同一词表 |
| `display_text` | 给人看的单位名 |
| `contains` | 该单位含多少个 `EA`；`EA` 自身省略 |
| `increment` | 起订倍数，UCP 原字段 |
| `price` | 该单位一件的价格 |
| `price_derived` | 价格是换算出来的（单价 = 箱价 ÷ 箱规）。友宝 `create-order` 不回价格，实际结算以供应商对账为准 |

`variants[].price` 恒为 **`EA` 单位的价格**，`quantity_unit` 恒为 `EA`。这样一个不认识 `sale_units`
的 UCP 标准客户端也能正确地按个下单。

字段映射（友宝批发 → UCP）：

| 友宝 `product_list[]` | UCP |
|---|---|
| `product_id` | `id` = `youbao-wholesale:<product_id>`；`metadata.vendor_sku` |
| `brand_name` + `product_name` | `title`（空格拼接、去首尾空白） |
| `spec_str`（如 `"500ml*15瓶/箱"`） | `description.plain`；箱规 `contains` 由 `/(\d+)\s*[瓶罐袋包个件]\/箱/` 提取，提不出记 12（与 `wholesale.ts` 的 `boxSize()` 一致） |
| `price`（元/箱，字符串） | `BX` 的 `price.amount = round(price × 100)`；`EA` 的 `price.amount = round(price × 100 / contains)`，标 `price_derived` |
| `stock` | `availability`：`> 0` → `in_stock`，否则 `out_of_stock`；原值放 `metadata.supplier_stock` |
| `image_url` | `media[0]` |
| `category_name` | `categories[].value`，`taxonomy: "merchant"` |
| `factory_id` / `factory_address`（响应级） | `Product.metadata`；自提目的地 ID `factory:<id>` |

友宝这个端点**没有服务端搜索**，`query` 是适配层在全量清单上做的子串匹配（去空格、不分大小写，
与 `searchCatalog()` 相同）。

### 5.2 机器库存（`youbao-vm`）— 扩展 `com.xiaopingfeng.vendling.inventory`

```http
POST /catalog/search
{ "filters": { "namespace": "youbao-vm", "location": "12345678" } }
```

```json
{
  "ucp": { "version": "2026-08-25", "status": "success",
           "capabilities": { "dev.ucp.shopping.catalog.search": [{ "version": "2026-08-25" }],
                             "com.xiaopingfeng.vendling.inventory": [{ "version": "2026-09-09" }],
                             "com.xiaopingfeng.vendling.sku": [{ "version": "2026-09-09" }] } },
  "products": [
    {
      "id": "youbao-vm:8837",
      "title": "红牛 250ml",
      "description": { "plain": "红牛 250ml" },
      "media": [{ "type": "image", "url": "https://.../8837.jpg" }],
      "price_range": { "min": { "amount": 600, "currency": "CNY" }, "max": { "amount": 600, "currency": "CNY" } },
      "variants": [
        {
          "id": "youbao-vm:8837",
          "sku": "6920202888883",
          "barcodes": [{ "type": "EAN", "value": "6920202888883" }],
          "title": "红牛 250ml",
          "description": { "plain": "红牛 250ml" },
          "price": { "amount": 600, "currency": "CNY" },
          "availability": { "available": true, "status": "in_stock" },
          "inventory": { "location": "12345678", "slot_id": "12345678-8837", "stock": 7, "capacity": null, "locked": false },
          "aliases": [
            { "sku_id": "youbao-wholesale:10088", "source": "manual", "confirmed_at": "2026-09-01T10:00:00+08:00" }
          ]
        }
      ]
    }
  ]
}
```

扩展定义：

| 字段 | 位置 | 说明 |
|---|---|---|
| `filters.namespace` | 请求 | 数据源，见本节开头的表 |
| `filters.location` | 请求 | 机器 ID；`namespace = youbao-vm` 时必填 |
| `variants[].inventory.location` | 响应 | 机器 ID |
| `variants[].inventory.slot_id` | 响应 | `<vmId>-<vendor_sku>`，见 §3.6 |
| `variants[].inventory.stock` | 响应 | 友宝 `productInventory` |
| `variants[].inventory.capacity` | 响应 | 货道容量。友宝**不提供**；有运营者现场数过（field task `count_capacity`）或从历史最高库存推出时才有值，否则 `null`。不许默认一个数 |
| `variants[].inventory.locked` | 响应 | 运营者锁定的货道，选品循环不得触碰 |
| `variants[].aliases[]` | 响应 | 其他命名空间里的同一件货，见 §5.4。这是从"机器缺货"走到"向谁采购"的唯一桥 |

字段映射（友宝货柜 → UCP）：

| 友宝 `data[]` | UCP |
|---|---|
| `productId` | `id` = `youbao-vm:<productId>` |
| `productName` | `title` |
| `productCode`（69 码） | `sku` 和 `barcodes[{type:"EAN"}]` |
| `productPrice`（分） | `price.amount` 原样 |
| `productInventory` | `inventory.stock`；`> 0` → `in_stock` |
| `productImgUrl` | `media[0]` |

**已知陷阱（适配层必须处理）**：友宝对**不存在的机器号也返回 OK**，并带一条看起来合理的商品
（一瓶 0.1 元的椰子水，库存 69）。适配层用账户级交易流水做交叉检查：一个在 30 天窗口内没有
任何流水的机器号会在 `messages[]` 里得到一条 `type: "warning"`、`code: "location_unverified"`，
内容说明"要么是全新机器，要么是号写错了"。这是唯一的检查手段，不能省。

### 5.3 Lookup

```http
POST /catalog/lookup
{ "ids": ["youbao-wholesale:10023", "youbao-vm:8837"] }
```

命名空间就在 ID 里，所以不需要 `filters.namespace`，一次请求可以跨命名空间，适配层按前缀分发
（`youbao-vm` 的 ID 需要 `filters.location`，否则该条返回 `missing`）。按 UCP 约定：ID 去重；
每个变体带 `inputs[]` 说明它是被哪个请求 ID 解析到的、匹配类型是 `exact` 还是 `featured`；
超过 50 个 ID 返回 `400 request_too_large`。

### 5.4 SKU 注册表 — 扩展 `com.xiaopingfeng.vendling.sku`

状态 **[缺]**。这是补货闭环里现在断掉的一环：要从"机器里 `youbao-vm:8837` 快空了"走到
"向友宝买 `youbao-wholesale:10088`，或向元气买 `yuanqi:E123`"，必须跨命名空间。现有代码没有
这条链：`sync.ts` 用货柜编号建商品，批发编号从未和它关联；行程下单发给的是模拟供应商，
所以还没被咬到。接真实采购之前必须补上。

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| 取一个 SKU | `GET` | `/skus/{sku_id}` | 身份、条码、别名、可采购来源 |
| 解析 | `POST` | `/skus/resolve` | 把一批 `sku_id` 解析到目标命名空间 |
| 记别名 | `PUT` | `/skus/{sku_id}/aliases` | 人工确认两个号是同一件货 |

```http
GET /skus/youbao-vm:8837
```

```json
{
  "ucp": { "version": "2026-08-25", "status": "success" },
  "sku_id": "youbao-vm:8837",
  "namespace": "youbao-vm",
  "vendor_sku": "8837",
  "title": "红牛 250ml",
  "barcodes": [{ "type": "EAN", "value": "6920202888883" }],
  "aliases": [
    { "sku_id": "youbao-wholesale:10088", "source": "manual", "confirmed_at": "2026-09-01T10:00:00+08:00" },
    { "sku_id": "yuanqi:E123", "source": "suggested", "confirmed_at": null }
  ],
  "purchasable_from": [
    { "sku_id": "youbao-wholesale:10088", "title": "红牛 维生素功能饮料 250ml",
      "sale_units": [ { "unit": "EA", "price": { "amount": 480, "currency": "CNY" }, "price_derived": true },
                      { "unit": "BX", "contains": 24, "price": { "amount": 11520, "currency": "CNY" } } ] }
  ]
}
```

```http
POST /skus/resolve
{ "ids": ["youbao-vm:8837", "youbao-vm:9120"], "to_namespace": "youbao-wholesale" }
```

```json
{
  "ucp": { "version": "2026-08-25", "status": "success" },
  "resolved":   [{ "from": "youbao-vm:8837", "to": "youbao-wholesale:10088" }],
  "unresolved": ["youbao-vm:9120"]
}
```

别名规则：

- `source` ∈ `barcode`（两边都有 EAN 时自动建立）、`manual`（运营者确认）、`suggested`（按名称相似度提出）。**只有 `barcode` 和 `manual` 参与下单**，`suggested` 只用于展示，未确认前 `resolve` 不返回它。
- 别名是对称的：记 `A → B` 即记 `B → A`。
- `resolve` 的 `unresolved` 不是错误。但带着未解析的行去 §10.2 的 `place` 会得到 `unresolved_sku`，行程不会下单。
- 现实约束：货柜库存带 69 码，批发目录的字段里**没有条码**（附录 A.1），所以友宝两个命名空间之间目前做不到自动 `barcode` 匹配，只能 `suggested` + 人工确认。元气接入时若目录带条码，自动匹配即刻可用。

---

## 6. 位置 Location

能力：`dev.ucp.common.location.search`、`dev.ucp.common.location.lookup`
· 扩展：`com.xiaopingfeng.vendling.location`（在线状态、场地类型、设备名册管理）

UCP 的 Location 是"地图上找得到的实体"——门店、餐厅、储物柜。一台售货机正是这样的实体：
有地址、有营业时段、可以按"这里现在有没有某件商品"筛选。

| 操作 | 方法 | 端点 | 状态 |
|---|---|---|---|
| Search Locations | `POST` | `/locations/search` | **[映射]** 数据在 `GET .../state` + `/machines/<id>/profile` |
| Lookup Locations | `POST` | `/locations/lookup` | **[映射]** `GET .../machine/<id>` 只回 `{id,name}` |
| 注册 / 更新一台机器（扩展） | `PUT` | `/locations/{id}` | **[有]** `POST .../sync/youbao {devices}` + `PATCH .../machines/<id>/profile` |
| 移除一台机器（扩展） | `DELETE` | `/locations/{id}` | **[有]** `DELETE .../sync/devices/<id>` |
| 立即同步遥测（扩展） | `POST` | `/locations/sync` | **[有]** `POST .../sync/youbao` |

### 6.1 实体

```json
{
  "id": "12345678",
  "name": "搜狐网络大厦 11F",
  "address": {
    "street_address": "科学院南路 2 号 搜狐网络大厦",
    "extended_address": "11F 电梯厅",
    "address_locality": "北京市",
    "address_region": "北京市",
    "address_country": "CN"
  },
  "timezone": "Asia/Shanghai",
  "hours": [
    { "day": "monday", "opens": "08:00", "closes": "21:00" }
  ],
  "amenities": {
    "com.xiaopingfeng.vendling.qr_chat": { "description": "扫码可与机器对话、点单、报修" },
    "com.xiaopingfeng.vendling.kiosk":   { "description": "机身平板，上报人流与环境" }
  },
  "online": true,
  "venue_name": "搜狐网络大厦11层",
  "venue_type": "office",
  "placement": "indoor",
  "last_synced_at": "2026-09-09T13:00:00+08:00",
  "profile_complete": false,
  "missing": ["city"]
}
```

| 字段 | 来源 | 说明 |
|---|---|---|
| `id` / `name` | 设备名册 `synced_devices` | |
| `address.*` | `MachineProfile`（`address`、`floor`、`spot`、`city`） | `floor` + `spot` 拼进 `extended_address`；`city` 进 `address_locality` |
| `hours[]` | **[缺]** `docs/scenarios.md` 规划的 `activeHours`，尚无存储 | 缺时**省略**整个字段，UCP 规定"缺 = 未知"而非"关门" |
| `amenities` | 固定 | |
| `online`（扩展） | `Machine.online`，由每小时同步的库存请求成败决定 | |
| `venue_name`（扩展） | 友宝流水的 `nodeName` | 设备接口不给位置，这是唯一出处 |
| `venue_type` / `placement`（扩展） | `MachineProfile.venueType` / `placement` | `office / gym / hospital / campus / transit / residential / retail / other`；`indoor / outdoor / semi_outdoor` |
| `profile_complete` / `missing`（扩展） | `missingRequired(profile)` | |

### 6.2 按商品可得性搜索

UCP 的 `filters.items[]` 问"哪些位置现在能提供这些商品"。这里直接落到货柜库存：

```http
POST /locations/search
{ "filters": { "items": [{ "id": "youbao-vm:8837" }] } }
```

只返回该商品 `stock > 0` 的机器。按 UCP 语义这是**临时性**信号，不是保留。

### 6.3 名册管理（扩展）

```http
PUT /locations/12345678
{ "name": "搜狐网络大厦 11F", "profile": { "city": "北京", "placement": "indoor", "venueType": "office" } }
```

- 注册后每小时自动同步；`syncRoute` 是**整体替换**机器 / 商品 / 货道 / 销售，但保留运营者的货道锁。
- `DELETE` 清掉档案、周边信息、遥测；**保留**事件与对话历史（那是发生过的事，不是配置）。响应里报告各清了多少条。
- `POST /locations/sync` 可带 `{ "sales_window_days": 30 }`；窗口不得小于补货策略的观察期（21 天），否则需求率被静默低估。

---

## 7. 结账 Checkout

能力：`dev.ucp.shopping.checkout` + `dev.ucp.shopping.fulfillment` · 扩展：`com.xiaopingfeng.vendling.approval`、`com.xiaopingfeng.vendling.sku`

这是"**下单进货**"：向一个供应商下一张真实的、花真钱的采购单。UCP 的结账会话模型正好把它拆成
"建单 → 补齐信息 → 审批 → 提交"几步，每一步都有明确状态，钱只在最后一步动。

| 操作 | 方法 | 端点 | 状态 |
|---|---|---|---|
| Create Checkout | `POST` | `/checkout-sessions` | **[映射]** 现在 `POST /api/youbao/order` 一步到位，没有会话 |
| Get Checkout | `GET` | `/checkout-sessions/{id}` | **[缺]** |
| Update Checkout | `PUT` | `/checkout-sessions/{id}` | **[缺]** |
| Complete Checkout | `POST` | `/checkout-sessions/{id}/complete` | **[有]** = `POST /api/youbao/order {confirm:true}` |
| Cancel Checkout | `POST` | `/checkout-sessions/{id}/cancel` | **[缺]** |

### 7.1 建单

```http
POST /checkout-sessions
Idempotency-Key: po_20260909_001
{
  "id": "po_20260909_001",
  "line_items": [
    { "item": { "id": "youbao-wholesale:10023" }, "quantity": 2, "quantity_unit": { "unit": "BX" } },
    { "item": { "id": "youbao-wholesale:10088" }, "quantity": 6 }
  ],
  "fulfillment": {
    "methods": [
      {
        "type": "shipping",
        "line_item_ids": ["*"],
        "destinations": [
          {
            "type": "shipping_address",
            "street_address": "科学院南路 2 号 搜狐网络大厦 11F",
            "address_locality": "北京市",
            "address_country": "CN",
            "first_name": "张三",
            "phone_number": "13800000000"
          }
        ]
      }
    ]
  }
}
```

- `id` 可选。给了就用作 PO 号（兼友宝 `out_trade_no`），没给由服务端生成 `po_<日期>_<序号>`。
- `line_items[].item.id` 是 §3.6 的 `sku_id`，必须来自**采购**命名空间（`youbao-wholesale`、`yuanqi`）。`youbao-vm:` 的 ID 不能直接下单，先经 §5.4 `resolve`。
- **一张单一个命名空间**：所有行的前缀必须相同，否则 `400 namespace_mismatch`。会话的供应商由第一行决定。
- **按个下单是缺省**：`quantity_unit` 省略即 `{ "unit": "EA" }`，`quantity` 是"个"数。要按箱就写 `{ "unit": "BX" }`，`quantity` 是箱数。`unit` 必须是该变体 `sale_units[]` 里有的，否则 `400 invalid`，`path` 指向 `$.line_items[n].quantity_unit`。
- 履约二选一：
  - `shipping`（友宝 `pick_up_type = 1`）：目的地必须有 `street_address` + `first_name`（联系人）+ `phone_number`，三者缺一友宝拒单，所以建单时就返回 `missing`。
  - `pickup`（友宝 `pick_up_type = 2`）：目的地由服务端枚举，`factory:<factory_id>`（缺省厂 `YOUBAO_DEFAULT_FACTORY_ID`）。平台用 `selected_destination_id` 选厂，用 `groups[].selected_option_id` 选自提时段；时段选项由服务端生成（未来 7 天的整点），选中的时间即友宝 `pull_time`。

### 7.2 会话实体

```json
{
  "ucp": { "version": "2026-08-25", "status": "success",
           "capabilities": { "dev.ucp.shopping.checkout": [{ "version": "2026-08-25" }],
                             "dev.ucp.shopping.fulfillment": [{ "version": "2026-08-25" }],
                             "com.xiaopingfeng.vendling.approval": [{ "version": "2026-09-09" }],
                             "com.xiaopingfeng.vendling.sku": [{ "version": "2026-09-09" }] },
           "payment_handlers": { "com.xiaopingfeng.vendling.on_account": [{ "id": "youbao_account", "version": "2026-09-09" }] } },
  "id": "po_20260909_001",
  "status": "requires_escalation",
  "currency": "CNY",
  "vendor": "youbao-wholesale",
  "line_items": [
    {
      "id": "li_1",
      "item": { "id": "youbao-wholesale:10023", "title": "三得利 乌龙茶 500ml", "price": 5700,
                "quantity_unit": { "unit": "BX", "display_text": "箱", "contains": 15 } },
      "quantity": 2,
      "totals": [{ "type": "subtotal", "amount": 11400 }, { "type": "total", "amount": 11400 }]
    },
    {
      "id": "li_2",
      "item": { "id": "youbao-wholesale:10088", "title": "红牛 250ml", "price": 480,
                "quantity_unit": { "unit": "EA", "display_text": "罐" } },
      "quantity": 6,
      "totals": [{ "type": "subtotal", "amount": 2880 }, { "type": "total", "amount": 2880 }]
    }
  ],
  "fulfillment": {
    "methods": [
      {
        "id": "fm_shipping", "type": "shipping", "line_item_ids": ["li_1", "li_2"],
        "destinations": [{ "type": "shipping_address", "id": "dest_1", "street_address": "…", "first_name": "张三", "phone_number": "138…" }],
        "selected_destination_id": "dest_1",
        "groups": [{ "id": "grp_1", "line_item_ids": ["li_1", "li_2"],
                     "options": [{ "id": "opt_std", "title": "友宝配送", "totals": [{ "type": "total", "amount": 0 }] }],
                     "selected_option_id": "opt_std" }]
      }
    ]
  },
  "totals": [
    { "type": "subtotal", "amount": 14280 },
    { "type": "fulfillment", "amount": 0 },
    { "type": "total", "amount": 14280 }
  ],
  "payment": {
    "instruments": [{ "id": "instr_account", "handler_id": "youbao_account", "type": "on_account", "selected": true,
                      "display": { "customer_code": "NBJ2…" } }]
  },
  "messages": [
    { "type": "warning", "code": "price_estimated", "path": "$.line_items[1]",
      "content": "单价由箱价换算，实际以友宝对账为准" },
    { "type": "error", "code": "approval_required", "severity": "requires_buyer_review", "path": "$",
      "content": "estimated cost 142.80 exceeds run budget 100.00 — needs owner approval" }
  ],
  "actions": {
    "com.xiaopingfeng.vendling.approval": [{ "id": "dec-1757400000000-3" }]
  },
  "links": [{ "type": "terms_of_service", "url": "https://open.uboxol.com/terms" }],
  "continue_url": "https://vendling.xiaopingfeng.com/tasks",
  "expires_at": "2026-09-10T14:03:00+08:00"
}
```

- `item.price` 是**所选单位**一件的价格（箱行是箱价，个行是单价），行 `totals` = `price × quantity`。这是 UCP 的规则：`price` 按 `quantity_unit.unit` 计。
- 服务端在响应里回显 `item.quantity_unit`（UCP 要求非 `each` 的行必须带），并补上 `display_text` / `contains`。
- `vendor`（扩展）：本单的采购命名空间，建单后不可变。
- 按个下单的行会附一条 `price_estimated` 警告（`type: "warning"`，不阻塞）：友宝只公布箱价，单价是换算的。

### 7.3 状态机

UCP 的六个状态，在采购场景里各自的含义：

| `status` | 含义 | 进入条件 | 出去 |
|---|---|---|---|
| `incomplete` | 信息不全 | 缺联系人 / 地址 / 自提时段；某行命中 `hardNoGos`（`hard_no_go`，永远过不去） | `PUT` 补齐 |
| `requires_escalation` | 要人批 | 预估金额 > `rules.spendingLimitPerRun`，或处于试用期 `probationUntil` | 运营者在 `continue_url` 或 §11 审批；批准 → `ready_for_complete`，驳回 → `canceled` |
| `ready_for_complete` | 可以提交 | 信息齐、护栏过（或已批） | `POST …/complete` |
| `complete_in_progress` | 已提交，等供应商 | 上游请求已发出、未回 | 由服务端推进 |
| `completed` | 已下单 | 友宝 `code = 1`，返回 `order_code` | 终态；`order` 字段出现 |
| `canceled` | 作废 | 主动取消、审批驳回、`expires_at` 过期（24 小时） | 终态 |

**紧急停机**（`rules.killSwitchEngaged`）不是一个状态：任何时候 `complete` 都会被拒，
返回当前会话 + `kill_switch_engaged`（`requires_buyer_review`），会话本身不动，开关关掉后可以再试。
这与现有 `killSwitchBlocks()` 行为一致（读不到规则时 `guard_unverifiable` 503，**拒绝而非放行**）。

### 7.4 提交

```http
POST /checkout-sessions/po_20260909_001/complete
Idempotency-Key: po_20260909_001
{
  "payment": { "instruments": [{ "id": "instr_account", "handler_id": "youbao_account", "type": "on_account" }] },
  "confirm": true
}
```

- `confirm` 是扩展字段，**必须是 JSON 布尔 `true`**。字符串 `"true"`、数字 `1` 一律 `400 confirmation_required`。现有路由已经这样做（测试 `youbao-routes.test.ts` 锁定），原因是曾有调用方把布尔序列化成字符串 `"false"` 还被放行。
- 成功：`status: "completed"`，并带 `order: { "id": "po_20260909_001", "label": "<友宝 order_code>", "permalink_url": "https://vendling.xiaopingfeng.com/ucp/v1/orders/po_20260909_001" }`。
- 供应商拒单：`200` + `supplier_rejected`，`status` 回到 `ready_for_complete`，`content` 带上游原文 `msg`。
- 每次提交无论成败都写一条事件（`kind: youbao_note`）到 §12 的事件流。花真钱的调用不能是黑箱。

### 7.5 请求 → 友宝字段

`vendor = youbao-wholesale` 时的翻译（元气接入后是另一张表，同一份请求）：

| 结账字段 | 友宝 `create-order/zp` |
|---|---|
| `id` | `out_trade_no` |
| `line_items[].item.id` 去掉 `youbao-wholesale:` 前缀 | `product_list[].product_id` |
| `line_items[].quantity_unit.unit` = `BX` / `EA`（或省略） | `product_list[].unit` = `1` / `2` |
| `line_items[].quantity` | `product_list[].product_num`（箱数或个数，随 `unit`） |
| `fulfillment.methods[0].type` = `shipping` / `pickup` | `pick_up_type` = `1` / `2` |
| 目的地 `first_name` / `phone_number` / `street_address`（+ `extended_address`） | `contact_name` / `contact_phone` / `address` |
| `selected_destination_id` = `factory:<id>` | `factory_id` |
| 选中自提时段 `options[].id` 对应的时间 | `pull_time` |
| 配送费选项 `totals[type=fulfillment]` | `product_list[].delivery_charge`（友宝按行收，适配层按行摊） |
| — | `customer_code`（环境变量，不出现在接口里） |

---

## 8. 订单 Order

能力：`dev.ucp.shopping.order` · 扩展：`com.xiaopingfeng.vendling.order`（列表查询、机器 / 交易状态字段）

UCP 的 Order 是"结账之后发生的一切的当前快照"：买了什么、怎么送、送到哪一步、有没有退款。
本系统有两类订单，同一个实体形状，用 `kind` 区分：

| `kind` | 谁是 Business | 数据来源 | ID |
|---|---|---|---|
| `purchase`（采购单） | 友宝批发 | `get-logistics/zp` | PO 号（§7） |
| `sale`（机器交易） | 本系统 / 机器 | 货柜 `trade_page` | 友宝 `outOrderNo` |

| 操作 | 方法 | 端点 | 状态 |
|---|---|---|---|
| Get Order | `GET` | `/orders/{id}` | **[映射]** 采购单：`wholesale.getOrderStatus()` 有实现无路由；交易：从流水按 ID 取 |
| List Orders（扩展） | `GET` | `/orders?kind=sale&location=&from=&to=&cursor=&limit=` | **[有]** `GET /api/youbao/orders?vmId=&start=&end=` |
| Order Event Webhook | `POST` | 平台提供的 URL | **[缺]** 见 §12 |

### 8.1 采购单（`kind: purchase`）

```json
{
  "ucp": { "version": "2026-08-25", "status": "success" },
  "id": "po_20260909_001",
  "label": "UB2026090912345",
  "kind": "purchase",
  "checkout_id": "po_20260909_001",
  "permalink_url": "https://vendling.xiaopingfeng.com/ucp/v1/orders/po_20260909_001",
  "currency": "CNY",
  "line_items": [
    { "id": "li_1", "item": { "id": "youbao-wholesale:10023", "title": "三得利 乌龙茶 500ml", "price": 5700,
                              "quantity_unit": { "unit": "BX", "display_text": "箱", "contains": 15 } },
      "quantity": { "original": 2, "total": 2, "fulfilled": 0 },
      "totals": [{ "type": "subtotal", "amount": 11400 }, { "type": "total", "amount": 11400 }],
      "status": "processing" }
  ],
  "fulfillment": {
    "expectations": [
      { "id": "exp_1", "line_items": [{ "id": "li_1", "quantity": 2 }], "method_type": "shipping",
        "destination": { "street_address": "…", "address_country": "CN" }, "description": "友宝配送中" }
    ],
    "events": [
      { "id": "fe_1", "occurred_at": "2026-09-09T14:05:00+08:00", "type": "processing",
        "line_items": [{ "id": "li_1", "quantity": 2 }], "description": "已接单" }
    ]
  },
  "adjustments": [],
  "totals": [{ "type": "subtotal", "amount": 14280 }, { "type": "fulfillment", "amount": 0 }, { "type": "total", "amount": 14280 }],
  "supplier_status": { "code": 2, "description": "待发货", "mapped": "ordered" },
  "logistics": []
}
```

友宝 `order_status` → UCP 的映射与代码 `STATUS_MAP` 一致：

| 友宝 `order_status` | 适配层 `mapped` | 行 `status` | 追加的 `fulfillment.events[].type` |
|---|---|---|---|
| 1、2、3、7、8、9 | `ordered` | `processing` | `processing` |
| 4 | `arrived` | `fulfilled`（`fulfilled = total`） | `delivered` |
| 5、6 | `cancelled` | `removed`（`total = 0`） | `canceled`，并加 `adjustments[{type:"cancellation"}]` |
| 其他 / 缺失 | `ordered` | `processing` | — |

`supplier_status`（原始码 + 描述）和 `logistics[]`（友宝物流条目原样透传）是扩展字段；
UCP 的 `events[]` 是从它们**推导**的规范视图，不是替代。友宝各码的确切含义以其 `order_status_desc` 为准。

### 8.2 机器交易（`kind: sale`）

```http
GET /orders?kind=sale&location=12345678&from=2026-09-09T00:00:00%2B08:00&to=2026-09-09T23:59:59%2B08:00&limit=100
```

```json
{
  "ucp": { "version": "2026-08-25", "status": "success",
           "capabilities": { "dev.ucp.shopping.order": [{ "version": "2026-08-25" }],
                             "com.xiaopingfeng.vendling.order": [{ "version": "2026-09-09" }] } },
  "orders": [
    {
      "id": "2026090913001234",
      "kind": "sale",
      "checkout_id": "2026090913001234",
      "permalink_url": "https://vendling.xiaopingfeng.com/ucp/v1/orders/2026090913001234",
      "currency": "CNY",
      "line_items": [
        { "id": "2026090913001234-8837", "item": { "id": "youbao-vm:8837", "title": "红牛 250ml", "price": 600 },
          "quantity": { "original": 1, "total": 1, "fulfilled": 1 },
          "totals": [{ "type": "subtotal", "amount": 600 }, { "type": "total", "amount": 600 }],
          "status": "fulfilled" }
      ],
      "fulfillment": {
        "expectations": [
          { "id": "exp_1", "line_items": [{ "id": "2026090913001234-8837", "quantity": 1 }],
            "method_type": "vending_dispense",
            "destination": { "street_address": "科学院南路 2 号 搜狐网络大厦", "extended_address": "11F", "address_country": "CN" },
            "description": "机器即时出货" }
        ],
        "events": [
          { "id": "fe_1", "occurred_at": "2026-09-09T13:00:12+08:00", "type": "dispensed",
            "line_items": [{ "id": "2026090913001234-8837", "quantity": 1 }] }
        ]
      },
      "adjustments": [],
      "totals": [{ "type": "subtotal", "amount": 600 }, { "type": "total", "amount": 600 }],
      "location": "12345678",
      "location_name": "搜狐网络大厦11层",
      "trade_status": "TRADE_SUCCESS_MANUAL",
      "trade_status_label": "交易成功"
    }
  ],
  "pagination": { "cursor": "eyJwYWdlIjoyfQ", "has_next_page": true, "total_count": 243 }
}
```

字段映射（友宝 `trade_page` → UCP）：

| 友宝 | UCP |
|---|---|
| `outOrderNo` | `id`；`checkout_id` 同值（售货机没有独立的结账会话，UCP 要求该字段必填，故同号） |
| `innerCode` | `location`（扩展）；`fulfillment.expectations[].destination` 从该机器档案取地址 |
| `nodeName` | `location_name`（扩展） |
| `tradeStatus` / `tradeStatusLabel` | `trade_status` / `trade_status_label`（扩展，原样） |
| `totalFee`（元，浮点） | `totals[type=total].amount = round(totalFee × 100)` |
| `createTime`（北京时间，无标记） | `fulfillment.events[0].occurred_at`，按 §3.5 解析 |
| `goodsDetailList[]` 每项 | 一个 `line_items[]`，`quantity` 恒为 1（友宝一行一件） |
| `goodsDetailList[].goodsId` | `item.id` = `youbao-vm:<goodsId>`；`title` 从该机器库存目录反查，查不到用 ID |
| `goodsDetailList[].goodsPrice`（分） | `item.price` 与行 `totals` |
| `goodsDetailList[].cost`（分） | **不映射**。本账号上恒等于 `goodsPrice`，无信息量；见附录 A.2.3 |
| `goodsDetailList[].orderStatus` | 见下表 |

`orderStatus` → 行状态与调整：

| 友宝 `orderStatus` | 行 `status` | `quantity` | `adjustments[]` |
|---|---|---|---|
| `1` 已支付 | `fulfilled` | `{1,1,1}` | — |
| `0` 未支付 | `processing` | `{1,1,0}` | — |
| `2` 已退款 | `removed` | `{1,0,0}` | `{ type: "refund", status: "completed", line_items: [{id, quantity: -1}], totals: [{type:"total", amount: -600}] }` |
| `3` 退款失败 | `fulfilled` | `{1,1,1}` | `{ type: "refund", status: "failed" }` |
| `4` 支付取消 | `removed` | `{1,0,0}` | `{ type: "cancellation", status: "completed" }` |

**只有 `orderStatus = 1` 的行进入销售统计**（与 `sync.ts` 一致）；列表接口缺省 `trade_status = TRADE_SUCCESS_MANUAL`，传 `trade_status=all` 取全部。

**账户级查询**：友宝流水没有机器过滤，`location` 参数是适配层在全量结果上做的筛选。
因此多机器线路上分页要跨机器完整翻页，不能"每机取第一页"——那会让低销量机器的历史被高销量机器挤掉，
`sync.ts` 的注释记录了这个真实事故。窗口上限 20 页 × 100 条，超过时响应带 `warning: "history_truncated"`。

---

## 9. 扩展：定价 Pricing

能力：`com.xiaopingfeng.vendling.pricing` · 状态 **[有]** = `POST /api/youbao/price`

改的是**真实机器上顾客看到的价格**。UCP 没有"商家改自己售价"的能力（它站在买方视角），
所以这是纯扩展，但复用 UCP 的 `Price` 类型、`messages[]` 错误模型和 `requires_buyer_review` 审批语义。

```http
PUT /locations/12345678/prices
Idempotency-Key: 4b1c…
{
  "prices": [
    { "item": { "id": "youbao-vm:8837" }, "price": { "amount": 650, "currency": "CNY" } }
  ],
  "confirm": true
}
```

```json
{
  "ucp": { "version": "2026-08-25", "status": "success",
           "capabilities": { "com.xiaopingfeng.vendling.pricing": [{ "version": "2026-09-09" }] } },
  "location": "12345678",
  "updated": [
    { "item": { "id": "youbao-vm:8837" }, "previous": { "amount": 600, "currency": "CNY" }, "price": { "amount": 650, "currency": "CNY" } }
  ]
}
```

规则：

1. `item.id` 必须是 `youbao-vm:` 命名空间（`400 namespace_mismatch`），适配层去掉前缀后是友宝 `productId`。`price.amount` 必须是正整数（分），`currency` 必须是 `CNY`。友宝字段 `productPrice` 直接收分。
2. `confirm` 必须是布尔 `true`（同 §7.4）。
3. 紧急停机时 `409 kill_switch_engaged`。
4. **价格上限护栏**：`|new − previous| > rules.priceCapPerItem` 时**不执行**，返回 `200 approval_required` 并生成待审批决策（`kind: price_change`），批准后由服务端执行。`previous` 从该机器最近一次库存同步取。
5. 无论成败写事件 `youbao_price_change`。

> **与现状的差距**：`rules.ts` 里有 `checkPriceChange()`，`device.ts` 的注释也要求调用方先跑它，
> 但现有 `POST /api/youbao/price` 只做了第 2、3、5 条，**没有接价格上限护栏**（第 4 条），
> 同样 `POST /api/youbao/order` 也没有接 `checkRestockBudget()`。两条真实写路径绕过了 README
> 承诺的"规则在代码里校验"。本规范把护栏定为必需项；实现时应从 `tools/pipeline.ts` 的 `runTool` 走。

---

## 10. 扩展：补货 Replenishment

能力：`com.xiaopingfeng.vendling.replenishment`

补货有三个不同的对象，容易混：

| 对象 | 是什么 | 谁执行 | 花不花钱 |
|---|---|---|---|
| **计划 Plan** | 策略算出来的"每个货道现在该订多少" | 本系统，每日 | 否 |
| **补货行程 Run** | 一次出门要跑的机器、要带的货、预估成本；可下单、可收货 | 运营者 | 下单那一步花 |
| **补货推荐 Recommendation** | 给友宝自家运维队伍的"往这台机器装什么"的提示 | 友宝 | 否 |

Run 的形状**刻意贴近 UCP Order**：行项目、按机器分组的履约期望、追加式的履约事件、金额汇总——
这样运营者的 Dashboard 和上游采购单可以用同一套渲染。

| 操作 | 方法 | 端点 | 状态 |
|---|---|---|---|
| 当前计划 | `GET` | `/replenishment/plan` | **[有]** `GET .../restock/plan` |
| 列出行程 | `GET` | `/replenishment/runs?status=` | **[映射]** `state.restockRuns` |
| 取一个行程 | `GET` | `/replenishment/runs/{id}` | **[映射]** |
| 生成行程 | `POST` | `/replenishment/runs` | **[有]** `POST .../run/restock` |
| 下单 | `POST` | `/replenishment/runs/{id}/place` | **[有]** `POST .../restock/place-order`（当前发给模拟供应商） |
| 收货 | `POST` | `/replenishment/runs/{id}/receive` | **[有]** `POST .../restock/receive` |
| 预测评分 | `GET` | `/replenishment/score?horizon_days=7` | **[有]** `GET .../restock/score` |
| 向友宝推荐 | `POST` | `/locations/{id}/restock-recommendations` | **[有]** `POST /api/youbao/restock-recommend` |

### 10.1 计划

```json
{
  "ucp": { "version": "2026-08-25", "status": "success" },
  "strategy_version": "v2-weekshape",
  "params": { "window_days": 21, "cover_days": 7, "safety_days": 2, "min_order_qty": 3, "max_order_qty": 40, "…": "…" },
  "lead_time": { "days": 1.6, "source": "measured", "samples": 7 },
  "stock_history_points": 1240,
  "measured_slots": 18,
  "plans": [
    {
      "slot_id": "12345678-8837", "location": "12345678", "item": { "id": "youbao-vm:8837", "title": "红牛 250ml" },
      "stock": 7,
      "demand": { "daily_rate": 0.52, "naive_daily_rate": 0.48, "available_days": 19, "empty_days": 2, "closed_days": 0, "measured": true },
      "days_of_cover": 13.4,
      "stockout_at": "2026-09-22T00:00:00+08:00",
      "recommendation": { "action": "hold" }
    },
    { "slot_id": "12345678-9120", "item": { "id": "youbao-vm:9120", "title": "三得利 乌龙茶 500ml" }, "…": "…", "recommendation": { "action": "order", "quantity": 20 } }
  ]
}
```

`lead_time.source` 是 `measured`（从历史行程的下单 → 收货实测 p90）或 `stated`（还不够样本，用参数），
必须原样透出——按"说的 2 天"和按"测的 9 天"做计划是两回事，读的人不该猜。`demand.measured = false`
表示需求率是从缺货期推断的，不是观测。

### 10.2 行程（Run）

```json
{
  "ucp": { "version": "2026-08-25", "status": "success" },
  "id": "run-1757404800000",
  "status": "approved",
  "week_of": "2026-09-08",
  "currency": "CNY",
  "line_items": [
    { "id": "12345678-9120", "location": "12345678", "item": { "id": "youbao-vm:9120", "title": "三得利 乌龙茶 500ml", "price": 380 },
      "source": { "sku_id": "youbao-wholesale:10023", "quantity_unit": { "unit": "EA" } },
      "quantity": { "original": 20, "total": 20, "fulfilled": 0 },
      "totals": [{ "type": "subtotal", "amount": 7600 }, { "type": "total", "amount": 7600 }],
      "status": "processing" }
  ],
  "fulfillment": {
    "expectations": [
      { "id": "stop_1", "line_items": [{ "id": "12345678-9120", "quantity": 20 }], "method_type": "operator_visit",
        "destination": { "street_address": "…", "extended_address": "11F" }, "description": "第 1 站，约 12 分钟" }
    ],
    "events": [
      { "id": "re_1", "occurred_at": "2026-09-09T04:00:00+08:00", "type": "planned",  "line_items": [] },
      { "id": "re_2", "occurred_at": "2026-09-09T09:12:00+08:00", "type": "approved", "line_items": [], "description": "resolved by 飞书 open_id ou_…" }
    ]
  },
  "totals": [{ "type": "subtotal", "amount": 7600 }, { "type": "total", "amount": 7600 }],
  "estimated_minutes": 12,
  "cost_is_estimated": true,
  "approval": { "required": true, "id": "dec-1757404800000-1", "approved": true },
  "placed_at": null,
  "delivered_at": null
}
```

| `status` | 条件 |
|---|---|
| `blocked` | 紧急停机时生成，`line_items` 为空。**和"没什么要补"不是一回事**，所以是独立状态而不是空数组 |
| `nothing_to_do` | 没有货道需要补 |
| `pending_approval` | 预估成本 > `spendingLimitPerRun`，决策未批 |
| `rejected` | 决策被驳回 |
| `approved` | 可下单（不需审批的行程直接是这个） |
| `placed` | 已下单（`placed_at`），等收货 |
| `delivered` | 已收货（`delivered_at`），库存已加回 |

- **下单** `POST …/place`：紧急停机 `409`；已下单 `409 already_placed`；待审批 `409 approval_required`；空行程 `400`。行项目是机内 SKU（`youbao-vm:`），下单前先经 §5.4 `resolve` 得到每行的 `source`（采购命名空间的 `sku_id` + 计量单位，缺省按个）；有一行解析不到就 `200 unresolved_sku`，整个行程不下单。当前实现把行项目交给 `SupplierSimAgent`（模拟），真实供应商接入后这一步应改为按 `source` 创建 §7 的结账会话并附上 `checkout_id`。一个行程里的 `source` 若跨多个供应商，拆成多张结账单。
- **收货** `POST …/receive` `{ "delivered": [{ "slot_id": "12345678-9120", "quantity": 20 }], "note": "…" }`：`quantity` 非负整数（曾有负数把库存打成负值）；有容量时封顶；已收货 `409 already_delivered`。追加 `fulfillment.events[type=delivered]`。
- 已下单未收货的行程覆盖的货道，在下一次计划里**跳过**——否则从下单到到货之间每天都会重复计划同样的货，`place` 又照单全收，就会为同一批货付两次钱。
- `cost_is_estimated = true` 表示有行项目没有真实成本（批发目录里没见过），用零售价 × 0.55 估的；这个数字决定要不要审批，所以必须说明它是估的。

### 10.3 向友宝的补货推荐

```http
POST /locations/12345678/restock-recommendations
{
  "reference": "WS20260909001",
  "line_items": [
    { "item": { "id": "youbao-vm:8837" }, "quantity": 12, "reason": "近 21 天日均 0.52，货道 7 件，覆盖不到一个周期" }
  ]
}
```

- `reference` → 友宝 `wholesaleNo`（必填）；`item.id` 必须是 `youbao-vm:`，适配层去前缀并转成**数字** `productId`（友宝这里要数字）；`quantity` → `productCount`（> 0）；`reason` → `recommendReason`（必填，超过 100 字截断）。
- 不花钱、没有 `confirm`，但**受紧急停机约束**——它会推动友宝的人去往机器里装货，那是本系统在改变世界。
- 响应 `{ "location", "reference", "accepted": n }`。

---

## 11. 扩展：审批 Approval

能力：`com.xiaopingfeng.vendling.approval`（extends `dev.ucp.shopping.checkout`）· 状态 **[有]** = `POST .../resolve-decision`

UCP 里"要人看一眼"的表达是：`status: requires_escalation`、`severity: requires_buyer_review`、
`continue_url` 指向人操作的页面、`actions` 里挂上待办。这个扩展补上待办本身的读写：

| 操作 | 方法 | 端点 |
|---|---|---|
| 列出待办 | `GET` | `/approvals?status=pending&kind=restock_plan` |
| 取一个 | `GET` | `/approvals/{id}` |
| 批 / 驳 | `POST` | `/approvals/{id}` `{ "approved": true, "resolver": { "channel": "feishu", "chat_id": "oc_…", "sender_id": "ou_…" } }` |

```json
{
  "id": "dec-1757404800000-1",
  "kind": "restock_plan",
  "at": "2026-09-09T04:00:00+08:00",
  "summary": "restock run built: 1 stops, 3 items, ~12 min",
  "reasoning": "3 slot(s) short of cover … estimated cost ¥142.80 — exceeds run budget ¥100.00",
  "location": "12345678",
  "subject": { "type": "replenishment_run", "id": "run-1757404800000" },
  "status": "pending",
  "approved": null
}
```

- `kind` ∈ `swap | price_change | fault_flag | restock_plan | note`，即 `Decision.kind`。
- 谁能批：带 `resolver` 的请求（飞书卡片按钮）必须同时是已注册的管理群 **和** 已注册的管理员，否则 `403`；不带 `resolver` 的请求已经过 operator token 门，视为运营者本人。
- 已处理过的 `409`；不需要审批的 `409`。
- 每次处理写事件 `hitl_resolution`，`reasoning` 里记录是谁——回答不了"这笔钱谁批的"的审计不算审计。

---

## 12. 扩展：事件 Events 与订单 Webhook

能力：`com.xiaopingfeng.vendling.events` · 状态 **[有]**（详见 [`event-system.md`](event-system.md)）

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| 读历史 | `GET` | `/events?limit=50&location=&kind=` | 最新在前 |
| 写事件 | `POST` | `/events` | 其他 Agent 的接入点；**不去重**，幂等是写入方的事 |
| 实时流 | `WebSocket` | `/events/stream` | 连上先发 `event-history`（最近 50），之后每条 `event` |
| 订单 Webhook（UCP 标准） | `POST` | 平台在自己档案 `capabilities["dev.ucp.shopping.order"][].config.webhook_url` 里给的 URL | **[缺]** |

事件实体：

```json
{ "id": "evt-1757404812000-3", "occurred_at": "2026-09-09T13:00:12+08:00", "kind": "order",
  "summary": "order event: 2026090913001234 (交易成功) at 搜狐网络大厦11层 — 1 item(s), ¥6",
  "reasoning": "友宝 trade_page poll", "location": "12345678" }
```

`kind` 是开放字符串，现有值见 `event-system.md` 的表（`order`、`hitl_resolution`、`machine_alert`、
`youbao_note`、`youbao_price_change`、`kill_switch`、`sync_problem` …）。`occurred_at` 是**事情发生的时间**，
不是入库时间：一笔订单的事件用它自己的 `createTime`。

**订单 Webhook 与现状的关系**：UCP 规定 Business 主动 `POST` 完整的 Order 快照到 Platform 的 URL，
头带 `Webhook-Id`、`Webhook-Timestamp`、`UCP-Agent`，并用 RFC 9421 签名；Platform 必须快速回 2xx、
异步处理。本系统现在的等价物是"每 5 分钟轮询友宝流水 → 去重 → 追加 `kind: order` 事件 → WebSocket 推送"。
要对接一个 UCP 平台，只需在 `pollOrderEventsTask` 追加事件的同时，把 §8.2 的 Order 实体 `POST`
到对方 URL；去重集合 `order_events_seen` 已经存在，重试策略照 Standard Webhooks（5s → 10s → 2min → … 最多 7 次）。

---

## 13. 护栏与安全

本规范里每一个**改变世界**的操作，护栏都在代码里、在调用上游之前：

| 操作 | `confirm: true` | 紧急停机 | 规则护栏 | 审批 | 记录 |
|---|---|---|---|---|---|
| §7 采购下单 complete | 必需 | 拒 | `spendingLimitPerRun`、`hardNoGos`、试用期 | `requires_escalation` | 事件 |
| §9 改价 | 必需 | 拒 | `priceCapPerItem` | `approval_required` | 事件 |
| §10.2 行程下单 place | — | 拒 | 同采购 | 决策必须已批 | 决策 + 事件 |
| §10.3 补货推荐 | — | 拒 | — | — | — |
| §6.3 名册增删 / 同步 | — | 不受影响 | — | — | 事件（仅变化时） |
| 读操作 | — | **不受影响**——刚踩了刹车的人需要更多可见性，不是更少 | — | — | — |

- 护栏**失败关闭**：读不到规则就拒绝（`503 guard_unverifiable`），不放行。
- 模拟数据与真实数据不混：`POST .../simulate/purchase` 默认关闭；平板模拟器的遥测标 `simulated = 1`。伪造的销售会进需求测算和利润，污染的是决策不是噪音。
- 顾客侧（`/m/<id>`、`/face-api/*`）**不在本规范内**，它拿不到任何本文的写能力：那是另一个 Worker（`vendling-face`），没有 `YOUBAO_*` 凭证，只能通过固定白名单的桥接读库存、写意图事件（见 [`face-split.md`](face-split.md)）。
- 敏感字段：成本、利润只在 admin 层工具 `viewCostPrice` 暴露；本规范的目录响应**不含成本**，采购单的 `price` 是采购价，只对运营者可见。

---

## 附录 A. 上游友宝接口原始规范

按**实际能跑通的写法**记录，不按友宝文档——两者多处不一致，代码以能工作的为准
（源自 Project Vend China 的 `vend_tools/youbao_client.py` / `youbao_vm_client.py`，已在生产验证；
本仓库的移植在 `src/adapters/youbao/`，`GET /api/youbao/selftest` 在 workerd 里回放同一组签名向量）。

### A.1 批发接口（`open.uboxol.com`，智谱专用 `/zp` 端点）

| 项 | 值 |
|---|---|
| Base URL | `https://open.uboxol.com`（测试 `https://open.dev.uboxol.com`），环境变量 `YOUBAO_BASE_URL` |
| 身份 | `customer_code`（`YOUBAO_CUSTOMER_CODE`）+ `secretKey`（`YOUBAO_SECRET_KEY`）+ 友宝公开的 RSA-2048 公钥（硬编码，非秘密） |
| 方法 / 内容 | 全部 `POST`，`content-type: application/json` |
| 请求头 | `Signature`、`Timestamp`（毫秒）、`Nonce`（32 位 hex） |
| 请求体 | `{ "encryptedAESKey", "data", "timestamp", "nonce" }` |
| 成功判定 | 响应 `code === 1`；否则 `msg` 是错误原因 |

**加密与签名（每次请求）**：

1. 生成随机 AES-128 密钥 `k`（16 字节）。
2. `encryptedAESKey = base64( RSA_PKCS1v15( pubkey, utf8( base64(k) ) ) )` —— 注意先 base64 再转字节再加密，顺序不能反。
3. `data = base64( AES-128-ECB-PKCS7( k, JSON(body) ) )`。
4. `Signature = base64( SHA-256( "data=<data>&encryptedAESKey=<…>&nonce=<…>&timestamp=<…>&secretKey=<secretKey>" ) )` —— 参数按 key 升序拼 `k=v&`，末尾接 `secretKey=`。**是普通 SHA-256，不是 HMAC；AES 是 128 位不是 256**，文档写的都不对。

| 端点 | 请求体（明文，加密前） | 响应 `data` |
|---|---|---|
| `/external-wholesale/product-list/zp` | `{ customer_code }` | `{ factory_id, factory_address, product_list: [{ product_id, brand_name, product_name, price("元/箱"字符串), spec_str, stock, image_url, category_name }] }` |
| `/external-wholesale/create-order/zp` | `{ customer_code, out_trade_no, factory_id, pick_up_type: 1\|2, product_list: [{ product_id, product_num, unit: 1\|2, delivery_charge? }], contact_name, contact_phone, address }`（`pick_up_type = 1`）或 `{ …, pull_time }`（`= 2`） | `{ order_code }` |
| `/external-wholesale/get-logistics/zp` | `{ out_trade_no }` | `{ order_status: 1..9, order_status_desc, logistics: [] }` |

已知事实：`unit` 1 = 箱、2 = 个；`factory_id` 缺省 2021（`YOUBAO_DEFAULT_FACTORY_ID`）；
产品列表没有服务端搜索；`create-order` 是真实下单、真实记账，没有沙箱。

### A.2 货柜 / 设备接口（`uboxapi.ubox.cn`）

| 项 | 值 |
|---|---|
| Base URL | `https://uboxapi.ubox.cn`，环境变量 `YOUBAO_VM_BASE_URL` |
| 身份 | `app_id`（`YOUBAO_VM_APP_ID`）+ `app_key`（`YOUBAO_VM_APP_KEY`）——与批发是**两套独立凭证** |
| 方法 / 内容 | 全部 `POST`，JSON，明文（不加密） |
| 签名 | `sign = sha1_hex_lower( concat( sorted_scalars "k=v" 无分隔 ) + "_" + app_key )`；参与签名的只有**标量**字段（含 `app_id`，不含 `sign`），数组 / 对象字段（`productPrices`、`products`）**不参与**——带上会得到 `code 401`。字段名是 `sign`（文档写成 `sgin`） |
| 成功判定 | 响应 `code === 200`；`401` = 签名错误，`message` / `msg` 是原因 |

| 端点 | 请求体 | 响应 `data` |
|---|---|---|
| `/openinterface/vm_product_inventory` | `{ vmId }` | `[{ productId, productName, productCode(69码), productPrice(分), productInventory, productImgUrl }]` |
| `/openinterface/update_vm_product_price` | `{ vmId, productPrices: [{ productId, productPrice(分) }] }` | — |
| `/openinterface/trade_page` | `{ current, size, startCreateTime, endCreateTime, tradeStatus? }`，时间格式 `"YYYY-MM-DD HH:mm:ss"` 北京时间 | `{ total, pages, records: [{ outOrderNo, tradeStatus, tradeStatusLabel, innerCode, nodeName, totalFee(元, 浮点), createTime("YYYY-MM-DD HH:mm:ss.SSS" 北京时间), goodsDetailList: [{ goodsId, goodsPrice(分), cost(分), orderStatus: 0..4 }] }] }` |
| `/openinterface/save_restock_recommend` | `{ vmId, wholesaleNo, products: [{ productId(数字), productCount, recommendReason(≤100 字) }] }` | — |

#### A.2.1 `trade_page` 的坑（全部有测试覆盖）

- 文档写的路径 `/trade/page` 返回 404，实际是 `/openinterface/trade_page`；请求体是**平铺**的，不是文档里的 `orderPageReq` 包装。
- **账户级**：没有 `vmId` 过滤，所有机器的流水混在一起，按 `innerCode` 自己分拣，且必须完整翻页后再分拣。
- 时间无时区标记、按北京时间解释：给它的 `startCreateTime` / `endCreateTime` 也必须是北京时间字符串。
- 同一响应里两种单位：`totalFee` 是元，`goodsPrice` / `cost` 是分。
- `code 401`（密钥轮换后）也是 HTTP 200，如果不检查 `code`，看起来就像"这段时间零销售"——曾经导致订单流静默中断、货道均值算成 0、复盘信利润 ¥0。
- `tradeStatus` 常用 `TRADE_SUCCESS_MANUAL`。

#### A.2.2 `vm_product_inventory` 的坑

对不存在的 `vmId` 也返回 `code 200` 和一条像真的商品（¥0.1 椰子水，库存 69）。唯一的核对方法是看该
`innerCode` 在流水里出没出现过（见 §5.2）。

#### A.2.3 `cost` 字段

本账号上每一行的 `cost` 都等于 `goodsPrice`（550/550、600/600、270/270），没有批发信息。若当真采信，
系统会认为所有商品零毛利：复盘信报净利 0 且标成"实测"、补货按零售价估预算、货架分配无从排序。
适配层在 `cost > 0 && cost !== goodsPrice` 时才采信，否则成本视为未知。真实成本要从批发目录来。

### A.3 环境变量

| 变量 | 接口 | 说明 |
|---|---|---|
| `YOUBAO_BASE_URL` | 批发 | 缺省 `https://open.uboxol.com` |
| `YOUBAO_CUSTOMER_CODE` | 批发 | 客户编码 |
| `YOUBAO_SECRET_KEY` | 批发 | 签名密钥 |
| `YOUBAO_DEFAULT_FACTORY_ID` | 批发 | 缺省提货厂 |
| `YOUBAO_VM_BASE_URL` | 货柜 | 缺省 `https://uboxapi.ubox.cn` |
| `YOUBAO_VM_APP_ID` / `YOUBAO_VM_APP_KEY` | 货柜 | 一对 |

真值位置与其他凭证的用法见本机 skill `project-vend-credentials`；staging 环境**刻意不配**任何一项。

---

## 附录 B. 现有路由 ↔ 标准端点映射

| 标准端点（本规范） | 现有路由 | 状态 | 备注 |
|---|---|---|---|
| `GET /.well-known/ucp` | `src/ucp/profile.ts` | 有 | §4，公开 |
| `POST /catalog/search` `namespace=youbao-wholesale` | `GET /api/youbao/catalog?keyword=&limit=` | 有 | `src/ucp/catalog.ts`；旧路由并存 |
| `POST /catalog/search` `namespace=youbao-vm` | `GET /api/youbao/inventory?vmId=` | 有 | `src/ucp/catalog.ts` |
| `POST /catalog/lookup` / `/catalog/product` | `src/ucp/catalog.ts` | 有 | 按 ID 前缀分发；`youbao-vm` 需要 `filters.location` |
| `GET /skus/{id}`、`POST /skus/resolve`、`PUT /skus/{id}/aliases` | `src/ucp/skus.ts`，别名存 DO 的 `ucp_store` | 有 | §5.4；只有人工 / 条码来源参与下单 |
| `POST /locations/search` / `lookup` | `src/ucp/locations.ts` ← `.../state` + `.../machines/<id>/profile` | 有 | §6；`hours` 筛选未应用（无数据） |
| `PUT /locations/{id}` | `src/ucp/locations.ts` → `.../sync/youbao` + `.../machines/<id>/profile` | 有 | |
| `DELETE /locations/{id}` | → `DELETE .../sync/devices/<id>` | 有 | |
| `POST /locations/sync` | → `.../sync/youbao`（名册取自 `.../sync/devices`） | 有 | |
| `POST /checkout-sessions` … `/complete` | `POST /api/youbao/order {poId, items:[{productId, productNum, unit}], contactOverride, confirm}` | 有 | `src/ucp/checkout.ts`：会话存 `ucp_store`，Create / Get / Update / Complete / Cancel 齐全，**接了预算护栏、试用期、hardNoGos**；旧路由 `POST /api/youbao/order` 并存且仍未接护栏 |
| `GET /orders/{id}` `kind=purchase` | `src/ucp/orders.ts` → `wholesale.getOrderStatus()` | 有 | |
| `GET /orders?kind=sale` | `src/ucp/orders.ts` → `device.queryOrders()` 翻页 | 有 | 按 `location` 过滤时跨页收集，上限 20 页 |
| `PUT /locations/{id}/prices` | `src/ucp/pricing.ts` | 有 | **接了 `checkPriceChange`**：超上限存为待审批动作，批准即执行；旧路由并存且仍未接 |
| `POST /locations/{id}/restock-recommendations` | `src/ucp/replenishment.ts` → `device.saveRestockRecommend()` | 有 | |
| `GET /replenishment/plan` | → `.../restock/plan` | 有 | |
| `POST /replenishment/runs` | → `.../run/restock` | 有 | |
| `GET /replenishment/runs[/{id}]` | `src/ucp/replenishment.ts` ← `state.restockRuns` | 有 | 行上带 `source`（已确认别名） |
| `POST /replenishment/runs/{id}/place` | → `.../restock/place-order` | 有 | 仍发给模拟供应商；未解析的行只是 `unresolved_sku` 警告 |
| `POST /replenishment/runs/{id}/receive` | → `.../restock/receive` | 有 | |
| `GET /replenishment/score` | → `.../restock/score` | 有 | |
| `GET /approvals[/{id}]` | `src/ucp/approvals.ts` ← `state.decisionLog` | 有 | 带 `subject`（行程 / 结账 / 改价） |
| `POST /approvals/{id}` | → `.../resolve-decision`，批准后执行停放的改价 | 有 | |
| `GET/POST /events` | `src/ucp/approvals.ts` → `.../events` | 有 | |
| `WS /events/stream` | `GET /ucp/v1/events/stream` 只返回 `websocket_url`；流仍在 `WS /agents/vendling-agent/route-01` | 有·旧壳 | |
| Order Webhook（出站） | `pollOrderEventsTask` + `order_events_seen` | 缺 | §12 |

MCP 绑定的对应关系（`src/tools/catalog.ts`，按频道裁剪）：`checkStock` ≈ `catalog.search(inventory)`
的顾客视图（无成本）；`viewCostPrice` ≈ 同上的 admin 视图；`viewDecisionLog` ≈ `GET /approvals`；
`requestProduct` / `reportFault` 是顾客投票，不在本规范内。`adjustPrice` / `createOrder` 作为工具名
**刻意未实现**——改价与花钱不应成为一轮对话的副作用，它们只走本规范带 `confirm` 的 HTTP 路径。

---

## 附录 C. 非商品类外部接口一览

本规范之外、系统当前也在调用的外部服务，列出以便凭证与依赖盘点：

| 服务 | 端点 | 用途 | 代码 |
|---|---|---|---|
| 飞书 | `https://open.feishu.cn/open-apis`：`/auth/v3/tenant_access_token/internal`、`/im/v1/chats`、`/im/v1/messages?receive_id_type=chat_id`；入站 `POST /webhooks/feishu` | 审批卡片、现场任务卡片、群聊 / 私聊 Agent、ACL | `src/channels/feishu/` |
| 智谱 BigModel | `https://open.bigmodel.cn/api/paas/v4`（OpenAI 兼容） | 首选推理模型 | `src/reasoning/llm.ts` |
| OpenRouter | Vercel AI SDK provider | 备选推理（Anthropic 系列在该账号被 403，缺省 `deepseek/deepseek-chat`） | 同上 |
| Firecrawl | `https://api.firecrawl.dev/v1/search` | 用户层 / 顾客层联网搜索 | `src/search/firecrawl.ts` |
| Workers AI | binding `AI`，`@cf/openai/whisper-large-v3-turbo` | 顾客界面语音转文字 | `src/face/routes.ts` |
| wttr.in | `https://wttr.in/<city>?format=j1&lang=zh` | 机器所在城市天气，30 分钟缓存，失败不发 | `src/face/protocol.ts` |
| Cloudflare Sandbox | binding `Sandbox`（容器） | 飞书用户层 `runCode` 工具 | `src/tools/catalog.ts` |
