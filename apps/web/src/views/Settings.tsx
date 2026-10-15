import { useEffect, useState } from "react";
import { api, bridge, openReport } from "../api";
import { fmtFull } from "../format";
import { Icon, Loading, Panel, StatusBadge, Switch } from "../ui";

export function SettingsView({ meta, onTheme }: { meta: any; onTheme: () => void }) {
  const [settings, setSettings] = useState<any>(null);
  const [secrets, setSecrets] = useState<any>(null);
  const [db, setDb] = useState<any>(null);
  const [sched, setSched] = useState<any>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [reports, setReports] = useState<any[]>([]);
  const [bg, setBg] = useState<{ openAtLogin: boolean; background: boolean } | null>(null);
  const [keyIn, setKeyIn] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [rev, setRev] = useState(0);
  const br = bridge();
  useEffect(() => {
    api("/settings").then(setSettings);
    api("/secrets").then(setSecrets);
    api("/db").then(setDb);
    api("/scheduler").then(setSched);
    api("/scheduler/jobs").then(setJobs);
    api("/reports").then(setReports);
    br?.getBackgroundMode().then(setBg).catch(() => undefined);
  }, [rev]);
  const save = async (patch: any) => {
    try { setSettings(await api("/settings", { method: "PUT", body: patch })); onTheme(); } catch (e: any) { setMsg(e.message); }
  };
  const act = async (fn: () => Promise<any>, ok: (r: any) => string) => {
    try { const r = await fn(); setMsg(ok(r)); setRev((x) => x + 1); } catch (e: any) { setMsg(e.message); }
  };
  if (!settings || !secrets || !db) return <Loading />;
  const byDate = new Map<string, any[]>();
  reports.forEach((r) => { const k = `${r.path.split(/[\\/]/).slice(-3, -1).join(" / ")}`; byDate.set(k, [...(byDate.get(k) || []), r]); });
  return (
    <div className="col" style={{ gap: 14 }}>
      {msg && <div className="callout"><span className="ic">{Icon.info()}</span>{msg}<button className="btn sm" style={{ marginLeft: "auto" }} onClick={() => setMsg(null)}>OK</button></div>}
      <div className="layout-2">
        <Panel title="Bakgrundskörning och schemaläggare" icon={Icon.clock()}>
          <div className="panel-pad col">
            <div className="row"><span className={`dot ${sched?.running ? "ok" : "warn"}`} /><b>{sched?.running ? "Schemaläggaren är aktiv" : "Schemaläggaren är stoppad"}</b><span className="small muted">klocka: {sched?.clock}</span></div>
            <div className="small muted">T−30-rapporter skapas så länge appen körs. Med bakgrundskörning startar appen vid inloggning och fortsätter i menyfältet/aktivitetsfältet när fönstret stängs.</div>
            {br ? (
              <Switch checked={!!bg?.background} label="Bakgrundskörning + autostart vid inloggning" onChange={async (v) => {
                const r = await br.setBackgroundMode(v); setBg(r); save({ background_mode: v, autostart: r.openAtLogin });
              }} />
            ) : <div className="callout warn small"><span className="ic">{Icon.info()}</span>Bakgrundskörning styrs från desktopappen (inte tillgängligt i webbläsarläge).</div>}
            {bg && <div className="small">Autostart: {bg.openAtLogin ? <StatusBadge kind="ok">På</StatusBadge> : <StatusBadge kind="neutral">Av</StatusBadge>}</div>}
            <div className="small">Nästa rapport: {sched?.next_job ? `${sched.next_job.home} – ${sched.next_job.away}, ${fmtFull(sched.next_job.due_at_utc)}` : "inga schemalagda"}</div>
            <div className="small muted">Jobb: {Object.entries(sched?.job_counts || {}).map(([k, v]) => `${k} ${v}`).join(" · ") || "inga"}</div>
            <div className="row"><button className="btn sm" onClick={() => act(() => api("/scheduler/tick", { body: {} }), () => "Schemaläggaren kördes nu.")}>{Icon.refresh(14)} Kör nu</button>
              <button className="btn sm" onClick={() => act(() => api("/sync", { body: {} }), () => "Datasynk startad.")}>Synka källor nu</button></div>
          </div>
        </Panel>
        <Panel title="Utseende" icon={Icon.gear()}>
          <div className="panel-pad col">
            <div className="seg" style={{ alignSelf: "flex-start" }}>
              <button className={settings.theme !== "light" ? "on" : ""} onClick={() => save({ theme: "matchiq-dark" })}>Mörkt (MatchIQ)</button>
              <button className={settings.theme === "light" ? "on" : ""} onClick={() => save({ theme: "light" })}>Ljus arbetsyta</button>
            </div>
            <div className="small muted">Mörkt tema följer mockuperna. Ljust tema: ljus arbetsyta, marinblå rubriker och ljusblå tabellränder (samma stil som PDF-rapporterna).</div>
            <div className="small">Tidszon i gränssnittet: Europe/Stockholm · lagring: UTC · rapporttid: T−30 (låst)</div>
          </div>
        </Panel>
      </div>
      <Panel title="API-nycklar" icon={Icon.shield()} right={<span className="small muted">Lagras i {secrets.backend} – aldrig i databasen eller källkoden</span>}>
        <div className="scroll-x"><table className="t"><tbody>{secrets.keys.map((k: any) => (
          <tr key={k.name}><td>{k.label}</td><td>{k.configured ? <StatusBadge kind="ok">Konfigurerad</StatusBadge> : <StatusBadge kind="neutral">Saknas</StatusBadge>}</td>
            <td><input className="in" type="password" autoComplete="off" placeholder={k.configured ? "Ersätt nyckel…" : "Klistra in nyckel"} value={keyIn[k.name] || ""} onChange={(e) => setKeyIn({ ...keyIn, [k.name]: e.target.value })} style={{ width: 260 }} /></td>
            <td><div className="row"><button className="btn sm" disabled={!keyIn[k.name]} onClick={() => act(() => api(`/secrets/${k.name}`, { method: "PUT", body: { value: keyIn[k.name] } }).then(() => setKeyIn({ ...keyIn, [k.name]: "" })), () => "Nyckeln sparades i nyckelförrådet.")}>Spara</button>
              {k.configured && <button className="btn sm danger" onClick={() => act(() => api(`/secrets/${k.name}`, { method: "DELETE" }), () => "Nyckeln togs bort.")}>Ta bort</button>}</div></td></tr>))}</tbody></table></div>
        <div className="small muted panel-pad">Utan nycklar fungerar appen med öppna källor och import. API-Football ger bekräftade startelvor och skador; The Odds API ger marknadsodds för jämförelse.</div>
      </Panel>
      <div className="layout-2">
        <Panel title="Databas – åtkomst, export och migrering" icon={Icon.db()}>
          <div className="panel-pad col small">
            <div><b>Datamapp:</b> <span className="mono">{db.data_dir}</span></div>
            <div><b>Databasfil:</b> <span className="mono">{db.path}</span> ({(db.bytes / 1e6).toFixed(1)} MB) · schemaversion {db.schema_version}</div>
            <div className="row wrap">
              {br && <button className="btn sm" onClick={() => br.showItemInFolder(db.path)}>Visa i Finder/Utforskaren</button>}
              <button className="btn sm" onClick={() => act(() => api("/db/backup", { body: {} }), (r) => `Säkerhetskopia skapad: ${r.path}`)}>Säkerhetskopiera nu</button>
              <button className="btn sm primary" onClick={() => act(() => api("/db/export", { body: {} }), (r) => `Export klar: ${r.path}`)}>Exportera hela databasen</button>
              {br && <button className="btn sm" onClick={async () => {
                const p = await br.pickFile([{ name: "MatchIQ-export", extensions: ["zip"] }]);
                if (p && window.confirm("Ersätta aktuell databas med exporten? Aktuell databas säkerhetskopieras först.")) act(() => api("/db/import", { body: { path: p } }), (r) => `Import klar. Säkerhetskopia av tidigare databas: ${r.backup}`);
              }}>Läs in export…</button>}
            </div>
            <div className="muted">Exporten är en zip med komplett SQLite-fil, en CSV per tabell, schema och manifest med SHA-256. Den kan läsas in i en nyare version av appen (migreras automatiskt framåt) eller öppnas med valfri SQLite-klient. Före varje migrering tas en säkerhetskopia.</div>
            <div><b>Migreringar:</b> {db.migrations.map((m: any) => `v${m.version} ${m.name} (${fmtFull(m.applied_at_utc)})`).join(", ")}</div>
            {db.exports.length > 0 && <div><b>Senaste exporter:</b>{db.exports.slice(0, 3).map((e: any) => <div key={e.path} className="mono tiny">{e.path}</div>)}</div>}
            <details><summary>Tabeller ({Object.keys(db.tables).length})</summary><div className="mono tiny">{Object.entries(db.tables).map(([t, n]) => `${t}: ${n}`).join(" · ")}</div></details>
          </div>
        </Panel>
        <Panel title="PDF-arkiv" icon={Icon.pdf()} right={<span className="small muted">reports/ÅÅÅÅ-MM-DD/TÄVLING/</span>}>
          <div style={{ maxHeight: 360, overflow: "auto" }}>
            {reports.length === 0 ? <div className="empty">Inga rapporter ännu.</div> : Array.from(byDate.entries()).map(([k, list]) => (
              <div key={k}><div className="panel-pad small" style={{ paddingBottom: 4 }}><b>{k}</b></div>
                {list.map((r) => (<div key={r.id} className="mini-row" style={{ gridTemplateColumns: "60px minmax(0,1fr) auto" }}>
                  <span>{r.kind === "late" ? <StatusBadge kind="err">SEN</StatusBadge> : r.kind === "T-30" ? <StatusBadge kind="ok">T−30</StatusBadge> : <StatusBadge kind="neutral">{r.kind}</StatusBadge>}</span>
                  <div className="teams"><div>{r.home} – {r.away}</div><div className="tiny muted">skapad {fmtFull(r.created_at_utc)}{r.exists ? "" : " · FIL SAKNAS"}</div></div>
                  <button className="btn sm" disabled={!r.exists} onClick={() => openReport(r)}>Öppna</button></div>))}
              </div>))}
          </div>
        </Panel>
      </div>
      <Panel title="Schemalagda rapportjobb" icon={Icon.cal()}>
        <div className="scroll-x" style={{ maxHeight: 320, overflow: "auto" }}><table className="t"><thead><tr><th>Match</th><th>Tävling</th><th>Avspark</th><th>T−30</th><th>Status</th><th>Kommentar</th></tr></thead>
          <tbody>{jobs.map((j) => <tr key={j.id}><td>{j.home} – {j.away}</td><td>{j.competition}</td><td>{fmtFull(j.kickoff_utc)}</td><td>{fmtFull(j.due_at_utc)}</td>
            <td>{j.status === "done" ? <StatusBadge kind="ok">klar</StatusBadge> : j.status === "pending" ? <StatusBadge kind="info">väntar</StatusBadge> : j.status === "late_done" ? <StatusBadge kind="err">sen rapport</StatusBadge> : <StatusBadge kind="neutral">{j.status}</StatusBadge>}</td>
            <td className="small muted">{j.last_error || (j.late_by_seconds ? `missad med ${Math.round(j.late_by_seconds / 60)} min` : "")}</td></tr>)}</tbody></table></div>
      </Panel>
      <Panel title="Om MatchIQ" icon={Icon.info()}>
        <div className="panel-pad small col">
          <div>MatchIQ {meta?.version} · statistisk prognosmotor. Prognoserna är statistiska skattningar, inte löften om utfall.</div>
          <div className="muted">Data: OpenFootball (CC0) · StatsBomb (Hudl) Open Data när aktiverad · övriga källor enligt källregistret. Klubbmärken visas som genererade sköldar; inga riktiga logotyper ingår.</div>
          <div className="muted">Loggar: <span className="mono">{meta?.data_dir}/logs/backend.log</span></div>
        </div>
      </Panel>
    </div>
  );
}
