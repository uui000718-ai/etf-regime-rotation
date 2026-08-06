# ETF 买卖信号系统：数据源、判断方法、功能布局与无成本部署

生成日期：2026-08-06

## 目标定义

你想要的不是“AI 推荐个股”，而是一个只覆盖 ETF 的投资决策系统：

- 美股：纳斯达克 100 ETF，例如 `QQQ`、`QQQM`。
- A 股：各板块 ETF，例如证券、银行、红利、消费、医药、芯片、半导体、人工智能、通信、机器人、新能源、光伏、电池、军工、电力、央企、科创、创业板等。
- 输出结果：告诉你哪些板块 ETF 应该买入、持有、观察、卖出。
- 运行频率：盘后每日更新，周末生成调仓建议。
- 原则：数据和规则决定信号，AI 负责解释原因、找风险、写报告，不直接决定买卖。

## 从开源项目学习什么

### 1. 从 `a-stock-data` 学数据源抓取

它最值得学习的是 A 股数据源封装方式：

- 行情：mootdx、腾讯财经、百度 K 线。
- 指数/ETF：腾讯财经、mootdx、百度 K 线。
- 板块：东财 push2、同花顺、行业/概念板块数据。
- 资金：东财 datacenter、东财 push2、板块资金流。
- 研报：东财 reportapi、同花顺一致预期、iwencai。
- ETF 期权：新浪 hq.sinajs，覆盖 50ETF、300ETF、科创50ETF、500ETF 期权。
- 备用源：交易所官方、巨潮、东财、同花顺、HKEX 等。

你的系统应该优先复用：

- A 股 ETF 行情。
- 行业/概念板块涨跌。
- 板块资金流。
- 行业研报标题和评级。
- ETF 期权隐含波动率。

不需要重点复用：

- 龙虎榜。
- 连板/打板。
- 个股互动易。
- 个股财报深挖。
- 人气榜。

这些数据会让 ETF 系统过度短线化。

### 2. 从 `daily_stock_analysis` 学自动化和多市场 fallback

它值得学习的是：

- A 股数据 fallback：Efinance、AkShare、Tushare、Pytdx、Baostock。
- 美股数据 fallback：YFinance、Longbridge。
- 新闻搜索 fallback：Anspire、SerpAPI、Tavily、Bocha、Brave、MiniMax、SearXNG。
- GitHub Actions 定时运行。
- 推送到飞书、企业微信、Telegram、Discord、Slack、邮件。
- Web 工作台、历史报告、回测和持仓记录。

你的系统可以借鉴它的运行方式：

- 每天自动拉数据。
- 自动生成 Markdown/HTML 报告。
- 自动推送摘要。
- 保存历史信号，用未来表现反向验证系统质量。

### 3. 从 `tickflow-stock-panel` 学功能布局和工程底座

它最接近你要做的系统：

- FastAPI 后端。
- React 前端。
- Polars 计算。
- DuckDB 查询。
- Parquet 存储。
- 指标流水线。
- 策略扫描。
- 回测。
- 监控。
- 盘后复盘。
- 板块/概念分析。

你的系统可以直接参考它的页面布局：

- Dashboard：今日市场状态。
- ETF Radar：ETF 买入/卖出信号。
- Sector Rotation：A 股板块轮动。
- Nasdaq 100：纳指 ETF 风险状态。
- Backtest：回测。
- Portfolio：目标仓位和当前仓位。
- Reports：每日报告、周报、月报。
- Settings：API Key、ETF 池、推送渠道。

### 4. 从 `ai-berkshire` 学判断纪律

它的价值不是数据，而是决策纪律：

- 强制输出结论。
- 交叉验证数据。
- 反方检查。
- 投资论文追踪。
- 组合复盘。
- 不让 AI 含糊其辞。

你的 ETF 系统应该改成：

- 买入必须满足硬条件。
- 卖出必须有触发条件。
- 观察必须说明缺哪一项。
- 每条建议必须给出证据。
- 每周检查上周信号是否有效。

### 5. 从 `TradingAgents-CN` 学多 Agent 分工

它偏重个股和交易框架，不建议完整引入。但可以学习角色结构：

- 市场 Agent：趋势、波动、成交。
- 新闻 Agent：政策、宏观、突发事件。
- 情绪 Agent：风险偏好、VIX、资金风险。
- 风控 Agent：回撤、相关性、拥挤度。
- 组合经理 Agent：最终权重建议。

## ETF 买入/卖出判断方法

