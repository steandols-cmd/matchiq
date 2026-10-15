import { useEffect, useState } from "react";
import { api, pollJob } from "../api";
import { navigate, type Competition, type Route } from "../App";
import { fmtFull, num, pct } from "../format";
import { ErrorBox, Icon, Loading, Meter, Modal, Panel, StatusBadge, Switch } from "../ui";

const TABS: [string, string][] = [["kallor", "Källor & licenser"], ["historik", "Hämta historik"], ["tackning", "Täckning"], ["import", "Import"], ["hamtlogg", "Hämtlogg"], ["andringar", "Ändringslogg"]];

export function DataView({ route, comps, onChanged }: { route: Route; comps: Competition[]; onChanged: () => void }) {
  const tab = route.params.get("tab") || "kallor";
  return (
    <div>
      <div className="tabs">{TABS.map(([k, l]) => (
        <button key={k} className={`tab ${tab === k ? "active" : ""}`} onClick={() => navigate(`data?tab=${k}`)}>{l}</button>))}</div>
      {tab === "kallor" && <Sources />}
      {tab === "historik" && <History comps={comps} onChanged={onChanged} />}
      {tab === "tackning" && <Coverage comps={comps} route={route} />}
      {tab === "import" && <Import onChanged={onChanged} />}
      {tab === "hamtlogg" && <FetchLog />}
      {tab === "andringar" && <ChangeLog />}
    </div>
  );
}

function trainingBadge(s: any) {
  if (s.training_allowed && s.training_policy !== "allowed")
    return <span title={s.training_approval_note || ""}><StatusBadge kind="info">Godkänd av användare</StatusBadge></span>;
  if (s.training_allowed) return <StatusBadge kind="ok">Används i prognoserna</StatusBadge>;
  return <StatusBadge kind={s.training_policy === "blocked" ? "err" : "warn"}>Spärrad från prognoserna</StatusBadge>;
}

