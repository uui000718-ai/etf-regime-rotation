# ETF 投研项目方案：基于 5 个开源项目的取舍

生成日期：2026-08-06

## 一句话结论

这些项目不要直接合并。更合理的做法是：

- 用 `a-stock-data` 做 A 股 ETF、指数、板块、资金流、行业研报和 ETF 期权的数据参考层。
- 用 `tickflow-stock-panel` 做 A 股 ETF 轮动工作台的工程底座参考。
- 用 `daily_stock_analysis` 借鉴定时分析、日报、推送、多市场数据 fallback。
- 用 `ai-berkshire` 借鉴投研纪律、反证机制、组合复盘，而不是数据源。
- 用 `TradingAgents-CN` 借鉴多 Agent 角色分工，但不建议作为主依赖。

最终项目应是“ETF 数据雷达 + 板块轮动回测 + 每周仓位建议 + AI 归因与反方报告”，而不是 AI 荐股系统。

## 项目分别是干什么的

### 1. xbtlin/ai-berkshire

定位：AI 价值投资研究框架。它把巴菲特、芒格、段永平、李录等视角做成 Skills/Agent 工作流，强调多 Agent 独立研究、交叉验证、否决清单、反共识检查、投资论文追踪、组合复盘。

对 ETF 项目的价值：

- 有价值的是研究流程、纪律、反证机制。
- 不适合作为行情数据底座。
- ETF 不需要管理层深挖，但需要宏观环境、行业景气度、估值分位、资金流、趋势、回撤风险。

建议改造为 4 个 ETF Agent：

- 趋势/资金 Agent：看动量、均线、成交额、板块资金。
- 估值/赔率 Agent：看估值分位、股债性价比、风险溢价。
- 宏观/流动性 Agent：看利率、美元、人民币、VIX、政策环境。
- 反方/风控 Agent：专门找不能买、该降仓、信号失真的理由。

不建议照搬的部分：个股护城河、管理层、财报深挖、单公司估值。

### 2. simonlin1212/a-stock-data

定位：A 股全栈数据工具包，封装多个零鉴权或低鉴权数据源。README 描述其为 10 层架构、47 个端点、15 个数据源，覆盖行情、研报、资金、公告、板块、ETF 期权、舆情等。

对你的 ETF 项目最有价值的数据：

- 腾讯财经：ETF/指数行情、PE/PB、市值、换手率等。
- mootdx/腾讯/百度 K 线：A 股 ETF 和指数 K 线、均线、盘口。
- 东财 push2/datacenter：行业/概念板块涨跌、板块资金流、资金趋势。
- 东财行业研报：用于解释板块 ETF 背后的行业景气与催化。
- 新浪 ETF 期权：50ETF、300ETF、科创50ETF、500ETF 期权的 IV、希腊字母、T 型报价，适合做市场情绪和风险保护参考。
- 交易所/巨潮公告：对 ETF 本身价值有限，但对政策、监管、指数成分事件可作辅助。

对 ETF 低价值、应弱化的数据：

- 龙虎榜、打板、连板、炸板。
- 个股互动易、人气榜、个股概念命中。
- 个股股东户数、个股财报三表。

这些更适合个股短线或个股基本面，容易把 ETF 系统带偏成题材追逐。

### 3. ZhuLinsen/daily_stock_analysis

定位：LLM 驱动的多市场股票分析、定时运行和推送系统。支持 A 股、港股、美股、日股、韩股、台股和 ETF，提供行情、K 线、技术指标、新闻、公告、基本面、Web/桌面工作台、回测、持仓和多渠道推送。

对你的 ETF 项目最有价值的能力：

- 美股：YFinance 作为基础源，Longbridge 补量比、换手率、PE 等字段。
- A 股：AkShare、Tushare、Pytdx、Baostock、TickFlow 多源 fallback。
- 新闻搜索：Anspire、SerpAPI、Tavily、Bocha、Brave、MiniMax、SearXNG。
- 调度与推送：GitHub Actions、本地定时、Docker、企业微信/飞书/邮件等。
- 回测评估：可借鉴“AI 预测 vs 后续表现”的记录结构。

需要改造的地方：

- 它默认是自选股逐只分析。
- 你的项目应改成“ETF 池 + 板块轮动 + 仓位建议”。
- 不要让 AI 给每只成分股写长报告，ETF 决策应以组合、板块和指数为核心。

### 4. hsliuping/TradingAgents-CN

定位：中文增强版多智能体金融交易研究框架，支持 A 股/港股/美股，包含基本面、技术面、新闻、情绪、研究员、交易员、风控等角色，并有 FastAPI/Vue/MongoDB/Redis 等工程组件。

对你的 ETF 项目有价值的部分：

