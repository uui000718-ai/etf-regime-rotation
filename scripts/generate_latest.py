from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_PATH = ROOT / "config" / "etf_universe.json"
SITE_DATA_DIR = ROOT / "site" / "data"
LATEST_PATH = SITE_DATA_DIR / "latest.json"
REPORTS_DIR = ROOT / "reports"


@dataclass
class Signal:
    symbol: str
    name: str
    market: str
    theme: str
    role: str
    status: str
    score: float
    price: float | None
    change_20d_pct: float | None
    change_60d_pct: float | None
    trend_score: float
    momentum_score: float
    flow_score: float
    risk_score: float
    event_score: float
    reasons: list[str]
    warnings: list[str]
    data_quality: str


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_universe() -> dict[str, list[dict[str, str]]]:
    return json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))


def fetch_us_history(symbol: str, days: int = 420) -> pd.DataFrame:
    import yfinance as yf

    cache_dir = ROOT / "data" / "cache" / "yfinance"
    cache_dir.mkdir(parents=True, exist_ok=True)
    if hasattr(yf, "set_tz_cache_location"):
        yf.set_tz_cache_location(str(cache_dir))

    end = datetime.now().date() + timedelta(days=1)
    start = end - timedelta(days=days * 2)
    df = yf.download(symbol, start=start.isoformat(), end=end.isoformat(), progress=False, auto_adjust=True)
    if df.empty:
        return pd.DataFrame()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0].lower() for col in df.columns]
    else:
        df.columns = [str(col).lower() for col in df.columns]

    df = df.reset_index()
    date_col = "date" if "date" in df.columns else df.columns[0]
    return pd.DataFrame(
        {
            "date": pd.to_datetime(df[date_col]),
            "open": pd.to_numeric(df.get("open"), errors="coerce"),
            "high": pd.to_numeric(df.get("high"), errors="coerce"),
            "low": pd.to_numeric(df.get("low"), errors="coerce"),
            "close": pd.to_numeric(df.get("close"), errors="coerce"),
            "volume": pd.to_numeric(df.get("volume"), errors="coerce"),
        }
    ).dropna(subset=["date", "close"])


def fetch_cn_history(symbol: str) -> pd.DataFrame:
    import akshare as ak

    start = (datetime.now().date() - timedelta(days=850)).strftime("%Y%m%d")
    end = datetime.now().date().strftime("%Y%m%d")
    df = ak.fund_etf_hist_em(symbol=symbol, period="daily", start_date=start, end_date=end, adjust="qfq")
    if df.empty:
        return pd.DataFrame()

    col_map = {
        "日期": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
    }
    df = df.rename(columns=col_map)
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df["date"]),
            "open": pd.to_numeric(df.get("open"), errors="coerce"),
            "high": pd.to_numeric(df.get("high"), errors="coerce"),
            "low": pd.to_numeric(df.get("low"), errors="coerce"),
            "close": pd.to_numeric(df.get("close"), errors="coerce"),
            "volume": pd.to_numeric(df.get("volume"), errors="coerce"),
        }
    )
    return out.dropna(subset=["date", "close"])


def safe_fetch(market: str, symbol: str) -> tuple[pd.DataFrame, str, str | None]:
    try:
        if market == "us":
            return fetch_us_history(symbol), "real", None
        return fetch_cn_history(symbol), "real", None
    except Exception as exc:
        return pd.DataFrame(), "missing", f"{type(exc).__name__}: {exc}"


def pct_change(close: pd.Series, periods: int) -> float | None:
    if len(close) <= periods:
        return None
    prev = close.iloc[-periods - 1]
    curr = close.iloc[-1]
    if not prev or math.isnan(prev) or math.isnan(curr):
        return None
    return float((curr / prev - 1) * 100)


