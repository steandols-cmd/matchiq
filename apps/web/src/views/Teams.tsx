import { useEffect, useState } from "react";
import { api } from "../api";
import { navigate, type Route } from "../App";
import { fmtDate, fmtDay, fmtFull, fmtTime, num } from "../format";
import { Crest, ErrorBox, FormDots, Icon, LineupBadge, Loading, Panel, StatusBadge } from "../ui";

export function TeamsView({ id, route }: { id: number | null; route: Route }) {
  const [q, setQ] = useState(route.params.get("q") || "");
  const [list, setList] = useState<any[] | null>(null);
  const [onlyReview, setOnlyReview] = useState(route.params.get("granska") === "1");
  useEffect(() => {
    const t = setTimeout(() => api(`/teams?q=${encodeURIComponent(q)}`).then(setList).catch(() => setList([])), 200);
    return () => clearTimeout(t);
  }, [q]);
  const shown = (list || []).filter((t) => !onlyReview || t.needs_review);
  return (
    <div className="layout-side">
      <Panel title="Lag" icon={Icon.users()}>
        <div className="filters">
          <input className="in grow" placeholder="Sök lag eller alias…" value={q} onChange={(e) => setQ(e.target.value)} />
          <label className="row small"><input type="checkbox" checked={onlyReview} onChange={(e) => setOnlyReview(e.target.checked)} />Att granska</label>
        </div>
        <div style={{ maxHeight: "70vh", overflow: "auto" }}>
          {list === null ? <Loading /> : shown.map((t) => (
            <div key={t.id} className="mini-row" style={{ gridTemplateColumns: "28px minmax(0,1fr) auto", background: t.id === id ? "var(--panel-hi)" : undefined }} onClick={() => navigate(`lag/${t.id}`)}>
              <Crest name={t.name} c1={t.color_primary} c2={t.color_secondary} crest={t.crest_path} size={22} />
              <div className="teams"><div><b>{t.name}</b></div><div className="tiny muted">{t.country || ""} {t.domestic_competition_code || ""} · {t.matches} matcher</div></div>
              {t.needs_review ? <StatusBadge kind="warn">Granska</StatusBadge> : <span />}
            </div>))}
        </div>
      </Panel>
      {id ? <TeamDetail id={id} /> : <Panel title="Välj ett lag"><div className="empty">Välj ett lag i listan för att se form, statistik, spelare och startelvor.</div></Panel>}
    </div>
  );
}

