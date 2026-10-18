// Review panels: annotations, compare, and shareable review links.
import { useEffect, useState } from "react";
import { ArrowRight, Circle, Copy, ExternalLink, Highlighter, MessageSquare, MoveUpRight, PenTool, Square, Strikethrough, Trash2, Type, Underline } from "lucide-react";
import { api, FileInfo, inspect, Job, uploadOne } from "../lib/api";
import { useApp } from "../lib/app-context";
import PdfViewer, { Mode, Shape } from "../components/PdfViewer";
import { Dropzone, JobResult, Spinner } from "../components/ui";
import { useEditor, useViewer } from "../pages/Editor";

type AnnType = "highlight" | "underline" | "strikeout" | "note" | "ink" | "rect" | "circle" | "arrow" | "textbox";

const TYPES: { id: AnnType; label: string; icon: any; mode: Mode }[] = [
  { id: "highlight", label: "Highlight", icon: Highlighter, mode: "rect" },
  { id: "underline", label: "Underline", icon: Underline, mode: "rect" },
  { id: "strikeout", label: "Strike", icon: Strikethrough, mode: "rect" },
  { id: "note", label: "Note", icon: MessageSquare, mode: "point" },
  { id: "ink", label: "Draw", icon: PenTool, mode: "ink" },
  { id: "rect", label: "Box", icon: Square, mode: "rect" },
  { id: "circle", label: "Ellipse", icon: Circle, mode: "rect" },
  { id: "arrow", label: "Arrow", icon: MoveUpRight, mode: "line" },
  { id: "textbox", label: "Text box", icon: Type, mode: "rect" },
];

