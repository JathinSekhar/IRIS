import { MailCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Alert, Button, Field, Input } from '../components/ui'
import { api, ApiError } from '../lib/api'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) return setError('Enter a valid email address.')
    setBusy(true)
    try {
      await api.forgotPassword(email.trim())
      setSent(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send the email.')
    } finally {
      setBusy(false)
    }
  }

  if (sent) {
    return (
      <div className="text-center">
        <span className="mx-auto grid size-14 place-items-center rounded-full bg-brand-100 text-brand-800">
          <MailCheck className="size-7" aria-hidden />
        </span>
        <h2 className="mt-6 font-display text-3xl font-medium text-slate-900">Check your email</h2>
        <p className="mt-3 text-slate-600">
          If an account exists for <strong className="font-medium text-slate-900">{email.trim()}</strong>, we have sent a
          link to choose a new password.
        </p>
        <Link to="/login" className="mt-8 inline-block text-sm font-medium text-brand-700 underline-offset-4 hover:underline">
          Back to sign in
        </Link>
      </div>
    )
  }

  return (
    <>
      <h2 className="font-display text-3xl font-medium text-slate-900">Reset your password</h2>
      <p className="mt-2 text-sm text-slate-600">Enter your email and we will send you a reset link.</p>
      <form onSubmit={onSubmit} noValidate className="mt-8 space-y-5">
        {error && <Alert>{error}</Alert>}
        <Field label="Email">
          {(id) => (
            <Input id={id} type="email" autoComplete="email" inputMode="email" value={email}
              onChange={(e) => setEmail(e.target.value)} autoFocus />
          )}
        </Field>
        <Button type="submit" block loading={busy}>Send reset link</Button>
      </form>
      <p className="mt-8 text-center text-sm text-slate-600">
        <Link to="/login" className="font-medium text-brand-700 underline-offset-4 hover:underline">Back to sign in</Link>
      </p>
    </>
  )
}
