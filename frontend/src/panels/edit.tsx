// Edit panels: text, images, links / bookmarks / attachments.
import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { inspect } from "../lib/api";
import { useApp } from "../lib/app-context";
import { Shape } from "../components/PdfViewer";
import { AssetPicker, ACCEPT, Spinner } from "../components/ui";
import { useEditor, useViewer } from "../pages/Editor";

const MAX_AUTO_PAGES = 40;

/** Load a per-page inspection (spans, images, links, ...) for every page of the current version. */
export function usePerPage<T>(what: string) {
  const { file, pages } = useEditor();
  const [data, setData] = useState<Record<number, T[]>>({});
  const [loading, setLoading] = useState(false);
  const [onlyPage, setOnlyPage] = useState(0);
  const many = pages.length > MAX_AUTO_PAGES;

  useEffect(() => {
    if (!file || !pages.length) return;
    let cancelled = false;
    setLoading(true);
    const list = many ? [onlyPage] : pages.map((_, i) => i);
    Promise.all(list.map((p) => inspect<T[]>(file.id, what, p).then((r) => [p, r] as const)))
      .then((res) => !cancelled && setData(Object.fromEntries(res)))
      .catch(() => undefined)
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [file?.id, pages.length, what, onlyPage, many]); // eslint-disable-line react-hooks/exhaustive-deps

  const pagePicker = many ? (
    <div className="mb-3">
      <label className="label">Page to edit (large document)</label>
      <input type="number" min={1} max={pages.length} className="input" value={onlyPage + 1} onChange={(e) => setOnlyPage(Math.max(0, Math.min(pages.length - 1, Number(e.target.value) - 1)))} />
    </div>
  ) : null;
  return { data, loading, pagePicker };
}

interface Span {
  text: string;
  bbox: number[];
  origin: number[];
  font: string;
  size: number;
  color: string;
  bold: boolean;
  italic: boolean;
}

export function EditTextPanel() {
  const { run, busy } = useEditor();
  const { data: spans, loading, pagePicker } = usePerPage<Span>("spans");
  const [tab, setTab] = useState<"edit" | "add">("edit");
  const [sel, setSel] = useState<{ page: number; span: Span } | null>(null);
  const [text, setText] = useState("");
  const [add, setAdd] = useState<{ page: number; x: number; y: number } | null>(null);
  const [style, setStyle] = useState({ size: 12, color: "#000000", font: "helv", bold: false, italic: false });

  const shapes: Shape[] = [];
  if (tab === "edit") {
    Object.entries(spans).forEach(([p, list]) =>
      list.forEach((s, i) => shapes.push({ page: Number(p), kind: "rect", rect: s.bbox, id: `${p}-${i}`, color: sel?.span === s ? "#f97316" : "#3b6cf680", fill: sel?.span === s ? "#f9731622" : "transparent", dashed: sel?.span !== s })),
    );
  } else if (add) shapes.push({ page: add.page, kind: "point", points: [[add.x, add.y]], color: "#16a34a", label: "New text" });

  useViewer({
    mode: tab === "add" ? "point" : "none",
    shapes,
    onShapeClick: (s) => {
      const [p, i] = String(s.id).split("-").map(Number);
      const span = spans[p]?.[i];
      if (span) {
        setSel({ page: p, span });
        setText(span.text);
      }
    },
    onPoint: (page, x, y) => setAdd({ page, x, y }),
  });

  const apply = async () => {
    if (!sel) return;
    const s = sel.span;
    await run("replace_text", { page: sel.page, bbox: s.bbox, new_text: text, font: s.font, size: s.size, color: s.color, bold: s.bold, italic: s.italic, origin: s.origin });
    setSel(null);
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-1 rounded-lg bg-slate-100 p-1 text-sm dark:bg-slate-800">
        <button className={`flex-1 rounded-md py-1.5 ${tab === "edit" ? "bg-white shadow dark:bg-slate-700" : ""}`} onClick={() => setTab("edit")}>Edit existing text</button>
        <button className={`flex-1 rounded-md py-1.5 ${tab === "add" ? "bg-white shadow dark:bg-slate-700" : ""}`} onClick={() => setTab("add")}>Add new text</button>
      </div>
      {tab === "edit" && (
        <>
          {pagePicker}
          {loading && <Spinner text="Finding text..." />}
          {!sel && !loading && <p className="text-sm text-slate-500">Click any outlined text in the document to change it.</p>}
          {sel && (
            <div className="space-y-2">
              <p className="text-xs text-slate-500">Font: {sel.span.font}, {sel.span.size}pt. The closest matching font is used.</p>
              <textarea className="input min-h-[80px]" value={text} onChange={(e) => setText(e.target.value)} autoFocus />
              <div className="flex gap-2">
                <button className="btn-primary flex-1" disabled={busy} onClick={apply}>Replace text</button>
                <button className="btn-secondary" onClick={() => setSel(null)}>Cancel</button>
              </div>
            </div>
          )}
        </>
      )}
      {tab === "add" && (
        <div className="space-y-3">
          <p className="text-sm text-slate-500">{add ? `Position set on page ${add.page + 1}.` : "Click on the page where the text should start."}</p>
          <textarea className="input min-h-[80px]" placeholder="Your text (supports English, Tamil, Hindi)" value={text} onChange={(e) => setText(e.target.value)} />
          <div className="grid grid-cols-2 gap-2">
            <div><label className="label">Size</label><input type="number" className="input" value={style.size} onChange={(e) => setStyle({ ...style, size: Number(e.target.value) })} /></div>
            <div><label className="label">Color</label><input type="color" className="h-10 w-full" value={style.color} onChange={(e) => setStyle({ ...style, color: e.target.value })} /></div>
            <div className="col-span-2"><label className="label">Font</label>
              <select className="input" value={style.font} onChange={(e) => setStyle({ ...style, font: e.target.value })}>
                <option value="helv">Sans (Helvetica)</option><option value="times">Serif (Times)</option><option value="courier">Monospace (Courier)</option>
              </select>
            </div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={style.bold} onChange={(e) => setStyle({ ...style, bold: e.target.checked })} /> Bold</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={style.italic} onChange={(e) => setStyle({ ...style, italic: e.target.checked })} /> Italic</label>
          </div>
          <button className="btn-primary w-full" disabled={busy || !add || !text.trim()} onClick={async () => { await run("add_text", { page: add!.page, x: add!.x, y: add!.y, text, ...style }); setAdd(null); setText(""); }}>
            Add text
          </button>
        </div>
      )}
    </div>
  );
}

interface Img {
  xref: number;
  bbox: number[];
  width: number;
  height: number;
}

export function ImagesPanel() {
  const { run, busy } = useEditor();
  const { toast } = useApp();
  const { data: images, pagePicker } = usePerPage<Img>("images");
  const [sel, setSel] = useState<{ page: number; img: Img } | null>(null);
  const [action, setAction] = useState<"none" | "move" | "add">("none");
  const [newImage, setNewImage] = useState<string>();
  const [crop, setCrop] = useState({ left: 0, top: 0, right: 0, bottom: 0 });

  const shapes: Shape[] = [];
  Object.entries(images).forEach(([p, list]) =>
    list.forEach((im, i) => shapes.push({ page: Number(p), kind: "rect", rect: im.bbox, id: `${p}-${i}`, color: sel?.img === im ? "#f97316" : "#8b5cf6", fill: sel?.img === im ? "#f9731622" : "#8b5cf611", label: sel?.img === im ? "Selected" : undefined })),
  );

  useViewer({
    mode: action === "none" ? "none" : "rect",
    shapes,
    onShapeClick: (s) => {
      const [p, i] = String(s.id).split("-").map(Number);
      if (images[p]?.[i]) setSel({ page: p, img: images[p][i] });
    },
    onRect: async (page, rect) => {
      if (action === "move" && sel) {
        if (page !== sel.page) return toast("Draw the new position on the same page.", "error");
        await run("move_image", { page, xref: sel.img.xref, rect });
        setSel(null);
      } else if (action === "add") {
        if (!newImage) return toast("Choose an image first.", "error");
        await run("add_image", { page, rect, image_file_id: newImage });
      }
      setAction("none");
    },
  });

  return (
    <div className="space-y-4">
      {pagePicker}
      <section className="space-y-2">
        <h3 className="label">Add an image</h3>
        <AssetPicker value={newImage} onChange={(id) => setNewImage(id)} />
        <button className="btn-secondary w-full" disabled={!newImage} onClick={() => setAction("add")}>
          {action === "add" ? "Now drag a box on the page..." : "Place on page"}
        </button>
      </section>
      <section className="space-y-2 border-t border-slate-200 pt-4 dark:border-slate-800">
        <h3 className="label">Selected image</h3>
        {!sel ? (
          <p className="text-sm text-slate-500">Click an image (purple box) in the document.</p>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-slate-500">Page {sel.page + 1} · {sel.img.width}×{sel.img.height}px</p>
            <button className="btn-secondary w-full" onClick={() => setAction("move")}>{action === "move" ? "Drag the new position/size..." : "Move / resize"}</button>
            <div>
              <span className="label">Replace with</span>
              <AssetPicker label="Choose replacement" onChange={(id) => id && run("replace_image", { page: sel.page, xref: sel.img.xref, image_file_id: id }).then(() => setSel(null))} />
            </div>
            <div>
              <span className="label">Crop (fraction of each side, 0 - 0.9)</span>
              <div className="grid grid-cols-4 gap-1">
                {(Object.keys(crop) as (keyof typeof crop)[]).map((k) => (
                  <input key={k} title={k} type="number" min={0} max={0.9} step={0.05} className="input px-2" value={crop[k]} onChange={(e) => setCrop({ ...crop, [k]: Number(e.target.value) })} />
                ))}
              </div>
              <button className="btn-secondary mt-2 w-full" disabled={busy} onClick={() => run("crop_image", { page: sel.page, xref: sel.img.xref, ...crop }).then(() => setSel(null))}>Crop image</button>
            </div>
            <button className="btn-danger w-full" disabled={busy} onClick={() => run("delete_image", { page: sel.page, xref: sel.img.xref }).then(() => setSel(null))}>
              <Trash2 size={14} /> Delete image
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

interface LinkInfo {
  index: number;
  bbox: number[];
  uri: string | null;
  page: number | null;
}

export function LinksPanel() {
  const { file, run, busy } = useEditor();
  const [tab, setTab] = useState<"links" | "bookmarks" | "attachments">("links");
  return (
    <div className="space-y-4">
      <div className="flex gap-1 rounded-lg bg-slate-100 p-1 text-xs dark:bg-slate-800">
        {(["links", "bookmarks", "attachments"] as const).map((t) => (
          <button key={t} className={`flex-1 rounded-md py-1.5 capitalize ${tab === t ? "bg-white shadow dark:bg-slate-700" : ""}`} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>
      {tab === "links" && <LinksTab />}
      {tab === "bookmarks" && file && <BookmarksTab fileId={file.id} run={run} busy={busy} />}
      {tab === "attachments" && file && <AttachmentsTab fileId={file.id} run={run} busy={busy} />}
    </div>
  );
}

function LinksTab() {
  const { run, busy } = useEditor();
  const { data: links, pagePicker } = usePerPage<LinkInfo>("links");
  const [draft, setDraft] = useState<{ page: number; rect?: number[]; index?: number; uri: string; target: string } | null>(null);
  const [drawing, setDrawing] = useState(false);

  const shapes: Shape[] = [];
  Object.entries(links).forEach(([p, list]) => list.forEach((l) => shapes.push({ page: Number(p), kind: "rect", rect: l.bbox, id: `${p}-${l.index}`, color: "#0ea5e9", fill: "#0ea5e922", label: l.uri ? "URL" : `→ p.${l.page}` })));
  if (draft?.rect) shapes.push({ page: draft.page, kind: "rect", rect: draft.rect, color: "#16a34a", dashed: true, label: "New link" });

  useViewer({
    mode: drawing ? "rect" : "none",
    shapes,
    onRect: (page, rect) => { setDraft({ page, rect, uri: "", target: "" }); setDrawing(false); },
    onShapeClick: (s) => {
      const [p, idx] = String(s.id).split("-").map(Number);
      const l = links[p]?.find((x) => x.index === idx);
      if (l) setDraft({ page: p, index: idx, uri: l.uri || "", target: l.page ? String(l.page) : "" });
    },
  });

  const save = async () => {
    if (!draft) return;
    await run("set_link", { page: draft.page, rect: draft.rect ?? null, index: draft.index ?? null, uri: draft.uri, target_page: draft.target ? Number(draft.target) : null });
    setDraft(null);
  };
  return (
    <div className="space-y-3">
      {pagePicker}
      <button className="btn-secondary w-full" onClick={() => { setDrawing(true); setDraft(null); }}>
        <Plus size={14} /> {drawing ? "Drag a box over the link area..." : "New link"}
      </button>
      {!draft && <p className="text-sm text-slate-500">Or click an existing link (blue box) to edit it.</p>}
      {draft && (
        <div className="space-y-2">
          <div><label className="label">Web address</label><input className="input" placeholder="https://..." value={draft.uri} onChange={(e) => setDraft({ ...draft, uri: e.target.value, target: "" })} /></div>
          <div><label className="label">Or go to page</label><input type="number" min={1} className="input" value={draft.target} onChange={(e) => setDraft({ ...draft, target: e.target.value, uri: "" })} /></div>
          <div className="flex gap-2">
            <button className="btn-primary flex-1" disabled={busy || (!draft.uri && !draft.target)} onClick={save}>Save link</button>
            {draft.index !== undefined && <button className="btn-danger" disabled={busy} onClick={() => run("set_link", { page: draft.page, index: draft.index, delete: true }).then(() => setDraft(null))}><Trash2 size={14} /></button>}
            <button className="btn-secondary" onClick={() => setDraft(null)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}

function BookmarksTab({ fileId, run, busy }: { fileId: string; run: any; busy: boolean }) {
  const { goTo, pages } = useEditor();
  const [items, setItems] = useState<{ level: number; title: string; page: number }[] | null>(null);
  useViewer({});
  useEffect(() => { inspect(fileId, "outline").then(setItems); }, [fileId]);
  if (!items) return <Spinner text="Loading bookmarks..." />;
  const upd = (i: number, patch: Partial<(typeof items)[0]>) => setItems(items.map((x, k) => (k === i ? { ...x, ...patch } : x)));
  return (
    <div className="space-y-2">
      {items.length === 0 && <p className="text-sm text-slate-500">No bookmarks yet.</p>}
      {items.map((b, i) => (
        <div key={i} className="flex items-center gap-1" style={{ paddingLeft: (b.level - 1) * 12 }}>
          <select className="input w-14 px-1" value={b.level} onChange={(e) => upd(i, { level: Number(e.target.value) })}>{[1, 2, 3, 4].map((l) => <option key={l}>{l}</option>)}</select>
          <input className="input min-w-0 flex-1" value={b.title} onChange={(e) => upd(i, { title: e.target.value })} />
          <input type="number" min={1} max={pages.length} className="input w-16 px-1" value={b.page} onChange={(e) => upd(i, { page: Number(e.target.value) })} />
          <button className="btn-ghost px-1" onClick={() => goTo(b.page - 1)} title="Go to">↗</button>
          <button className="btn-ghost px-1 text-red-600" onClick={() => setItems(items.filter((_, k) => k !== i))} aria-label="Remove"><Trash2 size={14} /></button>
        </div>
      ))}
      <button className="btn-secondary w-full" onClick={() => setItems([...items, { level: 1, title: "New bookmark", page: 1 }])}><Plus size={14} /> Add bookmark</button>
      <button className="btn-primary w-full" disabled={busy} onClick={() => run("set_bookmarks", { items })}>Save bookmarks</button>
    </div>
  );
}

function AttachmentsTab({ fileId, run, busy }: { fileId: string; run: any; busy: boolean }) {
  const [list, setList] = useState<{ name: string; size: number; description: string }[] | null>(null);
  const [asset, setAsset] = useState<string>();
  const [desc, setDesc] = useState("");
  useViewer({});
  useEffect(() => { inspect(fileId, "attachments").then(setList); }, [fileId]);
  return (
    <div className="space-y-3">
      {list === null ? <Spinner /> : list.length === 0 ? <p className="text-sm text-slate-500">No attachments.</p> : (
        <ul className="space-y-1">{list.map((a) => (
          <li key={a.name} className="flex items-center gap-2 rounded bg-slate-100 px-2 py-1 text-sm dark:bg-slate-800">
            <span className="flex-1 truncate">{a.name}</span>
            <button className="text-red-600" disabled={busy} onClick={() => run("remove_attachment", { name: a.name })} aria-label="Remove"><Trash2 size={14} /></button>
          </li>
        ))}</ul>
      )}
      <AssetPicker value={asset} accept={ACCEPT.any} label="Choose file to attach" onChange={(id) => setAsset(id)} />
      <input className="input" placeholder="Description (optional)" value={desc} onChange={(e) => setDesc(e.target.value)} />
      <button className="btn-primary w-full" disabled={busy || !asset} onClick={() => run("add_attachment", { attachment_file_id: asset, description: desc }).then(() => setAsset(undefined))}>Attach file</button>
    </div>
  );
}
