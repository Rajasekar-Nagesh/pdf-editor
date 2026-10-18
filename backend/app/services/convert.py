"""Conversions to and from PDF."""
import html
import ipaddress
import os
import re
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import pymupdf as fitz
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from PIL import Image

from ..config import get_settings
from .common import ToolContext, ToolError, ToolOutput, open_pdf, parse_pages, run_cmd, save_pdf

NUMBER_RE = re.compile(r"^[-+(]?\s*[₹$€£]?\s*[\d,]+(\.\d+)?\)?%?$")


def _to_number(value: str):
    """Turn '1,234.50' / '₹ 99' / '(12)' into a number so Excel can sum it; otherwise keep the text."""
    v = (value or "").strip()
    if not v or not NUMBER_RE.match(v):
        return v
    neg = v.startswith("(") and v.endswith(")") or v.startswith("-")
    pct = v.endswith("%")
    digits = re.sub(r"[^\d.]", "", v)
    if digits.count(".") > 1 or not digits.strip("."):
        return v
    num = float(digits)
    if pct:
        num /= 100
    num = -num if neg else num
    return int(num) if num.is_integer() and "." not in digits else num


def _write_sheet(ws, rows: list[list]) -> None:
    for r, row in enumerate(rows, 1):
        for c, val in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=_to_number(str(val)) if val is not None else None)
            if r == 1:
                cell.font = Font(bold=True)
    for c in range(1, max((len(r) for r in rows), default=0) + 1):
        width = max((len(str(row[c - 1])) for row in rows if len(row) >= c and row[c - 1]), default=8)
        ws.column_dimensions[get_column_letter(c)].width = min(60, max(8, width + 2))


# ------------------------------------------------------------------ PDF -> X


def pdf_to_word(ctx: ToolContext) -> ToolOutput:
    from pdf2docx import Converter

    name = f"{ctx.stem}.docx"
    out = ctx.out(name)
    open_pdf(ctx.inputs[0]).close()  # friendly errors for encrypted / broken files
    try:
        cv = Converter(str(ctx.inputs[0]))
        cv.convert(str(out), multi_processing=False)
        cv.close()
    except Exception as exc:
        raise ToolError("This PDF could not be converted to Word.") from exc
    return ToolOutput(files=[(out, name)])


def _tables_from_pdf(path: Path, pages: list[int], progress) -> list[tuple[int, list[list]]]:
    """Extract tables with pdfplumber (ruled + text strategies), falling back to Camelot."""
    import pdfplumber

    tables: list[tuple[int, list[list]]] = []
    with pdfplumber.open(path) as pdf:
        for n, i in enumerate(pages):
            page = pdf.pages[i]
            found = page.extract_tables()
            if not found:
                found = page.extract_tables({"vertical_strategy": "text", "horizontal_strategy": "text"})
            for t in found:
                rows = [[(c or "").replace("\n", " ").strip() for c in row] for row in t]
                rows = [r for r in rows if any(r)]
                if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                    tables.append((i, rows))
            progress(10 + int((n + 1) * 70 / len(pages)), f"Reading page {i + 1}")
    if not tables:
        try:
            import camelot

            for flavor in ("lattice", "stream"):
                ct = camelot.read_pdf(str(path), pages=",".join(str(p + 1) for p in pages), flavor=flavor)
                for t in ct:
                    rows = t.df.values.tolist()
                    if len(rows) >= 2:
                        tables.append((int(t.page) - 1, rows))
                if tables:
                    break
        except Exception:
            pass
    return tables


def pdf_to_excel(ctx: ToolContext, pages: str = "all") -> ToolOutput:
    doc = open_pdf(ctx.inputs[0])
    targets = parse_pages(pages, doc.page_count)
    text_pages = [(i, doc[i].get_text("text")) for i in targets]
    doc.close()
    tables = _tables_from_pdf(ctx.inputs[0], targets, ctx.progress)
    wb = Workbook()
    wb.remove(wb.active)
    for k, (page, rows) in enumerate(tables, 1):
        _write_sheet(wb.create_sheet(f"Table {k} (p{page + 1})"[:31]), rows)
    if not tables:
        # No table structure found: put each line on a row, splitting columns on 2+ spaces.
        ws = wb.create_sheet("Text")
        rows = []
        for i, txt in text_pages:
            for line in txt.splitlines():
                if line.strip():
                    rows.append(re.split(r"\s{2,}|\t", line.strip()))
        if not rows:
            raise ToolError("No text found. If this is a scanned document, use 'Scanned table to Excel'.")
        _write_sheet(ws, rows)
    name = f"{ctx.stem}.xlsx"
    wb.save(ctx.out(name))
    return ToolOutput(files=[(ctx.out(name), name)], data={"tables": len(tables)})


