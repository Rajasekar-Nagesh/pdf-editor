// Thin API client: adds auth / guest headers, turns errors into friendly messages,
// uploads with progress, and runs tools as jobs (polling until they finish).

export interface FileInfo {
  id: string;
  name: string;
  kind: string;
  mime: string;
  size: number;
  parent_id: string | null;
  is_saved: boolean;
  created_at: string | null;
  last_opened_at: string | null;
  expires_at: string | null;
}

export interface Job {
  id: string;
  tool: string;
  status: "queued" | "running" | "done" | "failed";
  progress: number;
  message: string;
  error: string | null;
  result: { files: FileInfo[]; zip: FileInfo | null; data: Record<string, any> } | null;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const TOKEN_KEY = "pdfdesk-token";
const GUEST_KEY = "pdfdesk-guest";

function storage(key: string, value?: string | null): string | null {
  try {
    if (value === undefined) return localStorage.getItem(key);
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage may be unavailable (private mode) */
  }
  return value ?? null;
}

let memoryGuest: string | null = null;

export function getToken(): string | null {
  return storage(TOKEN_KEY);
}
export function setToken(token: string | null) {
  storage(TOKEN_KEY, token);
}

/** Anonymous visitors get a random guest id so they can only see their own files. */
export function guestToken(): string {
  let g = storage(GUEST_KEY) || memoryGuest;
  if (!g) {
    const bytes = crypto.getRandomValues(new Uint8Array(24));
    g = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    memoryGuest = g;
    storage(GUEST_KEY, g);
  }
  return g;
}

export function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : { "X-Guest-Token": guestToken() };
}

async function errorFrom(res: Response): Promise<ApiError> {
  let message = `Request failed (${res.status})`;
  try {
    const data = await res.json();
    if (typeof data.detail === "string") message = data.detail;
  } catch {
    /* not JSON */
  }
  if (res.status === 429) message = "You are going a bit fast. Please wait a minute and try again.";
  if (res.status === 413) message = "That file is too large (maximum 100 MB).";
  if (res.status >= 502 && res.status <= 504) message = "The server is busy or restarting. Please try again shortly.";
  return new ApiError(message, res.status);
}

export async function api<T = any>(path: string, opts: RequestInit & { json?: unknown; public?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.public ? {} : authHeaders()), ...(opts.headers as Record<string, string>) };
  let body = opts.body;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  }
  let res: Response;
  try {
    res = await fetch(path, { ...opts, headers, body });
  } catch {
    throw new ApiError("Cannot reach the server. Check your internet connection.", 0);
  }
  if (!res.ok) throw await errorFrom(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function fetchBytes(path: string, isPublic = false): Promise<ArrayBuffer> {
  const res = await fetch(path, { headers: isPublic ? {} : authHeaders() });
  if (!res.ok) throw await errorFrom(res);
  return res.arrayBuffer();
}

export function fileBytes(id: string) {
  return fetchBytes(`/api/files/${id}/download`);
}

export async function downloadFile(file: { id: string; name: string }) {
  const data = await fileBytes(file.id);
  const url = URL.createObjectURL(new Blob([data]));
  const a = document.createElement("a");
  a.href = url;
  a.download = file.name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/** Upload files with a progress callback (0-100). */
export function uploadFiles(files: File[], onProgress?: (pct: number) => void, url = "/api/files", field = "files"): Promise<any> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    files.forEach((f) => form.append(field, f, f.name));
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    Object.entries(authHeaders()).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => {
      let data: any = {};
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else {
        let msg = typeof data.detail === "string" ? data.detail : `Upload failed (${xhr.status})`;
        if (xhr.status === 413) msg = "That file is too large (maximum 100 MB).";
        reject(new ApiError(msg, xhr.status));
      }
    };
    xhr.onerror = () => reject(new ApiError("Upload failed. Check your connection.", 0));
    xhr.send(form);
  });
}

export async function uploadOne(file: File, onProgress?: (pct: number) => void): Promise<FileInfo> {
  const data = await uploadFiles([file], onProgress);
  return data.files[0];
}

export async function uploadVersion(parentId: string, bytes: Uint8Array, name: string): Promise<FileInfo> {
  return uploadFiles([new File([bytes], name, { type: "application/pdf" })], undefined, `/api/files/${parentId}/versions`, "file");
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Start a tool job and wait for it to finish, reporting progress. Throws on failure. */
export async function runTool(
  tool: string,
  fileIds: string[],
  params: Record<string, unknown> = {},
  onProgress?: (pct: number, message: string) => void,
): Promise<Job> {
  let job = await api<Job>(`/api/tools/${tool}`, { method: "POST", json: { file_ids: fileIds, params } });
  return waitForJob(job, onProgress);
}

export async function waitForJob(job: Job, onProgress?: (pct: number, message: string) => void): Promise<Job> {
  let delay = 400;
  while (job.status === "queued" || job.status === "running") {
    onProgress?.(job.progress, job.message || (job.status === "queued" ? "Waiting in queue" : "Working"));
    await sleep(delay);
    delay = Math.min(delay * 1.4, 2000);
    job = await api<Job>(`/api/jobs/${job.id}`);
  }
  onProgress?.(100, job.message);
  if (job.status === "failed") throw new ApiError(job.error || "The job failed.", 400);
  return job;
}

export function inspect<T = any>(fileId: string, what: string, page = 0, q = ""): Promise<T> {
  const params = new URLSearchParams({ page: String(page), q });
  return api<{ result: T }>(`/api/files/${fileId}/inspect/${what}?${params}`).then((r) => r.result);
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}
