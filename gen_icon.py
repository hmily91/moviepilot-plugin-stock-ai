# -*- coding: utf-8 -*-
"""生成插件图标 icons/stockai.png（128x128，深蓝渐变背景 + 绿色上升折线）。仅使用标准库。"""
import zlib
import struct
import os


def make_png(path: str, size: int = 128) -> None:
    w = h = size
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # PNG 每行前缀：filter type 0
        for x in range(w):
            t = y / h
            # 深蓝渐变背景
            r = int(30 + 25 * t)
            g = int(58 + 35 * t)
            b = int(138 + 50 * t)
            # 绿色上升折线（粗度 ±4 像素）
            line_y = int(h - (x / w) * (h * 0.82) - h * 0.10)
            if abs(y - line_y) <= 4:
                r, g, b = 34, 197, 94
            raw += bytes((r, g, b))

    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit RGB
    idat = zlib.compress(bytes(raw), 9)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "stockai.png")
    make_png(out)
    print("icon OK:", os.path.getsize(out), "bytes ->", out)
