"""工具集加载器。

约定：`tools/<工具名>/` 为一个工具目录，内部至少包含
- `tools.py`  ：工具实现，需提供 `run(**kwargs)` 函数，以及 NAME/DESCRIPTION/PARAMETERS
- `tools.md`  ：自然语言说明（参数、作用等），会被原样嵌入 system 提示词
目录内可放任意其它文件（辅助模块、示例数据等），同目录的其它 .py 文件也会被自动导入，
便于把复杂工具拆分成多个模块。
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from config import tools_dir

_REGISTRY: dict[str, dict[str, Any]] = {}
_BUILTIN_MODULES = {"tools.py", "__init__.py", "loader.py"}


class ToolError(Exception):
    """工具执行错误（会作为工具结果返回给模型）。"""


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"无法加载模块: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _import_siblings(folder: Path, tool_name: str) -> None:
    """把工具目录下的其它 .py 文件先导入一遍，便于它们作为共享模块使用。"""

    pkg_name = f"agents_tools.{tool_name}"
    if pkg_name not in sys.modules:
        pkg = type(sys)("agents_tools")
        pkg.__path__ = [str(tools_dir())]  # type: ignore[attr-defined]
        sys.modules["agents_tools"] = pkg
    for py in sorted(folder.glob("*.py")):
        if py.name in _BUILTIN_MODULES:
            continue
        mod_name = f"{pkg_name}.{py.stem}"
        if mod_name in sys.modules:
            continue
        try:
            _load_module(py, mod_name)
        except Exception as exc:  # noqa: BLE001
            print(f"[tools] 加载辅助模块失败 {py}: {exc}")


def discover() -> dict[str, dict[str, Any]]:
    """扫描 tools/ 目录，重新构建工具注册表。"""

    root = tools_dir()
    root.mkdir(parents=True, exist_ok=True)
    registry: dict[str, dict[str, Any]] = {}

    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if folder.name.startswith((".", "_")):
            continue
        impl = folder / "tools.py"
        doc = folder / "tools.md"
        if not doc.exists():
            for alt in folder.glob("*.md"):
                doc = alt
                break
        if not impl.exists() or not doc.exists():
            continue
        name = folder.name
        try:
            _import_siblings(folder, name)
            module = _load_module(impl, f"agents_tools.{name}.tools")
            run = getattr(module, "run", None)
            if not callable(run):
                print(f"[tools] 跳过 {name}: 未找到 run() 函数")
                continue
            md = doc.read_text(encoding="utf-8")
            # 按硬件/环境自动启用的能力门控：tools.py 可声明 REQUIRES = ["pkg:xxx", "cli:yyy", ...]
            from capabilities import requires_satisfied

            ok_cap, missing, reason = requires_satisfied(getattr(module, "REQUIRES", None))
            registry[name] = {
                "name": getattr(module, "NAME", name),
                "description": (getattr(module, "DESCRIPTION", "") or "").strip(),
                "parameters": getattr(module, "PARAMETERS", {"type": "object", "properties": {}}),
                "doc": md.strip(),
                "run": run,
                "dangerous": bool(getattr(module, "DANGEROUS", False)),
                "path": str(folder),
                "requires": list(getattr(module, "REQUIRES", []) or []),
                "capability_ok": ok_cap,
                "capability_missing": missing,
                "capability_reason": reason,
            }
            if not ok_cap:
                print(f"[tools] {name}: 因缺少能力而默认停用（{reason}），"
                      f"可在设置页 tool_toggles 显式启用")
        except Exception as exc:  # noqa: BLE001
            print(f"[tools] 加载 {name} 失败: {exc}")
            traceback.print_exc()
    return registry


def registry() -> dict[str, dict[str, Any]]:
    if not _REGISTRY:
        _REGISTRY.update(discover())
    return _REGISTRY


def refresh() -> dict[str, dict[str, Any]]:
    _REGISTRY.clear()
    return registry()


def is_tool_enabled(name: str) -> bool:
    """检查工具是否被允许。

    优先级：
      1. config.json 的 tool_toggles[name] 显式 true/false —— 用户手动覆盖，最高优先；
      2. 未显式设置时，按「按硬件自动启用」：工具声明的 REQUIRES 能力不满足则自动停用，
         满足则默认启用。
    """
    import config
    toggles = config.get("tool_toggles", {}) or {}
    if name in toggles:
        return toggles.get(name, True) is not False
    item = registry().get(name)
    if item is None:
        return True
    # 未声明 REQUIRES 的工具默认可用；声明了则按能力自动启用/停用
    return bool(item.get("capability_ok", True))


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": item["name"],
            "description": item["description"],
            "parameters": item["parameters"],
            "dangerous": item["dangerous"],
            "enabled": is_tool_enabled(item["name"]),
            "requires": item.get("requires", []),
            "capability_ok": item.get("capability_ok", True),
            "capability_missing": item.get("capability_missing", []),
            "doc": item["doc"],
        }
        for item in sorted(registry().values(), key=lambda x: x["name"])
    ]


def list_enabled_tools() -> list[dict[str, Any]]:
    """只返回当前启用的工具（用于 function calling schema 和提示词）。"""
    return [t for t in list_tools() if t.get("enabled", True)]


def get_custom_config() -> dict[str, Any]:
    """读取 config.json 中的 custom 段，工具可据此自定义行为。"""
    import config
    return config.get("custom", {}) or {}


def get_tool(name: str) -> dict[str, Any] | None:
    return registry().get(name)


def _json_schema_to_text(schema: dict[str, Any], indent: int = 0) -> str:
    pad = "  " * indent
    props = schema.get("properties", {}) or {}
    required = set(schema.get("required", []) or [])
    if not props:
        return f"{pad}(无参数)"
    lines = []
    for key, spec in props.items():
        desc = spec.get("description", "")
        typ = spec.get("type", "string")
        if typ == "array" and isinstance(spec.get("items"), dict):
            typ = f"array<{spec['items'].get('type', 'string')}>"
        flag = "必填" if key in required else "可选"
        enum = spec.get("enum")
        if enum:
            desc = f"{desc} 可选值: {', '.join(str(e) for e in enum)}"
        lines.append(f"{pad}- {key} ({typ}, {flag}): {desc}".rstrip())
    return "\n".join(lines)


def build_prompt_section() -> str:
    """把每个工具的 tools.md 拼成 system 提示词中的「可用工具」章节（自动跳过被停用的工具）。"""

    items = [item for item in registry().values() if is_tool_enabled(item["name"])]
    if not items:
        return ""
    chunks = []
    for item in sorted(items, key=lambda x: x["name"]):
        header = f"### 工具 `{item['name']}`"
        if item["description"]:
            header += f" —— {item['description']}"
        schema = _json_schema_to_text(item.get("parameters", {}), indent=0)
        body = item["doc"].strip()
        # 若 tools.md 未描述参数，则自动附上签名参数列表
        if "参数" not in body and "Arguments" not in body:
            body = f"{body}\n\n参数:\n{schema}".strip()
        chunks.append(f"{header}\n{body}")
    return "\n\n".join(chunks)


async def call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """执行工具，返回统一的 {ok, output, changes} 结果。"""

    item = get_tool(name)
    if item is None:
        return {"ok": False, "output": f"错误：不存在名为 `{name}` 的工具。可用工具：{', '.join(registry().keys())}"}

    # 按硬件自动停用且用户未显式覆盖：给出清晰的安装/启用指引（含一键安装提示）
    if not item.get("capability_ok", True) and not is_tool_enabled(name):
        import config
        toggles = config.get("tool_toggles", {}) or {}
        if name not in toggles:
            missing = list(item.get("capability_missing", []) or ["未知能力"])
            pkg_tags = [m.split(":", 1)[1].strip() for m in missing
                        if isinstance(m, str) and m.startswith("pkg:")]
            other = [m for m in missing if not (isinstance(m, str) and m.startswith("pkg:"))]
            hint = [f"工具 `{name}` 因本机缺少能力（{', '.join(missing)}）而自动停用。"]
            if pkg_tags:
                hint.append(f"可自动补齐：调用 `pip_install` 安装 {pkg_tags}，"
                            f"或调用 `fix_capabilities`（批量补齐并刷新缓存）后重试。")
            if other:
                hint.append(f"其余能力（{', '.join(other)}）需手动安装对应 CLI/驱动。")
            hint.append("也可到设置页 tool_toggles 手动启用。")
            return {"ok": False, "output": "\n".join(hint)}

    run: Callable[..., Any] = item["run"]
    kwargs, missing, ignored = _prepare_kwargs(name, run, item.get("parameters") or {}, arguments or {})

    # 缺必填参数：不执行，返回对模型友好的结构化提示（列出工具、缺哪个、该传什么类型），
    # 让模型可据此自纠，而不是拿到裸 Python TypeError 后无从下手。
    if missing:
        schema_props = (item.get("parameters") or {}).get("properties", {}) or {}
        detail = "；".join(
            "{0}（{1}）".format(m, (schema_props.get(m, {}) or {}).get("type", "必填"))
            for m in missing
        )
        note = (
            f"工具 `{name}` 缺少必填参数: {detail}。请补齐这些参数后重新调用，"
            f"不要省略必填项。"
        )
        if ignored:
            note += f" 另外，你传了未知参数 {ignored}，已忽略（正确参数见该工具说明）。"
        return {"ok": False, "output": note}

    try:
        result = run(**kwargs)
        if inspect.isawaitable(result):
            result = await result
    except ToolError as exc:
        return {"ok": False, "output": f"工具 `{name}` 执行失败: {exc}"}
    except TypeError as exc:
        return {"ok": False, "output": f"工具 `{name}` 参数错误: {exc}（请核对参数名与取值是否匹配 schema）"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": f"工具 `{name}` 抛出异常: {exc}\n{traceback.format_exc(limit=3)}"}

    # 有参数被忽略时附一条提醒，避免模型误以为「多传的参数生效了」
    result_str = result if isinstance(result, str) else json_dumps(result)
    if ignored:
        note = f"注意: 已忽略未知参数 {ignored}（正确参数名见该工具说明）。"
        result_str = f"{result_str}\n{note}".strip()
    if isinstance(result, dict):
        out = dict(result)
        out.setdefault("ok", True)
        out["output"] = result_str
        return out
    return {"ok": True, "output": result_str}


def _prepare_kwargs(name: str, run: Callable[..., Any], schema: dict, arguments: dict) -> tuple:
    """净化参数并校验必填项。

    返回 (kwargs, missing, ignored)：
      - kwargs   可直接 run(**kwargs) 的参数字典；
      - missing  schema 标记 required 但本次未传的参数名列表；
      - ignored  传了但 run() 签名不认识、被丢弃的参数名列表。

    处理两类调用期隐患：
      1. 正文 JSON 解析失败时上游塞入的 ``{"__raw__": "..."}`` 标记——它不是真实参数，
         直接取出并丢弃，避免把整串原始 JSON 当成参数；
      2. 所有内置工具都是固定命名参数（无 **kwargs），LLM 多传/漏传都会在这里被拦截，
         而非落到裸 Python TypeError。
    """
    has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD
                    for p in inspect.signature(run).parameters.values())
    sig_params = set(inspect.signature(run).parameters)

    kwargs = dict(arguments or {})
    kwargs.pop("__raw__", None)          # 正文 JSON 解析失败的兜底标记，不是真实参数

    if not has_varkw:
        ignored = sorted(k for k in kwargs if k not in sig_params)
        kwargs = {k: v for k, v in kwargs.items() if k in sig_params}
    else:
        ignored = []

    # required 里只要本次没给有效值（缺键 / None / 空串 / 空列表）就视为缺失，便于自纠
    required = sorted({r for r in (schema.get("required") or [])
                       if kwargs.get(r) in (None, "", [])})
    return kwargs, required, ignored


def json_dumps(value: Any) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(value)


def run_sync(coro):  # pragma: no cover - 便捷函数
    return asyncio.run(coro)
