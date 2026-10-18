// PDF viewer built on pdf.js: lazy page rendering, thumbnails, zoom, search and an interaction
// overlay. All coordinates exchanged with panels are PDF points in the *visible* page space
// (origin top-left, rotation applied) - the same space the backend expects.
import { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Loader2, Maximize2, PanelLeft, Search, ZoomIn, ZoomOut } from "lucide-react";
import { fetchBytes, fileBytes, inspect } from "../lib/api";
import { loadPdf, PDFDoc, renderPage } from "../lib/pdf";

export interface Shape {
  page: number;
  kind: "rect" | "point" | "line" | "poly" | "ink";
  rect?: number[];
  points?: number[][];
  strokes?: number[][][];
  color?: string;
  fill?: string;
  label?: string;
  id?: string | number;
  dashed?: boolean;
  closed?: boolean;
}

export type Mode = "none" | "rect" | "point" | "ink" | "line" | "poly";

export interface PageSize {
  width: number;
  height: number;
}

interface Props {
  fileId?: string;
  publicUrl?: string; // for review / signing pages that load without auth
  mode?: Mode;
  shapes?: Shape[];
  onRect?: (page: number, rect: number[]) => void;
  onPoint?: (page: number, x: number, y: number) => void;
  onInk?: (page: number, stroke: number[][]) => void;
  onLine?: (page: number, from: number[], to: number[]) => void;
  onPoly?: (page: number, points: number[][]) => void;
  onShapeClick?: (shape: Shape) => void;
  onLoaded?: (pages: PageSize[]) => void;
  goTo?: { page: number; nonce: number };
  toolbarExtra?: ReactNode;
  thumbnails?: boolean;
  search?: boolean;
}

const MIN_ZOOM = 0.25;
const MAX_ZOOM = 4;

