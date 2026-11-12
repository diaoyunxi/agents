"""地理编码 / 逆地理编码（Nominatim 免密钥）。"""

from __future__ import annotations

import httpx

NAME = "geolocate"
DESCRIPTION = "地理编码/逆地理编码：地址->经纬度，或经纬度->地址（Nominatim 免密钥，限流 1 次/秒）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "address": {"type": "string", "description": "正查用：地址文本，如 北京市朝阳区"},
        "lat": {"type": "number", "description": "反查用：纬度"},
        "lon": {"type": "number", "description": "反查用：经度"},
        "limit": {"type": "integer", "description": "正查最多返回结果数，默认 3"},
        "timeout": {"type": "integer", "description": "超时秒数，默认 20"},
    },
    "required": [],
}


def run(address: str = "", lat: float | None = None, lon: float | None = None,
        limit: int = 3, timeout: int = 20) -> dict:
    limit = max(1, min(int(limit or 3), 10))
    timeout = max(5, min(int(timeout or 20), 60))
    headers = {"User-Agent": "agents-geolocate/1.0"}

    # 反查
    if lat is not None and lon is not None:
        try:
            resp = httpx.get(f"https://nominatim.openstreetmap.org/reverse",
                             params={"lat": lat, "lon": lon, "format": "json", "zoom": 16, "accept-language": "zh"},
                             headers=headers, timeout=timeout)
            if resp.status_code >= 400:
                return {"ok": False, "output": f"HTTP {resp.status_code}"}
            d = resp.json()
            addr = d.get("address", {})
            display = d.get("display_name", "")
            lines = [f"经纬度 {lat},{lon} ->"]
            for key in ("country", "state", "city", "town", "suburb", "road"):
                if addr.get(key):
                    lines.append(f"  {key}: {addr[key]}")
            lines.append(f"完整: {display}")
            return {"output": "\n".join(lines)}
        except httpx.HTTPError as exc:
            return {"ok": False, "output": f"反查失败: {exc}"}

    # 正查
    if not (address or "").strip():
        return {"ok": False, "output": "请提供 address（正查）或 lat+lon（反查）"}
    try:
        resp = httpx.get("https://nominatim.openstreetmap.org/search",
                         params={"q": address.strip(), "format": "json", "limit": limit, "accept-language": "zh"},
                         headers=headers, timeout=timeout)
        if resp.status_code >= 400:
            return {"ok": False, "output": f"HTTP {resp.status_code}"}
        results = resp.json()
        if not results:
            return {"output": f"未找到 `{address}` 的位置（换个更具体的写法）"}
        lines = [f"地址: {address.strip()} | {len(results)} 个结果"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.get('display_name','')}")
            lines.append(f"   坐标: {r.get('lat')},{r.get('lon')} | 类型: {r.get('type','')}")
        return {"output": "\n".join(lines)}
    except httpx.HTTPError as exc:
        return {"ok": False, "output": f"正查失败: {exc}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
