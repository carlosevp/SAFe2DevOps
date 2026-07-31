import { useEffect, useMemo, useState } from 'react'
import { Send, CheckCircle2, PlusCircle, Paperclip, AlertCircle } from 'lucide-react'
import {
  ApiError,
  getRemoteTopic,
  joinRemote,
  submitRemoteContribution,
  type RemoteJoinResult,
} from '../lib/api'

interface Props {
  dark: boolean
  inviteToken?: string | null
}

function readInviteFromLocation(): string | null {
  const params = new URLSearchParams(window.location.search)
  return params.get('invite')
}

export default function RemoteContributor({ dark, inviteToken }: Props) {
  const token = useMemo(() => inviteToken || readInviteFromLocation() || '', [inviteToken])
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [joined, setJoined] = useState<RemoteJoinResult | null>(null)
  const [contribution, setContribution] = useState('')
  const [submittedPreview, setSubmittedPreview] = useState<string | null>(null)
  const [addAnother, setAddAnother] = useState(false)
  const [note2, setNote2] = useState('')
  const [attachment, setAttachment] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [topicMeta, setTopicMeta] = useState<{
    team_name: string
    assessment_name: string
    topic_label: string
    question_text: string
    evidence_context: string
  } | null>(null)
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'

  useEffect(() => {
    if (!token) {
      setError('This invite link is missing or invalid.')
      setLoading(false)
      return
    }
    setLoading(true)
    getRemoteTopic(token)
      .then(topic => {
        setTopicMeta(topic)
        setError(null)
      })
      .catch((err: unknown) => {
        const message = err instanceof ApiError ? err.message : 'Unable to open invite link'
        setError(message)
      })
      .finally(() => setLoading(false))
  }, [token])

  async function handleJoin(e: React.FormEvent) {
    e.preventDefault()
    if (!token || !name || !email) return
    setError(null)
    try {
      const result = await joinRemote(token, name, email)
      setJoined(result)
      setTopicMeta({
        team_name: result.team_name,
        assessment_name: result.assessment_name,
        topic_label: result.topic_label,
        question_text: result.question_text,
        evidence_context: result.evidence_context,
      })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to join')
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!joined || !contribution.trim()) return
    setError(null)
    try {
      const result = await submitRemoteContribution({
        token,
        contributor_id: joined.contributor_id,
        body: contribution,
        attachment,
      })
      setSubmittedPreview(result.preview)
      setAttachment(null)
      setAddAnother(false)
      setNote2('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to submit contribution')
    }
  }

  async function handleSubmitAnother() {
    if (!joined || !note2.trim()) return
    setError(null)
    try {
      const result = await submitRemoteContribution({
        token,
        contributor_id: joined.contributor_id,
        body: note2,
      })
      setSubmittedPreview(result.preview)
      setNote2('')
      setAddAnother(false)
      // Refresh topic for async follow-up notes.
      const topic = await getRemoteTopic(token)
      setTopicMeta(topic)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to submit note')
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--background)' }}>
        <p className="text-sm" style={{ color: 'var(--muted-foreground)' }}>Opening invite…</p>
      </div>
    )
  }

  return (
    <div
      className="min-h-screen flex items-start justify-center"
      style={{ background: 'var(--background)', paddingTop: 48, paddingBottom: 48 }}
    >
      <div className="w-full max-w-lg px-4">
        <div className="flex items-center gap-2.5 mb-8 justify-center">
          <div
            className="rounded flex items-center justify-center text-xs font-bold"
            style={{ width: 32, height: 32, background: 'var(--primary)', color: '#fff' }}
          >
            SD
          </div>
          <span className="font-semibold text-sm" style={{ color: 'var(--foreground)' }}>
            SAFe DevOps Assessment
          </span>
        </div>

        {error && (
          <div
            className="rounded-xl p-4 mb-4 flex items-start gap-2 text-sm"
            style={{ background: dark ? '#3f1d1d' : '#fef2f2', color: dark ? '#fca5a5' : '#991b1b', border: `1px solid ${dark ? '#7f1d1d' : '#fecaca'}` }}
          >
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {!joined ? (
          <div
            className="rounded-2xl p-5 sm:p-7"
            style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
          >
            <h1 className="font-serif text-2xl mb-2" style={{ color: 'var(--foreground)' }}>
              You've been invited to contribute
            </h1>
            <p className="text-sm mb-6" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
              The <strong style={{ color: 'var(--foreground)' }}>{topicMeta?.team_name || 'team'}</strong> is running a DevOps maturity assessment
              {topicMeta?.assessment_name ? <> for <strong style={{ color: 'var(--foreground)' }}>{topicMeta.assessment_name}</strong></> : null}.
              Share your perspective on how the team delivers.
            </p>

            <form onSubmit={e => void handleJoin(e)} className="space-y-4">
              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--muted-foreground)' }}>
                  Your name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="e.g. Priya Sharma"
                  required
                  className="w-full rounded-lg px-3 py-2.5 text-sm outline-none transition-base"
                  style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)' }}
                />
              </div>
              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--muted-foreground)' }}>
                  Email address
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="priya@yourorg.com"
                  required
                  className="w-full rounded-lg px-3 py-2.5 text-sm outline-none transition-base"
                  style={{ background: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--foreground)' }}
                />
              </div>

              <div
                className="rounded-lg p-3 text-xs"
                style={{ background: dark ? '#141f35' : '#f8fafc', color: 'var(--muted-foreground)', lineHeight: 1.6 }}
              >
                Your name and responses will be visible to the assessment host. No maturity scores or internal evaluation data will be shared with you.
              </div>

              <button
                type="submit"
                className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg text-sm font-semibold transition-base"
                style={{ background: 'var(--primary)', color: '#fff' }}
              >
                Join assessment
              </button>
            </form>
          </div>
        ) : !submittedPreview ? (
          <div
            className="rounded-2xl p-5 sm:p-7 animate-fade-in"
            style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
          >
            <div className="flex items-center gap-2 mb-6">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
                style={{ background: 'var(--primary)', color: '#fff' }}
              >
                {joined.display_name.charAt(0).toUpperCase()}
              </div>
              <div>
                <p className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>{joined.display_name}</p>
                <p className="text-xs" style={{ color: 'var(--muted-foreground)' }}>
                  {joined.team_name} · {joined.assessment_name}
                </p>
              </div>
            </div>

            <div
              className="rounded-xl p-4 mb-4"
              style={{ background: dark ? '#0f1d40' : '#eef3fa', border: `1px solid ${dark ? '#1e3358' : '#b0c7e6'}` }}
            >
              <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--primary)' }}>
                {topicMeta?.topic_label || 'Current topic'}
              </p>
              <p className="font-serif text-base mb-2" style={{ color: 'var(--foreground)', lineHeight: 1.6 }}>
                {topicMeta?.question_text}
              </p>
              {topicMeta?.evidence_context && (
                <p className="text-xs" style={{ color: 'var(--muted-foreground)', lineHeight: 1.55 }}>
                  {topicMeta.evidence_context}
                </p>
              )}
            </div>

            <form onSubmit={e => void handleSubmit(e)} className="space-y-3">
              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--muted-foreground)' }}>
                  Your contribution
                </label>
                <textarea
                  value={contribution}
                  onChange={e => setContribution(e.target.value)}
                  placeholder="Share your perspective on this topic…"
                  required
                  className="w-full rounded-lg p-3 text-sm outline-none resize-none"
                  style={{
                    background: 'var(--muted)',
                    border: '1px solid var(--border)',
                    color: 'var(--foreground)',
                    minHeight: 130,
                    lineHeight: 1.7,
                  }}
                />
              </div>

              <label
                className="inline-flex items-center gap-2 text-xs px-3 py-2 rounded-lg transition-base cursor-pointer"
                style={{ color: 'var(--muted-foreground)', background: 'var(--muted)', border: `1px solid ${cardBorder}` }}
              >
                <Paperclip size={12} />
                {attachment ? attachment.name : 'Attach a file (optional)'}
                <input
                  type="file"
                  className="hidden"
                  accept=".pdf,.png,.jpg,.jpeg,.txt,.md,application/pdf,image/png,image/jpeg,text/plain,text/markdown"
                  onChange={e => setAttachment(e.target.files?.[0] || null)}
                />
              </label>

              <button
                type="submit"
                className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg text-sm font-semibold transition-base"
                style={{ background: 'var(--primary)', color: '#fff' }}
              >
                <Send size={14} />
                Submit contribution
              </button>
            </form>
          </div>
        ) : (
          <div
            className="rounded-2xl p-5 sm:p-7 text-center animate-fade-in"
            style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
          >
            <div
              className="w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-4"
              style={{ background: '#d1fae5' }}
            >
              <CheckCircle2 size={28} style={{ color: '#10b981' }} />
            </div>
            <h2 className="font-serif text-xl mb-2" style={{ color: 'var(--foreground)' }}>
              Contribution received
            </h2>
            <p className="text-sm mb-6" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
              Your contribution has been added for the host to review. It will be included in the assessment at their discretion.
            </p>

            <div
              className="rounded-xl p-4 text-left mb-6"
              style={{ background: 'var(--muted)', border: `1px solid ${cardBorder}` }}
            >
              <div className="flex items-center gap-2 mb-2">
                <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#10b981' }} />
                <span className="text-xs font-medium" style={{ color: '#10b981' }}>Submitted</span>
              </div>
              <p className="text-xs" style={{ color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
                {submittedPreview}
              </p>
            </div>

            {!addAnother ? (
              <button
                onClick={() => setAddAnother(true)}
                className="flex items-center gap-2 mx-auto text-sm px-4 py-2.5 rounded-lg transition-base"
                style={{ background: 'var(--muted)', color: 'var(--foreground)', border: `1px solid ${cardBorder}` }}
              >
                <PlusCircle size={14} />
                Add another note
              </button>
            ) : (
              <div className="text-left animate-fade-in">
                <textarea
                  value={note2}
                  onChange={e => setNote2(e.target.value)}
                  placeholder="Add another note for the host…"
                  className="w-full rounded-lg p-3 text-sm outline-none resize-none mb-3"
                  style={{
                    background: 'var(--muted)',
                    border: '1px solid var(--border)',
                    color: 'var(--foreground)',
                    minHeight: 80,
                    lineHeight: 1.7,
                  }}
                />
                <button
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-base"
                  style={{ background: 'var(--primary)', color: '#fff' }}
                  onClick={() => void handleSubmitAnother()}
                >
                  <Send size={13} />
                  Submit
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
