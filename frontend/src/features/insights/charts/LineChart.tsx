export type LineChartPoint = {
  label: string;
  value: number;
};

type LineChartProps = {
  data: LineChartPoint[];
  height?: number;
  color?: string;
  /** Fill the area under the line */
  filled?: boolean;
  formatValue?: (v: number) => string;
};

const PAD = { top: 16, right: 8, bottom: 36, left: 48 };
const VIEW_W = 480;

export function LineChart({
  data,
  height = 180,
  color = '#2563eb',
  filled = true,
  formatValue = String,
}: LineChartProps) {
  if (data.length === 0) {
    return <p className="py-8 text-center text-xs text-slate-400">No data</p>;
  }

  const maxV = Math.max(...data.map((d) => d.value), 1);
  const innerW = VIEW_W - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const innerBottom = PAD.top + innerH;

  const pts = data.map((d, i) => ({
    x: PAD.left + (data.length > 1 ? (i / (data.length - 1)) * innerW : innerW / 2),
    y: PAD.top + innerH - (d.value / maxV) * innerH,
    label: d.label,
  }));

  const linePath = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');
  // Area closes back along the baseline; pts is non-empty per the early return above.
  const areaPath = `${linePath} L${pts[pts.length - 1]!.x},${innerBottom} L${pts[0]!.x},${innerBottom} Z`;

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * maxV));
  const xStep = Math.max(1, Math.ceil(data.length / 8));

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${height}`}
      width="100%"
      height={height}
      role="img"
      aria-label="Line chart"
    >
      {yTicks.map((v) => {
        const y = PAD.top + innerH - (v / maxV) * innerH;
        return (
          <g key={v}>
            <line x1={PAD.left} y1={y} x2={PAD.left + innerW} y2={y} stroke="#e2e8f0" strokeWidth={1} />
            <text x={PAD.left - 6} y={y + 4} fontSize={10} textAnchor="end" fill="#94a3b8">
              {formatValue(v)}
            </text>
          </g>
        );
      })}

      {filled && <path d={areaPath} fill={color} fillOpacity={0.12} />}

      <path
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {pts.map((p) => (
        <circle key={p.label} cx={p.x} cy={p.y} r={3} fill={color} />
      ))}

      {pts.map((p, i) =>
        i % xStep === 0 || i === pts.length - 1 ? (
          <text
            key={`${p.label}-lbl`}
            x={p.x}
            y={innerBottom + 16}
            fontSize={10}
            textAnchor="middle"
            fill="#64748b"
          >
            {p.label}
          </text>
        ) : null
      )}

      <line
        x1={PAD.left}
        y1={PAD.top}
        x2={PAD.left}
        y2={innerBottom}
        stroke="#cbd5e1"
        strokeWidth={1}
      />
    </svg>
  );
}
