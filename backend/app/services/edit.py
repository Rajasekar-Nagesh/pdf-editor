"""Content editing: text replace/add, images, links, bookmarks, attachments, flatten, metadata."""
import io
from pathlib import Path

import pymupdf as fitz
from PIL import Image

from .common import (
    ToolContext,
    ToolError,
    ToolOutput,
    font_for,
    hex_to_rgb,
    open_pdf,
    require_page,
    save_pdf,
    text_length,
    visible_point,
    visible_to_unrotated,
)


def _done(ctx: ToolContext, doc: fitz.Document) -> ToolOutput:
    name = f"{ctx.stem}.pdf"
    return ToolOutput(files=[(save_pdf(doc, ctx.out(name)), name)])


# ---------------------------------------------------------------- text


def replace_text(
    ctx: ToolContext,
    page: int,
    bbox: list[float],
    new_text: str,
    font: str = "",
    size: float = 11,
    color: str = "#000000",
    bold: bool = False,
    italic: bool = False,
    origin: list[float] | None = None,
) -> ToolOutput:
    """Remove the text inside `bbox` (visible coords) and write `new_text` in a matching font.

    `origin` is the original span baseline origin in unrotated coordinates (from the spans inspector).
    """
    doc = open_pdf(ctx.inputs[0])
    p = require_page(doc, int(page))
    area = visible_to_unrotated(p, bbox)
    # Shrink slightly so we do not clip neighbouring lines that touch the box.
    clip = fitz.Rect(area.x0 + 0.3, area.y0 + area.height * 0.15, area.x1 - 0.3, area.y1 - area.height * 0.15)
    p.add_redact_annot(clip)
    p.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
    if new_text:
        size = float(size) or 11
        fontname, fontfile = font_for(new_text, font, bold, italic)
        if origin:
            point = fitz.Point(origin)
        else:
            point = fitz.Point(area.x0, area.y1 - size * 0.22)
        # Shrink the font if the new text would run far past the original box.
        width = text_length(new_text, fontname, fontfile, size)
        if area.width > 0 and width > area.width * 1.6:
            size = max(4.0, size * area.width * 1.6 / width)
        p.insert_text(
            point,
            new_text,
            fontsize=size,
            fontname=fontname,
            fontfile=fontfile,
            color=hex_to_rgb(color),
        )
    return _done(ctx, doc)


def add_text(
    ctx: ToolContext,
    page: int,
    x: float,
    y: float,
    text: str,
    size: float = 12,
    font: str = "helv",
    color: str = "#000000",
    bold: bool = False,
    italic: bool = False,
) -> ToolOutput:
    """Add new text with its top-left corner at (x, y) in visible coordinates. Supports multiple lines."""
    if not text:
        raise ToolError("Type some text to add.")
    doc = open_pdf(ctx.inputs[0])
    p = require_page(doc, int(page))
    size = float(size)
    fontname, fontfile = font_for(text, font, bold, italic)
    origin = visible_point(p, float(x), float(y) + size * 0.8)
    p.insert_text(
        origin, text, fontsize=size, fontname=fontname, fontfile=fontfile, color=hex_to_rgb(color), rotate=p.rotation
    )
    return _done(ctx, doc)


# ---------------------------------------------------------------- images


def _image_bytes(path: Path) -> bytes:
    """Normalise any supported image to PNG/JPEG bytes PyMuPDF can embed."""
    with Image.open(path) as img:
        img.load()
        if img.format in ("PNG", "JPEG"):
            return path.read_bytes()
        buf = io.BytesIO()
        img.convert("RGBA").save(buf, "PNG")
        return buf.getvalue()


def add_image(ctx: ToolContext, page: int, rect: list[float], image_file_id: str, keep_proportion: bool = True) -> ToolOutput:
    img = ctx.assets.get("image_file_id")
    if not img:
        raise ToolError("Choose an image to add.")
    doc = open_pdf(ctx.inputs[0])
    p = require_page(doc, int(page))
    p.insert_image(visible_to_unrotated(p, rect), stream=_image_bytes(img), keep_proportion=keep_proportion)
    return _done(ctx, doc)


def _check_xref(p: fitz.Page, xref: int) -> fitz.Rect:
    for info in p.get_image_info(xrefs=True):
        if info.get("xref") == xref:
            return fitz.Rect(info["bbox"])
    raise ToolError("That image was not found on this page.")


def replace_image(ctx: ToolContext, page: int, xref: int, image_file_id: str) -> ToolOutput:
    img = ctx.assets.get("image_file_id")
    if not img:
        raise ToolError("Choose a replacement image.")
    doc = open_pdf(ctx.inputs[0])
    p = require_page(doc, int(page))
    _check_xref(p, int(xref))
    p.replace_image(int(xref), stream=_image_bytes(img))
    return _done(ctx, doc)


def move_image(ctx: ToolContext, page: int, xref: int, rect: list[float]) -> ToolOutput:
    """Move and/or resize an image to a new rect (visible coords)."""
    doc = open_pdf(ctx.inputs[0])
    p = require_page(doc, int(page))
    _check_xref(p, int(xref))
    data = doc.extract_image(int(xref))
    smask = data.get("smask")
    pix = fitz.Pixmap(doc, int(xref))
    if smask:
        pix = fitz.Pixmap(pix, fitz.Pixmap(doc, smask))
    stream = pix.tobytes("png")
    p.delete_image(int(xref))
    p.insert_image(visible_to_unrotated(p, rect), stream=stream, keep_proportion=False)
    return _done(ctx, doc)


