// Hantering av backend-sidecaren (Python). Ingen Electron-import här, så modulen kan testas med Node.
import { spawn, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import * as fs from "node:fs";
import * as http from "node:http";
import * as path from "node:path";

export interface BackendCommand {
  command: string;
  args: string[];
  cwd?: string;
  env?: NodeJS.ProcessEnv;
}

export interface BackendHandle {
  port: number;
  token: string;
  baseUrl: string;
  proc: ChildProcess;
  stop(): Promise<void>;
}

export interface StartOptions extends BackendCommand {
  dataDir: string;
  timeoutMs?: number;
  log?: (line: string) => void;
  extraArgs?: string[];
}

/** Var finns backend? Paketerad app: PyInstaller-mappen i resources. Utveckling: Python-källkoden. */
export function resolveBackendCommand(isPackaged: boolean, resourcesPath: string, repoRoot: string): BackendCommand {
  if (isPackaged) {
    const exe = process.platform === "win32" ? "matchiq-backend.exe" : "matchiq-backend";
    return { command: path.join(resourcesPath, "backend", exe), args: [] };
  }
  const python = process.env.MATCHIQ_PYTHON || (process.platform === "win32" ? "python" : "python3");
  const backendDir = path.join(repoRoot, "backend");
  return {
    command: python,
    args: ["-m", "matchiq"],
    cwd: backendDir,
    env: { PYTHONPATH: backendDir },
  };
}

export function newToken(): string {
  return randomBytes(32).toString("base64url");
}

export function startBackend(opts: StartOptions): Promise<BackendHandle> {
  const token = newToken();
  fs.mkdirSync(opts.dataDir, { recursive: true });
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    ...(opts.env || {}),
    MATCHIQ_TOKEN: token,
    MATCHIQ_PARENT_PID: String(process.pid),
    MATCHIQ_DATA_DIR: opts.dataDir,
    PYTHONUNBUFFERED: "1",
    PYTHONIOENCODING: "utf-8",
  };
  const args = [...opts.args, "--port", "0", "--data-dir", opts.dataDir, ...(opts.extraArgs || [])];
  const proc = spawn(opts.command, args, { cwd: opts.cwd, env, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
  const log = opts.log || (() => undefined);
  let stderrTail = "";

  return new Promise<BackendHandle>((resolve, reject) => {
    let done = false;
    const timer = setTimeout(() => {
      if (!done) {
        done = true;
        proc.kill();
        reject(new Error(`Backend startade inte inom ${opts.timeoutMs ?? 45000} ms. ${stderrTail.slice(-800)}`));
      }
    }, opts.timeoutMs ?? 45000);
    let buf = "";
    proc.stdout!.setEncoding("utf8");
    proc.stdout!.on("data", (chunk: string) => {
      buf += chunk;
      let idx: number;
      while ((idx = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, idx).trim();
        buf = buf.slice(idx + 1);
        log(line);
        const m = /^MATCHIQ_READY port=(\d+)$/.exec(line);
        if (m && !done) {
          done = true;
          clearTimeout(timer);
          const port = Number(m[1]);
          const baseUrl = `http://127.0.0.1:${port}`;
          resolve({
            port, token, baseUrl, proc,
            stop: () => stopProcess(proc),
          });
        }
      }
    });
    proc.stderr!.setEncoding("utf8");
    proc.stderr!.on("data", (chunk: string) => {
      stderrTail = (stderrTail + chunk).slice(-4000);
      chunk.split(/\r?\n/).filter(Boolean).forEach((l) => log(`[backend] ${l}`));
    });
    proc.on("exit", (code) => {
      if (!done) {
        done = true;
        clearTimeout(timer);
        reject(new Error(`Backend avslutades (kod ${code}) innan den var redo. ${stderrTail.slice(-800)}`));
      }
    });
    proc.on("error", (err) => {
      if (!done) {
        done = true;
        clearTimeout(timer);
        reject(err);
      }
    });
  });
}

function stopProcess(proc: ChildProcess): Promise<void> {
  return new Promise((resolve) => {
    if (proc.exitCode !== null || proc.killed) return resolve();
    const t = setTimeout(() => {
      try { proc.kill("SIGKILL"); } catch { /* redan avslutad */ }
      resolve();
    }, 4000);
    proc.once("exit", () => { clearTimeout(t); resolve(); });
    proc.kill();
  });
}

/** Enkel GET mot backend med token (används för hälsokontroll och aviseringar från huvudprocessen). */
export function apiGet<T = unknown>(b: { port: number; token: string }, p: string): Promise<{ status: number; body: T }> {
  return request<T>(b, "GET", p);
}

export function apiPost<T = unknown>(b: { port: number; token: string }, p: string, body: unknown): Promise<{ status: number; body: T }> {
  return request<T>(b, "POST", p, body);
}

function request<T>(b: { port: number; token: string }, method: string, p: string, body?: unknown): Promise<{ status: number; body: T }> {
  return new Promise((resolve, reject) => {
    const data = body === undefined ? undefined : Buffer.from(JSON.stringify(body));
    const req = http.request({
      host: "127.0.0.1", port: b.port, path: `/api${p}`, method,
      headers: { Authorization: `Bearer ${b.token}`, ...(data ? { "Content-Type": "application/json", "Content-Length": data.length } : {}) },
    }, (res) => {
      let s = "";
      res.setEncoding("utf8");
      res.on("data", (c) => (s += c));
      res.on("end", () => {
        try { resolve({ status: res.statusCode || 0, body: (s ? JSON.parse(s) : null) as T }); } catch (e) { reject(e); }
      });
    });
    req.on("error", reject);
    if (data) req.write(data);
    req.end();
  });
}