function Sources() {
  const [list, setList] = useState<any[] | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [dialog, setDialog] = useState<any>(null);
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const load = () => api("/sources").then(setList).catch(setErr);
  useEffect(() => { load(); }, []);
  if (err) return <ErrorBox error={err} />;
  if (!list) return <Loading />;
  const submit = async () => {
    try {
      if (dialog.kind === "training") await api(`/sources/${dialog.s.id}/training`, { body: { approve: dialog.approve, note } });
      else await api(`/sources/${dialog.s.id}/enabled`, { body: { enabled: dialog.enabled, note } });
      setDialog(null); setNote(""); load();
    } catch (e: any) { setMsg(e.message); }
  };
  const sync = async (s: any) => {
    setMsg(`Hämtar från ${s.name}…`);
    try {
      const { job_id } = await api(`/sources/${s.id}/sync`, { body: {} });
      const r = await pollJob(job_id);
      setMsg(r.status === "ok" ? `${s.name}: klart (${JSON.stringify(r.result)})` : `${s.name}: ${r.status} – ${r.error}`);
      load();
    } catch (e: any) { setMsg(e.message); }
  };
  return (
    <div className="col" style={{ gap: 14 }}>
      <Panel title="Källregister" icon={Icon.db()} right={<span className="small muted">Data används som underlag i prognoserna bara när licensen tillåter det eller efter ditt dokumenterade beslut</span>}>
        <div className="scroll-x"><table className="t">
          <thead><tr><th>Källa</th><th>Licens / villkor</th><th>Prognosunderlag</th><th>Hämtning</th><th>Senast hämtad</th><th className="num">Hämtningar</th><th className="num">Fel</th></tr></thead>
          <tbody>{list.map((s) => (
            <tr key={s.id}><td><b>{s.name}</b><div className="tiny muted">{s.owner}</div></td><td className="small" style={{ maxWidth: 320 }}>{s.license}</td>
              <td>{trainingBadge(s)}</td>
              <td>{s.enabled ? <StatusBadge kind="ok">Aktiv</StatusBadge> : <StatusBadge kind="neutral">{s.automated_fetch === "manual_only" ? "Endast import" : "Avstängd"}</StatusBadge>}</td>
              <td className="small">{s.overview?.last_fetch ? fmtFull(s.overview.last_fetch) : "–"}</td><td className="num">{s.overview?.fetches ?? 0}</td><td className="num">{s.overview?.failed ?? 0}</td></tr>))}</tbody></table></div>
      </Panel>
      {msg && <div className="callout"><span className="ic">{Icon.info()}</span>{msg}</div>}
      <div className="layout-2">
        {list.map((s) => (
          <Panel key={s.id} title={s.name} right={trainingBadge(s)}>
            <div className="panel-pad col small">
              <div><b>Ägare:</b> {s.owner} · <a href={s.url} target="_blank" rel="noreferrer">{s.url}</a></div>
              <div><b>Licens/villkor:</b> {s.license}{s.terms_url ? <> · <a href={s.terms_url} target="_blank" rel="noreferrer">villkor</a></> : null}</div>
              <div><b>Tillåtna användningar:</b> <span className="chips" style={{ display: "inline-flex" }}>{s.allowed_uses.length ? s.allowed_uses.map((u: string) => <span key={u} className="badge neutral">{({ display: "visning", training: "prognosunderlag", evaluation: "utvärdering", benchmark: "marknadsjämförelse", sanity_check: "rimlighetskontroll" } as any)[u] || u}</span>) : <span className="badge neutral">ingen datainsamling</span>}</span></div>
              <div><b>Täckning:</b> {s.coverage}</div>
              <div><b>Uppdatering:</b> {s.update_frequency} · minsta intervall {s.min_interval_seconds}s{s.daily_quota ? ` · max ${s.daily_quota} anrop/dygn` : ""}</div>
              <div><b>Används i prognoserna:</b> {s.training_status}{s.training_approval_note ? <span className="muted"> – ”{s.training_approval_note}” ({fmtFull(s.training_approval_at_utc)})</span> : null}</div>
              {s.attribution && s.attribution !== "–" && <div><b>Attribution:</b> {s.attribution}</div>}
              {s.notes && <div className="muted">{s.notes}</div>}
              {s.requires_api_key ? <div><b>API-nyckel:</b> {s.api_key_configured ? <StatusBadge kind="ok">Konfigurerad</StatusBadge> : <><StatusBadge kind="warn">Saknas</StatusBadge> <a href="#/installningar">Ange under Inställningar</a></>}</div> : null}
              {(s.overview?.jobs || []).map((j: any) => <div key={j.job + j.scope} className="tiny muted">Jobb {j.job}{j.scope ? ` (${j.scope})` : ""}: {j.last_status || "–"} {j.last_error ? `· ${j.last_error}` : ""} · nästa {j.next_run_utc ? fmtFull(j.next_run_utc) : "–"}</div>)}
              <div className="row wrap" style={{ marginTop: 6 }}>
                {s.automated_fetch !== "manual_only" && (
                  <Switch checked={!!s.enabled} label="Automatisk hämtning" onChange={(v) => {
                    if (v && s.automated_fetch === "disabled") { setDialog({ kind: "enabled", s, enabled: true }); return; }
                    api(`/sources/${s.id}/enabled`, { body: { enabled: v } }).then(load).catch((e) => setMsg(e.message));
                  }} />)}
                {s.enabled && s.automated_fetch !== "manual_only" ? <button className="btn sm" onClick={() => sync(s)}>{Icon.refresh(14)} Hämta nu</button> : null}
                {s.training_policy !== "allowed" && s.data_kinds.length > 0 && !["workbook_legacy", "the_odds_api"].includes(s.id) ? (
                  s.training_allowed
                    ? <button className="btn sm danger" onClick={() => setDialog({ kind: "training", s, approve: false })}>Sluta använda i prognoserna</button>
                    : <button className="btn sm" onClick={() => setDialog({ kind: "training", s, approve: true })}>Använd i prognoserna…</button>) : null}
              </div>
            </div>
          </Panel>))}
      </div>
      {dialog && (
        <Modal title={dialog.kind === "training" ? (dialog.approve ? `Använd ${dialog.s.name} i prognosmodulen` : "Sluta använda i prognoserna") : `Aktivera automatisk hämtning från ${dialog.s.name}`} onClose={() => setDialog(null)}>
          <div className="col">
            {dialog.kind === "training" && dialog.approve && (
              <div className="callout warn"><span className="ic">{Icon.warn()}</span><div>
                {dialog.s.training_policy === "blocked" ? "Källans villkor tillåter inte att datan används i modeller eller beräkningar. Beslutet är ditt: godkänn bara om du har rätt att använda datan så (t.ex. ett skriftligt tillstånd) och ange grunden nedan. Beslutet och motiveringen loggas." :
                  dialog.s.training_policy === "unclear" ? "Rättigheterna är oklara. Dokumentera vilken bedömning eller vilket tillstånd beslutet bygger på." :
                    "Läs källans villkor innan du godkänner. Beslutet loggas med tid."}</div></div>)}
            {dialog.kind === "enabled" && <div className="callout warn"><span className="ic">{Icon.warn()}</span><div>Automatisk hämtning är avstängd som standard för den här källan ({dialog.s.notes}). Aktivera bara om du har granskat villkoren.</div></div>}
            <textarea className="in" rows={3} placeholder="Motivering / referens (loggas)" value={note} onChange={(e) => setNote(e.target.value)} />
            <div className="row"><button className="btn primary" onClick={submit}>Bekräfta</button><button className="btn" onClick={() => setDialog(null)}>Avbryt</button></div>
          </div>
        </Modal>)}
    </div>
  );
}

