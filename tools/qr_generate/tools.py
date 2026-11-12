"""生成二维码图片（存到工作区），或解析图片中的二维码。

生成需要 qrcode 库（本机已装则自动启用）；解析需要 pyzbar，未装时优雅降级。
"""

from __future__ import annotations

import base64
from pathlib import Path

from common import relative, resolve_path, workspace_dir

NAME = "qr_generate"
DANGEROUS = False
DESCRIPTION = "生成二维码并保存为 PNG（需提供 qrcode 库），也可解析图片中的二维码（需 pyzbar）"
PARAMETERS = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "description": "generate=生成；read=解析图片中的二维码", "enum": ["generate", "read"]},
        "data": {"type": "string", "description": "generate 用：要编码的内容（URL、文本等）"},
        "imagePath": {"type": "string", "description": "read 用：含二维码的图片路径（相对工作区）"},
        "outputPath": {"type": "string", "description": "generate 用：输出文件路径（相对工作区），默认 qr_<时间戳>.png"},
        "size": {"type": "integer", "description": "生成时边长像素，默认 300"},
    },
    "required": ["action"],
}

REQUIRES = ["pkg:qrcode"]  # 生成能力依赖 qrcode；read 走 pyzbar（缺失时按次降级）


def run(action: str, data: str = "", imagePath: str = "", outputPath: str = "", size: int = 300) -> dict:
    act = (action or "").strip().lower()

    if act == "generate":
        return _generate(data, outputPath, size)
    if act == "read":
        return _read(imagePath)
    return {"ok": False, "output": "action 必须是 generate 或 read"}


def _generate(data: str, outputPath: str, size: int) -> dict:
    data = (data or "").strip()
    if not data:
        return {"ok": False, "output": "generate 需要 data"}
    try:
        import qrcode
    except ImportError:
        return {"ok": False, "output": "未安装 qrcode，无法生成二维码。请 `pip install qrcode`。"}

    size = max(100, min(int(size or 300), 2000))
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    out_rel = (outputPath or f"qr_{int(__import__('time').time())}.png")
    try:
        target: Path = resolve_path(out_rel)
        target.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": str(exc)}
    img.save(target, format="PNG")
    return {"output": f"已生成二维码 {relative(target)}（{size}x{size}），内容: {data[:80]}"}


def _read(imagePath: str) -> dict:
    if not imagePath:
        return {"ok": False, "output": "read 需要 imagePath"}
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
    except ImportError:
        return {"ok": False, "output": "未安装 pyzbar，无法解析二维码。请 `pip install pyzbar`（Linux 还需 libzbar）。"}
    try:
        target: Path = resolve_path(imagePath, must_exist=True)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "output": str(exc)}
    results = pyzbar_decode(target.read_bytes())
    if not results:
        return {"output": f"未在 {relative(target)} 中识别到二维码"}
    texts = [r.data.decode("utf-8", errors="replace") for r in results]
    return {"output": "识别到 " + str(len(texts)) + " 个二维码：\n" + "\n".join(texts)}


__all__ = ["run", "NAME", "DESCRIPTION", "PARAMETERS", "REQUIRES"]
