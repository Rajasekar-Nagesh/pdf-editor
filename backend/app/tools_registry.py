"""Registry of every processing tool: what it accepts, how it runs, and how to call it."""
import inspect
from dataclasses import dataclass, field
from pathlib import Path

from .services import annotate, checks, compare, convert, edit, forms, optimize, pages, protect, signature, stamp
from .services.common import ToolContext, ToolError, ToolOutput
from .validation import OFFICE_KINDS

PDF = {"pdf"}
PDF_OR_IMAGE = {"pdf", "image"}


@dataclass
class ToolSpec:
    fn: object
    category: str
    min_files: int = 1
    max_files: int = 1
    accepts: set = field(default_factory=lambda: set(PDF))
    inline: bool = False  # run inside the request; params may contain secrets and are never stored
    batchable: bool = False  # can be a step in a saved batch action (1 PDF in -> 1 PDF out)
    versioned: bool = False  # output is a new version of the input (supports undo/redo chains)


def _batch(ctx: ToolContext, steps: list[dict]) -> ToolOutput:
    """Run saved steps on every input file. Office files and images are converted to PDF first."""
    import pymupdf as fitz

    if not steps:
        raise ToolError("Add at least one step to the batch action.")
    for st in steps:
        spec = TOOLS.get(st.get("tool", ""))
        if not spec or not spec.batchable:
            raise ToolError(f"'{st.get('tool')}' cannot be used in a batch action.")
    out = ToolOutput(data={"files": []})
    total = len(ctx.inputs) * len(steps)
    done = 0
    for idx, (path, display) in enumerate(zip(ctx.inputs, ctx.input_names)):
        stem = Path(display).stem
        work = ctx.workdir / f"batch-{idx}"
        work.mkdir()
        current = path
        try:
            if path.suffix.lower().lstrip(".") in OFFICE_KINDS or display.lower().rsplit(".", 1)[-1] in OFFICE_KINDS:
                src = work / f"{stem}{Path(display).suffix}"
                src.write_bytes(path.read_bytes())
                current = convert.office_file_to_pdf(src, work)
            else:
                with fitz.open(path) as d:
                    if not d.is_pdf:
                        current = work / f"{stem}.pdf"
                        fitz.open("pdf", d.convert_to_pdf()).save(current)
            for n, st in enumerate(steps):
                sub = work / f"step-{n}"
                sub.mkdir()
                sctx = ToolContext(workdir=sub, inputs=[current], input_names=[f"{stem}.pdf"], assets=ctx.assets)
                result = call_tool(st["tool"], sctx, st.get("params") or {})
                pdfs = [p for p, name in result.files if name.lower().endswith(".pdf")]
                if not pdfs:
                    raise ToolError(f"Step '{st['tool']}' produced no PDF.")
                current = pdfs[0]
                done += 1
                ctx.progress(int(done * 95 / total), f"{display}: step {n + 1} of {len(steps)}")
            final = ctx.out(f"{stem}.pdf")
            final.write_bytes(current.read_bytes())
            out.files.append((final, f"{stem}.pdf"))
            out.data["files"].append({"name": display, "status": "ok"})
        except ToolError as exc:
            out.data["files"].append({"name": display, "status": "failed", "error": str(exc)})
            done += len(steps)
    if not out.files:
        raise ToolError("Every file failed: " + "; ".join(f["error"] for f in out.data["files"] if f.get("error"))[:400])
    return out


