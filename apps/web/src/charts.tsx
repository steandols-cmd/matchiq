// Enkla SVG-diagram (inga externa bibliotek).
import { num, pct } from "./format";

export function BarCompare({ labels, a, b, aLabel, bLabel }: { labels: string[]; a: number[]; b: number[]; aLabel: string; bLabel: string }) {
  const W = 520, H = 220, pad = 34, gw = (W - pad * 2) / labels.length, bw = Math.min(46, gw / 3);
  const y = (v: number) => H - pad - v * (H - pad * 2);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`${aLabel} mot ${bLabel}`}>
      {[0, 0.2, 0.4, 0.6, 0.8].map((t) => (
        <g key={t}><line x1={pad} x2={W - pad} y1={y(t)} y2={y(t)} stroke="currentColor" opacity={0.12} />
          <text x={pad - 6} y={y(t) + 4} fontSize="10" textAnchor="end" fill="currentColor" opacity={0.6}>{Math.round(t * 100)}%</text></g>
      ))}
      {labels.map((l, i) => {
        const x0 = pad + i * gw + gw / 2 - bw - 3;
        return (
          <g key={l}>
            <rect x={x0} y={y(a[i])} width={bw} height={H - pad - y(a[i])} rx="3" fill="#22c98a" />
            <rect x={x0 + bw + 6} y={y(b[i])} width={bw} height={H - pad - y(b[i])} rx="3" fill="#3b8cf0" />
            <text x={x0 + bw / 2} y={y(a[i]) - 4} fontSize="11" textAnchor="middle" fill="currentColor">{pct(a[i])}</text>
            <text x={x0 + bw * 1.5 + 6} y={y(b[i]) - 4} fontSize="11" textAnchor="middle" fill="currentColor">{pct(b[i])}</text>
            <text x={pad + i * gw + gw / 2} y={H - 12} fontSize="12" textAnchor="middle" fill="currentColor">{l}</text>
          </g>
        );
      })}
      <g fontSize="11" fill="currentColor"><rect x={W - 220} y={6} width={10} height={10} fill="#22c98a" /><text x={W - 205} y={15}>{aLabel}</text>
        <rect x={W - 110} y={6} width={10} height={10} fill="#3b8cf0" /><text x={W - 95} y={15}>{bLabel}</text></g>
    </svg>
  );
}

export interface CalBin { lo: number; hi: number; n: number; mean_pred: number | null; obs_freq: number | null }

export function Calibration({ series }: { series: { name: string; color: string; bins: CalBin[] }[] }) {
  const W = 420, H = 320, pad = 40;
  const sx = (v: number) => pad + v * (W - pad * 1.6);
  const sy = (v: number) => H - pad - v * (H - pad * 1.8);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: 560 }} role="img" aria-label="Kalibreringsdiagram">
      {[0, 0.2, 0.4, 0.6, 0.8, 1].map((t) => (
        <g key={t} opacity={0.6}>
          <line x1={sx(0)} x2={sx(1)} y1={sy(t)} y2={sy(t)} stroke="currentColor" opacity={0.15} />
          <text x={sx(0) - 6} y={sy(t) + 4} fontSize="10" textAnchor="end" fill="currentColor">{Math.round(t * 100)}%</text>
          <text x={sx(t)} y={sy(0) + 14} fontSize="10" textAnchor="middle" fill="currentColor">{Math.round(t * 100)}%</text>
        </g>
      ))}
      <line x1={sx(0)} y1={sy(0)} x2={sx(1)} y2={sy(1)} stroke="currentColor" strokeDasharray="4 4" opacity={0.5} />
      <text x={sx(0.5)} y={H - 4} fontSize="11" textAnchor="middle" fill="currentColor">Prognostiserad sannolikhet</text>
      <text x={12} y={sy(0.5)} fontSize="11" textAnchor="middle" fill="currentColor" transform={`rotate(-90 12 ${sy(0.5)})`}>Observerad frekvens</text>
      {series.map((s, si) => {
        const pts = s.bins.filter((b) => b.n > 0 && b.mean_pred != null && b.obs_freq != null);
        return (
          <g key={s.name}>
            <polyline fill="none" stroke={s.color} strokeWidth="2" points={pts.map((b) => `${sx(b.mean_pred!)},${sy(b.obs_freq!)}`).join(" ")} />
            {pts.map((b, i) => <circle key={i} cx={sx(b.mean_pred!)} cy={sy(b.obs_freq!)} r={Math.min(9, 2.5 + Math.sqrt(b.n) / 3)} fill={s.color} opacity={0.85}><title>{`${s.name}: ${num(b.mean_pred! * 100, 0)}% → ${num(b.obs_freq! * 100, 0)}% (n=${b.n})`}</title></circle>)}
            <g transform={`translate(${pad + 6}, ${14 + si * 16})`}><rect width="10" height="10" fill={s.color} /><text x="15" y="9" fontSize="11" fill="currentColor">{s.name}</text></g>
          </g>
        );
      })}
    </svg>
  );
}

export function Series({ points, color = "#22c98a", label }: { points: { x: string; y: number }[]; color?: string; label: string }) {
  const W = 520, H = 160, pad = 30;
  if (!points.length) return <div className="empty">Inga datapunkter ännu.</div>;
  const max = Math.max(1, ...points.map((p) => p.y));
  const sx = (i: number) => pad + (points.length === 1 ? 0.5 : i / (points.length - 1)) * (W - pad * 2);
  const sy = (v: number) => H - pad - (v / max) * (H - pad * 2);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: 640 }} role="img" aria-label={label}>
      <line x1={pad} x2={W - pad} y1={sy(0)} y2={sy(0)} stroke="currentColor" opacity={0.2} />
      <polyline fill="none" stroke={color} strokeWidth="2" points={points.map((p, i) => `${sx(i)},${sy(p.y)}`).join(" ")} />
      {points.map((p, i) => <circle key={i} cx={sx(i)} cy={sy(p.y)} r="3" fill={color}><title>{`${p.x}: ${num(p.y, 3)}`}</title></circle>)}
      <text x={pad} y={14} fontSize="11" fill="currentColor" opacity={0.7}>{label}</text>
    </svg>
  );
}
