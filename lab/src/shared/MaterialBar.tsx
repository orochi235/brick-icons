import { useId, type ReactNode } from 'react';
import { familyInk, materialOf, shade, type Material } from '@lab/shared/materials';
import '@lab/shared/MaterialBar.css';

const LID = 3;
const STEP = 2;
const STRIPE_PERIOD = 16;
const STRIPE_WIDTH = 9;

type Stop = [offset: number, color: string, opacity: number];

function frontStops({ color, finish, opacity }: Material): Stop[] {
  if (finish === 'metallic') {
    return [[0, shade(color, 0.02), 1], [0.4, shade(color, 0.14), 1],
            [0.75, shade(color, -0.06), 1], [1, shade(color, -0.16), 1]];
  }
  if (finish === 'trans') {
    // Brightened by opacity, not lightness: lightening turns orange to cream.
    return [[0, shade(color, 0.04), opacity],
            [0.45, shade(color, 0.08), Math.min(1, opacity + 0.3)],
            [0.6, shade(color, 0.056), Math.min(1, opacity + 0.2)],
            [1, shade(color, -0.06), opacity]];
  }
  return [[0, shade(color, 0.08), opacity], [0.3, shade(color, 0.03), opacity],
          [0.6, color, opacity], [1, shade(color, -0.18), opacity]];
}

function Gradient({ id, stops }: { id: string; stops: Stop[] }) {
  return (
    <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
      {stops.map(([offset, color, opacity]) => (
        <stop key={offset} offset={offset} stopColor={color} stopOpacity={opacity} />
      ))}
    </linearGradient>
  );
}

export function MaterialBar({ source, width, height, timedOut = false }: {
  source: string;
  width: number;
  height: number;
  /** The run stopped at its time limit, so the length is a limit, not a cost. */
  timedOut?: boolean;
}) {
  const id = `mb${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`;
  const material = materialOf(source);
  const x = 0.5;
  const y = 0.5;
  const w = Math.max(0, width - 1);
  const top = y + LID;
  const frontH = Math.max(0, height - 1 - LID);
  const step = Math.min(STEP, w / 4);
  const lid = `${x},${y} ${x + w - step},${y} ${x + w},${top} ${x},${top}`;
  const edge = material.stroke
    ? { stroke: material.stroke, strokeWidth: 1, strokeLinejoin: 'round' as const } : {};

  let body: ReactNode;
  if (timedOut) {
    body = (
      <g fill="none" stroke={familyInk(material)} strokeWidth={1.2} strokeDasharray="4 3">
        <polyline points={`${x},${y} ${x + w - step},${y} ${x + w},${top}`} />
        <rect x={x} y={top} width={w} height={frontH} />
      </g>
    );
  } else if (material.finish === 'print') {
    // Each top-face stripe starts where its front stripe meets the edge and
    // narrows with the face toward the far end.
    const ink = shade(material.color, 0.2);
    const back = (px: number) => x + (px - x) * (w ? (w - step) / w : 1);
    const front: ReactNode[] = [];
    const lidStripes: ReactNode[] = [];
    for (let x0 = x - Math.ceil(frontH / STRIPE_PERIOD + 1) * STRIPE_PERIOD;
         x0 < x + w + frontH; x0 += STRIPE_PERIOD) {
      const x1 = x0 + STRIPE_WIDTH;
      front.push(<polygon key={x0} points={
        `${x0},${top} ${x1},${top} ${x1 - frontH},${top + frontH} ${x0 - frontH},${top + frontH}`} />);
      lidStripes.push(<polygon key={x0} points={
        `${x0},${top} ${x1},${top} ${back(x1)},${y} ${back(x0)},${y}`} />);
    }
    body = (
      <>
        <defs>
          <clipPath id={`${id}-front`}><rect x={x} y={top} width={w} height={frontH} /></clipPath>
          <clipPath id={`${id}-lid`}><polygon points={lid} /></clipPath>
        </defs>
        <polygon points={lid} fill="#ffffff" />
        <rect x={x} y={top} width={w} height={frontH} fill="#ffffff" />
        <g clipPath={`url(#${id}-front)`} fill={ink}>{front}</g>
        <g clipPath={`url(#${id}-lid)`} fill={ink}>{lidStripes}</g>
        <polygon points={lid} fill="none" {...edge} />
        <rect x={x} y={top} width={w} height={frontH} fill="none" {...edge} />
      </>
    );
  } else {
    const trans = material.finish === 'trans';
    const pad = Math.min(4, w / 6);
    body = (
      <>
        <defs>
          <Gradient id={`${id}-fill`} stops={frontStops(material)} />
          {trans && (
            <>
              <Gradient id={`${id}-wash`} stops={
                [[0, '#ffffff', 0.75], [0.25, '#ffffff', 0.35], [1, '#ffffff', 0]]} />
              <Gradient id={`${id}-glow`} stops={[[0, shade(material.color, 0.3), 0],
                [0.6, shade(material.color, 0.3), 0.55], [1, shade(material.color, 0.3), 0]]} />
              <filter id={`${id}-soft`} x="-10%" y="-60%" width="120%" height="220%">
                <feGaussianBlur stdDeviation={1.4} />
              </filter>
              <clipPath id={`${id}-clip`}>
                <rect x={x} y={top} width={w} height={frontH} />
              </clipPath>
            </>
          )}
        </defs>
        <polygon points={lid} fill={shade(material.color, 0.34)}
                 fillOpacity={material.opacity} {...edge} />
        <rect x={x} y={top} width={w} height={frontH} fill={`url(#${id}-fill)`} {...edge} />
        {trans && (
          // Runs off the near end: the bar grows out of its axis, so that end
          // has no edge to show.
          <g clipPath={`url(#${id}-clip)`}>
            <g filter={`url(#${id}-soft)`}>
              <rect x={x - 6} y={top + 1} width={Math.max(0, w + 6 - pad)}
                    height={frontH * 0.6} fill={`url(#${id}-wash)`} />
              <rect x={x - 6} y={top + frontH * 0.55} width={Math.max(0, w + 6 - pad * 1.6)}
                    height={frontH * 0.38} fill={`url(#${id}-glow)`} />
            </g>
            <line x1={x} y1={top + 2} x2={x + w - pad} y2={top + 2} stroke="#ffffff"
                  strokeOpacity={0.6} strokeWidth={0.8} strokeLinecap="round" />
          </g>
        )}
      </>
    );
  }

  return (
    <svg className="material-bar" width={width} height={height}
         viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      {body}
    </svg>
  );
}