export default function PdfViewer(props: Props) {
  const { fileId, publicUrl, thumbnails = true, search = true } = props;
  const [doc, setDoc] = useState<PDFDoc | null>(null);
  const [sizes, setSizes] = useState<PageSize[]>([]);
  const [error, setError] = useState("");
  const [zoom, setZoom] = useState(1);
  const [showThumbs, setShowThumbs] = useState(() => window.innerWidth >= 1024);
  const [current, setCurrent] = useState(0);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<{ page: number; bbox: number[] }[]>([]);
  const [hitIndex, setHitIndex] = useState(0);
  const scroller = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<(HTMLDivElement | null)[]>([]);

  // Load the document whenever the file (version) changes.
  useEffect(() => {
    let cancelled = false;
    let loaded: PDFDoc | null = null;
    setError("");
    setHits([]);
    (async () => {
      try {
        const data = publicUrl ? await fetchBytes(publicUrl, true) : fileId ? await fileBytes(fileId) : null;
        if (!data || cancelled) return;
        loaded = await loadPdf(data);
        const s: PageSize[] = [];
        for (let i = 1; i <= loaded.numPages; i++) {
          const vp = (await loaded.getPage(i)).getViewport({ scale: 1 });
          s.push({ width: vp.width, height: vp.height });
        }
        if (cancelled) return;
        setSizes(s);
        setDoc((old) => {
          old?.destroy();
          return loaded;
        });
        props.onLoaded?.(s);
      } catch (e: any) {
        if (!cancelled) setError(e?.message?.includes("password") ? "This PDF is password protected." : e?.message || "Could not open this PDF.");
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId, publicUrl]);

  useEffect(() => () => void doc?.destroy(), [doc]);

  const fitWidth = useCallback(() => {
    if (!scroller.current || !sizes.length) return;
    const avail = scroller.current.clientWidth - 48;
    const widest = Math.max(...sizes.map((s) => s.width));
    setZoom(Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, avail / widest)));
  }, [sizes]);

  // Fit to width on first load and on small screens.
  useEffect(() => {
    if (sizes.length) fitWidth();
  }, [sizes.length > 0]); // eslint-disable-line react-hooks/exhaustive-deps

  const scrollTo = useCallback((page: number) => {
    pageRefs.current[page]?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  useEffect(() => {
    if (props.goTo) scrollTo(props.goTo.page);
  }, [props.goTo, scrollTo]);

  // Track which page is in view (for the page indicator and thumbnails).
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const onScroll = () => {
      const mid = el.scrollTop + el.clientHeight / 3;
      let idx = 0;
      pageRefs.current.forEach((p, i) => {
        if (p && p.offsetTop <= mid) idx = i;
      });
      setCurrent(idx);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [sizes]);

  const runSearch = async () => {
    if (!fileId || !query.trim()) {
      setHits([]);
      return;
    }
    const res = await inspect<{ page: number; bbox: number[] }[]>(fileId, "search", 0, query.trim());
    setHits(res);
    setHitIndex(0);
    if (res.length) scrollTo(res[0].page);
  };

  const step = (d: number) => {
    if (!hits.length) return;
    const i = (hitIndex + d + hits.length) % hits.length;
    setHitIndex(i);
    scrollTo(hits[i].page);
  };

  const allShapes = useMemo(() => {
    const s: Shape[] = [...(props.shapes || [])];
    hits.forEach((h, i) => s.push({ page: h.page, kind: "rect", rect: h.bbox, color: i === hitIndex ? "#f97316" : "#facc15", fill: i === hitIndex ? "#f9731655" : "#facc1555" }));
    return s;
  }, [props.shapes, hits, hitIndex]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center gap-1 border-b border-slate-200 bg-white px-2 py-1.5 dark:border-slate-800 dark:bg-slate-900">
        {thumbnails && (
          <button className="btn-ghost px-2" title="Toggle page thumbnails" onClick={() => setShowThumbs((v) => !v)}>
            <PanelLeft size={18} />
          </button>
        )}
        <button className="btn-ghost px-2" title="Zoom out" onClick={() => setZoom((z) => Math.max(MIN_ZOOM, z / 1.2))}>
          <ZoomOut size={18} />
        </button>
        <span className="w-12 text-center text-xs tabular-nums">{Math.round(zoom * 100)}%</span>
        <button className="btn-ghost px-2" title="Zoom in" onClick={() => setZoom((z) => Math.min(MAX_ZOOM, z * 1.2))}>
          <ZoomIn size={18} />
        </button>
        <button className="btn-ghost px-2" title="Fit width" onClick={fitWidth}>
          <Maximize2 size={16} />
        </button>
        <span className="mx-2 text-xs text-slate-500">
          {sizes.length ? `Page ${current + 1} / ${sizes.length}` : ""}
        </span>
        {search && fileId && (
          <div className="ml-auto flex items-center gap-1">
            <div className="relative">
              <Search size={14} className="absolute left-2 top-2.5 text-slate-400" />
              <input
                className="input w-36 py-1.5 pl-7 sm:w-48"
                placeholder="Search text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && runSearch()}
                aria-label="Search text in document"
              />
            </div>
            {hits.length > 0 && <span className="text-xs text-slate-500">{hitIndex + 1}/{hits.length}</span>}
            <button className="btn-ghost px-1.5" onClick={() => step(-1)} title="Previous match"><ChevronUp size={16} /></button>
            <button className="btn-ghost px-1.5" onClick={() => step(1)} title="Next match"><ChevronDown size={16} /></button>
          </div>
        )}
        {props.toolbarExtra}
      </div>
      <div className="flex min-h-0 flex-1">
        {thumbnails && showThumbs && doc && (
          <Thumbnails doc={doc} sizes={sizes} current={current} onPick={scrollTo} />
        )}
        <div ref={scroller} className="relative min-w-0 flex-1 overflow-auto bg-slate-200/70 p-4 dark:bg-slate-950">
          {error && <div className="mx-auto mt-10 max-w-md rounded-lg bg-red-50 p-4 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{error}</div>}
          {!doc && !error && (
            <div className="flex h-full items-center justify-center text-slate-500">
              <Loader2 className="mr-2 animate-spin" /> Loading document...
            </div>
          )}
          {doc &&
            sizes.map((size, i) => (
              <div key={i} ref={(el) => (pageRefs.current[i] = el)} className="mx-auto mb-4 w-fit">
                <PageView
                  {...props}
                  doc={doc}
                  index={i}
                  size={size}
                  zoom={zoom}
                  shapes={allShapes.filter((s) => s.page === i)}
                />
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}

function Thumbnails({ doc, sizes, current, onPick }: { doc: PDFDoc; sizes: PageSize[]; current: number; onPick: (i: number) => void }) {
  return (
    <div className="hidden w-36 shrink-0 overflow-y-auto border-r border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-900 md:block">
      {sizes.map((s, i) => (
        <button key={i} onClick={() => onPick(i)} className={`mb-2 block w-full rounded p-1 text-center ${i === current ? "bg-brand-100 ring-2 ring-brand-500 dark:bg-brand-700/30" : "hover:bg-slate-100 dark:hover:bg-slate-800"}`}>
          <LazyCanvas doc={doc} index={i} scale={110 / s.width} />
          <span className="text-xs text-slate-500">{i + 1}</span>
        </button>
      ))}
    </div>
  );
}

export function LazyCanvas({ doc, index, scale, className = "" }: { doc: PDFDoc; index: number; scale: number; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setVisible(true), { rootMargin: "200px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  useEffect(() => {
    if (!visible || !ref.current) return;
    let task: ReturnType<typeof renderPage> | null = null;
    let cancelled = false;
    doc.getPage(index + 1).then((page) => {
      if (cancelled || !ref.current) return;
      task = renderPage(page, ref.current, scale);
      task.promise.catch(() => undefined);
    });
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [visible, doc, index, scale]);
  return <canvas ref={ref} className={`mx-auto block bg-white shadow ${className}`} />;
}

interface PageProps extends Props {
  doc: PDFDoc;
  index: number;
  size: PageSize;
  zoom: number;
  shapes: Shape[];
}

function PageView({ doc, index, size, zoom, shapes, mode = "none", ...cb }: PageProps) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const holder = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [draft, setDraft] = useState<{ start: number[]; end: number[] } | null>(null);
  const [stroke, setStroke] = useState<number[][] | null>(null);
  const [poly, setPoly] = useState<number[][]>([]);

  useEffect(() => {
    const el = holder.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { rootMargin: "600px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!visible || !canvas.current) return;
    let cancelled = false;
    let renderTask: ReturnType<typeof renderPage> | null = null;
    const timer = setTimeout(async () => {
      const page = await doc.getPage(index + 1);
      if (cancelled || !canvas.current) return;
      renderTask = renderPage(page, canvas.current, zoom);
      renderTask.promise.catch(() => undefined); // cancelled renders reject; that's expected
    }, 30);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      renderTask?.cancel();
    };
  }, [visible, zoom, doc, index]);

  useEffect(() => setPoly([]), [mode]);

  const toPdf = (e: React.PointerEvent | React.MouseEvent): number[] => {
    const r = (e.currentTarget as SVGElement).getBoundingClientRect();
    return [((e.clientX - r.left) / r.width) * size.width, ((e.clientY - r.top) / r.height) * size.height].map((v) => Math.round(v * 100) / 100);
  };

  const onDown = (e: React.PointerEvent) => {
    if (mode === "none" || mode === "poly") return;
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    const p = toPdf(e);
    if (mode === "ink") setStroke([p]);
    else setDraft({ start: p, end: p });
  };
  const onMove = (e: React.PointerEvent) => {
    if (stroke) setStroke((s) => (s ? [...s, toPdf(e)] : s));
    else if (draft) setDraft({ ...draft, end: toPdf(e) });
  };
  const onUp = (e: React.PointerEvent) => {
    const p = toPdf(e);
    if (stroke) {
      if (stroke.length > 1) cb.onInk?.(index, [...stroke, p]);
      setStroke(null);
      return;
    }
    if (!draft) return;
    const [x0, y0] = draft.start;
    const moved = Math.hypot(p[0] - x0, p[1] - y0) > 4;
    if (mode === "rect") {
      if (moved) cb.onRect?.(index, [Math.min(x0, p[0]), Math.min(y0, p[1]), Math.max(x0, p[0]), Math.max(y0, p[1])]);
      else cb.onPoint?.(index, x0, y0);
    } else if (mode === "point") cb.onPoint?.(index, p[0], p[1]);
    else if (mode === "line" && moved) cb.onLine?.(index, draft.start, p);
    setDraft(null);
  };
  const onClick = (e: React.MouseEvent) => {
    if (mode !== "poly") return;
    setPoly((pts) => [...pts, toPdf(e)]);
  };
  const onDouble = () => {
    if (mode === "poly" && poly.length >= 2) {
      cb.onPoly?.(index, poly.slice(0, -1).length >= 2 ? poly.slice(0, -1) : poly);
      setPoly([]);
    }
  };

  const w = size.width * zoom;
  const h = size.height * zoom;
  const sw = 1.5 / zoom; // constant on-screen stroke width
  const cursor = mode === "none" ? "default" : mode === "ink" ? "crosshair" : "crosshair";

  return (
    <div ref={holder} className="relative bg-white shadow-md" style={{ width: w, height: h }}>
      <canvas ref={canvas} className="absolute inset-0" style={{ width: w, height: h }} />
      <svg
        className="absolute inset-0 touch-none"
        style={{ cursor }}
        width={w}
        height={h}
        viewBox={`0 0 ${size.width} ${size.height}`}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onClick={onClick}
        onDoubleClick={onDouble}
      >
        {shapes.map((s, i) => (
          <ShapeView key={s.id ?? i} s={s} sw={sw} onClick={cb.onShapeClick && mode === "none" ? () => cb.onShapeClick?.(s) : undefined} />
        ))}
        {draft && mode === "rect" && (
          <rect
            x={Math.min(draft.start[0], draft.end[0])}
            y={Math.min(draft.start[1], draft.end[1])}
            width={Math.abs(draft.end[0] - draft.start[0])}
            height={Math.abs(draft.end[1] - draft.start[1])}
            fill="#3b6cf622"
            stroke="#3b6cf6"
            strokeWidth={sw}
            strokeDasharray={`${4 * sw}`}
          />
        )}
        {draft && mode === "line" && <line x1={draft.start[0]} y1={draft.start[1]} x2={draft.end[0]} y2={draft.end[1]} stroke="#3b6cf6" strokeWidth={sw * 1.5} />}
        {stroke && <polyline points={stroke.map((p) => p.join(",")).join(" ")} fill="none" stroke="#e11d48" strokeWidth={sw * 1.5} />}
        {poly.length > 0 && <polyline points={poly.map((p) => p.join(",")).join(" ")} fill="#3b6cf622" stroke="#3b6cf6" strokeWidth={sw} />}
      </svg>
    </div>
  );
}

function ShapeView({ s, sw, onClick }: { s: Shape; sw: number; onClick?: () => void }) {
  const color = s.color || "#3b6cf6";
  const common = { stroke: color, strokeWidth: sw * 1.4, strokeDasharray: s.dashed ? `${4 * sw}` : undefined, onClick, style: onClick ? { cursor: "pointer" } : undefined };
  let el: ReactNode = null;
  if (s.kind === "rect" && s.rect) {
    const [x0, y0, x1, y1] = s.rect;
    el = <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} fill={s.fill || "transparent"} {...common} pointerEvents={onClick ? "all" : "none"} />;
  } else if (s.kind === "point" && s.points?.[0]) {
    const [x, y] = s.points[0];
    el = <circle cx={x} cy={y} r={6 * sw} fill={s.fill || color} {...common} />;
  } else if (s.kind === "line" && s.points && s.points.length >= 2) {
    el = <line x1={s.points[0][0]} y1={s.points[0][1]} x2={s.points[1][0]} y2={s.points[1][1]} {...common} />;
  } else if (s.kind === "poly" && s.points) {
    const pts = s.points.map((p) => p.join(",")).join(" ");
    el = s.closed ? <polygon points={pts} fill={s.fill || `${color}33`} {...common} /> : <polyline points={pts} fill="none" {...common} />;
  } else if (s.kind === "ink" && s.strokes) {
    el = (
      <g>
        {s.strokes.map((st, i) => (
          <polyline key={i} points={st.map((p) => p.join(",")).join(" ")} fill="none" {...common} />
        ))}
      </g>
    );
  }
  const anchor = s.rect ? [s.rect[0], s.rect[1]] : s.points?.[0];
  return (
    <g>
      {el}
      {s.label && anchor && (
        <text x={anchor[0]} y={anchor[1] - 3 * sw} fontSize={11 * sw} fill={color} style={{ pointerEvents: "none", fontWeight: 600 }}>
          {s.label}
        </text>
      )}
    </g>
  );
}
