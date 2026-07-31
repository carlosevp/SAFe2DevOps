export type Screen =
  | 'welcome'
  | 'integrations'
  | 'setup'
  | 'evidence'
  | 'workshop'
  | 'checkpoint'
  | 'remote-contributor'
  | 'admin-review'
  | 'results'
  | 'ai-settings'
  | 'enterprise-standards'

export type CoverageState = 'not-discussed' | 'partial' | 'sufficient' | 'clarify'

export interface Practice {
  id: string
  name: string
  domain: 'CE' | 'CI' | 'CD' | 'RoD'
  coverage: CoverageState
  aiScore?: number
  adminScore?: number
}

export interface EvidenceMetric {
  label: string
  value: string
  source: 'jira' | 'azdo'
  freshness: string
  trend?: 'up' | 'down' | 'neutral'
}