TOOLS: dict[str, ToolSpec] = {
    # View & organise
    "reorder": ToolSpec(pages.reorder, "organize", versioned=True),
    "rotate": ToolSpec(pages.rotate, "organize", batchable=True, versioned=True),
    "delete_pages": ToolSpec(pages.delete_pages, "organize", versioned=True),
    "extract_pages": ToolSpec(pages.extract_pages, "organize"),
    "insert_blank": ToolSpec(pages.insert_blank, "organize", versioned=True),
    "crop": ToolSpec(pages.crop, "organize", batchable=True, versioned=True),
    "merge": ToolSpec(pages.merge, "organize", min_files=2, max_files=100, accepts=PDF_OR_IMAGE),
    "split": ToolSpec(pages.split, "organize"),
    # Edit
    "replace_text": ToolSpec(edit.replace_text, "edit", versioned=True),
    "add_text": ToolSpec(edit.add_text, "edit", versioned=True),
    "add_image": ToolSpec(edit.add_image, "edit", versioned=True),
    "replace_image": ToolSpec(edit.replace_image, "edit", versioned=True),
    "move_image": ToolSpec(edit.move_image, "edit", versioned=True),
    "crop_image": ToolSpec(edit.crop_image, "edit", versioned=True),
    "delete_image": ToolSpec(edit.delete_image, "edit", versioned=True),
    "set_link": ToolSpec(edit.set_link, "edit", versioned=True),
    "set_bookmarks": ToolSpec(edit.set_bookmarks, "edit", versioned=True),
    "add_attachment": ToolSpec(edit.add_attachment, "edit", versioned=True),
    "remove_attachment": ToolSpec(edit.remove_attachment, "edit", versioned=True),
    "flatten": ToolSpec(edit.flatten, "edit", batchable=True, versioned=True),
    "set_metadata": ToolSpec(edit.set_metadata, "edit", batchable=True, versioned=True),
    "watermark": ToolSpec(stamp.watermark, "edit", batchable=True, versioned=True),
    "page_numbers": ToolSpec(stamp.page_numbers, "edit", batchable=True, versioned=True),
    "header_footer": ToolSpec(stamp.header_footer, "edit", batchable=True, versioned=True),
    "bates": ToolSpec(stamp.bates, "edit", max_files=100, batchable=True),
    # Review
    "annotate": ToolSpec(annotate.annotate, "review", versioned=True),
    "delete_annotation": ToolSpec(annotate.delete_annotation, "review", versioned=True),
    "compare": ToolSpec(compare.compare, "review", min_files=2, max_files=2),
    # Forms & signatures
    "fill_form": ToolSpec(forms.fill_form, "forms", versioned=True),
    "add_fields": ToolSpec(forms.add_fields, "forms", versioned=True),
    "delete_field": ToolSpec(forms.delete_field, "forms", versioned=True),
    "prepare_form": ToolSpec(forms.prepare_form, "forms", versioned=True),
    "place_signature": ToolSpec(signature.place_signature, "forms", versioned=True),
    "validate_signatures": ToolSpec(signature.validate_signatures, "forms"),
    # Convert
    "pdf_to_word": ToolSpec(convert.pdf_to_word, "convert"),
    "pdf_to_excel": ToolSpec(convert.pdf_to_excel, "convert"),
    "pdf_to_pptx": ToolSpec(convert.pdf_to_pptx, "convert"),
    "pdf_to_images": ToolSpec(convert.pdf_to_images, "convert"),
    "pdf_to_html": ToolSpec(convert.pdf_to_html, "convert"),
    "pdf_to_text": ToolSpec(convert.pdf_to_text, "convert"),
    "office_to_pdf": ToolSpec(convert.office_to_pdf, "convert", max_files=50, accepts=set(OFFICE_KINDS)),
    "images_to_pdf": ToolSpec(convert.images_to_pdf, "convert", max_files=200, accepts={"image"}),
    "url_to_pdf": ToolSpec(convert.url_to_pdf, "convert", min_files=0, max_files=0),
    "to_pdfa": ToolSpec(optimize.to_pdfa, "convert", batchable=True),
    "validate_pdfa": ToolSpec(optimize.validate_pdfa, "convert"),
    "compress": ToolSpec(optimize.compress, "convert", batchable=True),
    # Scan & OCR
    "ocr": ToolSpec(optimize.ocr, "ocr", accepts=PDF_OR_IMAGE, batchable=True),
    "scanned_tables_to_excel": ToolSpec(checks.scanned_tables_to_excel, "ocr", accepts=PDF_OR_IMAGE),
    # Protect
    "add_password": ToolSpec(protect.add_password, "protect", inline=True),
    "remove_password": ToolSpec(protect.remove_password, "protect", inline=True),
    "find_sensitive": ToolSpec(protect.find_sensitive, "protect"),
    "redact": ToolSpec(protect.redact, "protect", batchable=True, versioned=True),
    "sanitize": ToolSpec(protect.sanitize, "protect", batchable=True),
    # Automate & check
    "batch": ToolSpec(_batch, "automate", max_files=200, accepts=PDF_OR_IMAGE | set(OFFICE_KINDS)),
    "accessibility_check": ToolSpec(checks.accessibility_check, "automate"),
    "auto_tag": ToolSpec(checks.auto_tag, "automate", batchable=True),
    "preflight": ToolSpec(checks.preflight, "automate"),
}


def call_tool(name: str, ctx: ToolContext, params: dict) -> ToolOutput:
    """Call a tool function with validated keyword arguments."""
    spec = TOOLS.get(name)
    if not spec:
        raise ToolError(f"Unknown tool '{name}'.")
    sig = inspect.signature(spec.fn)
    allowed = [p for p in sig.parameters if p != "ctx"]
    unknown = set(params) - set(allowed)
    if unknown:
        raise ToolError(f"Unexpected option(s): {', '.join(sorted(unknown))}.")
    missing = [
        p for p, prm in sig.parameters.items() if p != "ctx" and prm.default is inspect.Parameter.empty and p not in params
    ]
    if missing:
        raise ToolError(f"Missing option(s): {', '.join(missing)}.")
    try:
        return spec.fn(ctx, **params)
    except ToolError:
        raise
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        raise ToolError(f"Invalid options for this tool ({exc.__class__.__name__}: {str(exc)[:150]}).") from exc


def catalog() -> list[dict]:
    return [
        {
            "name": name,
            "category": spec.category,
            "min_files": spec.min_files,
            "max_files": spec.max_files,
            "accepts": sorted(spec.accepts),
            "batchable": spec.batchable,
            "params": [p for p in inspect.signature(spec.fn).parameters if p != "ctx"],
        }
        for name, spec in TOOLS.items()
    ]
