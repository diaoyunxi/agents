"""基于 ripgrep 的文件内容搜索（无 rg 时自动回退到内置 Python 搜索）。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from common import read_text, relative, resolve_path, workspace_dir

NAME = "search_content"
DESCRIPTION = "基于 ripgrep 的文件内容搜索：正则匹配、glob 过滤、上下文行，支持 content/count/files 三种输出"
PARAMETERS = {
    "type": "object",
    "properties": {
        "pattern": {"type": "string", "description": "要搜索的正则表达式（ripgrep 语法）"},
        "path": {"type": "string", "description": "限定搜索的目录，默认整个工作区，用 . 表示"},
        "glob": {"type": "string", "description": "文件名过滤，例如 *.py 或 **/*.ts；省略则搜索全部文本文件"},
        "caseSensitive": {"type": "boolean", "description": "是否区分大小写，默认 false"},
        "contextBefore": {"type": "integer", "description": "每个匹配前显示的行数，默认 0"},
        "contextAfter": {"type": "integer", "description": "每个匹配后显示的行数，默认 0"},
        "contextAround": {"type": "integer", "description": "匹配前后各显示的行数（同时设置时覆盖前两项）"},
        "outputMode": {
            "type": "string",
            "description": "content=匹配行（默认）；count=每文件命中数；files_with_matches=仅文件路径",
            "enum": ["content", "count", "files_with_matches"],
        },
        "ignore_globs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "要忽略的通配符模式（匹配路径任意一级），例如 [\"*.log\", \"dist\"]",
        },
        "maxResults": {"type": "integer", "description": "最多返回的结果条数，默认 100"},
    },
    "required": ["pattern"],
}

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".idea", ".vscode", "dist", "build"}
TEXT_EXTS = {
    ".py", ".md", ".txt", ".json", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".yml",
    ".yaml", ".toml", ".ini", ".cfg", ".sh", ".ps1", ".bat", ".c", ".h", ".cpp", ".java",
    ".go", ".rs", ".rb", ".php", ".sql", ".xml", ".vue", ".gitignore", ".env",
}
MAX_FILE_BYTES = 2 * 1024 * 1024


# --------------------------------------------------------------------------- #
# ripgrep 路径
# --------------------------------------------------------------------------- #


def _rg_binary() -> str | None:
    return shutil.which("rg") or shutil.which("ripgrep")


def _run_ripgrep(pattern: str, base: Path, glob: str | None, ignore_case: bool,
                 before: int, after: int, mode: str, max_results: int) -> dict:
    cmd = ["--no-messages", "--no-heading", "-n", "--color", "never"]
    if ignore_case:
        cmd.append("-i")
    if glob:
        cmd += ["--glob", glob]
    if mode == "files_with_matches":
        cmd.append("--files-with-matches")
    elif mode == "count":
        cmd.append("--count")
    else:
        cmd.append("--max-columns", "400")
    if before:
        cmd += ["--before-context", str(before)]
    if after:
        cmd += ["--after-context", str(after)]
    cmd += ["-e", pattern, str(base)]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=60)
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "ripgrep 搜索超时（>60s），请缩小范围"}
    except OSError as exc:
        return {"ok": False, "output": f"ripgrep 执行失败: {exc}"}

    if proc.returncode not in (0, 1):
        err = (proc.stderr or "").strip()[:300]
        return {"ok": False, "output": f"ripgrep 报错（exit {proc.returncode}）: {err}"}

    lines = [line for line in (proc.stdout or "").splitlines() if line.strip()]
    if not lines:
        return {"output": f"未找到匹配 `{pattern}` 的内容"}
    shown = lines[:max_results]
    note = f"\n... 结果已达上限 {max_results}，请缩小范围或调整关键词" if len(lines) > max_results else ""
    return {"output": "\n".join(shown) + note}


# --------------------------------------------------------------------------- #
# Python 回退（尊重 .gitignore）
# --------------------------------------------------------------------------- #


def _load_gitignore(folder: Path) -> list[str]:
    patterns: list[str] = []
    gi = folder / ".gitignore"
    if gi.is_file():
        try:
            for raw in read_text(gi, limit=50000).splitlines():
                line = raw.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
        except OSError:
            pass
    return patterns


def _gitignored(rel: str, is_dir: bool, patterns: list[str]) -> bool:
    import fnmatch

    ignored = False
    for pat in patterns:
        neg = pat.startswith("!")
        if neg:
            pat = pat[1:]
        dir_only = pat.endswith("/")
        if dir_only:
            pat = pat[:-1]
            if not is_dir and "/" not in pat.rstrip("/"):
                continue
        target = rel.replace("\\", "/").strip("/")
        stem = target.rsplit("/", 1)[-1]
        if fnmatch.fnmatch(target, pat) or fnmatch.fnmatch(stem, pat) or fnmatch.fnmatch(target, pat + "/*"):
            ignored = not neg
            if not neg:
                return True
    return ignored


def _walk(base: Path, ignore_globs: list[str]):
    """生成 (abs_path, rel_path)，跳过 SKIP_DIRS、.gitignore 命中与 ignore_globs。"""

    import fnmatch

    stack = [(base, [])]
    while stack:
        folder, inherited = stack.pop()
        patterns = inherited + _load_gitignore(folder)
        try:
            entries = sorted(folder.iterdir())
        except OSError:
            continue
        for item in entries:
            rel = str(item.relative_to(base)).replace("\\", "/")
            is_dir = item.is_dir()
            if is_dir and item.name in SKIP_DIRS:
                continue
            if _gitignored(rel, is_dir, patterns):
                continue
            if ignore_globs and (any(fnmatch.fnmatch(part, g) for g in ignore_globs for part in Path(rel).parts)
                                 or any(fnmatch.fnmatch(rel, g) for g in ignore_globs)):
                continue
            if is_dir:
                stack.append((item, patterns))
            else:
                yield item, rel


def _run_python(pattern: str, base: Path, glob: str | None, ignore_case: bool,
                before: int, after: int, mode: str, max_results: int,
                ignore_globs: list[str]) -> dict:
    try:
        flags = re.IGNORECASE if ignore_case else 0
        matcher = re.compile(pattern, flags)
    except re.error as exc:
        return {"ok": False, "output": f"正则表达式无效: {exc}"}

    def _glob_ok(name: str, rel: str) -> bool:
        if not glob:
            return True
        import fnmatch

        return fnmatch.fnmatch(name, glob) or fnmatch.fnmatch(rel, glob) or fnmatch.fnmatch(rel, "**/" + glob)

    out_lines: list[str] = []
    count_lines: list[str] = []
    total = 0
    for item, rel in _walk(base, ignore_globs):
        if not _glob_ok(item.name, rel):
            continue
        if glob is None and item.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            if item.stat().st_size > MAX_FILE_BYTES:
                continue
            text = read_text(item)
        except OSError:
            continue
        lines = text.splitlines()
        hit_idx = [i for i, line in enumerate(lines) if matcher.search(line)]
        if not hit_idx:
            continue
        total += len(hit_idx)
        if mode == "files_with_matches":
            out_lines.append(f"  {rel}")
        elif mode == "count":
            count_lines.append(f"  {rel}:{len(hit_idx)}")
        else:
            shown: set[int] = set()
            for i in hit_idx:
                lo, hi = max(0, i - before), min(len(lines), i + after + 1)
                for j in range(lo, hi):
                    if j in shown:
                        continue
                    shown.add(j)
                    mark = ":" if j in hit_idx else "-"
                    out_lines.append(f"  {rel}{mark}{j + 1}{mark} {lines[j].strip()[:300]}")
        if total >= max_results and mode != "files_with_matches":
            break
        if len(out_lines) >= max_results:
            break

    if mode == "count":
        if not count_lines:
            return {"output": f"未找到匹配 `{pattern}` 的内容"}
        return {"output": "\n".join(count_lines[:max_results])}
    if not out_lines:
        return {"output": f"未找到匹配 `{pattern}` 的内容"}
    note = f"\n... 结果已达上限 {max_results}，请缩小范围或调整关键词" if total >= max_results else ""
    return {"output": "\n".join(out_lines[:max_results]) + note}


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #


def run(pattern: str, path: str = ".", glob: str | None = None, caseSensitive: bool = False,
        contextBefore: int = 0, contextAfter: int = 0, contextAround: int = 0,
        outputMode: str = "content", ignore_globs: list[str] | None = None,
        maxResults: int = 100) -> dict:
    pattern = (pattern or "").strip()
    if not pattern:
        return {"ok": False, "output": "pattern 不能为空"}

    base: Path = resolve_path(path) if path not in ("", None) else workspace_dir().resolve()
    if not base.exists():
        return {"ok": False, "output": f"目录不存在: {relative(base)}"}
    if not base.is_dir():
        return {"ok": False, "output": f"不是目录: {relative(base)}"}

    mode = (outputMode or "content").strip()
    if mode not in ("content", "count", "files_with_matches"):
        return {"ok": False, "output": f"未知 outputMode: {mode}（可选 content/count/files_with_matches）"}

    ignore_case = not caseSensitive
    before = int(contextAround or contextBefore or 0)
    after = int(contextAround or contextAfter or 0)
    before, after = max(0, min(before, 20)), max(0, min(after, 20))
    max_results = max(1, min(int(maxResults or 100), 500))
    globs = [str(g) for g in (ignore_globs or []) if str(g).strip()]

    rg = _rg_binary()
    if rg:
        result = _run_ripgrep(pattern, base, glob, ignore_case, before, after, mode, max_results)
        if result.get("ok", True):
            header = f"[ripgrep] 模式: {pattern} | 范围: {relative(base) or '.'}"
            body = result.get("output", "")
            return {"output": f"{header}\n{body}"}
        # rg 执行失败（如参数不支持）时回退到内置搜索
    return _run_python(pattern, base, glob, ignore_case, before, after, mode, max_results, globs)


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
