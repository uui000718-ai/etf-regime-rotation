# ETF Regime Rotation

一个零服务器成本的 ETF 买卖信号系统。目标是每天生成固定地址的 `latest.json`，并通过手机端 PWA 展示：

- 哪些板块 ETF 应该买入
- 哪些板块 ETF 应该卖出
- 纳斯达克 100 ETF 当前是进攻、均衡还是防守
- 每条信号的规则证据

本项目只面向 ETF，不做个股推荐。

## 架构

```text
GitHub Actions
  -> scripts/generate_latest.py
  -> site/data/latest.json
  -> GitHub Pages
  -> 手机端 PWA 读取固定 JSON 地址
  -> Server 酱每日摘要通知
```

## 本地运行

```powershell
python -m pip install -r requirements.txt
python scripts/generate_latest.py
python scripts/notify_serverchan.py
```

本地打开：

```text
site/index.html
```

## GitHub Pages

推到 GitHub 后，在仓库设置里启用 Pages：

- Source: GitHub Actions
- Workflow: `.github/workflows/update-signals.yml`

发布后固定 JSON 地址形如：

```text
https://<github_user>.github.io/<repo>/data/latest.json
```

## Server 酱

在 GitHub 仓库 `Settings -> Secrets and variables -> Actions` 添加：

```text
SERVERCHAN_SENDKEY=你的 Server 酱 SendKey
SITE_URL=https://<github_user>.github.io/<repo>/
```

`SERVERCHAN_SENDKEY` 支持：

- Server 酱 Turbo：`SCT...`
- Server 酱 3：`sctp...`

代码不会保存或打印 SendKey。

## 数据源

第一版免费数据源：

- 美股 ETF：YFinance
- A 股 ETF：AkShare

预留扩展：

- TickFlow
- Tushare
- Longbridge
- a-stock-data 直连端点
- FRED/VIX/美债利率

## 信号模型

```text
score = trend 30% + momentum 25% + flow 20% + risk 15% + event 10%
```

状态：

- `buy`: 买入候选
- `hold`: 持有
- `watch`: 观察
- `sell`: 卖出/回避

AI 后续只负责解释和反方检查，不直接生成买卖动作。