const OP_KIND: Record<string, "ok" | "warn" | "err" | "info"> = { operativ: "ok", "begränsad": "warn", "spärrad": "info", inaktuell: "err", saknas: "err" };
const OP_LABEL: Record<string, string> = { operativ: "Operativ", "begränsad": "Begränsad", "spärrad": "Spärrad (licens)", inaktuell: "Inaktuell data", saknas: "Ingen data" };
const BACKFILL_SOURCES: { id: string; what: string }[] = [
  { id: "openfootball", what: "Spelscheman och resultat för alla säsonger som finns i källan (CC0). Grund för lagkopplingen – körs först." },
  { id: "wyscout_public", what: "Skott, skott på mål, hörnor, spelare och startelvor för säsongen 2017/18 i de fem stora ligorna (CC BY 4.0, cirka 77 MB)." },
  { id: "statsbomb_open", what: "Händelsedata för utvalda matcher och säsonger. Långsam utan GitHub-token (60 anrop/timme) – återupptas automatiskt." },
  { id: "api_football", what: "Lagstatistik per match (skott, skott på mål, hörnor), startelvor och spelarstatistik för alla sju tävlingar. Kräver API-nyckel; abonnemanget avgör vilka säsonger som ingår." },
];

export function OperationalGrid({ comps, compact = false }: { comps: Competition[]; compact?: boolean }) {
  const [op, setOp] = useState<any>(null);
  useEffect(() => { api("/operational").then(setOp).catch(() => setOp({ competitions: [] })); }, []);
  if (!op) return <Loading />;
  const name = (c: string) => comps.find((x) => x.code === c)?.name || c;
  const keys = ["goals", "corners", "shots", "sot"];
  return (
    <div className="scroll-x"><table className="t">
      <thead><tr><th>Tävling</th>{keys.map((k) => <th key={k}>{op.competitions[0]?.metrics[k]?.label || k}</th>)}</tr></thead>
      <tbody>{op.competitions.map((c: any) => (
        <tr key={c.competition}><td><b>{name(c.competition)}</b></td>
          {keys.map((k) => { const m = c.metrics[k]; return (
            <td key={k} title={[m.reason, ...(m.needs || [])].join("\n")}>
              <StatusBadge kind={OP_KIND[m.status] || "neutral"}>{OP_LABEL[m.status] || m.status}</StatusBadge>
              {!compact && <div className="tiny muted" style={{ marginTop: 3 }}>{m.recent_allowed} i fönstret{m.last_allowed ? ` · senast ${m.last_allowed.slice(0, 10)}` : ""}</div>}
            </td>); })}
        </tr>))}</tbody></table>
      {!compact && <div className="small muted panel-pad">Operativ = minst {op.operative_min} spelade matcher med värde från en källa som får användas i prognoserna de senaste {op.max_age_days} dagarna. Äldre räknemått används inte – prognosen visas då som saknad i stället för att bygga på inaktuell data. Håll muspekaren över en status för orsak och vad som behövs.</div>}
    </div>
  );
}

