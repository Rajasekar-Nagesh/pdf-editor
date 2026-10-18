// The editor workspace: left tool bar, center document view, right options panel.
// Every edit produces a new file version; undo/redo walks through those versions.
import { createContext, MutableRefObject, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, Download, Home, Redo2, Save, Undo2 } from "lucide-react";
import { api, downloadFile, FileInfo, Job, runTool, uploadFiles } from "../lib/api";
import { useApp } from "../lib/app-context";
import { TOOL_BY_ID, TOOLS, ToolDef } from "../lib/tools";
import PdfViewer, { Mode, PageSize, Shape } from "../components/PdfViewer";
import { Header } from "../components/Layout";
import { ACCEPT, Dropzone, JobResult, LoginRequired, ProgressBar } from "../components/ui";
import { PANELS, CENTER_PANELS } from "../panels";

export interface ViewerConfig {
  mode?: Mode;
  shapes?: Shape[];
  onRect?: (page: number, rect: number[]) => void;
  onPoint?: (page: number, x: number, y: number) => void;
  onInk?: (page: number, stroke: number[][]) => void;
  onLine?: (page: number, from: number[], to: number[]) => void;
  onPoly?: (page: number, pts: number[][]) => void;
  onShapeClick?: (s: Shape) => void;
}

export interface EditorCtx {
  tool: ToolDef;
  file: FileInfo | null;
  files: FileInfo[]; // for multi-file tools
  setFiles: (f: FileInfo[]) => void;
  pages: PageSize[];
  busy: boolean;
  /** Run a backend tool on the current file (or given file ids). Versioned PDF results become the new current file. */
  run: (backend: string, params?: Record<string, unknown>, fileIds?: string[]) => Promise<Job | null>;
  openFile: (f: FileInfo) => void;
  goTo: (page: number) => void;
  handlers: MutableRefObject<ViewerConfig>;
  setView: (v: { mode: Mode; shapes: Shape[] }) => void;
  refreshKey: number;
}

const Ctx = createContext<EditorCtx>(null as unknown as EditorCtx);
export const useEditor = () => useContext(Ctx);

