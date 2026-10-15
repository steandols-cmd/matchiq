// Formatering: alltid Europe/Stockholm i gränssnittet, UTC i lagringen. Saknat värde visas som "saknas".

const TZ = "Europe/Stockholm";
const dateFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, day: "numeric", month: "short" });
const timeFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const dayFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, weekday: "short" });
const longFmt = new Intl.DateTimeFormat("sv-SE", {
  timeZone: TZ, weekday: "long", day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit",
});
const fullFmt = new Intl.DateTimeFormat("sv-SE", {
  timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
});
const isoDayFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });

export const MISSING = "saknas";

export function d(iso?: string | null): Date | null {
  return iso ? new Date(iso) : null;
}
export function fmtTime(iso?: string | null): string {
  const x = d(iso);
  return x ? timeFmt.format(x) : "–";
}
export function fmtDate(iso?: string | null): string {
  const x = d(iso);
  return x ? dateFmt.format(x).replace(".", "") : "–";
}
export function fmtDay(iso?: string | null): string {
  const x = d(iso);
  if (!x) return "–";
  const s = dayFmt.format(x).replace(".", "");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
export function fmtLong(iso?: string | null): string {
  const x = d(iso);
  return x ? longFmt.format(x) : MISSING;
}
export function fmtFull(iso?: string | null): string {
  const x = d(iso);
  return x ? fullFmt.format(x) : MISSING;
}
export function localDay(iso: string): string {
  return isoDayFmt.format(new Date(iso));
}
export function num(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return MISSING;
  return v.toLocaleString("sv-SE", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
export function pct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return MISSING;
  return `${(v * 100).toLocaleString("sv-SE", { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`;
}
/** Avrunda tre sannolikheter till heltalsprocent som alltid summerar till exakt 100 (största resten). */
export function roundTo100(p: [number, number, number]): [number, number, number] {
  const raw = p.map((x) => x * 100);
  const floor = raw.map(Math.floor);
  let rest = 100 - floor.reduce((a, b) => a + b, 0);
  const order = raw.map((x, i) => [x - Math.floor(x), i] as [number, number]).sort((a, b) => b[0] - a[0]);
  for (const [, i] of order) {
    if (rest <= 0) break;
    floor[i] += 1;
    rest -= 1;
  }
  return floor as [number, number, number];
}
export function fairOdds(p?: number | null): string {
  if (!p) return MISSING;
  return num(1 / p, 2);
}
export function minutesUntil(iso: string, nowIso?: string): number {
  const now = nowIso ? new Date(nowIso) : new Date();
  return (new Date(iso).getTime() - now.getTime()) / 60000;
}
export function relTime(iso: string, nowIso?: string): string {
  const m = minutesUntil(iso, nowIso);
  const a = Math.abs(m);
  const s = a < 60 ? `${Math.round(a)} min` : a < 48 * 60 ? `${Math.round(a / 60)} h` : `${Math.round(a / 1440)} d`;
  return m >= 0 ? `om ${s}` : `för ${s} sedan`;
}
export function initials(name: string): string {
  const stop = new Set(["fc", "cf", "sc", "ac", "as", "fk", "sk", "bk", "if", "club", "de", "rc", "ssc", "afc", "the", "1."]);
  const words = name.replace(/[^\p{L}\p{N}\s.]/gu, " ").split(/\s+/).filter(Boolean);
  const sig = words.filter((w) => !stop.has(w.toLowerCase()));
  const use = sig.length ? sig : words;
  if (use.length === 1) return use[0].slice(0, 3).toUpperCase();
  return use.slice(0, 3).map((w) => w[0]).join("").toUpperCase();
}
