"""Compare two PDFs: word-level diff with highlights on both versions plus a side-by-side PDF."""
import difflib

import pymupdf as fitz

from .common import ToolContext, ToolError, ToolOutput, open_pdf, save_pdf

RED = (0.95, 0.3, 0.3)
GREEN = (0.2, 0.75, 0.3)
AMBER = (1.0, 0.75, 0.1)


def _words(doc: fitz.Document) -> list[tuple[str, int, fitz.Rect]]:
    out = []
    for page in doc:
        for x0, y0, x1, y1, w, *_ in page.get_text("words", sort=True):
            out.append((w, page.number, fitz.Rect(x0, y0, x1, y1)))
    return out


def _mark(doc: fitz.Document, items, color) -> None:
    for _w, pno, rect in items:
        page = doc[pno]  # keep a reference: annotations need their page object alive
        annot = page.add_highlight_annot(rect)
        annot.set_colors(stroke=color)
        annot.set_opacity(0.45)
        annot.update()


def compare(ctx: ToolContext) -> ToolOutput:
    if len(ctx.inputs) != 2:
        raise ToolError("Choose exactly two PDFs to compare (old version first, then new version).")
    a, b = open_pdf(ctx.inputs[0]), open_pdf(ctx.inputs[1])
    wa, wb = _words(a), _words(b)
    if not wa and not wb:
        raise ToolError("Neither document contains text. Run OCR on scanned documents first.")
    ctx.progress(20, "Finding differences")
    matcher = difflib.SequenceMatcher(a=[w[0] for w in wa], b=[w[0] for w in wb], autojunk=False)
    changes = []
    stats = {"inserted": 0, "deleted": 0, "replaced": 0}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        old, new = wa[i1:i2], wb[j1:j2]
        if tag == "delete":
            _mark(a, old, RED)
            stats["deleted"] += 1
        elif tag == "insert":
            _mark(b, new, GREEN)
            stats["inserted"] += 1
        else:
            _mark(a, old, AMBER)
            _mark(b, new, AMBER)
            stats["replaced"] += 1
        if len(changes) < 1000:
            changes.append(
                {
                    "type": {"delete": "deleted", "insert": "inserted", "replace": "changed"}[tag],
                    "old": " ".join(w[0] for w in old)[:500],
                    "new": " ".join(w[0] for w in new)[:500],
                    "page_a": (old[0][1] + 1) if old else None,
                    "page_b": (new[0][1] + 1) if new else None,
                }
            )
    ctx.progress(70, "Building side-by-side view")
    stem_a = ctx.input_names[0].rsplit(".", 1)[0]
    stem_b = ctx.input_names[1].rsplit(".", 1)[0]
    out = ToolOutput()
    path_a, path_b = ctx.out(f"{stem_a}-compared.pdf"), ctx.out(f"{stem_b}-compared.pdf")
    out.files.append((save_pdf(a, path_a), path_a.name))
    out.files.append((save_pdf(b, path_b), path_b.name))

    # show_pdf_page() does not copy annotations, so bake the highlights into page content first.
    a2, b2 = fitz.open(path_a), fitz.open(path_b)
    a2.bake()
    b2.bake()
    side = fitz.open()
    for i in range(max(a2.page_count, b2.page_count)):
        ra = a2[i].rect if i < a2.page_count else fitz.Rect(0, 0, 300, 300)
        rb = b2[i].rect if i < b2.page_count else fitz.Rect(0, 0, 300, 300)
        left_w = max(ra.width, 300)
        pg = side.new_page(width=left_w + rb.width + 30, height=max(ra.height, rb.height) + 30)
        pg.insert_text((10, 18), f"Original - page {i + 1}", fontsize=10, color=(0.4, 0.4, 0.4))
        pg.insert_text((left_w + 20, 18), f"Revised - page {i + 1}", fontsize=10, color=(0.4, 0.4, 0.4))
        if i < a2.page_count:
            pg.show_pdf_page(fitz.Rect(10, 25, 10 + ra.width, 25 + ra.height), a2, i)
        if i < b2.page_count:
            pg.show_pdf_page(fitz.Rect(left_w + 20, 25, left_w + 20 + rb.width, 25 + rb.height), b2, i)
    out.files.append((save_pdf(side, ctx.out("comparison-side-by-side.pdf")), "comparison-side-by-side.pdf"))
    out.data = {"stats": stats, "changes": changes, "identical": not changes}
    return out
