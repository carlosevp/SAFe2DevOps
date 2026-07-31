import { useEffect, useMemo, useState } from 'react'
import { Copy, Download, Plus, Power, Trash2, Upload, X } from 'lucide-react'
import {
  activateEnterpriseStandard,
  createEnterpriseStandard,
  deactivateEnterpriseStandard,
  deleteEnterpriseStandard,
  duplicateEnterpriseStandard,
  exportEnterpriseStandards,
  importEnterpriseStandards,
  listEnterpriseStandards,
  updateEnterpriseStandard,
  type EnterpriseStandard,
  type EnterpriseStandardInput,
} from '../lib/api'
import type { Screen } from '../types'

interface Props {
  dark: boolean
  onNavigate: (s: Screen) => void
}

const PRACTICE_KEYS = [
  'collaborate_research',
  'hypothesize',
  'architect',
  'synthesize',
  'develop',
  'build',
  'test_end_to_end',
  'verify',
  'stage',
  'deploy',
  'monitor',
  'respond',
  'stabilize',
  'release',
  'measure',
  'learn',
]

const APPLICABILITY_FIELDS = [
  'primary_technology',
  'application_type',
  'current_platform',
  'target_platform',
  'hosting_location',
  'customer_exposure',
  'lifecycle_stage',
  'application_has_secrets',
  'uses_cicd',
  'custom_context_tag',
]

const OPERATORS = ['equals', 'not_equals', 'contains', 'in', 'is_true', 'is_false']

const emptyDraft = (): EnterpriseStandardInput => ({
  stable_key: '',
  title: '',
  category: 'Delivery',
  description: '',
  requirement_level: 'preferred',
  active: true,
  applicability_mode: 'always',
  mapped_practice_keys: [],
  primary_interview_guidance: '',
  follow_up_guidance: '',
  evidence_expectations: '',
  recommendation_when_unmet: '',
  display_order: 100,
  conditions: [],
})

