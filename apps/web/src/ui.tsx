import { useEffect, useState, type ReactNode } from "react";
import { apiBlob } from "./api";
import { initials, num, roundTo100 } from "./format";

// ------------------------------------------------------------------ ikoner (egna, generiska)
const P = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" } as const;
export const Icon = {
  bars: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><path d="M5 20V12M12 20V5M19 20v-8" /></svg>),
  search: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></svg>),
  scale: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><path d="M12 4v16M7 20h10M5 7h14M5 7l-3 6a3 3 0 0 0 6 0zM19 7l-3 6a3 3 0 0 0 6 0z" /></svg>),
  db: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><ellipse cx="12" cy="5.5" rx="7" ry="2.8" /><path d="M5 5.5v13c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8v-13M5 12c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8" /></svg>),
  flag: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><path d="M6 21V4M6 4h11l-2 4 2 4H6" /></svg>),
  target: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="4" /><circle cx="12" cy="12" r=".8" fill="currentColor" /></svg>),
  net: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><rect x="3" y="5" width="18" height="13" rx="1" /><path d="M3 9h18M3 13h18M8 5v13M13 5v13M18 5v13" /></svg>),
  trend: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><path d="m3 17 6-6 4 4 8-8M15 7h6v6" /></svg>),
  trophy: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><path d="M8 4h8v5a4 4 0 0 1-8 0zM8 6H4a3 3 0 0 0 4 4M16 6h4a3 3 0 0 1-4 4M12 13v4M8 20h8" /></svg>),
  users: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><circle cx="9" cy="8" r="3.2" /><circle cx="17" cy="9" r="2.5" /><path d="M3 20c.6-3.3 3-5 6-5s5.4 1.7 6 5M15 15.2c2.8-.4 5 1 5.6 4" /></svg>),
  ball: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><circle cx="12" cy="12" r="9" /><path d="m12 7 4 3-1.5 4.5h-5L8 10zM12 3v4M16 10l4.5-1.5M14.5 14.5 17 19M9.5 14.5 7 19M8 10 3.5 8.5" /></svg>),
  gear: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.6 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></svg>),
  chev: (s = 18) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><path d="m9 6 6 6-6 6" /></svg>),
  info: (s = 16) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></svg>),
  check: (s = 18) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><circle cx="12" cy="12" r="9" /><path d="m8 12 3 3 5-6" /></svg>),
  warn: (s = 18) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><path d="M12 3 2 20h20zM12 10v4M12 17h.01" /></svg>),
  cal: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></svg>),
  shield: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><path d="M12 3 4 6v6c0 4.5 3.4 8 8 9 4.6-1 8-4.5 8-9V6z" /></svg>),
  pdf: (s = 18) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 14h8M8 17h5" /></svg>),
  refresh: (s = 18) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" /></svg>),
  clock: (s = 18) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>),
  pitch: (s = 22) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><rect x="2" y="5" width="20" height="14" rx="1.5" /><path d="M12 5v14" /><circle cx="12" cy="12" r="2.5" /><path d="M2 9h3v6H2M22 9h-3v6h3" /></svg>),
  card: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24"><rect x="7" y="3" width="11" height="16" rx="1.5" fill="#f5c518" transform="rotate(8 12 11)" /></svg>),
  upload: (s = 18) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><path d="M12 16V4M7 9l5-5 5 5M4 20h16" /></svg>),
  bulb: (s = 20) => (<svg width={s} height={s} viewBox="0 0 24 24" {...P}><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z" /></svg>),
};

