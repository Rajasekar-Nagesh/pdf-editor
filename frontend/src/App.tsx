import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppProvider } from "./lib/app-context";
import { Spinner } from "./components/ui";
import Home from "./pages/Home";
import { ForgotPassword, Login, ResetPassword, Signup } from "./pages/Auth";

// The editor pulls in pdf.js and pdf-lib, so load it only when needed.
const Editor = lazy(() => import("./pages/Editor"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const ReviewPage = lazy(() => import("./pages/Public").then((m) => ({ default: m.ReviewPage })));
const SignPage = lazy(() => import("./pages/Public").then((m) => ({ default: m.SignPage })));

function NotFound() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3">
      <h1 className="text-2xl font-bold">Page not found</h1>
      <a className="btn-primary" href="/">Go to all tools</a>
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Suspense fallback={<div className="p-10"><Spinner text="Loading..." /></div>}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/tool/:toolId" element={<Editor />} />
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/review/:token" element={<ReviewPage />} />
            <Route path="/sign/:token" element={<SignPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </AppProvider>
  );
}
