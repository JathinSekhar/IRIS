import { ArrowLeft } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import ConsultThread from '../components/ConsultThread'
import { Alert, Button, Card, Textarea } from '../components/ui'
import { api, ApiError } from '../lib/api'
import type { SessionNote, SessionNoteInput } from '../lib/types'

const RISK_LABEL: Record<string, string> = { low: 'Low', medium: 'Medium', high: 'High' }
const MODE_LABEL: Record<string, string> = { chat: 'Chat', video: 'Video', both: 'Chat and video' }

const EMPTY: SessionNoteInput = {
  mode: 'chat', concerns: '', risk_level: 'low', actions_taken: '', follow_up: '', referral: '', emergency_services_contacted: false,
}

function NoteView({ n }: { n: SessionNote }) {
  const row = (label: string, value: string) => (
    <p>
      <span className="font-semibold text-slate-900">{label}.</span> {value}
    </p>
  )
  return (
    <Card className="space-y-2 p-5 text-sm text-slate-700">
      <h2 className="font-medium text-slate-900">Session note</h2>
      {row('Mode', MODE_LABEL[n.mode] ?? n.mode)}
      {row('Concerns', n.concerns)}
      {row('Risk judgement', RISK_LABEL[n.risk_level] ?? n.risk_level)}
      {row('Actions taken', n.actions_taken)}
      {row('Follow-up', n.follow_up)}
      {n.referral && row('Referral', n.referral)}
      {row('Emergency services contacted', n.emergency_services_contacted ? 'Yes' : 'No')}
    </Card>
  )
}

/** One case: the conversation, and the session form that is required to end it. */
export default function DoctorCaseView() {
  const id = Number(useParams().id)
  const nav = useNavigate()
  const [note, setNote] = useState<SessionNote | null | undefined>(undefined)
  const [form, setForm] = useState<SessionNoteInput>(EMPTY)
  const [ending, setEnding] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const loadNote = useCallback(() => {
    api.doctorCaseNote(id).then(setNote).catch(() => setNote(null))
  }, [id])
  useEffect(() => {
    if (Number.isFinite(id)) loadNote()
  }, [id, loadNote])

  if (!Number.isFinite(id)) return null
  const set = <K extends keyof SessionNoteInput>(k: K, v: SessionNoteInput[K]) => setForm((f) => ({ ...f, [k]: v }))
  const ready = form.concerns.trim().length >= 3 && form.actions_taken.trim().length >= 3 && form.follow_up.trim().length >= 3

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!ready || busy) return
    setBusy(true)
    setError('')
    try {
      await api.closeCase(id, { ...form, referral: form.referral?.trim() || null })
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
          <form onSubmit={(e) => void submit(e)} className="space-y-4">
            <h2 className="font-medium text-slate-900">Session form</h2>
            <p className="text-sm text-slate-600">All fields except referral are required. The person does not see this note.</p>

            <label className="block text-sm">
              <span className="font-medium text-slate-800">How did you speak?</span>
              <select value={form.mode} onChange={(e) => set('mode', e.target.value as SessionNoteInput['mode'])}
                className="mt-1 block h-11 w-full rounded-lg border border-slate-300 bg-white px-3">
                <option value="chat">Chat</option>
                <option value="video">Video</option>
                <option value="both">Chat and video</option>
              </select>
            </label>

            <label className="block text-sm">
              <span className="font-medium text-slate-800">Concerns discussed</span>
              <Textarea rows={3} value={form.concerns} onChange={(e) => set('concerns', e.target.value)} maxLength={3000} />
            </label>

            <label className="block text-sm">
              <span className="font-medium text-slate-800">Your risk judgement</span>
              <select value={form.risk_level} onChange={(e) => set('risk_level', e.target.value as SessionNoteInput['risk_level'])}
                className="mt-1 block h-11 w-full rounded-lg border border-slate-300 bg-white px-3">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
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
              <span className="font-medium text-slate-800">Referral (optional)</span>
              <Textarea rows={2} value={form.referral ?? ''} onChange={(e) => set('referral', e.target.value)} maxLength={1000} />
            </label>

            <label className="flex items-center gap-3 text-sm text-slate-800">
              <input type="checkbox" checked={form.emergency_services_contacted} onChange={(e) => set('emergency_services_contacted', e.target.checked)}
                className="size-4" />
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
