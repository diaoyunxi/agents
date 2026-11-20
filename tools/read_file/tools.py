"""读取工作区内文件：文本带行号返回，图片以 base64 图像内容返回（供多模态模型使用）。"""

from __future__ import annotations

import base64
import io
from pathlib import Path

from common import SandboxError, read_text, relative, resolve_path

NAME = "read_file"
DESCRIPTION = "读取工作区中某个文件的文本内容（带行号）；图片文件会以图像形式返回给多模态模型"
PARAMETERS = {
    "type": "object",
    "properties": {
        "filePath": {"type": "string", "description": "相对工作区的文件路径，例如 src/app.py"},
        "offset": {"type": "integer", "description": "起始行号（从 1 开始），省略时从头开始"},
        "limit": {"type": "integer", "description": "最多显示的行数，默认 2000"},
        "max_chars": {"type": "integer", "description": "文本最多返回的字符数，默认 20000"},
    },
    "required": ["filePath"],
}

IMAGE_EXTS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}
IMAGE_MAGIC = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"BM": "image/bmp",
}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_DIM = 1568  # 超过则等比缩小，控制多模态 token 消耗


def _sniff_image(data: bytes, suffix: str) -> str | None:
    if suffix in IMAGE_EXTS:
        return IMAGE_EXTS[suffix]
    for magic, mime in IMAGE_MAGIC.items():
        if data.startswith(magic):
            return mime
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _encode_image(data: bytes, mime: str, rel: str) -> dict:
    """尽量用 Pillow 归一化（缩小 + 统一格式）；没有 Pillow 时原样 base64。"""

    width = height = 0
    out_fmt = "png"
    try:
        from PIL import Image  # type: ignore

        with Image.open(io.BytesIO(data)) as im:
            width, height = im.size
            if max(width, height) > MAX_IMAGE_DIM:
                scale = MAX_IMAGE_DIM / max(width, height)
                im = im.resize((max(1, int(width * scale)), max(1, int(height * scale))),
                               Image.LANCZOS)
                width, height = im.size
            has_alpha = im.mode in ("RGBA", "LA", "P")
            if mime == "image/gif":
                out_fmt, save_mime = "gif", "image/gif"
            elif has_alpha or mime == "image/png":
                out_fmt, save_mime = "png", "image/png"
            else:
                out_fmt, save_mime = "jpeg", "image/jpeg"
            buf = io.BytesIO()
            if im.mode == "P" and out_fmt != "gif":
                im = im.convert("RGBA" if out_fmt == "png" else "RGB")
            im.save(buf, format=out_fmt.upper())
            data, mime = buf.getvalue(), save_mime
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": f"图片解码失败: {rel}（{exc}）"}

    size_kb = len(data) / 1024
    dim = f"{width}x{height}" if width and height else "未知尺寸"
    return {
        "ok": True,
        "output": f"[图片] {rel} | {mime} | {dim} | {size_kb:.1f} KB —— 已作为图像内容提供给多模态模型",
        "images": [{"media_type": mime, "data": base64.b64encode(data).decode("ascii")}],
    }


def run(filePath: str, offset: int | None = None, limit: int = 2000, max_chars: int = 20000) -> dict:
    try:
        target: Path = resolve_path(filePath, must_exist=True)
    except SandboxError as exc:
        return {"ok": False, "output": str(exc)}

    if target.is_dir():
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lines = [f"[目录] {relative(target)}"] + [f"  {e.name}{'/' if e.is_dir() else ''}" for e in entries[:500]]
        return {"output": "\n".join(lines)}

    rel = relative(target)
    try:
        raw = target.read_bytes()
    except OSError as exc:
        return {"ok": False, "output": f"读取失败: {rel}（{exc}）"}

    mime = _sniff_image(raw, target.suffix.lower())
    if mime:
        if len(raw) > MAX_IMAGE_BYTES:
            return {"ok": False, "output": f"图片过大（>{MAX_IMAGE_BYTES // 1024 // 1024}MB）: {rel}，请先压缩"}
        return _encode_image(raw, mime, rel)

    text = read_text(target, limit=max_chars)
    total_lines = text.count("\n") + 1
    numbered_all = text.splitlines()
    begin = max(1, int(offset or 1))
    finish = min(total_lines, begin - 1 + max(1, int(limit or 2000)))
    slice_ = numbered_all[begin - 1 : finish]
    body = "\n".join(f"{begin + i:>6} | {line}" for i, line in enumerate(slice_))
    header = f"文件: {rel} | 总行数: {total_lines} | 显示范围: {begin}-{finish}"
    return {"output": f"{header}\n{body}"}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS"]
