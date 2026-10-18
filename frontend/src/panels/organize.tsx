// Page organizer that edits entirely in the browser with pdf-lib, then saves a new version.
import { useEffect, useRef, useState } from "react";
import { degrees, PDFDocument } from "pdf-lib";
import { CheckSquare, Copy, FilePlus2, Redo2, RotateCcw, RotateCw, Save, Trash2, Undo2 } from "lucide-react";
import { fileBytes, uploadOne, uploadVersion } from "../lib/api";
import { useApp } from "../lib/app-context";
import { loadPdf, PDFDoc } from "../lib/pdf";
import { LazyCanvas } from "../components/PdfViewer";
import { Spinner } from "../components/ui";
import { useEditor } from "../pages/Editor";

interface Item {
  key: string;
  src: number | null; // original page index, or null for an inserted blank page
  rotate: number; // extra rotation in degrees
}

let counter = 0;
const k = () => `i${counter++}`;

export function Organizer() {
  const { file, openFile } = useEditor();
  const { toast } = useApp();
  const [doc, setDoc] = useState<PDFDoc | null>(null);
  const bytes = useRef<ArrayBuffer | null>(null);
  const sizes = useRef<{ w: number; h: number; rot: number }[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [past, setPast] = useState<Item[][]>([]);
  const [future, setFuture] = useState<Item[][]>([]);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [drag, setDrag] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!file) return;
    (async () => {
      const data = await fileBytes(file.id);
      bytes.current = data;
      const d = await loadPdf(data);
      const s = [];
      for (let i = 1; i <= d.numPages; i++) {
        const p = await d.getPage(i);
        const vp = p.getViewport({ scale: 1 });
        s.push({ w: vp.width, h: vp.height, rot: p.rotate });
      }
      sizes.current = s;
      setDoc(d);
      setItems(s.map((_, i) => ({ key: k(), src: i, rotate: 0 })));
      setPast([]);
      setFuture([]);
    })().catch((e) => toast(e.message, "error"));
  }, [file?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const commit = (next: Item[]) => {
    setPast((p) => [...p, items]);
    setFuture([]);
    setItems(next);
  };
  const undo = () => past.length && (setFuture((f) => [items, ...f]), setItems(past[past.length - 1]), setPast(past.slice(0, -1)));
  const redo = () => future.length && (setPast((p) => [...p, items]), setItems(future[0]), setFuture(future.slice(1)));

  const targets = () => (sel.size ? items.filter((i) => sel.has(i.key)) : []);
  const rotate = (deg: number) => {
    const t = new Set(targets().map((i) => i.key));
    if (!t.size) return toast("Select pages first (click thumbnails).", "info");
    commit(items.map((i) => (t.has(i.key) ? { ...i, rotate: (i.rotate + deg + 360) % 360 } : i)));
  };
  const remove = () => {
    const t = new Set(targets().map((i) => i.key));
    if (!t.size) return toast("Select pages to delete.", "info");
    if (t.size >= items.length) return toast("You cannot delete every page.", "error");
    commit(items.filter((i) => !t.has(i.key)));
    setSel(new Set());
  };
  const insertBlank = () => {
    const lastSel = items.map((i) => sel.has(i.key)).lastIndexOf(true);
    const at = lastSel >= 0 ? lastSel + 1 : items.length;
    commit([...items.slice(0, at), { key: k(), src: null, rotate: 0 }, ...items.slice(at)]);
  };
  const duplicate = () => {
    const t = targets();
    if (!t.length) return toast("Select pages to duplicate.", "info");
    const out: Item[] = [];
    items.forEach((i) => { out.push(i); if (sel.has(i.key)) out.push({ ...i, key: k() }); });
    commit(out);
  };
  const onDrop = (overKey: string) => {
    if (!drag || drag === overKey) return;
    const from = items.findIndex((i) => i.key === drag);
    const to = items.findIndex((i) => i.key === overKey);
    const next = [...items];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    commit(next);
    setDrag(null);
  };

  /** Build the PDF with pdf-lib from the current item list. */
  const build = async (list: Item[]) => {
    const src = await PDFDocument.load(bytes.current!);
    const out = await PDFDocument.create();
    for (let idx = 0; idx < list.length; idx++) {
      const it = list[idx];
      if (it.src === null) {
        const ref = list.slice(0, idx).reverse().find((x) => x.src !== null) || list.find((x) => x.src !== null);
        const size = ref ? src.getPage(ref.src!).getSize() : { width: 595, height: 842 };
        const p = out.addPage([size.width, size.height]);
        p.setRotation(degrees(it.rotate));
      } else {
        const [p] = await out.copyPages(src, [it.src]);
        p.setRotation(degrees((p.getRotation().angle + it.rotate) % 360));
        out.addPage(p);
      }
    }
    return out.save();
  };

  const save = async () => {
    if (!file) return;
    setSaving(true);
    try {
      const data = await build(items);
      openFile(await uploadVersion(file.id, data, file.name));
      toast("Pages saved as a new version. Use Undo in the top bar to revert.", "success");
    } catch (e: any) {
      toast(e.message?.includes("encrypted") ? "Remove the password from this PDF first." : e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const extract = async () => {
    const t = targets();
    if (!t.length) return toast("Select pages to extract.", "info");
    setSaving(true);
    try {
      const data = await build(t);
      const f = await uploadOne(new File([data], `${file!.name.replace(/\.pdf$/i, "")}-extract.pdf`, { type: "application/pdf" }));
      openFile(f);
      toast("Extracted pages opened as a new document.", "success");
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  if (!doc) return <div className="p-8"><Spinner text="Loading pages..." /></div>;

  const bar = "btn-secondary px-2.5 py-1.5 text-xs";
  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-1.5 border-b border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-900">
        <button className={bar} onClick={() => setSel(sel.size === items.length ? new Set() : new Set(items.map((i) => i.key)))}><CheckSquare size={14} /> {sel.size === items.length ? "None" : "All"}</button>
        <button className={bar} onClick={() => rotate(-90)}><RotateCcw size={14} /> Left</button>
        <button className={bar} onClick={() => rotate(90)}><RotateCw size={14} /> Right</button>
        <button className={bar} onClick={remove}><Trash2 size={14} /> Delete</button>
        <button className={bar} onClick={insertBlank}><FilePlus2 size={14} /> Blank page</button>
        <button className={bar} onClick={duplicate}><Copy size={14} /> Duplicate</button>
        <button className={bar} onClick={extract} disabled={saving}>Extract</button>
        <button className={bar} onClick={undo} disabled={!past.length}><Undo2 size={14} /></button>
        <button className={bar} onClick={redo} disabled={!future.length}><Redo2 size={14} /></button>
        <button className="btn-primary ml-auto px-3 py-1.5 text-xs" onClick={save} disabled={saving || !past.length}><Save size={14} /> {saving ? "Saving..." : "Save changes"}</button>
      </div>
      <p className="px-3 pt-2 text-xs text-slate-500">Click to select · drag to reorder · {items.length} pages{sel.size ? ` · ${sel.size} selected` : ""}</p>
      <div className="grid flex-1 auto-rows-max grid-cols-2 gap-3 overflow-y-auto p-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6">
        {items.map((it, n) => {
          const s = it.src !== null ? sizes.current[it.src] : null;
          return (
            <div
              key={it.key}
              draggable
              onDragStart={() => setDrag(it.key)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => onDrop(it.key)}
              onClick={(e) => {
                const next = new Set(e.ctrlKey || e.metaKey || e.shiftKey ? sel : []);
                next.has(it.key) ? next.delete(it.key) : next.add(it.key);
                setSel(next);
              }}
              className={`card cursor-grab select-none p-2 text-center ${sel.has(it.key) ? "ring-2 ring-brand-500" : ""} ${drag === it.key ? "opacity-40" : ""}`}
            >
              <div className="flex h-40 items-center justify-center overflow-hidden">
                <div style={{ transform: `rotate(${it.rotate}deg)`, transition: "transform .2s" }}>
                  {s ? <LazyCanvas doc={doc} index={it.src!} scale={130 / Math.max(s.w, s.h)} /> : <div className="h-36 w-28 border bg-white shadow" />}
                </div>
              </div>
              <span className="text-xs text-slate-500">{n + 1}{it.src === null ? " (blank)" : ""}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
