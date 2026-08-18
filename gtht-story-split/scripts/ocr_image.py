#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ocr_image.py — 跨平台可插拔 OCR CLI（swift → pytesseract → paddleocr → 提示人工）

用法:
  python3 ocr_image.py <image> [<image> ...] [--json] [--backend 名] [--list-backends]

行为:
  - 后端按 config.ocr_backend_order 探测（默认 ["swift","pytesseract","paddleocr"]；
    GTHT_OCR_BACKEND 逗号分隔可覆盖，--backend 单次覆盖）。
  - 默认：逐图调用所选后端，每张图输出识别文本；多图时块间用 `===== <文件名> =====` 分隔。
  - --json：输出 JSON 数组 [{file, backend, lines:[{text,midY,minX,height,confidence}]}]。
  - **无可用后端时明确提示人工**，绝不静默丢 OCR（exit 4）。
  - 非法路径 / 无法读取 / OCR 失败：exit 3。

行结构（与 swift/Vision 一致）：
  [{text, midY, minX, height, confidence}]   # 坐标归一化，midY 原点在左下（上大下小）
"""
import sys
import json
import shutil
import subprocess
from pathlib import Path

import config

SWIFT = Path(__file__).parent / "ocr.swift"


# ---------------------------------------------------------------------------
# 后端探测
# ---------------------------------------------------------------------------
def _has_swift() -> bool:
    return shutil.which("swift") is not None and SWIFT.exists()


def _has_pytesseract() -> bool:
    try:
        import pytesseract
        pytesseract.get_tesseract_version()  # 触发 which 校验
        return True
    except Exception:
        return False


def _has_paddleocr() -> bool:
    try:
        import paddleocr  # noqa
        return True
    except Exception:
        return False


DETECTORS = {
    "swift": _has_swift,
    "pytesseract": _has_pytesseract,
    "paddleocr": _has_paddleocr,
}


def detect_backends(order: list) -> list:
    """按给定顺序返回可用后端列表。"""
    return [b for b in order if b in DETECTORS and DETECTORS[b]()]


def resolve_backend(order: list) -> str:
    """返回第一个可用后端；无则 None。"""
    avail = detect_backends(order)
    return avail[0] if avail else None


# ---------------------------------------------------------------------------
# swift（macOS Vision，最快路径）
# ---------------------------------------------------------------------------
def _ocr_swift(img: Path, as_json: bool):
    cmd = ["swift", str(SWIFT), str(img)]
    if as_json:
        cmd.append("--json")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"swift OCR 失败: {r.stderr.strip()}")
    if as_json:
        try:
            return json.loads(r.stdout or "[]")
        except Exception:
            return []
    return [{"text": ln} for ln in r.stdout.splitlines() if ln.strip()]


# ---------------------------------------------------------------------------
# pytesseract（跨平台，需系统 tesseract + chi_sim）
# ---------------------------------------------------------------------------
def _ocr_pytesseract(img: Path):
    from PIL import Image
    import pytesseract

    pil = Image.open(img)
    w, h = pil.size
    data = pytesseract.image_to_data(pil, lang="chi_sim+eng",
                                     output_type=pytesseract.Output.DICT)
    # 按 (block, par, line) 分组 → 视觉行
    groups = {}
    order = []
    for i, txt in enumerate(data["text"] or []):
        txt = (txt or "").strip()
        if not txt:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append({
            "text": txt,
            "left": int(data["left"][i]), "top": int(data["top"][i]),
            "width": int(data["width"][i]), "height": int(data["height"][i]),
            "conf": float(data["conf"][i]),
        })
    lines = []
    for key in order:
        words = groups[key]
        words.sort(key=lambda x: x["left"])
        min_left = min(x["left"] for x in words)
        max_right = max(x["left"] + x["width"] for x in words)
        min_top = min(x["top"] for x in words)
        max_bottom = max(x["top"] + x["height"] for x in words)
        lines.append({
            "text": " ".join(x["text"] for x in words),
            "midY": round(1 - ((min_top + max_bottom) / 2.0) / h, 6),
            "minX": round(min_left / w, 6),
            "height": round((max_bottom - min_top) / h, 6),
            "confidence": round(sum(x["conf"] for x in words) / len(words) / 100.0, 6),
        })
    return lines


# ---------------------------------------------------------------------------
# paddleocr（重依赖，跨平台兜底）
# ---------------------------------------------------------------------------
_paddle_engine = None


def _ocr_paddleocr(img: Path):
    global _paddle_engine
    from PIL import Image
    if _paddle_engine is None:
        from paddleocr import PaddleOCR
        _paddle_engine = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    pil = Image.open(img)
    w, h = pil.size
    result = _paddle_engine.ocr(str(img), cls=True) or []
    lines = []
    for page in result:
        for box, (text, conf) in (page or []):
            if not text or not box:
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            lines.append({
                "text": text,
                "midY": round(1 - (min(ys) + max(ys)) / 2.0 / h, 6),
                "minX": round(min(xs) / w, 6),
                "height": round((max(ys) - min(ys)) / h, 6),
                "confidence": round(float(conf), 6),
            })
    return lines


BACKENDS = {
    "swift": _ocr_swift,
    "pytesseract": _ocr_pytesseract,
    "paddleocr": _ocr_paddleocr,
}


# ---------------------------------------------------------------------------
# 对外
# ---------------------------------------------------------------------------
def ocr_one(img: str, backend: str, as_json: bool) -> dict:
    p = Path(img)
    if not p.exists():
        print(f"❌ 文件不存在: {img}", file=sys.stderr)
        sys.exit(3)
    if not p.is_file():
        print(f"❌ 不是文件: {img}", file=sys.stderr)
        sys.exit(3)

    fn = BACKENDS[backend]
    if backend == "swift":
        lines = fn(p, as_json)
        if as_json:
            return {"file": p.name, "backend": backend, "lines": lines}
        return {"file": p.name, "backend": backend, "text": "\n".join(x["text"] for x in lines)}
    # 非 swift 后端：内部统一 lines 结构
    lines = fn(p)
    if as_json:
        return {"file": p.name, "backend": backend, "lines": lines}
    return {"file": p.name, "backend": backend, "text": "\n".join(x["text"] for x in lines)}


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]

    if "--list-backends" in args:
        order = config.get_ocr_backend_order()
        print("检测结果:")
        for b in order:
            ok = b in DETECTORS and DETECTORS[b]()
            print(f"  {'✅' if ok else '❌'} {b}")
        print(f"顺序: {order}")
        sys.exit(0)

    backend = None
    if "--backend" in args:
        i = args.index("--backend")
        backend = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]

    if not args:
        print("用法: python3 ocr_image.py <image> [<image> ...] [--json] [--backend 名] [--list-backends]",
              file=sys.stderr)
        sys.exit(1)

    order = config.get_ocr_backend_order()
    if backend:
        if backend not in BACKENDS:
            print(f"❌ 未知后端: {backend}（支持 {list(BACKENDS)}）", file=sys.stderr)
            sys.exit(3)
        if not DETECTORS[backend]():
            print(f"❌ 后端不可用: {backend}", file=sys.stderr)
            sys.exit(4)
        order = [backend]

    chosen = resolve_backend(order)
    if not chosen:
        print("\n".join([
            "❌ 无可用 OCR 后端（按顺序探测失败: " + ",".join(order) + "）。",
            "   绝不静默丢 OCR——请人工读取图片文字，或安装任一后端后重试：",
            "   • swift（macOS，最快）：安装 Xcode CommandLineTools",
            "   • pytesseract：pip install pytesseract && brew install tesseract tesseract-lang",
            "   • paddleocr：pip install paddleocr",
            "   强制指定：GTHT_OCR_BACKEND=pytesseract 或 --backend pytesseract",
        ]), file=sys.stderr)
        sys.exit(4)

    if as_json:
        out = [ocr_one(a, chosen, True) for a in args]
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for i, a in enumerate(args):
            d = ocr_one(a, chosen, False)
            if len(args) > 1:
                print(f"===== {d['file']}（{d['backend']}） =====")
            print(d["text"], end="" if d["text"].endswith("\n") else "\n")


if __name__ == "__main__":
    main()
