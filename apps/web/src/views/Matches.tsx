import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { CompetitionTabs, navigate, type Competition, type Route } from "../App";
import { fmtDate, fmtDay, fmtFull, fmtTime, localDay, num, pct } from "../format";
import { Crest, ErrorBox, Flag, Icon, Loading, ModelBadge, P3, Panel, ProbCards, StatusBadge } from "../ui";

const STATUS_FILTERS = [
  ["kommande", "Kommande"], ["avslutade", "Avslutade"], ["alla", "Alla"],
] as const;

export function statusChip(m: any, nowIso?: string) {
  if (m.status === "finished") {
    const s = m.home_goals != null ? `${m.home_goals}–${m.away_goals}` : "spelad";
    return <StatusBadge kind="neutral">Slut {s}</StatusBadge>;
  }
  if (m.status === "scheduled" && nowIso && new Date(m.kickoff_utc).getTime() < new Date(nowIso).getTime() - 3 * 3600e3) {
    return <StatusBadge kind="warn">Resultat saknas</StatusBadge>;
  }
  if (m.status === "postponed") return <StatusBadge kind="warn">Uppskjuten</StatusBadge>;
  if (m.status === "cancelled") return <StatusBadge kind="err">Inställd</StatusBadge>;
  if (m.job_status === "done") return <StatusBadge kind="ok">T−30 klar</StatusBadge>;
  if (m.job_status === "late_done") return <StatusBadge kind="err">Sen rapport</StatusBadge>;
  if (m.job_status === "failed") return <StatusBadge kind="err">Rapport misslyckades</StatusBadge>;
  if (m.job_status === "pending") return <StatusBadge kind="info">T−30 {fmtTime(m.job_due)}</StatusBadge>;
  return <StatusBadge kind="neutral">Ej schemalagd</StatusBadge>;
}

function probsOf(m: any, fam: "V2" | "V3") {
  const s = m.snapshots?.[fam];
  if (s && s.p_home != null) return { p: s, frozen: true };
  const pv = m.preview?.[fam]?.probs;
  if (pv) return { p: pv, frozen: false };
  return { p: null, frozen: false };
}