def max_drawdown(close: pd.Series, window: int) -> float | None:
    if len(close) < 2:
        return None
    segment = close.tail(window)
    peak = segment.cummax()
    dd = segment / peak - 1
    return float(dd.min() * 100)


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def score_signal(etf: dict[str, str], market: str, history: pd.DataFrame, data_quality: str, error: str | None) -> Signal:
    warnings: list[str] = []
    reasons: list[str] = []

    if history.empty or len(history) < 80:
        if error:
            warnings.append(f"数据源失败：{error}")
        warnings.append("历史数据不足，暂不生成交易信号")
        return Signal(
            symbol=etf["symbol"],
            name=etf["name"],
            market=market,
            theme=etf["theme"],
            role=etf.get("role", "sector"),
            status="watch",
            score=50.0,
            price=None,
            change_20d_pct=None,
            change_60d_pct=None,
            trend_score=50.0,
            momentum_score=50.0,
            flow_score=50.0,
            risk_score=50.0,
            event_score=50.0,
            reasons=["数据不足，保持观察"],
            warnings=warnings,
            data_quality=data_quality,
        )

    df = history.sort_values("date").dropna(subset=["close"]).copy()
    close = df["close"]
    volume = df["volume"].fillna(0)
    price = float(close.iloc[-1])

    for window in [20, 60, 120, 200]:
        df[f"ma{window}"] = close.rolling(window).mean()

    ma20 = df["ma20"].iloc[-1]
    ma60 = df["ma60"].iloc[-1]
    ma120 = df["ma120"].iloc[-1]
    ma200 = df["ma200"].iloc[-1]
    chg20 = pct_change(close, 20)
    chg60 = pct_change(close, 60)
    chg120 = pct_change(close, 120)
    dd20 = max_drawdown(close, 20)
    dd60 = max_drawdown(close, 60)
    vol20 = close.pct_change().tail(20).std() * math.sqrt(252) * 100
    vol_avg60 = volume.tail(60).mean()
    vol_latest = volume.iloc[-1]

    trend_score = 35
    if pd.notna(ma20) and price > ma20:
        trend_score += 15
        reasons.append("价格站上 20 日均线")
    else:
        warnings.append("价格未站上 20 日均线")
    if pd.notna(ma60) and price > ma60:
        trend_score += 20
        reasons.append("价格站上 60 日均线")
    else:
        warnings.append("价格未站上 60 日均线")
    if pd.notna(ma120) and price > ma120:
        trend_score += 15
    if pd.notna(ma200) and price > ma200:
        trend_score += 15
        reasons.append("长期趋势仍在")
    trend_score = clamp(trend_score)

    momentum_score = 50
    if chg20 is not None:
        momentum_score += max(-20, min(20, chg20 * 2))
    if chg60 is not None:
        momentum_score += max(-20, min(20, chg60))
    if chg120 is not None:
        momentum_score += max(-10, min(10, chg120 / 2))
    momentum_score = clamp(momentum_score)
    if chg20 is not None and chg20 > 0:
        reasons.append(f"20 日动量为正：{chg20:.2f}%")
    if chg60 is not None and chg60 < 0:
        warnings.append(f"60 日动量为负：{chg60:.2f}%")

    flow_score = 50
    if vol_avg60 and vol_latest > vol_avg60 * 1.1:
        flow_score += 15
        reasons.append("成交量高于 60 日均量，资金关注度改善")
    elif vol_avg60 and vol_latest < vol_avg60 * 0.7:
        flow_score -= 10
        warnings.append("成交量低于 60 日均量，资金确认不足")
    flow_score = clamp(flow_score)

    risk_score = 75
    if dd20 is not None and dd20 < -10:
        risk_score -= 20
        warnings.append(f"20 日最大回撤偏大：{dd20:.2f}%")
    if dd60 is not None and dd60 < -15:
        risk_score -= 20
        warnings.append(f"60 日最大回撤偏大：{dd60:.2f}%")
    if pd.notna(vol20) and vol20 > 35:
        risk_score -= 15
        warnings.append(f"年化波动率偏高：{vol20:.2f}%")
    if pd.notna(ma20) and price > ma20 * 1.12:
        risk_score -= 25
        warnings.append("价格相对 20 日均线乖离过高，不追高")
    risk_score = clamp(risk_score)

    event_score = 50
    score = (
        trend_score * 0.30
        + momentum_score * 0.25
        + flow_score * 0.20
        + risk_score * 0.15
        + event_score * 0.10
    )
    score = round(float(score), 2)

    if score >= 75 and trend_score >= 70 and risk_score >= 50:
        status = "buy"
    elif score < 45 or (pd.notna(ma60) and price < ma60 and chg20 is not None and chg20 < 0):
        status = "sell"
    elif score >= 60:
        status = "hold"
    else:
        status = "watch"

    if status == "buy":
        reasons.insert(0, "综合评分进入买入候选区")
    elif status == "sell":
        reasons.insert(0, "趋势或综合评分触发卖出/回避")
    elif status == "hold":
        reasons.insert(0, "趋势尚未破坏，维持持有")
    else:
        reasons.insert(0, "信号不足，等待确认")

    return Signal(
        symbol=etf["symbol"],
        name=etf["name"],
        market=market,
        theme=etf["theme"],
        role=etf.get("role", "sector"),
        status=status,
        score=score,
        price=round(price, 4),
        change_20d_pct=round(chg20, 2) if chg20 is not None else None,
        change_60d_pct=round(chg60, 2) if chg60 is not None else None,
        trend_score=round(trend_score, 2),
        momentum_score=round(momentum_score, 2),
        flow_score=round(flow_score, 2),
        risk_score=round(risk_score, 2),
        event_score=round(event_score, 2),
        reasons=reasons[:5],
        warnings=warnings[:5],
        data_quality=data_quality,
    )


