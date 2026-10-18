"""Forms: fill existing fields, create new fields and auto-detect fields in a flat PDF."""
import re

import pymupdf as fitz

from .common import ToolContext, ToolError, ToolOutput, open_pdf, require_page, save_pdf, visible_to_unrotated

FIELD_TYPES = {
    "text": fitz.PDF_WIDGET_TYPE_TEXT,
    "date": fitz.PDF_WIDGET_TYPE_TEXT,
    "checkbox": fitz.PDF_WIDGET_TYPE_CHECKBOX,
    "radio": fitz.PDF_WIDGET_TYPE_RADIOBUTTON,
    "dropdown": fitz.PDF_WIDGET_TYPE_COMBOBOX,
    "listbox": fitz.PDF_WIDGET_TYPE_LISTBOX,
}
DATE_FORMAT = "dd/mm/yyyy"


def _truthy(v) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on", "checked", "x")


def fill_form(ctx: ToolContext, values: dict, flatten: bool = False) -> ToolOutput:
    doc = open_pdf(ctx.inputs[0])
    if not doc.is_form_pdf:
        raise ToolError("This PDF has no form fields. Use Prepare Form to create them.")
    filled = 0
    for page in doc:
        for w in page.widgets():
            if w.field_name not in values:
                continue
            v = values[w.field_name]
            if w.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                w.field_value = _truthy(v)
            elif w.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                # For radio groups the value is the chosen button's on-state name.
                w.field_value = str(v) == str(w.on_state())
            else:
                w.field_value = "" if v is None else str(v)
            w.update()
            filled += 1
    if flatten:
        doc.bake(annots=False, widgets=True)
    name = f"{ctx.stem}-filled.pdf"
    return ToolOutput(files=[(save_pdf(doc, ctx.out(name)), name)], data={"filled": filled})


def _unique(doc: fitz.Document, base: str) -> str:
    existing = {w.field_name for p in doc for w in p.widgets()}
    base = re.sub(r"[^A-Za-z0-9_]+", "_", base).strip("_")[:40] or "field"
    name, n = base, 1
    while name in existing:
        n += 1
        name = f"{base}_{n}"
    return name


def _add_widget(doc: fitz.Document, page: fitz.Page, spec: dict) -> str:
    ftype = spec.get("type", "text")
    if ftype not in FIELD_TYPES:
        raise ToolError(f"Unknown field type '{ftype}'.")
    w = fitz.Widget()
    w.field_type = FIELD_TYPES[ftype]
    w.rect = visible_to_unrotated(page, spec["rect"]) if not spec.get("_raw") else fitz.Rect(spec["rect"])
    w.field_name = spec.get("name") if ftype == "radio" and spec.get("name") else _unique(doc, spec.get("name") or ftype)
    w.field_label = spec.get("label", "")
    w.text_fontsize = float(spec.get("font_size", 0))  # 0 = auto size
    w.border_color = (0.3, 0.4, 0.8)
    w.border_width = 0.8
    w.fill_color = (0.93, 0.95, 1.0)
    if spec.get("required"):
        w.field_flags |= fitz.PDF_FIELD_IS_REQUIRED
    if ftype in ("text", "date"):
        w.field_value = str(spec.get("default", ""))
        if spec.get("multiline"):
            w.field_flags |= fitz.PDF_TX_FIELD_IS_MULTILINE
        if ftype == "date":
            w.script_format = f'AFDate_FormatEx("{DATE_FORMAT}");'
            w.script_change = f'AFDate_KeystrokeEx("{DATE_FORMAT}");'
            w.field_label = w.field_label or f"Date ({DATE_FORMAT})"
    elif ftype == "checkbox":
        w.field_value = bool(spec.get("default"))
    elif ftype == "radio":
        w.button_caption = spec.get("value", "Choice")
        w.field_value = bool(spec.get("default"))
    else:
        options = [str(o) for o in spec.get("options", []) if str(o).strip()]
        if not options:
            raise ToolError("Dropdown and list fields need at least one option.")
        w.choice_values = options
        w.field_value = spec.get("default") or options[0]
    page.add_widget(w)
    return w.field_name


def add_fields(ctx: ToolContext, fields: list[dict]) -> ToolOutput:
    """Create fields: [{page, rect, type, name, options, default, required, multiline, value}]."""
    if not fields:
        raise ToolError("Draw at least one field on the page.")
    doc = open_pdf(ctx.inputs[0])
    names = [_add_widget(doc, require_page(doc, int(f.get("page", 0))), f) for f in fields]
    name = f"{ctx.stem}-form.pdf"
    return ToolOutput(files=[(save_pdf(doc, ctx.out(name)), name)], data={"created": names})


def delete_field(ctx: ToolContext, name: str) -> ToolOutput:
    doc = open_pdf(ctx.inputs[0])
    found = False
    for page in doc:
        for w in list(page.widgets()):
            if w.field_name == name:
                page.delete_widget(w)
                found = True
    if not found:
        raise ToolError("Field not found.")
    out = f"{ctx.stem}.pdf"
    return ToolOutput(files=[(save_pdf(doc, ctx.out(out)), out)])


