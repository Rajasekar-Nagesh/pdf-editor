// Small reusable UI pieces: drop zone, progress bar, form fields, image picker, result view.
import { ReactNode, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Download, FileArchive, Info, Loader2, Upload, XCircle } from "lucide-react";
import { downloadFile, FileInfo, formatBytes, Job, uploadOne } from "../lib/api";
import { useApp } from "../lib/app-context";
import { Field, LANGUAGES } from "../lib/tools";

export const ACCEPT = {
  pdf: ".pdf,application/pdf",
  images: "image/*",
  office: ".doc,.docx,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.odp",
  any: ".pdf,image/*,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.odt,.ods,.odp",
};

export function Dropzone({
  onFiles,
  multiple = false,
  accept = ACCEPT.pdf,
  label = "Drop a PDF here or click to choose",
  compact = false,
}: {
  onFiles: (files: File[]) => void;
  multiple?: boolean;
  accept?: string;
  label?: string;
  compact?: boolean;
}) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => input.current?.click()}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const files = Array.from(e.dataTransfer.files);
        if (files.length) onFiles(multiple ? files : files.slice(0, 1));
      }}
      className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed text-center transition ${
        compact ? "p-4" : "p-10"
      } ${over ? "border-brand-500 bg-brand-50 dark:bg-brand-700/10" : "border-slate-300 hover:border-brand-500 dark:border-slate-700"}`}
    >
      <Upload className="mb-2 text-brand-600" size={compact ? 20 : 32} />
      <p className="text-sm font-medium">{label}</p>
      {!compact && <p className="mt-1 text-xs text-slate-500">Up to 100 MB · PDF, Word, Excel, PowerPoint, images</p>}
      <input
        ref={input}
        type="file"
        className="hidden"
        multiple={multiple}
        accept={accept}
        onChange={(e) => {
          const files = Array.from(e.target.files || []);
          if (files.length) onFiles(files);
          e.target.value = "";
        }}
      />
    </div>
  );
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  return (
    <div className="w-full" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <div className="mb-1 flex justify-between text-xs text-slate-500">
        <span className="truncate">{label}</span>
        <span>{Math.round(value)}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
        <div className="h-full rounded-full bg-brand-600 transition-all duration-300" style={{ width: `${Math.max(3, value)}%` }} />
      </div>
    </div>
  );
}

export function Spinner({ text = "Working..." }: { text?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-slate-500">
      <Loader2 size={16} className="animate-spin" /> {text}
    </span>
  );
}

/** Upload an image (or other asset) and return its file id via onChange. */
export function AssetPicker({ value, onChange, accept = ACCEPT.images, label = "Choose image" }: { value?: string; onChange: (id: string | undefined, file?: FileInfo) => void; accept?: string; label?: string }) {
  const { toast } = useApp();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="flex items-center gap-2">
      <button type="button" className="btn-secondary" disabled={busy} onClick={() => input.current?.click()}>
        {busy ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} {label}
      </button>
      {value && (
        <span className="flex min-w-0 items-center gap-1 text-xs">
          <span className="truncate">{name || "Selected"}</span>
          <button type="button" className="text-red-600" onClick={() => { onChange(undefined); setName(""); }} aria-label="Remove">
            <XCircle size={14} />
          </button>
        </span>
      )}
      <input
        ref={input}
        type="file"
        accept={accept}
        className="hidden"
        onChange={async (e) => {
          const f = e.target.files?.[0];
          e.target.value = "";
          if (!f) return;
          setBusy(true);
          try {
            const info = await uploadOne(f);
            setName(info.name);
            onChange(info.id, info);
          } catch (err: any) {
            toast(err.message, "error");
          } finally {
            setBusy(false);
          }
        }}
      />
    </div>
  );
}

export function FieldInput({ field, value, onChange }: { field: Field; value: any; onChange: (v: any) => void }) {
  const id = `f-${field.key}`;
  let control: ReactNode;
  switch (field.type) {
    case "checkbox":
      return (
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={!!value} onChange={(e) => onChange(e.target.checked)} />
          {field.label}
        </label>
      );
    case "select":
      control = (
        <select id={id} className="input" value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
          {field.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      );
      break;
    case "number":
      control = <input id={id} type="number" className="input" value={value ?? ""} min={field.min} max={field.max} step={field.step ?? "any"} onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} />;
      break;
    case "color":
      control = <input id={id} type="color" className="h-10 w-20 cursor-pointer rounded border border-slate-300 dark:border-slate-700" value={value || "#000000"} onChange={(e) => onChange(e.target.value)} />;
      break;
    case "textarea":
      control = <textarea id={id} className="input min-h-[90px]" value={value ?? ""} placeholder={field.placeholder} onChange={(e) => onChange(e.target.value)} />;
      break;
    case "password":
      control = <input id={id} type="password" autoComplete="new-password" className="input" value={value ?? ""} onChange={(e) => onChange(e.target.value)} />;
      break;
    case "image":
      control = <AssetPicker value={value} onChange={(v) => onChange(v)} />;
      break;
    case "langs":
    case "multiselect": {
      const opts = field.type === "langs" ? LANGUAGES : field.options || [];
      const arr: string[] = Array.isArray(value) ? value : [];
      control = (
        <div className="flex flex-wrap gap-2">
          {opts.map((o) => (
            <label key={o.value} className={`chip cursor-pointer border px-3 py-1 ${arr.includes(o.value) ? "border-brand-500 bg-brand-50 text-brand-700 dark:bg-brand-700/20 dark:text-brand-100" : "border-slate-300 dark:border-slate-700"}`}>
              <input type="checkbox" className="sr-only" checked={arr.includes(o.value)} onChange={(e) => onChange(e.target.checked ? [...arr, o.value] : arr.filter((x) => x !== o.value))} />
              {o.label}
            </label>
          ))}
        </div>
      );
      break;
    }
    default:
      control = <input id={id} type="text" className="input" value={value ?? ""} placeholder={field.placeholder} onChange={(e) => onChange(e.target.value)} />;
  }
  return (
    <div>
      <label htmlFor={id} className="label">{field.label}</label>
      {control}
      {field.help && <p className="mt-1 text-xs text-slate-500">{field.help}</p>}
    </div>
  );
}

export function defaults(fields: Field[] = []): Record<string, any> {
  return Object.fromEntries(fields.map((f) => [f.key, f.default ?? (f.type === "checkbox" ? false : "")]));
}

/** Convert form values to API params (drop empty optional images, coerce selects that are numbers). */
export function toParams(fields: Field[] = [], values: Record<string, any>): Record<string, any> {
  const out: Record<string, any> = {};
  for (const f of fields) {
    if (f.showIf && !f.showIf(values)) continue;
    let v = values[f.key];
    if (f.type === "image" && !v) continue;
    if (f.key === "angle") v = Number(v);
    if (f.type === "number" && v === "") continue;
    out[f.key] = v;
  }
  return out;
}

const STATUS_ICON: Record<string, ReactNode> = {
  pass: <CheckCircle2 size={16} className="text-emerald-600" />,
  fail: <XCircle size={16} className="text-red-600" />,
  warn: <AlertTriangle size={16} className="text-amber-500" />,
  info: <Info size={16} className="text-sky-600" />,
};

export function CheckList({ items }: { items: { id: string; title: string; status: string; detail: string }[] }) {
  return (
    <ul className="space-y-2">
      {items.map((i) => (
        <li key={i.id} className="flex gap-2 rounded-lg border border-slate-200 p-2 text-sm dark:border-slate-800">
          <span className="mt-0.5">{STATUS_ICON[i.status] || STATUS_ICON.info}</span>
          <div>
            <div className="font-medium">{i.title}</div>
            <div className="text-xs text-slate-500">{i.detail}</div>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Renders a finished job: download buttons plus tool-specific data. */
export function JobResult({ job, onOpen }: { job: Job; onOpen?: (f: FileInfo) => void }) {
  const { toast } = useApp();
  const r = job.result;
  if (!r) return null;
  const dl = (f: FileInfo) => downloadFile(f).catch((e) => toast(e.message, "error"));
  const d = r.data || {};
  return (
    <div className="space-y-3">
      {r.files.length > 0 && (
        <div className="space-y-2">
          {r.zip && (
            <button className="btn-primary w-full" onClick={() => dl(r.zip!)}>
              <FileArchive size={16} /> Download all ({r.files.length} files, ZIP)
            </button>
          )}
          <ul className="max-h-64 space-y-1 overflow-auto">
            {r.files.map((f) => (
              <li key={f.id} className="flex items-center gap-2 rounded-lg bg-slate-100 px-2 py-1.5 text-sm dark:bg-slate-800">
                <span className="min-w-0 flex-1 truncate" title={f.name}>{f.name}</span>
                <span className="text-xs text-slate-500">{formatBytes(f.size)}</span>
                {onOpen && f.kind === "pdf" && <button className="btn-ghost px-2 py-1 text-xs" onClick={() => onOpen(f)}>Open</button>}
                <button className="btn-ghost px-2 py-1" onClick={() => dl(f)} title="Download"><Download size={14} /></button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {d.before !== undefined && (
        <div className="rounded-lg bg-emerald-50 p-3 text-sm dark:bg-emerald-950">
          <div>Before: <b>{formatBytes(d.before)}</b></div>
          <div>After: <b>{formatBytes(d.after)}</b></div>
          <div>Saved: <b>{d.saved_percent}%</b></div>
        </div>
      )}
      {d.items && <CheckList items={d.items} />}
      {d.checks && <CheckList items={d.checks} />}
      {d.validation && (
        <div className={`rounded-lg p-3 text-sm ${d.validation.compliant ? "bg-emerald-50 dark:bg-emerald-950" : "bg-amber-50 dark:bg-amber-950"}`}>
          <b>veraPDF:</b> {d.validation.message}
          {d.validation.failed_rules?.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-xs">
              {d.validation.failed_rules.slice(0, 20).map((r: any, i: number) => <li key={i}>{r.clause}: {r.description}</li>)}
            </ul>
          )}
        </div>
      )}
      {d.signatures && (
        <div className="space-y-2">
          {d.signatures.length === 0 && <p className="text-sm text-slate-500">No digital signatures found.</p>}
          {d.signatures.map((s: any, i: number) => (
            <div key={i} className="rounded-lg border border-slate-200 p-2 text-sm dark:border-slate-800">
              <div className="font-medium">{s.signer || s.field}</div>
              <div className="text-xs text-slate-500">{s.signing_time ? new Date(s.signing_time).toLocaleString() : ""}</div>
              <div className="mt-1 flex flex-wrap gap-1">
                <span className={`chip ${s.intact ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"}`}>{s.intact ? "Unchanged since signing" : "Modified / broken"}</span>
                <span className={`chip ${s.valid ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"}`}>{s.valid ? "Signature valid" : "Signature invalid"}</span>
                <span className={`chip ${s.trusted ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{s.trusted ? "Trusted certificate" : "Certificate not trusted"}</span>
              </div>
            </div>
          ))}
          {d.note && <p className="text-xs text-slate-500">{d.note}</p>}
        </div>
      )}
      {d.count !== undefined && d.created && <p className="text-sm">Created <b>{d.count}</b> fillable field(s).</p>}
      {d.files && Array.isArray(d.files) && d.files.some((f: any) => f.status === "failed") && (
        <ul className="text-xs text-red-600">
          {d.files.filter((f: any) => f.status === "failed").map((f: any) => <li key={f.name}>{f.name}: {f.error}</li>)}
        </ul>
      )}
      {d.tables !== undefined && <p className="text-sm text-slate-500">{d.tables ? `${d.tables} table(s) found.` : "No ruled tables found - text was exported line by line."}</p>}
    </div>
  );
}

export function LoginRequired({ what }: { what: string }) {
  return (
    <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">
      Please <a className="font-semibold underline" href="/login">log in</a> or <a className="font-semibold underline" href="/signup">create a free account</a> to {what}.
    </div>
  );
}
