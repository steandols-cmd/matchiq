// Electron-huvudprocess: startar backend-sidecaren, servar gränssnittet via app://, hanterar
// bakgrundskörning (autostart + systemfält), aviseringar och säkra IPC-anrop.
import { app, BrowserWindow, dialog, ipcMain, Menu, nativeImage, Notification, protocol, shell, Tray } from "electron";
import * as fs from "node:fs";
import * as path from "node:path";
import { apiGet, apiPost, resolveBackendCommand, startBackend, type BackendHandle } from "./backend";

const APP_ORIGIN = "app://matchiq";
const isDev = !app.isPackaged;
const repoRoot = path.resolve(__dirname, "..", "..", "..");
const webRoot = isDev ? path.join(repoRoot, "apps", "web", "dist") : path.join(process.resourcesPath, "web");
const dataDir = process.env.MATCHIQ_DATA_DIR || path.join(app.getPath("userData"), "data");
const prefsFile = path.join(app.getPath("userData"), "desktop-prefs.json");
const logFile = path.join(app.getPath("userData"), "desktop.log");

let win: BrowserWindow | null = null;
let tray: Tray | null = null;
let backend: BackendHandle | null = null;
let quitting = false;

interface Prefs { background: boolean }
function readPrefs(): Prefs {
  try { return { background: false, ...JSON.parse(fs.readFileSync(prefsFile, "utf8")) }; } catch { return { background: false }; }
}
function writePrefs(p: Prefs) {
  fs.mkdirSync(path.dirname(prefsFile), { recursive: true });
  fs.writeFileSync(prefsFile, JSON.stringify(p, null, 2));
}
function log(line: string) {
  try { fs.appendFileSync(logFile, `${new Date().toISOString()} ${line}\n`); } catch { /* ignoreras */ }
}

protocol.registerSchemesAsPrivileged([
  { scheme: "app", privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } },
]);

const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json", ".woff2": "font/woff2",
};

