import { AlertTriangle, ShieldAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Field, Select, Spinner, Textarea, cx } from '../components/ui'
import { api, ApiError } from '../lib/api'
import type { Priority, ReviewerMessage, ReviewerMessageSummary } from '../lib/types'

const PRIORITY_STYLE: Record<string, string> = {
  high: 'bg-red-50 text-red-800 ring-red-200',
  medium: 'bg-amber-50 text-amber-800 ring-amber-200',
  low: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
}

function PriorityBadge({ p }: { p: string }) {
  return (
    <span className={cx('inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ring-1 ring-inset', PRIORITY_STYLE[p])}>{p}</span>
  )
}

const when = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

export default function ReviewerMessages({ refreshKey = 0 }: { refreshKey?: number }) {
  const [rows, setRows] = useState<ReviewerMessageSummary[] | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<number | null>(null)
  const [detail, setDetail] = useState<ReviewerMessage | null>(null)
  const [detailError, setDetailError] = useState('')
  const [opening, setOpening] = useState(false)
  const requested = useRef(false)
  const seq = useRef(0)

  const load = () =>
    api
      .reviewerMessages()
      .then(setRows)
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load messages.'))

  useEffect(() => {
    // Loading the queue is an audited action: do it exactly once on arrival, and again only after a reviewer acts
    // or when the alert counts say something new arrived (see Reviewer.tsx).
    if (requested.current) return
    requested.current = true
    void load()
  }, [])

  const firstKey = useRef(true)
  useEffect(() => {
    if (firstKey.current) {
      firstKey.current = false
      return
    }
    void load()
  }, [refreshKey])

  async function open(id: number) {
    const s = ++seq.current
    setSelected(id)
    setDetail(null)
    setDetailError('')
    setOpening(true)
    try {
      const d = await api.reviewerMessage(id)
      if (s === seq.current) setDetail(d)
    } catch (e) {
      if (s === seq.current) setDetailError(e instanceof ApiError ? e.message : 'Could not open this message.')
    } finally {
      if (s === seq.current) setOpening(false)
    }
  }

  function updated(d: ReviewerMessage) {
    setDetail(d)
    void load()
  }

  if (error) return <Alert>{error}</Alert>
  if (!rows) return <Spinner label="Loading messages" />

  return (
    <div>
      <p className="mt-1.5 text-sm text-slate-600">
        Every message waits here for a person. Highest priority first. The system never closes a case: only your review does. Opening a message is logged.
      </p>
      {rows.length === 0 ? (
        <Card className="mt-6 p-10 text-center text-slate-600">No messages yet.</Card>
      ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <Card className="self-start overflow-hidden">
            <ul className="divide-y divide-slate-100" aria-label="Messages">
              {rows.map((r) => (
                <li key={r.id}>
                  <button
                    onClick={() => void open(r.id)}
                    aria-current={r.id === selected}
                    className={cx('flex w-full items-center gap-3 px-4 py-3.5 text-left hover:bg-slate-50', r.id === selected && 'bg-brand-50/70')}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium text-slate-900">{r.user_name}</span>
                        {r.priority === 'high' && r.status !== 'reviewed' && !r.opened && <span className="size-2 shrink-0 animate-pulse rounded-full bg-red-600" aria-label="Urgent and not opened yet" />}
                        {(r.rule_flagged || r.baseline_floor === 'high') && <ShieldAlert className="size-4 shrink-0 text-red-600" aria-label="Safety layer fired" />}
                      </span>
                      <span className="text-xs text-slate-500">
                        {when(r.created_at)} · {r.status === 'reviewed' ? 'Reviewed' : r.opened ? 'Being read' : 'Not opened yet'}
                        {r.reviewer_raised && ' · Raised'}
                      </span>
                    </span>
                    <PriorityBadge p={r.priority} />
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          {detail ? (
            <MessageDetail key={`${detail.id}:${detail.history.length}:${detail.status}`} m={detail} onChange={updated} />
          ) : detailError ? (
            <Alert>{detailError}</Alert>
          ) : opening ? (
            <Spinner label="Opening message" />
          ) : (
            <Card className="grid min-h-48 place-items-center p-10 text-center text-sm text-slate-500">Select a message to review it.</Card>
          )}
        </div>
      )}
    </div>
  )
}

function MessageDetail({ m, onChange }: { m: ReviewerMessage; onChange: (d: ReviewerMessage) => void }) {
  const [to, setTo] = useState<'medium' | 'high'>(m.priority === 'medium' ? 'high' : 'medium')
  const [reason, setReason] = useState('')
  const [urgency, setUrgency] = useState<Priority>(m.priority)
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState<'' | 'escalate' | 'review'>('')
  const [err, setErr] = useState('')
  const pending = m.status === 'pending_human_review'
  const urgent = m.priority === 'high'

  async function run(kind: 'escalate' | 'review') {
    setBusy(kind)
    setErr('')
    try {
      const d = kind === 'escalate' ? await api.escalateMessage(m.id, to, reason) : await api.reviewMessage(m.id, urgency, notes)
      onChange(d)
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'That did not work. Please try again.')
    } finally {
      setBusy('')
    }
  }

  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium text-slate-900">{m.user_name}</h2>
          <p className="text-sm text-slate-600">{m.user_email}</p>
          <p className="text-xs text-slate-500">{when(m.created_at)}</p>
        </div>
        <div className="text-right">
          <PriorityBadge p={m.priority} />
          <p className="mt-1 text-xs text-slate-500">{pending ? 'Waiting for review' : 'Reviewed'}</p>
        </div>
      </div>

      <div
        className={cx('mt-5 flex gap-3 rounded-lg border p-4 text-sm', urgent ? 'border-red-200 bg-red-50 text-red-900' : 'border-slate-200 bg-slate-50 text-slate-800')}
      >
        <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
        <p>{m.reviewer_note.split(' Reasons:')[0]}</p>
      </div>

      <h3 className="mt-6 text-sm font-medium text-slate-900">Their message</h3>
      <blockquote className="mt-2 whitespace-pre-wrap border-l-2 border-brand-400 bg-slate-50 py-2.5 pl-4 pr-3 text-sm leading-relaxed text-slate-800">{m.text}</blockquote>

      <h3 className="mt-6 text-sm font-medium text-slate-900">Why it has this priority</h3>
      <dl className="mt-2 grid gap-3 text-sm sm:grid-cols-2">
        <div className="rounded-lg border border-slate-200 p-3">
          <dt className="text-xs text-slate-500">Rule layer (explicit language)</dt>
          <dd className="mt-0.5 font-medium capitalize text-slate-900">
            {m.rule_level === 'none' ? 'Nothing flagged' : `${m.rule_level}${m.rule_hits.length ? ` (${m.rule_hits.join(', ')})` : ''}`}
          </dd>
        </div>
        <div className="rounded-lg border border-slate-200 p-3">
          <dt className="text-xs text-slate-500">Check-in safety floor</dt>
          <dd className="mt-0.5 font-medium capitalize text-slate-900">
            {m.baseline_known ? m.baseline_floor : 'No check-in on record (unknown, not safe)'}
          </dd>
        </div>
      </dl>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-600">
        {m.reasons.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-slate-500">
        Model: {m.model_version}. Priority comes from the rules and the check-in only. Low means lower estimated urgency, not zero risk.
      </p>

      <h3 className="mt-6 text-sm font-medium text-slate-900">What IRIS replied to them</h3>
      <p className="mt-1 text-xs text-slate-500">AI-assisted draft wording, clinical review pending.</p>
      <div className="mt-2 rounded-lg border border-slate-200 p-3 text-sm text-slate-700">
        <p className="font-medium text-slate-900">{m.reply_shown.intro}</p>
        {m.reply_shown.self_help.length > 0 && <p className="mt-1">Suggested: {m.reply_shown.self_help.map((s) => s.title).join(', ')}.</p>}
        {m.reply_shown.show_crisis_resources && <p className="mt-1 font-medium text-brand-800">Helplines were shown to them.</p>}
      </div>

      {m.history.length > 0 && (
        <>
          <h3 className="mt-6 text-sm font-medium text-slate-900">Review history</h3>
          <ul className="mt-2 space-y-2 text-sm">
            {m.history.map((h) => (
              <li key={h.id} className="rounded-lg border border-slate-200 p-3">
                <p className="font-medium text-slate-900">
                  {h.kind === 'escalation' ? `Raised from ${h.from_urgency} to ${h.to_urgency}` : `Reviewed: judged ${h.to_urgency}`}
                  <span className="font-normal text-slate-500"> · {h.reviewer_name} · {when(h.created_at)}</span>
                </p>
                {h.notes && <p className="mt-0.5 text-slate-700">{h.notes}</p>}
              </li>
            ))}
          </ul>
        </>
      )}

      {pending && (
        <div className="mt-6 grid gap-6 border-t border-slate-200 pt-6">
          {err && <Alert>{err}</Alert>}

          {m.priority !== 'high' && (
            <section aria-label="Raise priority">
              <h3 className="text-sm font-medium text-slate-900">Raise the priority</h3>
              <p className="mt-0.5 text-xs text-slate-500">For warning signs, contradictions or doubt. It can only go up. A reason is required.</p>
              <div className="mt-3 grid gap-3">
                <Field label="Raise to">
                  {(id) => (
                    <Select id={id} value={to} onChange={(e) => setTo(e.target.value as 'medium' | 'high')}>
                      {m.priority === 'low' && <option value="medium">Medium</option>}
                      <option value="high">High</option>
                    </Select>
                  )}
                </Field>
                <Field label="Reason">
                  {(id) => <Textarea id={id} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} className="min-h-20" />}
                </Field>
                <div>
                  <Button variant="secondary" loading={busy === 'escalate'} disabled={reason.trim().length < 3} onClick={() => void run('escalate')}>
                    Raise priority
                  </Button>
                </div>
              </div>
            </section>
          )}

          <section aria-label="Record your review">
            <h3 className="text-sm font-medium text-slate-900">Record your review</h3>
            <p className="mt-0.5 text-xs text-slate-500">This is your own judgement and it closes the case. Nothing else ever does.</p>
            <div className="mt-3 grid gap-3">
              <Field label="Your judgement of urgency">
                {(id) => (
                  <Select id={id} value={urgency} onChange={(e) => setUrgency(e.target.value as Priority)}>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </Select>
                )}
              </Field>
              <Field label="Notes" optional>
                {(id) => <Textarea id={id} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} className="min-h-20" />}
              </Field>
              <div>
                <Button loading={busy === 'review'} onClick={() => void run('review')}>
                  Record my review
                </Button>
              </div>
            </div>
          </section>
        </div>
      )}
    </Card>
  )
}
