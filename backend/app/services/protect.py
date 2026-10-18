"""Protection: passwords/permissions, redaction and sanitising."""
import re

import pikepdf
import pymupdf as fitz

from .common import ToolContext, ToolError, ToolOutput, hex_to_rgb, open_pdf, require_page, save_pdf, visible_to_unrotated

# ------------------------------------------------------------------ passwords


def add_password(
    ctx: ToolContext,
    user_password: str = "",
    owner_password: str = "",
    allow_print: bool = True,
    allow_copy: bool = False,
    allow_edit: bool = False,
) -> ToolOutput:
    """AES-256 encryption. user_password opens the file; owner_password lifts the restrictions."""
    if not user_password and not owner_password:
        raise ToolError("Enter a password to open the file, or an owner password for restrictions.")
    if len(user_password) > 127 or len(owner_password) > 127:
        raise ToolError("Passwords can be at most 127 characters.")
    owner = owner_password or user_password
    perms = pikepdf.Permissions(
        print_lowres=bool(allow_print),
        print_highres=bool(allow_print),
        extract=bool(allow_copy),
        accessibility=True,  # screen readers keep working
        modify_annotation=bool(allow_edit),
        modify_assembly=bool(allow_edit),
        modify_form=bool(allow_edit),
        modify_other=bool(allow_edit),
    )
    name = f"{ctx.stem}-protected.pdf"
    try:
        with pikepdf.open(ctx.inputs[0]) as pdf:
            pdf.save(ctx.out(name), encryption=pikepdf.Encryption(user=user_password, owner=owner, R=6, allow=perms))
    except pikepdf.PasswordError as exc:
        raise ToolError("This PDF already has a password. Remove it first.") from exc
    return ToolOutput(files=[(ctx.out(name), name)])


def remove_password(ctx: ToolContext, password: str = "") -> ToolOutput:
    name = f"{ctx.stem}-unlocked.pdf"
    try:
        with pikepdf.open(ctx.inputs[0], password=password) as pdf:
            pdf.save(ctx.out(name))
    except pikepdf.PasswordError as exc:
        raise ToolError("The password is incorrect.") from exc
    return ToolOutput(files=[(ctx.out(name), name)])


# ------------------------------------------------------------------ redaction

PRESETS = {
    "pan": r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
    "gstin": r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b",
    "aadhaar": r"\b[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}\b",
    "phone": r"(?:(?:\+|00)\d{1,3}[\s-]?)?(?:\(?\d{2,5}\)?[\s-]?)?\d{3,5}[\s-]?\d{4,5}\b",
    "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
}
PRESET_LABELS = {
    "pan": "PAN number",
    "gstin": "GSTIN",
    "aadhaar": "Aadhaar number",
    "phone": "Phone number",
    "email": "Email address",
}


def _matches(page: fitz.Page, terms: list[str], presets: list[str], regex: str, case_sensitive: bool) -> list[dict]:
    """Find rects for plain terms and regex patterns. Regex runs line by line on the text layer."""
    found = []
    flags = 0 if case_sensitive else fitz.TEXT_PRESERVE_WHITESPACE
    for term in terms:
        term = term.strip()
        if term:
            for r in page.search_for(term, flags=flags):
                found.append({"rect": r, "text": term, "kind": "term"})
    patterns = [(PRESETS[p], PRESET_LABELS[p]) for p in presets if p in PRESETS]
    if regex:
        try:
            re.compile(regex)
        except re.error as exc:
            raise ToolError(f"The custom pattern is not a valid regular expression: {exc}") from exc
        patterns.append((regex, "Custom pattern"))
    if patterns:
        text = page.get_text("text")
        for pat, label in patterns:
            for m in re.finditer(pat, text, 0 if case_sensitive or pat in PRESETS.values() else re.IGNORECASE):
                value = m.group(0).strip()
                if len(value) < 3:
                    continue
                # Matches may span a line break in the text layer; search each line separately.
                for piece in [v for v in value.split("\n") if v.strip()]:
                    for r in page.search_for(piece):
                        found.append({"rect": r, "text": value, "kind": label})
    # De-duplicate overlapping hits.
    unique: list[dict] = []
    for f in found:
        if not any(abs(f["rect"].x0 - u["rect"].x0) < 1 and abs(f["rect"].y0 - u["rect"].y0) < 1 for u in unique):
            unique.append(f)
    return unique