export function MatchesView({ comp, route, comps }: { comp: string; route: Route; comps: Competition[] }) {
  const [rows, setRows] = useState<any[] | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const [status, setStatus] = useState<string>(route.params.get("status") || "kommande");
  const [team, setTeam] = useState<string>("");
  const [day, setDay] = useState<string>("alla");
  const [model, setModel] = useState<"V2" | "V3">("V2");
  const [sub, setSub] = useState<string>(route.params.get("vy") || "matcher");
  const [sel, setSel] = useState<number | null>(null);
  const [nowIso, setNowIso] = useState<string | undefined>();
  const compInfo = comps.find((c) => c.code === comp);

  useEffect(() => {
    let alive = true;
    setRows(null);
    setErr(null);
    (async () => {
      try {
        const sched = await api("/scheduler");
        const now = sched.now_utc as string;
        setNowIso(now);
        const params = new URLSearchParams({ competition: comp, limit: "400" });
        if (status === "kommande") {
          params.set("from", new Date(new Date(now).getTime() - 3 * 3600e3).toISOString());
          params.set("status", "scheduled,live,unknown,postponed");
          params.set("preview", "1");
        } else if (status === "avslutade") {
          params.set("status", "finished");
          params.set("order", "desc");
          params.set("limit", "120");
        } else {
          params.set("from", new Date(new Date(now).getTime() - 30 * 86400e3).toISOString());
          params.set("preview", "1");
        }
        if (team) params.set("team", team);
        const data = await api(`/matches?${params}`);
        if (alive) {
          setRows(data);
          setSel((s) => (s && data.some((r: any) => r.id === s) ? s : data[0]?.id ?? null));
        }
      } catch (e) {
        if (alive) setErr(e);
      }
    })();
    return () => { alive = false; };
  }, [comp, status, team]);

  const days = useMemo(() => {
    const set = new Map<string, string>();
    (rows || []).forEach((r) => set.set(localDay(r.kickoff_utc), r.kickoff_utc));
    return Array.from(set.entries()).slice(0, 7);
  }, [rows]);
  const visible = (rows || []).filter((r) => day === "alla" || localDay(r.kickoff_utc) === day);
  const selected = visible.find((r) => r.id === sel) || visible[0];

  return (
    <div>
      <CompetitionTabs comps={comps} active={comp} onPick={(c) => navigate(`matcher?c=${c}`)} />
      <div className="layout-match">
        <div className="col" style={{ gap: 14 }}>
          <div className="league-banner">
            <div className="league-emblem"><Flag code={comp} /></div>
            <div>
              <h1>{compInfo?.name || comp}</h1>
              <div style={{ color: "#c4d6f2" }}>
                {compInfo ? `${compInfo.matches} matcher i databasen · ${compInfo.upcoming} kommande` : ""}
              </div>
            </div>
            <div className="seg" role="tablist">
              {[["matcher", "Matcher"], ["tabell", "Tabell"], ["tackning", "Datatäckning"]].map(([k, l]) => (
                <button key={k} className={sub === k ? "on" : ""} onClick={() => setSub(k)}>{l}</button>
              ))}
            </div>
          </div>
          {sub === "tabell" && <Standings comp={comp} />}
          {sub === "tackning" && <CoverageMini comp={comp} />}
          {sub === "matcher" && (
            <Panel title="Matcher" icon={Icon.cal()} right={
              <div className="seg">
                <button className={model === "V2" ? "on v2" : ""} onClick={() => setModel("V2")}>V2</button>
                <button className={model === "V3" ? "on v3" : ""} onClick={() => setModel("V3")}>V3 exp.</button>
              </div>}>
              <div className="filters">
                <div className="chips">
                  {STATUS_FILTERS.map(([k, l]) => (
                    <button key={k} className={`chip ${status === k ? "on" : ""}`} onClick={() => { setStatus(k); setDay("alla"); }}>{l}</button>
                  ))}
                </div>
                <div className="chips">
                  <button className={`chip ${day === "alla" ? "on" : ""}`} onClick={() => setDay("alla")}>Alla datum</button>
                  {days.map(([dk, iso]) => (
                    <button key={dk} className={`chip ${day === dk ? "on" : ""}`} onClick={() => setDay(dk)}>{fmtDay(iso)} {fmtDate(iso)}</button>
                  ))}
                </div>
                <input className="in" placeholder="Filtrera lag…" value={team} onChange={(e) => setTeam(e.target.value)} style={{ marginLeft: "auto", width: 180 }} />
              </div>
              {err ? <ErrorBox error={err} /> : rows === null ? <Loading /> : visible.length === 0 ? (
                <div className="empty">
                  Inga matcher för valt filter.
                  {compInfo && compInfo.matches === 0 && (
                    <div className="small" style={{ marginTop: 8 }}>
                      Ingen data för {compInfo.name} ännu. Aktivera en källa under <a href="#/data?tab=kallor">Data &amp; källor</a> eller importera en fil.
                    </div>
                  )}
                </div>
              ) : (
                <div className="match-rows">
                  <div className="match-row" style={{ cursor: "default", color: "var(--muted)", fontSize: 12, fontWeight: 700 }}>
                    <div>Tid</div><div>Hemmalag</div><div /><div>Bortalag</div>
                    <div className="p3" style={{ border: 0 }}><div style={{ border: 0 }}>1</div><div style={{ border: 0 }}>X</div><div style={{ border: 0 }}>2</div></div>
                    <div className="status-cell">Status</div><div />
                  </div>
                  {visible.map((m) => {
                    const pr = probsOf(m, model);
                    return (
                      <div key={m.id} className={`match-row ${selected?.id === m.id ? "sel" : ""}`}
                        onClick={() => setSel(m.id)} onDoubleClick={() => navigate(`match/${m.id}`)}>
                        <div className="when"><span className="time">{m.kickoff_time_known ? fmtTime(m.kickoff_utc) : "–:–"}</span><span className="date">{fmtDay(m.kickoff_utc)} {fmtDate(m.kickoff_utc)}</span></div>
                        <div className="team"><Crest name={m.home} c1={m.home_c1} c2={m.home_c2} crest={m.home_crest} /><span>{m.home}</span></div>
                        <div className="vsx">{m.status === "finished" && m.home_goals != null ? <span className="score">{m.home_goals}–{m.away_goals}</span> : "vs"}</div>
                        <div className="team away"><Crest name={m.away} c1={m.away_c1} c2={m.away_c2} crest={m.away_crest} /><span>{m.away}</span></div>
                        <div title={pr.p ? (pr.frozen ? "Fryst prognos" : "Förhandsvisning – ej fryst") : "Ingen prognos"} style={{ opacity: pr.frozen || !pr.p ? 1 : 0.8 }}><P3 p={pr.p} /></div>
                        <div className="status-cell">{statusChip(m, nowIso)}</div>
                        <button className="chev" style={{ border: 0, background: "none", cursor: "pointer" }} onClick={(e) => { e.stopPropagation(); navigate(`match/${m.id}`); }} aria-label="Gå till match">{Icon.chev()}</button>
                      </div>
                    );
                  })}
                </div>
              )}
              <div className="small muted" style={{ padding: "10px 14px" }}>
                Procent med lägre opacitet är förhandsvisningar (beräknade nu, ej frysta). Frysta T−30-prognoser ändras aldrig i efterhand.
              </div>
            </Panel>
          )}
        </div>
        <div className="sticky-col">
          {selected ? <SidePreview m={selected} model={model} nowIso={nowIso} /> : <Panel title="Matchanalys"><div className="empty">Välj en match</div></Panel>}
        </div>
      </div>
    </div>
  );
}

