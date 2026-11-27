import { CalendarClock, ChevronDown, ClipboardCheck, Lock, ShieldCheck, Stethoscope, UserRound, Video } from 'lucide-react'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Alert, Button, Card, cx, Field, Input, Select, Spinner } from '../components/ui'
import { api, ApiError } from '../lib/api'
import type { ConsultHistory, Profile as ProfileData, ProfileInput, ThreadMessage } from '../lib/types'

// The same choices as the sign-up form.
const GENDERS = ['Female', 'Male', 'Non-binary']
const OCCUPATIONS = ['Student', 'Working', 'Other']
const LANGUAGES: [string, string][] = [['en', 'English'], ['hi', 'Hindi'], ['te', 'Telugu'], ['ta', 'Tamil']]

const fmtDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' }) : null

const toForm = (p: ProfileData): ProfileInput => ({
  full_name: p.full_name, gender: p.gender ?? '', occupation: p.occupation ?? '', language: p.language,
  phone: p.phone ?? '', emergency_contact: p.emergency_contact ?? '',
})

/** A choice list that also keeps a value saved earlier that is no longer offered, so saving never changes it silently. */
function withCurrent(options: string[], current: string | null) {
  return current && !options.includes(current) ? [...options, current] : options
}

function Section({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <Card className="p-6">
      <h2 className="flex items-center gap-2.5 font-medium text-slate-900">
        <span className="grid size-8 place-items-center rounded-lg bg-brand-50 text-brand-700 ring-1 ring-brand-100">{icon}</span>
        {title}
      </h2>
      <div className="mt-5">{children}</div>
    </Card>
  )
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 py-2.5 sm:flex-row sm:gap-4">
      <dt className="w-40 shrink-0 text-sm text-slate-500">{label}</dt>
      <dd className="text-sm text-slate-900">{value}</dd>
    </div>
  )
}

const fmtDateTime = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' })

const STATE: Record<ConsultHistory['state'], [string, string]> = {
  open: ['Waiting for a doctor', 'bg-amber-50 text-amber-800 ring-amber-200'],
  accepted: ['Doctor accepted', 'bg-sky-50 text-sky-800 ring-sky-200'],
  in_session: ['In progress', 'bg-brand-50 text-brand-800 ring-brand-200'],
  closed: ['Ended', 'bg-slate-100 text-slate-700 ring-slate-200'],
  cancelled: ['Cancelled', 'bg-slate-50 text-slate-500 ring-slate-200'],
}

/** The conversation with the doctor, read-only. The person's own view: no flags and no clinical note. */
function Conversation({ id }: { id: number }) {
  const [rows, setRows] = useState<ThreadMessage[] | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api.consultMessages(id).then(setRows).catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load the conversation.'))
  }, [id])
  if (error) return <Alert>{error}</Alert>
  if (!rows) return <p className="text-sm text-slate-500">Loading the conversation...</p>
  if (rows.length === 0) return <p className="text-sm text-slate-500">No messages were written in this conversation.</p>
  return (
    <ul className="max-h-80 space-y-2 overflow-y-auto rounded-xl bg-slate-50 p-3">
      {rows.map((m) => (
        <li key={m.id} className={m.mine ? 'flex justify-end' : 'flex justify-start'}>
          <div className={m.mine ? 'max-w-[80%] rounded-2xl rounded-br-md bg-brand-800 px-3.5 py-2 text-sm text-white' : 'max-w-[80%] rounded-2xl rounded-bl-md bg-white px-3.5 py-2 text-sm text-slate-800 ring-1 ring-slate-200'}>
            <p className="whitespace-pre-wrap break-words">{m.text}</p>
            <p className={m.mine ? 'mt-1 text-[11px] text-brand-100' : 'mt-1 text-[11px] text-slate-400'}>{fmtDateTime(m.created_at)}</p>
          </div>
        </li>
      ))}
    </ul>
  )
}

