// Public pages that work without an account: review (view + comment) and signing (for invited signers).
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { CheckCircle2, MessageSquare } from "lucide-react";
import { api } from "../lib/api";
import { useApp } from "../lib/app-context";
import PdfViewer, { Shape } from "../components/PdfViewer";
import { Header } from "../components/Layout";
import SignaturePad from "../components/SignaturePad";
import { Spinner } from "../components/ui";

interface Comment { id: number; author: string; text: string; page: number; x: number | null; y: number | null; parent_id: number | null; resolved: boolean; created_at: string }

const POLL_MS = 3000;

export function ReviewPage() {
  const { token = "" } = useParams();
  const { toast } = useApp();
  const [info, setInfo] = useState<{ title: string } | null>(null);
  const [error, setError] = useState("");
  const [comments, setComments] = useState<Comment[]>([]);
  const [name, setName] = useState(() => localStorage.getItem("pdfdesk-reviewer") || "");
  const [text, setText] = useState("");
  const [pin, setPin] = useState<{ page: number; x: number; y: number } | null>(null);
  const [replyTo, setReplyTo] = useState<number | null>(null);
  const [goTo, setGoTo] = useState<{ page: number; nonce: number }>();
  const lastId = useRef(0);
  const base = `/api/public/review/${token}`;

  useEffect(() => {
    api(base, { public: true }).then(setInfo).catch((e) => setError(e.message));
  }, [base]);

  // Poll for new comments so every viewer sees the same thread.
  useEffect(() => {
    if (!info) return;
    let stop = false;
    const tick = async () => {
      try {
        const r = await api<{ comments: Comment[]; resolved_ids: number[] }>(`${base}/comments?since=${lastId.current}`, { public: true });
        if (stop) return;
        const resolved = new Set(r.resolved_ids);
        setComments((old) => {
          const merged = [...old, ...r.comments.filter((c) => !old.some((o) => o.id === c.id))];
          return merged.map((c) => ({ ...c, resolved: resolved.has(c.id) }));
        });
        if (r.comments.length) lastId.current = Math.max(lastId.current, ...r.comments.map((c) => c.id));
      } catch {
        /* keep polling */
      }
    };
    tick();
    const t = setInterval(tick, POLL_MS);
    return () => { stop = true; clearInterval(t); };
  }, [info, base]);

  const post = async () => {
    if (!name.trim() || !text.trim()) return toast("Enter your name and a comment.", "error");
    localStorage.setItem("pdfdesk-reviewer", name.trim());
    try {
      const c = await api<Comment>(`${base}/comments`, { method: "POST", public: true, json: { author: name.trim(), text: text.trim(), page: pin?.page ?? 0, x: pin?.x ?? null, y: pin?.y ?? null, parent_id: replyTo } });
      setComments((old) => (old.some((o) => o.id === c.id) ? old : [...old, c]));
      lastId.current = Math.max(lastId.current, c.id);
      setText(""); setPin(null); setReplyTo(null);
    } catch (e: any) { toast(e.message, "error"); }
  };

  const shapes: Shape[] = useMemo(() => {
    const s: Shape[] = comments.filter((c) => c.x !== null && !c.parent_id).map((c, i) => ({ page: c.page, kind: "point", points: [[c.x!, c.y!]], color: c.resolved ? "#94a3b8" : "#f59e0b", label: `${i + 1}`, id: c.id }));
    if (pin) s.push({ page: pin.page, kind: "point", points: [[pin.x, pin.y]], color: "#2563eb", label: "New" });
    return s;
  }, [comments, pin]);

  if (error) return <div><Header /><p className="mx-auto mt-16 max-w-md text-center text-slate-500">{error}</p></div>;
  if (!info) return <div><Header /><div className="p-10"><Spinner text="Opening document..." /></div></div>;

  const roots = comments.filter((c) => !c.parent_id);
  return (
    <div className="flex h-screen flex-col">
      <Header />
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <div className="min-h-[55vh] flex-1 lg:min-h-0">
          <PdfViewer publicUrl={`${base}/document`} mode="point" shapes={shapes} goTo={goTo} onPoint={(page, x, y) => setPin({ page, x, y })} search={false} />
        </div>
        <aside className="flex w-full flex-col border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 lg:w-96 lg:border-l lg:border-t-0">
          <div className="border-b border-slate-200 p-4 dark:border-slate-800">
            <h1 className="font-semibold">{info.title}</h1>
            <p className="text-xs text-slate-500">Click on the page to pin a comment. Comments update automatically.</p>
          </div>
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {roots.length === 0 && <p className="text-sm text-slate-500"><MessageSquare size={14} className="mr-1 inline" />No comments yet.</p>}
            {roots.map((c, i) => (
              <div key={c.id} className={`rounded-lg border p-3 text-sm ${c.resolved ? "border-slate-200 opacity-60 dark:border-slate-800" : "border-amber-200 dark:border-amber-900"}`}>
                <div className="flex items-center gap-2">
                  <button className="chip bg-amber-100 text-amber-800" onClick={() => setGoTo({ page: c.page, nonce: Date.now() })}>{c.x !== null ? `#${i + 1} · ` : ""}p.{c.page + 1}</button>
                  <b className="flex-1 truncate">{c.author}</b>
                  <span className="text-[11px] text-slate-400">{new Date(c.created_at).toLocaleString()}</span>
                </div>
                <p className="mt-1 whitespace-pre-wrap">{c.text}</p>
                {comments.filter((r) => r.parent_id === c.id).map((r) => (
                  <div key={r.id} className="mt-2 border-l-2 border-slate-200 pl-2 text-xs dark:border-slate-700"><b>{r.author}</b>: {r.text}</div>
                ))}
                <div className="mt-2 flex gap-3 text-xs">
                  <button className="text-brand-600" onClick={() => setReplyTo(c.id)}>Reply</button>
                  <button className="text-slate-500" onClick={() => api(`${base}/comments/${c.id}/resolve`, { method: "POST", public: true }).then((u: Comment) => setComments((all) => all.map((x) => (x.id === u.id ? u : x))))}>
                    <CheckCircle2 size={12} className="mr-0.5 inline" />{c.resolved ? "Reopen" : "Resolve"}
                  </button>
                </div>
              </div>
            ))}
          </div>
          <div className="space-y-2 border-t border-slate-200 p-4 dark:border-slate-800">
            {replyTo && <div className="text-xs">Replying to a comment · <button className="underline" onClick={() => setReplyTo(null)}>cancel</button></div>}
            {pin && <div className="text-xs">Pinned on page {pin.page + 1} · <button className="underline" onClick={() => setPin(null)}>remove pin</button></div>}
            <input className="input" placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
            <textarea className="input" placeholder="Write a comment..." value={text} onChange={(e) => setText(e.target.value)} maxLength={4000} />
            <button className="btn-primary w-full" onClick={post}>Post comment</button>
          </div>
        </aside>
      </div>
    </div>
  );
}

