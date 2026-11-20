"""技能选择器：任务正式开始前，用一次独立的模型请求决定加载哪些技能。

该请求「不进主对话上下文」：它只接收 [技能清单 + 用户请求]，输出「应当加载的
技能名列表（或空）」；随后调用方把选中的技能注入正式对话的 system 提示词。
若模型返回了技能库里不存在的技能名，则重试，最多 3 次。
"""

from __future__ import annotations

import json
import re

import ai_client
import config
import skill_loader

# 选择请求的严格系统提示词：只允许回显清单内已存在的 name，禁止编造/解释。
_SELECTOR_SYSTEM = (
    "你是一个技能路由（skill router）。下面会给出一个「可用技能清单」和「用户请求」，"
    "你的唯一任务是判断哪些技能应当被加载进后续对话。\n"
    "输出规则（必须严格遵守）：\n"
    "1. 只输出一个 JSON 数组，元素是技能的 name（字符串），例如 [\"pdf\"] 或 [\"code-review\",\"executing-plans\"]。\n"
    "2. 如果没有任何技能与请求相关，输出空数组 []。\n"
    "3. 只能使用「可用技能清单」中真实存在的 name，禁止编造、禁止翻译、禁止增删字符。\n"
    "4. 不要输出任何解释、多余文字、Markdown 或代码块，只输出那个 JSON 数组。\n"
    "5. 依据每个技能的 description 与 when_to_use 判断相关性，宁缺毋滥，避免加载无关技能。"
)

_MAX_ATTEMPTS = 3


def _catalog() -> list:
    """返回紧凑技能清单（仅 name / description / when_to_use），用于喂给选择请求。"""
    items = []
    for s in skill_loader.load_skills():
        items.append({
            "name": s["name"],
            "description": s.get("description", ""),
            "when_to_use": s.get("when_to_use", ""),
        })
    return items


def _catalog_text(catalog: list) -> str:
    if not catalog:
        return "(空)"
    lines = []
    for it in catalog:
        desc = (it.get("description") or "").strip()
        when = (it.get("when_to_use") or "").strip()
        head = "- " + it["name"]
        if desc:
            head += " — " + desc
        if when:
            head += "（适用：" + when[:160] + "）"
        lines.append(head)
    return "\n".join(lines)


def _parse_names(text: str) -> list:
    """从模型输出中解析出技能名数组；解析失败时尽力回退提取引号内的 token。"""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
        t = t.strip()
    m = re.search(r"\[[\s\S]*\]", t)
    if not m:
        return []
    arr = m.group(0)
    try:
        data = json.loads(arr)
    except (json.JSONDecodeError, ValueError):
        return [x.strip() for x in re.findall(r'"([^"]+)"', arr) if x.strip()]
    if isinstance(data, list):
        return [str(x).strip().strip("\"'") for x in data if str(x).strip()]
    return []


async def _resolve_provider(provider_id: str = "", model: str = ""):
    """返回 (provider, model)；未指定时回落到 config 当前选择。抛错表示不可用。"""
    providers = config.get("providers", []) or []
    if not providers:
        raise ValueError("尚未配置任何 AI 提供商。")
    pid = provider_id or config.get("ai.active_provider_id", "")
    provider = next((p for p in providers if p.get("id") == pid), None) or providers[0]
    chosen = model or config.get("ai.active_model", "") or provider.get("default_model", "")
    if not chosen:
        raise ValueError("尚未选择模型。")
    return provider, chosen


async def select_skills(user_request: str, provider_id: str = "", model: str = "") -> dict:
    """决定加载哪些技能。

    返回：{"skills": [...], "ok": bool, "attempts": int, "note": str}
    - ok=True 且 skills 为合法清单内技能（或空）时，调用方据此注入上下文。
    - 选择请求本身（模型报错 / 未配置提供商）不阻塞主任务：ok=False 时按「加载全部」降级。
    """
    catalog = _catalog()
    if not catalog:
        return {"skills": [], "ok": True, "attempts": 0, "note": "技能库为空"}

    valid = {it["name"] for it in catalog}
    cat_text = _catalog_text(catalog)
    user_msg = "用户请求：\n{0}\n\n可用技能清单：\n{1}".format(user_request, cat_text)

    try:
        provider, chosen = await _resolve_provider(provider_id, model)
    except Exception as exc:  # noqa: BLE001
        # 无法发起选择请求（未配置提供商等）：降级为加载全部技能，不阻塞主任务。
        return {"skills": list(valid), "ok": False, "attempts": 0,
                "note": "无法调用技能选择请求（" + str(exc) + "），已降级为加载全部技能"}

    last_valid: list = []
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        messages = [
            {"role": "system", "content": _SELECTOR_SYSTEM},
            {"role": "user", "content": user_msg},
        ]
        content, _, _ = await ai_client.chat(provider, chosen, messages)
        raw_names = _parse_names(content)
        existing = [n for n in raw_names if n in valid]
        # 去重并保持出现顺序
        seen = set()
        existing = [n for n in existing if not (n in seen or seen.add(n))]
        last_valid = existing

        unknown = [n for n in raw_names if n not in valid]
        # 全部合法（含空数组）→ 成功。出现未知 name → 重试。
        if not unknown:
            return {"skills": existing, "ok": True, "attempts": attempt,
                    "note": "已选定技能: " + (", ".join(existing) if existing else "（无）")}

    # 重试耗尽：仍含未知 name。返回最后一次的合法子集（可能为空），不阻塞主任务。
    return {"skills": last_valid, "ok": True, "attempts": _MAX_ATTEMPTS,
            "note": "选择请求多次含非法技能名，已按合法子集处理: " +
                    (", ".join(last_valid) if last_valid else "（无）")}
