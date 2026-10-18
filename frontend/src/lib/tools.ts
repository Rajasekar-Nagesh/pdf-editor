// Catalog of every tool shown on the home screen and in the editor's left toolbar.
// "form" tools are driven by the field definitions below; other panels are custom components.
import {
  Bookmark, CheckSquare, Columns2, Combine, Crop, Droplets, Eraser, Eye, FileCheck2, FileCode2, FileImage,
  FileInput, FileOutput, FileSpreadsheet, FileText, FileType2, Fingerprint, FormInput, Globe, Hash,
  Highlighter, Image, Layers, LayoutGrid, Link2, ListOrdered, Lock, LockOpen, MessageSquare, Minimize2,
  PenLine, Presentation, Printer, RotateCw, Ruler, ScanText, Scissors, Send, ShieldCheck, ShieldOff, Sparkles,
  Table, Type, Wand2, Workflow, Accessibility, FilePlus2, FileX2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type FieldType =
  | "text" | "textarea" | "number" | "select" | "checkbox" | "color" | "pages" | "image" | "password" | "langs" | "multiselect";

export interface Field {
  key: string;
  label: string;
  type: FieldType;
  default?: any;
  options?: { value: string; label: string }[];
  help?: string;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
  showIf?: (p: Record<string, any>) => boolean;
}

export type InputKind = "pdf" | "pdfs" | "images" | "office" | "none" | "pdf-or-image" | "batch" | "two-pdfs";

export interface ToolDef {
  id: string;
  title: string;
  short?: string; // label under the icon in the editor's tool bar
  desc: string;
  category: string;
  icon: LucideIcon;
  backend?: string; // backend tool name for "form" tools
  input: InputKind;
  panel: string; // "form" or a custom panel name
  fields?: Field[];
  login?: boolean; // requires an account
  ai?: boolean;
  runLabel?: string;
}

export const CATEGORIES = [
  "View & organize", "Edit", "Review", "Forms & signatures", "Convert", "Scan & OCR", "Protect", "Automate & check", "AI",
];

const PAGES: Field = { key: "pages", label: "Pages", type: "pages", default: "all", placeholder: "all, 1-3, 5, odd, even" };
const POSITION: Field = {
  key: "position", label: "Position", type: "select", default: "bottom-center",
  options: ["top-left", "top-center", "top-right", "bottom-left", "bottom-center", "bottom-right"].map((v) => ({ value: v, label: v.replace("-", " ") })),
};
const LANGS: Field = { key: "languages", label: "Document languages", type: "langs", default: ["eng"] };

export const TOOLS: ToolDef[] = [
  // ---------------------------------------------------------------- View & organize
  { id: "view", title: "View PDF", desc: "Open, zoom, search and browse pages.", category: "View & organize", icon: Eye, input: "pdf", panel: "view" },
  { id: "organize", title: "Organize pages", desc: "Drag to reorder, rotate, delete, insert blank pages - in your browser.", category: "View & organize", icon: LayoutGrid, input: "pdf", panel: "organize" },
  { id: "rotate", title: "Rotate pages", desc: "Rotate some or all pages.", category: "View & organize", icon: RotateCw, input: "pdf", panel: "form", backend: "rotate",
    fields: [PAGES, { key: "angle", label: "Angle", type: "select", default: "90", options: [{ value: "90", label: "90° clockwise" }, { value: "180", label: "180°" }, { value: "270", label: "90° counter-clockwise" }] }] },
  { id: "delete_pages", short: "Delete", title: "Delete pages", desc: "Remove pages you do not need.", category: "View & organize", icon: FileX2, input: "pdf", panel: "form", backend: "delete_pages",
    fields: [{ ...PAGES, default: "" , placeholder: "e.g. 2, 5-7" }] },
  { id: "extract_pages", title: "Extract pages", desc: "Save selected pages as a new PDF.", category: "View & organize", icon: FileOutput, input: "pdf", panel: "form", backend: "extract_pages",
    fields: [{ ...PAGES, default: "1" }] },
  { id: "insert_blank", short: "Insert", title: "Insert blank page", desc: "Add empty pages anywhere.", category: "View & organize", icon: FilePlus2, input: "pdf", panel: "form", backend: "insert_blank",
    fields: [
      { key: "after", label: "Insert after page (0 = at start)", type: "number", default: 1, min: 0 },
      { key: "count", label: "Number of pages", type: "number", default: 1, min: 1, max: 500 },
      { key: "size", label: "Page size", type: "select", default: "same", options: [{ value: "same", label: "Same as neighbour" }, { value: "a4", label: "A4" }, { value: "letter", label: "Letter" }, { value: "legal", label: "Legal" }] },
    ] },
  { id: "crop", title: "Crop pages", desc: "Trim margins or draw a crop box.", category: "View & organize", icon: Crop, input: "pdf", panel: "crop" },
  { id: "merge", title: "Merge PDFs", desc: "Combine multiple PDFs and images into one.", category: "View & organize", icon: Combine, input: "pdfs", panel: "form", backend: "merge",
    fields: [{ key: "name", label: "Output file name", type: "text", default: "merged.pdf" }], runLabel: "Merge" },
  { id: "split", title: "Split PDF", desc: "Split by page ranges or every N pages.", category: "View & organize", icon: Scissors, input: "pdf", panel: "form", backend: "split",
    fields: [
      { key: "mode", label: "Split mode", type: "select", default: "every", options: [{ value: "every", label: "Every N pages" }, { value: "ranges", label: "By page ranges" }] },
      { key: "every", label: "Pages per file", type: "number", default: 1, min: 1, showIf: (p) => p.mode === "every" },
      { key: "ranges", label: "Ranges (one file each)", type: "text", default: "1-2; 3-", placeholder: "1-3; 4-6; 7-", showIf: (p) => p.mode === "ranges" },
    ], runLabel: "Split" },

  // ---------------------------------------------------------------- Edit
  { id: "edit_text", short: "Text", title: "Edit text", desc: "Click existing text to change it, or add new text.", category: "Edit", icon: Type, input: "pdf", panel: "edit-text" },
  { id: "images", short: "Images", title: "Edit images", desc: "Add, replace, move, resize, crop or delete images.", category: "Edit", icon: Image, input: "pdf", panel: "images" },
  { id: "links", short: "Links", title: "Links, bookmarks & attachments", desc: "Create and edit hyperlinks, bookmarks and file attachments.", category: "Edit", icon: Link2, input: "pdf", panel: "links" },
  { id: "flatten", title: "Flatten", desc: "Make annotations and form fields part of the page.", category: "Edit", icon: Layers, input: "pdf", panel: "form", backend: "flatten",
    fields: [{ key: "annotations", label: "Flatten annotations", type: "checkbox", default: true }, { key: "forms", label: "Flatten form fields", type: "checkbox", default: true }] },
  { id: "metadata", short: "Info", title: "Edit metadata", desc: "Title, author, subject and keywords.", category: "Edit", icon: FileText, input: "pdf", panel: "metadata" },
  { id: "watermark", title: "Watermark", desc: "Add a text or image watermark.", category: "Edit", icon: Droplets, input: "pdf", panel: "form", backend: "watermark",
    fields: [
      { key: "text", label: "Text", type: "text", default: "CONFIDENTIAL" },
      { key: "image_file_id", label: "Or an image", type: "image" },
      { key: "layout", label: "Layout", type: "select", default: "center", options: [{ value: "center", label: "Centered" }, { value: "tile", label: "Tiled" }] },
      { key: "opacity", label: "Opacity", type: "number", default: 0.25, min: 0.05, max: 1, step: 0.05 },
      { key: "rotation", label: "Rotation (degrees)", type: "number", default: 45 },
      { key: "size", label: "Font size", type: "number", default: 60 },
      { key: "color", label: "Color", type: "color", default: "#ff0000" },
      { key: "behind", label: "Place behind content", type: "checkbox", default: false },
      PAGES,
    ] },
  { id: "page_numbers", short: "Numbers", title: "Page numbers", desc: "Number your pages.", category: "Edit", icon: ListOrdered, input: "pdf", panel: "form", backend: "page_numbers",
    fields: [
      { key: "template", label: "Format", type: "text", default: "Page {n} of {total}", help: "Use {n}, {total}, {date}, {filename}" },
      POSITION, { key: "start", label: "Start at", type: "number", default: 1 }, { key: "size", label: "Font size", type: "number", default: 10 },
      { key: "color", label: "Color", type: "color", default: "#000000" }, PAGES,
    ] },
  { id: "header_footer", short: "Header", title: "Header & footer", desc: "Add text to the top and bottom of pages.", category: "Edit", icon: FileType2, input: "pdf", panel: "form", backend: "header_footer",
    fields: [
      { key: "header_left", label: "Header left", type: "text", default: "" }, { key: "header_center", label: "Header center", type: "text", default: "" },
      { key: "header_right", label: "Header right", type: "text", default: "{date}" }, { key: "footer_left", label: "Footer left", type: "text", default: "{filename}" },
      { key: "footer_center", label: "Footer center", type: "text", default: "" }, { key: "footer_right", label: "Footer right", type: "text", default: "Page {page} of {total}" },
      { key: "size", label: "Font size", type: "number", default: 9 }, { key: "color", label: "Color", type: "color", default: "#333333" }, PAGES,
    ] },
  { id: "bates", title: "Bates numbering", desc: "Legal numbering across one or more files.", category: "Edit", icon: Hash, input: "pdfs", panel: "form", backend: "bates",
    fields: [
      { key: "prefix", label: "Prefix", type: "text", default: "ABC" }, { key: "suffix", label: "Suffix", type: "text", default: "" },
      { key: "start", label: "Start number", type: "number", default: 1, min: 0 }, { key: "digits", label: "Digits", type: "number", default: 6, min: 1, max: 12 },
      { ...POSITION, default: "bottom-right" }, { key: "size", label: "Font size", type: "number", default: 9 },
    ], runLabel: "Apply Bates numbers" },

  // ---------------------------------------------------------------- Review
  { id: "annotate", title: "Annotate", desc: "Highlight, underline, notes, drawing, shapes and text boxes.", category: "Review", icon: Highlighter, input: "pdf", panel: "annotate" },
  { id: "compare", title: "Compare PDFs", desc: "See text differences between two versions side by side.", category: "Review", icon: Columns2, input: "two-pdfs", panel: "compare" },
  { id: "share_review", short: "Share", title: "Share for review", desc: "Send a link - reviewers comment in the browser, no account needed.", category: "Review", icon: MessageSquare, input: "pdf", panel: "share", login: true },

  // ---------------------------------------------------------------- Forms & signatures
  { id: "forms", short: "Forms", title: "Fill & create forms", desc: "Fill fields or add text, checkbox, radio, dropdown and date fields.", category: "Forms & signatures", icon: FormInput, input: "pdf", panel: "forms" },
  { id: "prepare_form", short: "Prepare", title: "Prepare form", desc: "Auto-detect blanks and boxes and make them fillable.", category: "Forms & signatures", icon: Wand2, input: "pdf", panel: "form", backend: "prepare_form", fields: [PAGES], runLabel: "Detect fields" },
  { id: "sign", title: "Sign", desc: "Draw, type or upload your signature and place it.", category: "Forms & signatures", icon: PenLine, input: "pdf", panel: "sign" },
  { id: "digital_sign", short: "Digital", title: "Digital signature", desc: "Sign with a .pfx/.p12 certificate or USB DSC token; validate signatures.", category: "Forms & signatures", icon: Fingerprint, input: "pdf", panel: "digital" },
  { id: "send_signature", short: "Send", title: "Send for signature", desc: "Invite signers by email, in order, with an audit trail.", category: "Forms & signatures", icon: Send, input: "pdf", panel: "send", login: true },

  // ---------------------------------------------------------------- Convert
  { id: "pdf_to_word", short: "Word", title: "PDF to Word", desc: "Editable .docx.", category: "Convert", icon: FileText, input: "pdf", panel: "form", backend: "pdf_to_word", runLabel: "Convert" },
  { id: "pdf_to_excel", short: "Excel", title: "PDF to Excel", desc: "Tables to spreadsheet sheets.", category: "Convert", icon: FileSpreadsheet, input: "pdf", panel: "form", backend: "pdf_to_excel", fields: [PAGES], runLabel: "Convert" },
  { id: "pdf_to_pptx", short: "PPT", title: "PDF to PowerPoint", desc: "One slide per page.", category: "Convert", icon: Presentation, input: "pdf", panel: "form", backend: "pdf_to_pptx", runLabel: "Convert" },
  { id: "pdf_to_images", short: "Images", title: "PDF to images", desc: "PNG or JPG per page.", category: "Convert", icon: FileImage, input: "pdf", panel: "form", backend: "pdf_to_images",
    fields: [{ key: "fmt", label: "Format", type: "select", default: "png", options: [{ value: "png", label: "PNG" }, { value: "jpg", label: "JPG" }] }, { key: "dpi", label: "Resolution (DPI)", type: "number", default: 150, min: 36, max: 600 }, PAGES], runLabel: "Convert" },
  { id: "pdf_to_html", short: "HTML", title: "PDF to HTML", desc: "A web page version.", category: "Convert", icon: FileCode2, input: "pdf", panel: "form", backend: "pdf_to_html", runLabel: "Convert" },
  { id: "pdf_to_text", short: "Text", title: "PDF to text", desc: "Plain text.", category: "Convert", icon: FileText, input: "pdf", panel: "form", backend: "pdf_to_text", runLabel: "Convert" },
  { id: "office_to_pdf", short: "Office", title: "Office to PDF", desc: "Word, Excel and PowerPoint to PDF.", category: "Convert", icon: FileInput, input: "office", panel: "form", backend: "office_to_pdf", runLabel: "Convert" },
  { id: "images_to_pdf", short: "Img→PDF", title: "Images to PDF", desc: "JPG, PNG and more into one PDF.", category: "Convert", icon: FileImage, input: "images", panel: "form", backend: "images_to_pdf",
    fields: [{ key: "page_size", label: "Page size", type: "select", default: "fit", options: [{ value: "fit", label: "Fit image" }, { value: "a4", label: "A4" }, { value: "letter", label: "Letter" }] }, { key: "margin", label: "Margin (pt)", type: "number", default: 0, min: 0 }, { key: "name", label: "File name", type: "text", default: "images.pdf" }], runLabel: "Convert" },
  { id: "url_to_pdf", short: "Web", title: "Web page to PDF", desc: "Save any public web page as PDF.", category: "Convert", icon: Globe, input: "none", panel: "form", backend: "url_to_pdf",
    fields: [{ key: "url", label: "Web address", type: "text", default: "https://", placeholder: "https://example.com" }, { key: "page_size", label: "Paper", type: "select", default: "A4", options: ["A4", "Letter", "Legal", "A3"].map((v) => ({ value: v, label: v })) }, { key: "landscape", label: "Landscape", type: "checkbox", default: false }], runLabel: "Convert" },
  { id: "to_pdfa", short: "PDF/A", title: "PDF/A-2b", desc: "Archive format, validated with veraPDF.", category: "Convert", icon: FileCheck2, input: "pdf", panel: "form", backend: "to_pdfa", fields: [{ key: "validate", label: "Validate with veraPDF", type: "checkbox", default: true }], runLabel: "Convert" },
  { id: "validate_pdfa", short: "Check A", title: "Validate PDF/A", desc: "Check PDF/A compliance with veraPDF.", category: "Convert", icon: ShieldCheck, input: "pdf", panel: "form", backend: "validate_pdfa",
    fields: [{ key: "flavour", label: "Level", type: "select", default: "2b", options: ["1b", "2b", "2u", "3b"].map((v) => ({ value: v, label: `PDF/A-${v.toUpperCase()}` })) }], runLabel: "Validate" },
  { id: "compress", title: "Compress", desc: "Shrink file size, see before and after.", category: "Convert", icon: Minimize2, input: "pdf", panel: "form", backend: "compress",
    fields: [{ key: "quality", label: "Quality", type: "select", default: "medium", options: [{ value: "low", label: "Low quality - smallest file" }, { value: "medium", label: "Medium - good balance" }, { value: "high", label: "High quality - for print" }] }], runLabel: "Compress" },

  // ---------------------------------------------------------------- Scan & OCR
  { id: "ocr", title: "OCR (searchable PDF)", desc: "Recognise text in scans: English, Tamil, Hindi.", category: "Scan & OCR", icon: ScanText, input: "pdf-or-image", panel: "form", backend: "ocr",
    fields: [LANGS, { key: "mode", label: "Pages that already have text", type: "select", default: "skip", options: [{ value: "skip", label: "Skip them" }, { value: "redo", label: "Redo their OCR" }, { value: "force", label: "Rasterise and OCR everything" }] }, { key: "deskew", label: "Straighten crooked scans", type: "checkbox", default: true }], runLabel: "Run OCR" },
  { id: "scanned_tables_to_excel", short: "Bill→XLS", title: "Scanned bill to Excel", desc: "Invoice and bill tables from scans into Excel.", category: "Scan & OCR", icon: Table, input: "pdf-or-image", panel: "form", backend: "scanned_tables_to_excel", fields: [LANGS], runLabel: "Extract tables" },

  // ---------------------------------------------------------------- Protect
  { id: "add_password", short: "Lock", title: "Add password", desc: "Encrypt and restrict printing, copying, editing.", category: "Protect", icon: Lock, input: "pdf", panel: "form", backend: "add_password",
    fields: [
      { key: "user_password", label: "Password to open", type: "password", default: "" },
      { key: "owner_password", label: "Permissions password (optional)", type: "password", default: "" },
      { key: "allow_print", label: "Allow printing", type: "checkbox", default: true },
      { key: "allow_copy", label: "Allow copying text", type: "checkbox", default: false },
      { key: "allow_edit", label: "Allow editing", type: "checkbox", default: false },
    ], runLabel: "Protect" },
  { id: "remove_password", short: "Unlock", title: "Remove password", desc: "Unlock a PDF you have the password for.", category: "Protect", icon: LockOpen, input: "pdf", panel: "form", backend: "remove_password", fields: [{ key: "password", label: "Current password", type: "password", default: "" }], runLabel: "Unlock" },
  { id: "redact", title: "Redact", desc: "Permanently remove areas, terms, PAN, GSTIN, Aadhaar, phones, emails.", category: "Protect", icon: Eraser, input: "pdf", panel: "redact" },
  { id: "sanitize", title: "Sanitize", desc: "Remove hidden text, metadata, comments, attachments, JavaScript.", category: "Protect", icon: ShieldOff, input: "pdf", panel: "form", backend: "sanitize",
    fields: [
      { key: "metadata", label: "Metadata", type: "checkbox", default: true }, { key: "comments", label: "Comments", type: "checkbox", default: true },
      { key: "attachments", label: "Attachments", type: "checkbox", default: true }, { key: "javascript", label: "JavaScript", type: "checkbox", default: true },
      { key: "hidden_text", label: "Hidden text", type: "checkbox", default: true }, { key: "links", label: "Links", type: "checkbox", default: false },
    ], runLabel: "Sanitize" },

  // ---------------------------------------------------------------- Automate & check
  { id: "batch", title: "Batch actions", desc: "Build reusable steps (e.g. OCR + compress + watermark) and run them on many files.", category: "Automate & check", icon: Workflow, input: "batch", panel: "batch" },
  { id: "accessibility_check", short: "Access", title: "Accessibility check", desc: "Tags, alt text, language, reading order.", category: "Automate & check", icon: Accessibility, input: "pdf", panel: "form", backend: "accessibility_check", runLabel: "Run check" },
  { id: "auto_tag", short: "Tag", title: "Auto-tag", desc: "Add structure tags, language, title and bookmarks.", category: "Automate & check", icon: Bookmark, input: "pdf", panel: "form", backend: "auto_tag",
    fields: [{ key: "language", label: "Language code", type: "text", default: "en-US", placeholder: "en-US, ta-IN, hi-IN" }, { key: "title", label: "Document title", type: "text", default: "" }, { key: "alt_text", label: "Alt text for images", type: "text", default: "" }, { key: "add_bookmarks", label: "Generate bookmarks from headings", type: "checkbox", default: true }], runLabel: "Auto-tag" },
  { id: "preflight", title: "Print preflight", desc: "Fonts embedded, image resolution, colour spaces.", category: "Automate & check", icon: Printer, input: "pdf", panel: "form", backend: "preflight",
    fields: [{ key: "min_dpi", label: "Minimum image DPI", type: "number", default: 300 }, { key: "require_cmyk", label: "Print job is CMYK", type: "checkbox", default: false }], runLabel: "Run preflight" },
  { id: "measure", title: "Measure", desc: "Distances and areas with a custom scale.", category: "Automate & check", icon: Ruler, input: "pdf", panel: "measure" },
  { id: "validate_signatures", short: "Verify", title: "Validate signatures", desc: "Check digital signatures in a PDF.", category: "Automate & check", icon: CheckSquare, input: "pdf", panel: "form", backend: "validate_signatures", fields: [{ key: "check_revocation", label: "Check revocation online (slower)", type: "checkbox", default: false }], runLabel: "Validate" },

  // ---------------------------------------------------------------- AI
  { id: "ai", short: "AI", title: "AI assistant", desc: "Chat with your PDF and get summaries with page citations.", category: "AI", icon: Sparkles, input: "pdf", panel: "ai", ai: true },
];

export const TOOL_BY_ID = Object.fromEntries(TOOLS.map((t) => [t.id, t]));

// Batch actions can only use tools that take one PDF and return one PDF.
export const BATCHABLE = ["ocr", "compress", "watermark", "page_numbers", "header_footer", "flatten", "rotate", "sanitize", "to_pdfa", "auto_tag", "bates", "redact", "crop", "set_metadata"];

export const REDACT_PRESETS = [
  { value: "pan", label: "PAN" },
  { value: "gstin", label: "GSTIN" },
  { value: "aadhaar", label: "Aadhaar" },
  { value: "phone", label: "Phone numbers" },
  { value: "email", label: "Email addresses" },
];

export const LANGUAGES = [
  { value: "eng", label: "English" },
  { value: "tam", label: "Tamil" },
  { value: "hin", label: "Hindi" },
];