function SidePreview({ m, model, nowIso }: { m: any; model: "V2" | "V3"; nowIso?: string }) {
  const pr = probsOf(m, model);
  return (
    <>
      <Panel title="Matchanalys – 1X2" icon={Icon.bars()} right={<ModelBadge family={model} status={m.preview?.[model]?.status} />}>
        <div className="hero" style={{ borderRadius: "0 0 14px 14px" }}>
          <div className="hero-meta" style={{ textAlign: "center" }}>{m.competition_name} · {fmtDay(m.kickoff_utc)} {fmtDate(m.kickoff_utc)} · {fmtTime(m.kickoff_utc)}</div>
          <div className="hero-teams">
            <div className="hero-team"><Crest name={m.home} c1={m.home_c1} c2={m.home_c2} crest={m.home_crest} size={44} /><div style={{ fontWeight: 800, fontSize: 17 }}>{m.home}</div></div>
            <div className="vs" style={{ width: 40, height: 40, fontSize: 13 }}>VS</div>
            <div className="hero-team"><Crest name={m.away} c1={m.away_c1} c2={m.away_c2} crest={m.away_crest} size={44} /><div style={{ fontWeight: 800, fontSize: 17 }}>{m.away}</div></div>
          </div>
          <ProbCards p={pr.p} compact />
          <div className="freeze-line">{pr.p ? (pr.frozen ? `Fryst prognos ${fmtFull(m.snapshots?.[model]?.created_at_utc)}` : "Förhandsvisning – ej fryst, beräknad med data fram till nu") : "Ingen prognos tillgänglig"}</div>
          <div className="row" style={{ justifyContent: "center", marginTop: 10 }}>
            <button className="go-btn" onClick={() => navigate(`match/${m.id}`)}>Gå till match</button>
          </div>
        </div>
      </Panel>
      <Panel title="Rapportstatus" icon={Icon.pdf()}>
        <div className="panel-pad col">
          <div className="row">{statusChip(m, nowIso)}<span className="small muted">{m.reports ? `${m.reports} rapport(er) arkiverade` : "Ingen rapport ännu"}</span></div>
          <div className="small muted">PDF skapas automatiskt exakt 30 minuter före officiell avspark ({m.job_due ? fmtFull(m.job_due) : "ej schemalagd"}).</div>
          <div className="row small">Startelvor: {m.lineup_status ? m.lineup_status.split(",").map((s: string) => s === "confirmed" ? "bekräftad" : "förväntad").join(", ") : <span className="missing">ej publicerade</span>}</div>
        </div>
      </Panel>
    </>
  );
}

