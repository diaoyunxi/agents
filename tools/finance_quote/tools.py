"""金融行情/汇率：默认走免密钥接口（货币汇率走 open.er-api.com；其余给出操作指引）。"""

from __future__ import annotations

import httpx

NAME = "finance_quote"
DESCRIPTION = "查询货币汇率 / 基础行情（免密钥汇率接口）；加密货币等深度行情给出可操作的获取方式"
PARAMETERS = {
    "type": "object",
    "properties": {
        "base": {"type": "string", "description": "基准货币 ISO 代码，如 CNY / USD，默认 CNY"},
        "symbols": {"type": "string", "description": "目标货币，逗号分隔，如 USD,EUR,JPY"},
        "query": {"type": "string", "description": "可选：其它查询意图（如 某只股票代码），用于提示获取方式"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 15"},
    },
    "required": [],
}


def run(base: str = "CNY", symbols: str = "", query: str = "", timeout: int = 15) -> dict:
    base = (base or "CNY").strip().upper() or "CNY"
    syms = [s.strip().upper() for s in (symbols or "").split(",") if s.strip()]
    timeout = max(5, min(int(timeout or 15), 60))

    lines = []
    if syms:
        try:
            resp = httpx.get("https://open.er-api.com/v6/latest/" + base, timeout=timeout)
            rates = resp.json().get("rates", {})
            lines.append(f"汇率（基准 {base}）更新于 {resp.json().get('time_last_update_utc', '')}:")
            for s in syms:
                lines.append(f"  1 {base} = {rates.get(s, '?')} {s}")
        except httpx.HTTPError as exc:
            lines.append(f"汇率接口请求失败: {exc}")
    else:
        lines.append(f"未提供目标货币（symbols）。汇率基准为 {base}。")

    if (query or "").strip():
        lines.append("")
        lines.append(f"查询意图: `{query}`。免密钥接口仅覆盖货币汇率；"
                     "股票/加密货币深度行情请配置专用 API（如 hq.sinajs.cn、CoinGecko、Alpha Vantage），"
                     "或用 http_request 带密钥调用后解析。")
    return {"output": "\n".join(lines)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
