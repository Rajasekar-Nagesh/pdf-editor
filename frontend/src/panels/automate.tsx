// Batch actions (saved workflows), measuring tool, and the AI assistant.
import { Fragment, ReactNode, useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Plus, Send, Sparkles, Trash2 } from "lucide-react";
import { api, FileInfo, Job, uploadFiles } from "../lib/api";
import { useApp } from "../lib/app-context";
import { BATCHABLE, Field, REDACT_PRESETS, TOOLS } from "../lib/tools";
import { Shape } from "../components/PdfViewer";
import { ACCEPT, defaults, Dropzone, FieldInput, JobResult, ProgressBar, toParams } from "../components/ui";
import { useEditor, useViewer } from "../pages/Editor";

// Field sets for batch steps that do not have a stand-alone form tool.
const EXTRA_STEP_FIELDS: Record<string, { title: string; fields: Field[] }> = {
  set_metadata: { title: "Set metadata", fields: [{ key: "title", label: "Title", type: "text", default: "" }, { key: "author", label: "Author", type: "text", default: "" }, { key: "keywords", label: "Keywords", type: "text", default: "" }] },
  crop: { title: "Crop margins", fields: ["left", "top", "right", "bottom"].map((k) => ({ key: k, label: `${k} (pt)`, type: "number" as const, default: 0 })) },
  redact: { title: "Redact patterns", fields: [{ key: "presets", label: "Patterns", type: "multiselect", default: ["pan", "aadhaar"], options: REDACT_PRESETS }] },
};

function stepDef(tool: string): { title: string; fields: Field[] } {
  if (EXTRA_STEP_FIELDS[tool]) return EXTRA_STEP_FIELDS[tool];
  const t = TOOLS.find((x) => x.backend === tool)!;
  return { title: t.title, fields: t.fields || [] };
}

interface Step { tool: string; values: Record<string, any> }
interface Workflow { id: string; name: string; steps: { tool: string; params: Record<string, any> }[] }

