import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { uploadOne } from "../lib/api";
import { useApp } from "../lib/app-context";
import { CATEGORIES, TOOLS } from "../lib/tools";
import { Page } from "../components/Layout";
import { ACCEPT, Dropzone, ProgressBar } from "../components/ui";

export default function Home() {
  const { aiEnabled, toast } = useApp();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [pct, setPct] = useState<number | null>(null);
  const visible = TOOLS.filter((t) => (!t.ai || aiEnabled) && (`${t.title} ${t.desc}`.toLowerCase().includes(q.toLowerCase())));

  const open = async (files: File[]) => {
    setPct(0);
    try {
      const f = await uploadOne(files[0], setPct);
      nav(`/tool/${f.kind === "pdf" ? "view" : f.kind === "image" ? "images_to_pdf" : "office_to_pdf"}?file=${f.id}`);
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setPct(null);
    }
  };

  return (
    <Page>
      <section className="border-b border-slate-200 bg-gradient-to-b from-brand-50 to-transparent dark:border-slate-800 dark:from-slate-900">
        <div className="mx-auto grid max-w-7xl items-center gap-8 px-4 py-10 md:grid-cols-2 md:py-14">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">Every PDF tool you need, in your browser.</h1>
            <p className="mt-3 text-slate-600 dark:text-slate-300">
              View, edit, convert, sign, protect and automate PDFs. OCR in English, Tamil and Hindi. No installation.
            </p>
            <div className="relative mt-6 max-w-md">
              <Search size={16} className="absolute left-3 top-3 text-slate-400" />
              <input className="input pl-9" placeholder="Find a tool, e.g. merge, OCR, sign" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search tools" />
            </div>
          </div>
          <div>
            <Dropzone onFiles={open} accept={ACCEPT.any} label="Drop a file to open it" />
            {pct !== null && <div className="mt-3"><ProgressBar value={pct} label="Uploading" /></div>}
          </div>
        </div>
      </section>
      <div className="mx-auto max-w-7xl space-y-10 px-4 py-10">
        {CATEGORIES.map((cat) => {
          const tools = visible.filter((t) => t.category === cat);
          if (!tools.length) return null;
          return (
            <section key={cat}>
              <h2 className="mb-3 text-lg font-bold">{cat}</h2>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {tools.map((t) => (
                  <Link key={t.id} to={`/tool/${t.id}`} className="card group flex gap-3 p-4 transition hover:-translate-y-0.5 hover:border-brand-500 hover:shadow-md">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600 group-hover:bg-brand-600 group-hover:text-white dark:bg-slate-800">
                      <t.icon size={20} />
                    </span>
                    <span>
                      <span className="block font-semibold">{t.title}{t.login && <span className="chip ml-2 bg-slate-100 text-slate-500 dark:bg-slate-800">account</span>}</span>
                      <span className="block text-sm text-slate-500">{t.desc}</span>
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          );
        })}
        {visible.length === 0 && <p className="text-center text-slate-500">No tools match "{q}".</p>}
      </div>
    </Page>
  );
}
