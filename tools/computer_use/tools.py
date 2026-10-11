"""computer_use —— 无障碍树优先的桌面操控工具。

参考 github 项目 ``Perception-Dynamics-Inc/a11y-computer-use`` 的核心思路：
模型读取「剪枝后的控件树」（每个元素带 ref，如 ``e3``），然后说 ``click e3``，
而不是去猜像素坐标。点击优先走 UI Automation 的无障碍动作（不移动鼠标），
只有必要时才退化为坐标或键盘的合成输入。

本工具仅支持 Windows。
"""

from __future__ import annotations

import time
from typing import Any

NAME = "computer_use"
DANGEROUS = True
DESCRIPTION = "观察并操控 Windows 桌面窗口：抓取剪枝控件树拿到元素 ref，再按 ref 点击、输入、设值"
PARAMETERS = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "description": "要执行的动作",
            "enum": [
                "windows", "snapshot", "find", "click", "type", "key", "set_value", "scroll", "status",
            ],
        },
        "app": {
            "type": "string",
            "description": "目标窗口：标题 / 类名 / 进程名的子串（不区分大小写），如 notepad.exe",
        },
        "ref": {
            "type": "string",
            "description": "元素引用，形如 e3，来自最近一次 snapshot / find 的结果",
        },
        "query": {"type": "string", "description": "find 用：标题或值的子串（不区分大小写）"},
        "role": {"type": "string", "description": "find 用：角色子串，如 button、edit、link"},
        "text": {"type": "string", "description": "type 用：要输入的文本"},
        "value": {"type": "string", "description": "set_value 用：要写入的值"},
        "chord": {"type": "string", "description": "key 用：快捷键，如 ctrl+s、alt+f4、escape"},
        "x": {"type": "integer", "description": "物理像素 X（click / scroll 无 ref 时使用）"},
        "y": {"type": "integer", "description": "物理像素 Y（click / scroll 无 ref 时使用）"},
        "button": {"type": "string", "description": "鼠标键：left/right/middle，默认 left"},
        "count": {"type": "integer", "description": "点击次数 1-3，默认 1"},
        "dx": {"type": "integer", "description": "scroll 水平滚动格数，正数向右"},
        "dy": {"type": "integer", "description": "scroll 垂直滚动格数，正数向下"},
        "into_view": {"type": "boolean", "description": "scroll 用：只把 ref 滚入可视区，不移动鼠标"},
        "max_elements": {"type": "integer", "description": "snapshot 最多返回的元素数，默认 300"},
        "include_bounds": {"type": "boolean", "description": "是否在每行打印坐标矩形，默认否"},
    },
    "required": ["action"],
}

# 会话级的“最近一次快照”，用于按 ref 重新定位元素。
_STATE: dict[str, Any] = {"snapshot": None}


def _error(code: str, message: str, detail: dict | None = None) -> dict:
    payload = {"ok": False, "output": f"[{code}] {message}"}
    if detail:
        payload["output"] += "\n" + _detail_text(detail)
    return payload