不要把个股推荐方法原样搬过来。ETF 不看管理层、不看护城河，核心看四件事：

1. 趋势是否走强。
2. 相对强弱是否领先。
3. 资金是否持续流入。
4. 风险是否可控。

### 买入信号

一个 A 股板块 ETF 进入“买入”需要同时满足：

- 价格站上 20 日和 60 日均线。
- 20 日收益率排名进入 ETF 池前 30%。
- 所属行业/概念板块 5 日或 20 日资金流为正。
- 成交额不低于过去 60 日均值的 80%。
- 最近 20 日最大回撤低于阈值，例如 8%-12%。
- 没有单日暴涨后严重乖离，例如收盘价高于 20 日均线 12% 以上则不追。

一个纳指 100 ETF 进入“买入/加仓”需要满足：

- `QQQ` 或 `QQQM` 在 120 日或 200 日均线上方。
- 60 日动量为正。
- VIX 不处于极端风险区。
- 美债利率快速上行压力不明显。
- 纳指相对标普 500 不持续走弱。

### 卖出信号

A 股板块 ETF 触发“卖出/降仓”：

- 跌破 20 日均线，且 5 日资金流转负。
- 跌破 60 日均线。
- 从买入后回撤超过预设止损，例如 8%-10%。
- 板块相对强弱跌出 ETF 池前 50%。
- 出现单日放量长阴，且后续 2 个交易日不能修复。
- 同主题 ETF 普遍走弱，说明不是单只 ETF 流动性问题。

纳指 100 ETF 触发“卖出/降仓”：

- 跌破 200 日均线。
- 60 日动量转负。
- VIX 快速上行且纳指相对标普 500 走弱。
- 美债实际利率快速上升，对成长股估值形成压力。

### 持有信号

- 趋势仍在，但短期资金分歧。
- 排名没有继续上升，但未跌破风控线。
- 估值偏高但趋势未破。
- 持有收益未触发止盈或止损。

### 观察信号

- 板块刚启动，但成交额或资金流还没确认。
- 政策/产业催化出现，但价格还没确认。
- 技术形态改善，但仍在 60 日均线下方。
- 主题过热，等回踩。

## 推荐评分模型

每只 ETF 每天计算 100 分：

```text
总分 = 趋势 30% + 动量 25% + 资金 20% + 风险 15% + 事件/估值 10%
```

分类：

- `>= 75`：买入候选。
- `60-74`：持有或观察。
- `45-59`：弱观察。
- `< 45`：卖出或回避。

硬性否决：

- 日均成交额太低。
- 溢价率异常。
- 跟踪误差异常。
- 单日涨幅过大，乖离过高。
- 跌破中期趋势线。

## 网站功能布局

### 首页 Dashboard

显示：

- 今日总信号：进攻、均衡、防守。
- 纳指 100 ETF 状态。
- A 股板块 ETF 状态。
- 当前建议仓位：纳指、A 股板块、现金。
- 今日买入候选 TOP 5。
- 今日卖出/降仓 TOP 5。

### ETF Radar

表格字段：

- ETF 代码。
- ETF 名称。
- 所属主题。
- 最新价。
- 20/60/120 日收益。
- 趋势分。
- 资金分。
- 风险分。
- 总分。
- 状态：买入、持有、观察、卖出。
- 主要理由。

### Sector Rotation

显示：

- 行业/概念板块热力图。
- 板块 5 日、20 日、60 日强弱。
- 板块资金流排名。
- 对应 ETF 列表。

### Nasdaq 100

显示：

- `QQQ`/`QQQM` 趋势状态。
- 20/60/120/200 日均线。
- VIX。
- 美债利率。
- 纳指相对标普 500 强弱。
- 美股风险状态。

### Portfolio

显示：

- 当前持仓。
- 系统建议目标仓位。
- 需要买入/卖出的 ETF。
- 组合波动率。
- 最大回撤。
- 单主题暴露。

### Backtest

显示：

- 策略净值。
- 沪深 300、纳指 100 对比。
- 最大回撤。
- 夏普。
- 胜率。
- 年化收益。
- 换手率。
- 每次买卖记录。

### Reports

保留：

- 每日报告。
- 每周调仓报告。
- 每月复盘报告。
- AI 反方报告。

## 是否需要买服务器

不需要。

如果你的目标是个人使用、每天盘后更新、网页查看结果，完全可以零成本实现。

推荐架构：

