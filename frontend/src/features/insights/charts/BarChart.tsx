export type BarChartPoint = {
  label: string;
  value: number;
};

type BarChartProps = {
  data: BarChartPoint[];
  height?: number;
  color?: string;
  formatValue?: (v: number) => string;
};

const PAD = { top: 16, right: 8, bottom: 36, left: 48 };
const VIEW_W = 480;

export function BarChart({
  data,
  height = 180,
  color = '#2563eb',
  formatValue = String,
}: BarChartProps) {
  if (data.length === 0) {
    return <p className="py-8 text-center text-xs text-slate-400">No data</p>;
  }

  const maxV = Math.max(...data.map((d) => d.value), 1);
  const innerW = VIEW_W - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const slotW = innerW / data.length;
  const barW = Math.max(4, slotW * 0.6);
  const innerBottom = PAD.top + innerH;

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * maxV));

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${height}`}
      width="100%"
      height={height}
      role="img"
      aria-label="Bar chart"
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

      {data.map((d, i) => {
        const barH = Math.max(0, (d.value / maxV) * innerH);
        const x = PAD.left + i * slotW + (slotW - barW) / 2;
        const y = innerBottom - barH;
        return (
          <g key={d.label}>
            <rect x={x} y={y} width={barW} height={barH} fill={color} rx={2} />
            <text
              x={x + barW / 2}
              y={innerBottom + 16}
              fontSize={10}
              textAnchor="middle"
              fill="#64748b"
            >
              {d.label}
            </text>
          </g>
        );
      })}

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