function History({ comps, onChanged }: { comps: Competition[]; onChanged: () => void }) {
  const [srcs, setSrcs] = useState<any[] | null>(null);
  const [state, setState] = useState<any>(null);
  const [sel, setSel] = useState<string[]>(["openfootball", "wyscout_public", "statsbomb_open"]);
  const [compSel, setCompSel] = useState<string[]>([]);
  const [job, setJob] = useState<any>(null);
  const [result, setResult] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState("");
  const [maxAge, setMaxAge] = useState<string>("");
  const [rev, setRev] = useState(0);
  useEffect(() => {
    api("/sources").then((r) => { setSrcs(r); const af = r.find((x: any) => x.id === "api_football"); setQuota(af?.quota_override ? String(af.quota_override) : ""); });
    api("/backfill/state").then(setState).catch(() => setState(null));
    api("/settings").then((s) => setMaxAge(String(s.counts_max_age_days ?? 450)));
  }, [rev]);
  const tabComps = comps.filter((c) => c.show_in_tabs).sort((a, b) => (a.tab_order || 99) - (b.tab_order || 99));
  const start = async () => {
    setError(null); setResult(null);
    try {
      const { job_id } = await api("/backfill", { body: { sources: sel, competitions: compSel.length ? [...compSel, ...(compSel.includes("UCL") ? ["UCLQ"] : [])] : null } });
      const r = await pollJob<any[]>(job_id, setJob);
      setResult(r); setJob(null); setRev((x) => x + 1); onChanged();
    } catch (e: any) { setError(e.message); setJob(null); }
  };
  const src = (id: string) => srcs?.find((s) => s.id === id);
  const toggle = (arr: string[], v: string) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  return (
    <div className="col" style={{ gap: 14 }}>
      <Panel title="Driftstatus per serie och mått" icon={Icon.check()} key={`op-${rev}`}>
        <OperationalGrid comps={comps} />
        <div className="row wrap panel-pad small">
          <span>Maxålder för skott, skott på mål och hörnor:</span>
          <input className="in" style={{ width: 90 }} value={maxAge} onChange={(e) => setMaxAge(e.target.value)} /> dagar
          <button className="btn sm" onClick={async () => { try { await api("/settings", { method: "PUT", body: { counts_max_age_days: Number(maxAge) } }); setRev((x) => x + 1); } catch (e: any) { setError(e.message); } }}>Spara</button>
        </div>
      </Panel>
      <Panel title="Hämta historik" icon={Icon.refresh()} right={<span className="small muted">Varje källa följer sina villkor och anropsgränser</span>}>
        <div className="panel-pad col" style={{ gap: 10 }}>
          {!srcs ? <Loading /> : BACKFILL_SOURCES.map(({ id, what }) => { const s = src(id); if (!s) return null; const blocked = !s.enabled || (s.requires_api_key && !s.api_key_configured); return (
            <label key={id} className="row" style={{ alignItems: "flex-start", gap: 10, opacity: blocked ? 0.65 : 1 }}>
              <input type="checkbox" disabled={blocked} checked={sel.includes(id) && !blocked} onChange={() => setSel(toggle(sel, id))} style={{ marginTop: 4 }} />
              <div><b>{s.name}</b> {trainingBadge(s)}
                <div className="small">{what}</div>
                <div className="tiny muted">Licens: {s.license}{blocked ? (s.enabled ? " · API-nyckel saknas (Inställningar → API-nycklar)" : " · källan är avstängd") : ""}</div></div>
            </label>); })}
          <div className="row wrap"><span className="small">Tävlingar:</span>
            {tabComps.map((c) => <button key={c.code} className={`chip ${compSel.includes(c.code) ? "on" : ""}`} onClick={() => setCompSel(toggle(compSel, c.code))}>{c.name}</button>)}
            <span className="tiny muted">{compSel.length ? "" : "(alla)"}</span></div>
          <div className="row"><button className="btn primary" disabled={!!job || sel.length === 0} onClick={start}>{Icon.refresh(16)} Starta hämtningen</button>
            <span className="small muted">Körs i bakgrunden och kan avbrytas av anropsgränser – en ny körning fortsätter där den slutade. Redan hämtade filer och matcher hämtas inte igen.</span></div>
          {job && <div className="col" style={{ gap: 4 }}><Meter value={job.total ? job.done / job.total : null} /><div className="small">{job.message || "Startar…"}</div></div>}
          {error && <div className="callout err small">{error}</div>}
          {result && <table className="t"><thead><tr><th>Källa</th><th>Status</th><th>Resultat</th></tr></thead><tbody>{result.map((r: any) => (
            <tr key={r.source}><td>{src(r.source)?.name || r.source}</td><td><StatusBadge kind={r.status === "ok" ? "ok" : r.status === "blocked" ? "warn" : r.status === "skipped" ? "neutral" : "err"}>{r.status}</StatusBadge>{r.error && <div className="tiny muted">{r.error}</div>}</td>
              <td className="tiny mono" style={{ whiteSpace: "normal" }}>{Object.entries(r.result || {}).filter(([k]) => k !== "event_kinds").map(([k, v]) => `${k}: ${v}`).join(" · ")}</td></tr>))}</tbody></table>}
        </div>
      </Panel>
      <Panel title="Hämtad historik per källa" icon={Icon.db()}>
        {!state ? <Loading /> : (<div className="panel-pad col" style={{ gap: 10 }}>
          <table className="t"><thead><tr><th>Källa</th><th className="num">Matcher</th><th className="num">Med lagstatistik</th><th className="num">Spelarrader</th></tr></thead>
            <tbody>{state.per_source.map((r: any) => <tr key={r.source_id}><td>{src(r.source_id)?.name || r.source_id}</td><td className="num">{r.matches}</td><td className="num">{r.with_stats}</td><td className="num">{r.player_rows}</td></tr>)}</tbody></table>
          {state.pending?.sources?.length > 0 && <div className="callout small"><span className="ic">{Icon.clock()}</span><div>Väntar på anropsgräns eller dygnskvot för {state.pending.sources.map((x: string) => src(x)?.name || x).join(", ")} – hämtningen fortsätter automatiskt i bakgrunden från {fmtFull(state.pending.next_utc)}. En GitHub-token (Inställningar → API-nycklar) gör OpenFootball- och StatsBomb-hämtningen betydligt snabbare.</div></div>}
          {state.files.length > 0 && <div className="small muted">Spårade källfiler: {state.files.map((f: any) => `${src(f.source_id)?.name || f.source_id}: ${f.n} (senast ${fmtFull(f.last)})`).join(" · ")}</div>}
          <div><b>API-Football – säsonger</b> <span className="small muted">{state.ids_supported === false ? "Abonnemanget tillåter inte ids-batchning – ett anrop per match används." : ""}</span></div>
          {state.scopes.filter((x: any) => x.source_id === "api_football").length === 0 ? <div className="small muted">Ingen historik hämtad från API-Football ännu.</div> : (
            <table className="t"><thead><tr><th>Tävling:säsong</th><th>Status</th><th>Meddelande från källan</th></tr></thead><tbody>
              {state.scopes.filter((x: any) => x.source_id === "api_football").map((x: any) => (
                <tr key={x.scope}><td>{x.scope}</td><td><StatusBadge kind={x.last_status === "ok" ? "ok" : x.last_status === "plan_restricted" ? "warn" : "err"}>{x.last_status === "plan_restricted" ? "Ingår inte i abonnemanget" : x.last_status}</StatusBadge></td><td className="small">{x.last_error || ""}</td></tr>))}</tbody></table>)}
          <div className="row wrap small"><span>Dygnskvot för API-Football (ditt abonnemang):</span>
            <input className="in" style={{ width: 110 }} placeholder="100" value={quota} onChange={(e) => setQuota(e.target.value)} />
            <button className="btn sm" onClick={async () => { try { await api("/sources/api_football/quota", { method: "PUT", body: { value: quota || null } }); setRev((x) => x + 1); } catch (e: any) { setError(e.message); } }}>Spara</button>
            <button className="btn sm" onClick={async () => { await api("/sources/api_football/backfill/reset", { body: {} }); setRev((x) => x + 1); }} title="Använd efter byte av abonnemang">Pröva säsongerna igen</button></div>
        </div>)}
      </Panel>
    </div>
  );
}

