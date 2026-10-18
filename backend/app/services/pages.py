"""Page organisation tools: reorder, rotate, delete, extract, insert blank, crop, merge, split."""
import pymupdf as fitz

from .common import ToolContext, ToolError, ToolOutput, open_pdf, parse_pages, parse_ranges, save_pdf


def reorder(ctx: ToolContext, order: list[int]) -> ToolOutput:
    """`order` is the new sequence of 1-based page numbers (pages left out are dropped)."""
    doc = open_pdf(ctx.inputs[0])
    if not order:
        raise ToolError("The new page order is empty.")
    zero = [int(p) - 1 for p in order]
    if any(p < 0 or p >= doc.page_count for p in zero):
        raise ToolError("The page order refers to a page that does not exist.")
    doc.select(zero)
    return ToolOutput(files=[(save_pdf(doc, ctx.out(f"{ctx.stem}.pdf")), f"{ctx.stem}.pdf")])


def rotate(ctx: ToolContext, pages: str = "all", angle: int = 90) -> ToolOutput:
    if int(angle) % 90:
        raise ToolError("Rotation must be a multiple of 90 degrees.")
    doc = open_pdf(ctx.inputs[0])
    for i in parse_pages(pages, doc.page_count):
        doc[i].set_rotation((doc[i].rotation + int(angle)) % 360)
    return ToolOutput(files=[(save_pdf(doc, ctx.out(f"{ctx.stem}.pdf")), f"{ctx.stem}.pdf")])


def delete_pages(ctx: ToolContext, pages: str) -> ToolOutput:
    doc = open_pdf(ctx.inputs[0])
    remove = set(parse_pages(pages, doc.page_count))
    if len(remove) >= doc.page_count:
        raise ToolError("You cannot delete every page of the document.")
    doc.select([i for i in range(doc.page_count) if i not in remove])
    return ToolOutput(files=[(save_pdf(doc, ctx.out(f"{ctx.stem}.pdf")), f"{ctx.stem}.pdf")])


def extract_pages(ctx: ToolContext, pages: str) -> ToolOutput:
    doc = open_pdf(ctx.inputs[0])
    doc.select(parse_pages(pages, doc.page_count))
    name = f"{ctx.stem}-extract.pdf"
    return ToolOutput(files=[(save_pdf(doc, ctx.out(name)), name)])


def insert_blank(ctx: ToolContext, after: int = 0, count: int = 1, size: str = "same") -> ToolOutput:
    """Insert `count` blank pages after page `after` (0 = at the start)."""
    doc = open_pdf(ctx.inputs[0])
    after = max(0, min(int(after), doc.page_count))
    count = max(1, min(int(count), 500))
    sizes = {"a4": fitz.paper_size("a4"), "letter": fitz.paper_size("letter"), "legal": fitz.paper_size("legal")}
    if size in sizes:
        w, h = sizes[size]
    else:
        ref = doc[max(0, after - 1)] if doc.page_count else None
        w, h = (ref.rect.width, ref.rect.height) if ref else fitz.paper_size("a4")
    for k in range(count):
        doc.new_page(pno=after + k, width=w, height=h)
    return ToolOutput(files=[(save_pdf(doc, ctx.out(f"{ctx.stem}.pdf")), f"{ctx.stem}.pdf")])


def crop(
    ctx: ToolContext,
    pages: str = "all",
    left: float = 0,
    top: float = 0,
    right: float = 0,
    bottom: float = 0,
    rect: list[float] | None = None,
) -> ToolOutput:
    """Crop by margins (points) or to an explicit rect [x0, y0, x1, y1] in visible page coordinates."""
    doc = open_pdf(ctx.inputs[0])
    for i in parse_pages(pages, doc.page_count):
        page = doc[i]
        # Work in the page's current visible box, then translate to the mediabox system.
        cur = page.cropbox
        if rect:
            r = fitz.Rect(rect)
            if page.rotation:
                r = (r * page.derotation_matrix).normalize()
            new = fitz.Rect(cur.x0 + r.x0, cur.y0 + r.y0, cur.x0 + r.x1, cur.y0 + r.y1)
        else:
            new = fitz.Rect(cur.x0 + float(left), cur.y0 + float(top), cur.x1 - float(right), cur.y1 - float(bottom))
        new = new & page.mediabox
        if new.is_empty or new.width < 10 or new.height < 10:
            raise ToolError(f"The crop area on page {i + 1} is too small.")
        page.set_cropbox(new)
    return ToolOutput(files=[(save_pdf(doc, ctx.out(f"{ctx.stem}.pdf")), f"{ctx.stem}.pdf")])


def merge(ctx: ToolContext, name: str = "merged.pdf") -> ToolOutput:
    """Merge all input files in order. Images are converted to pages."""
    if len(ctx.inputs) < 2:
        raise ToolError("Choose at least two files to merge.")
    out = fitz.open()
    for n, path in enumerate(ctx.inputs):
        ctx.progress(int(n * 90 / len(ctx.inputs)), f"Adding {ctx.input_names[n]}")
        src = open_pdf(path)
        out.insert_pdf(src)
        src.close()
    name = name if name.lower().endswith(".pdf") else f"{name}.pdf"
    return ToolOutput(files=[(save_pdf(out, ctx.out(name)), name)])


def split(ctx: ToolContext, mode: str = "every", every: int = 1, ranges: str = "") -> ToolOutput:
    """Split into several PDFs, either every N pages or by explicit ranges ("1-3; 4-6")."""
    doc = open_pdf(ctx.inputs[0])
    if mode == "ranges":
        groups = parse_ranges(ranges, doc.page_count)
    else:
        n = max(1, int(every))
        groups = [list(range(i, min(i + n, doc.page_count))) for i in range(0, doc.page_count, n)]
    if len(groups) > 1000:
        raise ToolError("That would create more than 1000 files. Use a larger split size.")
    out = ToolOutput()
    for k, group in enumerate(groups, 1):
        part = fitz.open()
        for p in group:
            part.insert_pdf(doc, from_page=p, to_page=p)
        label = f"{group[0] + 1}-{group[-1] + 1}" if len(group) > 1 else f"{group[0] + 1}"
        name = f"{ctx.stem}-part{k}-p{label}.pdf"
        out.files.append((save_pdf(part, ctx.out(name)), name))
        ctx.progress(int(k * 95 / len(groups)), f"Created part {k}")
    return out
