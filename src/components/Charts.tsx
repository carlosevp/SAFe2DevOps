import { SAMPLE_PRACTICES } from '../data/sampleData'

interface RadarChartProps {
  dark: boolean
}

const DOMAINS = [
  { key: 'CE', label: 'Continuous\nExploration', score: 2.5, color: '#3b7dd8' },
  { key: 'CI', label: 'Continuous\nIntegration', score: 3.0, color: '#0f8b8d' },
  { key: 'CD', label: 'Continuous\nDeployment', score: 2.8, color: '#7c3aed' },
  { key: 'RoD', label: 'Release on\nDemand', score: 1.8, color: '#f59e0b' },
]

function polarToXY(angle: number, r: number, cx: number, cy: number) {
  const rad = ((angle - 90) * Math.PI) / 180
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
}

export function RadarChart({ dark }: RadarChartProps) {
  const cx = 160, cy = 160, maxR = 110, maxScore = 5
  const n = DOMAINS.length
  const gridLevels = [1, 2, 3, 4, 5]

  const gridColor = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.07)'
  const axisColor = dark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.1)'
  const textColor = dark ? '#7ea4d3' : '#64748b'

  const dataPoints = DOMAINS.map((d, i) => {
    const angle = (360 / n) * i
    const r = (d.score / maxScore) * maxR
    return polarToXY(angle, r, cx, cy)
  })

  const dataPath = dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ') + 'Z'

  return (
    <svg viewBox="0 0 320 320" className="w-full max-w-xs mx-auto" aria-label="Domain maturity radar chart">
      {/* Grid levels */}
      {gridLevels.map(level => {
        const pts = Array.from({ length: n }, (_, i) => {
          const angle = (360 / n) * i
          const r = (level / maxScore) * maxR
          return polarToXY(angle, r, cx, cy)
        })
        const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ') + 'Z'
        return (
          <path key={level} d={path} fill="none" stroke={gridColor} strokeWidth={1} />
        )
      })}

      {/* Axis lines */}
      {DOMAINS.map((_, i) => {
        const angle = (360 / n) * i
        const end = polarToXY(angle, maxR, cx, cy)
        return (
          <line key={i} x1={cx} y1={cy} x2={end.x} y2={end.y} stroke={axisColor} strokeWidth={1} />
        )
      })}

      {/* Data fill */}
      <path d={dataPath} fill="rgba(59,125,216,0.15)" stroke="#3b7dd8" strokeWidth={2} />

      {/* Domain score dots */}
      {dataPoints.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={5} fill={DOMAINS[i].color} stroke={dark ? '#0f1829' : '#fff'} strokeWidth={2} />
      ))}

      {/* Labels */}
      {DOMAINS.map((d, i) => {
        const angle = (360 / n) * i
        const labelR = maxR + 28
        const pos = polarToXY(angle, labelR, cx, cy)
        const lines = d.label.split('\n')
        return (
          <text key={i} x={pos.x} y={pos.y} textAnchor="middle" fill={textColor} fontSize={11} fontFamily="Inter, sans-serif">
            {lines.map((line, li) => (
              <tspan key={li} x={pos.x} dy={li === 0 ? '-0.4em' : '1.3em'}>{line}</tspan>
            ))}
            <tspan x={pos.x} dy="1.4em" fill={DOMAINS[i].color} fontWeight={600} fontSize={13}>{d.score.toFixed(1)}</tspan>
          </text>
        )
      })}

      {/* Center label */}
      <text x={cx} y={cy + 4} textAnchor="middle" fill={dark ? '#7ea4d3' : '#94a3b8'} fontSize={10} fontFamily="Inter, sans-serif">
        out of 5.0
      </text>
    </svg>
  )
}

interface HeatmapProps {
  dark: boolean
  adminView?: boolean
}

const scoreColors = [
  { max: 1, bg: '#fee2e2', text: '#991b1b', darkBg: '#3b1010', darkText: '#fca5a5' },
  { max: 2, bg: '#fef3c7', text: '#92400e', darkBg: '#3b2409', darkText: '#fcd34d' },
  { max: 3, bg: '#dbeafe', text: '#1e40af', darkBg: '#0f1d40', darkText: '#93c5fd' },
  { max: 4, bg: '#d1fae5', text: '#065f46', darkBg: '#092b20', darkText: '#6ee7b7' },
  { max: 5, bg: '#dcfce7', text: '#14532d', darkBg: '#0a3b1e', darkText: '#4ade80' },
]

function getScoreStyle(score: number | undefined, dark: boolean) {
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

export function HeatmapChart({ dark, adminView = false }: HeatmapProps) {
  const domains = ['CE', 'CI', 'CD', 'RoD']
  const borderColor = dark ? '#1e3358' : '#e2e8f0'

  return (
    <div className="w-full overflow-x-auto">
      <div style={{ minWidth: 480 }}>
        {domains.map(domain => {
          const practices = SAMPLE_PRACTICES.filter(p => p.domain === domain)
          return (
            <div key={domain} className="mb-4">
              <div
                className="text-xs font-semibold uppercase tracking-widest mb-2"
                style={{ color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}
              >
                {DOMAIN_LABELS[domain]}
              </div>
              <div className="grid grid-cols-4 gap-1.5">
                {practices.map(p => {
                  const score = adminView ? (p.adminScore ?? p.aiScore) : p.aiScore
                  const style = getScoreStyle(score, dark)
                  return (
                    <div
                      key={p.id}
                      className="rounded p-2.5 cursor-pointer transition-base"
                      style={{
                        background: style.bg,
                        border: `1px solid ${borderColor}`,
                        minHeight: 60,
                      }}
                      onMouseEnter={e => (e.currentTarget.style.opacity = '0.82')}
                      onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
                    >
                      <div className="text-xs font-medium leading-snug" style={{ color: style.text }}>
                        {p.name}
                      </div>
                      {score ? (
                        <div className="mt-1.5 text-lg font-bold font-mono" style={{ color: style.text }}>
                          {score}.0
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