function TeamDetail({ id }: { id: number }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<unknown>(null);
  const [alias, setAlias] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [rev, setRev] = useState(0);
  useEffect(() => { setD(null); api(`/teams/${id}`).then(setD).catch(setErr); }, [id, rev]);
  if (err) return <ErrorBox error={err} />;
  if (!d) return <Loading />;
  const t = d.team;
  const act = async (fn: () => Promise<any>, ok: string) => { try { await fn(); setMsg(ok); setRev((x) => x + 1); } catch (e: any) { setMsg(e.message); } };
  const metrics: [string, string][] = [["goals", "Mål"], ["shots", "Skott"], ["sot", "Skott på mål"], ["corners", "Hörnor"], ["xg", "xG"]];
  return (
    <div className="col" style={{ gap: 14 }}>
      <section className="panel hero" style={{ borderRadius: 14 }}>
        <div className="row" style={{ gap: 18 }}>
          <Crest name={t.name} c1={t.color_primary} c2={t.color_secondary} crest={t.crest_path} size={74} />
          <div>
            <div className="hero-comp" style={{ letterSpacing: 3 }}>{t.country || "Land okänt"} · {t.domestic_competition_code || "inhemsk liga okänd"}</div>
            <h1 style={{ fontSize: 32, color: "#fff" }}>{t.name}</h1>
            <div className="row" style={{ marginTop: 6 }}><FormDots form={d.form} /><span style={{ color: "#c4d6f2" }} className="small">senaste matcherna (alla tävlingar)</span></div>
          </div>
          {t.needs_review ? <div style={{ marginLeft: "auto" }}><StatusBadge kind="warn">Möjlig dubblett – granska</StatusBadge></div> : null}
        </div>
      </section>
      <div className="layout-2">
        <Panel title="Snitt för / emot (senaste 10 matcher med värde)" icon={Icon.bars()}>
          <table className="t"><thead><tr><th>Mått</th><th className="num">För</th><th className="num">Emot</th><th className="num">n</th></tr></thead>
            <tbody>{metrics.map(([k, l]) => { const a = d.averages[k]; return (
              <tr key={k}><td>{l}</td>{a?.n ? <><td className="num">{num(a.for)}</td><td className="num">{num(a.against)}</td></> : <td colSpan={2} className="num missing">saknas</td>}<td className="num muted">{a?.n ?? 0}</td></tr>); })}</tbody></table>
          <div className="small muted panel-pad">Saknade värden räknas inte med (inte som 0). n = antal matcher med värde.</div>
        </Panel>
        <Panel title="Kommande matcher" icon={Icon.cal()}>
          {d.upcoming.length === 0 ? <div className="empty">Inga kommande matcher i databasen.</div> : d.upcoming.map((m: any) => (
            <div key={m.id} className="mini-row" onClick={() => navigate(`match/${m.id}`)}>
              <div className="small">{fmtDay(m.kickoff_utc)} {fmtDate(m.kickoff_utc)}<br /><b>{fmtTime(m.kickoff_utc)}</b></div>
              <div className="teams"><div>{m.home}</div><div>{m.away}</div></div><span className="small muted">{m.comp}</span>
              <button className="go-btn">Gå till match</button></div>))}
        </Panel>
      </div>
      <Panel title="Startelvor (senaste)" icon={Icon.pitch()}>
        {d.lineups.length === 0 ? <div className="empty">Inga registrerade elvor. Elvor visas bara när en källa publicerat dem – inga antas.</div> : (
          <div className="lineup-cards">{d.lineups.slice(0, 6).map((l: any) => (
            <div key={l.id} className="lineup-list panel" style={{ padding: 10 }}>
              <div className="row small"><LineupBadge status={l.status} /><b className="nowrap" style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{l.home} – {l.away}</b></div>
              <div className="tiny muted" style={{ margin: "2px 0 6px" }}>{fmtFull(l.kickoff_utc)} · källa {l.source_id}{l.formation ? ` · ${l.formation}` : ""}</div>
              {l.players.map((p: any) => <div key={p.slot} className="pl"><span className="muted">{p.number ?? "·"}</span><span>{p.name}</span><span className="pos">{p.position || ""}</span></div>)}
            </div>))}</div>)}
      </Panel>
      <div className="layout-2">
        <PlayerHistory players={d.players} />
        <Panel title="Frånvaro" icon={Icon.shield()}>
          {d.absences.length === 0 ? <div className="empty">Inga registrerade skador eller avstängningar.</div> : (
            <table className="t"><tbody>{d.absences.map((a: any) => (
              <tr key={a.id}><td>{a.player_name}</td><td><StatusBadge kind={a.kind === "doubtful" ? "warn" : "err"}>{({ injury: "Ute", suspension: "Avstängd", doubtful: "Tveksam", other: "Övrigt" } as any)[a.kind]}</StatusBadge></td><td className="small muted">{a.kickoff_utc ? fmtDate(a.kickoff_utc) : ""} · {a.source_id}</td></tr>))}</tbody></table>)}
        </Panel>
      </div>
      <Panel title="Identitet, alias och källornas ID" icon={Icon.db()}>
        <div className="panel-pad col">
          <div className="small muted">Alias matchas exakt (skiftläge, accenter och punkter normaliseras). Likartade namn slås aldrig ihop automatiskt.</div>
          <div className="chips">{d.aliases.map((a: any) => <span key={a.id} className="chip" title={`kontext: ${a.context || "global"} · källa: ${a.source_id || "alla"} · ${a.origin}`}>{a.alias}{a.context ? <span className="tiny muted"> · {a.context}</span> : null}{a.source_id ? <span className="tiny muted"> · {a.source_id}</span> : null}</span>)}</div>
          <div className="small">Käll-ID: {d.source_ids.length ? d.source_ids.map((s: any) => `${s.source_id}:${s.source_team_id}`).join(", ") : "inga"}</div>
          <div className="row"><input className="in" placeholder="Nytt exakt alias" value={alias} onChange={(e) => setAlias(e.target.value)} />
            <button className="btn sm" onClick={() => act(() => api(`/teams/${id}/aliases`, { body: { alias } }), "Alias tillagt.")}>Lägg till alias</button>
            {t.needs_review ? <button className="btn sm" onClick={() => act(() => api(`/teams/${id}`, { method: "PATCH", body: { review_done: true } }), "Markerat som granskat (eget lag).")}>Bekräfta som eget lag</button> : null}
          </div>
          {t.needs_review && d.possible_duplicates.length > 0 && (
            <div className="callout warn"><span className="ic">{Icon.warn()}</span><div>
              <b>Möjliga dubbletter (förslag – slås inte ihop automatiskt):</b>
              {d.possible_duplicates.map((p: any) => (
                <div key={p.id} className="row small" style={{ marginTop: 4 }}>{p.name} <span className="muted">(gemensamt: {p.shared.join(", ")})</span>
                  <button className="btn sm" onClick={() => { if (window.confirm(`Slå ihop ${t.name} in i ${p.name}? Detta kan inte ångras.`)) act(() => api(`/teams/merge`, { body: { keep_id: p.id, drop_id: id } }).then(() => navigate(`lag/${p.id}`)), "Sammanslaget."); }}>Slå ihop in i {p.name}</button></div>))}
            </div></div>)}
          <div className="row small">
            <label className="row">Färg 1 <input type="color" value={t.color_primary || "#1d428a"} onChange={(e) => act(() => api(`/teams/${id}`, { method: "PATCH", body: { color_primary: e.target.value } }), "Färg sparad.")} /></label>
            <label className="row">Färg 2 <input type="color" value={t.color_secondary || "#ffffff"} onChange={(e) => act(() => api(`/teams/${id}`, { method: "PATCH", body: { color_secondary: e.target.value } }), "Färg sparad.")} /></label>
            <label className="btn sm">{Icon.upload(14)} Eget klubbmärke (png/svg)
              <input type="file" accept=".png,.svg,.jpg,.jpeg,.webp" style={{ display: "none" }} onChange={async (e) => {
                const f = e.target.files?.[0]; if (!f) return;
                act(async () => api(`/teams/${id}/crest`, { raw: await f.arrayBuffer(), headers: { "X-Filename": f.name, "Content-Type": "application/octet-stream" }, method: "POST" }), "Klubbmärke sparat lokalt.");
              }} /></label>
          </div>
          <div className="tiny muted">Appen bäddar inte in klubbarnas logotyper. Genererade sköldar visas tills du själv lägger in ett märke du har rätt att använda.</div>
          {msg && <div className="small">{msg}</div>}
        </div>
      </Panel>
    </div>
  );
}


