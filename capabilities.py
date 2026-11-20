"""硬件 / 环境能力探测。

由 Python 在运行时自动探测本机「拥有什么」，为工具的「按硬件自动启用/停用」
提供事实依据。工具在 tools.py 里声明 `REQUIRES = [...]`（能力标签），加载器
据此决定该工具默认可用与否；用户仍可用 config.json 的 tool_toggles 显式覆盖。

能力标签（capability tag）约定：
- 无标签：        总是可用（仅依赖 Python 标准库，如 httpx/requests 视为已就绪）
- "pkg:NAME"      需要可导入的 Python 包 NAME
- "cli:NAME"      需要 PATH 中可执行的命令行工具 NAME
- "win" / "posix" / "macos"      需要对应操作系统
- "gpu:nvidia"    需要 NVIDIA GPU（nvidia-smi 可用）
- "cpu_count:N"   需要至少 N 个逻辑 CPU
- "mem_gb:N"      需要至少 N GB 内存（尽力而为，无法判定时不据此关停工具）

设计原则：
- 只做「硬件/已装依赖」层面的门控，不把「网络是否通」当作硬件；联网工具在离线时
  会在调用期给出明确错误，而非被静默关停。
- 结果带缓存，避免反复探测；提供 refresh() 供热重载。
"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
from typing import Any

# 结果缓存：进程内探测一次即可（可用 refresh 重置）
_CACHE: dict[str, Any] | None = None


# --------------------------------------------------------------------------- #
# 单项探测
# --------------------------------------------------------------------------- #

def _pkg_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False
    except Exception:  # noqa: BLE001  个别包 find_spec 会触发异常
        return False


def _cli_available(name: str) -> bool:
    return shutil.which(name) is not None


def _os_name() -> str:
    if platform.system() == "Windows":
        return "win"
    if platform.system() == "Darwin":
        return "macos"
    return "posix"


def _gpu_nvidia() -> bool:
    if _cli_available("nvidia-smi"):
        return True
    try:
        import torch  # type: ignore
        return bool(getattr(torch.cuda, "is_available", lambda: False)())
    except Exception:  # noqa: BLE001
        return False


def _total_mem_gb() -> float | None:
    """尽力获取物理内存总量（GB）；无法判定时返回 None（不据此关停工具）。"""
    if platform.system() == "Windows":
        try:
            import ctypes

            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return stat.ullTotalPhys / (1024 ** 3)
        except Exception:  # noqa: BLE001
            return None
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / (1024 * 1024)
    except OSError:
        pass
    return None


def _cpu_count() -> int:
    return int(os.cpu_count() or 1)


# --------------------------------------------------------------------------- #
# 对外接口
# --------------------------------------------------------------------------- #

def has(tag: str | None) -> bool:
    """判断单个能力标签是否满足。

    - None / 空串 / "always"：总是满足。
    - 未识别的标签：保守返回 True（不因未知标签误关停工具），并打印一次提示。
    """
    if not tag or tag in ("always", "*"):
        return True
    tag = str(tag).strip()

    if tag in ("win", "posix", "macos"):
        return _os_name() == tag

    if tag.startswith("pkg:"):
        return _pkg_available(tag[4:].strip())

    if tag.startswith("cli:"):
        return _cli_available(tag[4:].strip())

    if tag == "gpu:nvidia":
        return _gpu_nvidia()

    if tag.startswith("cpu_count:"):
        try:
            return _cpu_count() >= int(tag.split(":", 1)[1])
        except ValueError:
            return True

    if tag.startswith("mem_gb:"):
        try:
            need = float(tag.split(":", 1)[1])
        except ValueError:
            return True
        total = _total_mem_gb()
        if total is None:
            return True  # 无法判定时不关停
        return total >= need

    return True


def requires_satisfied(requires: list[str] | None) -> tuple[bool, list[str], str]:
    """返回 (是否全部满足, 缺失的能力标签列表, 人类可读原因)。"""
    missing = [tag for tag in (requires or []) if not has(tag)]
    if not missing:
        return True, [], "能力齐备"
    return False, missing, "缺少能力: " + ", ".join(missing)


def refresh() -> dict[str, Any]:
    """重置缓存并返回一份能力快照（summary）。"""
    global _CACHE
    _CACHE = None
    return summary()


def summary() -> dict[str, Any]:
    """探测并缓存一份本机能力快照，便于工具/界面/日志展示。"""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    probe_packages = [
        "httpx", "requests", "PIL", "numpy", "pandas", "qrcode",
        "docx", "pypdf", "pdfplumber", "openpyxl", "playwright",
        "docker", "feedparser", "sympy", "matplotlib", "sklearn",
        "chromadb", "faiss", "qdrant_client", "torch",
    ]
    probe_clis = ["git", "node", "npx", "npm", "docker", "ffmpeg", "rg", "pip", "nvidia-smi"]

    _CACHE = {
        "platform": _os_name(),
        "python": sys.version.split()[0],
        "cpu_count": _cpu_count(),
        "mem_gb": _total_mem_gb(),
        "gpu_nvidia": _gpu_nvidia(),
        "packages": {name: _pkg_available(name) for name in probe_packages},
        "clis": {name: _cli_available(name) for name in probe_clis},
    }
    return _CACHE


def describe() -> str:
    """人类可读的能力清单（用于日志/界面/工具健康检查）。"""
    snap = summary()
    lines = [f"平台: {snap['platform']} | Python {snap['python']} | CPU {snap['cpu_count']} 核"
             f" | GPU(nvidia): {'是' if snap['gpu_nvidia'] else '否'}"]
    if snap.get("mem_gb") is not None:
        lines.append(f"内存: 约 {snap['mem_gb']:.1f} GB")
    pk = snap["packages"]
    lines.append("已装包: " + (", ".join(k for k, v in pk.items() if v) or "（无）"))
    missing_pk = [k for k, v in pk.items() if not v]
    if missing_pk:
        lines.append("未装包: " + ", ".join(missing_pk))
    cl = snap["clis"]
    lines.append("可用 CLI: " + (", ".join(k for k, v in cl.items() if v) or "（无）"))
    missing_cl = [k for k, v in cl.items() if not v]
    if missing_cl:
        lines.append("缺失 CLI: " + ", ".join(missing_cl))
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover - 手动自检
    print(describe())
