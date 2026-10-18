import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { inspect } from "../lib/api";
import { useApp } from "../lib/app-context";
import { TOOLS } from "../lib/tools";
import { useEditor, useViewer } from "../pages/Editor";
import { defaults, FieldInput, toParams } from "../components/ui";

/** Generic options form for tools described by field definitions in lib/tools.ts. */
export function FormPanel() {
  const { tool, file, files, run, busy } = useEditor();
  const { toast } = useApp();
  const [values, setValues] = useState<Record<string, any>>(() => defaults(tool.fields));
  useViewer({});

  const ids = tool.input === "none" ? [] : ["pdf", "pdf-or-image"].includes(tool.input) ? (file ? [file.id] : []) : files.map((f) => f.id);
  const minFiles = tool.input === "pdfs" ? 2 : tool.input === "none" ? 0 : 1;

  const submit = () => {
    if (ids.length < minFiles) return toast(minFiles > 1 ? `Add at least ${minFiles} files.` : "Add a file first.", "error");
    run(tool.backend!, toParams(tool.fields, values), ids);
  };

  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); submit(); }}>
      {(tool.fields || []).filter((f) => !f.showIf || f.showIf(values)).map((f) => (
        <FieldInput key={f.key} field={f} value={values[f.key]} onChange={(v) => setValues((s) => ({ ...s, [f.key]: v }))} />
      ))}
      <button type="submit" className="btn-primary w-full" disabled={busy}>{tool.runLabel || "Apply"}</button>
    </form>
  );
}

/** Viewer side panel: document info and shortcuts to common tools. */
export function ViewPanel() {
  const { file, pages } = useEditor();
  const [meta, setMeta] = useState<Record<string, string>>({});
  useViewer({});
  useEffect(() => {
    if (file) inspect(file.id, "info").then((i) => setMeta(i.metadata || {})).catch(() => undefined);
  }, [file?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const quick = ["organize", "edit_text", "annotate", "sign", "compress", "ocr", "redact", "pdf_to_word"];
  return (
    <div className="space-y-4 text-sm">
      <dl className="grid grid-cols-3 gap-1">
        <dt className="text-slate-500">Pages</dt><dd className="col-span-2">{pages.length}</dd>
        {["title", "author", "subject", "keywords", "producer"].map((k) => meta[k] ? (
          <div key={k} className="contents"><dt className="capitalize text-slate-500">{k}</dt><dd className="col-span-2 break-words">{meta[k]}</dd></div>
        ) : null)}
      </dl>
      <div>
        <h3 className="label">Continue with</h3>
        <div className="grid grid-cols-2 gap-2">
          {quick.map((id) => {
            const t = TOOLS.find((x) => x.id === id)!;
            return (
              <Link key={id} to={`/tool/${id}?file=${file?.id}`} className="btn-secondary justify-start text-xs">
                <t.icon size={14} /> {t.title}
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export function MetadataPanel() {
  const { file, run, busy } = useEditor();
  const [m, setM] = useState({ title: "", author: "", subject: "", keywords: "", creator: "" });
  useViewer({});
  useEffect(() => {
    if (!file) return;
    inspect(file.id, "info").then((i) => setM((s) => ({ ...s, ...Object.fromEntries(Object.keys(s).map((k) => [k, i.metadata?.[k] || ""])) })));
  }, [file?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); run("set_metadata", m); }}>
      {(Object.keys(m) as (keyof typeof m)[]).map((k) => (
        <div key={k}>
          <label className="label capitalize">{k}</label>
          <input className="input" value={m[k]} onChange={(e) => setM({ ...m, [k]: e.target.value })} />
        </div>
      ))}
      <button className="btn-primary w-full" disabled={busy}>Save metadata</button>
    </form>
  );
}

export function CropPanel() {
  const { run, busy } = useEditor();
  const [box, setBox] = useState<{ page: number; rect: number[] } | null>(null);
  const [margins, setMargins] = useState({ left: 0, top: 0, right: 0, bottom: 0 });
  const [pages, setPages] = useState("all");
  useViewer({
    mode: "rect",
    shapes: box ? [{ page: box.page, kind: "rect", rect: box.rect, color: "#16a34a", fill: "#16a34a22", label: "Crop area", dashed: true }] : [],
    onRect: (page, rect) => setBox({ page, rect }),
  });
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-500">Drag on a page to draw the area to keep, or enter margins (points, 72 = 1 inch) below.</p>
      {box && (
        <div className="rounded-lg bg-emerald-50 p-2 text-xs dark:bg-emerald-950">
          Crop box drawn on page {box.page + 1}. <button className="underline" onClick={() => setBox(null)}>Clear</button>
        </div>
      )}
      {!box && (
        <div className="grid grid-cols-2 gap-2">
          {(Object.keys(margins) as (keyof typeof margins)[]).map((k) => (
            <div key={k}>
              <label className="label capitalize">{k}</label>
              <input type="number" min={0} className="input" value={margins[k]} onChange={(e) => setMargins({ ...margins, [k]: Number(e.target.value) })} />
            </div>
          ))}
        </div>
      )}
      <div>
        <label className="label">Apply to pages</label>
        <input className="input" value={pages} onChange={(e) => setPages(e.target.value)} placeholder="all, 1-3" />
      </div>
      <button className="btn-primary w-full" disabled={busy} onClick={() => run("crop", box ? { rect: box.rect, pages } : { ...margins, pages }).then(() => setBox(null))}>
        Crop
      </button>
    </div>
  );
}
