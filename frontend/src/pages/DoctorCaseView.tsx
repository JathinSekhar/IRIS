import { ArrowLeft, ShieldAlert } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import ConsultThread from '../components/ConsultThread'
import { Alert, Button, Card, Textarea } from '../components/ui'
import { api, ApiError } from '../lib/api'
import type { CaseDetail, SessionNote, SessionNoteInput, YesNo } from '../lib/types'

const RISK_LABEL: Record<string, string> = { low: 'Low', medium: 'Medium', high: 'High' }
const MODE_LABEL: Record<string, string> = { chat: 'Chat', video: 'Video', both: 'Chat and video' }
const YESNO_LABEL: Record<string, string> = { yes: 'Yes', no: 'No', not_assessed: 'Not assessed' }
const PLAN_LABEL: Record<string, string> = { not_needed: 'Not needed', created: 'Created', updated: 'Updated', reviewed: 'Reviewed' }

const RISK_QUESTIONS: { key: 'ideation' | 'plan' | 'intent' | 'means_access' | 'previous_attempt'; label: string }[] = [
  { key: 'ideation', label: 'Thoughts of suicide or self-harm' },
  { key: 'plan', label: 'Has a plan' },
  { key: 'intent', label: 'Intent to act' },
  { key: 'means_access', label: 'Access to means' },
  { key: 'previous_attempt', label: 'Previous attempt' },
]

const EMPTY = {
  mode: 'chat', concerns: '', observations: '', ideation: '', plan: '', intent: '', means_access: '', previous_attempt: '', protective_factors: '',
  risk_level: '', safety_plan: '', safety_plan_copy_given: false, impression: '', actions_taken: '', follow_up: '', follow_up_date: '', referral: '',
  emergency_services_contacted: false,
}
type FormState = typeof EMPTY

function NoteView({ n }: { n: SessionNote }) {
  const row = (label: string, value: ReactNode) => (
    <p>
      <span className="font-semibold text-slate-900">{label}.</span> {value}
    </p>
  )
  return (
    <Card className="space-y-2 p-5 text-sm text-slate-700">
      <h2 className="font-medium text-slate-900">Session note</h2>
      {row('Mode', MODE_LABEL[n.mode] ?? n.mode)}
      {row('Concerns', n.concerns)}
      {n.observations && row('Observations', n.observations)}
      {RISK_QUESTIONS.map((q) => <span key={q.key}>{row(q.label, YESNO_LABEL[n[q.key]])}</span>)}
      {row('Protective factors', n.protective_factors)}
      {row('Risk judgement', RISK_LABEL[n.risk_level] ?? n.risk_level)}
      {row('Safety plan', `${PLAN_LABEL[n.safety_plan]}${n.safety_plan !== 'not_needed' ? (n.safety_plan_copy_given ? ', copy given' : ', copy not given') : ''}`)}
      {n.impression && row('Clinical impression', n.impression)}
      {row('Actions taken', n.actions_taken)}
      {row('Follow-up', `${n.follow_up}${n.follow_up_date ? ` (${n.follow_up_date})` : ''}`)}
      {n.referral && row('Referral', n.referral)}
      {row('Emergency services contacted', n.emergency_services_contacted ? 'Yes' : 'No')}
    </Card>
  )
}

