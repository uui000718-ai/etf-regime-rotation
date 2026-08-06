from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_PATH = ROOT / "config" / "etf_universe.json"
SITE_DATA_DIR = ROOT / "site" / "data"
LATEST_PATH = SITE_DATA_DIR / "latest.json"
REPORTS_DIR = ROOT / "reports"

EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
EASTMONEY_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://quote.eastmoney.com/",
}
TENCENT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://gu.qq.com/",
}


@dataclass
class FetchedHistory:
    frame: pd.DataFrame
    provider: str
    errors: list[str]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_universe() -> dict[str, list[dict[str, str]]]:
    return json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))


def cn_secid(symbol: str) -> str:
    market = "1" if symbol.startswith(("5", "6", "9")) else "0"
    return f"{market}.{symbol}"


def cn_tencent_symbol(symbol: str) -> str:
    prefix = "sh" if symbol.startswith(("5", "6", "9")) else "sz"
    return f"{prefix}{symbol}"


def fetch_us_history(symbol: str, days: int = 520) -> pd.DataFrame:
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
            "amount": pd.NA,
            "turnover": pd.NA,
        }
    ).dropna(subset=["date", "close"])


def fetch_cn_history_akshare(symbol: str) -> pd.DataFrame:
    import akshare as ak

    start = (datetime.now().date() - timedelta(days=950)).strftime("%Y%m%d")
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
        "换手率": "turnover",
    }
    df = df.rename(columns=col_map)
    return pd.DataFrame(
        {
            "date": pd.to_datetime(df["date"]),
            "open": pd.to_numeric(df.get("open"), errors="coerce"),
            "high": pd.to_numeric(df.get("high"), errors="coerce"),
            "low": pd.to_numeric(df.get("low"), errors="coerce"),
            "close": pd.to_numeric(df.get("close"), errors="coerce"),
            "volume": pd.to_numeric(df.get("volume"), errors="coerce"),
            "amount": pd.to_numeric(df.get("amount"), errors="coerce"),
            "turnover": pd.to_numeric(df.get("turnover"), errors="coerce"),
        }
    ).dropna(subset=["date", "close"])


def fetch_cn_history_eastmoney(symbol: str) -> pd.DataFrame:
    start = (datetime.now().date() - timedelta(days=950)).strftime("%Y%m%d")
    params = {
        "secid": cn_secid(symbol),
        "klt": "101",
        "fqt": "1",
        "beg": start,
        "end": "20500101",
        "lmt": "600",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }
    session = requests.Session()
    session.trust_env = False
    response = session.get(EASTMONEY_KLINE_URL, params=params, headers=EASTMONEY_HEADERS, timeout=20)
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("data", {}).get("klines") or []
    parsed = []
    for row in rows:
        parts = row.split(",")
        if len(parts) < 11:
            continue
        parsed.append(
            {
                "date": parts[0],
                "open": parts[1],
                "close": parts[2],
                "high": parts[3],
                "low": parts[4],
                "volume": parts[5],
                "amount": parts[6],
                "turnover": parts[10],
            }
        )
    if not parsed:
        return pd.DataFrame()
    df = pd.DataFrame(parsed)
    return pd.DataFrame(
        {
            "date": pd.to_datetime(df["date"]),
            "open": pd.to_numeric(df["open"], errors="coerce"),
            "high": pd.to_numeric(df["high"], errors="coerce"),
            "low": pd.to_numeric(df["low"], errors="coerce"),
            "close": pd.to_numeric(df["close"], errors="coerce"),
            "volume": pd.to_numeric(df["volume"], errors="coerce"),
            "amount": pd.to_numeric(df["amount"], errors="coerce"),
            "turnover": pd.to_numeric(df["turnover"], errors="coerce"),
        }
    ).dropna(subset=["date", "close"])


