import type { Practice, EvidenceMetric } from '../types'

export const SAMPLE_PRACTICES: Practice[] = [
  { id: 'hyp', name: 'Hypothesis-Driven Development', domain: 'CE', coverage: 'sufficient', aiScore: 3, adminScore: 3 },
  { id: 'cdes', name: 'Continuous Design', domain: 'CE', coverage: 'partial', aiScore: 2, adminScore: 2 },
  { id: 'cex', name: 'Continuous Exploration', domain: 'CE', coverage: 'sufficient', aiScore: 3, adminScore: 3 },
  { id: 'cplan', name: 'Continuous Planning', domain: 'CE', coverage: 'partial', aiScore: 2 },
  { id: 'trunk', name: 'Trunk-Based Development', domain: 'CI', coverage: 'sufficient', aiScore: 4, adminScore: 4 },
  { id: 'ci', name: 'Continuous Integration', domain: 'CI', coverage: 'sufficient', aiScore: 3, adminScore: 3 },
  { id: 'tdd', name: 'Test-First Development', domain: 'CI', coverage: 'partial', aiScore: 2 },
  { id: 'nonfunc', name: 'Non-Functional Requirements', domain: 'CI', coverage: 'not-discussed' },
  { id: 'staging', name: 'Staging Environments', domain: 'CD', coverage: 'sufficient', aiScore: 3, adminScore: 3 },
  { id: 'cd', name: 'Continuous Deployment', domain: 'CD', coverage: 'sufficient', aiScore: 3, adminScore: 3 },
  { id: 'mon', name: 'Production Monitoring', domain: 'CD', coverage: 'not-discussed' },
  { id: 'recover', name: 'Recover from Failures', domain: 'CD', coverage: 'not-discussed' },
  { id: 'rod', name: 'Release on Demand', domain: 'RoD', coverage: 'partial', aiScore: 2 },
  { id: 'featflag', name: 'Feature Toggles', domain: 'RoD', coverage: 'partial', aiScore: 2 },
  { id: 'bizmon', name: 'Business Monitoring', domain: 'RoD', coverage: 'not-discussed' },
  { id: 'leanux', name: 'Lean UX Lifecycle', domain: 'RoD', coverage: 'not-discussed' },
]

export const SAMPLE_METRICS: EvidenceMetric[] = [
  { label: 'Jira items completed', value: '67', source: 'jira', freshness: '2 hours ago', trend: 'up' },
  { label: 'Bugs created', value: '11', source: 'jira', freshness: '2 hours ago', trend: 'neutral' },
  { label: 'Median cycle time', value: '6.4 days', source: 'jira', freshness: '2 hours ago', trend: 'down' },
  { label: 'Work in progress', value: '8 items', source: 'jira', freshness: '2 hours ago', trend: 'neutral' },
  { label: 'Pull requests completed', value: '44', source: 'azdo', freshness: '2 hours ago', trend: 'up' },
  { label: 'Median PR completion', value: '1.8 days', source: 'azdo', freshness: '2 hours ago', trend: 'down' },
  { label: 'Jira-key linkage', value: '89%', source: 'azdo', freshness: '2 hours ago', trend: 'up' },
  { label: 'Pipeline runs', value: '92', source: 'azdo', freshness: '2 hours ago', trend: 'up' },
  { label: 'Pipeline success rate', value: '84%', source: 'azdo', freshness: '2 hours ago', trend: 'neutral' },
  { label: 'Commit activity', value: '312 commits', source: 'azdo', freshness: '2 hours ago', trend: 'up' },
  { label: 'Active branches', value: '7', source: 'azdo', freshness: '2 hours ago', trend: 'neutral' },
  { label: 'Avg PR reviews', value: '1.9', source: 'azdo', freshness: '2 hours ago', trend: 'up' },
]

export const WORKSHOP_QUESTIONS = [
  {
    id: 'q1',
    text: 'Think of a recent representative change your team delivered. Walk us through how it moved from the initial need to production, and how the team knew it was successful.',
    topic: 'Delivery flow & feedback',
    why: 'This helps us understand your end-to-end delivery pipeline and how the team validates that change reached its intended goal.',
    evidence: 'Jira shows 67 completed items in the last 90 days. Azure DevOps shows 44 completed pull requests and regular pipeline activity with an 84% success rate.',
  },
  {
    id: 'q2',
    text: 'How does the team decide what to build next, and how does customer or user feedback influence that decision?',
    topic: 'Planning & discovery',
    why: 'Understanding how demand is shaped and validated tells us about your continuous exploration practices.',
    evidence: 'Cycle time averages 6.4 days. 11 bugs were created in the same period, suggesting a mix of enhancement and defect work.',
  },
  {
    id: 'q3',
    text: 'Describe what happens between a developer finishing a code change and it being ready to merge. Who\'s involved, and what checks run automatically?',
    topic: 'Integration & quality gates',
    why: 'Pull request and CI practices are strong indicators of integration maturity and team collaboration patterns.',
    evidence: '44 pull requests completed with a median completion time of 1.8 days and an average of 1.9 reviews per PR.',
  },
]

export const REMOTE_CONTRIBUTIONS = [
  {
    id: 'rc1',
    name: 'Priya Sharma',
    timestamp: '14 minutes ago',
    topic: 'Integration & quality gates',
    preview: 'We do require at least one approval before merge, and the build pipeline must pass. We added that rule about three months ago after a few regressions in prod.',
    status: 'pending',
  },
  {
    id: 'rc2',
    name: 'Tom Okeke',
    timestamp: '31 minutes ago',
    topic: 'Delivery flow & feedback',
    preview: 'Feature flags have been on the backlog for two sprints. We\'re not using them yet but we plan to.',
    status: 'included',
  },
]
