import { AlertTriangle, ShieldAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Alert, Card, Spinner, cx } from '../components/ui'
import ReviewerMessages from './ReviewerMessages'
import { api, ApiError } from '../lib/api'
import { BAND_LABEL } from '../lib/questionnaire'
import type { Answer, Question, Questionnaire, ReviewerCheckin, ReviewerCheckinSummary, UrgentAlerts } from '../lib/types'

const RISK_STYLE: Record<string, string> = {
  high: 'bg-red-50 text-red-800 ring-red-200',
  medium: 'bg-amber-50 text-amber-800 ring-amber-200',
  low: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  unknown: 'bg-slate-100 text-slate-700 ring-slate-200',
}
const BAND_STYLE: Record<string, string> = {
  minimal: 'text-emerald-700', mild: 'text-sky-700', moderate: 'text-amber-700',
  moderately_severe: 'text-orange-700', severe: 'text-red-700',
}

function RiskBadge({ risk }: { risk: string }) {
  return (
    <span className={cx('inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ring-1 ring-inset', RISK_STYLE[risk])}>
      {risk}
    </span>
  )
}

function answerText(q: Question, a: Answer | undefined): string {
  if (a === undefined) return 'Skipped'
  if (typeof a === 'string') return a
  if (Array.isArray(a)) return a.map((v) => q.options.find((o) => o.value === v)?.label ?? v).join(', ')
  return q.options.find((o) => o.value === a)?.label ?? String(a)
}