def fetch_cn_history_tencent(symbol: str) -> pd.DataFrame:
    tencent_symbol = cn_tencent_symbol(symbol)
    params = {"param": f"{tencent_symbol},day,,,600,qfq"}
    session = requests.Session()
    session.trust_env = False
    response = session.get(TENCENT_KLINE_URL, params=params, headers=TENCENT_HEADERS, timeout=20)
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", {}).get(tencent_symbol, {})
    rows = data.get("qfqday") or data.get("day") or []
    parsed = []
    for row in rows:
        if len(row) < 6:
            continue
        parsed.append(
            {
                "date": row[0],
                "open": row[1],
                "close": row[2],
                "high": row[3],
                "low": row[4],
                "volume": row[5],
            }
        )
    if not parsed:
        return pd.DataFrame()
    df = pd.DataFrame(parsed)
    return pd.DataFrame(
        {
            "date": pd.to_datetime(df["date"]),
            "open": pd.to_numeric(df["open"], errors="coerce"),
            "high": pd.to_numeric(df["high"], errors="coerce"),
            "low": pd.to_numeric(df["low"], errors="coerce"),
            "close": pd.to_numeric(df["close"], errors="coerce"),
            "volume": pd.to_numeric(df["volume"], errors="coerce"),
            "amount": pd.NA,
            "turnover": pd.NA,
        }
    ).dropna(subset=["date", "close"])


def fetch_cn_quote_names(symbols: list[str]) -> dict[str, str]:
    if not symbols:
        return {}
    session = requests.Session()
    session.trust_env = False
    result: dict[str, str] = {}
    prefixed = [cn_tencent_symbol(symbol) for symbol in symbols]
    for start in range(0, len(prefixed), 60):
        batch = prefixed[start : start + 60]
        try:
            response = session.get(
                TENCENT_QUOTE_URL + ",".join(batch),
                headers=TENCENT_HEADERS,
                timeout=20,
            )
            response.raise_for_status()
            text = response.content.decode("gbk", errors="ignore")
        except Exception:
            continue
        for chunk in text.split(";"):
            if "~" not in chunk or '="' not in chunk:
                continue
            left, value = chunk.split('="', 1)
            prefixed_symbol = left.replace("v_", "").strip()
            parts = value.strip('"').split("~")
            if len(parts) > 2 and parts[1] and parts[2]:
                result[parts[2]] = parts[1]
            elif len(parts) > 1 and prefixed_symbol:
                result[prefixed_symbol[-6:]] = parts[1]
    return result


def fetch_history(market: str, symbol: str) -> FetchedHistory:
    errors: list[str] = []
    if market == "us":
        try:
            frame = fetch_us_history(symbol)
            return FetchedHistory(frame=frame, provider="yfinance", errors=errors)
        except Exception as exc:
            return FetchedHistory(frame=pd.DataFrame(), provider="missing", errors=[f"yfinance: {exc}"])

    try:
        frame = fetch_cn_history_akshare(symbol)
        if not frame.empty:
            return FetchedHistory(frame=frame, provider="akshare", errors=errors)
        errors.append("akshare: empty")
    except Exception as exc:
        errors.append(f"akshare: {exc}")

    time.sleep(0.25)
    try:
        frame = fetch_cn_history_eastmoney(symbol)
        if not frame.empty:
            return FetchedHistory(frame=frame, provider="eastmoney_kline", errors=errors)
        errors.append("eastmoney_kline: empty")
    except Exception as exc:
        errors.append(f"eastmoney_kline: {exc}")

    time.sleep(0.25)
    try:
        frame = fetch_cn_history_tencent(symbol)
        if not frame.empty:
            return FetchedHistory(frame=frame, provider="tencent_fqkline", errors=errors)
        errors.append("tencent_fqkline: empty")
    except Exception as exc:
        errors.append(f"tencent_fqkline: {exc}")

    return FetchedHistory(frame=pd.DataFrame(), provider="missing", errors=errors)


def pct_change(close: pd.Series, periods: int) -> float | None:
    if len(close) <= periods:
        return None
    prev = close.iloc[-periods - 1]
    curr = close.iloc[-1]
    if pd.isna(prev) or pd.isna(curr) or float(prev) == 0:
        return None
    return float((curr / prev - 1) * 100)


def max_drawdown(close: pd.Series, window: int) -> float | None:
    if len(close) < 2:
        return None
    segment = close.tail(window)
    peak = segment.cummax()
    dd = segment / peak - 1
    return float(dd.min() * 100)


def rsi(close: pd.Series, window: int = 14) -> float | None:
    if len(close) <= window + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, pd.NA)
    value = 100 - (100 / (1 + rs.iloc[-1]))
    return float(value) if pd.notna(value) else None


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def compact_source_errors(errors: list[str]) -> list[str]:
    compact: list[str] = []
    for error in errors:
        source = str(error).split(":", 1)[0].strip()
        if source and source not in compact:
            compact.append(source)
    return compact