def find_sensitive(
    ctx: ToolContext, terms: list[str] | None = None, presets: list[str] | None = None, regex: str = "", case_sensitive: bool = False
) -> ToolOutput:
    """Preview what would be redacted."""
    doc = open_pdf(ctx.inputs[0])
    hits = []
    for page in doc:
        for m in _matches(page, terms or [], presets or [], regex, case_sensitive):
            r = m["rect"] * page.rotation_matrix if page.rotation else m["rect"]
            hits.append({"page": page.number, "bbox": [round(v, 2) for v in fitz.Rect(r).normalize()], "text": m["text"], "kind": m["kind"]})
    return ToolOutput(data={"matches": hits[:5000], "count": len(hits)})


def redact(
    ctx: ToolContext,
    areas: list[dict] | None = None,
    terms: list[str] | None = None,
    presets: list[str] | None = None,
    regex: str = "",
    case_sensitive: bool = False,
    fill: str = "#000000",
    label: str = "",
    remove_metadata: bool = True,
) -> ToolOutput:
    """Permanently remove text, images and drawings under the redaction areas."""
    doc = open_pdf(ctx.inputs[0])
    color = hex_to_rgb(fill)
    count = 0
    for a in areas or []:
        page = require_page(doc, int(a.get("page", 0)))
        page.add_redact_annot(visible_to_unrotated(page, a["rect"]), text=label or None, fill=color, fontsize=8)
        count += 1
    if terms or presets or regex:
        for page in doc:
            for m in _matches(page, terms or [], presets or [], regex, case_sensitive):
                page.add_redact_annot(m["rect"], text=label or None, fill=color, fontsize=8)
                count += 1
    if count == 0:
        raise ToolError("Nothing to redact. Draw areas or enter search terms / presets.")
    for n, page in enumerate(doc):
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
        ctx.progress(int((n + 1) * 90 / doc.page_count), "Redacting")
    if remove_metadata:
        doc.set_metadata({})
        doc.del_xml_metadata()
    name = f"{ctx.stem}-redacted.pdf"
    return ToolOutput(files=[(save_pdf(doc, ctx.out(name)), name)], data={"redactions": count})


# ------------------------------------------------------------------ sanitise


def _strip_javascript(path, out) -> int:
    """Remove document-level JavaScript, open actions and additional actions with pikepdf."""
    removed = 0
    with pikepdf.open(path) as pdf:
        root = pdf.Root
        names = root.get("/Names")
        if names is not None and "/JavaScript" in names:
            del names["/JavaScript"]
            removed += 1
        for key in ("/OpenAction", "/AA"):
            if key in root:
                del root[key]
                removed += 1
        for page in pdf.pages:
            if "/AA" in page.obj:
                del page.obj["/AA"]
                removed += 1
            for annot in page.obj.get("/Annots", []) or []:
                for key in ("/AA",):
                    if key in annot:
                        del annot[key]
                        removed += 1
                action = annot.get("/A")
                if action is not None and action.get("/S") in (pikepdf.Name.JavaScript, pikepdf.Name.Launch):
                    del annot["/A"]
                    removed += 1
        if "/AcroForm" in root:
            for field in root.AcroForm.get("/Fields", []) or []:
                if "/AA" in field:
                    del field["/AA"]
                    removed += 1
        pdf.save(out)
    return removed


def sanitize(
    ctx: ToolContext,
    metadata: bool = True,
    comments: bool = True,
    attachments: bool = True,
    javascript: bool = True,
    hidden_text: bool = True,
    links: bool = False,
    thumbnails: bool = True,
) -> ToolOutput:
    doc = open_pdf(ctx.inputs[0])
    if comments:
        for page in doc:
            for annot in list(page.annots()):
                if annot.type[0] not in (fitz.PDF_ANNOT_WIDGET, fitz.PDF_ANNOT_LINK):
                    page.delete_annot(annot)
    doc.scrub(
        attached_files=attachments,
        clean_pages=True,
        embedded_files=attachments,
        hidden_text=hidden_text,
        javascript=javascript,
        metadata=metadata,
        redactions=True,
        redact_images=0,
        remove_links=links,
        reset_fields=False,
        reset_responses=comments,
        thumbnails=thumbnails,
        xml_metadata=metadata,
    )
    mid = ctx.workdir / "scrubbed.pdf"
    save_pdf(doc, mid)
    name = f"{ctx.stem}-sanitized.pdf"
    removed_js = _strip_javascript(mid, ctx.out(name)) if javascript else 0
    if not javascript:
        mid.replace(ctx.out(name))
    return ToolOutput(files=[(ctx.out(name), name)], data={"javascript_entries_removed": removed_js})

