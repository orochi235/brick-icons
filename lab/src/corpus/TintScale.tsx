import { FloatingPanel } from '@weasel-js/labkit';
import { DEFAULT_PALETTE } from '@lab/corpus/palette';
import { formatScale, ramp, scaleAt, SCALE_IS_LOG, SCALE_LABEL, STEPS,
         type MeasuredMode, type RampName } from '@lab/corpus/tint';
import '@lab/corpus/TintScale.css';

/** Where the strip is labeled. The ends alone leave a log ramp looking
 *  linear; the midpoint is the tick that shows it is not. */
const TICKS = [0, 0.5, 1];

export interface TintScaleProps {
  mode: MeasuredMode;
  gradient: RampName;
}

/** What the wall's colors mean while a measured tint is on.
 *
 *  Read-only on purpose. Every row of `Legend` is also a filter, and the two
 *  sit on the same wall -- so a strip that looked clickable would promise a
 *  narrowing that does not exist. Nothing here takes focus or a handler.
 *
 *  It draws `STEPS` swatches rather than a CSS gradient because the ramp is
 *  quantised: a smooth strip would label bands the wall cannot produce.
 */
export function TintScale({ mode, gradient }: TintScaleProps) {
  const swatches = Array.from({ length: STEPS }, (_, i) => i / (STEPS - 1));
  const low = formatScale(mode, scaleAt(mode, 0));
  const high = formatScale(mode, scaleAt(mode, 1));

  return (
    <FloatingPanel anchor="bottom-right"
                   storageKey="brick-icons-lab.corpus-tint-scale"
                   className="corpus-tint-scale">
      <div className="corpus-tint-scale-head">
        <strong>{SCALE_LABEL[mode]}</strong>
        {SCALE_IS_LOG[mode] && (
          <span className="corpus-tint-scale-note">log</span>
        )}
      </div>
      {/* One image with one name: a screen reader gets the range in a
          sentence rather than eight unlabeled swatches. */}
      <div className="corpus-tint-scale-strip" role="img"
           aria-label={`${SCALE_LABEL[mode]}, ${low} to ${high}`
                       + (SCALE_IS_LOG[mode] ? ', logarithmic' : '')}>
        {swatches.map((t) => (
          <span key={t} className="corpus-tint-scale-swatch"
                style={{ background: ramp(t, gradient) }} />
        ))}
      </div>
      <div className="corpus-tint-scale-ticks" aria-hidden="true">
        {TICKS.map((t) => (
          <span key={t}>{formatScale(mode, scaleAt(mode, t))}</span>
        ))}
      </div>
      <div className="corpus-tint-scale-absent">
        <span className="corpus-tint-scale-swatch"
              style={{ background: DEFAULT_PALETTE.unmatched.fill }} />
        <span>not measured</span>
      </div>
    </FloatingPanel>
  );
}
