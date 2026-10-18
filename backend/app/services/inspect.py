"""Read-only inspection of a PDF used by the editor UI (text spans, images, links, outline, ...).

All coordinates returned are in the *visible* page space: PDF points, origin at the top-left of the
displayed (cropped and rotated) page - the same space pdf.js uses at scale 1.
"""
import pymupdf as fitz

from .common import ToolError, open_pdf, require_page, unrotated_to_visible


def _r(rect) -> list[float]:
    return [round(v, 2) for v in fitz.Rect(rect)]


def info(path) -> dict:
    doc = open_pdf(path)
    pages = [{"width": p.rect.width, "height": p.rect.height, "rotation": p.rotation} for p in doc]
    data = {
        "page_count": doc.page_count,
        "metadata": doc.metadata,
        "pages": pages,
        "is_encrypted": doc.is_encrypted,
        "has_forms": bool(doc.is_form_pdf),
        "embedded_files": doc.embfile_count(),
    }
    doc.close()
    return data


def spans(path, page: int) -> list[dict]:
    doc = open_pdf(path)
    p = require_page(doc, page)
    out = []
    for block in p.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]:
        for line in block.get("lines", []):
            for s in line["spans"]:
                if not s["text"].strip():
                    continue
                out.append(
                    {
                        "text": s["text"],
                        "bbox": _r(unrotated_to_visible(p, s["bbox"])),
                        "raw_bbox": _r(s["bbox"]),
                        "origin": [round(s["origin"][0], 2), round(s["origin"][1], 2)],
                        "font": s["font"],
                        "size": round(s["size"], 2),
                        "color": f"#{s['color']:06x}",
                        "bold": bool(s["flags"] & 16) or "bold" in s["font"].lower(),
                        "italic": bool(s["flags"] & 2) or "italic" in s["font"].lower() or "oblique" in s["font"].lower(),
                        "dir": list(line.get("dir", (1, 0))),
                    }
                )
    doc.close()
    return out


def images(path, page: int) -> list[dict]:
    doc = open_pdf(path)
    p = require_page(doc, page)
    out = []
    for info in p.get_image_info(xrefs=True):
        if not info.get("xref"):
            continue  # inline images cannot be edited individually
        out.append(
            {
                "xref": info["xref"],
                "bbox": _r(unrotated_to_visible(p, info["bbox"])),
                "width": info["width"],
                "height": info["height"],
            }
        )
    doc.close()
    return out


def links(path, page: int) -> list[dict]:
    doc = open_pdf(path)
    p = require_page(doc, page)
    out = []
    for i, lnk in enumerate(p.get_links()):
        out.append(
            {
                "index": i,
                "bbox": _r(unrotated_to_visible(p, lnk["from"])),
                "uri": lnk.get("uri"),
                "page": (lnk["page"] + 1) if lnk.get("kind") == fitz.LINK_GOTO else None,
            }
        )
    doc.close()
    return out


def outline(path) -> list[dict]:
    doc = open_pdf(path)
    toc = [{"level": lvl, "title": title, "page": pg} for lvl, title, pg in doc.get_toc(simple=True)]
    doc.close()
    return toc


def attachments(path) -> list[dict]:
    doc = open_pdf(path)
    out = []
    for name in doc.embfile_names():
        meta = doc.embfile_info(name)
        out.append({"name": name, "filename": meta.get("filename"), "size": meta.get("size"), "description": meta.get("desc")})
    doc.close()
    return out


def annotations(path, page: int) -> list[dict]:
    doc = open_pdf(path)
    p = require_page(doc, page)
    out = []
    for a in p.annots():
        out.append(
            {
                "xref": a.xref,
                "type": a.type[1],
                "bbox": _r(unrotated_to_visible(p, a.rect)),
                "content": a.info.get("content", ""),
                "author": a.info.get("title", ""),
            }
        )
    doc.close()
    return out


def fields(path) -> list[dict]:
    doc = open_pdf(path)
    out = []
    for p in doc:
        for w in p.widgets():
            out.append(
                {
                    "name": w.field_name,
                    "type": w.field_type_string,
                    "value": w.field_value,
                    "options": list(w.choice_values or []),
                    "on_state": w.on_state() if w.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON) else None,
                    "page": p.number,
                    "bbox": _r(unrotated_to_visible(p, w.rect)),
                    "label": w.field_label or "",
                }
            )
    doc.close()
    return out


def search(path, query: str) -> list[dict]:
    if not query.strip():
        return []
    doc = open_pdf(path)
    out = []
    for p in doc:
        for r in p.search_for(query):
            out.append({"page": p.number, "bbox": _r(unrotated_to_visible(p, r))})
            if len(out) >= 2000:
                doc.close()
                return out
    doc.close()
    return out


INSPECTORS = {
    "info": lambda path, page, q: info(path),
    "spans": lambda path, page, q: spans(path, page),
    "images": lambda path, page, q: images(path, page),
    "links": lambda path, page, q: links(path, page),
    "outline": lambda path, page, q: outline(path),
    "attachments": lambda path, page, q: attachments(path),
    "annotations": lambda path, page, q: annotations(path, page),
    "fields": lambda path, page, q: fields(path),
    "search": lambda path, page, q: search(path, q),
}


def inspect(path, what: str, page: int = 0, q: str = ""):
    if what not in INSPECTORS:
        raise ToolError(f"Unknown inspection '{what}'.")
    return INSPECTORS[what](path, page, q)
