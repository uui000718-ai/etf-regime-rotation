from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generate_latest import (  # noqa: E402
    FetchedHistory,
    analyze_etf,
    apply_cross_section_scores,
    build_portfolio,
    fetch_cn_quote_names,
    fetch_history,
    load_universe,
    market_regime,
)


REPORT_DIR = ROOT / "reports" / "backtests"
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_COST_BPS = 5.0


def date_to_str(value: pd.Timestamp) -> str:
    return value.strftime("%Y-%m-%d")


def as_weight_map(portfolio: dict[str, Any]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for item in portfolio.get("targets", []):
        symbol = item["symbol"]
        weights[symbol] = weights.get(symbol, 0.0) + float(item["target_weight_pct"]) / 100
    if "CASH" not in weights:
        invested = sum(weights.values())
        if invested < 1:
            weights["CASH"] = 1 - invested
    return weights


def turnover(old: dict[str, float], new: dict[str, float]) -> float:
    symbols = (set(old) | set(new)) - {"CASH"}
    return sum(abs(new.get(symbol, 0.0) - old.get(symbol, 0.0)) for symbol in symbols)


def max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak:
            worst = min(worst, value / peak - 1)
    return worst * 100


def annualized_volatility(daily_returns: list[float]) -> float:
    if len(daily_returns) < 2:
        return 0.0
    return float(pd.Series(daily_returns).std() * math.sqrt(252) * 100)


def build_price_panel(histories: dict[tuple[str, str], FetchedHistory]) -> pd.DataFrame:
    series: dict[str, pd.Series] = {}
    for (_, symbol), fetched in histories.items():
        frame = fetched.frame.copy()
        if frame.empty:
            continue
        frame["date"] = pd.to_datetime(frame["date"])
        close = pd.to_numeric(frame["close"], errors="coerce")
        series[symbol] = pd.Series(close.values, index=frame["date"], name=symbol)

    panel = pd.DataFrame(series).sort_index()
    panel = panel[~panel.index.duplicated(keep="last")]
    return panel.ffill()


def weekly_signal_dates(price_panel: pd.DataFrame, start_date: pd.Timestamp, end_date: pd.Timestamp) -> list[pd.Timestamp]:
    dates = [date for date in price_panel.index if start_date <= date <= end_date]
    if not dates:
        return []

    weekly: list[pd.Timestamp] = []
    seen_weeks: set[tuple[int, int]] = set()
    for date in dates:
        year, week, _ = date.isocalendar()
        key = (year, week)
        if key not in seen_weeks:
            weekly.append(date)
            seen_weeks.add(key)
    return weekly


def signals_for_date(
    signal_date: pd.Timestamp,
    universe: dict[str, list[dict[str, str]]],
    histories: dict[tuple[str, str], FetchedHistory],
    cn_names: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for market in ["us", "cn"]:
        for etf in universe.get(market, []):
            symbol = etf["symbol"]
            fetched = histories[(market, symbol)]
            frame = fetched.frame.copy()
            frame["date"] = pd.to_datetime(frame["date"])
            sliced = frame[frame["date"] <= signal_date].copy()
            etf_for_signal = etf
            if market == "cn" and cn_names.get(symbol):
                etf_for_signal = {**etf, "name": cn_names[symbol]}
            rows.append(
                analyze_etf(
                    etf_for_signal,
                    market,
                    FetchedHistory(frame=sliced, provider=fetched.provider, errors=fetched.errors),
                )
            )
    return apply_cross_section_scores(rows)


def next_trading_date(price_panel: pd.DataFrame, date: pd.Timestamp) -> pd.Timestamp | None:
    future = price_panel.index[price_panel.index > date]
    return future[0] if len(future) else None


def benchmark_return(price_panel: pd.DataFrame, symbols: list[str], start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    available = [symbol for symbol in symbols if symbol in price_panel.columns]
    if not available:
        return None
    segment = price_panel.loc[(price_panel.index >= start) & (price_panel.index <= end), available].dropna(how="all")
    if len(segment) < 2:
        return None
    first = segment.iloc[0]
    last = segment.iloc[-1]
    returns = (last / first - 1).replace([float("inf"), -float("inf")], pd.NA).dropna()
    if returns.empty:
        return None
    return float(returns.mean() * 100)


def run_backtest(lookback_days: int = DEFAULT_LOOKBACK_DAYS, cost_bps: float = DEFAULT_COST_BPS) -> dict[str, Any]:
    universe = load_universe()
    cn_names = fetch_cn_quote_names([item["symbol"] for item in universe.get("cn", [])])

    histories: dict[tuple[str, str], FetchedHistory] = {}
    for market in ["us", "cn"]:
        for etf in universe.get(market, []):
            symbol = etf["symbol"]
            histories[(market, symbol)] = fetch_history(market, symbol)

    price_panel = build_price_panel(histories)
    if price_panel.empty:
        raise RuntimeError("No price data available for backtest.")

    end_date = price_panel.index.max()
    start_date = end_date - pd.Timedelta(days=lookback_days)
    signal_dates = weekly_signal_dates(price_panel, start_date, end_date)

    schedules: dict[pd.Timestamp, dict[str, Any]] = {}
    trade_log: list[dict[str, Any]] = []
    for signal_date in signal_dates:
        trade_date = next_trading_date(price_panel, signal_date)
        if trade_date is None or trade_date > end_date:
            continue
        signals = signals_for_date(signal_date, universe, histories, cn_names)
        portfolio = build_portfolio(signals)
        weights = as_weight_map(portfolio)
        schedules[trade_date] = {
            "signal_date": signal_date,
            "trade_date": trade_date,
            "weights": weights,
            "portfolio": portfolio,
            "regime": market_regime(signals),
            "buys": [
                {
                    "symbol": item["symbol"],
                    "name": item["name"],
                    "score": item["score"],
                }
                for item in signals
                if item["market"] == "cn" and item["status"] == "buy"
            ][:5],
        }

    if not schedules:
        raise RuntimeError("No rebalance schedule generated.")

    first_trade_date = min(schedules)
    dates = [date for date in price_panel.index if first_trade_date <= date <= end_date]
    current_weights: dict[str, float] = {"CASH": 1.0}
    value = 1.0
    total_cost = 0.0
    equity_curve: list[dict[str, Any]] = []
    daily_returns: list[float] = []
    previous_date: pd.Timestamp | None = None

    for date in dates:
        day_return = 0.0
        if previous_date is not None:
            asset_returns = price_panel.loc[date] / price_panel.loc[previous_date] - 1
            for symbol, weight in current_weights.items():
                if symbol == "CASH":
                    continue
                asset_return = asset_returns.get(symbol)
                if pd.notna(asset_return):
                    day_return += weight * float(asset_return)
            value *= 1 + day_return
            daily_returns.append(day_return)

        if date in schedules:
            scheduled = schedules[date]
            new_weights = scheduled["weights"]
            trade_turnover = turnover(current_weights, new_weights)
            cost = trade_turnover * cost_bps / 10000
            value *= 1 - cost
            total_cost += cost
            current_weights = new_weights
            trade_log.append(
                {
                    "signal_date": date_to_str(scheduled["signal_date"]),
                    "trade_date": date_to_str(date),
                    "turnover_pct": round(trade_turnover * 100, 2),
                    "cost_pct": round(cost * 100, 4),
                    "regime": scheduled["regime"],
                    "targets": scheduled["portfolio"]["targets"],
                    "cn_buys": scheduled["buys"],
                }
            )

        equity_curve.append({"date": date_to_str(date), "value": round(value, 6), "daily_return_pct": round(day_return * 100, 4)})
        previous_date = date

    cn_symbols = [item["symbol"] for item in universe.get("cn", [])]
    us_symbols = [item["symbol"] for item in universe.get("us", [])]
    period_start = first_trade_date
    period_end = dates[-1]

    cn_benchmark = benchmark_return(price_panel, cn_symbols, period_start, period_end)
    us_benchmark = benchmark_return(price_panel, us_symbols, period_start, period_end)

    result = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "strategy": "etf-regime-rotation-v2",
        "assumptions": {
            "lookback_days": lookback_days,
            "rebalance": "weekly",
            "execution": "signals are generated after close and executed at next available close",
            "cash_return": "0%",
            "transaction_cost_bps_per_turnover": cost_bps,
        },
        "period": {
            "start": date_to_str(period_start),
            "end": date_to_str(period_end),
            "trading_points": len(dates),
        },
        "metrics": {
            "total_return_pct": round((value - 1) * 100, 2),
            "max_drawdown_pct": round(max_drawdown([row["value"] for row in equity_curve]), 2),
            "annualized_volatility_pct": round(annualized_volatility(daily_returns), 2),
            "transaction_cost_pct": round(total_cost * 100, 4),
            "rebalance_count": len(trade_log),
        },
        "benchmarks": {
            "cn_equal_weight_universe_pct": None if cn_benchmark is None else round(cn_benchmark, 2),
            "nasdaq_core_equal_weight_pct": None if us_benchmark is None else round(us_benchmark, 2),
        },
        "latest_targets": trade_log[-1]["targets"] if trade_log else [],
        "trade_log": trade_log,
        "equity_curve": equity_curve,
        "disclaimer": "Rule-based ETF research backtest. It is not investment advice.",
    }
    return result


def write_report(result: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "last_month_backtest.json"
    md_path = REPORT_DIR / "last_month_backtest.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    metrics = result["metrics"]
    benchmarks = result["benchmarks"]
    period = result["period"]
    latest_targets = "\n".join(
        f"- {item['symbol']} {item['name']}: {item['target_weight_pct']}%"
        for item in result.get("latest_targets", [])
    )
    trades = "\n".join(
        f"| {item['signal_date']} | {item['trade_date']} | {item['turnover_pct']} | "
        f"{item['cost_pct']} | {item['regime']['label']} | "
        f"{', '.join(target['symbol'] for target in item['targets'])} |"
        for item in result.get("trade_log", [])
    )
    body = f"""# ETF 轮动策略近一月回测

- 回测区间：{period['start']} 至 {period['end']}
- 策略收益：{metrics['total_return_pct']}%
- 最大回撤：{metrics['max_drawdown_pct']}%
- 年化波动率：{metrics['annualized_volatility_pct']}%
- 交易成本估算：{metrics['transaction_cost_pct']}%
- 调仓次数：{metrics['rebalance_count']}
- A股ETF等权基准：{benchmarks['cn_equal_weight_universe_pct']}%
- 纳指核心等权基准：{benchmarks['nasdaq_core_equal_weight_pct']}%

## 最新目标仓位

{latest_targets}

## 调仓记录

| 信号日 | 执行日 | 换手率% | 成本% | 市场状态 | 目标 |
| --- | --- | ---: | ---: | --- | --- |
{trades}

说明：信号按收盘后生成、下一可交易日收盘执行；现金收益按 0；交易成本按单边换手 5bp 估算。本报告不构成投资建议。
"""
    md_path.write_text(body, encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


def main() -> None:
    result = run_backtest()
    write_report(result)


if __name__ == "__main__":
    main()