export default function EnterpriseStandards({ dark, onNavigate }: Props) {
  const [items, setItems] = useState<EnterpriseStandard[]>([])
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [activeFilter, setActiveFilter] = useState<'all' | 'true' | 'false'>('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState<EnterpriseStandardInput>(emptyDraft())
  const [showEditor, setShowEditor] = useState(false)
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'

  async function reload() {
    setLoading(true)
    try {
      const rows = await listEnterpriseStandards({
        search: search || undefined,
        category: category || undefined,
        active: activeFilter === 'all' ? undefined : activeFilter === 'true',
      })
      setItems(rows)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load standards')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void reload()
  }, [search, category, activeFilter])

  const categories = useMemo(
    () => Array.from(new Set(items.map(i => i.category))).sort(),
    [items],
  )

  function openCreate() {
    setEditingId(null)
    setDraft(emptyDraft())
    setShowEditor(true)
  }

  function openEdit(row: EnterpriseStandard) {
    setEditingId(row.id)
    setDraft({
      stable_key: row.stable_key,
      title: row.title,
      category: row.category,
      description: row.description,
      requirement_level: row.requirement_level,
      active: row.active,
      applicability_mode: row.applicability_mode,
      mapped_practice_keys: [...row.mapped_practice_keys],
      primary_interview_guidance: row.primary_interview_guidance,
      follow_up_guidance: row.follow_up_guidance,
      evidence_expectations: row.evidence_expectations,
      recommendation_when_unmet: row.recommendation_when_unmet,
      display_order: row.display_order,
      conditions: row.conditions.map(c => ({
        field: c.field,
        operator: c.operator,
        value: c.value,
        logical_group: c.logical_group,
      })),
    })
    setShowEditor(true)
  }

  async function saveDraft() {
    try {
      if (editingId) {
        const { stable_key: _k, ...rest } = draft
        await updateEnterpriseStandard(editingId, rest)
      } else {
        await createEnterpriseStandard(draft)
      }
      setShowEditor(false)
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    }
  }

  async function handleImport(file: File) {
    try {
      const text = await file.text()
      const parsed = JSON.parse(text) as { standards?: EnterpriseStandardInput[] } | EnterpriseStandardInput[]
      const standards = Array.isArray(parsed) ? parsed : parsed.standards || []
      await importEnterpriseStandards(standards)
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    }
  }

  async function handleExport() {
    const bundle = await exportEnterpriseStandards()
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'enterprise-standards.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--background)' }}>
      <div className="max-w-5xl mx-auto px-5 py-8">
        <div className="flex items-center gap-2 text-xs font-medium mb-3" style={{ color: 'var(--muted-foreground)' }}>
          <button onClick={() => onNavigate('welcome')} className="hover:underline">Admin</button>
          <span>/</span>
          <span>Enterprise Standards</span>
        </div>
        <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
          <div>
            <h1 className="text-2xl font-semibold mb-1" style={{ color: 'var(--foreground)' }}>Enterprise Standards</h1>
            <p className="text-sm" style={{ color: 'var(--muted-foreground)' }}>
              Preferred tools, platforms, and delivery practices that enrich the adaptive interview without changing SAFe maturity scores.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => void handleExport()} className="flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg" style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}>
              <Download size={14} /> Export
            </button>
            <label className="flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg cursor-pointer" style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}>
              <Upload size={14} /> Import
              <input type="file" accept=".json,.yaml,.yml,application/json" className="hidden" onChange={e => {
                const file = e.target.files?.[0]
                if (file) void handleImport(file)
              }} />
            </label>
            <button onClick={openCreate} className="flex items-center gap-1.5 text-sm px-3 py-2 rounded-lg font-semibold" style={{ background: 'var(--primary)', color: '#fff' }}>
              <Plus size={14} /> Create standard
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 text-sm rounded-lg px-3 py-2" style={{ background: dark ? '#3f1d1d' : '#fef2f2', color: dark ? '#fca5a5' : '#991b1b' }}>
            {error}
          </div>
        )}

        <div className="grid md:grid-cols-3 gap-3 mb-5">
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search title, key, or category"
            className="rounded-lg px-3 py-2.5 text-sm outline-none"
            style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}`, color: 'var(--foreground)' }}
          />
          <select
            value={category}
            onChange={e => setCategory(e.target.value)}
            className="rounded-lg px-3 py-2.5 text-sm outline-none"
            style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}`, color: 'var(--foreground)' }}
          >
            <option value="">All categories</option>
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <select
            value={activeFilter}
            onChange={e => setActiveFilter(e.target.value as 'all' | 'true' | 'false')}
            className="rounded-lg px-3 py-2.5 text-sm outline-none"
            style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}`, color: 'var(--foreground)' }}
          >
            <option value="all">Active and inactive</option>
            <option value="true">Active only</option>
            <option value="false">Inactive only</option>
          </select>
        </div>

        <div className="space-y-3">
          {loading && <p className="text-sm" style={{ color: 'var(--muted-foreground)' }}>Loading standards…</p>}
          {!loading && items.length === 0 && (
            <p className="text-sm" style={{ color: 'var(--muted-foreground)' }}>No standards match the current filters.</p>
          )}
          {items.map(row => (
            <div key={row.id} className="rounded-xl p-4" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div>
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <h3 className="font-semibold text-sm" style={{ color: 'var(--foreground)' }}>{row.title}</h3>
                    <span className="text-[11px] px-2 py-0.5 rounded" style={{ background: 'var(--muted)', color: 'var(--muted-foreground)' }}>{row.category}</span>
                    <span className="text-[11px] px-2 py-0.5 rounded" style={{ background: dark ? '#0f1d40' : '#eef3fa', color: 'var(--primary)' }}>{row.requirement_level}</span>
                    <span className="text-[11px] px-2 py-0.5 rounded" style={{ background: row.active ? '#d1fae5' : 'var(--muted)', color: row.active ? '#065f46' : 'var(--muted-foreground)' }}>
                      {row.active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  <p className="text-xs mb-2" style={{ color: 'var(--muted-foreground)' }}>
                    {row.stable_key} · Updated {new Date(row.updated_at).toLocaleDateString()}
                  </p>
                  <p className="text-xs" style={{ color: 'var(--muted-foreground)' }}>
                    SAFe: {row.mapped_practice_keys.join(', ') || '—'}
                  </p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <button onClick={() => openEdit(row)} className="text-xs px-2.5 py-1.5 rounded-lg" style={{ background: 'var(--muted)', color: 'var(--foreground)' }}>Edit</button>
                  <button
                    onClick={() => void duplicateEnterpriseStandard(row.id).then(reload)}
                    className="text-xs px-2.5 py-1.5 rounded-lg flex items-center gap-1"
                    style={{ background: 'var(--muted)', color: 'var(--foreground)' }}
                  >
                    <Copy size={11} /> Duplicate
                  </button>
                  <button
                    onClick={() => void (row.active ? deactivateEnterpriseStandard(row.id) : activateEnterpriseStandard(row.id)).then(reload)}
                    className="text-xs px-2.5 py-1.5 rounded-lg flex items-center gap-1"
                    style={{ background: 'var(--muted)', color: 'var(--foreground)' }}
                  >
                    <Power size={11} /> {row.active ? 'Deactivate' : 'Activate'}
                  </button>
                  <button
                    disabled={row.referenced}
                    onClick={() => {
                      if (row.referenced) return
                      void deleteEnterpriseStandard(row.id).then(reload).catch(err => setError(err instanceof Error ? err.message : 'Delete failed'))
                    }}
                    className="text-xs px-2.5 py-1.5 rounded-lg flex items-center gap-1"
                    style={{ background: dark ? '#3f1d1d' : '#fef2f2', color: dark ? '#fca5a5' : '#991b1b', opacity: row.referenced ? 0.45 : 1 }}
                    title={row.referenced ? 'Cannot delete a referenced standard' : 'Delete'}
                  >
                    <Trash2 size={11} /> Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {showEditor && (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto px-4 py-8" style={{ background: 'rgba(15,23,42,0.55)' }}>
          <div className="w-full max-w-2xl rounded-xl p-5" style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold" style={{ color: 'var(--foreground)' }}>{editingId ? 'Edit standard' : 'Create standard'}</h2>
              <button onClick={() => setShowEditor(false)} style={{ color: 'var(--muted-foreground)' }}><X size={16} /></button>
            </div>
            <div className="space-y-3">
              <div className="grid md:grid-cols-2 gap-3">
                <Field label="Title">
                  <input value={draft.title} onChange={e => setDraft(d => ({ ...d, title: e.target.value }))} className="field" />
                </Field>
                <Field label="Stable key">
                  <input
                    value={draft.stable_key}
                    disabled={Boolean(editingId)}
                    onChange={e => setDraft(d => ({ ...d, stable_key: e.target.value }))}
                    className="field"
                    placeholder="approved_secret_management"
                  />
                </Field>
              </div>
              <div className="grid md:grid-cols-3 gap-3">
                <Field label="Category">
                  <input value={draft.category} onChange={e => setDraft(d => ({ ...d, category: e.target.value }))} className="field" />
                </Field>
                <Field label="Requirement level">
                  <select value={draft.requirement_level} onChange={e => setDraft(d => ({ ...d, requirement_level: e.target.value as EnterpriseStandardInput['requirement_level'] }))} className="field">
                    <option value="required">Required</option>
                    <option value="preferred">Preferred</option>
                    <option value="recommended">Recommended</option>
                  </select>
                </Field>
                <Field label="Active">
                  <select value={draft.active ? 'true' : 'false'} onChange={e => setDraft(d => ({ ...d, active: e.target.value === 'true' }))} className="field">
                    <option value="true">Active</option>
                    <option value="false">Inactive</option>
                  </select>
                </Field>
              </div>
              <Field label="Description">
                <textarea value={draft.description} onChange={e => setDraft(d => ({ ...d, description: e.target.value }))} className="field" rows={2} />
              </Field>
              <Field label="Applicability">
                <select
                  value={draft.applicability_mode}
                  onChange={e => setDraft(d => ({
                    ...d,
                    applicability_mode: e.target.value as 'always' | 'conditions',
                    conditions: e.target.value === 'always' ? [] : d.conditions.length ? d.conditions : [{ field: 'primary_technology', operator: 'equals', value: '', logical_group: 'all' }],
                  }))}
                  className="field"
                >
                  <option value="always">Always applicable</option>
                  <option value="conditions">Conditional</option>
                </select>
              </Field>
              {draft.applicability_mode === 'conditions' && (
                <div className="space-y-2 rounded-lg p-3" style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}` }}>
                  <p className="text-xs font-medium" style={{ color: 'var(--muted-foreground)' }}>Applicability rules</p>
                  {draft.conditions.map((c, idx) => (
                    <div key={idx} className="grid grid-cols-2 md:grid-cols-5 gap-2">
                      <select value={c.field} onChange={e => setDraft(d => ({ ...d, conditions: d.conditions.map((x, i) => i === idx ? { ...x, field: e.target.value } : x) }))} className="field">
                        {APPLICABILITY_FIELDS.map(f => <option key={f} value={f}>{f}</option>)}
                      </select>
                      <select value={c.operator} onChange={e => setDraft(d => ({ ...d, conditions: d.conditions.map((x, i) => i === idx ? { ...x, operator: e.target.value } : x) }))} className="field">
                        {OPERATORS.map(o => <option key={o} value={o}>{o}</option>)}
                      </select>
                      <input value={c.value} onChange={e => setDraft(d => ({ ...d, conditions: d.conditions.map((x, i) => i === idx ? { ...x, value: e.target.value } : x) }))} className="field" placeholder="value" />
                      <select value={c.logical_group} onChange={e => setDraft(d => ({ ...d, conditions: d.conditions.map((x, i) => i === idx ? { ...x, logical_group: e.target.value as 'all' | 'any' } : x) }))} className="field">
                        <option value="all">all</option>
                        <option value="any">any</option>
                      </select>
                      <button
                        onClick={() => setDraft(d => ({ ...d, conditions: d.conditions.filter((_, i) => i !== idx) }))}
                        className="text-xs rounded-lg"
                        style={{ background: 'var(--card)', color: 'var(--muted-foreground)', border: `1px solid ${cardBorder}` }}
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                  <button
                    onClick={() => setDraft(d => ({ ...d, conditions: [...d.conditions, { field: 'primary_technology', operator: 'equals', value: '', logical_group: 'all' }] }))}
                    className="text-xs px-2 py-1 rounded"
                    style={{ background: 'var(--card)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
                  >
                    Add rule
                  </button>
                </div>
              )}
              <Field label="Related SAFe practices">
                <div className="flex flex-wrap gap-2">
                  {PRACTICE_KEYS.map(key => {
                    const on = draft.mapped_practice_keys.includes(key)
                    return (
                      <button
                        key={key}
                        type="button"
                        onClick={() => setDraft(d => ({
                          ...d,
                          mapped_practice_keys: on
                            ? d.mapped_practice_keys.filter(k => k !== key)
                            : [...d.mapped_practice_keys, key],
                        }))}
                        className="text-[11px] px-2 py-1 rounded"
                        style={{
                          background: on ? (dark ? '#0f1d40' : '#eef3fa') : 'var(--muted)',
                          color: on ? 'var(--primary)' : 'var(--muted-foreground)',
                          border: `1px solid ${on ? 'var(--primary)' : cardBorder}`,
                        }}
                      >
                        {key}
                      </button>
                    )
                  })}
                </div>
              </Field>
              <Field label="Primary interview guidance">
                <textarea value={draft.primary_interview_guidance} onChange={e => setDraft(d => ({ ...d, primary_interview_guidance: e.target.value }))} className="field" rows={2} />
              </Field>
              <Field label="Optional follow-up guidance">
                <textarea value={draft.follow_up_guidance} onChange={e => setDraft(d => ({ ...d, follow_up_guidance: e.target.value }))} className="field" rows={2} />
              </Field>
              <Field label="Evidence expectations">
                <textarea value={draft.evidence_expectations} onChange={e => setDraft(d => ({ ...d, evidence_expectations: e.target.value }))} className="field" rows={2} />
              </Field>
              <Field label="Recommendation when unmet">
                <textarea value={draft.recommendation_when_unmet} onChange={e => setDraft(d => ({ ...d, recommendation_when_unmet: e.target.value }))} className="field" rows={2} />
              </Field>
            </div>
            <div className="flex justify-end gap-2 mt-5">
              <button onClick={() => setShowEditor(false)} className="text-sm px-3 py-2 rounded-lg" style={{ background: 'var(--muted)', color: 'var(--foreground)' }}>Cancel</button>
              <button onClick={() => void saveDraft()} className="text-sm px-4 py-2 rounded-lg font-semibold" style={{ background: 'var(--primary)', color: '#fff' }}>Save standard</button>
            </div>
          </div>
          <style>{`
            .field {
              width: 100%;
              border-radius: 0.5rem;
              padding: 0.55rem 0.75rem;
              font-size: 0.875rem;
              outline: none;
              background: var(--muted);
              border: 1px solid ${cardBorder};
              color: var(--foreground);
            }
          `}</style>
        </div>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--muted-foreground)' }}>{label}</label>
      {children}
    </div>
  )
}
