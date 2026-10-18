// Create a signature by drawing, typing or uploading an image. Produces a transparent PNG data URL.
import { useEffect, useRef, useState } from "react";
import { Eraser } from "lucide-react";

/** Crop transparent margins so the placed signature fills its box. */
function trimmed(src: HTMLCanvasElement): string {
  const { width, height } = src;
  const data = src.getContext("2d")!.getImageData(0, 0, width, height).data;
  let x0 = width, y0 = height, x1 = -1, y1 = -1;
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++)
      if (data[(y * width + x) * 4 + 3] > 10) {
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      }
  if (x1 < 0) return src.toDataURL("image/png");
  const pad = 6;
  x0 = Math.max(0, x0 - pad); y0 = Math.max(0, y0 - pad);
  x1 = Math.min(width - 1, x1 + pad); y1 = Math.min(height - 1, y1 + pad);
  const out = document.createElement("canvas");
  out.width = x1 - x0 + 1;
  out.height = y1 - y0 + 1;
  out.getContext("2d")!.drawImage(src, x0, y0, out.width, out.height, 0, 0, out.width, out.height);
  return out.toDataURL("image/png");
}

const FONTS = ["'Brush Script MT', cursive", "'Segoe Script', cursive", "'Lucida Handwriting', cursive", "cursive"];

export default function SignaturePad({ onChange }: { onChange: (dataUrl: string | null) => void }) {
  const [tab, setTab] = useState<"draw" | "type" | "upload">("draw");
  const [typed, setTyped] = useState("");
  const [font, setFont] = useState(FONTS[0]);
  const [color, setColor] = useState("#1e3a8a");
  const canvas = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const dirty = useRef(false);

  const ctx = () => canvas.current!.getContext("2d")!;
  const clear = () => {
    const c = canvas.current;
    if (!c) return;
    ctx().clearRect(0, 0, c.width, c.height);
    dirty.current = false;
    onChange(null);
  };

  useEffect(() => {
    if (tab !== "type") return;
    if (!typed.trim()) return onChange(null);
    const c = document.createElement("canvas");
    c.width = 600;
    c.height = 160;
    const x = c.getContext("2d")!;
    x.fillStyle = color;
    x.font = `64px ${font}`;
    x.textBaseline = "middle";
    const w = Math.min(580, x.measureText(typed).width);
    x.fillText(typed, (600 - w) / 2, 85, 580);
    onChange(trimmed(c));
  }, [typed, font, color, tab]); // eslint-disable-line react-hooks/exhaustive-deps

  const pos = (e: React.PointerEvent) => {
    const r = canvas.current!.getBoundingClientRect();
    return [((e.clientX - r.left) / r.width) * canvas.current!.width, ((e.clientY - r.top) / r.height) * canvas.current!.height];
  };

  return (
    <div className="space-y-2">
      <div className="flex gap-1 rounded-lg bg-slate-100 p-1 text-sm dark:bg-slate-800">
        {(["draw", "type", "upload"] as const).map((t) => (
          <button key={t} className={`flex-1 rounded-md py-1.5 capitalize ${tab === t ? "bg-white shadow dark:bg-slate-700" : ""}`} onClick={() => { setTab(t); onChange(null); }}>
            {t}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2 text-xs">
        Ink <input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-6 w-10" />
      </div>
      {tab === "draw" && (
        <div>
          <canvas
            ref={canvas}
            width={600}
            height={200}
            className="h-36 w-full touch-none rounded-lg border border-slate-300 bg-white dark:border-slate-700"
            onPointerDown={(e) => {
              drawing.current = true;
              (e.target as Element).setPointerCapture(e.pointerId);
              const [x, y] = pos(e);
              const c = ctx();
              c.strokeStyle = color;
              c.lineWidth = 3.5;
              c.lineCap = "round";
              c.lineJoin = "round";
              c.beginPath();
              c.moveTo(x, y);
            }}
            onPointerMove={(e) => {
              if (!drawing.current) return;
              const [x, y] = pos(e);
              ctx().lineTo(x, y);
              ctx().stroke();
              dirty.current = true;
            }}
            onPointerUp={() => {
              drawing.current = false;
              if (dirty.current) onChange(trimmed(canvas.current!));
            }}
          />
          <button className="btn-ghost mt-1 text-xs" onClick={clear}><Eraser size={14} /> Clear</button>
        </div>
      )}
      {tab === "type" && (
        <div className="space-y-2">
          <input className="input" placeholder="Type your name" value={typed} onChange={(e) => setTyped(e.target.value)} />
          <div className="grid grid-cols-2 gap-1">
            {FONTS.map((f) => (
              <button key={f} className={`rounded border px-2 py-1 text-xl ${font === f ? "border-brand-500" : "border-slate-300 dark:border-slate-700"}`} style={{ fontFamily: f, color }} onClick={() => setFont(f)}>
                {typed || "Signature"}
              </button>
            ))}
          </div>
        </div>
      )}
      {tab === "upload" && (
        <input
          type="file"
          accept="image/png,image/jpeg"
          className="block w-full text-sm"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            if (f.size > 3 * 1024 * 1024) return alert("Please choose an image under 3 MB.");
            const reader = new FileReader();
            reader.onload = () => onChange(reader.result as string);
            reader.readAsDataURL(f);
          }}
        />
      )}
    </div>
  );
}