function Appointment({ c }: { c: ConsultHistory }) {
  const [open, setOpen] = useState(false)
  const [label, tone] = STATE[c.state]
  const live = c.state === 'open' || c.state === 'accepted' || c.state === 'in_session'
  return (
    <li className="rounded-xl border border-slate-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium text-slate-900">{c.doctor_name ?? (c.state === 'cancelled' ? 'No doctor (request cancelled)' : 'No doctor yet')}</p>
          {c.doctor_name && (
            <p className="mt-0.5 text-xs text-slate-500">
              {c.doctor_specialty ? `${c.doctor_specialty} · ` : ''}Registration number: {c.doctor_registration_number}
            </p>
          )}
          <p className="mt-2 text-sm text-slate-600">
            Requested {fmtDateTime(c.requested_at)}
            {c.ended_at && c.state === 'closed' && <> · ended {fmtDateTime(c.ended_at)}</>}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
            <span>{c.message_count} message{c.message_count === 1 ? '' : 's'}</span>
            {c.video_used && <span className="inline-flex items-center gap-1"><Video className="size-3.5" aria-hidden /> Video call</span>}
          </p>
        </div>
        <span className={cx('shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset', tone)}>{label}</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-3">
        {live && <Link to="/talk-to-a-doctor" className="text-sm font-semibold text-brand-700 hover:underline">Go to this request</Link>}
        {c.message_count > 0 && (
          <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open}
            className="inline-flex items-center gap-1 text-sm font-semibold text-brand-700 hover:underline">
            {open ? 'Hide conversation' : 'View conversation'}
            <ChevronDown className={cx('size-4 transition-transform', open && 'rotate-180')} aria-hidden />
          </button>
        )}
      </div>
      {open && <div className="mt-3"><Conversation id={c.id} /></div>}
    </li>
  )
}

function Appointments() {
  const [rows, setRows] = useState<ConsultHistory[] | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api.consultHistory().then(setRows).catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load your appointments.'))
  }, [])
  if (error) return <Alert>{error}</Alert>
  if (!rows) return <p className="text-sm text-slate-500">Loading...</p>
  if (rows.length === 0) {
    return (
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-slate-700">You have not talked to a doctor on IRIS yet.</p>
        <Link to="/talk-to-a-doctor" className="inline-flex h-10 shrink-0 items-center rounded-lg border border-brand-800 px-4 text-sm font-medium text-brand-800 hover:bg-brand-50">
          Ask for a doctor
        </Link>
      </div>
    )
  }
  return <ul className="space-y-3">{rows.map((c) => <Appointment key={c.id} c={c} />)}</ul>
}