export function BatchCenter() {
  const { run, busy } = useEditor();
  const { user, toast } = useApp();
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [steps, setSteps] = useState<Step[]>([{ tool: "ocr", values: defaults(stepDef("ocr").fields) }]);
  const [name, setName] = useState("My batch action");
  const [saved, setSaved] = useState<Workflow[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [uploadPct, setUploadPct] = useState<number | null>(null);

  const loadSaved = () => user && api<{ workflows: Workflow[] }>("/api/workflows").then((r) => setSaved(r.workflows)).catch(() => undefined);
  useEffect(() => { loadSaved(); }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  const params = () => steps.map((s) => ({ tool: s.tool, params: toParams(stepDef(s.tool).fields, s.values) }));
  const upd = (i: number, patch: Partial<Step>) => setSteps(steps.map((s, k) => (k === i ? { ...s, ...patch } : s)));
  const move = (i: number, d: number) => {
    const j = i + d;
    if (j < 0 || j >= steps.length) return;
    const next = [...steps];
    [next[i], next[j]] = [next[j], next[i]];
    setSteps(next);
  };

  const save = async () => {
    try {
      await api("/api/workflows", { method: "POST", json: { name, steps: params() } });
      toast("Batch action saved", "success");
      loadSaved();
    } catch (e: any) { toast(e.message, "error"); }
  };
  const load = (w: Workflow) => {
    setName(w.name);
    setSteps(w.steps.map((s) => ({ tool: s.tool, values: { ...defaults(stepDef(s.tool).fields), ...s.params } })));
  };
  const start = async () => {
    if (!files.length) return toast("Add files to process.", "error");
    setJob(null);
    setJob(await run("batch", { steps: params() }, files.map((f) => f.id)));
  };

  return (
    <div className="grid h-full gap-4 overflow-y-auto p-4 lg:grid-cols-3">
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">1. Files</h2>
        <Dropzone multiple compact accept={ACCEPT.any} label="Add PDFs, Office files or images" onFiles={async (picked) => {
          setUploadPct(0);
          try { const r = await uploadFiles(picked, setUploadPct); setFiles((f) => [...f, ...r.files]); } catch (e: any) { toast(e.message, "error"); } finally { setUploadPct(null); }
        }} />
        {uploadPct !== null && <ProgressBar value={uploadPct} label="Uploading" />}
        <ul className="space-y-1">{files.map((f, i) => (
          <li key={f.id} className="card flex items-center gap-2 px-2 py-1.5 text-sm"><span className="flex-1 truncate">{f.name}</span><button className="text-red-600" onClick={() => setFiles(files.filter((_, k) => k !== i))}><Trash2 size={14} /></button></li>
        ))}</ul>
        <p className="text-xs text-slate-500">Office files and images are converted to PDF before the steps run.</p>
      </section>
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">2. Steps</h2>
        {steps.map((s, i) => {
          const def = stepDef(s.tool);
          return (
            <div key={i} className="card space-y-2 p-3">
              <div className="flex items-center gap-1">
                <span className="text-xs font-semibold text-slate-400">{i + 1}</span>
                <select className="input py-1.5" value={s.tool} onChange={(e) => upd(i, { tool: e.target.value, values: defaults(stepDef(e.target.value).fields) })}>
                  {BATCHABLE.map((b) => <option key={b} value={b}>{stepDef(b).title}</option>)}
                </select>
                <button className="btn-ghost px-1" onClick={() => move(i, -1)}><ArrowUp size={14} /></button>
                <button className="btn-ghost px-1" onClick={() => move(i, 1)}><ArrowDown size={14} /></button>
                <button className="btn-ghost px-1 text-red-600" disabled={steps.length === 1} onClick={() => setSteps(steps.filter((_, k) => k !== i))}><Trash2 size={14} /></button>
              </div>
              {def.fields.filter((f) => (!f.showIf || f.showIf(s.values)) && f.type !== "password").map((f) => (
                <FieldInput key={f.key} field={f} value={s.values[f.key]} onChange={(v) => upd(i, { values: { ...s.values, [f.key]: v } })} />
              ))}
            </div>
          );
        })}
        <button className="btn-secondary w-full" onClick={() => setSteps([...steps, { tool: "compress", values: defaults(stepDef("compress").fields) }])}><Plus size={14} /> Add step</button>
      </section>
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">3. Run</h2>
        <button className="btn-primary w-full" disabled={busy} onClick={start}>Run on {files.length} file(s)</button>
        {job && <JobResult job={job} />}
        <div className="border-t border-slate-200 pt-3 dark:border-slate-800">
          <h3 className="label">Saved batch actions</h3>
          {user ? (
            <>
              <div className="flex gap-1"><input className="input" value={name} onChange={(e) => setName(e.target.value)} /><button className="btn-secondary" onClick={save}>Save</button></div>
              <ul className="mt-2 space-y-1">{saved.map((w) => (
                <li key={w.id} className="flex items-center gap-2 text-sm">
                  <button className="flex-1 truncate text-left underline" onClick={() => load(w)}>{w.name}</button>
                  <span className="text-xs text-slate-500">{w.steps.length} steps</span>
                  <button className="text-red-600" onClick={() => api(`/api/workflows/${w.id}`, { method: "DELETE" }).then(loadSaved)}><Trash2 size={13} /></button>
                </li>
              ))}</ul>
            </>
          ) : <p className="text-xs text-slate-500">Log in to save batch actions for reuse.</p>}
        </div>
      </section>
    </div>
  );
}

// ------------------------------------------------------------------ measure tool

const PAPER_UNITS: Record<string, number> = { pt: 1, mm: 72 / 25.4, cm: 72 / 2.54, in: 72 };

interface Measurement { page: number; kind: "distance" | "area"; points: number[][] }

export function MeasurePanel() {
  const [kind, setKind] = useState<"distance" | "area">("distance");
  const [scale, setScale] = useState({ paper: 1, paperUnit: "cm", real: 1, realUnit: "m" });
  const [items, setItems] = useState<Measurement[]>([]);
  const factor = (PAPER_UNITS[scale.paperUnit] ? 1 / PAPER_UNITS[scale.paperUnit] : 1) * (scale.real / (scale.paper || 1)); // pt -> real units

  const length = (pts: number[][]) => pts.slice(1).reduce((s, p, i) => s + Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]), 0);
  const area = (pts: number[][]) => Math.abs(pts.reduce((s, p, i) => { const q = pts[(i + 1) % pts.length]; return s + p[0] * q[1] - q[0] * p[1]; }, 0)) / 2;
  const fmt = (m: Measurement) =>
    m.kind === "distance" ? `${(length(m.points) * factor).toFixed(2)} ${scale.realUnit}` : `${(area(m.points) * factor * factor).toFixed(2)} ${scale.realUnit}²`;

  const shapes: Shape[] = items.map((m, i) => ({ page: m.page, kind: m.kind === "distance" ? "line" : "poly", points: m.points, closed: m.kind === "area", color: "#db2777", label: fmt(m), id: i }));
  useViewer({
    mode: kind === "distance" ? "line" : "poly",
    shapes,
    onLine: (page, a, b) => setItems((x) => [...x, { page, kind: "distance", points: [a, b] }]),
    onPoly: (page, pts) => pts.length >= 3 && setItems((x) => [...x, { page, kind: "area", points: pts }]),
  });

  return (
    <div className="space-y-4">
      <div className="flex gap-1 rounded-lg bg-slate-100 p-1 text-sm dark:bg-slate-800">
        <button className={`flex-1 rounded-md py-1.5 ${kind === "distance" ? "bg-white shadow dark:bg-slate-700" : ""}`} onClick={() => setKind("distance")}>Distance</button>
        <button className={`flex-1 rounded-md py-1.5 ${kind === "area" ? "bg-white shadow dark:bg-slate-700" : ""}`} onClick={() => setKind("area")}>Area</button>
      </div>
      <p className="text-xs text-slate-500">{kind === "distance" ? "Drag from one point to another." : "Click each corner, then double-click to close the shape."}</p>
      <div>
        <span className="label">Scale</span>
        <div className="flex items-center gap-1 text-sm">
          <input type="number" className="input w-16 px-2" value={scale.paper} onChange={(e) => setScale({ ...scale, paper: Number(e.target.value) })} />
          <select className="input w-16 px-1" value={scale.paperUnit} onChange={(e) => setScale({ ...scale, paperUnit: e.target.value })}>{Object.keys(PAPER_UNITS).map((u) => <option key={u}>{u}</option>)}</select>
          <span>=</span>
          <input type="number" className="input w-16 px-2" value={scale.real} onChange={(e) => setScale({ ...scale, real: Number(e.target.value) })} />
          <input className="input w-14 px-2" value={scale.realUnit} onChange={(e) => setScale({ ...scale, realUnit: e.target.value })} />
        </div>
        <p className="mt-1 text-xs text-slate-500">Example: 1 cm on paper = 1 m in reality (1:100).</p>
      </div>
      <ul className="space-y-1 text-sm">
        {items.map((m, i) => (
          <li key={i} className="flex items-center gap-2"><span className="chip bg-pink-100 text-pink-800">p.{m.page + 1}</span><span className="flex-1">{m.kind}: <b>{fmt(m)}</b></span><button className="text-red-600" onClick={() => setItems(items.filter((_, k) => k !== i))}><Trash2 size={13} /></button></li>
        ))}
      </ul>
      {items.length > 0 && <button className="btn-secondary w-full" onClick={() => setItems([])}>Clear all</button>}
    </div>
  );
}

