// Account dashboard: saved documents, recent files, batch actions, signature requests, review links.
import { useEffect, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { Bell, Download, ExternalLink, FileText, Pencil, Star, Trash2, XCircle } from "lucide-react";
import { api, downloadFile, FileInfo, formatBytes } from "../lib/api";
import { useApp } from "../lib/app-context";
import { Page } from "../components/Layout";
import { Spinner } from "../components/ui";

const TABS = [
  ["saved", "Saved documents"],
  ["recent", "Recent files"],
  ["batch", "Batch actions"],
  ["signatures", "Signature requests"],
  ["reviews", "Review links"],
] as const;

export default function Dashboard() {
  const { user, ready } = useApp();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "saved";
  if (ready && !user) return <Navigate to="/login" replace />;
  return (
    <Page>
      <div className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="mb-4 text-2xl font-bold">My documents</h1>
        <div className="mb-6 flex gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-800">
          {TABS.map(([k, label]) => (
            <button key={k} onClick={() => setParams({ tab: k })} className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${tab === k ? "border-brand-600 text-brand-700 dark:text-white" : "border-transparent text-slate-500"}`}>
              {label}
            </button>
          ))}
        </div>
        {(tab === "saved" || tab === "recent") && <Files scope={tab} />}
        {tab === "batch" && <Workflows />}
        {tab === "signatures" && <SignatureRequests />}
        {tab === "reviews" && <Reviews />}
      </div>
    </Page>
  );
}

function Files({ scope }: { scope: string }) {
  const { toast } = useApp();
  const [files, setFiles] = useState<FileInfo[] | null>(null);
  const load = () => api<{ files: FileInfo[] }>(`/api/files?scope=${scope}&limit=200`).then((r) => setFiles(r.files));
  useEffect(() => { setFiles(null); load(); }, [scope]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!files) return <Spinner />;
  if (!files.length) return <p className="text-slate-500">{scope === "saved" ? "No saved documents yet. Use the save icon in the editor to keep a document here." : "No files yet."} <Link to="/" className="text-brand-600 underline">Open a tool</Link></p>;
  const act = (p: Promise<any>) => p.then(load).catch((e) => toast(e.message, "error"));
  return (
    <div className="card divide-y divide-slate-200 dark:divide-slate-800">
      {files.map((f) => (
        <div key={f.id} className="flex flex-wrap items-center gap-2 p-3 text-sm">
          <FileText size={18} className="text-brand-600" />
          <span className="min-w-0 flex-1 truncate font-medium">{f.name}</span>
          <span className="text-xs text-slate-500">{formatBytes(f.size)} · {f.last_opened_at ? new Date(f.last_opened_at).toLocaleString() : ""}</span>
          {f.kind === "pdf" && <Link className="btn-ghost px-2 py-1" to={`/tool/view?file=${f.id}`} title="Open"><ExternalLink size={15} /></Link>}
          <button className="btn-ghost px-2 py-1" title="Download" onClick={() => downloadFile(f)}><Download size={15} /></button>
          <button className="btn-ghost px-2 py-1" title="Rename" onClick={() => { const n = prompt("New name", f.name); if (n) act(api(`/api/files/${f.id}`, { method: "PATCH", json: { name: n } })); }}><Pencil size={15} /></button>
          <button className={`btn-ghost px-2 py-1 ${f.is_saved ? "text-amber-500" : ""}`} title={f.is_saved ? "Remove from saved" : "Save"} onClick={() => act(api(`/api/files/${f.id}`, { method: "PATCH", json: { is_saved: !f.is_saved } }))}><Star size={15} fill={f.is_saved ? "currentColor" : "none"} /></button>
          <button className="btn-ghost px-2 py-1 text-red-600" title="Delete" onClick={() => confirm(`Delete ${f.name}?`) && act(api(`/api/files/${f.id}`, { method: "DELETE" }))}><Trash2 size={15} /></button>
        </div>
      ))}
    </div>
  );
}

function Workflows() {
  const [list, setList] = useState<any[] | null>(null);
  const load = () => api<{ workflows: any[] }>("/api/workflows").then((r) => setList(r.workflows));
  useEffect(() => { load(); }, []);
  if (!list) return <Spinner />;
  return (
    <div className="space-y-3">
      <Link to="/tool/batch" className="btn-primary">Create a batch action</Link>
      {list.map((w) => (
        <div key={w.id} className="card flex items-center gap-3 p-3 text-sm">
          <div className="flex-1">
            <div className="font-medium">{w.name}</div>
            <div className="text-xs text-slate-500">{w.steps.map((s: any) => s.tool.replace(/_/g, " ")).join(" → ")}</div>
          </div>
          <button className="btn-ghost px-2 text-red-600" onClick={() => api(`/api/workflows/${w.id}`, { method: "DELETE" }).then(load)}><Trash2 size={15} /></button>
        </div>
      ))}
    </div>
  );
}

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-amber-100 text-amber-800", completed: "bg-emerald-100 text-emerald-800", declined: "bg-red-100 text-red-800", cancelled: "bg-slate-200 text-slate-700",
  waiting: "bg-slate-100 text-slate-600", sent: "bg-sky-100 text-sky-800", viewed: "bg-indigo-100 text-indigo-800", signed: "bg-emerald-100 text-emerald-800",
};

function SignatureRequests() {
  const { toast } = useApp();
  const [list, setList] = useState<any[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const load = () => api<{ requests: any[] }>("/api/signature-requests").then((r) => setList(r.requests));
  useEffect(() => { load(); }, []);
  if (!list) return <Spinner />;
  if (!list.length) return <p className="text-slate-500">No signature requests yet. Open a PDF and choose <Link to="/tool/send_signature" className="text-brand-600 underline">Send for signature</Link>.</p>;
  const files = async (id: string, key: "current" | "audit") => {
    const r = await api<any>(`/api/signature-requests/${id}/files`);
    if (r[key]) downloadFile(r[key]);
  };
  return (
    <div className="space-y-3">
      {list.map((r) => (
        <div key={r.id} className="card p-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex-1 font-semibold">{r.title}</span>
            <span className={`chip ${STATUS_COLORS[r.status]}`}>{r.status}</span>
            <span className="text-xs text-slate-500">{new Date(r.created_at).toLocaleDateString()}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {r.signers.map((s: any) => (
              <span key={s.id} className={`chip ${STATUS_COLORS[s.status]}`} title={s.email}>{s.order}. {s.name}: {s.status}</span>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="btn-secondary px-2 py-1 text-xs" onClick={() => files(r.id, "current")}><Download size={13} /> Document</button>
            {r.audit_file_id && <button className="btn-secondary px-2 py-1 text-xs" onClick={() => files(r.id, "audit")}><Download size={13} /> Audit trail</button>}
            {r.status === "pending" && (
              <>
                <button className="btn-secondary px-2 py-1 text-xs" onClick={() => api(`/api/signature-requests/${r.id}/remind`, { method: "POST" }).then((x: any) => toast(`${x.sent} reminder(s) sent`, "success")).then(load)}><Bell size={13} /> Remind</button>
                <button className="btn-ghost px-2 py-1 text-xs text-red-600" onClick={() => confirm("Cancel this request?") && api(`/api/signature-requests/${r.id}/cancel`, { method: "POST" }).then(load)}><XCircle size={13} /> Cancel</button>
              </>
            )}
            <button className="btn-ghost px-2 py-1 text-xs" onClick={() => setOpen(open === r.id ? null : r.id)}>{open === r.id ? "Hide" : "Show"} history</button>
          </div>
          {open === r.id && (
            <ol className="mt-3 space-y-1 border-l-2 border-slate-200 pl-3 text-xs dark:border-slate-700">
              {r.events.map((e: any, i: number) => <li key={i}><b>{e.action}</b> · {e.actor} · {new Date(e.at).toLocaleString()} {e.detail && <span className="text-slate-500">· {e.detail}</span>}</li>)}
            </ol>
          )}
        </div>
      ))}
    </div>
  );
}

function Reviews() {
  const [list, setList] = useState<any[] | null>(null);
  const load = () => api<{ links: any[] }>("/api/review-links").then((r) => setList(r.links));
  useEffect(() => { load(); }, []);
  if (!list) return <Spinner />;
  if (!list.length) return <p className="text-slate-500">No review links yet. Open a PDF and choose <Link to="/tool/share_review" className="text-brand-600 underline">Share for review</Link>.</p>;
  return (
    <div className="card divide-y divide-slate-200 dark:divide-slate-800">
      {list.map((l) => (
        <div key={l.id} className={`flex flex-wrap items-center gap-2 p-3 text-sm ${l.active ? "" : "opacity-50"}`}>
          <span className="flex-1 font-medium">{l.title}</span>
          <span className="text-xs text-slate-500">{l.comments} comment(s)</span>
          {l.active && <a className="btn-ghost px-2 py-1" href={`/review/${l.token}`} target="_blank" rel="noreferrer"><ExternalLink size={15} /></a>}
          {l.active && <button className="btn-ghost px-2 py-1 text-xs text-red-600" onClick={() => api(`/api/review-links/${l.id}`, { method: "DELETE" }).then(load)}>Disable</button>}
        </div>
      ))}
    </div>
  );
}
