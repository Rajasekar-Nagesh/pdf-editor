"""Shared helpers for PDF tools: context objects, page-range parsing, subprocess with timeouts."""
import logging
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf as fitz  # PyMuPDF

log = logging.getLogger("pdfdesk.tools")


class ToolError(Exception):
    """An error with a message that is safe and friendly to show to the user."""


@dataclass
class ToolContext:
    workdir: Path
    inputs: list[Path]
    input_names: list[str]
    assets: dict[str, Path] = field(default_factory=dict)  # params "<x>_file_id" resolved to paths
    progress: Callable[[int, str], None] = lambda pct, msg="": None

    def out(self, name: str) -> Path:
        """A path for an output file inside the job's working directory."""
        p = self.workdir / "out"
        p.mkdir(exist_ok=True)
        return p / name

    @property
    def stem(self) -> str:
        return Path(self.input_names[0]).stem if self.input_names else "document"


@dataclass
class ToolOutput:
    files: list[tuple[Path, str]] = field(default_factory=list)  # (local path, download name)
    data: dict = field(default_factory=dict)


def open_pdf(path: Path) -> fitz.Document:
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise ToolError("This file could not be opened as a PDF. It may be damaged.") from exc
    if doc.needs_pass:
        raise ToolError("This PDF is password protected. Remove the password first (Protect > Remove password).")
    if not doc.is_pdf:
        doc = fitz.open("pdf", doc.convert_to_pdf())
    return doc


def save_pdf(doc: fitz.Document, path: Path) -> Path:
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path


def parse_pages(spec: str | None, count: int) -> list[int]:
    """Parse "1-3,5,8-" (1-based, inclusive) into sorted unique 0-based indices.

    Empty / "all" means every page. Supports "odd", "even" and "last".
    """
    if spec is None or str(spec).strip().lower() in ("", "all", "*"):
        return list(range(count))
    spec = str(spec).strip().lower()
    if spec == "odd":
        return list(range(0, count, 2))
    if spec == "even":
        return list(range(1, count, 2))
    result: set[int] = set()
    for part in spec.split(","):
        part = part.strip().replace("last", str(count))
        if not part:
            continue
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if m:
            start = int(m.group(1)) if m.group(1) else 1
            end = int(m.group(2)) if m.group(2) else count
        elif part.isdigit():
            start = end = int(part)
        else:
            raise ToolError(f'Invalid page range "{part}". Use a format like 1-3,5,8-.')
        if start < 1 or end < start:
            raise ToolError(f'Invalid page range "{part}".')
        for p in range(start, min(end, count) + 1):
            result.add(p - 1)
    if not result:
        raise ToolError("The page range does not match any page in this document.")
    return sorted(result)


def parse_ranges(spec: str, count: int) -> list[list[int]]:
    """Parse "1-3;4-6;7-" into groups of 0-based pages (one output document per group)."""
    groups = [g for g in re.split(r"[;\n]", spec or "") if g.strip()]
    if not groups:
        raise ToolError("Enter at least one page range, e.g. 1-3; 4-6.")
    return [parse_pages(g, count) for g in groups]


def run_cmd(args: list[str], timeout: int, what: str, cwd: Path | None = None, env: dict | None = None) -> str:
    """Run an external program with a timeout. Output is captured and never logged in full."""
    if shutil.which(args[0]) is None and not Path(args[0]).exists():
        raise ToolError(f"{what} is not installed on this server.")
    try:
        proc = subprocess.run(
            args, cwd=cwd, env=env, capture_output=True, timeout=timeout, check=False, text=True, errors="replace"
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"{what} took too long (over {timeout} seconds) and was stopped.") from exc
    if proc.returncode != 0:
        log.warning("%s exited with %s", what, proc.returncode)
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        raise ToolError(f"{what} failed: {' '.join(tail)[:300] or 'unknown error'}")
    return proc.stdout


def visible_to_unrotated(page: fitz.Page, rect) -> fitz.Rect:
    """Convert a rect given in the page's visible (rotated, top-left origin) space to PyMuPDF space."""
    r = fitz.Rect(rect)
    if page.rotation:
        r = r * page.derotation_matrix
    return r.normalize()


def visible_point(page: fitz.Page, x: float, y: float) -> fitz.Point:
    p = fitz.Point(x, y)
    if page.rotation:
        p = p * page.derotation_matrix
    return p


def unrotated_to_visible(page: fitz.Page, rect) -> fitz.Rect:
    r = fitz.Rect(rect)
    if page.rotation:
        r = r * page.rotation_matrix
    return r.normalize()


def hex_to_rgb(color: str | None, default=(0, 0, 0)) -> tuple[float, float, float]:
    if not color:
        return default
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", c):
        return default
    return tuple(int(c[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def require_page(doc: fitz.Document, page: int) -> fitz.Page:
    if page < 0 or page >= doc.page_count:
        raise ToolError(f"Page {page + 1} does not exist (document has {doc.page_count} pages).")
    return doc[page]


# Fonts for non-Latin scripts (installed in the Docker image via fonts-noto-*).
SCRIPT_FONTS = [
    (re.compile(r"[஀-௿]"), ["/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf"]),
    (re.compile(r"[ऀ-ॿ]"), ["/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"]),
]
UNICODE_FALLBACK = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
]


def font_for(text: str, family: str = "helv", bold: bool = False, italic: bool = False) -> tuple[str, str | None]:
    """Pick (fontname, fontfile) able to render `text`, matching the requested family/style for Latin text."""
    for pattern, files in SCRIPT_FONTS:
        if pattern.search(text):
            for f in files:
                if Path(f).exists():
                    return ("F" + Path(f).stem.replace("-", "")[:20], f)
    if any(ord(ch) > 255 for ch in text):
        for f in UNICODE_FALLBACK:
            if Path(f).exists():
                return ("FUni", f)
    family = (family or "helv").lower()
    if any(k in family for k in ("times", "serif", "roman", "georgia", "garamond", "cambria", "tiro")) and "sans" not in family:
        names = ("tiro", "tibo", "tiit", "tibi")
    elif any(k in family for k in ("courier", "mono", "consol", "cour")):
        names = ("cour", "cobo", "coit", "cobi")
    else:
        names = ("helv", "hebo", "heit", "hebi")
    idx = (1 if bold else 0) + (2 if italic else 0)
    return names[idx], None


def text_length(text: str, fontname: str, fontfile: str | None, size: float) -> float:
    if fontfile:
        return fitz.Font(fontfile=fontfile).text_length(text, fontsize=size)
    return fitz.get_text_length(text, fontname=fontname, fontsize=size)
