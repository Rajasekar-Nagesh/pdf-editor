// App-wide state: logged-in user, theme, toasts and AI availability.
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";

export interface User {
  id: string;
  email: string;
  name: string;
}

interface Toast {
  id: number;
  kind: "success" | "error" | "info";
  text: string;
}

interface AppState {
  user: User | null;
  ready: boolean;
  aiEnabled: boolean;
  dark: boolean;
  toggleDark: () => void;
  login: (token: string, user: User) => void;
  logout: () => void;
  toast: (text: string, kind?: Toast["kind"]) => void;
}

const Ctx = createContext<AppState>(null as unknown as AppState);
export const useApp = () => useContext(Ctx);

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [aiEnabled, setAi] = useState(false);
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    const token = getToken();
    (token ? api<User>("/api/auth/me").then(setUser).catch(() => setToken(null)) : Promise.resolve()).finally(() =>
      setReady(true),
    );
    api<{ enabled: boolean }>("/api/ai/status", { public: true })
      .then((s) => setAi(s.enabled))
      .catch(() => setAi(false));
  }, []);

  const toggleDark = useCallback(() => {
    setDark((d) => {
      const next = !d;
      document.documentElement.classList.toggle("dark", next);
      try {
        localStorage.setItem("pdfdesk-theme", next ? "dark" : "light");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const toast = useCallback((text: string, kind: Toast["kind"] = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 7000 : 4000);
  }, []);

  const login = (token: string, u: User) => {
    setToken(token);
    setUser(u);
  };
  const logout = () => {
    setToken(null);
    setUser(null);
  };

  return (
    <Ctx.Provider value={{ user, ready, aiEnabled, dark, toggleDark, login, logout, toast }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[min(92vw,380px)] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto rounded-lg px-4 py-3 text-sm shadow-lg ${
              t.kind === "error" ? "bg-red-600 text-white" : t.kind === "success" ? "bg-emerald-600 text-white" : "bg-slate-800 text-white"
            }`}
          >
            {t.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
