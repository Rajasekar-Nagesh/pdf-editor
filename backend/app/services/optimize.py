"""Compression, PDF/A conversion + veraPDF validation, and OCR."""
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pikepdf

from ..config import get_settings
from .common import ToolContext, ToolError, ToolOutput, open_pdf, run_cmd

GS_PRESETS = {"low": "/screen", "medium": "/ebook", "high": "/printer"}
ICC_CANDIDATES = [
    "/usr/share/color/icc/ghostscript/srgb.icc",
    "/usr/share/ghostscript/iccprofiles/srgb.icc",
    "/usr/share/color/icc/sRGB.icc",
    "/usr/share/color/icc/colord/sRGB.icc",
]


def _gs() -> str:
    for name in ("gs", "gsc"):
        if shutil.which(name):
            return name
    raise ToolError("Ghostscript is not installed on this server.")


def compress(ctx: ToolContext, quality: str = "medium") -> ToolOutput:
    """quality: low (smallest file), medium, high (best quality). Keeps whichever result is smallest."""
    if quality not in GS_PRESETS:
        raise ToolError("Choose low, medium or high quality.")
    src = ctx.inputs[0]
    open_pdf(src).close()
    before = src.stat().st_size
    candidates = []

    ctx.progress(10, "Optimising images")
    gs_out = ctx.workdir / "gs.pdf"
    try:
        run_cmd(
            [
                _gs(), "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.6", f"-dPDFSETTINGS={GS_PRESETS[quality]}",
                "-dNOPAUSE", "-dBATCH", "-dQUIET", "-dSAFER", "-dDetectDuplicateImages=true",
                "-dCompressFonts=true", f"-sOutputFile={gs_out}", str(src),
            ],
            timeout=get_settings().ghostscript_timeout,
            what="Ghostscript",
        )
        candidates.append(gs_out)
    except ToolError:
        if quality == "low":
            raise

    ctx.progress(70, "Optimising structure")
    pk_out = ctx.workdir / "pk.pdf"
    with pikepdf.open(src) as pdf:
        pdf.remove_unreferenced_resources()
        pdf.save(pk_out, compress_streams=True, object_stream_mode=pikepdf.ObjectStreamMode.generate, recompress_flate=True)
    candidates.append(pk_out)

    best = min(candidates, key=lambda p: p.stat().st_size)
    if best.stat().st_size >= before:
        best = src  # never return a bigger file
    name = f"{ctx.stem}-compressed.pdf"
    final = ctx.out(name)
    shutil.copyfile(best, final)
    after = final.stat().st_size
    return ToolOutput(
        files=[(final, name)],
        data={"before": before, "after": after, "saved_percent": round(100 * (before - after) / before, 1) if before else 0},
    )


def _pdfa_def(workdir: Path, title: str) -> tuple[Path, str]:
    icc = next((p for p in ICC_CANDIDATES if Path(p).exists()), None)
    if not icc:
        raise ToolError("No sRGB ICC profile is installed on this server (needed for PDF/A).")
    safe_title = title.replace("(", "").replace(")", "").replace("\\", "")[:120]
    ps = workdir / "PDFA_def.ps"
    ps.write_text(
        f"""%!
/ICCProfile ({icc}) def
[/Title ({safe_title}) /DOCINFO pdfmark
[/_objdef {{icc_PDFA}} /type /stream /OBJ pdfmark
[{{icc_PDFA}} <</N 3>> /PUT pdfmark
[{{icc_PDFA}} ICCProfile (r) file /PUT pdfmark
[/_objdef {{OutputIntent_PDFA}} /type /dict /OBJ pdfmark
[{{OutputIntent_PDFA}} <<
  /Type /OutputIntent
  /S /GTS_PDFA1
  /DestOutputProfile {{icc_PDFA}}
  /OutputConditionIdentifier (sRGB)
>> /PUT pdfmark
[{{Catalog}} <</OutputIntents [ {{OutputIntent_PDFA}} ]>> /PUT pdfmark
"""
    )
    return ps, icc


