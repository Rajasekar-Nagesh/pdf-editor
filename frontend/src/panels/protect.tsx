// Redaction: draw areas, search terms, regex presets (PAN, GSTIN, Aadhaar, phone, email), preview, apply.
import { useState } from "react";
import { REDACT_PRESETS } from "../lib/tools";
import { Shape } from "../components/PdfViewer";
import { useEditor, useViewer } from "../pages/Editor";

export function RedactPanel() {
  const { run, busy } = useEditor();
  const [areas, setAreas] = useState<{ page: number; rect: number[] }[]>([]);
  const [terms, setTerms] = useState("");
  const [presets, setPresets] = useState<string[]>([]);
  const [regex, setRegex] = useState("");
  const [label, setLabel] = useState("");
  const [matches, setMatches] = useState<{ page: number; bbox: number[]; text: string; kind: string }[] | null>(null);

  const termList = terms.split(/[\n,]/).map((t) => t.trim()).filter(Boolean);
  const shapes: Shape[] = [
    ...areas.map((a, i) => ({ page: a.page, kind: "rect" as const, rect: a.rect, color: "#000", fill: "#00000088", id: `a${i}` })),
    ...(matches || []).map((m, i) => ({ page: m.page, kind: "rect" as const, rect: m.bbox, color: "#dc2626", fill: "#dc262644", id: `m${i}` })),
  ];
  useViewer({ mode: "rect", shapes, onRect: (page, rect) => setAreas((a) => [...a, { page, rect }]) });

  const find = async () => {
    const job = await run("find_sensitive", { terms: termList, presets, regex });
    if (job) setMatches(job.result?.data.matches || []);
  };
  const apply = async () => {
    const job = await run("redact", { areas, terms: termList, presets, regex, label });
    if (job) { setAreas([]); setMatches(null); }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500">Drag on the page to black out areas, and/or search for text. Redaction permanently removes the text, images and drawings underneath.</p>
      {areas.length > 0 && <div className="flex justify-between text-sm"><span>{areas.length} area(s)</span><button className="text-xs underline" onClick={() => setAreas(areas.slice(0, -1))}>Undo last</button></div>}
      <div>
        <span className="label">Find automatically</span>
        <div className="flex flex-wrap gap-2">
          {REDACT_PRESETS.map((p) => (
            <label key={p.value} className={`chip cursor-pointer border px-3 py-1 ${presets.includes(p.value) ? "border-red-500 bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-200" : "border-slate-300 dark:border-slate-700"}`}>
              <input type="checkbox" className="sr-only" checked={presets.includes(p.value)} onChange={(e) => setPresets(e.target.checked ? [...presets, p.value] : presets.filter((x) => x !== p.value))} />
              {p.label}
            </label>
          ))}
        </div>
      </div>
      <div><label className="label">Words or phrases (one per line)</label><textarea className="input" value={terms} onChange={(e) => setTerms(e.target.value)} placeholder={"Rajesh Kumar\nAccount 1234"} /></div>
      <div><label className="label">Custom pattern (regular expression)</label><input className="input font-mono" value={regex} onChange={(e) => setRegex(e.target.value)} placeholder="e.g. INV-\d{6}" /></div>
      <div><label className="label">Overlay label (optional)</label><input className="input" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="REDACTED" /></div>
      <button className="btn-secondary w-full" disabled={busy || (!termList.length && !presets.length && !regex)} onClick={find}>Preview matches</button>
      {matches && <p className="text-sm">{matches.length} match(es) highlighted in red.</p>}
      <button className="btn-danger w-full" disabled={busy || (!areas.length && !termList.length && !presets.length && !regex)} onClick={apply}>Apply redaction permanently</button>
    </div>
  );
}
