import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Alert, Button, Field, Input } from '../components/ui'
import { api, ApiError } from '../lib/api'

/** Supabase sends people here from the reset email with the one-time token in the URL fragment (#access_token=...). */
function readToken(): string | null {
  const p = new URLSearchParams(window.location.hash.replace(/^#/, ''))
  return p.get('type') === 'recovery' ? p.get('access_token') : null
}

export default function ResetPassword() {
  const navigate = useNavigate()
  const [token] = useState(readToken)
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  // Remove the token from the address bar and history as soon as it has been read.
  useEffect(() => {
    if (window.location.hash) window.history.replaceState(null, '', window.location.pathname)
  }, [])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    if (password.length < 8) return setError('Use at least 8 characters.')
    if (password !== confirm) return setError('The two passwords do not match.')
    setBusy(true)
    try {
      await api.resetPassword(token!, password)
      navigate('/login?reset=1', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not change your password.')
    } finally {
      setBusy(false)
    }
  }

  if (!token) {
    return (
      <>
        <h2 className="font-display text-3xl font-medium text-slate-900">This link is not valid</h2>
        <p className="mt-3 text-slate-600">The reset link is missing, already used, or has expired. Request a new one.</p>
        <Link to="/forgot-password" className="mt-8 inline-flex h-11 items-center rounded-lg bg-brand-800 px-6 text-sm font-medium text-white hover:bg-brand-900">
          Send a new link
        </Link>
      </>
    )
  }

  return (
    <>
      <h2 className="font-display text-3xl font-medium text-slate-900">Choose a new password</h2>
      <form onSubmit={onSubmit} noValidate className="mt-8 space-y-5">
        {error && <Alert>{error}</Alert>}
        <Field label="New password" hint="At least 8 characters.">
          {(id, d) => (
            <Input id={id} aria-describedby={d} type="password" autoComplete="new-password" value={password}
              onChange={(e) => setPassword(e.target.value)} autoFocus />
          )}
        </Field>
        <Field label="Confirm new password">
          {(id) => (
            <Input id={id} type="password" autoComplete="new-password" value={confirm}
              onChange={(e) => setConfirm(e.target.value)} />
          )}
        </Field>
        <Button type="submit" block loading={busy}>Change password</Button>
      </form>
    </>
  )
}