/** Panels call this every render to configure the center viewer (mode, overlay shapes, handlers). */
export function useViewer(cfg: ViewerConfig) {
  const ctx = useEditor();
  ctx.handlers.current = cfg;
  const key = JSON.stringify([cfg.mode, cfg.shapes]);
  useEffect(() => {
    ctx.setView({ mode: cfg.mode || "none", shapes: cfg.shapes || [] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
}

export default function Editor() {
  const { toolId = "view" } = useParams();
  const [search, setSearch] = useSearchParams();
  const nav = useNavigate();
  const { user, toast, aiEnabled } = useApp();
  const tool = TOOL_BY_ID[toolId] || TOOL_BY_ID.view;

  const [history, setHistory] = useState<FileInfo[]>([]);
  const [index, setIndex] = useState(-1);
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [pages, setPages] = useState<PageSize[]>([]);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<{ pct: number; msg: string } | null>(null);
  const [lastJob, setLastJob] = useState<Job | null>(null);
  const [view, setView] = useState<{ mode: Mode; shapes: Shape[] }>({ mode: "none", shapes: [] });
  const [goToState, setGoTo] = useState<{ page: number; nonce: number } | undefined>();
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const handlers = useRef<ViewerConfig>({});
  const file = index >= 0 ? history[index] : null;
  const single = ["pdf", "pdf-or-image"].includes(tool.input);

  // Load the file named in the URL (?file=id) when arriving from the home page or switching tools.
  const fileParam = search.get("file");
  useEffect(() => {
    if (!fileParam || file?.id === fileParam) return;
    api<FileInfo>(`/api/files/${fileParam}`)
      .then((f) => {
        setHistory([f]);
        setIndex(0);
        if (!single) setFiles([f]);
      })
      .catch((e) => toast(e.message, "error"));
  }, [fileParam]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => setLastJob(null), [toolId]);

  const pushVersion = useCallback(
    (f: FileInfo) => {
      setHistory((h) => [...h.slice(0, index + 1), f]);
      setIndex((i) => i + 1);
      setSearch((s) => {
        s.set("file", f.id);
        return s;
      }, { replace: true });
    },
    [index, setSearch],
  );

  const undo = () => index > 0 && (setIndex(index - 1), setSearch({ file: history[index - 1].id }, { replace: true }));
  const redo = () => index < history.length - 1 && (setIndex(index + 1), setSearch({ file: history[index + 1].id }, { replace: true }));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || (e.target as HTMLElement)?.tagName?.match(/INPUT|TEXTAREA|SELECT/)) return;
      if (e.key.toLowerCase() === "z" && !e.shiftKey) { e.preventDefault(); undo(); }
      if (e.key.toLowerCase() === "y" || (e.key.toLowerCase() === "z" && e.shiftKey)) { e.preventDefault(); redo(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const run = useCallback(
    async (backend: string, params: Record<string, unknown> = {}, fileIds?: string[]) => {
      const ids = fileIds ?? (file ? [file.id] : []);
      setBusy(true);
      setLastJob(null);
      setProgress({ pct: 1, msg: "Starting" });
      try {
        const job = await runTool(backend, ids, params, (pct, msg) => setProgress({ pct, msg }));
        const out = job.result?.files || [];
        if (file && out.length === 1 && out[0].kind === "pdf" && out[0].parent_id === file.id) {
          pushVersion(out[0]);
          toast("Done. Use Undo to revert.", "success");
        } else {
          setLastJob(job);
          toast("Done.", "success");
        }
        return job;
      } catch (e: any) {
        toast(e.message || "Something went wrong.", "error");
        return null;
      } finally {
        setBusy(false);
        setProgress(null);
      }
    },
    [file, pushVersion, toast],
  );

  const onUpload = async (picked: File[]) => {
    setUploadPct(0);
    try {
      const res = await uploadFiles(picked, setUploadPct);
      const uploaded: FileInfo[] = res.files;
      if (single) {
        setHistory([uploaded[0]]);
        setIndex(0);
        setSearch({ file: uploaded[0].id }, { replace: true });
      } else {
        setFiles((f) => [...f, ...uploaded]);
      }
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setUploadPct(null);
    }
  };

  const ctx: EditorCtx = useMemo(
    () => ({
      tool, file, files, setFiles, pages, busy, run,
      openFile: (f: FileInfo) => { if (single || tool.panel === "compare") pushVersion(f); else nav(`/tool/view?file=${f.id}`); },
      goTo: (page: number) => setGoTo({ page, nonce: Date.now() }),
      handlers, setView, refreshKey: index,
    }),
    [tool, file, files, pages, busy, run, pushVersion, index, single, nav],
  );

  const Panel = PANELS[tool.panel];
  const Center = CENTER_PANELS[tool.panel];
  const sameCategory = TOOLS.filter((t) => t.category === tool.category && (!t.ai || aiEnabled));
  const needsFile = single && !file;
  const blocked = tool.login && !user;
  const switchTool = (t: ToolDef) => nav(`/tool/${t.id}${file ? `?file=${file.id}` : ""}`);

  let center: ReactNode;
  if (needsFile)
    center = (
      <div className="mx-auto mt-10 max-w-xl p-4">
        <h1 className="mb-1 text-2xl font-bold">{tool.title}</h1>
        <p className="mb-6 text-slate-500">{tool.desc}</p>
        <Dropzone onFiles={onUpload} accept={tool.input === "pdf-or-image" ? `${ACCEPT.pdf},${ACCEPT.images}` : ACCEPT.pdf} />
        {uploadPct !== null && <div className="mt-4"><ProgressBar value={uploadPct} label="Uploading" /></div>}
      </div>
    );
  else if (Center) center = <Center key={tool.id} />;
  else if (single && file)
    center = (
      <PdfViewer
        key={file.id}
        fileId={file.id}
        mode={view.mode}
        shapes={view.shapes}
        goTo={goToState}
        onLoaded={setPages}
        onRect={(p, r) => handlers.current.onRect?.(p, r)}
        onPoint={(p, x, y) => handlers.current.onPoint?.(p, x, y)}
        onInk={(p, s) => handlers.current.onInk?.(p, s)}
        onLine={(p, a, b) => handlers.current.onLine?.(p, a, b)}
        onPoly={(p, pts) => handlers.current.onPoly?.(p, pts)}
        onShapeClick={handlers.current.onShapeClick ? (s) => handlers.current.onShapeClick?.(s) : undefined}
      />
    );
  else center = <MultiFiles onUpload={onUpload} uploadPct={uploadPct} />;

  return (
    <Ctx.Provider value={ctx}>
      <div className="flex h-screen flex-col">
        <Header />
        <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-900">
          <Link to="/" className="btn-ghost px-2" title="All tools"><ArrowLeft size={18} /></Link>
          <tool.icon size={18} className="text-brand-600" />
          <span className="font-semibold">{tool.title}</span>
          {file && <span className="hidden truncate text-sm text-slate-500 sm:inline">· {file.name}</span>}
          {file && single && (
            <div className="ml-auto flex items-center gap-1">
              <button className="btn-ghost px-2" onClick={undo} disabled={index <= 0 || busy} title="Undo (Ctrl+Z)"><Undo2 size={18} /></button>
              <button className="btn-ghost px-2" onClick={redo} disabled={index >= history.length - 1 || busy} title="Redo (Ctrl+Y)"><Redo2 size={18} /></button>
              {user && (
                <button
                  className="btn-ghost px-2"
                  title="Save to My documents"
                  onClick={() => api(`/api/files/${file.id}`, { method: "PATCH", json: { is_saved: true } }).then(() => toast("Saved to My documents", "success")).catch((e) => toast(e.message, "error"))}
                >
                  <Save size={18} />
                </button>
              )}
              <button className="btn-primary" onClick={() => downloadFile(file).catch((e) => toast(e.message, "error"))}>
                <Download size={16} /> <span className="hidden sm:inline">Download</span>
              </button>
            </div>
          )}
        </div>
        <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
          {/* Left tool bar (horizontal on small screens) */}
          <nav className="flex shrink-0 gap-1 overflow-x-auto border-b border-slate-200 bg-white p-1.5 dark:border-slate-800 dark:bg-slate-900 lg:w-16 lg:flex-col lg:overflow-y-auto lg:border-b-0 lg:border-r" aria-label="Tools">
            <Link to="/" className="btn-ghost shrink-0 flex-col gap-0.5 px-2 py-1.5 text-[10px]" title="All tools"><Home size={18} />Home</Link>
            {sameCategory.map((t) => (
              <button key={t.id} onClick={() => switchTool(t)} title={t.title}
                className={`btn shrink-0 flex-col gap-0.5 px-2 py-1.5 text-[10px] leading-tight ${t.id === tool.id ? "bg-brand-100 text-brand-700 dark:bg-brand-700/30 dark:text-white" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"}`}>
                <t.icon size={18} />
                <span className="w-12 truncate">{t.short || t.title.split(" ")[0]}</span>
              </button>
            ))}
          </nav>
          <section className="relative min-h-[50vh] min-w-0 flex-1 lg:min-h-0">
            {center}
            {progress && !Panel && (
              <div className="absolute inset-x-4 bottom-4 rounded-xl bg-white p-3 shadow-lg dark:bg-slate-900">
                <ProgressBar value={progress.pct} label={progress.msg} />
              </div>
            )}
          </section>
          {Panel && (
            <aside className="w-full shrink-0 overflow-y-auto border-t border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 lg:w-[340px] lg:border-l lg:border-t-0">
              <h2 className="mb-1 font-semibold">{tool.title}</h2>
              <p className="mb-4 text-sm text-slate-500">{tool.desc}</p>
              {blocked ? (
                <LoginRequired what="use this feature" />
              ) : needsFile ? (
                <p className="text-sm text-slate-500">Upload a file to get started.</p>
              ) : (
                <Panel key={tool.id} />
              )}
              {progress && <div className="mt-4"><ProgressBar value={progress.pct} label={progress.msg} /></div>}
              {lastJob && (
                <div className="mt-4 border-t border-slate-200 pt-4 dark:border-slate-800">
                  <h3 className="mb-2 text-sm font-semibold">Result</h3>
                  <JobResult job={lastJob} onOpen={(f) => nav(`/tool/view?file=${f.id}`)} />
                </div>
              )}
            </aside>
          )}
        </div>
      </div>
    </Ctx.Provider>
  );
}

/** Center view for multi-file tools: ordered list with add / remove / reorder. */
function MultiFiles({ onUpload, uploadPct }: { onUpload: (f: File[]) => void; uploadPct: number | null }) {
  const { tool, files, setFiles } = useEditor();
  const accept = tool.input === "images" ? ACCEPT.images : tool.input === "office" ? ACCEPT.office : tool.input === "batch" ? ACCEPT.any : `${ACCEPT.pdf},${ACCEPT.images}`;
  const move = (i: number, d: number) => {
    const next = [...files];
    const j = i + d;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    setFiles(next);
  };
  if (tool.input === "none") return <div className="p-8 text-slate-500">Fill in the options on the right.</div>;
  return (
    <div className="mx-auto max-w-2xl space-y-4 overflow-y-auto p-4">
      <h1 className="text-2xl font-bold">{tool.title}</h1>
      <p className="text-slate-500">{tool.desc}</p>
      <Dropzone onFiles={onUpload} multiple accept={accept} label="Drop files here or click to add" />
      {uploadPct !== null && <ProgressBar value={uploadPct} label="Uploading" />}
      <ol className="space-y-2">
        {files.map((f, i) => (
          <li key={f.id + i} className="card flex items-center gap-2 p-2 text-sm">
            <span className="w-6 text-center text-slate-400">{i + 1}</span>
            <span className="min-w-0 flex-1 truncate">{f.name}</span>
            <button className="btn-ghost px-2" onClick={() => move(i, -1)} aria-label="Move up">↑</button>
            <button className="btn-ghost px-2" onClick={() => move(i, 1)} aria-label="Move down">↓</button>
            <button className="btn-ghost px-2 text-red-600" onClick={() => setFiles(files.filter((_, k) => k !== i))} aria-label="Remove">✕</button>
          </li>
        ))}
      </ol>
    </div>
  );
}
