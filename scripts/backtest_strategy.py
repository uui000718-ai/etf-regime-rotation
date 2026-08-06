from __future__ import annotations

import argparse
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
DEFAULT_CAPITAL = 10000.0


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


def enrich_targets_with_amounts(targets: list[dict[str, Any]], account_value: float) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in targets:
        weight = float(item["target_weight_pct"])
        enriched.append({**item, "target_amount_yuan": round(account_value * weight / 100, 2)})
    return enriched


def monthly_allocations(trade_log: list[dict[str, Any]]) -> dict[str, Any]:
    months: dict[str, Any] = {}
    for trade in trade_log:
        month = trade["trade_date"][:7]
        bucket = months.setdefault(month, {"unique_etfs": [], "rebalances": []})
        etfs = [item for item in trade["targets"] if item["symbol"] != "CASH"]
        for item in etfs:
            if item["symbol"] not in bucket["unique_etfs"]:
                bucket["unique_etfs"].append(item["symbol"])
        bucket["rebalances"].append(
            {
                "signal_date": trade["signal_date"],
                "trade_date": trade["trade_date"],
                "targets": etfs,
            }
        )
    return months


def monthly_performance(equity_curve: list[dict[str, Any]], period_start: pd.Timestamp, period_end: pd.Timestamp) -> dict[str, Any]:
    if not equity_curve:
        return {}
    curve = pd.DataFrame(equity_curve)
    curve["date"] = pd.to_datetime(curve["date"])
    months = sorted(curve["date"].dt.strftime("%Y-%m").unique())
    performance: dict[str, Any] = {}
    for month in months:
        month_start = pd.Timestamp(f"{month}-01")
        if month == date_to_str(period_start)[:7]:
            start_boundary = period_start
        else:
            start_boundary = month_start - pd.Timedelta(days=1)
        month_end = min(month_start + pd.offsets.MonthEnd(0), period_end)

        start_rows = curve[curve["date"] <= start_boundary]
        end_rows = curve[curve["date"] <= month_end]
        if start_rows.empty or end_rows.empty:
            continue
        start_value = float(start_rows.iloc[-1]["account_value_yuan"])
        end_value = float(end_rows.iloc[-1]["account_value_yuan"])
        performance[month] = {
            "start_value_yuan": round(start_value, 2),
            "end_value_yuan": round(end_value, 2),
            "profit_loss_yuan": round(end_value - start_value, 2),
            "return_pct": round((end_value / start_value - 1) * 100, 2) if start_value else None,
        }
    return performance


def run_backtest(
    lookback_days: int | None = DEFAULT_LOOKBACK_DAYS,
    cost_bps: float = DEFAULT_COST_BPS,
    capital: float = DEFAULT_CAPITAL,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
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

    final_date = pd.Timestamp(end_date) if end_date else price_panel.index.max()
    first_date = pd.Timestamp(start_date) if start_date else final_date - pd.Timedelta(days=lookback_days or DEFAULT_LOOKBACK_DAYS)
    signal_start = first_date - pd.Timedelta(days=7)
    signal_dates = weekly_signal_dates(price_panel, signal_start, final_date)

    schedules: dict[pd.Timestamp, dict[str, Any]] = {}
    for signal_date in signal_dates:
        trade_date = next_trading_date(price_panel, signal_date)
        if trade_date is None or trade_date < first_date or trade_date > final_date:
            continue
        signals = signals_for_date(signal_date, universe, histories, cn_names)
        portfolio = build_portfolio(signals)
        schedules[trade_date] = {
            "signal_date": signal_date,
            "trade_date": trade_date,
            "weights": as_weight_map(portfolio),
            "portfolio": portfolio,
            "regime": market_regime(signals),
            "buys": [
                {"symbol": item["symbol"], "name": item["name"], "score": item["score"]}
                for item in signals
                if item["market"] == "cn" and item["status"] == "buy"
            ][:5],
        }

    if not schedules:
        raise RuntimeError("No rebalance schedule generated.")

    period_start = min([date for date in price_panel.index if date >= first_date])
    period_end = max([date for date in price_panel.index if date <= final_date])
    dates = [date for date in price_panel.index if period_start <= date <= period_end]
    current_weights: dict[str, float] = {"CASH": 1.0}
    value = 1.0
    total_cost_pct = 0.0
    total_cost_amount = 0.0
    equity_curve: list[dict[str, Any]] = []
    daily_returns: list[float] = []
    trade_log: list[dict[str, Any]] = []
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
            cost_pct = trade_turnover * cost_bps / 10000
            cost_amount = value * capital * cost_pct
            value *= 1 - cost_pct
            total_cost_pct += cost_pct
            total_cost_amount += cost_amount
            current_weights = new_weights
            account_value = value * capital
            trade_log.append(
                {
                    "signal_date": date_to_str(scheduled["signal_date"]),
                    "trade_date": date_to_str(date),
                    "turnover_pct": round(trade_turnover * 100, 2),
                    "cost_pct": round(cost_pct * 100, 4),
                    "cost_amount_yuan": round(cost_amount, 2),
                    "account_value_yuan": round(account_value, 2),
                    "regime": scheduled["regime"],
                    "targets": enrich_targets_with_amounts(scheduled["portfolio"]["targets"], account_value),
                    "cn_buys": scheduled["buys"],
                }
            )

        equity_curve.append(
            {
                "date": date_to_str(date),
                "value": round(value, 6),
                "account_value_yuan": round(value * capital, 2),
                "daily_return_pct": round(day_return * 100, 4),
            }
        )
        previous_date = date

    cn_symbols = [item["symbol"] for item in universe.get("cn", [])]
    us_symbols = [item["symbol"] for item in universe.get("us", [])]
    cn_benchmark = benchmark_return(price_panel, cn_symbols, period_start, period_end)
    us_benchmark = benchmark_return(price_panel, us_symbols, period_start, period_end)
    final_value = capital * value

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "strategy": "etf-regime-rotation-v2",
        "assumptions": {
            "lookback_days": lookback_days,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital_yuan": capital,
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
            "profit_loss_yuan": round(final_value - capital, 2),
            "final_value_yuan": round(final_value, 2),
            "max_drawdown_pct": round(max_drawdown([row["value"] for row in equity_curve]), 2),
            "annualized_volatility_pct": round(annualized_volatility(daily_returns), 2),
            "transaction_cost_pct": round(total_cost_pct * 100, 4),
            "transaction_cost_yuan": round(total_cost_amount, 2),
            "rebalance_count": len(trade_log),
        },
        "benchmarks": {
            "cn_equal_weight_universe_pct": None if cn_benchmark is None else round(cn_benchmark, 2),
            "nasdaq_core_equal_weight_pct": None if us_benchmark is None else round(us_benchmark, 2),
        },
        "latest_targets": trade_log[-1]["targets"] if trade_log else [],
        "monthly_allocations": monthly_allocations(trade_log),
        "monthly_performance": monthly_performance(equity_curve, period_start, period_end),
        "trade_log": trade_log,
        "equity_curve": equity_curve,
        "disclaimer": "Rule-based ETF research backtest. It is not investment advice.",
    }


