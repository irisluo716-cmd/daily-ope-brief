# daily-ope-brief · 通机行业每日素材采集器

每天自动抓取**发电机 / 通用汽油发动机 / 割草机器人 / 水泵 / 微耕机 / 草坪车**六大品类、
覆盖全球（重点北美 + 欧洲）的 7 类情报，产出一份当日「原始素材」文件，供人工据此撰写简报。

> **设计原则：脚本只采集，不下结论。**
> 它只负责把当天的相关条目抓下来、去重、按 7 类归好；
> 排序、判断、推测标注（依据 / 样本 / 置信度）、中文成稿——全部由人 / AI 在素材基础上完成。
> 这样脚本永远不会自动编造「X% 用户」「主要对手」之类没根据的结论。

## 七类情报与数据源

| 类别 | 来源 | 是否需 key |
|---|---|---|
| 关税 | Federal Register API（USTR / BIS / CBP / ITC + 关键词）+ 预公示 | 否 |
| 排放 | Federal Register API（EPA + 发动机相关关键词） | 否 |
| CPSC 召回 | SaferProducts REST API（按品类关键词过滤） | 否 |
| 灾害天气预警 | NWS 活跃预警（聚合）+ NHC 活跃热带气旋 | 否 |
| 大公司动向 | Google News RSS（按品牌）+ 行业媒体 RSS | 否 |
| 新产品 | Google News RSS（按「发布 / 新品」主题） | 否 |
| 用户评论风向 | YouTube Data API（评测）+ Reddit 公开 RSS | YouTube 需 key |

**未自动接入（按需手动补）**：电商评论（Amazon / Home Depot / Lowe's，无干净 API、易被反爬）走人工浏览器抓取；
欧洲 Meteoalarm 预警、EU Safety Gate 召回、PowerOutage 停电数据为后续可加项。

## 产出

- `briefs/raw/YYYY-MM-DD.md` —— 人读的当日素材（按 7 类分组，每条含 标题 / 来源 / 日期 / 链接 / 摘录）
- `briefs/raw/YYYY-MM-DD.json` —— 机器可读版（备用）

## 本地运行

```bash
pip install -r requirements.txt
export YOUTUBE_API_KEY="你的key"     # 不设也能跑，只是没有 YouTube 那一类
python collect.py
```

## 自动运行（GitHub Actions）

`.github/workflows/daily.yml` 已配好：每天北京时间 06:00 自动采集并提交到仓库，也可在 Actions 页手动触发。

**需要配置的 Secret**：仓库 → Settings → Secrets and variables → Actions → New repository secret
- `YOUTUBE_API_KEY`　= 你的 YouTube Data API key
- `REDDIT_FEED_URL`（可选）= 你的 Reddit 认证 RSS feed 链接（形如 `https://www.reddit.com/.rss?feed=TOKEN&user=NAME`，或自定义 multireddit 的 `.rss?feed=` 链接）。数据中心 IP 下公开 `.json` 会 403，认证 `.rss` 可正常返回；建议建一个只含通机版块的自定义 feed，覆盖最干净。
- `MINIMAX_API_KEY` = MiniMax API key（用于 `synthesize.py` 的成稿合成 + AI 评审）。

## 成稿合成 + AI 评审（synthesize.py）

`collect.py` 只产**原始素材**；`synthesize.py` 把素材合成为**面向中国读者的中文成稿页面**：

- **模型 A 生成 → AI Judge 评审 → REJECT 把意见喂回重写（最多 3 次）→ 只有 PASS 才发布**。
- **日期由代码动态注入**进两段 Prompt（强制按今天的精确日期判定时效、剔除旧闻、写页眉）。
- 通过后渲染隆鑫 CI 的 HTML（含 Powered by Loncin 标识、每条带原文链接 + 中文小结、响应式适配手机），写：
  - `briefs/<日期>.html` —— 当日存档（**按天累积**）
  - `briefs/latest.html` —— **当日端口**（只显示今天）
  - `briefs/index.html` —— 存档索引（往日列表）
- 用 **MiniMax**（OpenAI 兼容 `/chat/completions`，仅 stdlib，无第三方 SDK）。模型 / 端点 / 时效线在 `sources.yaml` 的 `synthesis:` 段配置：默认 `generator: MiniMax-M2.5`、`judge: MiniMax-M2`（M 系列还有 M2.1 / M2.7，按账号可用模型调整）；`base_url` 默认国际版 `https://api.minimax.io/v1`，国内账号改对应域名；`new_within_days` 控制"多少天内算新闻"。

> ⚠️ 这些 key / token 绝不要写进代码或 `sources.yaml` 提交。脚本一律从环境变量读取。

## 给中国读者：镜像到 Gitee

GitHub 在国内访问不稳，建议把仓库镜像到 Gitee（码云）供阅读：

1. Gitee → 右上「+」→ **从 GitHub/GitLab 导入仓库**，填 GitHub 仓库地址；
2. 导入后在该 Gitee 仓库 → **管理 → 仓库镜像管理**，添加 **Pull 类型**镜像（源 = GitHub 仓库），设为定时同步；
3. 之后 GitHub 每日提交的素材会自动同步到 Gitee，读者直接在 Gitee 网页浏览 `briefs/raw/` 下的 `.md` 即可。

## 自定义（只改 `sources.yaml`）

- 加 / 减监控品牌 → 改 `news.company_queries`
- 调召回 / 天气 / 排放关键词 → 改对应 `keywords`
- 增删 Reddit 子版块 / YouTube 查询词 → 改 `reddit.subreddits` / `youtube.queries`
- 回看天数 → `lookback_days`

## 已知限制

- **Reddit RSS** 对数据中心 IP（GitHub Actions）会随机 429 限流；脚本带退避重试，仍失败的子版块会跳过并在素材末尾记一行说明，可手动补抓。
- 行业媒体 RSS 若改版 / 无 RSS 会自动跳过，不影响其他源。
- 各源「当天 0 条」可能是真没新事（如飓风淡季无活跃风暴），不一定是故障——看素材末尾「采集日志」的报错行区分。