def pdf_to_pptx(ctx: ToolContext, dpi: int = 150) -> ToolOutput:
    """One slide per page; the page is rendered as a picture and its text is kept in the notes."""
    from pptx import Presentation
    from pptx.util import Emu

    doc = open_pdf(ctx.inputs[0])
    prs = Presentation()
    first = doc[0].rect
    prs.slide_width = Emu(int(first.width * 12700))
    prs.slide_height = Emu(int(first.height * 12700))
    blank = prs.slide_layouts[6]
    dpi = max(72, min(int(dpi), 300))
    for page in doc:
        slide = prs.slides.add_slide(blank)
        img = ctx.out(f"slide-{page.number}.png")
        page.get_pixmap(dpi=dpi).save(img)
        slide.shapes.add_picture(str(img), 0, 0, width=prs.slide_width, height=prs.slide_height)
        slide.notes_slide.notes_text_frame.text = page.get_text("text")[:5000]
        img.unlink()
        ctx.progress(int((page.number + 1) * 95 / doc.page_count), f"Slide {page.number + 1}")
    name = f"{ctx.stem}.pptx"
    prs.save(ctx.out(name))
    return ToolOutput(files=[(ctx.out(name), name)])


def pdf_to_images(ctx: ToolContext, fmt: str = "png", dpi: int = 150, pages: str = "all") -> ToolOutput:
    fmt = "jpg" if fmt.lower() in ("jpg", "jpeg") else "png"
    dpi = max(36, min(int(dpi), 600))
    doc = open_pdf(ctx.inputs[0])
    targets = parse_pages(pages, doc.page_count)
    out = ToolOutput()
    for n, i in enumerate(targets):
        name = f"{ctx.stem}-page{i + 1}.{fmt}"
        pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
        if fmt == "jpg":
            pix.save(ctx.out(name), jpg_quality=88)
        else:
            pix.save(ctx.out(name))
        out.files.append((ctx.out(name), name))
        ctx.progress(int((n + 1) * 95 / len(targets)), f"Page {i + 1}")
    return out


def pdf_to_html(ctx: ToolContext) -> ToolOutput:
    doc = open_pdf(ctx.inputs[0])
    title = html.escape(doc.metadata.get("title") or ctx.stem)
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{title}</title><meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<style>body{font-family:system-ui,sans-serif;background:#f3f4f6;margin:0;padding:16px}"
        ".page{background:#fff;margin:0 auto 24px;max-width:900px;padding:32px;box-shadow:0 1px 4px #0002;overflow:auto}"
        "img{max-width:100%}</style></head><body>",
    ]
    for page in doc:
        parts.append(f"<section class='page' id='page-{page.number + 1}'>")
        parts.append(page.get_text("xhtml"))
        parts.append("</section>")
    parts.append("</body></html>")
    name = f"{ctx.stem}.html"
    ctx.out(name).write_text("\n".join(parts), encoding="utf-8")
    return ToolOutput(files=[(ctx.out(name), name)])


def pdf_to_text(ctx: ToolContext) -> ToolOutput:
    doc = open_pdf(ctx.inputs[0])
    text = "\n\n".join(f"----- Page {p.number + 1} -----\n{p.get_text('text', sort=True)}" for p in doc)
    name = f"{ctx.stem}.txt"
    ctx.out(name).write_text(text, encoding="utf-8")
    return ToolOutput(files=[(ctx.out(name), name)])


# ------------------------------------------------------------------ X -> PDF