function Coverage({ comps, route }: { comps: Competition[]; route: Route }) {
  const [comp, setComp] = useState(route.params.get("c") || "UCL");
  const [cov, setCov] = useState<any>(null);
  const [season, setSeason] = useState<string>("");
  useEffect(() => { setCov(null); api(`/coverage?competition=${comp}${season ? `&season=${encodeURIComponent(season)}` : ""}`).then(setCov).catch(() => setCov({ seasons: [], teams: [] })); }, [comp, season]);
  const metrics: [string, string][] = [["goals", "Resultat"], ["shots", "Skott"], ["sot", "Skott på mål"], ["corners", "Hörnor"], ["xg", "xG"]];
  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="row wrap">
        <select className="in" value={comp} onChange={(e) => { setComp(e.target.value); setSeason(""); }}>{comps.map((c) => <option key={c.code} value={c.code}>{c.name} ({c.matches})</option>)}</select>
        <span className="small muted">Täckning = andel spelade matcher där båda lagens värde finns. Saknade värden är tomma, aldrig 0.</span>
      </div>
      {!cov ? <Loading /> : (
        <>
          <Panel title="Täckning per säsong och mått" icon={Icon.db()}>
            {cov.seasons.length === 0 ? <div className="empty">Ingen data för tävlingen. Aktivera en källa eller importera en fil.</div> : (
              <div className="scroll-x"><table className="t">
                <thead><tr><th>Säsong</th><th className="num">Matcher</th><th className="num">Spelade</th>{metrics.map(([k, l]) => <th key={k}>{l} (prognoser / alla)</th>)}</tr></thead>
                <tbody>{cov.seasons.slice().reverse().map((s: any) => (
                  <tr key={s.season} className="click" onClick={() => setSeason(s.season)}><td><b>{s.season}</b></td><td className="num">{s.matches}</td><td className="num">{s.finished}</td>
                    {metrics.map(([k]) => { const m = s.metrics[k]; return (
                      <td key={k}><div className="row small"><div style={{ width: 70 }}><Meter value={m.pct_training} /></div><span>{pct(m.pct_training)}</span><span className="muted">/ {pct(m.pct_any)}</span>{m.missing > 0 && <span className="tiny muted">({m.missing} saknas)</span>}</div></td>); })}
                  </tr>))}</tbody></table></div>)}
            <div className="small muted panel-pad">Prognoser = källor som får användas som underlag i prognoserna enligt källregistret (just nu: {(cov.training_sources || []).join(", ") || "inga"}). Klicka en säsong för lagvis täckning.</div>
          </Panel>
          <Panel title={`Täckning per lag${season ? ` – ${season}` : " – alla säsonger"}`} icon={Icon.users()} right={season ? <button className="btn sm" onClick={() => setSeason("")}>Visa alla</button> : null}>
            <div className="scroll-x" style={{ maxHeight: 520, overflow: "auto" }}><table className="t">
              <thead><tr><th>Lag</th><th className="num">Matcher</th><th className="num">Skott</th><th className="num">Skott på mål</th><th className="num">Hörnor</th><th className="num">xG</th></tr></thead>
              <tbody>{(cov.teams || []).map((t: any) => (
                <tr key={t.id} className="click" onClick={() => navigate(`lag/${t.id}`)}><td>{t.name}</td><td className="num">{t.matches}</td>
                  {["shots", "sot", "corners", "xg"].map((k) => <td key={k} className="num" style={{ color: t[k] < t.matches ? "var(--warn)" : undefined }}>{t[k]}{t[k] < t.matches ? ` (−${t.matches - t[k]})` : ""}</td>)}</tr>))}</tbody></table></div>
          </Panel>
        </>)}
    </div>
  );
}