def write_report(result: dict[str, Any], output_name: str = "last_month_backtest") -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / f"{output_name}.json"
    md_path = REPORT_DIR / f"{output_name}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    metrics = result["metrics"]
    benchmarks = result["benchmarks"]
    period = result["period"]
    latest_targets = "\n".join(
        f"- {item['symbol']} {item['name']}: {item['target_weight_pct']}%, {item['target_amount_yuan']} yuan"
        for item in result.get("latest_targets", [])
    )
    monthly_sections = []
    for month in sorted(result.get("monthly_allocations", {})):
        bucket = result["monthly_allocations"][month]
        rebalance_rows = []
        for item in bucket["rebalances"]:
            target_text = ", ".join(
                f"{target['symbol']} {target['target_weight_pct']}%"
                for target in item["targets"]
            )
            rebalance_rows.append(f"- {item['trade_date']}: {target_text or 'no ETF position'}")
        monthly_sections.append(
            f"### {month}\n\n"
            f"- ETFs used in month: {', '.join(bucket['unique_etfs']) or 'none'}\n"
            + "\n".join(rebalance_rows)
        )
    monthly_text = "\n\n".join(monthly_sections)
    monthly_perf = "\n".join(
        f"| {month} | {item['start_value_yuan']} | {item['end_value_yuan']} | "
        f"{item['profit_loss_yuan']} | {item['return_pct']}% |"
        for month, item in sorted(result.get("monthly_performance", {}).items())
    )
    trades = "\n".join(
        f"| {item['signal_date']} | {item['trade_date']} | {item['turnover_pct']} | "
        f"{item['cost_pct']} | {item['cost_amount_yuan']} | {item['account_value_yuan']} | "
        f"{item['regime']['label']} | {', '.join(target['symbol'] for target in item['targets'])} |"
        for item in result.get("trade_log", [])
    )

    body = f"""# ETF Rotation Strategy Backtest

- Period: {period['start']} to {period['end']}
- Initial capital: {result['assumptions']['initial_capital_yuan']} yuan
- Final value: {metrics['final_value_yuan']} yuan
- Total return: {metrics['total_return_pct']}%
- Profit/loss: {metrics['profit_loss_yuan']} yuan
- Max drawdown: {metrics['max_drawdown_pct']}%
- Annualized volatility: {metrics['annualized_volatility_pct']}%
- Estimated transaction cost: {metrics['transaction_cost_pct']}%, about {metrics['transaction_cost_yuan']} yuan
- Rebalances: {metrics['rebalance_count']}
- CN ETF equal-weight benchmark: {benchmarks['cn_equal_weight_universe_pct']}%
- Nasdaq core equal-weight benchmark: {benchmarks['nasdaq_core_equal_weight_pct']}%

## Latest Targets

{latest_targets}

## Monthly Buy/Hold Plan

{monthly_text}

## Monthly Performance

| Month | Start yuan | End yuan | P/L yuan | Return |
| --- | ---: | ---: | ---: | ---: |
{monthly_perf}

## Rebalance Log

| Signal date | Trade date | Turnover % | Cost % | Cost yuan | Account yuan | Regime | Targets |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
{trades}

Notes: signals are generated after close and executed at the next available close. Cash return is 0. Transaction cost uses {result['assumptions']['transaction_cost_bps_per_turnover']} bps of ETF turnover. This is not investment advice.
"""
    md_path.write_text(body, encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the ETF regime rotation strategy.")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--start", dest="start_date")
    parser.add_argument("--end", dest="end_date")
    parser.add_argument("--capital", type=float, default=DEFAULT_CAPITAL)
    parser.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    parser.add_argument("--output", default="last_month_backtest")
    args = parser.parse_args()

    result = run_backtest(
        lookback_days=args.lookback_days,
        cost_bps=args.cost_bps,
        capital=args.capital,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    write_report(result, args.output)


if __name__ == "__main__":
    main()
