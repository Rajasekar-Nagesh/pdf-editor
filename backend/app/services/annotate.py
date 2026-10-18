"""Annotations: highlight, underline, strikethrough, sticky notes, ink, shapes, text boxes."""
import pymupdf as fitz

from .common import ToolContext, ToolError, ToolOutput, hex_to_rgb, open_pdf, require_page, save_pdf, visible_point, visible_to_unrotated

TEXT_MARKUP = {"highlight", "underline", "strikeout", "squiggly"}


def _quads_in(page: fitz.Page, area: fitz.Rect) -> list[fitz.Quad]:
    """Quads of the words that intersect `area`, merged per line for tidy markup."""
    lines: dict[tuple, fitz.Rect] = {}
    for x0, y0, x1, y1, _w, block, line, _wn in page.get_text("words"):
        r = fitz.Rect(x0, y0, x1, y1)
        if r.intersects(area):
            key = (block, line)
            lines[key] = lines[key] | r if key in lines else r
    return [r.quad for r in lines.values()]


def _apply_one(doc: fitz.Document, a: dict, author: str) -> None:
    kind = a.get("type")
    page = require_page(doc, int(a.get("page", 0)))
    color = hex_to_rgb(a.get("color"), (1, 0.85, 0) if kind == "highlight" else (1, 0, 0))
    opacity = float(a.get("opacity", 1))
    annot = None

    if kind in TEXT_MARKUP:
        area = visible_to_unrotated(page, a["rect"])
        quads = _quads_in(page, area) or [area.quad]
        annot = {
            "highlight": page.add_highlight_annot,
            "underline": page.add_underline_annot,
            "strikeout": page.add_strikeout_annot,
            "squiggly": page.add_squiggly_annot,
        }[kind](quads)
        annot.set_colors(stroke=color)
    elif kind == "note":
        pt = visible_point(page, *a["point"])
        annot = page.add_text_annot(pt, a.get("text", ""), icon="Note")
        annot.set_colors(stroke=color)
    elif kind == "ink":
        strokes = [
            [tuple(visible_point(page, float(x), float(y))) for x, y in stroke]
            for stroke in a.get("strokes", [])
            if len(stroke) > 1
        ]
        if not strokes:
            raise ToolError("The drawing is empty.")
        annot = page.add_ink_annot(strokes)
        annot.set_colors(stroke=color)
        annot.set_border(width=float(a.get("width", 2)))
    elif kind in ("rect", "circle"):
        area = visible_to_unrotated(page, a["rect"])
        annot = page.add_rect_annot(area) if kind == "rect" else page.add_circle_annot(area)
        fill = hex_to_rgb(a["fill"]) if a.get("fill") else None
        annot.set_colors(stroke=color, fill=fill)
        annot.set_border(width=float(a.get("width", 2)))
    elif kind in ("line", "arrow"):
        p1 = visible_point(page, *a["from"])
        p2 = visible_point(page, *a["to"])
        annot = page.add_line_annot(p1, p2)
        annot.set_colors(stroke=color)
        annot.set_border(width=float(a.get("width", 2)))
        if kind == "arrow":
            annot.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_OPEN_ARROW)
    elif kind == "textbox":
        area = visible_to_unrotated(page, a["rect"])
        annot = page.add_freetext_annot(
            area,
            a.get("text", ""),
            fontsize=float(a.get("size", 12)),
            text_color=color,
            fill_color=hex_to_rgb(a["fill"]) if a.get("fill") else None,
            rotate=page.rotation,
        )
    else:
        raise ToolError(f"Unknown annotation type '{kind}'.")

    annot.set_opacity(max(0.05, min(1.0, opacity)))
    info = annot.info
    info["title"] = author or "PDFDesk"
    if a.get("comment") and kind != "note":
        info["content"] = a["comment"]
    annot.set_info(info)
    annot.update()


def annotate(ctx: ToolContext, annotations: list[dict], author: str = "") -> ToolOutput:
    if not annotations:
        raise ToolError("Add at least one annotation first.")
    doc = open_pdf(ctx.inputs[0])
    for a in annotations:
        _apply_one(doc, a, author)
    name = f"{ctx.stem}.pdf"
    return ToolOutput(files=[(save_pdf(doc, ctx.out(name)), name)])


def delete_annotation(ctx: ToolContext, page: int, xref: int) -> ToolOutput:
    doc = open_pdf(ctx.inputs[0])
    p = require_page(doc, int(page))
    for annot in p.annots():
        if annot.xref == int(xref):
            p.delete_annot(annot)
            break
    else:
        raise ToolError("That annotation was not found.")
    name = f"{ctx.stem}.pdf"
    return ToolOutput(files=[(save_pdf(doc, ctx.out(name)), name)])