function PlayerHistory({ players }: { players: any[] }) {
  const keys = Array.from(new Set(players.map((p) => `${p.comp} ${p.season}`)));
  const [sel, setSel] = useState<string>(keys[0] || "");
  const rows = players.filter((p) => `${p.comp} ${p.season}` === sel);
  return (
    <Panel title="Spelarhistorik per tävling och säsong" icon={Icon.users()} right={keys.length > 0 ? (
      <select className="in" value={sel} onChange={(e) => setSel(e.target.value)}>{keys.map((k) => <option key={k} value={k}>{k}</option>)}</select>) : null}>
      {players.length === 0 ? <div className="empty">Ingen spelarstatistik ännu. Den hämtas under Data &amp; källor → Hämta historik (Wyscout 2017/18, StatsBomb för utvalda matcher, API-Football med nyckel).</div> : (
        <div className="scroll-x" style={{ maxHeight: 460, overflow: "auto" }}><table className="t"><thead><tr><th>Spelare</th><th className="num">Matcher</th><th className="num">Från start</th><th className="num">Minuter</th><th className="num">Mål</th><th className="num">Skott</th><th className="num">På mål</th><th className="num">xG</th><th>Källa</th></tr></thead>
          <tbody>{rows.map((p: any) => <tr key={`${p.name}-${p.source_id}`}><td>{p.name}</td><td className="num">{p.apps}</td><td className="num">{p.starts ?? "–"}</td>
            <td className="num">{p.minutes == null ? "saknas" : `${Math.round(p.minutes)}${p.est ? "*" : ""}`}</td><td className="num">{p.goals ?? "–"}</td><td className="num">{p.shots ?? "–"}</td>
            <td className="num">{p.sot ?? "–"}</td><td className="num">{num(p.xg, 2)}</td><td className="tiny muted">{p.source_id}</td></tr>)}</tbody></table></div>)}
      <div className="tiny muted panel-pad">* Minuter uppskattade ur startelva och byten (Wyscout) eller händelseklockan (StatsBomb). Spelare som inte deltog har ingen rad. Saknade värden visas som – eller saknas, aldrig som 0.</div>
    </Panel>
  );
}