- 多 Agent 分工：技术面、新闻面、情绪面、风控辩论。
- 缓存、报告导出、批量分析、模拟交易等工程结构。
- 数据源统一管理：Tushare、AkShare、BaoStock；美股常见为 Finnhub/YFinance。

风险：

- 项目较重，偏交易框架和个股分析。
- README 显示混合许可证，部分目录商业使用需授权。
- 对 ETF 投资来说，复杂 Agent 不一定提高收益，可能增加不可控噪声。

建议：只借鉴角色设计，不把它作为项目主框架。

### 5. t.co 短链接对应的 shy3130/tickflow-stock-panel

定位：自托管 A 股量化工作台，基于 TickFlow 数据源，覆盖选股、指标流水线、回测、实时监控、盘后复盘、概念/行业分析和扩展数据。

对你的 ETF 项目最有价值：

- 数据落地：Polars + DuckDB + Parquet，很适合做 ETF 历史数据和因子表。
- 回测：支持 T+1、手续费、滑点、止损、净值、夏普、回撤、胜率。
- 板块分析：概念/行业涨幅轮动、领涨领跌主线、成分穿透。
- 监控：盘中价格/信号/异动规则和飞书推送。
- ETF/指数数据同步状态已有入口。

限制：

- 当前更偏 A 股个股/板块，纳指 100 ETF 需要自己补美股数据模块。
- TickFlow 权限可能分层，免费能力与实时数据能力要实测。

## 数据源优先级建议

### 美股纳斯达克 100 ETF

标的池：

- 主标的：`QQQM` 或 `QQQ`。
- 观察标的：`TQQQ`、`SQQQ` 只能用于增强或风控观察，不建议进入默认主策略。

数据源优先级：

1. YFinance：免费，适合日线、复权价格、成交量、股息。作为美股 ETF 历史数据主源。
2. Longbridge：补充实时行情、量比、换手、部分估值字段。适合盘中监控。
3. 新闻搜索源：Brave/SerpAPI/Tavily/Anspire，用于重大事件、FOMC、财报季、AI 半导体周期等解释。
4. 建议额外补充：FRED 利率、10Y 美债、实际利率、美元指数、VIX、Nasdaq/ETF 发行商持仓权重。

### A 股板块 ETF

数据源优先级：

1. TickFlow：如果可用，适合作为 A 股 ETF、指数、板块、分钟/日线数据主源。
2. a-stock-data：作为免费直连接口和备份源，尤其是腾讯财经、东财 push2、东财行业研报、ETF 期权、板块资金流。
3. AkShare：覆盖面广，适合补缺，但要做好接口失效和字段变更处理。
4. Tushare Pro：规范稳定，适合历史行情、指数、基金基础信息；需要 token 和权限。
5. Pytdx/mootdx/Baostock：行情和历史数据备用。
6. 新闻/研报：东财行业研报、财联社、搜索 API，主要用于解释板块轮动原因，不应直接生成买卖信号。

## 适合你的项目形态

项目名称建议：`etf-regime-rotation`，中文可叫 `ETF板块轮动系统`。

核心目标：

- 投资范围固定为：美股纳斯达克 100 ETF + A 股板块 ETF。
- 不做个股推荐。
- 用规则生成“可解释的仓位建议”，AI 只做归因、反证、摘要，不直接决定交易。
- 低频为主：日线级别、盘后决策、周度再平衡；盘中只做风险预警。

## 推荐系统架构

### 数据层

- `instrument_master`：ETF 清单、交易所、跟踪指数、费率、所属主题。
- `etf_daily`：OHLCV、复权价格、成交额、换手。
- `index_daily`：纳指 100、沪深 300、中证 500、科创 50、创业板、行业/概念指数。
- `board_flow_daily`：行业/概念涨跌、成交额、主力资金、5/20 日趋势。
- `macro_daily`：美债利率、VIX、美元指数、人民币汇率、A 股成交额。
- `news_events`：新闻、政策、研报标题、事件标签。

### 因子层

- 趋势：20/60/120/200 日均线、动量、突破、回撤。
- 相对强弱：ETF 相对沪深300/纳指100/自身板块指数的强弱。
- 资金：板块资金流、成交额放大、ETF 份额变化。
- 估值：行业 PE/PB 分位、股债性价比、纳指估值压力。
- 风险：最大回撤、波动率、VIX、汇率、相关性上升。

### 策略层

- 纳指核心仓：趋势过滤 + 风险 regime。例如 `QQQ/QQQM` 在 200 日线上方保持核心仓，下方分级降仓。
- A 股板块轮动仓：从 ETF 池中按 1/3/6 月动量、板块资金、估值分位、政策催化综合打分，取前 3-5 个。
- 防守仓：当 A 股和纳指都跌破风险线，提高现金或货币 ETF 权重。
- 禁止项：不追单日暴涨、不过度集中单一主题、不碰流动性差 ETF。

### AI 研究层

