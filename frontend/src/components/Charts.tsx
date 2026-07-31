export type RadarPoint = {
  domain_key: string
  domain_short_name: string
  domain_name: string
  score: number
  weight: number
}

export type HeatmapCell = {
  practice_key: string
  practice_name: string
  domain_short_name: string
  score: number | null
  named_maturity_level?: string | null
}

interface RadarChartProps {
  dark: boolean
  data?: RadarPoint[]
  summary?: string
}

const FALLBACK_RADAR: RadarPoint[] = [
  { domain_key: 'continuous_exploration', domain_short_name: 'CE', domain_name: 'Continuous Exploration', score: 2.5, weight: 1 },
  { domain_key: 'continuous_integration', domain_short_name: 'CI', domain_name: 'Continuous Integration', score: 3.0, weight: 1 },
  { domain_key: 'continuous_deployment', domain_short_name: 'CD', domain_name: 'Continuous Deployment', score: 2.8, weight: 1 },
  { domain_key: 'release_on_demand', domain_short_name: 'RoD', domain_name: 'Release on Demand', score: 1.8, weight: 1 },
]

const DOMAIN_COLORS: Record<string, string> = {
  CE: '#3b7dd8',
  CI: '#0f8b8d',
  CD: '#7c3aed',
  RoD: '#f59e0b',
}

function polarToXY(angle: number, r: number, cx: number, cy: number) {
  const rad = ((angle - 90) * Math.PI) / 180
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
}

export function RadarChart({ dark, data, summary }: RadarChartProps) {
  const domains = (data && data.length ? data : FALLBACK_RADAR).map(d => ({
    key: d.domain_short_name,
    label: d.domain_name.replace(' ', '\n'),
    score: d.score,
    color: DOMAIN_COLORS[d.domain_short_name] || '#3b7dd8',
  }))
  const cx = 160, cy = 160, maxR = 110, maxScore = 5
  const n = domains.length
  const gridLevels = [1, 2, 3, 4, 5]
  const gridColor = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.07)'
  const axisColor = dark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.1)'
  const textColor = dark ? '#7ea4d3' : '#64748b'
  const dataPoints = domains.map((d, i) => {
    const angle = (360 / n) * i
    const r = (d.score / maxScore) * maxR
    return polarToXY(angle, r, cx, cy)
  })
  const dataPath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ') + 'Z'
  const srSummary =
    summary ||
    `Radar chart of domain maturity scores: ${domains.map(d => `${d.key} ${d.score.toFixed(1)}`).join(', ')} out of 5.0.`

  return (
    <div>
      <svg
        viewBox="0 0 320 320"
        className="w-full max-w-xs mx-auto print:max-w-none"
        role="img"
        aria-label={srSummary}
      >
        <title>{srSummary}</title>
        {gridLevels.map(level => {
          const pts = Array.from({ length: n }, (_, i) => {
            const angle = (360 / n) * i
            const r = (level / maxScore) * maxR
            return polarToXY(angle, r, cx, cy)
          })
          const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ') + 'Z'
          return <path key={level} d={path} fill="none" stroke={gridColor} strokeWidth={1} />
        })}
        {domains.map((_, i) => {
          const angle = (360 / n) * i
          const end = polarToXY(angle, maxR, cx, cy)
          return <line key={i} x1={cx} y1={cy} x2={end.x} y2={end.y} stroke={axisColor} strokeWidth={1} />
        })}
        <path d={dataPath} fill="rgba(59,125,216,0.15)" stroke="#3b7dd8" strokeWidth={2} />
        {dataPoints.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={5} fill={domains[i].color} stroke={dark ? '#0f1829' : '#fff'} strokeWidth={2} />
        ))}
        {domains.map((d, i) => {
          const angle = (360 / n) * i
          const pos = polarToXY(angle, maxR + 28, cx, cy)
          const lines = d.label.split('\n')
          return (
            <text key={i} x={pos.x} y={pos.y} textAnchor="middle" fill={textColor} fontSize={11}>
              {lines.map((line, li) => (
                <tspan key={li} x={pos.x} dy={li === 0 ? '-0.4em' : '1.3em'}>{line}</tspan>
              ))}
              <tspan x={pos.x} dy="1.4em" fill={domains[i].color} fontWeight={600} fontSize={13}>{d.score.toFixed(1)}</tspan>
            </text>
          )
        })}
        <text x={cx} y={cy + 4} textAnchor="middle" fill={dark ? '#7ea4d3' : '#94a3b8'} fontSize={10}>
          out of 5.0
        </text>
      </svg>
      <p className="sr-only">{srSummary}</p>
    </div>
  )
}