function Import({ onChanged }: { onChanged: () => void }) {
  const [info, setInfo] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sheet, setSheet] = useState<string>("");
  const [target, setTarget] = useState("matches");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [opts, setOpts] = useState<any>({ competition: "UCL", source_id: "user_file", timezone: "Europe/Stockholm" });
  const [preview, setPreview] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  useEffect(() => { api("/imports").then(setHistory).catch(() => undefined); }, [result]);

  const pick = async (f: File) => {
    setErr(null); setInfo(null); setPreview(null); setResult(null); setBusy("Läser filen…");
    try {
      const r = await api("/imports/inspect", { raw: await f.arrayBuffer(), method: "POST", headers: { "X-Filename": f.name, "Content-Type": "application/octet-stream" } });
      setInfo({ ...r, file_name: f.name });
      setSheet(r.sheets[0]?.sheet || "");
    } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };
  const sh = info?.sheets.find((s: any) => s.sheet === sheet);
  const fields = info ? [...info.targets[target].required, ...info.targets[target].optional] : [];
  const runPreview = async () => {
    setErr(null); setBusy("Förhandsgranskar…");
    try { setPreview(await api("/imports/preview", { body: { stored_copy: info.stored_copy, sheet, header_row: sh?.header_row, target, mapping, options: opts } })); }
    catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };
  const runImport = async (profile?: string) => {
    setErr(null); setBusy("Importerar…");
    try {
      const { job_id } = await api("/imports/run", { body: { stored_copy: info.stored_copy, file_name: info.file_name, profile, sheet, header_row: sh?.header_row, target, mapping, options: opts } });
      const r = await pollJob(job_id, (j) => setBusy(`${j.message} (${j.done}/${j.total})`));
      setResult(r); onChanged();
    } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  };

  return (
    <div className="col" style={{ gap: 14 }}>
      <Panel title="Importera Excel eller CSV" icon={Icon.upload()}>
        <div className="panel-pad col">
          <div className="small muted">Filen läses från en kopia i datamappen – originalet ändras aldrig. Du ser blad, kolumner, radantal, saknade värden och dubbletter innan något importeras. Importen kan köras om utan dubbletter.</div>
          <label className="btn" style={{ alignSelf: "flex-start" }}>{Icon.upload(16)} Välj fil (.xlsx, .csv)
            <input type="file" accept=".xlsx,.xlsm,.csv,.txt" style={{ display: "none" }} onChange={(e) => { const f = e.target.files?.[0]; if (f) pick(f); }} /></label>
          {busy && <div className="callout"><span className="ic">{Icon.clock()}</span>{busy}</div>}
          {err && <div className="callout err"><span className="ic">{Icon.warn()}</span>{err}</div>}
        </div>
      </Panel>
      {info && (
        <Panel title={`${info.file_name} · ${(info.bytes / 1024).toFixed(0)} kB`} icon={Icon.db()} right={<span className="mono tiny">SHA-256 {info.sha256.slice(0, 16)}…</span>}>
          <div className="panel-pad col">
            {info.previously_imported && <div className="callout warn"><span className="ic">{Icon.info()}</span>Samma fil importerades {fmtFull(info.previously_imported.finished_at_utc)}. En ny import skapar inga dubbletter.</div>}
            {info.profile && (
              <>
                <div className="callout ok"><span className="ic">{Icon.check()}</span><div><b>Känd profil: {info.profile.label}.</b> Bladen mappas automatiskt (CL-historik, inhemsk historik, prognoslogg, elvor, MD2/MD3). Kontrollvärdena nedan verifieras mot filen – saknade datamängder redovisas öppet.</div></div>
                <div className="scroll-x"><table className="t"><thead><tr><th>Kontroll</th><th className="num">Förväntat</th><th className="num">I filen</th><th>Status</th><th>Kommentar</th></tr></thead>
                  <tbody>{info.profile.inventory.map((r: any) => (
                    <tr key={r.key}><td>{r.label}</td><td className="num">{r.expected.toLocaleString("sv-SE")}</td><td className="num">{r.found == null ? "–" : r.found.toLocaleString("sv-SE")}</td>
                      <td>{r.status === "stämmer" ? <StatusBadge kind="ok">Stämmer</StatusBadge> : r.status === "avviker" ? <StatusBadge kind="warn">Avviker</StatusBadge> : <StatusBadge kind="err">Saknas i filen</StatusBadge>}</td><td className="small muted">{r.note}</td></tr>))}</tbody></table></div>
                <button className="btn primary" style={{ alignSelf: "flex-start" }} disabled={!!busy} onClick={() => runImport(info.profile.id)}>Importera arbetsboken</button>
              </>)}
            <div className="row wrap"><b>Blad:</b>
              <select className="in" value={sheet} onChange={(e) => { setSheet(e.target.value); setPreview(null); }}>{info.sheets.map((s: any) => <option key={s.sheet} value={s.sheet}>{s.sheet} ({s.rows} rader)</option>)}</select>
              {sh && <span className="small muted">Rubrikrad {sh.header_row} · {sh.rows} rader · {sh.duplicate_rows} dubblettrader</span>}</div>
            {sh && (
              <div className="scroll-x" style={{ maxHeight: 260, overflow: "auto" }}><table className="t"><thead><tr><th>Kolumn</th><th className="num">Saknade</th><th>Exempel</th></tr></thead>
                <tbody>{sh.columns.map((c: any, i: number) => (<tr key={c.name}><td>{c.name}</td><td className="num" style={{ color: c.missing ? "var(--warn)" : undefined }}>{c.missing} ({num(c.missing_pct, 0)} %)</td><td className="small muted">{sh.sample.map((r: any[]) => r[i]).filter((x: any) => x != null).slice(0, 3).join(" · ")}</td></tr>))}</tbody></table></div>)}
          </div>
        </Panel>)}
      {info && sh && (
        <Panel title="Mappning" icon={Icon.scale()}>
          <div className="panel-pad col">
            <div className="row wrap">
              <label className="row small">Måltabell <select className="in" value={target} onChange={(e) => { setTarget(e.target.value); setMapping({}); setPreview(null); }}>{Object.entries<any>(info.targets).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}</select></label>
              <label className="row small">Tävling <select className="in" value={opts.competition} onChange={(e) => setOpts({ ...opts, competition: e.target.value })}>{["UCL", "SWE1", "ENG1", "ESP1", "GER1", "ITA1", "FRA1", "NED1", "POR1", "BEL1", "TUR1", "NOR1"].map((c) => <option key={c}>{c}</option>)}</select></label>
              <label className="row small">Ursprungskälla <select className="in" value={opts.source_id} onChange={(e) => setOpts({ ...opts, source_id: e.target.value })}>
                {["user_file", "openfootball", "uefa", "football_data_couk", "statsbomb_open", "api_football", "football_data_org", "manual"].map((s) => <option key={s}>{s}</option>)}</select></label>
              <label className="row small">Tidszon för lokala tider <input className="in" value={opts.timezone} onChange={(e) => setOpts({ ...opts, timezone: e.target.value })} style={{ width: 170 }} /></label>
            </div>
            <div className="small muted">Ursprungskällan avgör licens och träningsspärr. Okänt ursprung ("user_file") spärras från prognoserna tills du beslutat.</div>
            <div className="layout-3">{fields.map((f: string) => (
              <label key={f} className="col" style={{ gap: 3 }}><span className="small">{info.targets[target].labels[f]}{info.targets[target].required.includes(f) ? " *" : ""}</span>
                <select className="in" value={mapping[f] || ""} onChange={(e) => setMapping({ ...mapping, [f]: e.target.value })}>
                  <option value="">– ej mappad –</option>{sh.columns.map((c: any) => <option key={c.name} value={c.name}>{c.name}</option>)}</select></label>))}</div>
            <div className="row"><button className="btn" disabled={!!busy} onClick={runPreview}>Förhandsgranska</button>
              {preview && <button className="btn primary" disabled={!!busy || preview.stats.ok === 0} onClick={() => runImport()}>Importera {preview.stats.ok} rader</button>}</div>
            {preview && (
              <>
                <div className="row wrap small"><StatusBadge kind="ok">{preview.stats.ok} giltiga</StatusBadge><StatusBadge kind={preview.stats.errors ? "err" : "neutral"}>{preview.stats.errors} fel</StatusBadge>
                  <StatusBadge kind="info">{preview.would_create_matches} nya matcher</StatusBadge><StatusBadge kind="neutral">{preview.would_update_matches} befintliga</StatusBadge>
                  <StatusBadge kind={preview.stats.duplicate_keys ? "warn" : "neutral"}>{preview.stats.duplicate_keys} dubbletter i filen</StatusBadge></div>
                {preview.stats.new_teams.length > 0 && <div className="callout warn small"><span className="ic">{Icon.warn()}</span><div><b>Nya lagnamn utan exakt alias</b> (skapas som nya lag och flaggas för granskning om liknande namn finns): {preview.stats.new_teams.join(", ")}</div></div>}
                <div className="scroll-x" style={{ maxHeight: 300, overflow: "auto" }}><table className="t"><thead><tr><th>Rad</th><th>Avspark (UTC)</th><th>Hemma</th><th>Borta</th><th>Status</th></tr></thead>
                  <tbody>{preview.sample.map((r: any) => (<tr key={r.row}><td>{r.row}</td><td className="small">{r.kickoff_utc || "–"}</td><td>{r.home}{r.home_team_id ? "" : " ✱"}</td><td>{r.away}{r.away_team_id ? "" : " ✱"}</td>
                    <td>{r.errors.length ? <span className="missing small">{r.errors.join("; ")}</span> : r.match_exists ? <StatusBadge kind="neutral">uppdateras</StatusBadge> : <StatusBadge kind="info">ny</StatusBadge>}</td></tr>))}</tbody></table></div>
              </>)}
          </div>
        </Panel>)}
      {result && (
        <Panel title="Importresultat" icon={Icon.check()}>
          <pre className="mono panel-pad" style={{ whiteSpace: "pre-wrap", margin: 0 }}>{JSON.stringify({ counts: result.counts, warnings: result.warnings, teams_needing_review: result.teams_needing_review }, null, 2)}</pre>
          {result.teams_needing_review > 0 && <div className="panel-pad"><a href="#/lag?granska=1">Granska {result.teams_needing_review} lag med möjliga dubbletter →</a></div>}
        </Panel>)}
      <Panel title="Tidigare importer" icon={Icon.clock()}>
        {history.length === 0 ? <div className="empty">Inga importer ännu.</div> : (
          <table className="t"><thead><tr><th>Fil</th><th>Profil</th><th>Start</th><th>Status</th></tr></thead>
            <tbody>{history.map((h) => <tr key={h.id}><td>{h.file_name}<div className="mono tiny muted">{h.file_sha256.slice(0, 16)}…</div></td><td>{h.profile}</td><td>{fmtFull(h.started_at_utc)}</td><td>{h.status === "done" ? <StatusBadge kind="ok">klar</StatusBadge> : h.status === "error" ? <StatusBadge kind="err">fel</StatusBadge> : h.status}</td></tr>)}</tbody></table>)}
      </Panel>
    </div>
  );
}

