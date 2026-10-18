"""Stamping: watermarks, page numbers, headers/footers and Bates numbering."""
import io
from datetime import date

import pymupdf as fitz
from PIL import Image

from .common import ToolContext, ToolError, ToolOutput, font_for, hex_to_rgb, open_pdf, parse_pages, save_pdf, text_length

POSITIONS = {
    "top-left", "top-center", "top-right",
    "bottom-left", "bottom-center", "bottom-right",
}


def _prepare(doc: fitz.Document, pages: list[int]) -> None:
    """Normalise rotation so we can stamp in visible coordinates without extra maths."""
    for i in pages:
        if doc[i].rotation:
            doc[i].remove_rotation()


def _place(page: fitz.Page, text: str, position: str, size: float, margin: float, color, font: str = "helv") -> None:
    if position not in POSITIONS:
        raise ToolError(f"Unknown position '{position}'.")
    fontname, fontfile = font_for(text, font)
    r = page.rect
    lines = text.split("\n")
    widest = max(text_length(line, fontname, fontfile, size) for line in lines)
    vert, horiz = position.split("-")
    if horiz == "left":
        x = margin
    elif horiz == "right":
        x = r.width - margin - widest
    else:
        x = (r.width - widest) / 2
    block_h = size * 1.2 * len(lines)
    y = margin + size if vert == "top" else r.height - margin - block_h + size
    page.insert_text((x, y), text, fontsize=size, fontname=fontname, fontfile=fontfile, color=color)


def _fmt(template: str, n: int, total: int, filename: str) -> str:
    return (
        template.replace("{n}", str(n))
        .replace("{page}", str(n))
        .replace("{total}", str(total))
        .replace("{date}", date.today().isoformat())
        .replace("{filename}", filename)
    )


def watermark(
    ctx: ToolContext,
    text: str = "",
    image_file_id: str | None = None,
    pages: str = "all",
    opacity: float = 0.25,
    rotation: float = 45,
    size: float = 60,
    color: str = "#ff0000",
    layout: str = "center",  # center or tile
    scale: float = 0.5,  # image width as a fraction of page width
    behind: bool = False,
) -> ToolOutput:
    img_path = ctx.assets.get("image_file_id")
    if not text and not img_path:
        raise ToolError("Enter watermark text or choose an image.")
    opacity = max(0.02, min(1.0, float(opacity)))
    doc = open_pdf(ctx.inputs[0])
    targets = parse_pages(pages, doc.page_count)
    _prepare(doc, targets)

    img_bytes = None
    if img_path:
        with Image.open(img_path) as im:
            im = im.convert("RGBA")
            alpha = im.getchannel("A").point(lambda a: int(a * opacity))
            im.putalpha(alpha)
            if rotation:
                im = im.rotate(float(rotation), expand=True, resample=Image.BICUBIC)
            buf = io.BytesIO()
            im.save(buf, "PNG")
            img_bytes = buf.getvalue()
            img_ratio = im.height / im.width

    rgb = hex_to_rgb(color, (1, 0, 0))
    for n, i in enumerate(targets):
        page = doc[i]
        r = page.rect
        centers = [fitz.Point(r.width / 2, r.height / 2)]
        if layout == "tile":
            step_x, step_y = r.width / 3, r.height / 4
            centers = [fitz.Point(step_x * (cx + 0.5), step_y * (cy + 0.5)) for cx in range(3) for cy in range(4)]
        for c in centers:
            if img_bytes:
                w = r.width * float(scale) * (0.4 if layout == "tile" else 1)
                h = w * img_ratio
                page.insert_image(fitz.Rect(c.x - w / 2, c.y - h / 2, c.x + w / 2, c.y + h / 2), stream=img_bytes, overlay=not behind)
            else:
                fs = float(size) * (0.45 if layout == "tile" else 1)
                fontname, fontfile = font_for(text, "helv", bold=True)
                tw = text_length(text, fontname, fontfile, fs)
                # Rotate around the centre point using a morph matrix.
                start = fitz.Point(c.x - tw / 2, c.y + fs / 3)
                page.insert_text(
                    start,
                    text,
                    fontsize=fs,
                    fontname=fontname,
                    fontfile=fontfile,
                    color=rgb,
                    fill_opacity=opacity,
                    stroke_opacity=opacity,
                    morph=(c, fitz.Matrix(-float(rotation))),
                    overlay=not behind,
                )
        ctx.progress(int((n + 1) * 95 / len(targets)), "Stamping")
    name = f"{ctx.stem}-watermarked.pdf"
    return ToolOutput(files=[(save_pdf(doc, ctx.out(name)), name)])


