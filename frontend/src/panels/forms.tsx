// Forms and signature panels.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Trash2, Usb } from "lucide-react";
import { api, authHeaders, FileInfo, inspect } from "../lib/api";
import { useApp } from "../lib/app-context";
import { Shape } from "../components/PdfViewer";
import SignaturePad from "../components/SignaturePad";
import { Spinner } from "../components/ui";
import { useEditor, useViewer } from "../pages/Editor";

interface FieldInfo { name: string; type: string; value: any; options: string[]; on_state: string | null; page: number; bbox: number[] }

const FIELD_TYPES = [
  { value: "text", label: "Text" },
  { value: "checkbox", label: "Checkbox" },
  { value: "radio", label: "Radio button" },
  { value: "dropdown", label: "Dropdown" },
  { value: "date", label: "Date" },
];

export function FormsPanel() {
  const { file, run, busy, refreshKey } = useEditor();
  const [tab, setTab] = useState<"fill" | "create">("fill");
  const [fields, setFields] = useState<FieldInfo[] | null>(null);
  const [values, setValues] = useState<Record<string, any>>({});
  const [flatten, setFlatten] = useState(false);
  const [newType, setNewType] = useState("text");
  const [newName, setNewName] = useState("");
  const [options, setOptions] = useState("Option 1, Option 2");
  const [pending, setPending] = useState<any[]>([]);

  useEffect(() => {
    if (!file) return;
    inspect<FieldInfo[]>(file.id, "fields").then((f) => {
      setFields(f);
      setValues(Object.fromEntries(f.map((x) => [x.name, x.type === "CheckBox" ? x.value !== "Off" && !!x.value : x.value ?? ""])));
    });
  }, [file?.id, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const shapes: Shape[] = (fields || []).map((f, i) => ({ page: f.page, kind: "rect", rect: f.bbox, color: "#6366f1", fill: "#6366f115", id: i, label: tab === "create" ? f.name : undefined }));
  pending.forEach((p, i) => shapes.push({ page: p.page, kind: "rect", rect: p.rect, color: "#16a34a", dashed: true, label: `${p.type}: ${p.name}`, id: `p${i}` }));

  useViewer({
    mode: tab === "create" ? "rect" : "none",
    shapes,
    onRect: (page, rect) => {
      const base = newName.trim() || `${newType}_${pending.length + 1}`;
      setPending((p) => [...p, { page, rect, type: newType, name: base, options: options.split(",").map((s) => s.trim()).filter(Boolean), value: base }]);
    },
    onShapeClick: (s) => document.getElementById(`field-${s.id}`)?.focus(),
  });

  return (
    <div className="space-y-4">
      <div className="flex gap-1 rounded-lg bg-slate-100 p-1 text-sm dark:bg-slate-800">
        <button className={`flex-1 rounded-md py-1.5 ${tab === "fill" ? "bg-white shadow dark:bg-slate-700" : ""}`} onClick={() => setTab("fill")}>Fill</button>
        <button className={`flex-1 rounded-md py-1.5 ${tab === "create" ? "bg-white shadow dark:bg-slate-700" : ""}`} onClick={() => setTab("create")}>Create fields</button>
      </div>
      {fields === null && <Spinner text="Reading form..." />}
      {tab === "fill" && fields && (
        fields.length === 0 ? (
          <div className="space-y-2 text-sm text-slate-500">
            <p>This PDF has no fillable fields.</p>
            <button className="btn-secondary w-full" disabled={busy} onClick={() => run("prepare_form", {})}>Auto-detect fields</button>
            <button className="btn-ghost w-full" onClick={() => setTab("create")}>Or draw fields yourself</button>
          </div>
        ) : (
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); run("fill_form", { values, flatten }); }}>
            {fields.map((f, i) => {
              if (f.type === "RadioButton" && fields.findIndex((x) => x.name === f.name) !== i) return null;
              const id = `field-${i}`;
              const set = (v: any) => setValues({ ...values, [f.name]: v });
              return (
                <div key={id}>
                  <label htmlFor={id} className="label">{f.name}</label>
                  {f.type === "CheckBox" ? (
                    <input id={id} type="checkbox" className="h-4 w-4" checked={!!values[f.name]} onChange={(e) => set(e.target.checked)} />
                  ) : f.type === "RadioButton" ? (
                    <div className="flex flex-wrap gap-3 text-sm">
                      {fields.filter((x) => x.name === f.name).map((x) => (
                        <label key={x.on_state || ""} className="flex items-center gap-1"><input type="radio" name={f.name} checked={values[f.name] === x.on_state} onChange={() => set(x.on_state)} /> {x.on_state}</label>
                      ))}
                    </div>
                  ) : f.options.length ? (
                    <select id={id} className="input" value={values[f.name] ?? ""} onChange={(e) => set(e.target.value)}>{f.options.map((o) => <option key={o}>{o}</option>)}</select>
                  ) : (
                    <input id={id} className="input" value={values[f.name] ?? ""} onChange={(e) => set(e.target.value)} />
                  )}
                </div>
              );
            })}
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={flatten} onChange={(e) => setFlatten(e.target.checked)} /> Flatten after filling (not editable)</label>
            <button className="btn-primary w-full" disabled={busy}>Save filled form</button>
          </form>
        )
      )}
      {tab === "create" && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <div><label className="label">Field type</label><select className="input" value={newType} onChange={(e) => setNewType(e.target.value)}>{FIELD_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</select></div>
            <div><label className="label">{newType === "radio" ? "Group name" : "Name"}</label><input className="input" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="auto" /></div>
          </div>
          {newType === "dropdown" && <div><label className="label">Options (comma separated)</label><input className="input" value={options} onChange={(e) => setOptions(e.target.value)} /></div>}
          <p className="text-xs text-slate-500">Drag on the page to draw each field. {newType === "radio" ? "Use the same group name for buttons that belong together." : ""}</p>
          {pending.length > 0 && (
            <>
              <ul className="space-y-1 text-xs">{pending.map((p, i) => (
                <li key={i} className="flex items-center gap-2"><span className="flex-1">{p.type} · {p.name} · p.{p.page + 1}</span><button className="text-red-600" onClick={() => setPending(pending.filter((_, k) => k !== i))}><Trash2 size={12} /></button></li>
              ))}</ul>
              <button className="btn-primary w-full" disabled={busy} onClick={() => run("add_fields", { fields: pending.map((p, i) => ({ ...p, value: p.type === "radio" ? `Choice${i + 1}` : undefined })) }).then((j) => j && setPending([]))}>
                Create {pending.length} field(s)
              </button>
            </>
          )}
          <button className="btn-secondary w-full" disabled={busy} onClick={() => run("prepare_form", {})}>Auto-detect fields (Prepare Form)</button>
          {fields && fields.length > 0 && (
            <div className="border-t border-slate-200 pt-3 dark:border-slate-800">
              <h3 className="label">Existing fields</h3>
              <ul className="space-y-1 text-xs">{[...new Set(fields.map((f) => f.name))].map((n) => (
                <li key={n} className="flex items-center gap-2"><span className="flex-1 truncate">{n}</span><button className="text-red-600" disabled={busy} onClick={() => run("delete_field", { name: n })}><Trash2 size={12} /></button></li>
              ))}</ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function SignPanel() {
  const { run, busy } = useEditor();
  const [sig, setSig] = useState<string | null>(null);
  const [placements, setPlacements] = useState<{ page: number; rect: number[] }[]>([]);
  const { toast } = useApp();
  useViewer({
    mode: "rect",
    shapes: placements.map((p, i) => ({ page: p.page, kind: "rect", rect: p.rect, color: "#1d4ed8", fill: "#1d4ed815", label: "Signature", id: i })),
    onRect: (page, rect) => (sig ? setPlacements((p) => [...p, { page, rect }]) : toast("Create your signature first.", "error")),
    onPoint: (page, x, y) => (sig ? setPlacements((p) => [...p, { page, rect: [x - 75, y - 25, x + 75, y + 25] }]) : toast("Create your signature first.", "error")),
  });
  return (
    <div className="space-y-4">
      <SignaturePad onChange={setSig} />
      <p className="text-xs text-slate-500">Then click on the page to place it (or drag to set its size). You can place it several times.</p>
      {placements.length > 0 && (
        <div className="flex items-center justify-between text-sm">
          <span>{placements.length} placement(s)</span>
          <button className="text-xs underline" onClick={() => setPlacements(placements.slice(0, -1))}>Remove last</button>
        </div>
      )}
      <button className="btn-primary w-full" disabled={busy || !sig || !placements.length} onClick={() => run("place_signature", { image_data: sig, placements }).then((j) => j && setPlacements([]))}>
        Apply signature
      </button>
    </div>
  );
}

const DEFAULT_BRIDGE = "http://127.0.0.1:8765";

export function DigitalPanel() {
  const { file, run, busy, openFile } = useEditor();
  const { toast } = useApp();
  const [tab, setTab] = useState<"pfx" | "token" | "validate">("pfx");
  const [box, setBox] = useState<{ page: number; rect: number[] } | null>(null);
  const [visible, setVisible] = useState(true);
  const [pfx, setPfx] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [meta, setMeta] = useState({ reason: "I approve this document", location: "", contact: "", tsa_url: "" });
  const [bridge, setBridge] = useState(() => localStorage.getItem("pdfdesk-bridge") || DEFAULT_BRIDGE);
  const [pin, setPin] = useState("");
  const [working, setWorking] = useState(false);

  useViewer({
    mode: visible && tab !== "validate" ? "rect" : "none",
    shapes: box && visible ? [{ page: box.page, kind: "rect", rect: box.rect, color: "#0f766e", fill: "#0f766e18", label: "Signature block" }] : [],
    onRect: (page, rect) => setBox({ page, rect }),
    onPoint: (page, x, y) => setBox({ page, rect: [x - 100, y - 30, x + 100, y + 30] }),
  });

  const signPfx = async () => {
    if (!pfx || !file) return toast("Choose your .pfx or .p12 certificate.", "error");
    setWorking(true);
    try {
      const form = new FormData();
      form.append("file_id", file.id);
      form.append("certificate", pfx);
      form.append("password", password);
      form.append("page", String(box?.page ?? 0));
      if (visible && box) form.append("rect", JSON.stringify(box.rect));
      Object.entries(meta).forEach(([k, v]) => form.append(k, v));
      const res = await fetch("/api/sign/digital", { method: "POST", headers: authHeaders(), body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Signing failed");
      setPassword("");
      openFile(data.file as FileInfo);
      toast(`Signed by ${data.signature.signer}`, "success");
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setWorking(false);
    }
  };

  const signToken = async () => {
    if (!file) return;
    setWorking(true);
    try {
      localStorage.setItem("pdfdesk-bridge", bridge);
      // 1) Read the certificate from the USB token via the local bridge on this computer.
      const certRes = await fetch(`${bridge}/certificate`).catch(() => null);
      if (!certRes?.ok) throw new Error("Could not reach the DSC signing bridge. Is it running on this computer? (see README)");
      const { certificate } = await certRes.json();
      // 2) Server reserves the signature and returns the bytes to sign.
      const prep = await api<{ to_sign: string; state_token: string }>("/api/sign/dsc/prepare", {
        method: "POST",
        json: { file_id: file.id, certificate, page: box?.page ?? 0, rect: visible && box ? box.rect : null, reason: meta.reason, location: meta.location, contact: meta.contact },
      });
      // 3) The token signs locally; the PIN goes only to the bridge on this computer, never to our server.
      const signRes = await fetch(`${bridge}/sign`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ data: prep.to_sign, digest: "sha256", pin }) });
      const signed = await signRes.json().catch(() => ({}));
      if (!signRes.ok) throw new Error(signed.error || "The token did not sign. Check the PIN.");
      // 4) Server embeds the signature.
      const done = await api<{ file: FileInfo; signature: { signer: string } }>("/api/sign/dsc/complete", { method: "POST", json: { state_token: prep.state_token, signature: signed.signature } });
      setPin("");
      openFile(done.file);
      toast(`Signed with token: ${done.signature.signer}`, "success");
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setWorking(false);
    }
  };

  const metaFields = (
    <div className="space-y-2">
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} /> Visible signature block</label>
      {visible && <p className="text-xs text-slate-500">{box ? `Block on page ${box.page + 1}.` : "Drag on the page to place the signature block."}</p>}
      <input className="input" placeholder="Reason" value={meta.reason} onChange={(e) => setMeta({ ...meta, reason: e.target.value })} />
      <input className="input" placeholder="Location (e.g. Chennai)" value={meta.location} onChange={(e) => setMeta({ ...meta, location: e.target.value })} />
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex gap-1 rounded-lg bg-slate-100 p-1 text-xs dark:bg-slate-800">
        {([["pfx", "Certificate file"], ["token", "USB DSC token"], ["validate", "Validate"]] as const).map(([k, l]) => (
          <button key={k} className={`flex-1 rounded-md py-1.5 ${tab === k ? "bg-white shadow dark:bg-slate-700" : ""}`} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>
      {tab === "pfx" && (
        <div className="space-y-3">
          <div><label className="label">Certificate (.pfx / .p12)</label><input type="file" accept=".pfx,.p12" className="block w-full text-sm" onChange={(e) => setPfx(e.target.files?.[0] || null)} /></div>
          <div><label className="label">Certificate password</label><input type="password" autoComplete="off" className="input" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
          {metaFields}
          <input className="input" placeholder="Timestamp server URL (optional)" value={meta.tsa_url} onChange={(e) => setMeta({ ...meta, tsa_url: e.target.value })} />
          <p className="text-xs text-slate-500">Your certificate and password are used only for this request and are never stored.</p>
          <button className="btn-primary w-full" disabled={working || !pfx} onClick={signPfx}>{working ? "Signing..." : "Sign digitally"}</button>
        </div>
      )}
      {tab === "token" && (
        <div className="space-y-3">
          <p className="flex gap-2 text-xs text-slate-500"><Usb size={28} className="shrink-0" /> Plug in your DSC token and start the PDFDesk signing bridge on this computer (see the README). The private key never leaves the token.</p>
          <div><label className="label">Bridge address</label><input className="input" value={bridge} onChange={(e) => setBridge(e.target.value)} /></div>
          <div><label className="label">Token PIN</label><input type="password" autoComplete="off" className="input" value={pin} onChange={(e) => setPin(e.target.value)} /></div>
          {metaFields}
          <button className="btn-primary w-full" disabled={working || !pin} onClick={signToken}>{working ? "Signing with token..." : "Sign with USB token"}</button>
        </div>
      )}
      {tab === "validate" && (
        <div className="space-y-2">
          <p className="text-sm text-slate-500">Check every digital signature in this PDF: integrity, validity and trust.</p>
          <button className="btn-primary w-full" disabled={busy} onClick={() => run("validate_signatures", {})}>Validate signatures</button>
        </div>
      )}
    </div>
  );
}

export function SendPanel() {
  const { file } = useEditor();
  const { toast } = useApp();
  const [title, setTitle] = useState(file?.name.replace(/\.pdf$/i, "") || "");
  const [message, setMessage] = useState("");
  const [signers, setSigners] = useState([{ name: "", email: "", order: 1 }]);
  const [sent, setSent] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  useViewer({});

  const submit = async () => {
    setBusy(true);
    try {
      const req = await api("/api/signature-requests", { method: "POST", json: { file_id: file!.id, title, message, signers } });
      setSent(req);
      toast("Invitations sent", "success");
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  if (sent)
    return (
      <div className="space-y-3 text-sm">
        <p>Request <b>{sent.title}</b> created. Signers are emailed in order; you will get the signed document and an audit trail when everyone has signed.</p>
        <Link className="btn-primary w-full" to="/dashboard?tab=signatures">Track status</Link>
      </div>
    );
  return (
    <div className="space-y-3">
      <div><label className="label">Title</label><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
      <div><label className="label">Message (optional)</label><textarea className="input" value={message} onChange={(e) => setMessage(e.target.value)} /></div>
      <h3 className="label">Signers</h3>
      {signers.map((s, i) => (
        <div key={i} className="space-y-1 rounded-lg border border-slate-200 p-2 dark:border-slate-700">
          <div className="flex gap-1">
            <input className="input" placeholder="Name" value={s.name} onChange={(e) => setSigners(signers.map((x, k) => (k === i ? { ...x, name: e.target.value } : x)))} />
            <button className="btn-ghost px-2 text-red-600" disabled={signers.length === 1} onClick={() => setSigners(signers.filter((_, k) => k !== i))}><Trash2 size={14} /></button>
          </div>
          <input className="input" type="email" placeholder="Email" value={s.email} onChange={(e) => setSigners(signers.map((x, k) => (k === i ? { ...x, email: e.target.value } : x)))} />
          <label className="flex items-center gap-2 text-xs">Signing order
            <input type="number" min={1} className="input w-20" value={s.order} onChange={(e) => setSigners(signers.map((x, k) => (k === i ? { ...x, order: Number(e.target.value) } : x)))} />
          </label>
        </div>
      ))}
      <button className="btn-secondary w-full" onClick={() => setSigners([...signers, { name: "", email: "", order: signers.length + 1 }])}><Plus size={14} /> Add signer</button>
      <p className="text-xs text-slate-500">Signers with the same order number sign in parallel.</p>
      <button className="btn-primary w-full" disabled={busy || !title || signers.some((s) => !s.name || !s.email)} onClick={submit}>Send for signature</button>
    </div>
  );
}
