import { ReactNode, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { LayoutDashboard, LogIn, LogOut, Menu, Moon, Sun, X } from "lucide-react";
import { useApp } from "../lib/app-context";

export function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2 font-bold tracking-tight">
      <img src="/favicon.svg" alt="" className="h-7 w-7" />
      <span className="text-lg">PDF<span className="text-brand-600">Desk</span></span>
    </Link>
  );
}

export function Header() {
  const { user, logout, dark, toggleDark } = useApp();
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const linkCls = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-2 text-sm font-medium ${isActive ? "bg-brand-50 text-brand-700 dark:bg-slate-800 dark:text-white" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"}`;

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4">
        <Logo />
        <nav className="ml-4 hidden items-center gap-1 md:flex">
          <NavLink to="/" end className={linkCls}>All tools</NavLink>
          {user && <NavLink to="/dashboard" className={linkCls}>My documents</NavLink>}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <button className="btn-ghost px-2" onClick={toggleDark} title={dark ? "Light mode" : "Dark mode"} aria-label="Toggle dark mode">
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <div className="hidden items-center gap-1 md:flex">
            {user ? (
              <>
                <span className="px-2 text-sm text-slate-500">{user.name || user.email}</span>
                <button className="btn-ghost" onClick={() => { logout(); nav("/"); }}><LogOut size={16} /> Log out</button>
              </>
            ) : (
              <>
                <Link to="/login" className="btn-ghost"><LogIn size={16} /> Log in</Link>
                <Link to="/signup" className="btn-primary">Sign up free</Link>
              </>
            )}
          </div>
          <button className="btn-ghost px-2 md:hidden" onClick={() => setOpen((v) => !v)} aria-label="Menu">
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>
      {open && (
        <div className="border-t border-slate-200 px-4 py-2 dark:border-slate-800 md:hidden" onClick={() => setOpen(false)}>
          <NavLink to="/" end className={linkCls}>All tools</NavLink>
          {user ? (
            <>
              <NavLink to="/dashboard" className={linkCls}><LayoutDashboard size={14} className="mr-1 inline" />My documents</NavLink>
              <button className="btn-ghost w-full justify-start" onClick={() => { logout(); nav("/"); }}>Log out</button>
            </>
          ) : (
            <div className="flex gap-2 py-2">
              <Link to="/login" className="btn-secondary flex-1">Log in</Link>
              <Link to="/signup" className="btn-primary flex-1">Sign up</Link>
            </div>
          )}
        </div>
      )}
    </header>
  );
}

export function Page({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-full flex-col">
      <Header />
      <main className="flex-1">{children}</main>
      <footer className="border-t border-slate-200 py-6 text-center text-xs text-slate-500 dark:border-slate-800">
        PDFDesk · Guest files are deleted automatically after 1 hour · Files of signed-in users are kept until you delete them
      </footer>
    </div>
  );
}
