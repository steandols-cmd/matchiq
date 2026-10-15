import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api, openReport } from "../api";
import { CompetitionTabs, navigate, type Competition, type Route } from "../App";
import { fmtDate, fmtDay, fmtFull, fmtLong, fmtTime, num, pct, roundTo100 } from "../format";
import { BarCompare } from "../charts";
import { Crest, ErrorBox, FormDots, Icon, LineupBadge, Loading, Meter, ModelBadge, Panel, ProbCards, StatusBadge } from "../ui";

type Fam = "V2" | "V3";
const METRICS: [string, string][] = [["goals", "Mål"], ["corners", "Hörnor"], ["shots", "Skott"], ["sot", "Skott på mål"]];

function normalize(d: any) {
  const fr = d.frozen;
  const pv = d.preview;
  if (fr) {
    const snaps = fr.snapshots;
    const any = snaps.V2 || snaps.V3 || Object.values(snaps)[0];
    const pl = any.payload || {};
    const models: Record<string, any> = {};
    for (const [fam, s] of Object.entries<any>(snaps)) {
      const key = fam === "LEGACY" ? s.model_version_id : fam;
      models[key] = s.payload?.model || {
        probs: s.p_home != null ? { p_home: s.p_home, p_draw: s.p_draw, p_away: s.p_away } : null,
        metrics: legacyMetrics(s), status: "arkiverad", coverage: {}, params: {}, version: s.model_version_id,
      };
    }
    if (!models.V2 && models["LEGACY-V2"]) models.V2 = models["LEGACY-V2"];
    if (!models.V3 && models["LEGACY-V3"]) models.V3 = models["LEGACY-V3"];
    return {
      source: "frozen" as const, kind: fr.kind, created: any.created_at_utc, cutoff: any.data_cutoff_utc,
      models, lineups: pl.lineups || pv?.lineups, absences: pl.absences || pv?.absences, flags: pl.flags || [],
      training: pl.training_sources || pv?.training_sources || [], blocked: pl.blocked_sources || pv?.blocked_sources || [],
      used: pl.sources_used || pv?.sources_used || {}, snapIds: Object.fromEntries(Object.entries<any>(snaps).map(([k, s]) => [k, s.id])),
      note: pl.note, eligible: any.prematch_eligible,
    };
  }
  return {
    source: "preview" as const, kind: "preview", created: d.now_utc, cutoff: pv?.data_cutoff_utc, models: pv?.models || {},
    lineups: pv?.lineups, absences: pv?.absences, flags: pv?.flags || [], training: pv?.training_sources || [],
    blocked: pv?.blocked_sources || [], used: pv?.sources_used || {}, snapIds: {}, note: null, eligible: null,
  };
}

function legacyMetrics(s: any) {
  const blk = (h: number | null, a: number | null) => h == null ? null : ({
    home: { mean: h, lo: null, hi: null }, away: { mean: a, lo: null, hi: null }, total: { mean: (h || 0) + (a || 0), lo: null, hi: null },
  });
  return { goals: blk(s.goals_home, s.goals_away), corners: blk(s.corners_home, s.corners_away), shots: blk(s.shots_home, s.shots_away), sot: blk(s.sot_home, s.sot_away) };
}

