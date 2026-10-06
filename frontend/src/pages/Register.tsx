import { MailCheck } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { homeFor, useAuth } from '../auth/AuthContext'
import { Alert, Button, Field, Input, Select } from '../components/ui'
import { ApiError } from '../lib/api'
import type { RegisterPayload } from '../lib/types'

function ageFrom(dob: string): number | null {
  if (!dob) return null
  const d = new Date(dob)
  if (Number.isNaN(d.getTime())) return null
  const t = new Date()
  let age = t.getFullYear() - d.getFullYear()
  if (t.getMonth() < d.getMonth() || (t.getMonth() === d.getMonth() && t.getDate() < d.getDate())) age--
  return age
}

const EMAIL = /^\S+@\S+\.\S+$/
type Errors = Partial<Record<string, string>>

export default function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [f, setF] = useState({
    full_name: '', email: '', password: '', date_of_birth: '', gender: '', occupation: '', language: 'en',
    phone: '', emergency_contact: '', guardian_name: '', guardian_email: '',
  })
  const [errors, setErrors] = useState<Errors>({})
  const [formError, setFormError] = useState('')
  const [busy, setBusy] = useState(false)
  const [sentTo, setSentTo] = useState('')
  const [today] = useState(() => new Date().toISOString().slice(0, 10))

  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF((s) => ({ ...s, [k]: e.target.value }))
  const age = useMemo(() => ageFrom(f.date_of_birth), [f.date_of_birth])
  const minor = age !== null && age >= 13 && age < 18

  function validate(): Errors {
    const e: Errors = {}
    if (!f.full_name.trim()) e.full_name = 'Enter your name.'
    if (!EMAIL.test(f.email.trim())) e.email = 'Enter a valid email address.'
    if (f.password.length < 8) e.password = 'Use at least 8 characters.'
    if (age === null) e.date_of_birth = 'Enter your date of birth.'
    else if (age < 13) e.date_of_birth = 'You need to be at least 13 to use IRIS.'
    else if (age > 100) e.date_of_birth = 'Enter a valid date of birth.'
    if (minor) {
      if (!f.guardian_name.trim()) e.guardian_name = "Enter your parent or guardian's name."
      if (!EMAIL.test(f.guardian_email.trim())) e.guardian_email = 'Enter a valid email address.'
    }
    return e
  }

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault()
    setFormError('')
    const e = validate()
    setErrors(e)
    if (Object.keys(e).length) return
    const body: RegisterPayload = { full_name: f.full_name.trim(), email: f.email.trim(), password: f.password,
      date_of_birth: f.date_of_birth, language: f.language }
    for (const k of ['gender', 'occupation', 'phone', 'emergency_contact'] as const) if (f[k].trim()) body[k] = f[k].trim()
    if (minor) { body.guardian_name = f.guardian_name.trim(); body.guardian_email = f.guardian_email.trim() }
    setBusy(true)
    try {
      const result = await register(body)
      if (result.user) navigate(homeFor(result.user), { replace: true })
      else setSentTo(body.email) // the project requires email confirmation before the first sign-in
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : 'Could not create your account.')
    } finally {
      setBusy(false)
    }
  }

  if (sentTo) {
    return (
      <div className="text-center">
        <span className="mx-auto grid size-14 place-items-center rounded-full bg-brand-100 text-brand-800">
          <MailCheck className="size-7" aria-hidden />
        </span>
        <h2 className="mt-6 font-display text-3xl font-medium text-slate-900">Check your email</h2>
        <p className="mt-3 text-slate-600">
          We sent a confirmation link to <strong className="font-medium text-slate-900">{sentTo}</strong>. Open it to
          activate your account, then sign in.
        </p>
        <p className="mt-6 text-sm text-slate-500">
          Nothing there? Check your spam folder, or wait a few minutes and try again.
        </p>
        <Link to="/login" className="mt-8 inline-flex h-11 items-center rounded-lg bg-brand-800 px-6 text-sm font-medium text-white hover:bg-brand-900">
          Go to sign in
        </Link>
      </div>
    )
  }

  return (
    <>
      <h2 className="font-display text-3xl font-medium text-slate-900">Create your account</h2>
      <p className="mt-2 text-sm text-slate-600">Everything you share stays private.</p>

      <form onSubmit={onSubmit} noValidate className="mt-8 space-y-5">
        {formError && <Alert>{formError}</Alert>}

        <Field label="Full name" error={errors.full_name}>
          {(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!errors.full_name} autoComplete="name"
            value={f.full_name} onChange={set('full_name')} autoFocus />}
        </Field>
        <Field label="Email" error={errors.email}>
          {(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!errors.email} type="email" autoComplete="email"
            inputMode="email" value={f.email} onChange={set('email')} />}
        </Field>
        <Field label="Password" hint="At least 8 characters." error={errors.password}>
          {(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!errors.password} type="password"
            autoComplete="new-password" value={f.password} onChange={set('password')} />}
        </Field>

        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Date of birth" error={errors.date_of_birth}>
            {(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!errors.date_of_birth} type="date"
              max={today} autoComplete="bday" value={f.date_of_birth} onChange={set('date_of_birth')} />}
          </Field>
          <Field label="Gender" optional>
            {(id) => (
              <Select id={id} value={f.gender} onChange={set('gender')}>
                <option value="">Prefer not to say</option>
                <option>Female</option><option>Male</option><option>Non-binary</option>
              </Select>
            )}
          </Field>
          <Field label="Occupation" optional>
            {(id) => (
              <Select id={id} value={f.occupation} onChange={set('occupation')}>
                <option value="">Select</option>
                <option>Student</option><option>Working</option><option>Other</option>
              </Select>
            )}
          </Field>
          <Field label="Preferred language">
            {(id) => (
              <Select id={id} value={f.language} onChange={set('language')}>
                <option value="en">English</option><option value="hi">Hindi</option>
                <option value="te">Telugu</option><option value="ta">Tamil</option>
              </Select>
            )}
          </Field>
        </div>

        {minor && (
          <fieldset className="space-y-5 rounded-lg border border-amber-200 bg-amber-50/60 p-4">
            <legend className="px-1 text-sm font-medium text-amber-900">Parent or guardian</legend>
            <p className="text-xs text-amber-900/80">
              Because you are under 18, a parent or guardian needs to give consent. We will contact them using these details.
            </p>
            <Field label="Their full name" error={errors.guardian_name}>
              {(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!errors.guardian_name}
                value={f.guardian_name} onChange={set('guardian_name')} />}
            </Field>
            <Field label="Their email" error={errors.guardian_email}>
              {(id, d) => <Input id={id} aria-describedby={d} aria-invalid={!!errors.guardian_email} type="email"
                value={f.guardian_email} onChange={set('guardian_email')} />}
            </Field>
          </fieldset>
        )}

        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Phone" optional>
            {(id) => <Input id={id} type="tel" autoComplete="tel" value={f.phone} onChange={set('phone')} />}
          </Field>
          <Field label="Emergency contact" optional hint="Name and phone.">
            {(id, d) => <Input id={id} aria-describedby={d} value={f.emergency_contact} onChange={set('emergency_contact')} />}
          </Field>
        </div>

        <Button type="submit" block loading={busy}>Create account</Button>
      </form>

      <p className="mt-8 text-center text-sm text-slate-600">
        Already have an account?{' '}
        <Link to="/login" className="font-medium text-brand-700 underline-offset-4 hover:underline">Sign in</Link>
      </p>
    </>
  )
}