def _detail_text(detail: dict) -> str:
    import json

    try:
        return json.dumps(detail, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(detail)


def _resolve_ref(ref: str, snap):
    """按 ref 在最新树中重新定位元素，返回 (节点, 最新快照)。"""

    U = _uia
    anchor_node = snap.by_ref(ref)
    if anchor_node is None:
        raise U.UIError("invalid_arguments", f"ref {ref!r} 不在最近一次快照 {snap.snapshot_id} 中")
    # 沿用该快照生成时的元素预算，避免复定位时把目标排除在新树之外
    return U.resolve(anchor_node, snap.app, snap.scope, getattr(snap, "max_elements", 300))


def _load():
    try:
        from . import _uia  # type: ignore

        return _uia
    except ImportError:  # 被加载器以无包名方式导入时的回退
        import importlib.util
        import sys
        from pathlib import Path

        path = Path(__file__).with_name("_uia.py")
        spec = importlib.util.spec_from_file_location("_uia", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["_uia"] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module


_uia = None


def _ensure():
    global _uia
    if _uia is None:
        _uia = _load()
    return _uia


def run(
    action: str,
    app: str | None = None,
    ref: str | None = None,
    query: str | None = None,
    role: str | None = None,
    text: str | None = None,
    value: str | None = None,
    chord: str | None = None,
    x: int | None = None,
    y: int | None = None,
    button: str = "left",
    count: int = 1,
    dx: int = 0,
    dy: int = 0,
    into_view: bool = False,
    max_elements: int = 300,
    include_bounds: bool = False,
) -> dict:
    U = _ensure()
    act = (action or "").strip().lower()

    try:
        if act == "status":
            return _do_status(U)
        if act == "windows":
            return _do_windows(U)
        if act == "snapshot":
            return _do_snapshot(U, app, max_elements, include_bounds)
        if act == "find":
            return _do_find(U, app, query, role, max_elements, include_bounds)
        if act == "click":
            return _do_click(U, ref, x, y, button, count, app)
        if act == "type":
            return _do_type(U, text, ref, app)
        if act == "key":
            return _do_key(U, chord, ref, app)
        if act == "set_value":
            return _do_set_value(U, ref, value, app)
        if act == "scroll":
            return _do_scroll(U, ref, x, y, dx, dy, into_view, app)
        return _error("invalid_arguments", f"未知 action {action!r}")
    except U.UIError as exc:
        return _error(exc.code, exc.message, exc.detail)
    except Exception as exc:  # noqa: BLE001 - 工具不应把栈抛给模型
        return _error("error", f"computer_use 执行失败: {exc}")


# --------------------------------------------------------------------------- #
# 各动作
# --------------------------------------------------------------------------- #


def _do_status(U) -> dict:
    if not U.IS_WINDOWS:
        return {"ok": True, "output": "computer_use 仅支持 Windows；当前平台不可用。"}
    U._uia()
    return {"ok": True, "output": "computer_use 就绪（Windows UI Automation 可用）。"}


def _do_windows(U) -> dict:
    items = U.list_windows()
    if not items:
        return {"output": "未发现可见的顶层窗口。"}
    lines = [f"发现 {len(items)} 个顶层窗口："]
    for i, item in enumerate(items, start=1):
        title = item["title"] or "(无标题)"
        lines.append(f"{i:>3}. {title} | exe={item['exe'] or '?'} | class={item['class']} | pid={item['pid']}")
    lines.append("提示：snapshot 的 app 参数可以是标题、类名或 exe 的子串。")
    return {"output": "\n".join(lines)}


def _do_snapshot(U, app: str | None, max_elements: int, include_bounds: bool) -> dict:
    snap = U.snapshot(app or "", "window", max_elements)
    _STATE["snapshot"] = snap
    return {"output": U.render(snap, include_bounds)}


def _do_find(U, app: str | None, query: str | None, role: str | None,
             max_elements: int, include_bounds: bool) -> dict:
    if not (query or role):
        return _error("invalid_arguments", "find 至少需要 query 或 role 之一")
    snap = U.snapshot(app or "", "window", max_elements)
    _STATE["snapshot"] = snap
    matches = U.find(snap, query=query, role=role)
    if not matches:
        return {"output": f"[{snap.snapshot_id}] {snap.app} 中没有匹配的元素。"}
    return {"output": U.render_matches(snap, matches, include_bounds)}


def _do_click(U, ref: str | None, x: int | None, y: int | None,
              button: str, count: int, app: str | None) -> dict:
    if ref:
        snap = _require_snapshot(U, app)
        node, fresh = _resolve_ref(ref, snap)
        _STATE["snapshot"] = fresh
        used = U.press(node, U._uia()[0])
        if used:
            return {"output": f"已通过无障碍动作({used})激活 {node.ref} {node.role} {node.name!r}"}
        point = U.center_of(node)
        if point is None:
            return _error("not_visible", f"{node.ref} 没有可用坐标，无法点击")
        U.click_point(point[0], point[1], button, count)
        return {"output": f"已点击 {node.ref} {node.role} {node.name!r} 于坐标 {point[0]},{point[1]}"}
    if x is None or y is None:
        return _error("invalid_arguments", "click 需要 ref，或同时给出 x 与 y")
    U.click_point(int(x), int(y), button, count)
    return {"output": f"已点击坐标 {int(x)},{int(y)}（{button} x{count}）"}


def _do_type(U, text: str | None, ref: str | None, app: str | None) -> dict:
    if text is None:
        return _error("invalid_arguments", "type 需要 text")
    if ref:
        snap = _require_snapshot(U, app)
        node, fresh = _resolve_ref(ref, snap)
        _STATE["snapshot"] = fresh
        if node.secure:
            return _error("secure_field", "目标是密码字段，拒绝输入")
        if node.editable and U.set_value(node, text, U._uia()[0]):
            return {"output": f"已用 ValuePattern 直接写入 {node.ref}，共 {len(text)} 字符"}
        if not U.focus(node):
            return _error("focus_lost", f"无法让 {node.ref} 获得焦点，未输入任何内容")
        time.sleep(0.05)
        U.type_unicode(text)
        return {"output": f"已聚焦 {node.ref} 并输入 {len(text)} 字符"}
    U.type_unicode(text)
    return {"output": f"已向当前焦点窗口输入 {len(text)} 字符"}


def _do_key(U, chord: str | None, ref: str | None, app: str | None) -> dict:
    if not chord:
        return _error("invalid_arguments", "key 需要 chord，如 ctrl+s")
    if ref:
        snap = _require_snapshot(U, app)
        node, fresh = _resolve_ref(ref, snap)
        _STATE["snapshot"] = fresh
        U.focus(node)
        time.sleep(0.05)
    U.press_chord(chord)
    return {"output": f"已发送按键 {chord}"}


def _do_set_value(U, ref: str | None, value: str | None, app: str | None) -> dict:
    if not ref:
        return _error("invalid_arguments", "set_value 需要 ref")
    if value is None:
        return _error("invalid_arguments", "set_value 需要 value")
    snap = _require_snapshot(U, app)
    node, fresh = _resolve_ref(ref, snap)
    _STATE["snapshot"] = fresh
    if not U.set_value(node, value, U._uia()[0]):
        return _error(
            "unsupported",
            f"{node.ref} {node.role} 不支持 ValuePattern 直接设值；可改用 click + type",
        )
    return {"output": f"已把 {node.ref} 的值设为 {value!r}"}


def _do_scroll(U, ref: str | None, x: int | None, y: int | None,
               dx: int, dy: int, into_view: bool, app: str | None) -> dict:
    if ref:
        snap = _require_snapshot(U, app)
        node, fresh = _resolve_ref(ref, snap)
        _STATE["snapshot"] = fresh
        if into_view:
            if U.scroll_into_view(node, U._uia()[0]):
                return {"output": f"已把 {node.ref} 滚入可视区（未移动鼠标）"}
            return _error("unsupported", f"{node.ref} 不支持 ScrollItemPattern.ScrollIntoView")
        point = U.center_of(node)
        if point is None:
            return _error("not_visible", f"{node.ref} 没有可用坐标，无法滚动")
        U.scroll_wheel(point[0], point[1], dx, dy)
        return {"output": f"已在 {node.ref} 处滚动 dx={dx} dy={dy}"}
    if x is None or y is None:
        return _error("invalid_arguments", "scroll 需要 ref，或同时给出 x 与 y")
    U.scroll_wheel(int(x), int(y), dx, dy)
    return {"output": f"已在坐标 {int(x)},{int(y)} 处滚动 dx={dx} dy={dy}"}


def _require_snapshot(U, app: str | None):
    snap = _STATE.get("snapshot")
    if snap is None or (app and app.strip() and app.strip().lower() not in (snap.app or "").lower()):
        target = app or (snap.app if snap is not None else None)
        if not target:
            raise U.UIError("invalid_arguments", "还没有快照，请先调用 action=snapshot")
        snap = U.snapshot(target, "window", 300)
        _STATE["snapshot"] = snap
    return snap


__all__ = ["DANGEROUS", "DESCRIPTION", "NAME", "PARAMETERS", "run"]