- GitHub Actions：定时抓数据、算信号、生成 JSON/Markdown/HTML。
- GitHub Pages：托管静态网站。
- GitHub 仓库：保存历史数据和报告。
- 免费数据源：YFinance、AkShare、Baostock、部分东财/腾讯/新浪接口。
- 可选 token：Tushare、Longbridge、TickFlow，根据需要再配置。

这种架构没有后端常驻服务，所以不需要服务器。

## 零成本实现方案

### 方案 A：最稳的零成本静态网站

适合你现在的目标。

运行方式：

1. GitHub Actions 每天定时运行 Python 脚本。
2. Python 抓 ETF 数据。
3. 计算买入/卖出信号。
4. 生成 `data/signals.json`、`reports/daily.md`、`site/index.html`。
5. GitHub Pages 展示网页。

优点：

- 不用服务器。
- 不用数据库服务。
- 不用后端。
- 成本为 0。
- 历史数据可直接存在仓库或 GitHub Actions artifact。

缺点：

- 不是实时盘中系统。
- 交互能力有限。
- 私密持仓不适合放 public repo。

### 方案 B：Streamlit Community Cloud

适合快速做一个可交互的数据面板。

运行方式：

- Streamlit 免费托管 app。
- GitHub Actions 负责更新数据。
- Streamlit 读取 GitHub 仓库里的 JSON/CSV/Parquet。

优点：

- 开发最快。
- 图表和筛选器很容易做。
- 免费。

缺点：

- 免费资源有限。
- 在美国托管，国内访问可能不稳定。
- 不适合重计算，重计算应放 GitHub Actions。

### 方案 C：Vercel Hobby + GitHub Actions

适合做更像正式产品的前端。

运行方式：

- Vercel 托管静态 React/Next.js 页面。
- GitHub Actions 定时生成数据文件。
- 前端读取静态 JSON。

优点：

- 页面体验更好。
- 免费 Hobby 计划够个人项目使用。
- 自动 HTTPS。

缺点：

- 不适合长时间后端任务。
- 免费函数执行时间有限，抓数据和回测仍应放 GitHub Actions。

## 最推荐的无成本架构

```text
GitHub Actions
  ├─ 每天 18:30 抓 A 股 ETF、板块、资金流
  ├─ 每天美股收盘后抓 QQQ/QQQM、VIX、利率
  ├─ 计算 ETF 信号
  ├─ 生成 JSON/Markdown/HTML
  └─ 推送到 GitHub Pages

GitHub Pages
  └─ 展示 ETF Dashboard

本地电脑
  └─ 需要深度回测或开发时再运行
```

第一版不需要：

- 不需要云服务器。
- 不需要数据库服务器。
- 不需要 Redis/MongoDB。
- 不需要实时 WebSocket。
- 不需要登录系统。
- 不需要复杂 Agent 框架。

## MVP 开发清单

第一阶段：

- 建 ETF 池：`config/etf_universe_cn.yaml`、`config/etf_universe_us.yaml`。
- 写数据抓取器：`src/connectors/yfinance.py`、`src/connectors/akshare_cn.py`。
- 写信号计算：`src/signals/trend.py`、`src/signals/momentum.py`、`src/signals/risk.py`。
- 生成结果：`data/latest_signals.json`。
- 生成报告：`reports/daily.md`。
- 建静态网页：`site/index.html`。
- 建 GitHub Actions：每天自动运行。

第二阶段：

- 加板块资金流。
- 加行业/概念映射。
- 加回测。
- 加周报。
- 加飞书/企业微信推送。

第三阶段：

- 加 AI 解释和反方报告。
- 加组合仓位建议。
- 加美债、VIX、美元指数。
- 加 ETF 份额、溢价率、跟踪误差。

## 最终建议

如果你的目标是“每天告诉我哪个 ETF 应该买入、哪个应该卖出”，不要先做重型网站。先做一个静态网站 MVP：

- 数据每天自动更新。
- 表格清楚列出买入/持有/观察/卖出。
- 每个信号必须有规则证据。
- 周末才给调仓建议。
- AI 只负责解释，不负责拍脑袋。

这样可以零成本启动，而且更容易验证系统到底有没有用。

## 参考来源

- https://github.com/xbtlin/ai-berkshire
- https://github.com/simonlin1212/a-stock-data
- https://github.com/ZhuLinsen/daily_stock_analysis
- https://github.com/hsliuping/TradingAgents-CN
- https://github.com/shy3130/tickflow-stock-panel
- https://docs.github.com/en/actions
- https://docs.github.com/en/pages
- https://docs.streamlit.io/deploy/streamlit-community-cloud
- https://vercel.com/docs/plans/hobby