// ------------------------------------------------------------------ flaggor (allmängods) och tävlingsikoner
export function Flag({ code }: { code: string }) {
  const w = 22, h = 15;
  switch (code) {
    case "SWE1":
      return (<svg className="flag" viewBox="0 0 16 10" width={w} height={h}><rect width="16" height="10" fill="#006aa7" /><rect x="5" width="2" height="10" fill="#fecc00" /><rect y="4" width="16" height="2" fill="#fecc00" /></svg>);
    case "ENG1":
      return (<svg className="flag" viewBox="0 0 30 20" width={w} height={h}><rect width="30" height="20" fill="#fff" /><rect x="13" width="4" height="20" fill="#ce1124" /><rect y="8" width="30" height="4" fill="#ce1124" /></svg>);
    case "ESP1":
      return (<svg className="flag" viewBox="0 0 30 20" width={w} height={h}><rect width="30" height="20" fill="#aa151b" /><rect y="5" width="30" height="10" fill="#f1bf00" /></svg>);
    case "GER1":
      return (<svg className="flag" viewBox="0 0 30 18" width={w} height={h}><rect width="30" height="6" fill="#000" /><rect y="6" width="30" height="6" fill="#dd0000" /><rect y="12" width="30" height="6" fill="#ffce00" /></svg>);
    case "ITA1":
      return (<svg className="flag" viewBox="0 0 30 20" width={w} height={h}><rect width="10" height="20" fill="#009246" /><rect x="10" width="10" height="20" fill="#fff" /><rect x="20" width="10" height="20" fill="#ce2b37" /></svg>);
    case "FRA1":
      return (<svg className="flag" viewBox="0 0 30 20" width={w} height={h}><rect width="10" height="20" fill="#002395" /><rect x="10" width="10" height="20" fill="#fff" /><rect x="20" width="10" height="20" fill="#ed2939" /></svg>);
    default:
      return (<span style={{ color: "#cfe0ff", display: "inline-flex" }}>{Icon.ball(20)}</span>);
  }
}

// ------------------------------------------------------------------ klubbmärke (genererat – inga riktiga logotyper)
const crestCache = new Map<string, string>();
export function Crest({ name, c1, c2, crest, size = 28 }: { name: string; c1?: string | null; c2?: string | null; crest?: string | null; size?: number }) {
  const [url, setUrl] = useState<string | null>(crest ? crestCache.get(crest) || null : null);
  useEffect(() => {
    let alive = true;
    if (crest && !crestCache.has(crest)) {
      apiBlob(`/crests/${encodeURIComponent(crest)}`).then((b) => {
        const u = URL.createObjectURL(b);
        crestCache.set(crest, u);
        if (alive) setUrl(u);
      }).catch(() => undefined);
    }
    return () => { alive = false; };
  }, [crest]);
  if (url) return <img src={url} width={size} height={size} alt="" style={{ objectFit: "contain", flex: "none" }} />;
  const a = c1 || "#1d428a";
  const b = c2 || "#ffffff";
  const txt = initials(name);
  const fs = txt.length >= 3 ? 7.2 : 9;
  return (
    <svg width={size} height={size * 1.12} viewBox="0 0 32 36" style={{ flex: "none" }} aria-label={name}>
      <path d="M16 1.5 3 6v11c0 8 5.7 14.4 13 17.5C23.3 31.4 29 25 29 17V6z" fill={a} stroke="rgba(255,255,255,.75)" strokeWidth="1.4" />
      <path d="M16 4.5 6 8v9c0 6.4 4.4 11.6 10 14.3z" fill={b} opacity="0.22" />
      <text x="16" y="21" textAnchor="middle" fontSize={fs} fontWeight="800" fill="#fff" style={{ fontFamily: "inherit" }}>{txt}</text>
    </svg>
  );
}

// ------------------------------------------------------------------ modellmärken
export function ModelBadge({ family, status }: { family: string; status?: string | null }) {
  if (family === "V2") return <span className="badge v2" title="V2 – enkel jämförelsebaslinje">V2 · BASLINJE</span>;
  if (family === "V3") {
    const prod = status === "produktion";
    return <span className="badge v3" title="V3 – experimentell modell tills den klarat tidsordnad validering">{prod ? "V3 · PRODUKTION" : "V3 · EXPERIMENTELL"}</span>;
  }
  if (family === "BASE") return <span className="badge base">BASLINJE</span>;
  return <span className="badge neutral">{family}</span>;
}

export function StatusBadge({ kind, children }: { kind: "ok" | "warn" | "err" | "info" | "neutral"; children: ReactNode }) {
  return <span className={`badge ${kind}`}>{children}</span>;
}

export function LineupBadge({ status }: { status: string }) {
  if (status === "confirmed") return <StatusBadge kind="ok">Bekräftad</StatusBadge>;
  if (status === "expected") return <StatusBadge kind="warn">Obekräftad</StatusBadge>;
  return <StatusBadge kind="err">Opublicerad</StatusBadge>;
}

