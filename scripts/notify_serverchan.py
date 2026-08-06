from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlencode

import requests


ROOT = Path(__file__).resolve().parents[1]
LATEST_PATH = ROOT / "site" / "data" / "latest.json"


def endpoint_for_key(sendkey: str) -> str:
    if sendkey.startswith("sctp"):
        match = re.match(r"^sctp(\d+)t", sendkey)
        if not match:
            raise ValueError("Invalid ServerChan 3 sendkey format")
        uid = match.group(1)
        return f"https://{uid}.push.ft07.com/send/{sendkey}.send"
    return f"https://sctapi.ftqq.com/{sendkey}.send"


def build_message(payload: dict) -> tuple[str, str]:
    regime = payload.get("regime", {})
    buys = payload.get("summary", {}).get("buy", [])
    sells = payload.get("summary", {}).get("sell", [])
    site_url = os.getenv("SITE_URL", "").rstrip("/")
    latest_url = f"{site_url}/data/latest.json" if site_url else ""

    title = f"ETF 信号日报：{regime.get('label', '未知')}，买入 {regime.get('buy_count', 0)}，卖出 {regime.get('sell_count', 0)}"
    lines = [
        f"生成时间：{payload.get('generated_at', '')}",
        f"市场状态：{regime.get('label', '未知')}",
        f"平均分：{regime.get('average_score', '')}",
        "",
        "## 买入候选",
    ]
    if buys:
        for item in buys[:5]:
            lines.append(f"- {item['symbol']} {item['name']}：{item['score']} 分，{item['theme']}")
    else:
        lines.append("- 今日无买入候选")

    lines.append("")
    lines.append("## 卖出/回避")
    if sells:
        for item in sells[:5]:
            lines.append(f"- {item['symbol']} {item['name']}：{item['score']} 分，{item['theme']}")
    else:
        lines.append("- 今日无卖出/回避信号")

    if site_url:
        lines.extend(["", f"[打开 PWA 看板]({site_url})", f"[查看 latest.json]({latest_url})"])

    lines.extend(["", "说明：规则化 ETF 研究输出，不构成投资建议。"])
    return title, "\n".join(lines)


def main() -> None:
    sendkey = os.getenv("SERVERCHAN_SENDKEY")
    if not sendkey:
        print("SERVERCHAN_SENDKEY not set; skip notification.")
        return

    payload = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    title, desp = build_message(payload)
    response = requests.post(endpoint_for_key(sendkey), data={"title": title, "desp": desp}, timeout=20)
    response.raise_for_status()
    result = response.json()
    if result.get("code") != 0:
        raise RuntimeError(f"ServerChan returned non-zero code: {result}")
    print("ServerChan notification sent.")


if __name__ == "__main__":
    main()