function serveApp() {
  protocol.handle("app", async (request) => {
    const url = new URL(request.url);
    let rel = decodeURIComponent(url.pathname);
    if (rel === "/" || rel === "") rel = "/index.html";
    const file = path.normalize(path.join(webRoot, rel));
    if (!file.startsWith(path.normalize(webRoot))) return new Response("Förbjudet", { status: 403 });
    try {
      // Uint8Array (kopia) i stället för Buffer: kompatibel med BodyInit i nyare TypeScript-lib.
      const data = new Uint8Array(await fs.promises.readFile(file));
      return new Response(data, { headers: { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" } });
    } catch {
      return new Response("Saknas", { status: 404 });
    }
  });
}

function isTrustedSender(frameUrl: string | undefined): boolean {
  return !!frameUrl && frameUrl.startsWith(`${APP_ORIGIN}/`);
}

function createWindow(show = true) {
  win = new BrowserWindow({
    width: 1480, height: 940, minWidth: 380, minHeight: 600, show: false, backgroundColor: "#061428", title: "MatchIQ",
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  win.loadURL(`${APP_ORIGIN}/index.html#/matcher`);
  win.once("ready-to-show", () => { if (show) win?.show(); });
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://")) shell.openExternal(url);
    // Blob-fönster används för att visa PDF-rapporter när de inte kan öppnas i systemets PDF-läsare.
    return url.startsWith("blob:") ? { action: "allow" } : { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => { if (!url.startsWith(APP_ORIGIN)) e.preventDefault(); });
  win.on("close", (e) => {
    if (!quitting && readPrefs().background) {
      e.preventDefault();
      win?.hide();
      if (process.platform === "darwin") app.dock?.hide();
    }
  });
  win.on("closed", () => { win = null; });
}

function showWindow() {
  if (!win) createWindow(true);
  else { win.show(); win.focus(); }
  if (process.platform === "darwin") app.dock?.show();
}

function trayIcon() {
  const p = isDev ? path.join(__dirname, "..", "build", "tray.png") : path.join(process.resourcesPath, "tray.png");
  const img = nativeImage.createFromPath(p);
  return img.isEmpty() ? nativeImage.createEmpty() : img.resize({ width: 18, height: 18 });
}

function updateTray() {
  const bg = readPrefs().background;
  if (bg && !tray) {
    tray = new Tray(trayIcon());
    tray.setToolTip("MatchIQ – schemaläggaren är aktiv");
    tray.on("click", showWindow);
  }
  if (!bg && tray) { tray.destroy(); tray = null; }
  tray?.setContextMenu(Menu.buildFromTemplate([
    { label: "Öppna MatchIQ", click: showWindow },
    { label: "Schemaläggaren är aktiv (T−30-rapporter)", enabled: false },
    { type: "separator" },
    { label: "Avsluta MatchIQ", click: () => { quitting = true; app.quit(); } },
  ]));
}

function setBackground(enabled: boolean) {
  writePrefs({ ...readPrefs(), background: enabled });
  // Autostart vid inloggning (macOS och Windows). --hidden startar utan fönster, bara systemfältet.
  app.setLoginItemSettings({ openAtLogin: enabled, args: enabled ? ["--hidden"] : [] });
  updateTray();
  return { openAtLogin: app.getLoginItemSettings().openAtLogin, background: enabled };
}

function registerIpc() {
  ipcMain.handle("matchiq:getBackend", (e) => {
    if (!isTrustedSender(e.senderFrame?.url) || !backend) throw new Error("Ej tillåtet");
    return { baseUrl: backend.baseUrl, token: backend.token };
  });
  const insideData = (p: string) => path.resolve(p).startsWith(path.resolve(dataDir));
  ipcMain.handle("matchiq:openPath", async (e, p: string) => {
    if (!isTrustedSender(e.senderFrame?.url) || !insideData(p)) return "Sökvägen ligger utanför datamappen";
    return shell.openPath(p);
  });
  ipcMain.handle("matchiq:showItemInFolder", (e, p: string) => {
    if (isTrustedSender(e.senderFrame?.url) && insideData(p)) shell.showItemInFolder(p);
  });
  ipcMain.handle("matchiq:setBackgroundMode", (e, enabled: boolean) => {
    if (!isTrustedSender(e.senderFrame?.url)) throw new Error("Ej tillåtet");
    return setBackground(!!enabled);
  });
  ipcMain.handle("matchiq:getBackgroundMode", () => ({ openAtLogin: app.getLoginItemSettings().openAtLogin, background: readPrefs().background }));
  ipcMain.handle("matchiq:pickFile", async (e, filters?: { name: string; extensions: string[] }[]) => {
    if (!isTrustedSender(e.senderFrame?.url)) return null;
    const r = await dialog.showOpenDialog({ properties: ["openFile"], filters: filters || [] });
    return r.canceled ? null : r.filePaths[0];
  });
}

/** Operativsystemsaviseringar när en T−30-rapport (eller sen rapport) skapats – även när fönstret är dolt. */
function startNotificationPoller() {
  setInterval(async () => {
    if (!backend || !Notification.isSupported()) return;
    try {
      const r = await apiGet<any[]>(backend, "/notifications?undelivered=1");
      if (r.status !== 200 || !r.body?.length) return;
      for (const n of r.body.slice(0, 5)) {
        const note = new Notification({ title: n.title, body: n.body || "", silent: n.level === "info" });
        note.on("click", () => { showWindow(); if (n.match_id) win?.webContents.executeJavaScript(`location.hash='#/match/${Number(n.match_id)}'`); });
        note.show();
      }
      await apiPost(backend, "/notifications/mark", { ids: r.body.map((n) => n.id), delivered: true });
    } catch (err) { log(`aviseringsfel: ${String(err)}`); }
  }, 30_000);
}

async function boot() {
  const hidden = process.argv.includes("--hidden");
  serveApp();
  registerIpc();
  try {
    backend = await startBackend({ ...resolveBackendCommand(!isDev, process.resourcesPath, repoRoot), dataDir, log });
    log(`backend redo på port ${backend.port}`);
    backend.proc.on("exit", (code) => {
      log(`backend avslutades (${code})`);
      if (!quitting) dialog.showErrorBox("MatchIQ", `Backend avslutades oväntat (kod ${code}). Starta om appen. Logg: ${logFile}`);
    });
  } catch (err) {
    log(`backend-fel: ${String(err)}`);
    dialog.showErrorBox("MatchIQ kunde inte starta", `${String(err)}\n\nLogg: ${logFile}`);
    app.quit();
    return;
  }
  updateTray();
  createWindow(!(hidden && readPrefs().background));
  startNotificationPoller();
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", showWindow);
  app.whenReady().then(boot);
  app.on("activate", showWindow);
  app.on("window-all-closed", () => {
    if (!readPrefs().background && process.platform !== "darwin") { quitting = true; app.quit(); }
  });
  app.on("before-quit", async (e) => {
    quitting = true;
    if (backend) {
      e.preventDefault();
      const b = backend;
      backend = null;
      await b.stop();
      app.quit();
    }
  });
}