def page_numbers(
    ctx: ToolContext,
    template: str = "Page {n} of {total}",
    position: str = "bottom-center",
    start: int = 1,
    pages: str = "all",
    size: float = 10,
    margin: float = 24,
    color: str = "#000000",
    font: str = "helv",
) -> ToolOutput:
    doc = open_pdf(ctx.inputs[0])
    targets = parse_pages(pages, doc.page_count)
    _prepare(doc, targets)
    total = len(targets) + int(start) - 1
    for k, i in enumerate(targets):
        _place(doc[i], _fmt(template, int(start) + k, total, ctx.input_names[0]), position, float(size), float(margin), hex_to_rgb(color), font)
    name = f"{ctx.stem}-numbered.pdf"
    return ToolOutput(files=[(save_pdf(doc, ctx.out(name)), name)])


def header_footer(
    ctx: ToolContext,
    header_left: str = "",
    header_center: str = "",
    header_right: str = "",
    footer_left: str = "",
    footer_center: str = "",
    footer_right: str = "",
    pages: str = "all",
    size: float = 9,
    margin: float = 20,
    color: str = "#333333",
    font: str = "helv",
) -> ToolOutput:
    slots = {
        "top-left": header_left, "top-center": header_center, "top-right": header_right,
        "bottom-left": footer_left, "bottom-center": footer_center, "bottom-right": footer_right,
    }
    if not any(v.strip() for v in slots.values()):
        raise ToolError("Enter text for at least one header or footer position.")
    doc = open_pdf(ctx.inputs[0])
    targets = parse_pages(pages, doc.page_count)
    _prepare(doc, targets)
    total = doc.page_count
    for i in targets:
        for pos, tmpl in slots.items():
            if tmpl.strip():
                _place(doc[i], _fmt(tmpl, i + 1, total, ctx.input_names[0]), pos, float(size), float(margin), hex_to_rgb(color), font)
    name = f"{ctx.stem}-header-footer.pdf"
    return ToolOutput(files=[(save_pdf(doc, ctx.out(name)), name)])


def bates(
    ctx: ToolContext,
    prefix: str = "",
    suffix: str = "",
    start: int = 1,
    digits: int = 6,
    position: str = "bottom-right",
    size: float = 9,
    margin: float = 18,
    color: str = "#000000",
) -> ToolOutput:
    """Bates numbering runs continuously across all input files (in the given order)."""
    counter = int(start)
    digits = max(1, min(int(digits), 12))
    out = ToolOutput()
    for idx, path in enumerate(ctx.inputs):
        doc = open_pdf(path)
        first = counter
        _prepare(doc, list(range(doc.page_count)))
        for page in doc:
            label = f"{prefix}{str(counter).zfill(digits)}{suffix}"
            _place(page, label, position, float(size), float(margin), hex_to_rgb(color))
            counter += 1
        stem = ctx.input_names[idx].rsplit(".", 1)[0]
        name = f"{stem}_{prefix}{str(first).zfill(digits)}-{prefix}{str(counter - 1).zfill(digits)}{suffix}.pdf"
        out.files.append((save_pdf(doc, ctx.out(name)), name))
        ctx.progress(int((idx + 1) * 95 / len(ctx.inputs)), "Numbering")
    out.data = {"first": int(start), "last": counter - 1}
    return out