def market_regime(signals: list[Signal]) -> dict[str, Any]:
    buy_count = sum(1 for s in signals if s.status == "buy")
    sell_count = sum(1 for s in signals if s.status == "sell")
    avg_score = sum(s.score for s in signals) / len(signals) if signals else 0
    if avg_score >= 70 and buy_count >= sell_count:
        mode = "offensive"
        cn = "进攻"
    elif avg_score < 50 or sell_count > buy_count:
        mode = "defensive"
        cn = "防守"
    else:
        mode = "balanced"
        cn = "均衡"
    return {
        "mode": mode,
        "label": cn,
        "average_score": round(avg_score, 2),
        "buy_count": buy_count,
        "sell_count": sell_count,
    }


def to_dict(signal: Signal) -> dict[str, Any]:
    return {
        "symbol": signal.symbol,
        "name": signal.name,
        "market": signal.market,
        "theme": signal.theme,
        "role": signal.role,
        "status": signal.status,
        "score": signal.score,
        "price": signal.price,
        "change_20d_pct": signal.change_20d_pct,
        "change_60d_pct": signal.change_60d_pct,
        "scores": {
            "trend": signal.trend_score,
            "momentum": signal.momentum_score,
            "flow": signal.flow_score,
            "risk": signal.risk_score,
            "event": signal.event_score,
        },
        "reasons": signal.reasons,
        "warnings": signal.warnings,
        "data_quality": signal.data_quality,
    }


def write_daily_report(payload: dict[str, Any]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    rows = []
    for item in payload["signals"]:
        rows.append(
            f"| {item['market']} | {item['symbol']} | {item['name']} | {item['theme']} | "
            f"{item['status']} | {item['score']} | {item['change_20d_pct']} | {item['change_60d_pct']} | "
            f"{'；'.join(item['reasons'][:2])} |"
        )
    body = "\n".join(
        [
            f"# ETF 每日信号报告 {date}",
            "",
            f"- 市场状态：{payload['regime']['label']}",
            f"- 平均分：{payload['regime']['average_score']}",
            f"- 买入候选：{payload['regime']['buy_count']}",
            f"- 卖出/回避：{payload['regime']['sell_count']}",
            "",
            "| 市场 | 代码 | 名称 | 主题 | 状态 | 分数 | 20日% | 60日% | 理由 |",
            "| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
            *rows,
            "",
            "说明：本报告由规则生成，不构成投资建议。",
        ]
    )
    (REPORTS_DIR / f"{date}.md").write_text(body, encoding="utf-8")


def main() -> None:
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    universe = load_universe()
    signals: list[Signal] = []

    for market in ["us", "cn"]:
        for etf in universe.get(market, []):
            history, quality, error = safe_fetch(market, etf["symbol"])
            signals.append(score_signal(etf, market, history, quality, error))

    signals = sorted(signals, key=lambda s: s.score, reverse=True)
    payload = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "strategy": "etf-regime-rotation-mvp",
        "regime": market_regime(signals),
        "signals": [to_dict(s) for s in signals],
        "summary": {
            "buy": [to_dict(s) for s in signals if s.status == "buy"][:8],
            "sell": [to_dict(s) for s in signals if s.status == "sell"][:8],
            "watch": [to_dict(s) for s in signals if s.status == "watch"][:8],
            "hold": [to_dict(s) for s in signals if s.status == "hold"][:8],
        },
        "disclaimer": "规则化 ETF 研究输出，不构成投资建议。",
    }
    LATEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_daily_report(payload)
    print(f"Wrote {LATEST_PATH}")


if __name__ == "__main__":
    main()