export function AnnotatePanel() {
  const { run, busy, file, pages, refreshKey } = useEditor();
  const [type, setType] = useState<AnnType>("highlight");
  const [color, setColor] = useState("#facc15");
  const [opacity, setOpacity] = useState(0.6);
  const [text, setText] = useState("");
  const [pending, setPending] = useState<any[]>([]);
  const [existing, setExisting] = useState<{ page: number; xref: number; type: string; content: string }[]>([]);
  const { toast } = useApp();
  const def = TYPES.find((t) => t.id === type)!;

  useEffect(() => {
    if (!file || !pages.length || pages.length > 40) return;
    Promise.all(pages.map((_, p) => inspect<any[]>(file.id, "annotations", p).then((l) => l.filter((a) => a.type !== "Link" && a.type !== "Widget").map((a) => ({ ...a, page: p })))))
      .then((r) => setExisting(r.flat()))
      .catch(() => undefined);
  }, [file?.id, pages.length, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const add = (a: any) => {
    if ((type === "note" || type === "textbox") && !text.trim()) return toast("Type the note text first.", "error");
    setPending((p) => [...p, { ...a, type, color, opacity, ...(type === "note" || type === "textbox" ? { text } : {}) }]);
  };

  const shapes: Shape[] = pending.map((a, i) => {
    if (a.strokes) return { page: a.page, kind: "ink", strokes: a.strokes, color: a.color, id: i };
    if (a.point) return { page: a.page, kind: "point", points: [a.point], color: a.color, label: "Note", id: i };
    if (a.from) return { page: a.page, kind: "line", points: [a.from, a.to], color: a.color, id: i };
    return { page: a.page, kind: "rect", rect: a.rect, color: a.color, fill: `${a.color}44`, label: a.type, id: i };
  });

  useViewer({
    mode: def.mode,
    shapes,
    onRect: (page, rect) => add({ page, rect }),
    onPoint: (page, x, y) => (type === "note" ? add({ page, point: [x, y] }) : undefined),
    onInk: (page, stroke) => add({ page, strokes: [stroke] }),
    onLine: (page, from, to) => add({ page, from, to }),
  });

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-1">
        {TYPES.map((t) => (
          <button key={t.id} onClick={() => setType(t.id)} className={`btn flex-col gap-0.5 border px-1 py-2 text-xs ${type === t.id ? "border-brand-500 bg-brand-50 dark:bg-brand-700/20" : "border-slate-200 dark:border-slate-700"}`}>
            <t.icon size={16} /> {t.label}
          </button>
        ))}
      </div>
      <p className="text-xs text-slate-500">
        {def.mode === "rect" ? "Drag over the area on the page." : def.mode === "point" ? "Click where the note should go." : def.mode === "ink" ? "Draw with your mouse, pen or finger." : "Drag from start to end."}
      </p>
      <div className="flex items-center gap-3">
        <label className="flex items-center gap-1 text-sm">Color <input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-8 w-10" /></label>
        <label className="flex flex-1 items-center gap-1 text-sm">Opacity <input type="range" min={0.1} max={1} step={0.05} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} className="flex-1" /></label>
      </div>
      {(type === "note" || type === "textbox") && <textarea className="input" placeholder="Note / text box content" value={text} onChange={(e) => setText(e.target.value)} />}
      {pending.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm"><span>{pending.length} new annotation(s)</span><button className="text-xs underline" onClick={() => setPending([])}>Discard</button></div>
          <button className="btn-primary w-full" disabled={busy} onClick={() => run("annotate", { annotations: pending }).then((j) => j && setPending([]))}>Save annotations</button>
        </div>
      )}
      {existing.length > 0 && (
        <div className="border-t border-slate-200 pt-3 dark:border-slate-800">
          <h3 className="label">Existing annotations</h3>
          <ul className="max-h-56 space-y-1 overflow-auto">
            {existing.map((a) => (
              <li key={`${a.page}-${a.xref}`} className="flex items-center gap-2 text-xs">
                <span className="chip bg-slate-100 dark:bg-slate-800">p.{a.page + 1}</span>
                <span className="flex-1 truncate">{a.type}{a.content ? `: ${a.content}` : ""}</span>
                <button className="text-red-600" disabled={busy} onClick={() => run("delete_annotation", { page: a.page, xref: a.xref })} aria-label="Delete"><Trash2 size={13} /></button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** Full-width compare view: choose two PDFs, then see both highlighted side by side with a change list. */
export function CompareCenter() {
  const { run, busy } = useEditor();
  const { toast } = useApp();
  const [a, setA] = useState<FileInfo | null>(null);
  const [b, setB] = useState<FileInfo | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [goA, setGoA] = useState<{ page: number; nonce: number }>();
  const [goB, setGoB] = useState<{ page: number; nonce: number }>();

  const pick = (set: (f: FileInfo) => void) => async (files: File[]) => {
    try { set(await uploadOne(files[0])); } catch (e: any) { toast(e.message, "error"); }
  };

  if (!job) {
    return (
      <div className="mx-auto max-w-3xl space-y-4 p-4">
        <h1 className="text-2xl font-bold">Compare PDFs</h1>
        <div className="grid gap-4 md:grid-cols-2">
          {[["Original", a, setA], ["Revised", b, setB]].map(([label, f, set]: any) => (
            <div key={label} className="space-y-2">
              <h2 className="font-semibold">{label}</h2>
              {f ? <div className="card flex items-center justify-between p-3 text-sm"><span className="truncate">{f.name}</span><button className="text-xs underline" onClick={() => set(null)}>Change</button></div>
                : <Dropzone compact onFiles={pick(set)} label={`Drop the ${label.toLowerCase()} PDF`} />}
            </div>
          ))}
        </div>
        <button className="btn-primary w-full" disabled={!a || !b || busy} onClick={async () => setJob(await run("compare", {}, [a!.id, b!.id]))}>Compare</button>
      </div>
    );
  }
  const d = job.result!.data;
  const [fa, fb] = job.result!.files;
  return (
    <div className="flex h-full flex-col lg:flex-row">
      <div className="grid min-h-0 flex-1 grid-rows-2 md:grid-cols-2 md:grid-rows-1">
        <div className="min-h-0 border-r border-slate-200 dark:border-slate-800"><PdfViewer fileId={fa.id} thumbnails={false} search={false} goTo={goA} /></div>
        <div className="min-h-0"><PdfViewer fileId={fb.id} thumbnails={false} search={false} goTo={goB} /></div>
      </div>
      <aside className="max-h-[40vh] w-full overflow-y-auto border-t border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 lg:max-h-none lg:w-80 lg:border-l lg:border-t-0">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold">{d.identical ? "No text differences" : `${d.changes.length} change(s)`}</h2>
          <button className="text-xs underline" onClick={() => setJob(null)}>New comparison</button>
        </div>
        <div className="mb-3 flex gap-2 text-xs">
          <span className="chip bg-red-100 text-red-800">Deleted {d.stats.deleted}</span>
          <span className="chip bg-emerald-100 text-emerald-800">Inserted {d.stats.inserted}</span>
          <span className="chip bg-amber-100 text-amber-800">Changed {d.stats.replaced}</span>
        </div>
        <ul className="space-y-2">
          {d.changes.map((c: any, i: number) => (
            <li key={i}>
              <button className="w-full rounded-lg border border-slate-200 p-2 text-left text-xs hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
                onClick={() => { if (c.page_a) setGoA({ page: c.page_a - 1, nonce: Date.now() }); if (c.page_b) setGoB({ page: c.page_b - 1, nonce: Date.now() }); }}>
                <span className="font-semibold capitalize">{c.type}</span> {c.page_a ? `p.${c.page_a}` : ""} <ArrowRight size={10} className="inline" /> {c.page_b ? `p.${c.page_b}` : ""}
                {c.old && <div className="mt-1 text-red-700 line-through dark:text-red-300">{c.old}</div>}
                {c.new && <div className="mt-1 text-emerald-700 dark:text-emerald-300">{c.new}</div>}
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-4"><JobResult job={job} /></div>
      </aside>
    </div>
  );
}

interface ReviewLink { id: string; token: string; url: string; file_id: string; title: string; active: boolean; comments: number; created_at: string }

export function SharePanel() {
  const { file } = useEditor();
  const { toast } = useApp();
  const [links, setLinks] = useState<ReviewLink[] | null>(null);
  const [title, setTitle] = useState(file?.name || "");
  useViewer({});
  const load = () => api<{ links: ReviewLink[] }>("/api/review-links").then((r) => setLinks(r.links.filter((l) => l.file_id === file?.id)));
  useEffect(() => { load(); }, [file?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const copy = (url: string) => navigator.clipboard.writeText(url).then(() => toast("Link copied", "success"));
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500">Anyone with the link can view this version of the document and add comments. Comments appear for everyone within a few seconds.</p>
      <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title for reviewers" />
      <button className="btn-primary w-full" onClick={() => api<ReviewLink>("/api/review-links", { method: "POST", json: { file_id: file!.id, title } }).then((l) => { copy(l.url); load(); }).catch((e) => toast(e.message, "error"))}>
        Create review link
      </button>
      {links === null ? <Spinner /> : links.map((l) => (
        <div key={l.id} className={`rounded-lg border p-2 text-sm ${l.active ? "border-slate-200 dark:border-slate-700" : "opacity-50"}`}>
          <div className="font-medium">{l.title}</div>
          <div className="text-xs text-slate-500">{l.comments} comment(s) · {l.active ? "active" : "disabled"}</div>
          {l.active && (
            <div className="mt-2 flex gap-1">
              <button className="btn-secondary px-2 py-1 text-xs" onClick={() => copy(l.url)}><Copy size={12} /> Copy</button>
              <a className="btn-secondary px-2 py-1 text-xs" href={`/review/${l.token}`} target="_blank" rel="noreferrer"><ExternalLink size={12} /> Open</a>
              <button className="btn-ghost px-2 py-1 text-xs text-red-600" onClick={() => api(`/api/review-links/${l.id}`, { method: "DELETE" }).then(load)}>Disable</button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
