import { Eye, EyeOff } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { homeFor, useAuth } from '../auth/AuthContext'
import { Alert, Button, Field, Input } from '../components/ui'
import { ApiError } from '../lib/api'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const confirmed = params.get('confirmed') === '1'
  const reset = params.get('reset') === '1'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) return setError('Enter a valid email address.')
    if (!password) return setError('Enter your password.')
    setBusy(true)
    try {
      const u = await login(email.trim(), password)
      navigate(homeFor(u), { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not sign in.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h2 className="font-display text-3xl font-medium text-slate-900">Welcome back</h2>
      <p className="mt-2 text-sm text-slate-600">Sign in to continue to IRIS.</p>

      <form onSubmit={onSubmit} noValidate className="mt-8 space-y-5">
        {confirmed && !error && <Alert tone="info">Your email is confirmed. Sign in to continue.</Alert>}
        {reset && !error && <Alert tone="info">Your password has been changed. Sign in with the new one.</Alert>}
        {error && <Alert>{error}</Alert>}
        <Field label="Email">
          {(id) => (
            <Input id={id} type="email" autoComplete="email" inputMode="email" placeholder="name@example.com"
              value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
          )}
        </Field>
        <Field label="Password">
          {(id) => (
            <div className="relative">
              <Input id={id} type={show ? 'text' : 'password'} autoComplete="current-password" className="pr-11"
                value={password} onChange={(e) => setPassword(e.target.value)} />
              <button type="button" onClick={() => setShow((s) => !s)}
                aria-label={show ? 'Hide password' : 'Show password'} aria-pressed={show}
                className="absolute inset-y-0 right-0 grid w-11 place-items-center text-slate-500 hover:text-slate-800">
                {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          )}
        </Field>
        <div className="text-right">
          <Link to="/forgot-password" className="text-sm font-medium text-brand-700 underline-offset-4 hover:underline">
            Forgot password?
          </Link>
        </div>
        <Button type="submit" block loading={busy}>Sign in</Button>
      </form>

      <p className="mt-8 text-center text-sm text-slate-600">
        New to IRIS?{' '}
        <Link to="/register" className="font-medium text-brand-700 underline-offset-4 hover:underline">
          Create an account
        </Link>
      </p>
    </>
  )
}
