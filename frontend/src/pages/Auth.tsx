import { FormEvent, ReactNode, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp, User } from "../lib/app-context";
import { Page } from "../components/Layout";

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Page>
      <div className="mx-auto max-w-sm px-4 py-12">
        <div className="card p-6">
          <h1 className="mb-5 text-xl font-bold">{title}</h1>
          {children}
        </div>
      </div>
    </Page>
  );
}

function useSubmit() {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const wrap = (fn: () => Promise<void>) => async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await fn();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return { error, busy, wrap };
}

const ErrorBox = ({ error }: { error: string }) => (error ? <p className="rounded-lg bg-red-50 p-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-200" role="alert">{error}</p> : null);

export function Login() {
  const { login } = useApp();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const { error, busy, wrap } = useSubmit();
  return (
    <Card title="Log in">
      <form className="space-y-3" onSubmit={wrap(async () => {
        const r = await api<{ token: string; user: User }>("/api/auth/login", { method: "POST", json: { email, password }, public: true });
        login(r.token, r.user);
        nav("/dashboard");
      })}>
        <div><label className="label" htmlFor="email">Email</label><input id="email" type="email" required autoComplete="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div><label className="label" htmlFor="pw">Password</label><input id="pw" type="password" required autoComplete="current-password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
        <ErrorBox error={error} />
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Logging in..." : "Log in"}</button>
        <div className="flex justify-between text-sm">
          <Link to="/forgot-password" className="text-brand-600 hover:underline">Forgot password?</Link>
          <Link to="/signup" className="text-brand-600 hover:underline">Create account</Link>
        </div>
      </form>
    </Card>
  );
}

export function Signup() {
  const { login } = useApp();
  const nav = useNavigate();
  const [f, setF] = useState({ name: "", email: "", password: "" });
  const { error, busy, wrap } = useSubmit();
  return (
    <Card title="Create your free account">
      <form className="space-y-3" onSubmit={wrap(async () => {
        const r = await api<{ token: string; user: User }>("/api/auth/signup", { method: "POST", json: f, public: true });
        login(r.token, r.user);
        nav("/dashboard");
      })}>
        <div><label className="label" htmlFor="name">Name</label><input id="name" className="input" autoComplete="name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
        <div><label className="label" htmlFor="email">Email</label><input id="email" type="email" required autoComplete="email" className="input" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
        <div><label className="label" htmlFor="pw">Password (at least 8 characters)</label><input id="pw" type="password" required minLength={8} maxLength={72} autoComplete="new-password" className="input" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></div>
        <ErrorBox error={error} />
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Creating..." : "Sign up"}</button>
        <p className="text-center text-sm">Already have an account? <Link to="/login" className="text-brand-600 hover:underline">Log in</Link></p>
      </form>
    </Card>
  );
}

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState(false);
  const { error, busy, wrap } = useSubmit();
  return (
    <Card title="Reset your password">
      {done ? (
        <p className="text-sm">If an account exists for <b>{email}</b>, we have sent a reset link. Check your inbox (and spam folder).</p>
      ) : (
        <form className="space-y-3" onSubmit={wrap(async () => { await api("/api/auth/forgot-password", { method: "POST", json: { email }, public: true }); setDone(true); })}>
          <div><label className="label" htmlFor="email">Email</label><input id="email" type="email" required className="input" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          <ErrorBox error={error} />
          <button className="btn-primary w-full" disabled={busy}>Send reset link</button>
        </form>
      )}
    </Card>
  );
}

export function ResetPassword() {
  const [params] = useSearchParams();
  const { login } = useApp();
  const nav = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const { error, busy, wrap } = useSubmit();
  return (
    <Card title="Choose a new password">
      <form className="space-y-3" onSubmit={wrap(async () => {
        if (password !== confirm) throw new Error("The passwords do not match.");
        const r = await api<{ token: string; user: User }>("/api/auth/reset-password", { method: "POST", json: { token: params.get("token") || "", password }, public: true });
        login(r.token, r.user);
        nav("/dashboard");
      })}>
        <div><label className="label" htmlFor="pw">New password</label><input id="pw" type="password" required minLength={8} maxLength={72} className="input" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
        <div><label className="label" htmlFor="pw2">Repeat password</label><input id="pw2" type="password" required className="input" value={confirm} onChange={(e) => setConfirm(e.target.value)} /></div>
        <ErrorBox error={error} />
        <button className="btn-primary w-full" disabled={busy}>Save password</button>
      </form>
    </Card>
  );
}