def verapdf_validate(path: Path, flavour: str = "2b") -> dict:
    """Run veraPDF and summarise the machine-readable report."""
    s = get_settings()
    exe = s.verapdf_path
    if not shutil.which(exe) and not Path(exe).exists():
        return {"available": False, "compliant": None, "message": "veraPDF is not installed on this server."}
    # veraPDF exits non-zero when a file is not compliant but still prints the report, so we
    # call it directly instead of through run_cmd().
    try:
        proc = subprocess.run(
            [exe, "--flavour", flavour, "--format", "mrr", str(path)],
            capture_output=True, text=True, errors="replace", timeout=s.verapdf_timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"available": True, "compliant": None, "message": "veraPDF validation timed out."}
    xml = proc.stdout or ""
    if "<" not in xml:
        return {"available": True, "compliant": None, "message": "veraPDF did not produce a report."}
    try:
        root = ET.fromstring(xml[xml.index("<"):])
    except (ValueError, ET.ParseError):
        return {"available": True, "compliant": None, "message": "Could not read the veraPDF report."}
    report = next((el for el in root.iter() if el.tag.endswith("validationReport")), None)
    compliant = report is not None and report.get("isCompliant") == "true"
    failed = []
    for rule in root.iter():
        if rule.tag.endswith("rule") and rule.get("status") == "failed":
            desc = next((c.text for c in rule if c.tag.endswith("description")), "")
            failed.append({"clause": rule.get("clause"), "test": rule.get("testNumber"), "description": (desc or "").strip()[:300], "failed_checks": rule.get("failedChecks")})
    return {
        "available": True,
        "compliant": compliant,
        "profile": report.get("profileName") if report is not None else None,
        "failed_rules": failed[:100],
        "message": "Compliant with PDF/A-" + flavour.upper() if compliant else "Not compliant",
    }


def to_pdfa(ctx: ToolContext, validate: bool = True) -> ToolOutput:
    doc = open_pdf(ctx.inputs[0])
    title = doc.metadata.get("title") or ctx.stem
    doc.close()
    ps, icc = _pdfa_def(ctx.workdir, title)
    name = f"{ctx.stem}-pdfa.pdf"
    out = ctx.out(name)
    ctx.progress(10, "Converting to PDF/A-2b")
    run_cmd(
        [
            _gs(), "-dPDFA=2", "-dBATCH", "-dNOPAUSE", "-dQUIET", "-dNOOUTERSAVE", "-dSAFER",
            f"--permit-file-read={icc}", "-sColorConversionStrategy=RGB", "-sProcessColorModel=DeviceRGB",
            "-dPDFACompatibilityPolicy=1", "-sDEVICE=pdfwrite", f"-sOutputFile={out}", str(ps), str(ctx.inputs[0]),
        ],
        timeout=get_settings().ghostscript_timeout,
        what="Ghostscript",
    )
    data = {}
    if validate:
        ctx.progress(70, "Validating with veraPDF")
        data["validation"] = verapdf_validate(out, "2b")
    return ToolOutput(files=[(out, name)], data=data)


def validate_pdfa(ctx: ToolContext, flavour: str = "2b") -> ToolOutput:
    if flavour not in ("1a", "1b", "2a", "2b", "2u", "3a", "3b", "3u", "4"):
        raise ToolError("Unknown PDF/A level.")
    return ToolOutput(data={"validation": verapdf_validate(ctx.inputs[0], flavour)})


OCR_LANGS = {"eng", "tam", "hin"}


def ocr_file(src: Path, dest: Path, languages: list[str], mode: str = "skip", deskew: bool = True, rotate: bool = True) -> None:
    langs = [lang for lang in languages if lang in OCR_LANGS] or ["eng"]
    args = ["ocrmypdf", "-l", "+".join(langs), "--output-type", "pdf", "--jobs", "2"]
    args.append({"skip": "--skip-text", "force": "--force-ocr", "redo": "--redo-ocr"}.get(mode, "--skip-text"))
    if deskew and mode != "redo":
        args.append("--deskew")
    if rotate:
        args.append("--rotate-pages")
    args += [str(src), str(dest)]
    run_cmd(args, timeout=get_settings().ocr_timeout, what="OCR")


def ocr(ctx: ToolContext, languages: list[str] | None = None, mode: str = "skip", deskew: bool = True) -> ToolOutput:
    """Make scanned PDFs (or images) searchable with OCRmyPDF + Tesseract."""
    src = ctx.inputs[0]
    doc = open_pdf(src)
    if not src.read_bytes()[:1024].count(b"%PDF"):
        # An image input: convert to PDF first.
        tmp = ctx.workdir / "image.pdf"
        doc.save(tmp)
        src = tmp
    doc.close()
    ctx.progress(5, "Recognising text (this can take a while)")
    name = f"{ctx.stem}-ocr.pdf"
    ocr_file(src, ctx.out(name), languages or ["eng"], mode, deskew)
    return ToolOutput(files=[(ctx.out(name), name)])