function Standings({ comp }: { comp: string }) {
  const [rows, setRows] = useState<any[] | null>(null);
  useEffect(() => { api(`/standings?competition=${comp}`).then(setRows).catch(() => setRows([])); }, [comp]);
  if (rows === null) return <Loading />;
  return (
    <Panel title="Tabell (beräknad ur resultat)" icon={Icon.trophy()}>
      {rows.length === 0 ? <div className="empty">Inga resultat för aktuell säsong.</div> : (
        <div className="scroll-x"><table className="t">
          <thead><tr><th>#</th><th>Lag</th><th className="num">S</th><th className="num">V</th><th className="num">O</th><th className="num">F</th><th className="num">Mål</th><th className="num">+/-</th><th className="num">P</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.team_id} className="click" onClick={() => navigate(`lag/${r.team_id}`)}>
              <td>{r.pos}</td><td><div className="row"><Crest name={r.team} size={20} />{r.team}</div></td><td className="num">{r.p}</td><td className="num">{r.w}</td><td className="num">{r.d}</td><td className="num">{r.l}</td><td className="num">{r.gf}–{r.ga}</td><td className="num">{r.gd > 0 ? `+${r.gd}` : r.gd}</td><td className="num"><b>{r.pts}</b></td>
            </tr>))}
          </tbody></table></div>)}
      <div className="small muted panel-pad">Tabellen räknas ur lagrade 90-minutersresultat och är inte en officiell tabell (t.ex. ligafasens särskiljning kan skilja).</div>
    </Panel>
  );
}

const OP_KIND: Record<string, "ok" | "warn" | "err" | "info"> = { operativ: "ok", "begränsad": "warn", "spärrad": "info", inaktuell: "err", saknas: "err" };
const OP_LABEL: Record<string, string> = { operativ: "Operativ", "begränsad": "Begränsad", "spärrad": "Spärrad (licens)", inaktuell: "Inaktuell data", saknas: "Ingen data" };

function CoverageMini({ comp }: { comp: string }) {
  const [cov, setCov] = useState<any>(null);
  const [op, setOp] = useState<any>(null);
  useEffect(() => { api(`/coverage?competition=${comp}`).then(setCov).catch(() => setCov({ seasons: [] })); }, [comp]);
  useEffect(() => { api(`/operational?competitions=${comp}`).then(setOp).catch(() => setOp(null)); }, [comp]);
  if (!cov) return <Loading />;
  const m = op?.competitions?.[0]?.metrics;
  return (
    <div className="col" style={{ gap: 14 }}>
    {m && <Panel title="Driftstatus för prognosmodulen" icon={Icon.check()} right={<a className="btn sm" href="#/data?tab=historik">Hämta historik</a>}>
      <div className="panel-pad col" style={{ gap: 8 }}>{["goals", "corners", "shots", "sot"].map((k) => (
        <div key={k} className="row" style={{ alignItems: "flex-start" }}><span style={{ width: 120 }}><b>{m[k].label}</b></span>
          <StatusBadge kind={OP_KIND[m[k].status] || "neutral"}>{OP_LABEL[m[k].status] || m[k].status}</StatusBadge>
          <span className="small muted">{m[k].reason}{m[k].needs?.length ? ` ${m[k].needs[0]}` : ""}</span></div>))}</div>
    </Panel>}
    <Panel title="Datatäckning per säsong" icon={Icon.db()} right={<a className="btn sm" href="#/data?tab=tackning">Detaljer</a>}>
      {cov.seasons.length === 0 ? <div className="empty">Ingen data.</div> : (
        <div className="scroll-x"><table className="t">
          <thead><tr><th>Säsong</th><th className="num">Spelade</th><th>Resultat</th><th>Skott</th><th>Skott på mål</th><th>Hörnor</th></tr></thead>
          <tbody>{cov.seasons.slice().reverse().map((s: any) => (
            <tr key={s.season}><td>{s.season}</td><td className="num">{s.finished}</td>
              {["goals", "shots", "sot", "corners"].map((m) => (
                <td key={m} title={`Alla källor: ${pct(s.metrics[m].pct_any)} · tillåtna för träning: ${pct(s.metrics[m].pct_training)}`}>
                  <div className="row small"><span style={{ width: 44 }}>{pct(s.metrics[m].pct_training)}</span><span className="muted">({pct(s.metrics[m].pct_any)})</span></div>
                </td>))}
            </tr>))}</tbody></table></div>)}
      <div className="small muted panel-pad">Första siffran = andel matcher med värde från källor som får användas för träning; inom parentes = alla källor. Saknade värden lagras tomma, aldrig som 0.</div>
    </Panel>
    </div>
  );
}
