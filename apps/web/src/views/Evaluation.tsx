import { useEffect, useState } from "react";
import { api, pollJob } from "../api";
import { navigate, type Route } from "../App";
import { fmtDate, fmtFull, num, pct } from "../format";
import { Calibration, Series } from "../charts";
import { ErrorBox, Icon, Loading, ModelBadge, Panel, StatusBadge, Switch } from "../ui";

const MODEL_LABEL: Record<string, string> = {
  "V2-2.0": "V2", "V3-3.0": "V3", "BASE-1.0": "Baslinje", "LEGACY-ORIG": "Arbetsbok – ursprung", "LEGACY-V2": "Arbetsbok – V2", "LEGACY-V3": "Arbetsbok – V3-skugga",
};
const FAM: Record<string, string> = { "V2-2.0": "V2", "V3-3.0": "V3", "BASE-1.0": "BASE" };
const COLORS: Record<string, string> = { "V2-2.0": "#f2b233", "V3-3.0": "#5fe0a0", "BASE-1.0": "#8ca3c2", "LEGACY-ORIG": "#b48cff", "LEGACY-V2": "#ffd27a", "LEGACY-V3": "#a8f5c8" };
const METRICS: [string, string][] = [["goals", "Mål"], ["corners", "Hörnor"], ["shots", "Skott"], ["sot", "Skott på mål"]];

