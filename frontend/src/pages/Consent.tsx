import { Clock, Lock, SkipForward, Stethoscope, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { homeFor, useAuth } from '../auth/AuthContext'
import { Alert, Button, Card } from '../components/ui'
import { api, ApiError } from '../lib/api'
import { CONSENT_VERSION } from '../lib/questionnaire'

const POINTS: { icon: LucideIcon; title: string; text: string }[] = [
  { icon: Clock, title: 'About 6 minutes', text: 'Around 30 questions. You can stop and come back at any time.' },
  { icon: Lock, title: 'Confidential', text: 'Only trained reviewers can see your answers. They are never shown to other users.' },
  {
    icon: Stethoscope,
    title: 'The questions doctors ask',
    text: 'Based on PHQ-9, GAD-7 and the C-SSRS screener. This is a screening, not a diagnosis.',
  },
  { icon: SkipForward, title: 'Your choice', text: 'You can skip any question, or the whole check-in, and still use IRIS.' },
]

export default function Consent() {
  const { user, setUser } = useAuth()
  const navigate = useNavigate()
  const [agreed, setAgreed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function accept() {
    setBusy(true)
    setError('')
    try {
      const u = await api.acceptConsent(CONSENT_VERSION)
      setUser(u)
      navigate(homeFor(u), { replace: true })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not save your consent.')
    } finally {
      setBusy(false)
    }
  }

  if (user?.consent_accepted && !busy) return <Navigate to={homeFor(user)} replace />

  return (
    <Card className="p-6 sm:p-10">
      <p className="text-sm font-medium text-brand-700">Before we begin</p>
      <h1 className="mt-1 font-display text-3xl font-medium text-slate-900">
        Hi {user?.first_name}, a short check-in
      </h1>
      <p className="mt-3 text-slate-600">
        We would like to understand how you have been doing, the way a doctor would at a first visit. It helps IRIS and the
        people reviewing it support you better.
      </p>

      <ul className="mt-8 grid gap-4 sm:grid-cols-2">
        {POINTS.map(({ icon: Icon, title, text }) => (
          <li key={title} className="flex gap-3 rounded-lg border border-slate-200 p-4">
            <Icon className="mt-0.5 size-5 shrink-0 text-brand-700" aria-hidden />
            <div>
              <p className="text-sm font-medium text-slate-900">{title}</p>
              <p className="mt-1 text-sm text-slate-600">{text}</p>
            </div>
          </li>
        ))}
      </ul>

      {user?.is_minor && (
        <div className="mt-6">
          <Alert tone="info">
            A parent or guardian consent request is pending. You can continue while we wait for their reply.
          </Alert>
        </div>
      )}

      <label className="mt-8 flex cursor-pointer items-start gap-3 text-sm text-slate-800">
        <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)}
          className="mt-0.5 size-4.5 rounded border-slate-300 accent-brand-800" />
        <span>
          I understand that IRIS is a screening and support tool, not a medical diagnosis, and I agree to my answers being
          stored and reviewed by trained staff.
        </span>
      </label>

      {error && <div className="mt-4"><Alert>{error}</Alert></div>}

      <div className="mt-8">
        <Button onClick={accept} disabled={!agreed} loading={busy} block className="sm:w-auto">
          Agree and continue
        </Button>
      </div>
    </Card>
  )
}
