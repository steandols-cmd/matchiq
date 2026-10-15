import { useCallback, useEffect, useMemo, useState } from "react";
import { api, bridge } from "./api";
import { fmtFull, relTime } from "./format";
import { Flag, Icon } from "./ui";
import { MatchesView } from "./views/Matches";
import { MatchView } from "./views/Match";
import { TeamsView } from "./views/Teams";
import { DataView } from "./views/Data";
import { EvaluationView } from "./views/Evaluation";
import { SettingsView } from "./views/Settings";

export interface Route {
  path: string[];
  params: URLSearchParams;
}

function parseHash(): Route {
  const h = window.location.hash.replace(/^#\/?/, "");
  const [p, q] = h.split("?");
  return { path: (p || "matcher").split("/").filter(Boolean), params: new URLSearchParams(q || "") };
}

export function navigate(to: string) {
  window.location.hash = to.startsWith("#") ? to : `#/${to.replace(/^\//, "")}`;
}

export function useRoute(): Route {
  const [r, setR] = useState<Route>(parseHash());
  useEffect(() => {
    const f = () => setR(parseHash());
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  return r;
}

export interface Competition { code: string; name: string; show_in_tabs: number; tab_order: number | null; matches: number; upcoming: number }

export function CompetitionTabs({ comps, active, onPick }: { comps: Competition[]; active: string; onPick: (c: string) => void }) {
  const tabs = comps.filter((c) => c.show_in_tabs).sort((a, b) => (a.tab_order || 99) - (b.tab_order || 99));
  return (
    <nav className="comp-tabs" aria-label="Tävlingar">
      {tabs.map((c) => (
        <button key={c.code} className={`comp-tab ${c.code === active ? "active" : ""}`} onClick={() => onPick(c.code)} title={`${c.name} – ${c.matches} matcher`}>
          <Flag code={c.code} />
          <span>{c.name}</span>
        </button>
      ))}
    </nav>
  );
}

export function App() {
  const route = useRoute();
  const [meta, setMeta] = useState<any>(null);
  const [comps, setComps] = useState<Competition[]>([]);
  const [sched, setSched] = useState<any>(null);
  const [toast, setToast] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const loadTheme = useCallback(async () => {
    try {
      const s = await api("/settings");
      document.documentElement.dataset.theme = s.theme === "light" ? "light" : "dark";
    } catch {
      /* ignoreras */
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        setMeta(await api("/meta"));
        setComps(await api("/competitions"));
        await loadTheme();
      } catch (e: any) {
        setError(e?.message || String(e));
      }
    })();
  }, [loadTheme]);

  useEffect(() => {
    let alive = true;
    let lastSeen = 0;
    const tick = async () => {
      try {
        const s = await api("/scheduler");
        if (alive) setSched(s);
        const notes: any[] = await api("/notifications?unread=1");
        const fresh = notes.filter((n) => n.id > lastSeen);
        if (fresh.length && lastSeen) setToast(fresh[0]);
        if (notes.length) lastSeen = Math.max(lastSeen, ...notes.map((n) => n.id));
        else if (!lastSeen) lastSeen = 1;
      } catch {
        /* backend kan starta om */
      }
    };
    tick();
    const t = setInterval(tick, 20000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const section = route.path[0] || "matcher";
  const nav = [
    ["matcher", "Matcher"], ["lag", "Lag & spelare"], ["data", "Data & källor"], ["utvardering", "Utvärdering"],
  ];
  const defaultComp = route.params.get("c") || "UCL";

  const view = useMemo(() => {
    switch (section) {
      case "match": return <MatchView key={`${route.path[1]}-${route.params.get("flik") || ""}`} id={Number(route.path[1])} route={route} comps={comps} />;
      case "lag": return <TeamsView id={route.path[1] ? Number(route.path[1]) : null} route={route} />;
      case "data": return <DataView route={route} comps={comps} onChanged={() => api("/competitions").then(setComps)} />;
      case "utvardering": return <EvaluationView route={route} />;
      case "installningar": return <SettingsView meta={meta} onTheme={loadTheme} />;
      default: return <MatchesView comp={defaultComp} route={route} comps={comps} />;
    }
  }, [section, route, comps, meta, defaultComp, loadTheme]);

  if (error) {
    return (
      <div className="page">
        <div className="callout err"><span className="ic">{Icon.warn()}</span>
          <div><b>Kunde inte nå backend.</b><div className="small">{error}</div>
            <div className="small muted">Starta om appen. Om felet kvarstår: se loggfilen i datamappen (logs/backend.log).</div></div>
        </div>
      </div>
    );
  }

  const next = sched?.next_job;
  return (
    <>
      <header className="topbar">
        <a className="brand" href="#/matcher">
          <span className="logo">MATCH<b>IQ</b></span>
          <span className="ver">{meta ? meta.version.split(".").slice(0, 2).join(".") : ""}</span>
        </a>
        <span className="brand-sub">Football Intelligence</span>
        <nav className="nav">
          {nav.map(([k, label]) => (
            <a key={k} href={`#/${k}`} className={section === k || (k === "matcher" && section === "match") ? "active" : ""}>{label}</a>
          ))}
          <span className="sched-chip" title={sched ? `Klocka: ${sched.clock}. Jobbstatus: ${JSON.stringify(sched.job_counts)}` : ""}>
            <i className={`dot ${sched?.running ? "ok" : "warn"}`} />
            {sched?.running ? "Schemaläggare aktiv" : "Schemaläggare stoppad"}
            {next && <span className="muted">· nästa T−30 {relTime(next.due_at_utc, sched.now_utc)}</span>}
          </span>
          <a href="#/installningar" className={section === "installningar" ? "active" : ""} title="Inställningar" aria-label="Inställningar">{Icon.gear(20)}</a>
        </nav>
      </header>
      <main className="page">{view}</main>
      {toast && (
        <div className="toast" role="status">
          <div className="row"><b>{toast.title}</b><button className="btn sm" style={{ marginLeft: "auto" }} onClick={() => setToast(null)}>OK</button></div>
          <div className="small muted">{toast.body}</div>
          <div className="tiny muted">{fmtFull(toast.created_at_utc)}</div>
        </div>
      )}
      {bridge() ? null : null}
    </>
  );
}