export function EvaluationView({ route }: { route: Route }) {
  const [ev, setEv] = useState<any>(null);
  const [models, setModels] = useState<any[]>([]);
  const [err, setErr] = useState<unknown>(null);
  const [eligible, setEligible] = useState(true);
  const [split, setSplit] = useState<"test" | "validation">("test");
  const [job, setJob] = useState<any>(null);
  const [rev, setRev] = useState(0);
  useEffect(() => {
    setEv(null);
    api(`/evaluation?eligible=${eligible ? 1 : 0}`).then(setEv).catch(setErr);
    api("/models").then(setModels).catch(() => undefined);
  }, [eligible, rev]);
  const runSel = async () => {
    try {
      const { job_id } = await api("/models/selection", { body: { competition: "UCL" } });
      await pollJob(job_id, setJob);
      setJob(null); setRev((x) => x + 1);
    } catch (e: any) { setJob({ status: "error", message: e.message }); }
  };
  if (err) return <ErrorBox error={err} />;
  if (!ev) return <Loading text="Laddar utvärdering…" />;
  const bt = ev.backtest;
  const order = ["V2-2.0", "V3-3.0", "BASE-1.0"].filter((k) => bt[k]);
  const cfg = order.length ? bt[order[0]].config : null;
  const pros = ev.prospective;
  const pkeys = Object.keys(pros).sort();

  return (
    <div className="col" style={{ gap: 14 }}>
      <div className="layout-3">
        {models.filter((m) => ["V2", "V3", "BASE"].includes(m.family)).map((m) => (
          <Panel key={m.id} title={<span className="row"><ModelBadge family={m.family} status={m.status} />{m.id}</span>}>
            <div className="panel-pad col small">
              <div>{m.description}</div>
              <div>Status: <b>{m.status}</b>{m.family === "V3" && m.status !== "produktion" ? <span className="muted"> – visas som experimentell i hela appen</span> : null}</div>
              {m.gates?.checks ? (
                <div className="col" style={{ gap: 3 }}>{m.gates.checks.map((c: any) => (
                  <div key={c.key} className="row" style={{ alignItems: "flex-start" }}><span style={{ color: c.ok ? "var(--ok)" : "var(--warn)", flex: "none" }}>{c.ok ? Icon.check(15) : Icon.warn(15)}</span><span>{c.text}</span></div>))}</div>
              ) : m.family === "BASE"
                ? <div className="muted">Jämförelsenivå – prövas inte mot produktionsgrindarna. Resultaten finns i valideringstabellen nedan.</div>
                : <div className="muted">Ingen valideringskörning ännu.</div>}
              {m.family === "V3" && m.params?.calibrated && <div className="tiny muted">Valda parametrar (på {m.params.selected_on?.join(", ")}): halveringstid {m.params.half_life_days} d, k={m.params.k}, räknemått {m.params.half_life_days_counts} d / k={m.params.k_counts}, brygga {m.params.bridge}{m.params.bridge !== "off" ? ` β=${m.params.beta}` : ""}, ρ={m.params.rho}</div>}
            </div>
          </Panel>))}
      </div>
      <Panel title="Tidsordnad walk-forward-validering" icon={Icon.trend()} right={<>
        <div className="seg"><button className={split === "validation" ? "on" : ""} onClick={() => setSplit("validation")}>Validering</button><button className={split === "test" ? "on" : ""} onClick={() => setSplit("test")}>Orörd holdout</button></div>
        <button className="btn sm" onClick={runSel} disabled={!!job && job.status === "running"}>{Icon.refresh(14)} Kör modellval &amp; validering</button></>}>
        <div className="panel-pad col small">
          {job && <div className="callout"><span className="ic">{Icon.clock()}</span>{job.message} {job.total ? `(${job.done}/${job.total})` : ""}</div>}
          {cfg ? <div className="muted">Expanding window per matchdag ({cfg.cutoff_rule}). Modellval på {cfg.validation.join(", ")}; orörd holdout {cfg.test.join(", ")}. Underlag från: {cfg.train_sources.join(", ")}. Körd {fmtFull(bt[order[0]].created_at_utc)}.</div>
            : <div className="muted">Ingen walk-forward-körning ännu. Kör modellval (kräver historik med tillåtna källor).</div>}
        </div>
        {order.length > 0 && (
          <>
            <div className="scroll-x"><table className="t">
              <thead><tr><th>Modell</th><th className="num">n (1X2)</th><th className="num">Brier ↓</th><th className="num">Log loss ↓</th><th className="num">Träff</th>
                {METRICS.map(([k, l]) => <th key={k} className="num">{l}: MAE / RMSE / bias / täckning (n)</th>)}</tr></thead>
              <tbody>{order.map((k) => { const s = bt[k].summary.by_split[split] || {}; return (
                <tr key={k}><td><ModelBadge family={FAM[k]} /></td><td className="num">{s["1x2"]?.n ?? 0}</td><td className="num">{num(s["1x2"]?.brier, 3)}</td><td className="num">{num(s["1x2"]?.logloss, 3)}</td><td className="num">{pct(s["1x2"]?.hit_rate)}</td>
                  {METRICS.map(([mk]) => { const c = s[mk] || {}; return <td key={mk} className="num small">{c.n ? `${num(c.mae, 2)} / ${num(c.rmse, 2)} / ${c.bias > 0 ? "+" : ""}${num(c.bias, 2)} / ${pct(c.coverage)} (${c.n})` : "saknas"}</td>; })}</tr>); })}</tbody></table></div>
            <div className="layout-2" style={{ padding: 14 }}>
              <div><b className="small">Kalibreringsdiagram 1X2 ({split === "test" ? "holdout" : "validering"})</b>
                <Calibration series={order.map((k) => ({ name: MODEL_LABEL[k], color: COLORS[k], bins: bt[k].summary.calibration[split] || [] }))} /></div>
              <div><b className="small">Per säsong</b>
                <div className="scroll-x"><table className="t"><thead><tr><th>Säsong</th>{order.map((k) => <th key={k} className="num">{MODEL_LABEL[k]} Brier / LL (n)</th>)}</tr></thead>
                  <tbody>{Object.keys(bt[order[0]].summary.by_season).map((season) => (
                    <tr key={season}><td>{season}</td>{order.map((k) => { const x = bt[k].summary.by_season[season]?.["1x2"]; return <td key={k} className="num small">{x?.n ? `${num(x.brier, 3)} / ${num(x.logloss, 3)} (${x.n})` : "–"}</td>; })}</tr>))}</tbody></table></div>
                <div className="tiny muted" style={{ marginTop: 8 }}>Lägre Brier och log loss är bättre. Kalibreringen poolar 1-, X- och 2-sannolikheter. Intervalltäckning = andel utfall inom P10–P90 (mål: ~80 %).</div>
              </div>
            </div>
          </>)}
      </Panel>
      <Panel title="Frysta prognoser mot faktiskt utfall" icon={Icon.check()} right={<Switch checked={eligible} onChange={setEligible} label="Endast förmatch-behöriga" />}>
        <div className="panel-pad small muted">Varje prognos utvärderas mot sitt eget frysta snapshot – den räknas aldrig om med efterhandsinformation. Minst 200 förmatchsobservationer per mått krävs innan produktionsstatus kan övervägas.</div>
        {pkeys.length === 0 ? <div className="empty">Inga frysta prognoser med facit ännu.</div> : (
          <>
            <div className="scroll-x"><table className="t">
              <thead><tr><th>Modell</th><th className="num">Matcher</th><th className="num">Brier</th><th className="num">Log loss</th><th className="num">Träff</th>{METRICS.map(([k, l]) => <th key={k} className="num">{l} MAE / bias (n)</th>)}<th>Mot krav (200)</th></tr></thead>
              <tbody>{pkeys.map((k) => { const s = pros[k]; const n = s["1x2"]?.n || 0; return (
                <tr key={k}><td>{FAM[k] ? <ModelBadge family={FAM[k]} /> : <StatusBadge kind="neutral">{MODEL_LABEL[k] || k}</StatusBadge>}</td><td className="num">{s.n_matches}</td><td className="num">{num(s["1x2"]?.brier, 3)}</td><td className="num">{num(s["1x2"]?.logloss, 3)}</td><td className="num">{pct(s["1x2"]?.hit_rate)}</td>
                  {METRICS.map(([mk]) => <td key={mk} className="num small">{s[mk]?.n ? `${num(s[mk].mae, 2)} / ${s[mk].bias > 0 ? "+" : ""}${num(s[mk].bias, 2)} (${s[mk].n})` : "saknas"}</td>)}
                  <td style={{ minWidth: 120 }}><div className="row small"><div className="meter" style={{ width: 70 }}><i style={{ width: `${Math.min(100, (n / ev.gate_min_obs) * 100)}%` }} /></div>{n}/{ev.gate_min_obs}</div></td></tr>); })}</tbody></table></div>
            <div className="layout-2" style={{ padding: 14 }}>
              <div><b className="small">Brier per match över tid</b>{pkeys.slice(0, 3).map((k) => <Series key={k} label={MODEL_LABEL[k] || k} color={COLORS[k]} points={pros[k].series.map((p: any) => ({ x: p.date, y: p.brier }))} />)}</div>
              <div><b className="small">Kalibrering (frysta prognoser, 5 intervall)</b><Calibration series={pkeys.map((k) => ({ name: MODEL_LABEL[k] || k, color: COLORS[k] || "#ccc", bins: pros[k].calibration }))} /></div>
            </div>
            <div className="scroll-x" style={{ maxHeight: 420, overflow: "auto" }}><table className="t">
              <thead><tr><th>Datum</th><th>Match</th><th>Modell</th><th>Typ</th><th className="num">1 / X / 2</th><th>Utfall</th><th className="num">Mål prognos → utfall</th><th className="num">Hörnor</th><th className="num">Skott</th><th className="num">SOT</th></tr></thead>
              <tbody>{pkeys.flatMap((k) => pros[k].rows.map((r: any) => (
                <tr key={k + r.match_id} className="click" onClick={() => navigate(`match/${r.match_id}`)}>
                  <td className="nowrap small">{fmtDate(r.kickoff_utc)}</td><td className="nowrap">{r.home} – {r.away}</td><td className="small">{MODEL_LABEL[k] || k}</td>
                  <td>{r.kind === "late" ? <StatusBadge kind="err">sen</StatusBadge> : <StatusBadge kind={r.prematch_eligible ? "ok" : "warn"}>{r.kind}</StatusBadge>}</td>
                  <td className="num small">{r.p[0] == null ? "saknas" : r.p.map((x: number) => `${Math.round(x * 100)}`).join(" / ")}</td><td><b>{r.outcome}</b></td>
                  {METRICS.map(([mk]) => <td key={mk} className="num small">{r.pred[mk][0] == null ? "saknas" : `${num(r.pred[mk][0], 1)}–${num(r.pred[mk][1], 1)}`} → {r.actual[mk][0] ?? "?"}–{r.actual[mk][1] ?? "?"}</td>)}
                </tr>)))}</tbody></table></div>
          </>)}
      </Panel>
    </div>
  );
}