def crop_image(ctx: ToolContext, page: int, xref: int, left: float = 0, top: float = 0, right: float = 0, bottom: float = 0) -> ToolOutput:
    """Crop an image by fractions (0-0.95) of its width/height from each side; shrinks its box accordingly."""
    fr = [max(0.0, min(0.95, float(v))) for v in (left, top, right, bottom)]
    if fr[0] + fr[2] >= 0.95 or fr[1] + fr[3] >= 0.95:
        raise ToolError("The crop removes almost the entire image.")
    doc = open_pdf(ctx.inputs[0])
    p = require_page(doc, int(page))
    box = _check_xref(p, int(xref))
    pix = fitz.Pixmap(doc, int(xref))
    if pix.alpha == 0 and doc.extract_image(int(xref)).get("smask"):
        pix = fitz.Pixmap(pix, fitz.Pixmap(doc, doc.extract_image(int(xref))["smask"]))
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    w, h = img.size
    cropped = img.crop((int(w * fr[0]), int(h * fr[1]), int(w * (1 - fr[2])), int(h * (1 - fr[3]))))
    buf = io.BytesIO()
    cropped.save(buf, "PNG")
    new_box = fitz.Rect(
        box.x0 + box.width * fr[0], box.y0 + box.height * fr[1], box.x1 - box.width * fr[2], box.y1 - box.height * fr[3]
    )
    p.delete_image(int(xref))
    p.insert_image(new_box, stream=buf.getvalue(), keep_proportion=False)
    return _done(ctx, doc)


def delete_image(ctx: ToolContext, page: int, xref: int) -> ToolOutput:
    doc = open_pdf(ctx.inputs[0])
    p = require_page(doc, int(page))
    box = _check_xref(p, int(xref))
    # Redacting the image area removes it from this page only (other pages may share the image).
    p.add_redact_annot(box)
    p.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE, graphics=fitz.PDF_REDACT_LINE_ART_NONE, text=fitz.PDF_REDACT_TEXT_NONE)
    return _done(ctx, doc)


# ---------------------------------------------------------------- links, bookmarks, attachments


def set_link(
    ctx: ToolContext,
    page: int,
    rect: list[float] | None = None,
    uri: str = "",
    target_page: int | None = None,
    index: int | None = None,
    delete: bool = False,
) -> ToolOutput:
    """Create a link, or edit/delete the existing link at `index` on the page."""
    doc = open_pdf(ctx.inputs[0])
    p = require_page(doc, int(page))
    existing = p.get_links()
    if index is not None:
        if not 0 <= int(index) < len(existing):
            raise ToolError("That link no longer exists.")
        old = existing[int(index)]
        p.delete_link(old)
        if delete:
            return _done(ctx, doc)
        if rect is None:
            rect = list(old["from"])
            area = fitz.Rect(rect)
        else:
            area = visible_to_unrotated(p, rect)
    else:
        if rect is None:
            raise ToolError("Draw a box where the link should go.")
        area = visible_to_unrotated(p, rect)
    if uri:
        if not uri.lower().startswith(("http://", "https://", "mailto:", "tel:")):
            uri = "https://" + uri
        p.insert_link({"kind": fitz.LINK_URI, "from": area, "uri": uri})
    elif target_page:
        tp = int(target_page) - 1
        if not 0 <= tp < doc.page_count:
            raise ToolError("The target page does not exist.")
        p.insert_link({"kind": fitz.LINK_GOTO, "from": area, "page": tp, "to": fitz.Point(0, 0)})
    else:
        raise ToolError("Enter a web address or a page number for the link.")
    return _done(ctx, doc)


def set_bookmarks(ctx: ToolContext, items: list[dict]) -> ToolOutput:
    """Replace the outline with `items` = [{level, title, page}] (1-based page)."""
    doc = open_pdf(ctx.inputs[0])
    toc = []
    prev_level = 0
    for it in items:
        level = max(1, int(it.get("level", 1)))
        level = min(level, prev_level + 1)  # levels may only increase by one
        page = max(1, min(int(it.get("page", 1)), doc.page_count))
        title = str(it.get("title", "")).strip() or f"Page {page}"
        toc.append([level, title[:300], page])
        prev_level = level
    doc.set_toc(toc)
    return _done(ctx, doc)


def add_attachment(ctx: ToolContext, attachment_file_id: str, attachment_name: str = "", description: str = "") -> ToolOutput:
    path = ctx.assets.get("attachment_file_id")
    if not path:
        raise ToolError("Choose a file to attach.")
    doc = open_pdf(ctx.inputs[0])
    name = attachment_name or path.name
    base, n = name, 1
    while name in doc.embfile_names():
        n += 1
        name = f"{Path(base).stem}-{n}{Path(base).suffix}"
    doc.embfile_add(name, path.read_bytes(), filename=name, desc=description)
    return _done(ctx, doc)


def remove_attachment(ctx: ToolContext, name: str) -> ToolOutput:
    doc = open_pdf(ctx.inputs[0])
    if name not in doc.embfile_names():
        raise ToolError("Attachment not found.")
    doc.embfile_del(name)
    return _done(ctx, doc)


# ---------------------------------------------------------------- flatten & metadata


def flatten(ctx: ToolContext, annotations: bool = True, forms: bool = True) -> ToolOutput:
    doc = open_pdf(ctx.inputs[0])
    doc.bake(annots=bool(annotations), widgets=bool(forms))
    return _done(ctx, doc)


def set_metadata(
    ctx: ToolContext, title: str = "", author: str = "", subject: str = "", keywords: str = "", creator: str = ""
) -> ToolOutput:
    doc = open_pdf(ctx.inputs[0])
    meta = dict(doc.metadata or {})
    meta.update({"title": title, "author": author, "subject": subject, "keywords": keywords, "creator": creator})
    meta["producer"] = "PDFDesk"
    doc.set_metadata({k: v for k, v in meta.items() if k in ("title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate")})
    return _done(ctx, doc)
