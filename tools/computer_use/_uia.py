"""Windows UI Automation 访问层。

灵感来自 github 项目 ``Perception-Dynamics-Inc/a11y-computer-use``：不靠像素坐标，
而是把控件树剪枝成带引用（ref，如 ``e3``）的文本给模型阅读，再按 ref 重新定位元素
并调用无障碍动作（Invoke / Toggle / Select / Expand / SetValue / ScrollIntoView），
必要时才退化为坐标或键盘的合成输入（SendInput）。

本模块只依赖标准库 + ``comtypes``（Windows 自带 UI Automation COM 接口的封装），
不引入 ``uiautomation`` 之类的第三方包。非 Windows 平台会在调用时给出结构化错误。
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Any

IS_WINDOWS = hasattr(ctypes, "windll")

# --------------------------------------------------------------------------- #
# 控件类型（UIA ControlTypeId -> 简短角色名）
# --------------------------------------------------------------------------- #

_CONTROL_TYPES: dict[int, str] = {
    50000: "button", 50001: "calendar", 50002: "checkbox", 50003: "combobox",
    50004: "edit", 50005: "link", 50006: "image", 50007: "listitem",
    50008: "list", 50009: "menu", 50010: "menubar", 50011: "menuitem",
    50012: "progressbar", 50013: "radiobutton", 50014: "scrollbar",
    50015: "slider", 50016: "spinner", 50017: "statusbar", 50018: "tab",
    50019: "tabitem", 50020: "text", 50021: "toolbar", 50022: "tooltip",
    50023: "tree", 50024: "treeitem", 50025: "custom", 50026: "group",
    50027: "thumb", 50028: "datagrid", 50029: "dataitem", 50030: "document",
    50031: "splitbutton", 50032: "window", 50033: "pane", 50034: "header",
    50035: "headeritem", 50036: "table", 50037: "titlebar", 50038: "separator",
    50039: "semanticzoom", 50040: "appbar",
}

#: 即使没有交互 pattern 也当作目标看的角色（配合键盘焦点判断）。
_CLICKABLE_ROLES = frozenset({
    "button", "splitbutton", "link", "menuitem", "listitem", "tabitem",
    "treeitem", "dataitem", "checkbox", "radiobutton", "combobox", "slider",
    "spinner",
})

#: 容器/结构类角色：有名字时保留，用于把可交互元素区分开。
_KEEP_ROLES = frozenset({
    "window", "menu", "menubar", "menuitem", "toolbar", "tab", "tabitem",
    "list", "table", "datagrid", "tree", "statusbar", "titlebar", "header",
    "document", "edit", "combobox", "text", "link", "image",
})

#: 纯包装角色：无名字且不可交互时会被“提升”（用子节点替代自身），减少噪音。
_WRAPPER_ROLES = frozenset({"pane", "group", "custom", "semanticzoom"})

_MAX_DEPTH = 24
_MAX_VALUE_CHARS = 160
_MAX_NAME_CHARS = 120


class UIError(Exception):
    """结构化失败。``code`` 为稳定的机器可读标识（对齐参考项目的 ErrorCode）。"""

    def __init__(self, code: str, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message, "detail": self.detail}


# --------------------------------------------------------------------------- #
# COM / UIA 初始化
# --------------------------------------------------------------------------- #

_local = threading.local()


def _ensure_dpi() -> None:
    """声明进程 DPI 感知，使 SetCursorPos / 控件矩形都使用物理像素。"""

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:  # noqa: BLE001
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass


def _uia():
    """返回 (UIA 常量模块, IUIAutomation 实例)，按线程缓存。"""

    if not IS_WINDOWS:
        raise UIError("unsupported", "computer_use 目前仅支持 Windows（UI Automation）")
    cached = getattr(_local, "uia", None)
    if cached is not None:
        return cached
    import comtypes.client

    try:
        from comtypes.gen import UIAutomationClient as UIA
    except ImportError:  # 首次使用需生成 COM 包装模块
        try:
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient as UIA
        except Exception as exc:
            raise UIError("unsupported", f"无法加载 UI Automation 类型库: {exc}") from exc

    try:
        instance = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
    except Exception as exc:
        raise UIError("unsupported", f"无法创建 UIAutomation 对象: {exc}") from exc
    _ensure_dpi()
    _local.uia = (UIA, instance)
    return _local.uia


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001 - 跨进程 UIA 调用必须降级而不是崩
        return default


def _pattern(el, pid: int):
    try:
        return el.GetCurrentPattern(pid)
    except Exception:  # noqa: BLE001
        return None


def _qi(obj, iface):
    if obj is None:
        return None
    try:
        return obj.QueryInterface(iface)
    except Exception:  # noqa: BLE001
        return None


def _first_child(walker, el):
    try:
        return walker.GetFirstChildElement(el)
    except Exception:  # noqa: BLE001
        return None


def _next_sibling(walker, el):
    try:
        return walker.GetNextSiblingElement(el)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# 元素读取
# --------------------------------------------------------------------------- #


@dataclass
class Node:
    """剪枝后的一个控件节点；``handle`` 只在本次读取内有效，用于执行动作。"""

    role: str
    name: str = ""
    value: str | None = None
    bounds: tuple[int, int, int, int] | None = None  # (left, top, width, height)
    enabled: bool = True
    focused: bool = False
    focusable: bool = False
    secure: bool = False
    clickable: bool = False
    editable: bool = False
    checked: bool | None = None
    selected: bool = False
    expanded: bool | None = None
    automation_id: str = ""
    offscreen: bool = False
    ref: str = ""
    children: list[Node] = field(default_factory=list)
    handle: Any = None

    @property
    def anchor(self) -> Anchor:
        return Anchor(
            role=self.role, name=self.name, automation_id=self.automation_id,
            bounds=self.bounds,
        )


@dataclass(frozen=True)
class Anchor:
    """跨快照稳定定位元素所需的“锚点”（不持有 COM 句柄）。"""

    role: str
    name: str
    automation_id: str
    bounds: tuple[int, int, int, int] | None


def _read(el, UIA) -> Node:
    role_id = _safe(lambda: int(el.CurrentControlType), -1)
    role = _CONTROL_TYPES.get(role_id, "custom")
    name = (_safe(lambda: el.CurrentName, "") or "").strip()
    secure = bool(_safe(lambda: el.CurrentIsPassword, False)) and role in ("edit", "document")

    bounds = None
    rect = _safe(lambda: el.CurrentBoundingRectangle)
    if rect is not None:
        try:
            left, top = int(rect.left), int(rect.top)
            width, height = int(rect.right) - left, int(rect.bottom) - top
            if width > 0 and height > 0:
                bounds = (left, top, width, height)
        except Exception:  # noqa: BLE001
            bounds = None

    invoke = _qi(_pattern(el, UIA.UIA_InvokePatternId), UIA.IUIAutomationInvokePattern)
    toggle = _qi(_pattern(el, UIA.UIA_TogglePatternId), UIA.IUIAutomationTogglePattern)
    select = _qi(_pattern(el, UIA.UIA_SelectionItemPatternId), UIA.IUIAutomationSelectionItemPattern)
    expand = _qi(_pattern(el, UIA.UIA_ExpandCollapsePatternId), UIA.IUIAutomationExpandCollapsePattern)
    value = _qi(_pattern(el, UIA.UIA_ValuePatternId), UIA.IUIAutomationValuePattern)

    focusable = bool(_safe(lambda: el.CurrentIsKeyboardFocusable, False))
    editable = bool(value is not None and not _safe(lambda: value.CurrentIsReadOnly, True))
    clickable = any(p is not None for p in (invoke, toggle, select, expand)) or (
        focusable and role in _CLICKABLE_ROLES
    )

    checked = None
    if toggle is not None:
        state = _safe(lambda: int(toggle.CurrentToggleState), None)
        checked = None if state is None else state != 0

    expanded = None
    if expand is not None:
        state = _safe(lambda: int(expand.CurrentExpandCollapseState), None)
        expanded = None if state in (None, 3) else state in (1, 2)

    selected = bool(_safe(lambda: select.CurrentIsSelected, False)) if select is not None else False

    text_value = None
    if not secure and value is not None:
        raw = _safe(lambda: value.CurrentValue)
        if raw is not None:
            text_value = str(raw)[:_MAX_VALUE_CHARS]

    return Node(
        role=role,
        name=name[:_MAX_NAME_CHARS],
        value=text_value,
        bounds=bounds,
        enabled=bool(_safe(lambda: el.CurrentIsEnabled, True)),
        focused=bool(_safe(lambda: el.CurrentHasKeyboardFocus, False)),
        focusable=focusable,
        secure=secure,
        clickable=clickable,
        editable=editable,
        checked=checked,
        selected=selected,
        expanded=expanded,
        automation_id=(_safe(lambda: el.CurrentAutomationId, "") or "").strip(),
        offscreen=bool(_safe(lambda: el.CurrentIsOffscreen, False)),
        handle=el,
    )


def _structural(node: Node) -> bool:
    return bool(node.name) or node.clickable or node.editable or node.role in _KEEP_ROLES


def _prune(node: Node) -> list[Node]:
    """递归剪枝：丢弃无意义包装，把它们的子节点提升到上一层。"""

    kept: list[Node] = []
    for child in node.children:
        kept.extend(_prune(child))
    node.children = kept

    wrapper = node.role in _WRAPPER_ROLES and not node.name and not (node.clickable or node.editable)
    if wrapper:
        return kept
    if _structural(node) or kept:
        return [node]
    return []


# --------------------------------------------------------------------------- #
# 快照
# --------------------------------------------------------------------------- #


@dataclass
class Snapshot:
    app: str
    scope: str
    snapshot_id: str
    roots: list[Node]
    nodes: list[Node]  # 前序，带 ref
    created: float
    truncated: bool = False
    max_elements: int = 300  # 生成本快照的元素预算，复定位时沿用同一预算

    def by_ref(self, ref: str) -> Node | None:
        for node in self.nodes:
            if node.ref == ref:
                return node
        return None


def _exe_for_pid(pid: int) -> str | None:
    """进程可执行文件名（Windows 上的应用标识，等价于 macOS 的 bundle id）。"""

    if not pid:
        return None
    import os

    k32 = ctypes.windll.kernel32
    handle = k32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buf))
        if k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
    finally:
        k32.CloseHandle(handle)
    return None


def list_windows() -> list[dict[str, Any]]:
    """枚举顶层窗口：标题、类名、进程、可执行名。"""

    _UIA, uia = _uia()
    walker = uia.RawViewWalker
    root = uia.GetRootElement()
    out: list[dict[str, Any]] = []
    el = _first_child(walker, root)
    while el is not None:
        name = (_safe(lambda: el.CurrentName, "") or "").strip()
        pid = int(_safe(lambda: el.CurrentProcessId, 0) or 0)
        out.append({
            "title": name,
            "class": (_safe(lambda: el.CurrentClassName, "") or "").strip(),
            "pid": pid,
            "exe": _exe_for_pid(pid) or "",
        })
        el = _next_sibling(walker, el)
    return out


def find_window(app: str):
    """按标题 / 类名 / 进程可执行名的子串（不区分大小写）找到顶层窗口元素。

    评分优先：进程名精确 > 标题子串 > 进程名子串 > 类名子串。这样 ``chrome`` 会命中
    ``chrome.exe``，而不会先撞上 Electron 应用共用的窗口类名 ``Chrome_WidgetWin_1``。
    """

    needle = (app or "").strip().lower()
    if not needle:
        return None
    needle_stem = needle.removesuffix(".exe")
    _UIA, uia = _uia()
    walker = uia.RawViewWalker
    root = uia.GetRootElement()
    best_el, best_score = None, 0
    el = _first_child(walker, root)
    while el is not None:
        name = (_safe(lambda: el.CurrentName, "") or "").lower()
        cls = (_safe(lambda: el.CurrentClassName, "") or "").lower()
        pid = int(_safe(lambda: el.CurrentProcessId, 0) or 0)
        exe = (_exe_for_pid(pid) or "").lower()
        stem = exe.removesuffix(".exe")
        score = 0
        if stem and (stem == needle or stem == needle_stem):
            score = 100
        elif needle in name or needle_stem in name:
            score = 60
        elif stem and (needle in stem or needle_stem in stem):
            score = 50
        elif needle in cls or needle_stem in cls:
            score = 10
        if score > best_score:
            best_el, best_score = el, score
        el = _next_sibling(walker, el)
    return best_el


_counter = {"n": 0}


def snapshot(app: str, scope: str = "window", max_elements: int = 300) -> Snapshot:
    """抓取 ``app`` 的剪枝无障碍树，为每个节点分配 ref（e1、e2…）。"""

    UIA, uia = _uia()
    name = (app or "").strip()
    if not name:
        raise UIError("app_not_found", "必须提供 app（窗口标题 / 类名 / 进程名子串）")
    root_el = find_window(name)
    if root_el is None:
        raise UIError("app_not_found", f"找不到匹配 {name!r} 的窗口", {"windows": [
            w["title"] for w in list_windows()[:30]
        ]})

    walker = uia.RawViewWalker
    budget = {"left": max(1, int(max_elements))}
    truncated = {"hit": False}

    def walk(el, depth: int) -> Node:
        node = _read(el, UIA)
        if depth >= _MAX_DEPTH or budget["left"] <= 0:
            if depth < _MAX_DEPTH and budget["left"] <= 0:
                truncated["hit"] = True
            return node
        child = _first_child(walker, el)
        while child is not None:
            if budget["left"] <= 0:
                truncated["hit"] = True
                break
            budget["left"] -= 1
            node.children.append(walk(child, depth + 1))
            child = _next_sibling(walker, child)
        return node

    raw_root = walk(root_el, 0)
    roots = _prune(raw_root)

    _counter["n"] += 1
    snap_id = f"snap-{_counter['n']}"
    nodes: list[Node] = []

    def assign(items: list[Node]) -> None:
        for node in items:
            nodes.append(node)
            assign(node.children)

    assign(roots)
    for index, node in enumerate(nodes, start=1):
        node.ref = f"e{index}"

    return Snapshot(app=name, scope=scope, snapshot_id=snap_id, roots=roots,
                    nodes=nodes, created=time.time(), truncated=truncated["hit"],
                    max_elements=max(1, int(max_elements)))


# --------------------------------------------------------------------------- #
# 渲染
# --------------------------------------------------------------------------- #


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")


def _line(node: Node, include_bounds: bool) -> str:
    parts = [node.ref, node.role]
    if node.name:
        parts.append(f'"{_escape(node.name)}"')
    if node.value is not None and node.value != node.name:
        parts.append(f'="{_escape(node.value)}"')
    flags = []
    if node.clickable:
        flags.append("click")
    if node.editable:
        flags.append("edit")
    if node.focused:
        flags.append("focus")
    if node.checked is not None:
        flags.append("on" if node.checked else "off")
    if node.selected:
        flags.append("selected")
    if node.expanded is not None:
        flags.append("expanded" if node.expanded else "collapsed")
    if not node.enabled:
        flags.append("disabled")
    if node.secure:
        flags.append("secure")
    if node.offscreen:
        flags.append("offscreen")
    if flags:
        parts.append("(" + ",".join(flags) + ")")
    if include_bounds and node.bounds:
        left, top, width, height = node.bounds
        parts.append(f"@{left},{top},{width}x{height}")
    return " ".join(parts)


def render(snapshot: Snapshot, include_bounds: bool = False) -> str:
    """把快照渲染成带 ref 的缩进文本。"""

    lines = [f"[{snapshot.snapshot_id}] {snapshot.app} ({snapshot.scope}, {len(snapshot.nodes)} 个元素)"]

    def emit(nodes: list[Node], depth: int) -> None:
        for node in nodes:
            lines.append("  " * depth + _line(node, include_bounds))
            emit(node.children, depth + 1)

    emit(snapshot.roots, 1)
    if snapshot.truncated:
        lines.append("… 元素数量达到上限，已截断；请用 find 缩小范围或提高 max_elements")
    return "\n".join(lines)


def render_matches(snapshot: Snapshot, matches: list[Node], include_bounds: bool = False) -> str:
    lines = [f"[{snapshot.snapshot_id}] {snapshot.app} 匹配 {len(matches)} 个元素"]
    lines.extend("  " + _line(node, include_bounds) for node in matches)
    return "\n".join(lines)


def find(snapshot: Snapshot, query: str | None = None,
         role: str | None = None, editable: bool | None = None,
         clickable: bool | None = None) -> list[Node]:
    """在快照内筛选元素。至少给出一个筛选条件。"""

    needle = (query or "").strip().lower()
    role_needle = (role or "").strip().lower()
    out: list[Node] = []
    for node in snapshot.nodes:
        if needle and needle not in node.name.lower() and needle not in (node.value or "").lower():
            continue
        if role_needle and role_needle not in node.role:
            continue
        if editable is not None and node.editable != editable:
            continue
        if clickable is not None and node.clickable != clickable:
            continue
        out.append(node)
    return out


# --------------------------------------------------------------------------- #
# ref 重新定位
# --------------------------------------------------------------------------- #


def _norm(text: str) -> str:
    return " ".join((text or "").split()).casefold()


def _nearest(candidates: list[Node], bounds: tuple[int, int, int, int] | None) -> Node | None:
    if not candidates:
        return None
    if bounds is None:
        return candidates[0]
    cx, cy = bounds[0] + bounds[2] // 2, bounds[1] + bounds[3] // 2
    best, best_d = None, None
    for node in candidates:
        if node.bounds is None:
            continue
        nx, ny = node.bounds[0] + node.bounds[2] // 2, node.bounds[1] + node.bounds[3] // 2
        dist = (nx - cx) ** 2 + (ny - cy) ** 2
        if best_d is None or dist < best_d:
            best, best_d = node, dist
    return best or candidates[0]


def _match(fresh: Snapshot, anchor: Anchor) -> Node | None:
    """按锚点在最新树里重新定位元素。

    规则（对齐参考项目的 ref 重定位语义）：
    - AutomationId（开发者分配的稳定 id）优先。
    - **有标题的元素以标题为准**：标题失配即 ``None``（调用方报 stale_ref），
      绝不退化为“占用旧位置的元素”——那正是列表重排后误点其它项的成因。
    - 只有无标题元素才走位置阶梯：同角色中最近且在 400px 内。
    """

    if anchor.automation_id:
        exact = [n for n in fresh.nodes if n.automation_id == anchor.automation_id and n.role == anchor.role]
        if exact:
            return _nearest(exact, anchor.bounds)
    name = _norm(anchor.name)
    if name:
        named = [n for n in fresh.nodes if n.role == anchor.role and _norm(n.name) == name]
        return _nearest(named, anchor.bounds) if named else None
    same_role = [n for n in fresh.nodes if n.role == anchor.role]
    candidate = _nearest(same_role, anchor.bounds)
    if candidate is not None and candidate.bounds and anchor.bounds:
        cx, cy = anchor.bounds[0] + anchor.bounds[2] // 2, anchor.bounds[1] + anchor.bounds[3] // 2
        nx, ny = candidate.bounds[0] + candidate.bounds[2] // 2, candidate.bounds[1] + candidate.bounds[3] // 2
        if (nx - cx) ** 2 + (ny - cy) ** 2 <= 400 ** 2:
            return candidate
    return None


def resolve(node: Node, app: str, scope: str, max_elements: int | None = None) -> tuple[Node, Snapshot]:
    """按 ``node`` 的锚点在最新树中重新定位，返回（新节点, 新快照）。

    ``max_elements`` 省略时沿用原快照的预算：ref 是在那个预算下分配的，
    用更小的预算重扫会让目标根本不在新树里（曾导致误匹配到别的控件）。
    """

    fresh = snapshot(app, scope, max_elements or 300)
    found = _match(fresh, node.anchor)
    if found is None:
        raise UIError(
            "stale_ref",
            f"ref {node.ref}（{node.role} {node.name!r}）在新树里已找不到，界面可能已变化；请重新 snapshot",
            {"app": app},
        )
    return found, fresh


# --------------------------------------------------------------------------- #
# 无障碍动作
# --------------------------------------------------------------------------- #


def press(node: Node, UIA) -> str | None:
    """用无障碍 pattern 激活元素（不移动鼠标）。返回使用的方式名或 None。"""

    if node.secure:
        raise UIError("secure_field", "目标是密码/安全字段，拒绝操作")
    el = node.handle
    invoke = _qi(_pattern(el, UIA.UIA_InvokePatternId), UIA.IUIAutomationInvokePattern)
    if invoke is not None and _safe(lambda: (invoke.Invoke() or True), False):
        return "invoke"
    toggle = _qi(_pattern(el, UIA.UIA_TogglePatternId), UIA.IUIAutomationTogglePattern)
    if toggle is not None and _safe(lambda: (toggle.Toggle() or True), False):
        return "toggle"
    select = _qi(_pattern(el, UIA.UIA_SelectionItemPatternId), UIA.IUIAutomationSelectionItemPattern)
    if select is not None and _safe(lambda: (select.Select() or True), False):
        return "select"
    expand = _qi(_pattern(el, UIA.UIA_ExpandCollapsePatternId), UIA.IUIAutomationExpandCollapsePattern)
    if expand is not None:
        state = _safe(lambda: int(expand.CurrentExpandCollapseState), None)
        if state == 0:
            if _safe(lambda: (expand.Expand() or True), False):
                return "expand"
        elif _safe(lambda: (expand.Collapse() or True), False):
            return "collapse"
    if (node.focusable or node.editable) and _safe(lambda: (el.SetFocus() or True), False):
        return "focus"
    return None


def set_value(node: Node, value: str, UIA) -> bool:
    """用 ValuePattern 直接写值（一步确定，无键盘模拟）。"""

    if node.secure:
        raise UIError("secure_field", "目标是密码/安全字段，拒绝写入")
    vp = _qi(_pattern(node.handle, UIA.UIA_ValuePatternId), UIA.IUIAutomationValuePattern)
    if vp is None or _safe(lambda: vp.CurrentIsReadOnly, True):
        return False
    vp.SetValue(value)
    return True


def scroll_into_view(node: Node, UIA) -> bool:
    """用 ScrollItemPattern 把元素滚入可视区（不移动鼠标）。"""

    sip = _qi(_pattern(node.handle, UIA.UIA_ScrollItemPatternId), UIA.IUIAutomationScrollItemPattern)
    if sip is None:
        return False
    sip.ScrollIntoView()
    return True


def focus(node: Node) -> bool:
    if node.secure:
        raise UIError("secure_field", "目标是密码/安全字段，拒绝聚焦")
    return bool(_safe(lambda: (node.handle.SetFocus() or True), False))


# --------------------------------------------------------------------------- #
# 合成输入（SendInput）
# --------------------------------------------------------------------------- #

KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1
INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000

_BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p),
    )


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_void_p),
    )


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = (("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD))


class _INPUTUNION(ctypes.Union):
    _fields_ = (("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT))


class _INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("u", _INPUTUNION))


def _send(events: list[_INPUT]) -> None:
    if not events:
        return
    array = (_INPUT * len(events))(*events)
    ctypes.windll.user32.SendInput(len(events), array, ctypes.sizeof(_INPUT))


def type_unicode(text: str) -> None:
    """以 KEYEVENTF_UNICODE 注入文本，与键盘布局无关。"""

    if not text:
        return
    events: list[_INPUT] = []
    for unit in memoryview(text.encode("utf-16-le")).cast("H"):
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            events.append(_INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=_KEYBDINPUT(0, unit, flags, 0, None))))
    _send(events)


_VK_MODS = {"ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12,
            "win": 0x5B, "cmd": 0x5B, "meta": 0x5B}
_VK_KEYS: dict[str, int] = {c: 0x41 + i for i, c in enumerate("abcdefghijklmnopqrstuvwxyz")}
_VK_KEYS.update({str(d): 0x30 + d for d in range(10)})
_VK_KEYS.update({
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "space": 0x20, "backspace": 0x08,
    "delete": 0x2E, "escape": 0x1B, "esc": 0x1B, "left": 0x25, "up": 0x26,
    "right": 0x27, "down": 0x28, "home": 0x24, "end": 0x23, "pageup": 0x21,
    "pagedown": 0x22,
})
_VK_KEYS.update({f"f{i}": 0x6F + i for i in range(1, 13)})


def _vk_event(vk: int, up: bool) -> _INPUT:
    return _INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=_KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, None)))


def press_chord(chord: str) -> None:
    """按下快捷键组合，如 ``ctrl+a``、``alt+f4``、``escape``。"""

    parts = [p.strip().lower() for p in (chord or "").split("+") if p.strip()]
    if not parts:
        raise UIError("invalid_arguments", f"空快捷键: {chord!r}")
    *mods, key = parts
    mvks = []
    for mod in mods:
        if mod not in _VK_MODS:
            raise UIError("invalid_arguments", f"未知修饰键 {mod!r}（支持 ctrl/shift/alt/win）")
        mvks.append(_VK_MODS[mod])
    if key in _VK_MODS:
        raise UIError("invalid_arguments", f"快捷键 {chord!r} 缺少非修饰键")
    if key not in _VK_KEYS:
        raise UIError("invalid_arguments", f"未知按键 {key!r}")
    kvk = _VK_KEYS[key]
    events = (
        [_vk_event(vk, False) for vk in mvks]
        + [_vk_event(kvk, False), _vk_event(kvk, True)]
        + [_vk_event(vk, True) for vk in reversed(mvks)]
    )
    _send(events)


def click_point(x: int, y: int, button: str = "left", count: int = 1) -> None:
    """在物理像素坐标处合成鼠标点击。"""

    if button not in _BUTTONS:
        raise UIError("invalid_arguments", f"未知鼠标键 {button!r}（left/right/middle）")
    if not 1 <= int(count) <= 3:
        raise UIError("invalid_arguments", "count 必须是 1-3")
    _ensure_dpi()
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    down, up = _BUTTONS[button]
    events: list[_INPUT] = []
    for _ in range(int(count)):
        events.append(_INPUT(INPUT_MOUSE, _INPUTUNION(mi=_MOUSEINPUT(0, 0, 0, down, 0, None))))
        events.append(_INPUT(INPUT_MOUSE, _INPUTUNION(mi=_MOUSEINPUT(0, 0, 0, up, 0, None))))
    _send(events)


def scroll_wheel(x: int, y: int, dx: int = 0, dy: int = 0) -> None:
    """在坐标处合成滚轮（dy>0 向下滚动，dx>0 向右滚动）。"""

    _ensure_dpi()
    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    events: list[_INPUT] = []
    if dy:
        delta = ctypes.c_ulong(-int(dy) * 120).value
        events.append(_INPUT(INPUT_MOUSE, _INPUTUNION(
            mi=_MOUSEINPUT(0, 0, delta, MOUSEEVENTF_WHEEL, 0, None))))
    if dx:
        delta = ctypes.c_ulong(int(dx) * 120).value
        events.append(_INPUT(INPUT_MOUSE, _INPUTUNION(
            mi=_MOUSEINPUT(0, 0, delta, MOUSEEVENTF_HWHEEL, 0, None))))
    _send(events)


def center_of(node: Node) -> tuple[int, int] | None:
    if not node.bounds:
        return None
    left, top, width, height = node.bounds
    return left + width // 2, top + height // 2