# ----------------------------------------------------------------- auto-detect ("Prepare Form")

CHECKBOX_CHARS = "☐□❏❑■▢◻⬜"
LABEL_RE = re.compile(r"([A-Za-z][A-Za-z0-9 ./&()'-]{1,40})\s*[:：]?\s*$")


def _label_left_of(words, rect: fitz.Rect) -> str:
    """Find the words on the same line immediately to the left of a field."""
    same_line = [w for w in words if abs(((w[1] + w[3]) / 2) - ((rect.y0 + rect.y1) / 2)) < max(8, rect.height) and w[2] <= rect.x0 + 2]
    same_line.sort(key=lambda w: w[0])
    text = " ".join(w[4] for w in same_line[-5:])
    text = text.replace("_", "").strip()
    m = LABEL_RE.search(text)
    return m.group(1).strip() if m else ""


def _label_above(words, rect: fitz.Rect) -> str:
    above = [w for w in words if 0 < rect.y0 - w[3] < 16 and w[0] < rect.x1 and w[2] > rect.x0]
    above.sort(key=lambda w: w[0])
    return " ".join(w[4] for w in above)[:40]


def detect_fields(page: fitz.Page) -> list[dict]:
    """Heuristics: underscore runs, checkbox glyphs, empty drawn boxes and signature/answer lines."""
    words = page.get_text("words")
    found: list[dict] = []
    occupied: list[fitz.Rect] = []

    def add(rect: fitz.Rect, ftype: str, label: str):
        if rect.width < 6 or rect.height < 6:
            return
        if any(rect.intersects(o) and (rect & o).get_area() > 0.4 * rect.get_area() for o in occupied):
            return
        occupied.append(rect)
        name = label or ftype
        if ftype == "text" and re.search(r"\b(date|dob|d\.o\.b)\b", label, re.I):
            ftype = "date"
        found.append({"page": page.number, "rect": list(rect), "type": ftype, "name": name, "_raw": True})

    # 1) Runs of underscores in the text layer ("Name: ________").
    for x0, y0, x1, y1, w, *_ in words:
        m = re.search(r"_{4,}", w)
        if m:
            total = len(w) or 1
            fx0 = x0 + (x1 - x0) * m.start() / total
            fx1 = x0 + (x1 - x0) * m.end() / total
            r = fitz.Rect(fx0, y1 - 14, fx1, y1 + 1)
            label = w[: m.start()].strip(":： ") or _label_left_of(words, r)
            add(r, "text", label)

    # 2) Checkbox glyphs.
    for x0, y0, x1, y1, w, *_ in words:
        if w and w[0] in CHECKBOX_CHARS:
            side = max(8, min(14, y1 - y0))
            r = fitz.Rect(x0, (y0 + y1) / 2 - side / 2, x0 + side, (y0 + y1) / 2 + side / 2)
            following = [ww for ww in words if ww[0] >= x1 and abs(ww[1] - y0) < 4][:3]
            add(r, "checkbox", " ".join(ww[4] for ww in following) or w[1:].strip())

    # 3) Vector drawings: empty boxes and horizontal lines.
    text_rects = [fitz.Rect(w[:4]) for w in words]
    for d in page.get_drawings():
        for item in d["items"]:
            if item[0] == "re":
                r = fitz.Rect(item[1])
                empty = not any(r.contains(t) or (r & t).get_area() > 0.5 * t.get_area() for t in text_rects if t.get_area() > 0)
                if not empty:
                    continue
                if 6 <= r.width <= 20 and 6 <= r.height <= 20 and abs(r.width - r.height) < 4:
                    following = [ww for ww in words if ww[0] >= r.x1 and abs(((ww[1] + ww[3]) / 2) - ((r.y0 + r.y1) / 2)) < 6][:3]
                    add(r, "checkbox", " ".join(ww[4] for ww in following))
                elif r.width >= 50 and 12 <= r.height <= 40:
                    add(r, "text", _label_left_of(words, r) or _label_above(words, r))
            elif item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) < 1 and abs(p2.x - p1.x) >= 60:
                    x0, x1 = sorted((p1.x, p2.x))
                    r = fitz.Rect(x0, p1.y - 14, x1, p1.y - 0.5)
                    if any(r.intersects(t) for t in text_rects):
                        continue  # a line under existing text is an underline, not a blank
                    label = _label_left_of(words, r) or _label_above(words, fitz.Rect(x0, p1.y + 14, x1, p1.y + 30))
                    add(r, "text", label)
    return found


def prepare_form(ctx: ToolContext, pages: str = "all") -> ToolOutput:
    from .common import parse_pages

    doc = open_pdf(ctx.inputs[0])
    created = []
    targets = parse_pages(pages, doc.page_count)
    for n, i in enumerate(targets):
        page = doc[i]
        for spec in detect_fields(page):
            created.append({"page": i, "name": _add_widget(doc, page, spec), "type": spec["type"]})
        ctx.progress(int((n + 1) * 95 / len(targets)), f"Scanning page {i + 1}")
    name = f"{ctx.stem}-fillable.pdf"
    return ToolOutput(files=[(save_pdf(doc, ctx.out(name)), name)], data={"created": created, "count": len(created)})
