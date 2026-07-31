import { useState } from 'react'
import { Send, CheckCircle2, PlusCircle, Paperclip } from 'lucide-react'

interface Props {
  dark: boolean
}

export default function RemoteContributor({ dark }: Props) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [joined, setJoined] = useState(false)
  const [contribution, setContribution] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [addAnother, setAddAnother] = useState(false)
  const [note2, setNote2] = useState('')
  const cardBorder = dark ? '#1e3358' : '#e2e8f0'

  function handleJoin(e: React.FormEvent) {
    e.preventDefault()
    if (name && email) setJoined(true)
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (contribution) setSubmitted(true)
  }

  return (
    <div
      className="min-h-screen flex items-start justify-center"
      style={{ background: 'var(--background)', paddingTop: 48, paddingBottom: 48 }}
    >
      <div className="w-full max-w-lg px-4">
        {/* Brand */}
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

        {!joined ? (
          <div
            className="rounded-2xl p-7"
            style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
          >
            <h1 className="font-serif text-2xl mb-2" style={{ color: 'var(--foreground)' }}>
              You've been invited to contribute
            </h1>
            <p className="text-sm mb-6" style={{ color: 'var(--muted-foreground)', lineHeight: 1.65 }}>
              The <strong style={{ color: 'var(--foreground)' }}>Claims Integration</strong> team is running a DevOps maturity assessment. Share your perspective on how the team delivers.
            </p>

            <form onSubmit={handleJoin} className="space-y-4">
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
                  onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
                  onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
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
                  onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
                  onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
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
                onMouseEnter={e => (e.currentTarget.style.opacity = '0.88')}
                onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
              >
                Join assessment
              </button>
            </form>
          </div>
        ) : !submitted ? (
          <div
            className="rounded-2xl p-7 animate-fade-in"
            style={{ background: 'var(--card)', border: `1px solid ${cardBorder}` }}
          >
            <div className="flex items-center gap-2 mb-6">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
                style={{ background: 'var(--primary)', color: '#fff' }}
              >
                {name.charAt(0).toUpperCase()}
              </div>
              <div>
                <p className="text-sm font-medium" style={{ color: 'var(--foreground)' }}>{name}</p>
                <p className="text-xs" style={{ color: 'var(--muted-foreground)' }}>Claims Integration · DevOps Maturity Assessment</p>
              </div>
            </div>

            <div
              className="rounded-xl p-4 mb-4"
              style={{ background: dark ? '#0f1d40' : '#eef3fa', border: `1px solid ${dark ? '#1e3358' : '#b0c7e6'}` }}
            >
              <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: 'var(--primary)' }}>
                Current topic
              </p>
              <p className="font-serif text-base mb-2" style={{ color: 'var(--foreground)', lineHeight: 1.6 }}>
                Describe what happens between a developer finishing a code change and it being ready to merge.
              </p>
              <p className="text-xs" style={{ color: 'var(--muted-foreground)', lineHeight: 1.55 }}>
                Azure DevOps shows 44 completed PRs with an average of 1.9 reviews each and a median completion time of 1.8 days.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-3">
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
                  onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
                  onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
                />
              </div>

              <button
                type="button"
                className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg transition-base"
                style={{ color: 'var(--muted-foreground)', background: 'var(--muted)', border: `1px solid ${cardBorder}` }}
              >
                <Paperclip size={12} />
                Attach a file (optional)
              </button>

              <button
                type="submit"
                className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg text-sm font-semibold transition-base"
                style={{ background: 'var(--primary)', color: '#fff' }}
                onMouseEnter={e => (e.currentTarget.style.opacity = '0.88')}
                onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
              >
                <Send size={14} />
                Submit contribution
              </button>
            </form>
          </div>
        ) : (
          <div
            className="rounded-2xl p-7 text-center animate-fade-in"
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
                {contribution.slice(0, 100)}{contribution.length > 100 ? '…' : ''}
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
                  onFocus={e => (e.currentTarget.style.borderColor = 'var(--ring)')}
                  onBlur={e => (e.currentTarget.style.borderColor = 'var(--border)')}
                />
                <button
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold transition-base"
                  style={{ background: 'var(--primary)', color: '#fff' }}
                  onClick={() => setAddAnother(false)}
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