def percentile_score(series: pd.Series, value: float | None, *, lower_is_better: bool = False) -> float:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if value is None or pd.isna(value) or numeric.empty:
        return 50.0
    ranks = numeric.rank(ascending=not lower_is_better, pct=True) * 100
    tmp = pd.Series([*numeric.tolist(), float(value)])
    rank = tmp.rank(ascending=not lower_is_better, pct=True).iloc[-1] * 100
    return float(rank if math.isfinite(rank) else 50.0)


def analyze_etf(etf: dict[str, str], market: str, fetched: FetchedHistory) -> dict[str, Any]:
    symbol = etf["symbol"]
    name = etf.get("name") or symbol
    warnings: list[str] = []

    if fetched.frame.empty or len(fetched.frame) < 80:
        return {
            "symbol": symbol,
            "name": name,
            "market": market,
            "theme": etf.get("theme", "ETF"),
            "role": etf.get("role", "sector"),
            "provider": fetched.provider,
            "source_errors": compact_source_errors(fetched.errors),
            "data_quality": "missing" if fetched.frame.empty else "partial",
            "warnings": ["历史数据不足，暂不生成交易信号"],
            "reasons": ["数据不足，保持观察"],
            "status": "watch",
            "score": 50.0,
            "price": None,
            "change_1d_pct": None,
            "change_20d_pct": None,
            "change_60d_pct": None,
            "change_120d_pct": None,
            "volume_ratio": None,
            "turnover": None,
            "max_drawdown_20d_pct": None,
            "max_drawdown_60d_pct": None,
            "volatility_20d_pct": None,
            "rsi_14": None,
            "distance_to_support_pct": None,
            "distance_to_resistance_pct": None,
            "scores": {"trend": 50.0, "momentum": 50.0, "flow": 50.0, "risk": 50.0, "event": 50.0},
            "decision_stability": {"applied": False, "reason": "数据不足"},
        }

    df = fetched.frame.sort_values("date").dropna(subset=["close"]).copy()
    close = pd.to_numeric(df["close"], errors="coerce")
    volume = pd.to_numeric(df.get("volume", pd.Series(index=df.index)), errors="coerce").fillna(0)
    amount = pd.to_numeric(df.get("amount", pd.Series(index=df.index)), errors="coerce")
    turnover = pd.to_numeric(df.get("turnover", pd.Series(index=df.index)), errors="coerce")

    for window in [20, 60, 120, 200]:
        df[f"ma{window}"] = close.rolling(window).mean()

    price = float(close.iloc[-1])
    ma20 = df["ma20"].iloc[-1]
    ma60 = df["ma60"].iloc[-1]
    ma120 = df["ma120"].iloc[-1]
    ma200 = df["ma200"].iloc[-1]
    chg1 = pct_change(close, 1)
    chg20 = pct_change(close, 20)
    chg60 = pct_change(close, 60)
    chg120 = pct_change(close, 120)
    dd20 = max_drawdown(close, 20)
    dd60 = max_drawdown(close, 60)
    vol20 = close.pct_change().tail(20).std() * math.sqrt(252) * 100
    rsi14 = rsi(close)
    vol_avg60 = volume.tail(60).mean()
    vol_latest = volume.iloc[-1]
    volume_ratio = float(vol_latest / vol_avg60) if vol_avg60 and vol_avg60 > 0 else None
    up_volume = volume.tail(20)[close.pct_change().tail(20) > 0].sum()
    total_volume = volume.tail(20).sum()
    up_volume_ratio = float(up_volume / total_volume) if total_volume else None
    support_60 = float(close.tail(60).min())
    resistance_60 = float(close.tail(60).max())
    distance_to_support = (price / support_60 - 1) * 100 if support_60 else None
    distance_to_resistance = (resistance_60 / price - 1) * 100 if price else None

    trend_score = 35.0
    reasons: list[str] = []
    if pd.notna(ma20) and price > ma20:
        trend_score += 15
        reasons.append("价格站上20日均线")
    else:
        warnings.append("价格未站上20日均线")
    if pd.notna(ma60) and price > ma60:
        trend_score += 20
        reasons.append("价格站上60日均线")
    else:
        warnings.append("价格未站上60日均线")
    if pd.notna(ma120) and price > ma120:
        trend_score += 15
    if pd.notna(ma200) and price > ma200:
        trend_score += 15
        reasons.append("长期趋势仍在")
    if pd.notna(ma20) and pd.notna(ma60) and ma20 > ma60:
        trend_score += 8
        reasons.append("短期均线强于中期均线")
    trend_score = clamp(trend_score)

    base_momentum = 50.0
    if chg20 is not None:
        base_momentum += max(-20, min(20, chg20 * 1.8))
    if chg60 is not None:
        base_momentum += max(-20, min(20, chg60 * 0.9))
    if chg120 is not None:
        base_momentum += max(-10, min(10, chg120 * 0.35))
    if chg60 is not None and chg60 > 45:
        base_momentum -= min(16, (chg60 - 45) * 0.5)
        warnings.append("60日涨幅过高，追涨风险上升")
    base_momentum = clamp(base_momentum)

    flow_score = 50.0
    if volume_ratio is not None:
        if 0.9 <= volume_ratio <= 3.0:
            flow_score += min(20, (volume_ratio - 0.9) * 10)
            reasons.append("成交量处于有效放大区间")
        elif volume_ratio > 4.5:
            flow_score -= min(20, (volume_ratio - 4.5) * 5)
            warnings.append("成交量异常放大，可能存在短线拥挤")
        elif volume_ratio < 0.7:
            flow_score -= 12
            warnings.append("成交量低于60日均量，资金确认不足")
    if up_volume_ratio is not None:
        flow_score += (up_volume_ratio - 0.5) * 36
        if up_volume_ratio > 0.56:
            reasons.append("近20日上涨日成交占优")
        elif up_volume_ratio < 0.44:
            warnings.append("近20日下跌日成交占优")
    flow_score = clamp(flow_score)

    risk_score = 78.0
    if dd20 is not None and dd20 < -8:
        risk_score -= min(24, (-8 - dd20) * 2.0)
        warnings.append(f"20日最大回撤偏大：{dd20:.2f}%")
    if dd60 is not None and dd60 < -15:
        risk_score -= min(20, (-15 - dd60) * 1.2)
        warnings.append(f"60日最大回撤偏大：{dd60:.2f}%")
    if pd.notna(vol20) and vol20 > 35:
        risk_score -= min(20, (vol20 - 35) * 0.7)
        warnings.append(f"年化波动率偏高：{vol20:.2f}%")
    if rsi14 is not None and rsi14 > 78:
        risk_score -= 12
        warnings.append(f"RSI过热：{rsi14:.1f}")
    if pd.notna(ma20) and price > ma20 * 1.12:
        risk_score -= 22
        warnings.append("价格相对20日均线乖离过高，不追高")
    risk_score = clamp(risk_score)

    data_quality = "real" if fetched.provider != "missing" else "missing"
    if fetched.provider != "akshare" and market == "cn":
        data_quality = "fallback"
    if len(df) < 160:
        data_quality = "partial"
        warnings.append("历史窗口较短，降低信号置信度")

    return {
        "symbol": symbol,
        "name": name,
        "market": market,
        "theme": etf.get("theme", "ETF"),
        "role": etf.get("role", "sector"),
        "provider": fetched.provider,
        "source_errors": compact_source_errors(fetched.errors),
        "data_quality": data_quality,
        "warnings": warnings,
        "reasons": reasons,
        "status": "watch",
        "score": 50.0,
        "price": round(price, 4),
        "change_1d_pct": round(chg1, 2) if chg1 is not None else None,
        "change_20d_pct": round(chg20, 2) if chg20 is not None else None,
        "change_60d_pct": round(chg60, 2) if chg60 is not None else None,
        "change_120d_pct": round(chg120, 2) if chg120 is not None else None,
        "volume_ratio": round(volume_ratio, 2) if volume_ratio is not None else None,
        "turnover": round(float(turnover.iloc[-1]), 2) if len(turnover) and pd.notna(turnover.iloc[-1]) else None,
        "max_drawdown_20d_pct": round(dd20, 2) if dd20 is not None else None,
        "max_drawdown_60d_pct": round(dd60, 2) if dd60 is not None else None,
        "volatility_20d_pct": round(float(vol20), 2) if pd.notna(vol20) else None,
        "rsi_14": round(rsi14, 2) if rsi14 is not None else None,
        "distance_to_support_pct": round(distance_to_support, 2) if distance_to_support is not None else None,
        "distance_to_resistance_pct": round(distance_to_resistance, 2) if distance_to_resistance is not None else None,
        "scores": {
            "trend": round(trend_score, 2),
            "momentum": round(base_momentum, 2),
            "flow": round(flow_score, 2),
            "risk": round(risk_score, 2),
            "event": 50.0,
        },
        "decision_stability": {"applied": False, "reason": ""},
    }