/** The person's own details. They can change how they are described and reached; sign-in and age details stay as they are. */
export default function Profile() {
  const { user, refresh } = useAuth()
  const [profile, setProfile] = useState<ProfileData | null>(null)
  const [form, setForm] = useState<ProfileInput | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api.profile()
      .then((p) => { setProfile(p); setForm(toForm(p)) })
      .catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load your profile.'))
  }, [])

  if (!profile || !form || !user) return error ? <Alert>{error}</Alert> : <Spinner />

  const changed = JSON.stringify(form) !== JSON.stringify(toForm(profile))
  const set = (k: keyof ProfileInput) => (e: { target: { value: string } }) => {
    setSaved(false)
    setForm({ ...form, [k]: e.target.value })
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    if (!form) return
    if (!form.full_name.trim()) { setError('Enter your name.'); return }
    setBusy(true)
    setError('')
    try {
      const p = await api.updateProfile(form)
      setProfile(p)
      setForm(toForm(p))
      setSaved(true)
      void refresh()                                            // the header shows the new name
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Your changes were not saved. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  const initial = (profile.full_name.split(/\s+/).find((w) => !w.endsWith('.')) ?? profile.full_name).charAt(0).toUpperCase()
  const { checkin } = user

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div className="flex items-center gap-4">
        <span aria-hidden className="grid size-16 shrink-0 place-items-center rounded-full bg-brand-100 font-display text-2xl font-semibold text-brand-800">
          {initial}
        </span>
        <div>
          <h1 className="font-display text-3xl font-medium text-slate-900">{profile.full_name}</h1>
          <p className="mt-1 text-sm text-slate-500">Member since {fmtDate(profile.member_since)}</p>
        </div>
      </div>

      <Section icon={<UserRound className="size-4" aria-hidden />} title="Your details">
        <form onSubmit={(e) => void save(e)} className="space-y-4" noValidate>
          <Field label="Full name">
            {(id) => <Input id={id} value={form.full_name} onChange={set('full_name')} maxLength={120} autoComplete="name" />}
          </Field>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Gender" optional>
              {(id) => (
                <Select id={id} value={form.gender ?? ''} onChange={set('gender')}>
                  <option value="">Prefer not to say</option>
                  {withCurrent(GENDERS, profile.gender).map((g) => <option key={g}>{g}</option>)}
                </Select>
              )}
            </Field>
            <Field label="Occupation" optional>
              {(id) => (
                <Select id={id} value={form.occupation ?? ''} onChange={set('occupation')}>
                  <option value="">Select</option>
                  {withCurrent(OCCUPATIONS, profile.occupation).map((o) => <option key={o}>{o}</option>)}
                </Select>
              )}
            </Field>
            <Field label="Preferred language">
              {(id) => (
                <Select id={id} value={form.language} onChange={set('language')}>
                  {LANGUAGES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  {!LANGUAGES.some(([v]) => v === profile.language) && <option value={profile.language}>{profile.language}</option>}
                </Select>
              )}
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Phone" optional>
              {(id) => <Input id={id} value={form.phone ?? ''} onChange={set('phone')} maxLength={32} type="tel" autoComplete="tel" />}
            </Field>
            <Field label="Emergency contact" optional hint="Name and phone.">
              {(id, d) => <Input id={id} aria-describedby={d} value={form.emergency_contact ?? ''} onChange={set('emergency_contact')} maxLength={200} />}
            </Field>
          </div>
          {error && <Alert>{error}</Alert>}
          {saved && !changed && <Alert tone="info">Your details are saved.</Alert>}
          <div className="flex flex-wrap items-center gap-3 pt-1">
            <Button type="submit" loading={busy} disabled={!changed || busy}>Save changes</Button>
            {changed && (
              <Button type="button" variant="ghost" onClick={() => { setForm(toForm(profile)); setError('') }} disabled={busy}>
                Undo
              </Button>
            )}
          </div>
        </form>
      </Section>

      <Section icon={<Lock className="size-4" aria-hidden />} title="Sign-in and age">
        <dl className="divide-y divide-slate-100">
          <Row label="Email" value={profile.email} />
          <Row label="Date of birth" value={`${fmtDate(profile.date_of_birth)} (${profile.age})`} />
          {profile.is_minor && (
            <>
              <Row label="Parent or guardian" value={`${profile.guardian_name ?? ''}${profile.guardian_email ? `, ${profile.guardian_email}` : ''}`} />
              <Row label="Guardian consent" value={profile.guardian_consent_status === 'granted' ? 'Given' : 'Waiting'} />
            </>
          )}
        </dl>
        <p className="mt-3 text-xs text-slate-500">These details are used for signing in and for the rules for people under 18, so they cannot be changed here.</p>
      </Section>

      <Section icon={<Stethoscope className="size-4" aria-hidden />} title="Your doctor appointments">
        <Appointments />
      </Section>

      <Section icon={<ClipboardCheck className="size-4" aria-hidden />} title="Health check-in">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-slate-700">
            {checkin.last_completed_at ? `Last completed ${fmtDate(checkin.last_completed_at)}.` : 'You have not completed a check-in yet.'}
            {checkin.state === 'ok' && checkin.next_due_at && (
              <span className="mt-1 flex items-center gap-1.5 text-slate-500">
                <CalendarClock className="size-4" aria-hidden /> Next one due {fmtDate(checkin.next_due_at)}
              </span>
            )}
          </p>
          {checkin.state !== 'ok' && (
            <Link to="/check-in" className="inline-flex h-10 shrink-0 items-center rounded-lg bg-brand-800 px-4 text-sm font-medium text-white hover:bg-brand-900">
              {checkin.last_completed_at ? 'Update my check-in' : 'Start check-in'}
            </Link>
          )}
        </div>
      </Section>

      <Section icon={<ShieldCheck className="size-4" aria-hidden />} title="Privacy">
        <p className="text-sm text-slate-700">
          {profile.consent_accepted_at ? `You agreed to the IRIS terms on ${fmtDate(profile.consent_accepted_at)}.` : 'You have not agreed to the current IRIS terms yet.'}{' '}
          Your answers and messages are read by trained reviewers, and by a doctor only if you ask for one and agree to share.
        </p>
      </Section>
    </div>
  )
}