// ------------------------------------------------------------------ AI assistant

interface Msg { role: "user" | "assistant"; content: string; citations?: number[] }

/** Render "[p. 3]" / "[pp. 4-5]" citations as buttons that jump to the page. */
function WithCitations({ text, onPage }: { text: string; onPage: (p: number) => void }) {
  const parts = text.split(/(\[pp?\.\s*[\d,\s\-–]+\])/g);
  const out: ReactNode[] = parts.map((part, i) => {
    const m = part.match(/^\[pp?\.\s*(\d+)/);
    if (!m) return <Fragment key={i}>{part}</Fragment>;
    return <button key={i} className="mx-0.5 rounded bg-brand-100 px-1 text-xs font-semibold text-brand-700 hover:bg-brand-500 hover:text-white dark:bg-brand-700/40 dark:text-brand-100" onClick={() => onPage(Number(m[1]) - 1)}>{part.slice(1, -1)}</button>;
  });
  return <div className="whitespace-pre-wrap">{out}</div>;
}

export function AiPanel() {
  const { file, goTo } = useEditor();
  const { aiEnabled, toast } = useApp();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [note, setNote] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useViewer({});
  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [msgs, thinking]);

  if (!aiEnabled) return <p className="text-sm text-slate-500">The AI assistant is not enabled on this server.</p>;

  const summary = async () => {
    setThinking(true);
    try {
      const r = await api<{ answer: string; citations: number[]; note: string }>("/api/ai/summary", { method: "POST", json: { file_id: file!.id } });
      setMsgs((m) => [...m, { role: "user", content: "Summarise this document." }, { role: "assistant", content: r.answer, citations: r.citations }]);
      setNote(r.note);
    } catch (e: any) { toast(e.message, "error"); } finally { setThinking(false); }
  };
  const ask = async () => {
    const q = input.trim();
    if (!q) return;
    const next: Msg[] = [...msgs, { role: "user", content: q }];
    setMsgs(next);
    setInput("");
    setThinking(true);
    try {
      const r = await api<{ answer: string; citations: number[] }>("/api/ai/chat", { method: "POST", json: { file_id: file!.id, messages: next.map(({ role, content }) => ({ role, content })) } });
      setMsgs([...next, { role: "assistant", content: r.answer, citations: r.citations }]);
    } catch (e: any) { toast(e.message, "error"); } finally { setThinking(false); }
  };

  return (
    <div className="flex h-[60vh] flex-col lg:h-[calc(100vh-260px)]">
      <button className="btn-secondary mb-3" disabled={thinking} onClick={summary}><Sparkles size={14} /> One-click summary</button>
      <div className="flex-1 space-y-3 overflow-y-auto pr-1 text-sm">
        {msgs.length === 0 && <p className="text-slate-500">Ask anything about this document. Answers cite page numbers you can click.</p>}
        {msgs.map((m, i) => (
          <div key={i} className={`rounded-lg p-2.5 ${m.role === "user" ? "ml-6 bg-brand-600 text-white" : "mr-2 bg-slate-100 dark:bg-slate-800"}`}>
            {m.role === "assistant" ? <WithCitations text={m.content} onPage={goTo} /> : m.content}
          </div>
        ))}
        {thinking && <div className="mr-2 animate-pulse rounded-lg bg-slate-100 p-2.5 text-slate-500 dark:bg-slate-800">Reading the document...</div>}
        {note && <p className="text-xs text-slate-500">{note}</p>}
        <div ref={end} />
      </div>
      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); ask(); }}>
        <input className="input" placeholder="Ask a question..." value={input} onChange={(e) => setInput(e.target.value)} disabled={thinking} />
        <button className="btn-primary px-3" disabled={thinking || !input.trim()} aria-label="Send"><Send size={16} /></button>
      </form>
      <p className="mt-2 text-[11px] text-slate-400">AI answers can be wrong. Check the cited pages.</p>
    </div>
  );
}