export function MatchView({ id, route, comps }: { id: number; route: Route; comps: Competition[] }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [fam, setFam] = useState<Fam>((route.params.get("modell") as Fam) || "V2");
  const [tab, setTab] = useState(route.params.get("flik") || "statistik");
  const [models, setModels] = useState<any[]>([]);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    setErr(null);
    api(`/matches/${id}`).then((x) => alive && setD(x)).catch((e) => alive && setErr(e));
    api("/models").then((x) => alive && setModels(x)).catch(() => undefined);
    return () => { alive = false; };
  }, [id, reload]);

  const ctx = useMemo(() => (d ? normalize(d) : null), [d]);
  if (err) return <ErrorBox error={err} />;
  if (!d || !ctx) return <Loading text="Beräknar prognos…" />;
  const m = d.match;
  const model = ctx.models[fam];
  const probs = model?.probs || null;
  const finished = m.status === "finished";

  const tabs: [string, string, ReactNode][] = [
    ["statistik", "Statistik", Icon.bars()], ["djupanalys", "Djupanalys", Icon.search()], ["v2v3", "V2 mot V3", Icon.scale()],
    ["odds", "Oddsjämförelse", Icon.scale()], ["datakvalitet", "Datakvalitet", Icon.db()],
    ["utfall", finished ? "Utfall" : "Eftermatch", Icon.check()], ["rapporter", "Rapporter", Icon.pdf()],
  ];

  return (
    <div>
      <CompetitionTabs comps={comps} active={m.comp_code} onPick={(c) => navigate(`matcher?c=${c}`)} />
      <div className="layout-match">
        <div className="col" style={{ gap: 0 }}>
          <section className="panel" style={{ overflow: "hidden" }}>
            <div className="hero">
              <div className="hero-top">
                <div className="hero-comp">{m.comp_name}</div>
                <div className="hero-meta">{[m.stage === "LEAGUE_PHASE" ? "Ligafas" : m.stage, m.matchday, fmtLong(m.kickoff_utc)].filter(Boolean).join(" · ")}</div>
              </div>
              <div className="hero-teams">
                <div className="hero-team" onClick={() => navigate(`lag/${m.home_team_id}`)} style={{ cursor: "pointer" }}>
                  <Crest name={m.home_name} c1={m.home_c1} c2={m.home_c2} crest={m.home_crest} size={86} /><div className="name">{m.home_name}</div><div className="role">Hemmalag</div>
                </div>
                <div className="vs">VS</div>
                <div className="hero-team" onClick={() => navigate(`lag/${m.away_team_id}`)} style={{ cursor: "pointer" }}>
                  <Crest name={m.away_name} c1={m.away_c1} c2={m.away_c2} crest={m.away_crest} size={86} /><div className="name">{m.away_name}</div><div className="role">Bortalag</div>
                </div>
              </div>
              <div className="model-switch">
                <div className="seg">
                  <button className={fam === "V2" ? "on v2" : ""} onClick={() => setFam("V2")}>V2 · jämförelsebaslinje</button>
                  <button className={fam === "V3" ? "on v3" : ""} onClick={() => setFam("V3")}>V3 · experimentell</button>
                </div>
              </div>
              <ProbCards p={probs} />
              <div className="freeze-line">
                {ctx.source === "frozen"
                  ? <>Fryst {ctx.kind === "late" ? "SEN rapport" : ctx.kind === "legacy" ? "prognos (importerad från arbetsbok)" : ctx.kind === "manual" ? "manuell prognos" : "T−30-prognos"} {fmtFull(ctx.created)} · datagräns {fmtFull(ctx.cutoff)}{ctx.eligible === 0 ? " · ej behörig som förmatchsprognos" : ""}</>
                  : <>Förhandsvisning – ej fryst. Beräknad med data fram till {fmtFull(ctx.cutoff)}. T−30-prognosen fryses automatiskt.</>}
              </div>
            </div>
          </section>
          <div className="tabs" role="tablist">
            {tabs.map(([k, l, ic]) => (
              <button key={k} className={`tab ${tab === k ? "active" : ""}`} onClick={() => setTab(k)} role="tab" aria-selected={tab === k}>
                <span className="icon">{ic}</span>{l}
              </button>
            ))}
          </div>
          {tab === "statistik" && <StatsTab m={m} model={model} fam={fam} />}
          {tab === "djupanalys" && <DeepTab d={d} ctx={ctx} fam={fam} />}
          {tab === "v2v3" && <CompareTab m={m} ctx={ctx} models={models} />}
          {tab === "odds" && <OddsTab d={d} model={model} fam={fam} />}
          {tab === "datakvalitet" && <QualityTab d={d} ctx={ctx} fam={fam} models={models} />}
          {tab === "utfall" && <OutcomeTab d={d} ctx={ctx} onSaved={() => setReload((x) => x + 1)} />}
          {tab === "rapporter" && <ReportsTab d={d} onChanged={() => setReload((x) => x + 1)} />}
        </div>
        <div className="sticky-col">
          <LineupPanel m={m} ctx={ctx} />
          <LeagueMatches m={m} />
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Statistik
function iv(b: any) {
  if (!b || b.lo == null || b.hi == null) return "";
  return `[${b.lo}–${b.hi}]`;
}

function StatCard({ title, icon, blk, home, away, digits = 1, note }: { title: string; icon: ReactNode; blk: any; home: string; away: string; digits?: number; note?: string }) {
  return (
    <div className="stat-card">
      <div className="head"><span className="icon">{icon}</span>{title}<span className="info" title={note || "Förväntat värde och 80 %-intervall (P10–P90)"}>{Icon.info()}</span></div>
      {blk ? (
        <div className="kv">
          <span className="k">{home}</span><span className="v">{num(blk.home.mean, digits)}</span><span className="iv">{iv(blk.home)}</span>
          <span className="k">{away}</span><span className="v">{num(blk.away.mean, digits)}</span><span className="iv">{iv(blk.away)}</span>
          <span className="k">Totalt</span><span className="v tot">{num(blk.total.mean, digits)}</span><span className="iv">{iv(blk.total)}</span>
        </div>
      ) : (
        <div><div className="missing">Saknas</div><div className="missing-note">Ingen tillåten träningsdata för måttet (spärrad källa eller för få matcher). Visas aldrig som 0.</div></div>
      )}
    </div>
  );
}

function StatsTab({ m, model, fam }: { m: any; model: any; fam: Fam }) {
  if (!model) return <div className="panel empty">Modellen {fam} har ingen prognos för matchen.</div>;
  const mets = model.metrics || {};
  const ex = mets.goals?.extras || {};
  const p = model.probs;
  const r = p ? roundTo100([p.p_home, p.p_draw, p.p_away]) : null;
  return (
    <div className="col">
      <div className="row"><ModelBadge family={fam} status={model.status} /><span className="small muted">{model.version ? `Version ${model.version}` : ""} · intervall = 80 % (P10–P90) ur modellens fördelning</span></div>
      <div className="stat-grid">
        <StatCard title="Förväntade hörnor" icon={Icon.flag()} blk={mets.corners} home={m.home_name} away={m.away_name} />
        <StatCard title="Förväntade mål" icon={Icon.trend()} blk={mets.goals} home={m.home_name} away={m.away_name} digits={2} />
        <StatCard title="Totalt antal skott" icon={Icon.target()} blk={mets.shots} home={m.home_name} away={m.away_name} />
        <StatCard title="Skott på mål" icon={Icon.net()} blk={mets.sot} home={m.home_name} away={m.away_name} />
        <div className="stat-card">
          <div className="head"><span className="icon">{Icon.net()}</span>Båda lagen gör mål</div>
          {ex.btts != null ? (<><div className="big-yes">{ex.btts >= 0.5 ? "Ja" : "Nej"}</div><div className="center muted">Sannolikhet: {pct(ex.btts)}</div>
            <div className="center small muted">Över 2,5 mål: {pct(ex.over_2_5)} · troligast {ex.most_likely_score ? `${ex.most_likely_score[0]}–${ex.most_likely_score[1]}` : "–"}</div></>)
            : <div className="missing">Saknas</div>}
        </div>
        <div className="stat-card">
          <div className="head"><span className="icon">{Icon.trophy()}</span>Fulltid 1X2 (modell)</div>
          {r ? (
            <div className="kv">
              <span className="k">{m.home_name} (1)</span><span className="v">{r[0]}%</span><span className="iv">{num(1 / p.p_home, 2)}</span>
              <span className="k">X</span><span className="v">{r[1]}%</span><span className="iv">{num(1 / p.p_draw, 2)}</span>
              <span className="k">{m.away_name} (2)</span><span className="v">{r[2]}%</span><span className="iv">{num(1 / p.p_away, 2)}</span>
            </div>) : <div className="missing">Saknas</div>}
        </div>
      </div>
      {(model.warnings || []).length > 0 && (
        <div className="callout warn"><span className="ic">{Icon.warn()}</span><div>{model.warnings.map((w: string, i: number) => <div key={i}>{w}</div>)}</div></div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ Djupanalys
function DeepTab({ d, ctx, fam }: { d: any; ctx: any; fam: Fam }) {
  const m = d.match;
  const deep = d.deep;
  const model = ctx.models[fam];
  const p = model?.probs;
  const avg = deep.averages;
  const g = model?.metrics?.goals;
  const sentence = p && g ? (() => {
    const fav = p.p_home > p.p_away ? m.home_name : m.away_name;
    const fp = Math.max(p.p_home, p.p_away);
    const cov = model.coverage?.goals || {};
    const thin = Math.min(cov.home_n ?? 99, cov.away_n ?? 99) < 5;
    return `${fam} ger ${fav} ${pct(fp)} chans att vinna, med förväntat målresultat ${num(g.home.mean, 2)}–${num(g.away.mean, 2)}. ` +
      `Prognosen bygger på ${cov.home_n ?? "?"} respektive ${cov.away_n ?? "?"} tidigare matcher i tävlingen` +
      (thin ? ", vilket är tunt – osäkerheten är större än vanligt." : ".") +
      (ctx.lineups?.home?.status !== "confirmed" || ctx.lineups?.away?.status !== "confirmed" ? " Minst en startelva är inte bekräftad vid datagränsen." : "");
  })() : "Ingen modellprognos finns att sammanfatta.";
  const rows: [string, string][] = [["goals", "Mål"], ["shots", "Skott"], ["sot", "Skott på mål"], ["corners", "Hörnor"], ["xg", "xG"]];
  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="layout-2">
        <Panel title="Senaste form" icon={Icon.trend()}>
          <div className="panel-pad col">
            {[["home", m.home_name, m.home_team_id], ["away", m.away_name, m.away_team_id]].map(([side, name]) => {
              const f = deep.form[side as string] as any[];
              const gf = f.reduce((a, x) => a + x.gf, 0), ga = f.reduce((a, x) => a + x.ga, 0);
              return (<div key={side as string} className="row"><Crest name={name as string} /><b style={{ width: 150 }} className="nowrap">{name as string}</b><FormDots form={f} /><span className="muted small" style={{ marginLeft: "auto" }}>Mål {gf}–{ga}</span></div>);
            })}
            <div className="tiny muted">Senaste fem matcherna i alla tävlingar före avspark (äldst till vänster).</div>
          </div>
        </Panel>
        <Panel title="Snitt för / emot (senaste 10 i tävlingen)" icon={Icon.bars()}>
          <div className="scroll-x"><table className="t">
            <thead><tr><th>Mått</th><th className="num">{m.home_name}</th><th className="num">n</th><th className="num">{m.away_name}</th><th className="num">n</th></tr></thead>
            <tbody>{rows.map(([k, l]) => (
              <tr key={k}><td>{l}</td>
                <td className="num">{avg.home[k]?.n ? `${num(avg.home[k].for)} / ${num(avg.home[k].against)}` : <span className="missing">saknas</span>}</td><td className="num muted">{avg.home[k]?.n ?? 0}</td>
                <td className="num">{avg.away[k]?.n ? `${num(avg.away[k].for)} / ${num(avg.away[k].against)}` : <span className="missing">saknas</span>}</td><td className="num muted">{avg.away[k]?.n ?? 0}</td>
              </tr>))}</tbody></table></div>
        </Panel>
      </div>
      <div className="layout-2">
        <Panel title="Inbördes möten" icon={Icon.scale()}>
          {deep.h2h.length === 0 ? <div className="empty">Inga tidigare möten i databasen.</div> : (
            <table className="t"><tbody>{deep.h2h.map((h: any) => (
              <tr key={h.id}><td className="nowrap">{fmtDate(h.kickoff_utc)} {new Date(h.kickoff_utc).getFullYear()}</td><td>{h.home}</td><td className="center"><b>{h.hg}–{h.ag}</b></td><td>{h.away}</td><td className="muted small">{h.comp}</td></tr>))}</tbody></table>)}
        </Panel>
        <Panel title="Skador & avstängningar" icon={Icon.shield()}>
          <div className="panel-pad">
            {[["home", m.home_name], ["away", m.away_name]].map(([side, name]) => {
              const list = (ctx.absences?.[side] || []) as any[];
              return (<div key={side} style={{ marginBottom: 8 }}><b>{name}</b>
                {list.length === 0 ? <div className="small muted">Inga rapporterade frånvaron vid datagränsen (det betyder inte att alla är tillgängliga).</div> :
                  list.map((a, i) => <div key={i} className="row small"><StatusBadge kind={a.kind === "doubtful" ? "warn" : "err"}>{({ injury: "Ute", suspension: "Avstängd", doubtful: "Tveksam", other: "Övrigt" } as any)[a.kind]}</StatusBadge>{a.player_name}<span className="muted tiny" style={{ marginLeft: "auto" }}>{a.source_id}</span></div>)}
              </div>);
            })}
          </div>
        </Panel>
      </div>
      <Panel title="Analys & slutsats" icon={Icon.bulb()}>
        <div className="panel-pad">
          <p style={{ margin: 0 }}>{sentence}</p>
          <p className="small muted">Texten genereras regelbaserat ur modellens siffror och datatäckningen – inga påhittade faktorpoäng eller spelarbetyg används.</p>
        </div>
      </Panel>
    </div>
  );
}

// ------------------------------------------------------------------ V2 mot V3
function CompareTab({ m, ctx, models }: { m: any; ctx: any; models: any[] }) {
  const fams = ["V2", "V3", "BASE"].filter((f) => ctx.models[f]);
  const rows: [string, (x: any) => string][] = [
    ["1 (hemma)", (x) => pct(x?.probs?.p_home, 1)], ["X", (x) => pct(x?.probs?.p_draw, 1)], ["2 (borta)", (x) => pct(x?.probs?.p_away, 1)],
    ...METRICS.flatMap(([k, l]) => [
      [`${l} – ${m.home_name}`, (x: any) => blk(x, k, "home")], [`${l} – ${m.away_name}`, (x: any) => blk(x, k, "away")], [`${l} – totalt`, (x: any) => blk(x, k, "total")],
    ] as [string, (x: any) => string][]),
    ["Båda lagen gör mål", (x) => pct(x?.metrics?.goals?.extras?.btts)], ["Över 2,5 mål", (x) => pct(x?.metrics?.goals?.extras?.over_2_5)],
  ];
  return (
    <div className="col" style={{ gap: 14 }}>
      <Panel title="V2 och V3 sida vid sida" icon={Icon.scale()}>
        <div className="scroll-x"><table className="t">
          <thead><tr><th>Mått</th>{fams.map((f) => <th key={f} className="num"><ModelBadge family={f} status={ctx.models[f]?.status} /></th>)}</tr></thead>
          <tbody>{rows.map(([l, fn]) => <tr key={l}><td>{l}</td>{fams.map((f) => <td key={f} className="num">{fn(ctx.models[f])}</td>)}</tr>)}</tbody>
        </table></div>
      </Panel>
      <div className="layout-2">
        {models.filter((x) => x.family === "V2" || x.family === "V3").map((x) => (
          <Panel key={x.id} title={<span className="row"><ModelBadge family={x.family} status={x.status} />{x.id}</span>}>
            <div className="panel-pad col small">
              <div>{x.description}</div>
              <div>Status: <b>{x.status}</b> {x.status_reason ? <span className="muted">({x.status_reason})</span> : null}</div>
              {x.gates?.checks ? x.gates.checks.map((c: any) => (
                <div key={c.key} className="row"><span style={{ color: c.ok ? "var(--ok)" : "var(--warn)" }}>{c.ok ? Icon.check(16) : Icon.warn(16)}</span>{c.text}</div>
              )) : <div className="muted">Ingen valideringskörning ännu – kör modellval under Utvärdering.</div>}
            </div>
          </Panel>
        ))}
      </div>
    </div>
  );
}
function blk(x: any, k: string, side: string) {
  const b = x?.metrics?.[k]?.[side];
  if (!b) return "saknas";
  return `${num(b.mean, k === "goals" ? 2 : 1)}${b.lo != null ? ` [${b.lo}–${b.hi}]` : ""}`;
}

// ------------------------------------------------------------------ Odds
function OddsTab({ d, model, fam }: { d: any; model: any; fam: Fam }) {
  const odds: any[] = d.odds || [];
  const p = model?.probs;
  const latest = new Map<string, any>();
  for (const o of odds) if (!latest.has(o.bookmaker)) latest.set(o.bookmaker, o);
  const books = Array.from(latest.values());
  if (!books.length) {
    return (
      <Panel title="Oddsjämförelse" icon={Icon.scale()}>
        <div className="empty">
          Inga marknadsodds finns för matchen.
          <div className="small" style={{ marginTop: 8 }}>Aktivera <b>The Odds API</b> (kräver nyckel) under Data &amp; källor eller importera odds från fil. Odds används endast för jämförelse – aldrig som träningsdata.</div>
        </div>
      </Panel>
    );
  }
  const noVig = books.map((b) => { const inv = [1 / b.odds_home, 1 / b.odds_draw, 1 / b.odds_away]; const s = inv[0] + inv[1] + inv[2]; return inv.map((x) => x / s); });
  const market = [0, 1, 2].map((i) => noVig.reduce((a, v) => a + v[i], 0) / noVig.length);
  const best = [0, 1, 2].map((i) => books.reduce((a, b) => Math.max(a, [b.odds_home, b.odds_draw, b.odds_away][i]), 0));
  const mp = p ? [p.p_home, p.p_draw, p.p_away] : null;
  const labels = ["Hemma", "Oavgjort", "Borta"];
  return (
    <div className="col" style={{ gap: 14 }}>
      <Panel title="Oddsjämförelse" icon={Icon.scale()} right={<span className="small muted">Senast hämtat {fmtFull(books[0].fetched_at_utc)}</span>}>
        <div className="scroll-x"><table className="t">
          <thead><tr><th>Utfall</th><th className="num">Modell {fam}</th><th className="num">Rättvist odds</th>{books.map((b) => <th key={b.bookmaker} className="num">{b.bookmaker}</th>)}<th className="num">EV (bästa)</th></tr></thead>
          <tbody>{labels.map((l, i) => {
            const ev = mp ? mp[i] * best[i] - 1 : null;
            return (<tr key={l}><td><b>{l}</b></td><td className="num">{mp ? pct(mp[i]) : "saknas"}</td><td className="num">{mp ? num(1 / mp[i], 2) : "–"}</td>
              {books.map((b) => <td key={b.bookmaker} className="num">{num([b.odds_home, b.odds_draw, b.odds_away][i], 2)}</td>)}
              <td className="num" style={{ color: ev != null && ev > 0 ? "var(--ok)" : "var(--muted)" }}>{ev == null ? "–" : `${ev > 0 ? "+" : ""}${num(ev * 100, 1)}%`}</td></tr>);
          })}</tbody>
        </table></div>
      </Panel>
      <Panel title="Marknad (marginalrensad) mot modell" icon={Icon.bars()}>
        <div className="panel-pad"><BarCompare labels={labels} a={mp || [0, 0, 0]} b={market} aLabel={`Modell ${fam}`} bLabel="Marknad (snitt)" /></div>
      </Panel>
      <div className="callout warn"><span className="ic">{Icon.warn()}</span><div><b>Viktigt:</b> EV räknas mot en modell som inte är fullt kalibrerad (V3 är experimentell). Detta är statistik, inga spelråd. Spela ansvarsfullt – 18 år.</div></div>
    </div>
  );
}

// ------------------------------------------------------------------ Datakvalitet
function QualityTab({ d, ctx, fam, models }: { d: any; ctx: any; fam: Fam; models: any[] }) {
  const m = d.match;
  const model = ctx.models[fam] || {};
  const cov = model.coverage || {};
  const q = (v: number) => (v >= 0.85 ? ["Hög", "ok"] : v >= 0.6 ? ["Medel", "warn"] : ["Låg", "err"]) as [string, "ok" | "warn" | "err"];
  const teamScore = (k: string) => {
    const c = cov[k];
    if (!c || c.status === "spärrad" || c.status === "otillräcklig") return 0;
    return Math.min(1, Math.min(c.home_n ?? 0, c.away_n ?? 0) / 10);
  };
  const lu = ctx.lineups || {};
  const luScore = ["home", "away"].reduce((a, s) => a + (lu[s]?.status === "confirmed" ? 0.5 : lu[s]?.status === "expected" ? 0.3 : 0), 0);
  const absences = (ctx.absences?.home?.length || 0) + (ctx.absences?.away?.length || 0);
  const mv = models.find((x) => x.family === fam);
  const calib = mv?.gates ? (mv.gates.checks.filter((c: any) => c.ok).length / mv.gates.checks.length) : 0;
  const rows: [string, ReactNode, number, string][] = [
    ["Laghistorik i tävlingen (mål)", Icon.users(), teamScore("goals"), `${cov.goals?.home_n ?? 0} / ${cov.goals?.away_n ?? 0} matcher (mål ≥ 10 per lag = full poäng)`],
    ["Hörnor", Icon.flag(), teamScore("corners"), cov.corners ? `${cov.corners.league_n} matcher i tävlingen · status ${cov.corners.status}` : "saknas"],
    ["Skott", Icon.target(), teamScore("shots"), cov.shots ? `${cov.shots.league_n} matcher · status ${cov.shots.status}` : "saknas"],
    ["Skott på mål", Icon.net(), teamScore("sot"), cov.sot ? `${cov.sot.league_n} matcher · status ${cov.sot.status}` : "saknas"],
    ["Startelvor vid datagränsen", Icon.pitch(), luScore, `${lu.home?.label || "Opublicerad"} / ${lu.away?.label || "Opublicerad"}`],
    ["Skador & avstängningar", Icon.shield(), absences > 0 ? 0.8 : 0.4, absences > 0 ? `${absences} rapporterade frånvaron` : "inga rapporter (osäkert om komplett)"],
    ["Oddsdata (jämförelse)", Icon.trend(), d.odds?.length ? 1 : 0, d.odds?.length ? `${d.odds.length} oddsrader` : "saknas – används inte i modellen"],
    ["Modellkalibrering", Icon.gear(), calib, mv ? `${mv.status} · ${mv.gates ? `${mv.gates.checks.filter((c: any) => c.ok).length}/${mv.gates.checks.length} grindar uppfyllda` : "ej validerad"}` : "–"],
  ];
  const core = rows.slice(0, 5).map((r) => r[2]);
  const total = core.reduce((a, b) => a + b, 0) / core.length;
  const [lbl, kind] = q(total);
  return (
    <div className="col" style={{ gap: 14 }}>
      <Panel title="Datakvalitet" icon={Icon.db()} right={<span className="small muted">Datagräns {fmtFull(ctx.cutoff)}</span>}>
        <div className="scroll-x"><table className="t">
          <tbody>{rows.map(([l, ic, v, note]) => {
            const [ql, qk] = q(v);
            return (<tr key={l}><td style={{ width: 28, color: "var(--accent)" }}>{ic}</td><td className="nowrap">{l}</td><td><StatusBadge kind={qk}>{ql}</StatusBadge></td><td style={{ width: "26%" }}><Meter value={v} /></td><td className="num nowrap">{Math.round(v * 100)}%</td><td className="small muted">{note}</td></tr>);
          })}</tbody></table></div>
      </Panel>
      <div className="layout-2">
        <Panel title={<span>Prognosstatus: <span style={{ color: kind === "ok" ? "var(--ok)" : kind === "warn" ? "var(--warn)" : "var(--danger)" }}>{lbl}</span></span>} icon={Icon.check()}>
          <div className="panel-pad col small">
            <div><b>{Math.round(total * 100)} %</b> sammanvägd datakvalitet (laghistorik, räknemått och startelvor; regelbaserad bedömning).</div>
            {(ctx.flags || []).map((f: any, i: number) => (
              <div key={i} className="row" style={{ alignItems: "flex-start" }}><span style={{ color: f.level === "warning" ? "var(--warn)" : "var(--muted)", flex: "none" }}>{f.level === "warning" ? Icon.warn(16) : Icon.info(16)}</span><span>{f.text}</span></div>
            ))}
          </div>
        </Panel>
        <Panel title="Källor och licenser" icon={Icon.shield()}>
          <div className="panel-pad col small">
            <div><b>Träningsdata från:</b> {ctx.training.join(", ") || "ingen"}</div>
            {Object.entries<any>(ctx.used || {}).map(([k, v]) => (
              <div key={k}>{({ goals: "Mål", shots: "Skott", sot: "Skott på mål", corners: "Hörnor" } as any)[k]}: {Object.keys(v).length ? Object.entries(v).map(([s, n]) => `${s} (${n})`).join(", ") : <span className="missing">ingen tillåten källa</span>}</div>
            ))}
            {ctx.blocked.length > 0 && <div><b>Spärrade från träning:</b>{ctx.blocked.map((b: any) => <div key={b.id} className="muted">· {b.name}: {b.reason}</div>)}</div>}
            <a href="#/data?tab=kallor">Hantera källor och licenser →</a>
          </div>
        </Panel>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Utfall / eftermatch
function OutcomeTab({ d, ctx, onSaved }: { d: any; ctx: any; onSaved: () => void }) {
  const m = d.match;
  const o = d.outcome || {};
  const started = new Date(m.kickoff_utc).getTime() <= new Date(d.now_utc).getTime();
  const fields: [string, string][] = [["home_goals", `Mål ${m.home_name}`], ["away_goals", `Mål ${m.away_name}`], ["home_corners", `Hörnor ${m.home_name}`], ["away_corners", `Hörnor ${m.away_name}`], ["home_shots", `Skott ${m.home_name}`], ["away_shots", `Skott ${m.away_name}`], ["home_sot", `Skott på mål ${m.home_name}`], ["away_sot", `Skott på mål ${m.away_name}`]];
  const [form, setForm] = useState<Record<string, string>>(Object.fromEntries(fields.map(([k]) => [k, o[k] ?? ""])));
  const [msg, setMsg] = useState<string | null>(null);
  const save = async () => {
    try {
      await api(`/matches/${m.id}/outcome`, { body: form });
      setMsg("Facit sparat. Den frysta prognosen är oförändrad.");
      onSaved();
    } catch (e: any) { setMsg(e.message); }
  };
  const actual: Record<string, [number | null, number | null]> = { goals: [o.home_goals, o.away_goals], corners: [o.home_corners, o.away_corners], shots: [o.home_shots, o.away_shots], sot: [o.home_sot, o.away_sot] };
  return (
    <div className="col" style={{ gap: 14 }}>
      {ctx.source === "frozen" && d.outcome && (
        <Panel title="Fryst prognos mot faktiskt utfall" icon={Icon.check()}>
          <div className="scroll-x"><table className="t">
            <thead><tr><th>Mått</th><th>Lag</th>{["V2", "V3"].filter((f) => ctx.models[f]).map((f) => <th key={f} className="num">{f} prognos</th>)}<th className="num">Utfall</th>{["V2", "V3"].filter((f) => ctx.models[f]).map((f) => <th key={f} className="num">{f} fel</th>)}</tr></thead>
            <tbody>{METRICS.flatMap(([k, l]) => (["home", "away"] as const).map((side, i) => {
              const a = actual[k][i];
              return (<tr key={k + side}><td>{i === 0 ? l : ""}</td><td>{side === "home" ? m.home_name : m.away_name}</td>
                {["V2", "V3"].filter((f) => ctx.models[f]).map((f) => <td key={f} className="num">{num(ctx.models[f]?.metrics?.[k]?.[side]?.mean, 2)}</td>)}
                <td className="num"><b>{a ?? "saknas"}</b></td>
                {["V2", "V3"].filter((f) => ctx.models[f]).map((f) => { const pv = ctx.models[f]?.metrics?.[k]?.[side]?.mean; return <td key={f} className="num">{a == null || pv == null ? "–" : num(Math.abs(pv - a), 2)}</td>; })}
              </tr>);
            }))}</tbody></table></div>
        </Panel>
      )}
      <Panel title="Ange faktiskt utfall (90 minuter)" icon={Icon.check()} right={d.outcome ? <StatusBadge kind="info">Källa: {d.outcome.entered_by}</StatusBadge> : null}>
        <div className="panel-pad col">
          {!started ? <div className="callout"><span className="ic">{Icon.clock()}</span>Matchen har inte spelats. Facit kan anges efter avspark.</div> : (
            <>
              <div className="layout-4">{fields.map(([k, l]) => (
                <label key={k} className="col" style={{ gap: 4 }}><span className="small muted">{l}</span>
                  <input className="in" inputMode="numeric" value={form[k] ?? ""} placeholder="saknas" onChange={(e) => setForm({ ...form, [k]: e.target.value.replace(/[^0-9]/g, "") })} /></label>))}</div>
              <div className="row"><button className="btn primary" onClick={save}>Spara facit</button><span className="small muted">Tomt fält = saknas (aldrig 0). Varje ändring loggas.</span></div>
              {msg && <div className="small">{msg}</div>}
            </>)}
        </div>
      </Panel>
    </div>
  );
}

// ------------------------------------------------------------------ Rapporter
function ReportsTab({ d, onChanged }: { d: any; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const before = new Date(d.match.kickoff_utc).getTime() > new Date(d.now_utc).getTime();
  const act = async (fn: () => Promise<any>, ok: string) => {
    setBusy(true); setMsg(null);
    try { await fn(); setMsg(ok); onChanged(); } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="col" style={{ gap: 14 }}>
      <Panel title="PDF-rapporter" icon={Icon.pdf()} right={<>
        {before && <button className="btn sm" disabled={busy} onClick={() => act(() => api(`/matches/${d.match.id}/freeze`, { body: { pdf: true } }), "Manuell prognos fryst och PDF arkiverad.")}>Frys prognos nu</button>}
        <button className="btn sm" disabled={busy} onClick={() => act(() => api(`/reports/test`, { body: { match_id: d.match.id } }), "Testrapport skapad.")}>Skapa testrapport</button></>}>
        {d.reports.length === 0 ? <div className="empty">Ingen rapport ännu. T−30-rapporten skapas automatiskt.</div> : (
          <table className="t"><thead><tr><th>Typ</th><th>Skapad</th><th>Datagräns</th><th>Fil</th><th /></tr></thead>
            <tbody>{d.reports.map((r: any) => (
              <tr key={r.id}><td>{r.kind === "late" ? <StatusBadge kind="err">SEN</StatusBadge> : r.kind === "T-30" ? <StatusBadge kind="ok">T−30</StatusBadge> : <StatusBadge kind="neutral">{r.kind}</StatusBadge>}</td>
                <td>{fmtFull(r.created_at_utc)}</td><td>{fmtFull(r.data_cutoff_utc)}</td><td className="mono small">{r.path.split(/[\\/]/).pop()}</td>
                <td><button className="btn sm" onClick={() => openReport(r)}>Öppna</button></td></tr>))}</tbody></table>)}
        {msg && <div className="panel-pad small">{msg}</div>}
      </Panel>
      <Panel title="Schemalagda jobb" icon={Icon.clock()}>
        {d.jobs.length === 0 ? <div className="empty">Inget T−30-jobb (matchen saknar känd avsparkstid eller registrerades efter sin deadline).</div> : (
          <table className="t"><thead><tr><th>Förfaller (T−30)</th><th>Status</th><th>Försök</th><th>Kommentar</th></tr></thead>
            <tbody>{d.jobs.map((j: any) => (<tr key={j.id}><td>{fmtFull(j.due_at_utc)}</td><td>{j.status}</td><td>{j.attempts}</td><td className="small muted">{j.last_error || (j.late_by_seconds ? `missad med ${Math.round(j.late_by_seconds / 60)} min` : "")}</td></tr>))}</tbody></table>)}
      </Panel>
    </div>
  );
}

// ------------------------------------------------------------------ Startelvor
function LineupPanel({ m, ctx }: { m: any; ctx: any }) {
  const lu = ctx.lineups || {};
  const [side, setSide] = useState<"home" | "away" | "both">("both");
  const show = (s: "home" | "away") => side === "both" || side === s;
  return (
    <Panel title="Startelvor" icon={Icon.users()} right={<span style={{ color: "var(--accent)" }}>{Icon.pitch()}</span>}>
      <div className="lineup-head">
        {(["home", "away"] as const).map((s) => (
          <button key={s} className={`lineup-team ${s === "home" ? "homec" : ""}`} onClick={() => setSide(side === s ? "both" : s)}>
            <Crest name={s === "home" ? m.home_name : m.away_name} c1={s === "home" ? m.home_c1 : m.away_c1} c2={s === "home" ? m.home_c2 : m.away_c2} crest={s === "home" ? m.home_crest : m.away_crest} size={26} /><span>{s === "home" ? m.home_name : m.away_name}</span>
          </button>))}
      </div>
      <div className="lineup-cols">
        {(["home", "away"] as const).filter(show).map((s) => {
          const x = lu[s] || { status: "unpublished", players: [] };
          return (
            <div key={s} className="lineup-list">
              <div className="lineup-status">
                <div className="row"><b className="small">Startelva – {s === "home" ? m.home_name : m.away_name}</b></div>
                <div className="row"><LineupBadge status={x.status} />{x.formation && <span className="small muted">{x.formation}</span>}</div>
                {x.source && <div className="tiny muted">Källa: {x.source} · sedd {fmtFull(x.fetched_at_utc)}</div>}
              </div>
              {x.players?.length ? x.players.map((p: any, i: number) => (
                <div className="pl" key={i}><span className="muted">{p.number ?? "·"}</span><span>{p.name}</span><span className="pos">{p.position || ""}</span></div>
              )) : <div className="lineup-empty">{x.note || "Ingen elva publicerad ännu."} Ingen spelarstatus antas.</div>}
            </div>);
        })}
      </div>
    </Panel>
  );
}

function LeagueMatches({ m }: { m: any }) {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    const ko = new Date(m.kickoff_utc).getTime();
    const p = new URLSearchParams({ competition: m.comp_code, from: new Date(ko - 2 * 86400e3).toISOString(), to: new Date(ko + 3 * 86400e3).toISOString(), limit: "12" });
    api(`/matches?${p}`).then(setRows).catch(() => setRows([]));
  }, [m.id, m.comp_code, m.kickoff_utc]);
  return (
    <Panel title="Matcher i vald liga" icon={Icon.ball()} right={<span className="small muted">{m.comp_name}</span>}>
      {rows.map((r) => (
        <div key={r.id} className="mini-row" onClick={() => navigate(`match/${r.id}`)} style={r.id === m.id ? { background: "var(--panel-hi)" } : undefined}>
          <div className="small"><div>{fmtDay(r.kickoff_utc)} {fmtDate(r.kickoff_utc)}</div><b>{fmtTime(r.kickoff_utc)}</b></div>
          <div className="teams"><div><Crest name={r.home} c1={r.home_c1} c2={r.home_c2} size={16} />{r.home}</div><div><Crest name={r.away} c1={r.away_c1} c2={r.away_c2} size={16} />{r.away}</div></div>
          <span className="chev">{Icon.chev(14)}</span>
          <button className="go-btn" onClick={(e) => { e.stopPropagation(); navigate(`match/${r.id}`); }}>Gå till match</button>
        </div>))}
      {rows.length === 0 && <div className="empty">Inga närliggande matcher.</div>}
    </Panel>
  );
}