function CheckinQueue() {
  const [rows, setRows] = useState<ReviewerCheckinSummary[] | null>(null)
  const [qn, setQn] = useState<Questionnaire | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<number | null>(null)
  const [detail, setDetail] = useState<ReviewerCheckin | null>(null)
  const [detailError, setDetailError] = useState('')
  const [opening, setOpening] = useState(false)
  const requested = useRef(false)
  const openSeq = useRef(0)

  useEffect(() => {
    // Loading the queue is itself an audited action: do it exactly once, even when React re-runs effects in development.
    if (requested.current) return
    requested.current = true
    Promise.all([api.reviewerQueue(), api.questionnaire()])
      .then(([r, q]) => { setRows(r); setQn(q) })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load check-ins.'))
  }, [])

  /** Opening a record is a deliberate click. The server writes an audit entry for each one. */
  async function open(id: number) {
    const seq = ++openSeq.current
    setSelected(id)
    setDetail(null)
    setDetailError('')
    setOpening(true)
    try {
      const d = await api.reviewerCheckin(id)
      if (seq === openSeq.current) setDetail(d)
    } catch (e) {
      if (seq === openSeq.current) setDetailError(e instanceof ApiError ? e.message : 'Could not open this check-in.')
    } finally {
      if (seq === openSeq.current) setOpening(false)
    }
  }

  if (error) return <Alert>{error}</Alert>
  if (!rows || !qn) return <Spinner label="Loading check-ins" />

  return (
    <div>
      <h1 className="font-display text-3xl font-medium text-slate-900">Review queue</h1>
      <p className="mt-1.5 text-sm text-slate-600">
        Check-ins sorted by urgency. Escalated cases appear first. Opening a record is logged.
      </p>

      {rows.length === 0 ? (
        <Card className="mt-8 p-10 text-center text-slate-600">No completed check-ins yet.</Card>
      ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <Card className="self-start overflow-hidden">
            <ul className="divide-y divide-slate-100" aria-label="Check-ins">
              {rows.map((r) => (
                <li key={r.id}>
                  <button onClick={() => void open(r.id)} aria-current={r.id === selected}
                    className={cx('flex w-full items-center gap-3 px-4 py-3.5 text-left hover:bg-slate-50', r.id === selected && 'bg-brand-50/70')}>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium text-slate-900">{r.user_name}</span>
                        {r.escalated && <ShieldAlert className="size-4 shrink-0 text-red-600" aria-label="Escalated" />}
                      </span>
                      <span className="text-xs text-slate-500">
                        {new Date(r.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
                      </span>
                    </span>
                    <RiskBadge risk={r.baseline_risk} />
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          {detail ? (
            <Detail c={detail} qn={qn} />
          ) : detailError ? (
            <Alert>{detailError}</Alert>
          ) : opening ? (
            <Spinner label="Opening check-in" />
          ) : (
            <Card className="grid min-h-48 place-items-center p-10 text-center text-sm text-slate-500">
              Select a check-in to review it.
            </Card>
          )}
        </div>
      )}
    </div>
  )
}

function Detail({ c, qn }: { c: ReviewerCheckin; qn: Questionnaire }) {
  const { phq9, gad7, safety } = c.scores
  const byId = new Map(qn.questions.map((q) => [q.id, q]))
  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium text-slate-900">{c.user_name}</h2>
          <p className="text-sm text-slate-600">{c.user_email}{c.is_minor && ' · Minor'}</p>
          {c.emergency_contact && <p className="text-sm text-slate-600">Emergency contact: {c.emergency_contact}</p>}
        </div>
        <RiskBadge risk={c.baseline_risk} />
      </div>

      {safety.flag && (
        <div className={cx('mt-5 flex gap-3 rounded-lg border p-4 text-sm', safety.escalate ? 'border-red-200 bg-red-50 text-red-900' : 'border-amber-200 bg-amber-50 text-amber-900')}>
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <div>
            <p className="font-medium">
              Suicide risk screen (C-SSRS): <span className="capitalize">{safety.tier_label}</span>
            </p>
            <p className="mt-0.5">
              {safety.escalate ? 'Needs prompt human follow-up.' : 'Self-harm thoughts endorsed. Crisis resources were shown to the user.'}{' '}
              <span className="font-medium">Minimum urgency: {safety.urgency_floor}.</span>
            </p>
          </div>
        </div>
      )}

      <dl className="mt-5 grid gap-4 sm:grid-cols-2">
        {[['Depression (PHQ-9)', phq9], ['Anxiety (GAD-7)', gad7]].map(([label, s]) => {
          const sc = s as typeof phq9
          return (
            <div key={label as string} className="rounded-lg border border-slate-200 p-4">
              <dt className="text-xs text-slate-500">{label as string}</dt>
              <dd className="mt-1 flex items-baseline gap-2">
                <span className="text-2xl font-semibold text-slate-900">{sc.score}</span>
                <span className="text-sm text-slate-500">/ {sc.max}</span>
                <span className={cx('ml-auto text-sm font-medium', BAND_STYLE[sc.band])}>{BAND_LABEL[sc.band]}</span>
              </dd>
              {!sc.complete && <p className="mt-1 text-xs text-amber-700">Incomplete: {sc.answered} of {sc.max === 27 ? 9 : 7} items answered</p>}
            </div>
          )
        })}
      </dl>

      {c.free_text && (
        <>
          <h3 className="mt-6 text-sm font-medium text-slate-900">In their own words</h3>
          <blockquote className="mt-2 border-l-2 border-brand-400 bg-slate-50 py-2.5 pl-4 pr-3 text-sm italic leading-relaxed text-slate-700">
            {c.free_text}
          </blockquote>
        </>
      )}

      <h3 className="mt-6 text-sm font-medium text-slate-900">All answers</h3>
      <div className="mt-2 divide-y divide-slate-100 text-sm">
        {qn.sections.map((s) => {
          const qs = qn.questions.filter((q) => q.section === s.id && q.id in c.answers && q.type !== 'text')
          if (!qs.length) return null
          return (
            <div key={s.id} className="py-3">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{s.title}</p>
              <ul className="mt-2 space-y-1.5">
                {qs.map((q) => (
                  <li key={q.id} className="flex justify-between gap-4">
                    <span className="text-slate-600">{byId.get(q.id)?.prompt}</span>
                    <span className="shrink-0 text-right font-medium text-slate-900">{answerText(q, c.answers[q.id])}</span>
                  </li>
                ))}
              </ul>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

const age = (sec: number) => (sec < 60 ? `${sec}s` : `${Math.round(sec / 60)} min`)

/** Counts-only polling (no names, no text, not audited), so an urgent message shows up here within seconds of being sent. */
function useUrgentAlerts() {
  const [alerts, setAlerts] = useState<UrgentAlerts | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const last = useRef('')
  useEffect(() => {
    let stop = false
    const tick = () => {
      if (document.hidden) return
      api.reviewerAlerts()
        .then((a) => {
          if (stop) return
          setAlerts(a)
          const sig = `${a.urgent_waiting}:${a.latest_urgent_id}`
          if (last.current && sig !== last.current) setRefreshKey((k) => k + 1)
          last.current = sig
        })
        .catch(() => undefined)
    }
    tick()
    const id = window.setInterval(tick, 4000)
    return () => {
      stop = true
      window.clearInterval(id)
    }
  }, [])
  useEffect(() => {
    const n = alerts?.urgent_unopened ?? 0
    document.title = n > 0 ? `(${n}) Urgent waiting · IRIS` : 'IRIS'
    return () => {
      document.title = 'IRIS'
    }
  }, [alerts?.urgent_unopened])
  return { alerts, refreshKey }
}

/** The reviewer's home: two queues, both audited. Check-ins first; messages (the chat) in the second tab. An urgent message raises a banner at once. */
export default function Reviewer() {
  const [tab, setTab] = useState<'checkins' | 'messages'>('checkins')
  const { alerts, refreshKey } = useUrgentAlerts()
  const tabs = [['checkins', 'Check-ins'], ['messages', 'Messages']] as const
  const unopened = alerts?.urgent_unopened ?? 0
  const doctorWaiting = alerts?.doctor_requests_waiting ?? 0
  const doctorOverdue = alerts?.doctor_requests_overdue ?? 0
  return (
    <div>
      {doctorWaiting > 0 && (
        <div role="status" className="mb-3 flex items-center gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm font-medium text-amber-900">
          <ShieldAlert className="size-5 shrink-0" aria-hidden />
          {doctorWaiting} urgent doctor request{doctorWaiting > 1 ? 's' : ''} waiting for a doctor to accept
        </div>
      )}
      {doctorOverdue > 0 && (
        <div role="alert" className="mb-3 flex items-center gap-2 rounded-xl border-2 border-red-300 bg-red-50 px-4 py-2.5 text-sm font-medium text-red-900">
          <ShieldAlert className="size-5 shrink-0" aria-hidden />
          {doctorOverdue} doctor request{doctorOverdue > 1 ? 's have' : ' has'} waited longer than the goal with nobody accepting. Consider contacting
          the person or finding a doctor.
        </div>
      )}
      {unopened > 0 && (
        <div role="alert" className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border-2 border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900">
          <span className="flex items-center gap-2 font-medium">
            <ShieldAlert className="size-5 shrink-0 animate-pulse" aria-hidden />
            {unopened} urgent message{unopened > 1 ? 's' : ''} waiting, not opened yet
            {alerts?.oldest_unopened_seconds != null && <span className="font-normal"> · oldest {age(alerts.oldest_unopened_seconds)}</span>}
          </span>
          {tab !== 'messages' && (
            <button onClick={() => setTab('messages')} className="rounded-lg bg-red-700 px-3.5 py-1.5 font-medium text-white hover:bg-red-800">
              Open messages
            </button>
          )}
        </div>
      )}
      <div role="tablist" aria-label="Review queues" className="mb-6 inline-flex rounded-lg bg-slate-100 p-1">
        {tabs.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
            className={cx('rounded-md px-4 py-1.5 text-sm font-medium', tab === id ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900')}>
            {label}
            {id === 'messages' && (alerts?.urgent_waiting ?? 0) > 0 && (
              <span className="ml-1.5 rounded-full bg-red-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">{alerts?.urgent_waiting}</span>
            )}
          </button>
        ))}
      </div>
      {tab === 'checkins' ? <CheckinQueue /> : <div><h1 className="font-display text-3xl font-medium text-slate-900">Message queue</h1><ReviewerMessages refreshKey={refreshKey} /></div>}
    </div>
  )
}
