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
        except Exception as exc:
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
            registry[name] = {
                "name": getattr(module, "NAME", name),
                "description": (getattr(module, "DESCRIPTION", "") or "").strip(),
                "parameters": getattr(module, "PARAMETERS", {"type": "object", "properties": {}}),
                "doc": md.strip(),
                "run": run,
                "dangerous": bool(getattr(module, "DANGEROUS", False)),
                "path": str(folder),
            }
        except Exception as exc:
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


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": item["name"],
            "description": item["description"],
            "parameters": item["parameters"],
            "dangerous": item["dangerous"],
            "doc": item["doc"],
        }
        for item in sorted(registry().values(), key=lambda x: x["name"])
    ]


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
    """把每个工具的 tools.md 拼成 system 提示词中的「可用工具」章节。"""

    items = registry().values()
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

    run: Callable[..., Any] = item["run"]
    kwargs = arguments or {}
    try:
        signature = inspect.signature(run)
        if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()):
            allowed = set(signature.parameters)
            kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        result = run(**kwargs)
        if inspect.isawaitable(result):
            result = await result
    except ToolError as exc:
        return {"ok": False, "output": f"工具 `{name}` 执行失败: {exc}"}
    except TypeError as exc:
        return {"ok": False, "output": f"工具 `{name}` 参数错误: {exc}"}
    except Exception as exc:
        return {"ok": False, "output": f"工具 `{name}` 抛出异常: {exc}\n{traceback.format_exc(limit=3)}"}

    if isinstance(result, str):
        return {"ok": True, "output": result}
    if isinstance(result, dict):
        out = dict(result)
        out.setdefault("ok", True)
        out.setdefault("output", "")
        return out
    return {"ok": True, "output": json_dumps(result)}


def json_dumps(value: Any) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(value)


def run_sync(coro):  # pragma: no cover - 便捷函数
    return asyncio.run(coro)