// ------------------------------------------------------------------ 1X2
export function ProbCards({ p, compact = false }: { p: { p_home: number; p_draw: number; p_away: number } | null; compact?: boolean }) {
  if (!p) {
    return <div className="callout warn" style={{ marginTop: 14 }}><span className="ic">{Icon.warn()}</span>1X2 saknas – för lite tillåten träningsdata för tävlingen. Inget värde visas som 0.</div>;
  }
  const r = roundTo100([p.p_home, p.p_draw, p.p_away]);
  const bar = (cls: string, color: string) => (
    <div className="bars">{[10, 16, 22, 28].map((h, i) => <i key={i} style={{ height: h, background: color, opacity: 0.35 + i * 0.18 }} />)}</div>
  );
  return (
    <>
      <div className={`prob-cards ${compact ? "compact" : ""}`}>
        <div className="prob-card home"><div className="lbl">Hemma</div><div className="val">{r[0]}%</div>{bar("h", "#22c98a")}</div>
        <div className="prob-card draw"><div className="lbl">X</div><div className="val">{r[1]}%</div>{bar("x", "#3b8cf0")}</div>
        <div className="prob-card away"><div className="lbl">Borta</div><div className="val">{r[2]}%</div>{bar("a", "#e9b83a")}</div>
      </div>
      <div className="prob-bar" aria-label="1X2-fördelning">
        <div className="h" style={{ width: `${r[0]}%` }}>{r[0]}%</div>
        <div className="x" style={{ width: `${r[1]}%` }}>{r[1]}%</div>
        <div className="a" style={{ width: `${r[2]}%` }}>{r[2]}%</div>
      </div>
      <div className="fair">Rättvisa odds: <b>{num(1 / p.p_home, 2)}</b> · <b>{num(1 / p.p_draw, 2)}</b> · <b>{num(1 / p.p_away, 2)}</b></div>
    </>
  );
}

export function P3({ p, empty = "–" }: { p?: { p_home: number | null; p_draw: number | null; p_away: number | null } | null; empty?: string }) {
  if (!p || p.p_home == null || p.p_draw == null || p.p_away == null) {
    return <div className="p3"><div className="na">{empty}</div><div className="na">{empty}</div><div className="na">{empty}</div></div>;
  }
  const r = roundTo100([p.p_home, p.p_draw, p.p_away]);
  const top = r.indexOf(Math.max(...r));
  return <div className="p3">{r.map((v, i) => <div key={i} className={i === top ? "top" : ""}>{v}%</div>)}</div>;
}

export function FormDots({ form }: { form: { result: string }[] }) {
  if (!form.length) return <span className="muted small">ingen historik</span>;
  return <span className="form-dots">{form.slice(0, 5).reverse().map((f, i) => <i key={i} className={f.result}>{f.result}</i>)}</span>;
}

export function Meter({ value, kind }: { value: number | null | undefined; kind?: "warn" | "err" }) {
  const v = value == null ? 0 : Math.max(0, Math.min(1, value));
  const k = kind || (value == null ? "err" : v < 0.6 ? "err" : v < 0.85 ? "warn" : undefined);
  return <div className={`meter ${k || ""}`}><i style={{ width: `${v * 100}%` }} /></div>;
}

export function Panel({ title, icon, right, children, className = "", navy = false }: { title?: ReactNode; icon?: ReactNode; right?: ReactNode; children: ReactNode; className?: string; navy?: boolean }) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className={`panel-head ${navy ? "navy" : ""}`}>
          {icon && <span className="icon">{icon}</span>}
          <h2>{title}</h2>
          {right && <div style={{ marginLeft: "auto" }} className="row">{right}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Loading({ text = "Laddar…" }: { text?: string }) {
  return <div className="loading">{text}</div>;
}

export function ErrorBox({ error }: { error: unknown }) {
  return <div className="callout err" style={{ margin: 12 }}><span className="ic">{Icon.warn()}</span>{String((error as Error)?.message || error)}</div>;
}

export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <label className="row" style={{ cursor: "pointer" }}>
      <span className="switch"><input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} /><span /></span>
      {label && <span>{label}</span>}
    </label>
  );
}

export function Modal({ onClose, title, children }: { onClose: () => void; title: string; children: ReactNode }) {
  return (
    <div className="modal-back" onClick={onClose}>
      <div className="panel modal" onClick={(e) => e.stopPropagation()}>
        <div className="panel-head"><h3>{title}</h3><button className="btn sm" style={{ marginLeft: "auto" }} onClick={onClose}>Stäng</button></div>
        <div className="panel-pad">{children}</div>
      </div>
    </div>
  );
}