function Seg({ value, onChange, name }: { value: string; onChange: (v: YesNo) => void; name: string }) {
  return (
    <div role="radiogroup" aria-label={name} className="flex flex-wrap gap-2">
      {(['yes', 'no', 'not_assessed'] as const).map((v) => (
        <button
          key={v}
          type="button"
          role="radio"
          aria-checked={value === v}
          onClick={() => onChange(v)}
          className={
            'h-9 rounded-lg border px-3 text-sm font-medium ' +
            (value === v ? 'border-brand-800 bg-brand-800 text-white' : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50')
          }
        >
          {YESNO_LABEL[v]}
        </button>
      ))}
    </div>
  )
}

const selectCls = 'mt-1 block h-11 w-full rounded-lg border border-slate-300 bg-white px-3'

/** One case: who the doctor is speaking with, the conversation, and the session form that is required to end it. */
export default function DoctorCaseView() {
  const id = Number(useParams().id)
  const nav = useNavigate()
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [note, setNote] = useState<SessionNote | null | undefined>(undefined)
  const [form, setForm] = useState<FormState>(EMPTY)
  const [ending, setEnding] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const loadNote = useCallback(() => {
    api.doctorCaseNote(id).then(setNote).catch(() => setNote(null))
  }, [id])
  useEffect(() => {
    if (!Number.isFinite(id)) return
    loadNote()
    api.doctorCaseDetail(id).then(setDetail).catch(() => undefined)
  }, [id, loadNote])

  if (!Number.isFinite(id)) return null
  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setForm((f) => ({ ...f, [k]: v }))
  const text = (s: string) => s.trim().length >= 3
  const ready =
    text(form.concerns) && text(form.protective_factors) && text(form.actions_taken) && text(form.follow_up) &&
    RISK_QUESTIONS.every((q) => form[q.key] !== '') && form.risk_level !== '' && form.safety_plan !== ''

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!ready || busy) return
    setBusy(true)
    setError('')
    const body = {
      ...form,
      observations: form.observations.trim() || null,
      impression: form.impression.trim() || null,
      referral: form.referral.trim() || null,
      follow_up_date: form.follow_up_date || null,
      safety_plan_copy_given: form.safety_plan === 'not_needed' ? false : form.safety_plan_copy_given,
    } as unknown as SessionNoteInput
    try {
      await api.closeCase(id, body)
      nav('/doctor')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not end the session. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  const closed = note != null
  return (
    <div className="mx-auto max-w-2xl space-y-4 py-8">
      <Link to="/doctor" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
        <ArrowLeft className="size-4" aria-hidden /> Back to cases
      </Link>
      <h1 className="font-display text-2xl font-medium text-slate-900">Conversation</h1>

      {detail && (
        <Card className="space-y-1.5 p-4 text-sm text-slate-700">
          <p>
            <span className="font-semibold text-slate-900">{detail.full_name}</span>, {detail.age} years old
            {detail.phone && <> · {detail.phone}</>}
          </p>
          {detail.emergency_contact && <p><span className="font-semibold text-slate-900">Emergency contact.</span> {detail.emergency_contact}</p>}
          {detail.is_minor && (
            <p className="mt-2 flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-amber-900">
              <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>
                This person is under 18. A consultation with a minor needs an identified adult family member.
                {detail.guardian_name ? ` Guardian: ${detail.guardian_name} (${detail.guardian_consent_status ?? 'consent status unknown'}).` : ' No guardian is on record.'}
              </span>
            </p>
          )}
        </Card>
      )}

      <ConsultThread
        load={() => api.doctorCaseMessages(id)}
        send={(t) => api.sendDoctorCaseMessage(id, t)}
        otherName="the person"
        showFlags
        active={!closed}
      />

      {closed && note && <NoteView n={note} />}

      {!closed && !ending && (
        <Button variant="secondary" onClick={() => setEnding(true)}>
          End session and complete the form
        </Button>
      )}

      {!closed && ending && (
        <Card className="p-5">
          <form onSubmit={(e) => void submit(e)} className="space-y-5">
            <div>
              <h2 className="font-medium text-slate-900">Session form</h2>
              <p className="text-sm text-slate-600">The person does not see this note. Every risk question needs an answer; "Not assessed" is an answer.</p>
            </div>

            <label className="block text-sm">
              <span className="font-medium text-slate-800">How did you speak?</span>
              <select value={form.mode} onChange={(e) => set('mode', e.target.value)} className={selectCls}>
                <option value="chat">Chat</option>
                <option value="video">Video</option>
                <option value="both">Chat and video</option>
              </select>
            </label>

            <label className="block text-sm">
              <span className="font-medium text-slate-800">What the person reported (concerns)</span>
              <Textarea rows={3} value={form.concerns} onChange={(e) => set('concerns', e.target.value)} maxLength={3000} />
            </label>

            <label className="block text-sm">
              <span className="font-medium text-slate-800">What you observed (optional)</span>
              <Textarea rows={2} value={form.observations} onChange={(e) => set('observations', e.target.value)} maxLength={3000} />
            </label>

            <fieldset className="space-y-3">
              <legend className="text-sm font-medium text-slate-800">Risk assessment</legend>
              {RISK_QUESTIONS.map((q) => (
                <div key={q.key} className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm text-slate-700">{q.label}</span>
                  <Seg name={q.label} value={form[q.key]} onChange={(v) => set(q.key, v)} />
                </div>
              ))}
            </fieldset>

            <label className="block text-sm">
              <span className="font-medium text-slate-800">Protective factors and reasons for living</span>
              <Textarea rows={2} value={form.protective_factors} onChange={(e) => set('protective_factors', e.target.value)} maxLength={2000} />
            </label>

            <label className="block text-sm">
              <span className="font-medium text-slate-800">Your overall risk judgement</span>
              <select value={form.risk_level} onChange={(e) => set('risk_level', e.target.value)} className={selectCls}>
                <option value="">Choose</option>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </label>

            <label className="block text-sm">
              <span className="font-medium text-slate-800">Safety plan</span>
              <select value={form.safety_plan} onChange={(e) => set('safety_plan', e.target.value)} className={selectCls}>
                <option value="">Choose</option>
                <option value="not_needed">Not needed</option>
                <option value="created">Created</option>
                <option value="updated">Updated</option>
                <option value="reviewed">Reviewed</option>
              </select>
            </label>
            {form.safety_plan !== '' && form.safety_plan !== 'not_needed' && (
              <label className="flex items-center gap-3 text-sm text-slate-800">
                <input type="checkbox" checked={form.safety_plan_copy_given} onChange={(e) => set('safety_plan_copy_given', e.target.checked)} className="size-4" />
                The person received a copy of the safety plan
              </label>
            )}

            <label className="block text-sm">
              <span className="font-medium text-slate-800">Clinical impression (optional, in your own words)</span>
              <Textarea rows={2} value={form.impression} onChange={(e) => set('impression', e.target.value)} maxLength={2000} />
            </label>

            <label className="block text-sm">
              <span className="font-medium text-slate-800">Actions taken</span>
              <Textarea rows={3} value={form.actions_taken} onChange={(e) => set('actions_taken', e.target.value)} maxLength={3000} />
            </label>

            <label className="block text-sm">
              <span className="font-medium text-slate-800">Follow-up plan</span>
              <Textarea rows={2} value={form.follow_up} onChange={(e) => set('follow_up', e.target.value)} maxLength={3000} />
            </label>

            <label className="block text-sm">
              <span className="font-medium text-slate-800">Follow-up date (optional)</span>
              <input type="date" value={form.follow_up_date} min={new Date().toISOString().slice(0, 10)}
                onChange={(e) => set('follow_up_date', e.target.value)} className={selectCls} />
            </label>

            <label className="block text-sm">
              <span className="font-medium text-slate-800">Referral (optional)</span>
              <Textarea rows={2} value={form.referral} onChange={(e) => set('referral', e.target.value)} maxLength={1000} />
            </label>

            <label className="flex items-center gap-3 text-sm text-slate-800">
              <input type="checkbox" checked={form.emergency_services_contacted} onChange={(e) => set('emergency_services_contacted', e.target.checked)} className="size-4" />
              Emergency services were contacted
            </label>

            {error && <Alert>{error}</Alert>}
            <div className="flex gap-3">
              <Button type="submit" disabled={!ready || busy} loading={busy}>
                Save and end session
              </Button>
              <Button type="button" variant="secondary" onClick={() => setEnding(false)} disabled={busy}>
                Keep talking
              </Button>
            </div>
          </form>
        </Card>
      )}

      <p className="text-sm text-slate-500">
        Helplines for the person: Tele-MANAS 14416, KIRAN 1800-599-0019, emergency 112. Reading this conversation is recorded in the audit log.
      </p>
    </div>
  )
}