def office_file_to_pdf(src: Path, outdir: Path) -> Path:
    """Convert one Office/ODF file with LibreOffice headless (isolated profile, with a timeout)."""
    s = get_settings()
    with tempfile.TemporaryDirectory() as profile:
        run_cmd(
            [
                "soffice",
                f"-env:UserInstallation=file://{profile}",
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf",
                "--outdir",
                str(outdir),
                str(src),
            ],
            timeout=s.libreoffice_timeout,
            what="LibreOffice",
            env={**os.environ, "HOME": profile},
        )
    out = outdir / f"{src.stem}.pdf"
    if not out.exists():
        raise ToolError("LibreOffice could not convert this file.")
    return out


def office_to_pdf(ctx: ToolContext) -> ToolOutput:
    out = ToolOutput()
    for n, (path, display) in enumerate(zip(ctx.inputs, ctx.input_names)):
        ctx.progress(int(n * 90 / len(ctx.inputs)), f"Converting {display}")
        work = ctx.workdir / f"lo-{n}"
        work.mkdir()
        src = work / (Path(display).stem + path.suffix)
        src.write_bytes(path.read_bytes())
        pdf = office_file_to_pdf(src, work)
        out.files.append((pdf, f"{Path(display).stem}.pdf"))
    return out


def images_to_pdf(ctx: ToolContext, page_size: str = "fit", margin: float = 0, name: str = "images.pdf") -> ToolOutput:
    """Combine images into one PDF. page_size: fit (page = image size), a4 or letter."""
    doc = fitz.open()
    for n, path in enumerate(ctx.inputs):
        with Image.open(path) as im:
            frames = getattr(im, "n_frames", 1)
        for f in range(frames):
            with Image.open(path) as im:
                if frames > 1:
                    im.seek(f)
                im = im.convert("RGB") if im.mode not in ("RGB", "L") else im
                buf = ctx.out(f"img-{n}-{f}.jpg")
                im.save(buf, "JPEG", quality=92)
                w, h = im.size
                dpi = (im.info.get("dpi") or (96, 96))[0] or 96
            iw, ih = w * 72 / dpi, h * 72 / dpi
            if page_size in ("a4", "letter"):
                pw, ph = fitz.paper_size(page_size)
                if iw > ih:
                    pw, ph = ph, pw
            else:
                pw, ph = iw + 2 * float(margin), ih + 2 * float(margin)
            page = doc.new_page(width=pw, height=ph)
            m = float(margin)
            page.insert_image(fitz.Rect(m, m, pw - m, ph - m), filename=str(buf), keep_proportion=True)
            buf.unlink()
        ctx.progress(int((n + 1) * 95 / len(ctx.inputs)), "Adding images")
    name = name if name.lower().endswith(".pdf") else f"{name}.pdf"
    return ToolOutput(files=[(save_pdf(doc, ctx.out(name)), name)])


def check_public_url(url: str) -> str:
    """Block SSRF: only http(s) URLs that resolve to public IP addresses are allowed."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ToolError("Enter a full web address starting with http:// or https://")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ToolError("That web address could not be found.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ToolError("That address points to a private network and cannot be converted.")
    return url.strip()


def url_to_pdf(ctx: ToolContext, url: str, page_size: str = "A4", landscape: bool = False) -> ToolOutput:
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import sync_playwright

    url = check_public_url(url)
    timeout_ms = get_settings().chromium_timeout * 1000
    host = urlparse(url).hostname or "page"
    name = f"{re.sub(r'[^A-Za-z0-9.-]+', '-', host)}.pdf"

    def guard(route):
        # Re-check every sub-request so redirects/iframes cannot reach internal services.
        try:
            check_public_url(route.request.url) if route.request.url.startswith("http") else None
            route.continue_()
        except ToolError:
            route.abort()

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                page = browser.new_page()
                page.route("**/*", guard)
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                page.emulate_media(media="screen")
                page.pdf(
                    path=str(ctx.out(name)),
                    format=page_size if page_size in ("A4", "Letter", "Legal", "A3") else "A4",
                    landscape=bool(landscape),
                    print_background=True,
                    margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"},
                )
            finally:
                browser.close()
    except PWError as exc:
        msg = "timed out" if "Timeout" in str(exc) else "could not be loaded"
        raise ToolError(f"The web page {msg}.") from exc
    return ToolOutput(files=[(ctx.out(name), name)])
