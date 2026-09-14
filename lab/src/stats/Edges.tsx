import { wallHashString } from '@lab/corpus/wallHash';
import type { Edges } from '@lab/stats/types';

const BIN_LABEL: Record<string, string> = {
  '0': 'no gaps', '1-2': '1–2 gaps', '3-5': '3–5 gaps', '6-20': '6–20 gaps',
  '21+': '21+ gaps', none: 'nothing declared',
};

const nameOf = (bin: string) => BIN_LABEL[bin] ?? bin;
const share = (n: number, of: number) => (of === 0 ? 0 : (100 * n) / of);

/** Where each slot's drawings leave out edges their part files declare. */
export function EdgeScores({ edges }: { edges: Edges }) {
  if (edges.slots.length === 0) {
    return <p className="stats-empty">no drawing in this set has been scored</p>;
  }
  const bins = [...edges.slots[0]!.bins.map((b) => b.label), 'none'];
  return (
    <div className="stats-edges">
      <ul className="stats-legend">
        {bins.map((bin) => (
          <li key={bin}>
            <span className="stats-swatch" data-bin={bin} aria-hidden="true" />
            {nameOf(bin)}
          </li>
        ))}
      </ul>
      <div className="stats-bars">
        {edges.slots.map((slot) => {
          const segs = [...slot.bins, { label: 'none', n: slot.none_declared }];
          const gapped = slot.bins.filter((b) => b.label !== '0')
            .reduce((total, b) => total + b.n, 0);
          const said = segs.map((s) => `${s.n.toLocaleString()} ${nameOf(s.label)}`);
          return (
            <div key={slot.source} className="stats-bar-row">
              <span className="stats-bar-name">{slot.source}</span>
              <div className="stats-bar" role="img"
                   aria-label={`${slot.source}: ${said.join(', ')}`}>
                {segs.map((s, i) => (s.n === 0 ? null : (
                  // Only the width is inline: it is computed per datum.
                  <span key={s.label} className="stats-seg" data-bin={s.label}
                        style={{ width: `${share(s.n, slot.scored)}%` }}
                        title={said[i]} />
                )))}
              </div>
              <span className="stats-bar-value">
                {share(gapped, slot.scored).toFixed(1)}%
                <span className="stats-muted"> with gaps</span>
              </span>
            </div>
          );
        })}
      </div>
      <table>
        <thead>
          <tr><th>slot</th><th className="stats-num">scored</th>
              <th className="stats-num">no gaps</th>
              <th className="stats-num">with gaps</th>
              <th className="stats-num">nothing declared</th></tr>
        </thead>
        <tbody>
          {edges.slots.map((slot) => {
            const clean = slot.bins.find((b) => b.label === '0')?.n ?? 0;
            const gapped = slot.scored - slot.none_declared - clean;
            return (
              <tr key={slot.source}>
                <td>{slot.source}</td>
                <td className="stats-num">{slot.scored.toLocaleString()}</td>
                <td className="stats-num">{clean.toLocaleString()}</td>
                <td className="stats-num">{gapped.toLocaleString()}</td>
                <td className="stats-num">{slot.none_declared.toLocaleString()}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <h3>Most gaps</h3>
      <table className="stats-edges-worst">
        <thead>
          <tr><th>part</th><th>title</th><th>slot</th>
              <th className="stats-num">gaps</th>
              <th className="stats-num">uncovered</th></tr>
        </thead>
        <tbody>
          {edges.worst.map((w) => (
            <tr key={`${w.source}-${w.part}`}>
              <td>
                <a href={`/corpus${wallHashString({ source: w.source, part: w.part })}`}>
                  {w.part}
                </a>
              </td>
              <td>{w.title}</td>
              <td>{w.source}</td>
              <td className="stats-num">{w.gaps.toLocaleString()}</td>
              <td className="stats-num">{w.uncovered.toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