- 每日：生成“为什么今天变了”的归因，不预测涨跌。
- 每周：输出 ETF 评分表、入选/剔除原因、反方观点、下周观察点。
- 每月：检查策略是否漂移、回测表现是否恶化、仓位是否过度集中。

### 执行与通知层

- 盘后 18:30：同步 A 股数据，生成 A 股 ETF 轮动信号。
- 美股收盘后：同步 Nasdaq ETF 与宏观数据。
- 每周末：生成组合再平衡报告。
- 推送：飞书/企业微信/邮件。

## MVP 范围

第一版只做这些：

1. ETF 池
   - 美股：`QQQM`、`QQQ`。
   - A 股：30-80 只高流动性板块 ETF，覆盖证券、银行、红利、消费、医药、半导体、芯片、人工智能、通信、机器人、新能源、光伏、电池、军工、电力、央企、科创、创业板等。

2. 数据
   - 美股：YFinance。
   - A 股：TickFlow 或 AkShare/Tushare。
   - 额外接入：`a-stock-data` 的腾讯财经和东财板块资金流。
   - 存储：DuckDB + Parquet。

3. 信号
   - `trend_score`：价格是否在 60/120/200 日均线上方。
   - `momentum_score`：20/60/120 日收益排名。
   - `flow_score`：板块资金流 1/5/20 日。
   - `risk_score`：波动率、回撤、跌破均线、成交缩量。
   - `event_score`：政策/行业研报/新闻催化，只作为加减分。

4. 输出
   - 每日 ETF 雷达表：候选、持有、观察、剔除。
   - 每周调仓建议：目标权重、变动原因、风险检查。
   - 回测页：策略净值、最大回撤、夏普、胜率、换手率。

## 仓位规则模板

这只是系统规则模板，不构成投资建议。

- Nasdaq 100 ETF：30%-60% 核心仓。若价格在 200 日线上方且 60 日动量为正，维持；若跌破 200 日线或 VIX 明显升高，分级降仓。
- A 股板块 ETF：30%-60% 轮动仓。每周选综合得分前 3-5 个，每个 8%-15%，单主题上限 25%。
- 现金/货币基金 ETF：0%-40%。当两地市场均处风险状态或信号分散时提高。
- 单个 ETF 流动性门槛：日均成交额、规模、跟踪误差、费率都要过线。

## 最推荐的开发路径

### 路线 A：最快落地

- Fork `tickflow-stock-panel`。
- 保留它的 A 股数据、指标、回测、监控。
- 增加美股 ETF 数据适配器：YFinance/Longbridge。
- 把选股策略改成 ETF 池轮动策略。
- 加一个每周组合再平衡报告。

### 路线 B：更干净，长期更好

- 新建轻量项目：FastAPI + DuckDB + Polars + APScheduler + React。
- 数据连接器参考 `a-stock-data` 和 `daily_stock_analysis`。
- AI 报告模板参考 `ai-berkshire`。
- 只借鉴 `TradingAgents-CN` 的角色设计，不引入完整重型框架。

我更建议路线 B；如果目标是一个月内先跑起来，则选路线 A。

## 建议目录结构

```text
etf-regime-rotation/
  data/
    raw/
    parquet/
    duckdb/
  src/
    connectors/
      us_yfinance.py
      us_longbridge.py
      cn_tickflow.py
      cn_astockdata.py
      news_search.py
    universe/
      etf_universe_cn.yaml
      etf_universe_us.yaml
    features/
      trend.py
      momentum.py
      flow.py
      valuation.py
      risk.py
    strategy/
      regime.py
      rotation.py
      allocation.py
    backtest/
      engine.py
      metrics.py
    reports/
      daily.py
      weekly.py
      prompts/
    jobs/
      sync_daily.py
      run_after_close.py
      weekly_rebalance.py
  tests/
  .env.example
```

## 最终取舍

- 数据源主干：`TickFlow/Tushare/AkShare/a-stock-data` 管 A 股，`YFinance/Longbridge` 管美股。
- 工程底座：`tickflow-stock-panel` 的 Polars + DuckDB + Parquet + 回测/监控思想最贴近需求。
- 自动化：借 `daily_stock_analysis` 的 GitHub Actions/定时/推送模式。
- AI 工作流：借 `ai-berkshire` 的反证、结论纪律、组合复盘。
- 多 Agent：只轻量借鉴 `TradingAgents-CN`，不要把整个项目作为主依赖。

## 参考来源

- https://github.com/xbtlin/ai-berkshire
- https://github.com/simonlin1212/a-stock-data
- https://github.com/ZhuLinsen/daily_stock_analysis
- https://github.com/hsliuping/TradingAgents-CN
- https://github.com/shy3130/tickflow-stock-panel
- https://news.daheiai.com/realtime.php?file=quick_2026-07-02_1201