interface HeatmapProps {
  dark: boolean
  adminView?: boolean
  cells?: HeatmapCell[]
  summary?: string
}

const scoreColors = [
  { max: 1, bg: '#fee2e2', text: '#991b1b', darkBg: '#3b1010', darkText: '#fca5a5' },
  { max: 2, bg: '#fef3c7', text: '#92400e', darkBg: '#3b2409', darkText: '#fcd34d' },
  { max: 3, bg: '#dbeafe', text: '#1e40af', darkBg: '#0f1d40', darkText: '#93c5fd' },
  { max: 4, bg: '#d1fae5', text: '#065f46', darkBg: '#092b20', darkText: '#6ee7b7' },
  { max: 5, bg: '#dcfce7', text: '#14532d', darkBg: '#0a3b1e', darkText: '#4ade80' },
]

function getScoreStyle(score: number | null | undefined, dark: boolean) {
  if (!score) return { bg: dark ? '#1a2540' : '#f1f5f9', text: dark ? '#475569' : '#94a3b8' }
  const tier = scoreColors.find(c => score <= c.max) || scoreColors[scoreColors.length - 1]
  return { bg: dark ? tier.darkBg : tier.bg, text: dark ? tier.darkText : tier.text }
}

const DOMAIN_LABELS: Record<string, string> = {
  CE: 'Continuous Exploration',
  CI: 'Continuous Integration',
  CD: 'Continuous Deployment',
  RoD: 'Release on Demand',
}

export function HeatmapChart({ dark, cells, summary }: HeatmapProps) {
  const domains = ['CE', 'CI', 'CD', 'RoD']
  const borderColor = dark ? '#1e3358' : '#e2e8f0'
  const data = cells && cells.length
    ? cells
    : domains.flatMap(domain =>
        Array.from({ length: 4 }, (_, i) => ({
          practice_key: `${domain}-${i}`,
          practice_name: `Practice ${i + 1}`,
          domain_short_name: domain,
          score: null as number | null,
        })),
      )
  const srSummary =
    summary ||
    `Heatmap of sixteen practice scores. ${data.filter(c => c.score != null).length} practices scored.`

  return (
    <div className="w-full overflow-x-auto" role="img" aria-label={srSummary}>
      <p className="sr-only">{srSummary}</p>
      <div style={{ minWidth: 480 }}>
        {domains.map(domain => {
          const practices = data.filter(p => p.domain_short_name === domain)
          return (
            <div key={domain} className="mb-4">
              <div className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--muted-foreground)' }}>
                {DOMAIN_LABELS[domain] || domain}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
                {practices.map(p => {
                  const style = getScoreStyle(p.score, dark)
                  return (
                    <div
                      key={p.practice_key}
                      className="rounded p-2.5 transition-base print:break-inside-avoid"
                      style={{ background: style.bg, border: `1px solid ${borderColor}`, minHeight: 60 }}
                    >
                      <div className="text-xs font-medium leading-snug" style={{ color: style.text }}>
                        {p.practice_name}
                      </div>
                      {p.score != null ? (
                        <div className="mt-1.5 text-lg font-bold font-mono" style={{ color: style.text }}>
                          {Number(p.score).toFixed(1)}
                        </div>
                      ) : (
                        <div className="mt-1.5 text-xs" style={{ color: dark ? '#475569' : '#cbd5e1' }}>
                          Not scored
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
