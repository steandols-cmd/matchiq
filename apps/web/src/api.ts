// Klient mot den lokala backend-sidecaren. Token och adress kommer från Electron-bryggan
// (window.matchiq) eller – i utvecklingsläge i webbläsare – från URL:en (#…?token=…).

export interface Backend {
  baseUrl: string;
  token: string;
}

export interface DesktopBridge {
  getBackend(): Promise<Backend>;
  openPath(p: string): Promise<string>;
  showItemInFolder(p: string): Promise<void>;
  setBackgroundMode(enabled: boolean): Promise<{ openAtLogin: boolean; background: boolean }>;
  getBackgroundMode(): Promise<{ openAtLogin: boolean; background: boolean }>;
  pickFile(filters?: { name: string; extensions: string[] }[]): Promise<string | null>;
  platform: string;
  version: string;
}

declare global {
  interface Window {
    matchiq?: DesktopBridge;
  }
}

let backendPromise: Promise<Backend> | null = null;

export function bridge(): DesktopBridge | undefined {
  return window.matchiq;
}

function fromLocation(): Backend {
  const params = new URLSearchParams(window.location.search || window.location.hash.split("?")[1] || "");
  let token = params.get("token") || "";
  if (token) {
    try {
      sessionStorage.setItem("matchiq_token", token);
    } catch {
      /* lagring kan vara blockerad */
    }
    const clean = window.location.href.replace(/([?&])token=[^&#]*/, "$1").replace(/[?&]$/, "");
    window.history.replaceState(null, "", clean);
  } else {
    try {
      token = sessionStorage.getItem("matchiq_token") || "";
    } catch {
      token = "";
    }
  }
  const api = params.get("api") || window.location.origin;
  return { baseUrl: api.replace(/\/$/, ""), token };
}

export function getBackend(): Promise<Backend> {
  if (!backendPromise) {
    backendPromise = window.matchiq ? window.matchiq.getBackend() : Promise.resolve(fromLocation());
  }
  return backendPromise;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown; raw?: BodyInit; headers?: Record<string, string> } = {}): Promise<T> {
  const b = await getBackend();
  const headers: Record<string, string> = { Authorization: `Bearer ${b.token}`, ...(opts.headers || {}) };
  let body: BodyInit | undefined = opts.raw;
  if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(`${b.baseUrl}/api${path}`, { method: opts.method || (body ? "POST" : "GET"), headers, body });
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = typeof data === "object" && data && "error" in data ? String((data as any).error) : `HTTP ${res.status}`;
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

export async function apiBlob(path: string): Promise<Blob> {
  const b = await getBackend();
  const res = await fetch(`${b.baseUrl}/api${path}`, { headers: { Authorization: `Bearer ${b.token}` } });
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`);
  return res.blob();
}

export async function openReport(report: { id: number; path: string }): Promise<void> {
  const br = bridge();
  if (br) {
    const err = await br.openPath(report.path);
    if (!err) return;
  }
  const blob = await apiBlob(`/reports/${report.id}/file`);
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

export async function pollJob<T = any>(jobId: string, onProgress?: (j: any) => void): Promise<T> {
  for (;;) {
    const j = await api(`/jobs/${jobId}`);
    onProgress?.(j);
    if (j.status === "done") return j.result as T;
    if (j.status === "error") throw new Error(j.error || "Jobbet misslyckades");
    await new Promise((r) => setTimeout(r, 700));
  }
}