def apply_cross_section_scores(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    df = pd.DataFrame(items)
    for market in sorted(df["market"].dropna().unique()):
        idx = df.index[df["market"] == market]
        market_df = df.loc[idx]
        rank20 = market_df["change_20d_pct"].rank(pct=True) * 100
        rank60 = market_df["change_60d_pct"].rank(pct=True) * 100
        risk_rank = market_df["volatility_20d_pct"].rank(ascending=False, pct=True) * 100
        for row_idx in idx:
            item = items[int(row_idx)]
            scores = item["scores"]
            momentum_rank = float(rank20.get(row_idx, 50) * 0.45 + rank60.get(row_idx, 50) * 0.55)
            risk_rank_score = float(risk_rank.get(row_idx, 50)) if not pd.isna(risk_rank.get(row_idx, pd.NA)) else 50.0
            scores["momentum"] = round(clamp(scores["momentum"] * 0.45 + momentum_rank * 0.55), 2)
            scores["risk"] = round(clamp(scores["risk"] * 0.75 + risk_rank_score * 0.25), 2)
            item["relative_rank"] = round(momentum_rank, 2)

    for item in items:
        scores = item["scores"]
        item["score"] = round(
            scores["trend"] * 0.30
            + scores["momentum"] * 0.25
            + scores["flow"] * 0.20
            + scores["risk"] * 0.15
            + scores["event"] * 0.10,
            2,
        )
        assign_status(item)

    items.sort(key=lambda value: (value["market"], value["score"]), reverse=True)
    for market in ["cn", "us"]:
        market_items = [item for item in items if item["market"] == market]
        market_items.sort(key=lambda value: value["score"], reverse=True)
        for rank, item in enumerate(market_items, start=1):
            item["rank"] = rank
    return sorted(items, key=lambda value: value["score"], reverse=True)


def assign_status(item: dict[str, Any]) -> None:
    scores = item["scores"]
    score = item["score"]
    warnings = item["warnings"]
    reasons = item["reasons"]
    chg20 = item["change_20d_pct"]
    chg60 = item["change_60d_pct"]
    near_support = item["distance_to_support_pct"] is not None and item["distance_to_support_pct"] <= 3.5
    near_resistance = item["distance_to_resistance_pct"] is not None and item["distance_to_resistance_pct"] <= 3.0
    major_risk = scores["risk"] < 42 or (item["max_drawdown_20d_pct"] is not None and item["max_drawdown_20d_pct"] <= -12)

    if score >= 72 and scores["trend"] >= 68 and scores["momentum"] >= 62 and scores["risk"] >= 48:
        status = "buy"
    elif score < 48 or major_risk or (scores["trend"] < 45 and (chg20 or 0) < 0):
        status = "sell"
    elif score >= 60 and scores["trend"] >= 55:
        status = "hold"
    else:
        status = "watch"

    stability_reason = ""
    if status == "buy" and scores["flow"] < 50:
        status = "hold"
        stability_reason = "买入结论缺少量能确认，降级为持有"
        warnings.append(stability_reason)
    elif status == "buy" and near_resistance and scores["flow"] < 62:
        status = "hold"
        stability_reason = "价格贴近60日压力位且量能确认不足，避免追买"
        warnings.append(stability_reason)
    elif status == "sell" and near_support and scores["flow"] >= 50 and not major_risk:
        status = "watch"
        stability_reason = "价格贴近60日支撑且未见显著风险，卖出降级为观察"
        warnings.append(stability_reason)

    item["status"] = status
    item["action_label"] = {"buy": "买入候选", "hold": "持有", "watch": "观察", "sell": "卖出/回避"}[status]
    item["decision_stability"] = {"applied": bool(stability_reason), "reason": stability_reason}

    prefix = {
        "buy": "综合评分进入买入候选区",
        "hold": "趋势尚未破坏，维持持有",
        "watch": "信号不足，等待确认",
        "sell": "趋势或风险触发卖出/回避",
    }[status]
    item["reasons"] = [prefix, *reasons][:6]


def market_regime(signals: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [item for item in signals if item["data_quality"] != "missing"]
    buy_count = sum(1 for item in signals if item["status"] == "buy")
    sell_count = sum(1 for item in signals if item["status"] == "sell")
    avg_score = sum(item["score"] for item in usable) / len(usable) if usable else 0
    if avg_score >= 66 and buy_count >= 3 and sell_count <= buy_count:
        mode = "offensive"
        label = "进攻"
    elif avg_score < 54 or sell_count > buy_count * 1.2:
        mode = "defensive"
        label = "防守"
    else:
        mode = "balanced"
        label = "均衡"
    return {
        "mode": mode,
        "label": label,
        "average_score": round(avg_score, 2),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "usable_count": len(usable),
    }


def build_portfolio(payload_signals: list[dict[str, Any]]) -> dict[str, Any]:
    buys = [item for item in payload_signals if item["market"] == "cn" and item["status"] == "buy"]
    buys = sorted(buys, key=lambda item: item["score"], reverse=True)[:5]
    us_core = [item for item in payload_signals if item["market"] == "us" and item["status"] in {"buy", "hold"}]
    targets: list[dict[str, Any]] = []
    cn_weight = 55 if len(buys) >= 3 else 35 if buys else 0
    if buys:
        per_weight = round(cn_weight / len(buys), 2)
        for item in buys:
            targets.append({"symbol": item["symbol"], "name": item["name"], "market": "cn", "target_weight_pct": per_weight})
    if us_core:
        qqq = max(us_core, key=lambda item: item["score"])
        targets.append({"symbol": qqq["symbol"], "name": qqq["name"], "market": "us", "target_weight_pct": 30})
    invested = sum(item["target_weight_pct"] for item in targets)
    cash = max(0, round(100 - invested, 2))
    if cash:
        targets.append({"symbol": "CASH", "name": "现金/货币基金", "market": "cash", "target_weight_pct": cash})
    return {
        "rebalance_frequency": "weekly",
        "max_cn_positions": 5,
        "single_theme_cap_pct": 25,
        "targets": targets,
        "notes": ["仓位为规则模板，不构成投资建议", "买入候选不足时自动提高现金比例"],
    }


def write_daily_report(payload: dict[str, Any]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    rows = []
    for item in payload["signals"]:
        rows.append(
            f"| {item['rank']} | {item['market']} | {item['symbol']} | {item['name']} | {item['theme']} | "
            f"{item['action_label']} | {item['score']} | {item['change_20d_pct']} | {item['change_60d_pct']} | "
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
            f"- 可用数据标的：{payload['regime']['usable_count']}",
            "",
            "| 排名 | 市场 | 代码 | 名称 | 主题 | 状态 | 分数 | 20日% | 60日% | 理由 |",
            "| ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |",
            *rows,
            "",
            "说明：本报告由规则生成，不构成投资建议。",
        ]
    )
    (REPORTS_DIR / f"{date}.md").write_text(body, encoding="utf-8")


def main() -> None:
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    universe = load_universe()
    cn_names = fetch_cn_quote_names([item["symbol"] for item in universe.get("cn", [])])
    rows: list[dict[str, Any]] = []

    for market in ["us", "cn"]:
        for etf in universe.get(market, []):
            if market == "cn" and cn_names.get(etf["symbol"]):
                etf = {**etf, "name": cn_names[etf["symbol"]]}
            fetched = fetch_history(market, etf["symbol"])
            rows.append(analyze_etf(etf, market, fetched))

    signals = apply_cross_section_scores(rows)
    payload = {
        "schema_version": 2,
        "generated_at": now_iso(),
        "strategy": "etf-regime-rotation-v2",
        "strategy_sources": [
            "a-stock-data: A股 ETF 前缀路由、东财限流与数据源 fallback",
            "daily_stock_analysis: 资金确认不足时降级买入，靠近支撑时不机械卖出",
            "tickflow-stock-panel: ETF 与个股策略池隔离、日线信号用于次日执行、回测需考虑 T+1/费用/滑点",
            "TradingAgents-CN: 风险管理覆盖层，先看反方和保守情景再给组合动作",
        ],
        "regime": market_regime(signals),
        "signals": signals,
        "summary": {
            "buy": [item for item in signals if item["status"] == "buy"][:8],
            "sell": [item for item in signals if item["status"] == "sell"][:8],
            "watch": [item for item in signals if item["status"] == "watch"][:8],
            "hold": [item for item in signals if item["status"] == "hold"][:8],
        },
        "portfolio": build_portfolio(signals),
        "disclaimer": "规则化 ETF 研究输出，不构成投资建议。",
    }
    LATEST_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_daily_report(payload)
    print(f"Wrote {LATEST_PATH}")


if __name__ == "__main__":
    main()
