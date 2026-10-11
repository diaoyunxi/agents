"""运行时公共设施：工作区沙箱路径解析、文件变更记录。"""

from __future__ import annotations

import difflib
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from config import workspace_dir

# --------------------------------------------------------------------------- #
# 路径沙箱
# --------------------------------------------------------------------------- #


class SandboxError(Exception):
    """访问了工作区之外的路径。"""


def resolve_path(path: str | Path, must_exist: bool = False) -> Path:
    """把相对路径解析为工作区内的绝对路径，越界时抛出 SandboxError。"""

    root = workspace_dir().resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = Path(str(candidate)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SandboxError(
            f"路径 `{candidate}` 超出工作区 `{root}` 范围，已拒绝。"
        ) from exc
    if must_exist and not candidate.exists():
        raise SandboxError(f"路径不存在: {candidate}")
    return candidate


def relative(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(workspace_dir().resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def read_text(path: Path, limit: int | None = None) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover
        text = data.decode("utf-8", errors="replace")
    if limit and len(text) > limit:
        text = text[:limit] + f"\n... [已截断，共 {len(text)} 字符]"
    return text


# --------------------------------------------------------------------------- #
# 文件变更收集
# --------------------------------------------------------------------------- #


@dataclass
class FileChange:
    path: str
    action: str  # create | modify | delete
    language: str = ""
    additions: int = 0
    deletions: int = 0
    diff: str = ""
    before: str = ""
    after: str = ""
    time: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("before", "after"):
            if len(data[key]) > 20000:
                data[key] = data[key][:20000] + "\n... [截断]"
        return data


_current_changes: ContextVar[list[FileChange] | None] = ContextVar("current_changes", default=None)
_local = threading.local()


class ChangeCollector:
    """一次对话过程中收集所有工具产生的文件变更，供右侧侧边栏展示。"""

    def __init__(self, base_dir: str | None = None) -> None:
        self.base_dir = base_dir
        self.changes: list[FileChange] = []
        self._token = None

    def __enter__(self) -> "ChangeCollector":
        self._token = _current_changes.set(self.changes)
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._token is not None:
            _current_changes.reset(self._token)

    def snapshot(self) -> list[dict[str, Any]]:
        return [c.to_dict() for c in self.changes]


def _make_diff(path: str, before: str, after: str, lang: str = "") -> tuple[str, int, int]:
    diff_lines = list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
            n=3,
        )
    )
    additions = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    deletions = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    return "\n".join(diff_lines[:800]), additions, deletions


LANG_EXT = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "tsx", ".jsx": "jsx",
    ".json": "json", ".md": "markdown", ".html": "html", ".css": "css", ".yml": "yaml",
    ".yaml": "yaml", ".toml": "toml", ".sh": "bash", ".ps1": "powershell", ".txt": "text",
    ".go": "go", ".rs": "rust", ".java": "java", ".c": "c", ".cpp": "cpp", ".cs": "csharp",
    ".sql": "sql", ".xml": "xml", ".ini": "ini", ".vue": "vue", ".rb": "ruby", ".php": "php",
}


def language_of(path: str | Path) -> str:
    return LANG_EXT.get(Path(path).suffix.lower(), "")


def record_change(path: str | Path, action: str, before: str = "", after: str = "") -> FileChange | None:
    """记录一次文件变更（由工具调用）。没有活动采集器时静默忽略。"""

    bucket = _current_changes.get()
    if bucket is None:
        return None
    rel = relative(Path(path)) if Path(path).is_absolute() else str(path).replace("\\", "/")
    lang = language_of(rel)
    diff, add, dele = "", 0, 0
    if action == "delete":
        diff, add, dele = _make_diff(rel, before, "")
    elif before or after:
        diff, add, dele = _make_diff(rel, before, after, lang)
    change = FileChange(
        path=rel, action=action, language=lang, additions=add, deletions=dele,
        diff=diff, before=before, after=after,
    )
    bucket.append(change)
    return change


@contextmanager
def collecting(base_dir: str | None = None) -> Iterator[ChangeCollector]:
    with ChangeCollector(base_dir) as collector:
        yield collector
