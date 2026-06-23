# 独立工程 · 零售在售新 SKU 自动发现（Amazon / Home Depot / Lowe's）

> 立档：2026-06-23　状态：**独立工程 · 待启动**（不在每日简报当前迭代内做，后续单独拉出来做）
> 归属：每日简报 backlog 的 B3 拆出；产物回流 `资产库/对手SKU库`(含 _database/sku.db)、`资产库/行业数据/北美商超产品追踪`，并进每日简报「新产品」栏。
> 目的：对手一旦在零售上新，自动发现 → SKU + 参数入库 + 提醒，补上"对手新品早信号"。
> 相对评论 VoC：**更轻、更便宜、可做性更高**（数据量小；Amazon 有官方接口）。

---

## 1. 本质：这是个"差集"问题
定期把"监控空间(对手品牌 × 品类 × 零售商)"的在售列表拉下来，跟 `sku.db` 比对，**多出来的就是新品**。核心=「列表 + diff」，难点在*怎么列*和*怎么判重*。

## 2. 关键差异：Amazon 这次有官方路
**Amazon PA-API 的 SearchItems 能按品牌/品类/关键词列商品**，返回 ASIN、标题、品牌、价格、参数、图（只是不返回评论）。官方、免费、稳。
> ⚠️ 门槛：需 Amazon Associates 账号且 180 天内 ≥3 笔达标销售才保留访问权。不做联盟站可能卡；卡了退回第三方。

HD/Lowe's 仍无官方搜索 API → 第三方或 sitemap。

## 3. 五条路线

| 路线 | 覆盖 | 稳定 | 成本 | 维护 | 适合 |
|---|---|---|---|---|---|
| **A. Amazon PA-API**（官方 SearchItems / New Releases） | 仅 Amazon | 高 | 免费(需联盟资格) | 低 | Amazon 新品发现首选 ⭐ |
| **B. 第三方搜索/商品 API**（Unwrangle / Rainforest / SerpApi / Oxylabs） | 三家 | 高 | 按结果 | 几乎零 | HD/Lowe's 主力 ⭐ |
| **C. Google Shopping API**（SerpApi） | 跨零售商一网 | 中高 | 按查询 | 低 | 一查多家一起扫，快速验证 |
| **D. Sitemap diff**（抓站点地图比 URL 增量 → 解析新页 JSON-LD） | HD/Lowe's | 中 | 极低 | 中高 | 省钱但要维护 |
| **E. Browser MCP / 现有商超追踪** | 三家 | 高 | $0 | 中 | 精确核对、深挖 |

## 4. 降噪关键：别扫全站，只盯对手
- **品牌店铺页 / 卖家页**：盯 Champion、WEN、Westinghouse、DuroMax、Firman、Mammotion、Segway 等品牌页，diff 新条目；
- **品类 New Releases / Best Sellers**（Amazon 按 BrowseNode 有新品榜）——天然新品早信号；
- 数据量小、信噪比高，A/B 都能直接打。

## 5. 推荐组合
- **Amazon**：有联盟资格 → A（免费）；没有 → B（Rainforest/Unwrangle）兜底。
- **HD/Lowe's**：B（Unwrangle 覆盖三家 / SerpApi 有 Home Depot）；想省 → D（sitemap diff）。
- **先验证**：用 C（Google Shopping）跑几个品类/品牌，一个 API 多家一起看，验证价值后再上专项。

## 6. 接入架构（和 vault 打通）
```
监控清单（对手品牌 × 品类 × 零售商，源自 B端对手库 + 对手SKU库）
 → A/B/C 拉在售列表 → 跟 sku.db 差集比对（按"品牌+型号"判重，非 ASIN，防变体误报）
 → 新 SKU：MiniMax 归一化标题 → 品牌/型号/功率段/价格 → 起草卡片进 对手SKU库
 → 飞书提醒"对手上新" + 进每日简报「新产品」栏
```

## 7. 三个坑
1. **监控空间界定**是真难点——太宽=噪音爆炸，必须锁到"你盯的对手品牌 + 功率段/品类"。`B端对手库`+`对手SKU库` 已划好名单。
2. **变体误报**——同款多 listing（颜色/捆绑/包装），按"品牌+型号"判重，别按 ASIN。
3. **身份对齐**——零售标题很脏，用 MiniMax 把"XXX 4500W Dual Fuel Inverter Generator Model ABC"归一化成 sku.db 里的型号，才能正确判重。

---

## 8. 子任务拆解（启动时按此走）
- [ ] **监控清单**：从 `B端对手库` + `对手SKU库` 导出"对手品牌 × 品类 × 零售商"watch list。
- [ ] **选型**：Amazon 先试 PA-API 资格；不行用 B。HD/Lowe's 用 B（Unwrangle/SerpApi）；可先用 C（Google Shopping）快速验证。
- [ ] **拉取层**：写 collector 按品牌页/品类 New Releases 拉在售列表，落 JSON 快照。
- [ ] **diff 引擎**：快照 vs `sku.db`，按"品牌+型号"判重出新 SKU（防变体误报）。
- [ ] **归一化 + 入库**：MiniMax 把脏标题归一成 品牌/型号/功率段/价格 → 起草卡片进 `对手SKU库`。
- [ ] **提醒**：飞书"对手上新" + 进每日简报新品栏。
- [ ] **预算闸**：第三方 API 设月度上限。

## 9. 不做什么
- 不扫全站（只盯 watch list）。
- 不自建大规模爬虫 + 代理（维护坑）。
- 当前每日简报迭代内**不接**；先把 P1/P2/P3 跑顺，这条作为独立工程择期启动。
- 与「电商评论 VoC」是两件事，但可共用同一第三方厂商选型（见 [电商评论VoC-方案.md](电商评论VoC-方案.md)）。