export function SignPage() {
  const { token = "" } = useParams();
  const { toast } = useApp();
  const [info, setInfo] = useState<any>(null);
  const [error, setError] = useState("");
  const [sig, setSig] = useState<string | null>(null);
  const [placements, setPlacements] = useState<{ page: number; rect: number[] }[]>([]);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState("");
  const base = `/api/public/sign/${token}`;

  useEffect(() => { api(base, { public: true }).then(setInfo).catch((e) => setError(e.message)); }, [base]);

  const submit = async () => {
    setBusy(true);
    try {
      await api(`${base}/sign`, { method: "POST", public: true, json: { image_data: sig, placements } });
      setDone("Thank you! Your signature has been added. Everyone will receive the completed document by email.");
    } catch (e: any) { toast(e.message, "error"); } finally { setBusy(false); }
  };
  const decline = async () => {
    const reason = prompt("Why are you declining? (optional)") ?? null;
    if (reason === null) return;
    await api(`${base}/decline`, { method: "POST", public: true, json: { reason } });
    setDone("You declined to sign. The sender has been notified.");
  };

  if (error) return <div><Header /><p className="mx-auto mt-16 max-w-md text-center text-slate-500">{error}</p></div>;
  if (!info) return <div><Header /><div className="p-10"><Spinner text="Opening document..." /></div></div>;
  if (done) return <div><Header /><div className="mx-auto mt-16 max-w-md rounded-xl bg-emerald-50 p-6 text-center dark:bg-emerald-950">{done}</div></div>;

  return (
    <div className="flex h-screen flex-col">
      <Header />
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <div className="min-h-[55vh] flex-1 lg:min-h-0">
          <PdfViewer
            publicUrl={`${base}/document`}
            search={false}
            mode={info.can_sign ? "rect" : "none"}
            shapes={placements.map((p, i) => ({ page: p.page, kind: "rect", rect: p.rect, color: "#1d4ed8", fill: "#1d4ed815", label: "Your signature", id: i }))}
            onRect={(page, rect) => (sig ? setPlacements((p) => [...p, { page, rect }]) : toast("Create your signature first.", "error"))}
            onPoint={(page, x, y) => (sig ? setPlacements((p) => [...p, { page, rect: [x - 75, y - 25, x + 75, y + 25] }]) : toast("Create your signature first.", "error"))}
          />
        </div>
        <aside className="w-full space-y-4 overflow-y-auto border-t border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900 lg:w-96 lg:border-l lg:border-t-0">
          <div>
            <h1 className="text-lg font-semibold">{info.title}</h1>
            <p className="text-sm text-slate-500">Hello {info.signer.name}, please review and sign.</p>
            {info.message && <p className="mt-2 rounded-lg bg-slate-100 p-2 text-sm dark:bg-slate-800">{info.message}</p>}
          </div>
          <ul className="space-y-1 text-xs">
            {info.signers.map((s: any, i: number) => <li key={i}>{s.order}. {s.name} - <b>{s.status}</b></li>)}
          </ul>
          {info.can_sign ? (
            <>
              <SignaturePad onChange={setSig} />
              <p className="text-xs text-slate-500">Click on the document where you want to sign (or drag to size it).</p>
              {placements.length > 0 && <button className="text-xs underline" onClick={() => setPlacements(placements.slice(0, -1))}>Remove last placement</button>}
              <label className="flex items-start gap-2 text-xs"><input type="checkbox" required id="consent" /> I agree that this electronic signature is the legal equivalent of my handwritten signature.</label>
              <button className="btn-primary w-full" disabled={busy || !sig || !placements.length} onClick={() => ((document.getElementById("consent") as HTMLInputElement)?.checked ? submit() : toast("Please tick the consent box.", "error"))}>
                {busy ? "Signing..." : "Sign document"}
              </button>
              <button className="btn-ghost w-full text-red-600" onClick={decline}>Decline to sign</button>
            </>
          ) : (
            <p className="rounded-lg bg-amber-50 p-3 text-sm dark:bg-amber-950">
              {info.request_status !== "pending" ? `This request is ${info.request_status}.` : info.signer.status === "signed" ? "You have already signed." : "Earlier signers have not finished yet. You will get an email when it is your turn."}
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}