function FetchLog() {
  const [rows, setRows] = useState<any[] | null>(null);
  useEffect(() => { api("/fetches?limit=200").then(setRows).catch(() => setRows([])); }, []);
  if (!rows) return <Loading />;
  return (
    <Panel title="Hämtlogg" icon={Icon.refresh()} right={<span className="small muted">Källa, URL, tid, HTTP-status, SHA-256, parserstatus och radantal per hämtning</span>}>
      {rows.length === 0 ? <div className="empty">Inga hämtningar ännu.</div> : (
        <div className="scroll-x"><table className="t">
          <thead><tr><th>Tid</th><th>Källa</th><th>URL</th><th className="num">HTTP</th><th>Parser</th><th className="num">Nya</th><th className="num">Uppd.</th><th className="num">Oförändr.</th><th>SHA-256</th><th>Fel</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.id}><td className="nowrap small">{fmtFull(r.started_at_utc)}</td><td>{r.source_id}</td><td className="small mono" style={{ maxWidth: 360, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={r.url}>{r.url}</td>
              <td className="num">{r.http_status ?? "–"}</td><td>{r.parser_status === "ok" ? <StatusBadge kind="ok">ok</StatusBadge> : r.parser_status === "error" ? <StatusBadge kind="err">fel</StatusBadge> : <StatusBadge kind="neutral">{r.parser_status}</StatusBadge>}</td>
              <td className="num">{r.rows_imported}</td><td className="num">{r.rows_updated}</td><td className="num">{r.rows_unchanged}</td><td className="mono tiny">{r.sha256 ? `${r.sha256.slice(0, 12)}…` : "–"}</td><td className="small">{r.error || ""}</td></tr>))}</tbody></table></div>)}
    </Panel>
  );
}

function ChangeLog() {
  const [rows, setRows] = useState<any[] | null>(null);
  useEffect(() => { api("/changelog?limit=300").then(setRows).catch(() => setRows([])); }, []);
  if (!rows) return <Loading />;
  return (
    <Panel title="Ändringslogg" icon={Icon.clock()} right={<span className="small muted">Varje ändring loggas med källa och tid</span>}>
      <div className="scroll-x"><table className="t"><thead><tr><th>Tid</th><th>Objekt</th><th>Fält</th><th>Före</th><th>Efter</th><th>Källa</th><th>Aktör</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.id}><td className="small nowrap">{fmtFull(r.at_utc)}</td><td className="small">{r.entity} {r.entity_id}</td><td className="small">{r.field || "–"}</td><td className="small muted" style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis" }}>{r.old_value ?? "–"}</td><td className="small" style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis" }}>{r.new_value ?? "–"}</td><td className="small">{r.source_id || "–"}</td><td className="small">{r.actor}</td></tr>)}</tbody></table></div>
    </Panel>
  );
}
