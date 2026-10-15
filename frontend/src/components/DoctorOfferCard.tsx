import { Stethoscope } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../lib/api'
import type { DoctorOfferPrompt } from '../lib/types'
import { Alert, Button, cx } from './ui'

/**
 * IRIS offering a doctor when it sees risk (an explicit message, a High check-in, or a reviewer's suggestion). The person chooses: nothing is shared
 * until they tick the agreement and say yes, and "Not now" shares nothing. Renders nothing when there is no offer waiting.
 */
export default function DoctorOfferCard({ refreshKey = 0, className }: { refreshKey?: number; className?: string }) {
  const nav = useNavigate()
  const [offer, setOffer] = useState<DoctorOfferPrompt | null>(null)
  const [agree, setAgree] = useState(false)
  const [agreeAi, setAgreeAi] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.doctorOffer().then(setOffer).catch(() => undefined)
  }, [refreshKey])

  if (!offer) return null

  async function yes() {
    if (!offer) return
    setBusy(true)
    setError('')
    try {
      await api.requestDoctor(true, agreeAi, offer.id)
      nav('/talk-to-a-doctor')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Your request was not sent. Please try again.')
      setBusy(false)
    }
  }

  async function notNow() {
    if (!offer) return
    setBusy(true)
    await api.dismissOffer(offer.id).catch(() => undefined)
    setOffer(null)
    setBusy(false)
  }

  return (
    <div role="region" aria-label="Talk to a doctor" className={cx('rounded-2xl border border-brand-200 bg-brand-50/60 p-4', className)}>
      <div className="flex items-start gap-3">
        <span className="grid size-9 shrink-0 place-content-center rounded-full bg-white text-brand-700 ring-1 ring-brand-200">
          <Stethoscope className="size-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1 space-y-3">
          <div>
            <p className="font-semibold text-slate-900">{offer.title}</p>
            <p className="mt-1 text-sm text-slate-700">{offer.body}</p>
          </div>
          <label className="flex items-start gap-2.5 text-sm text-slate-800">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-0.5 size-4" />
            <span>I agree to share my recent messages and check-in answers with the doctor who accepts.</span>
          </label>
          <label className={cx('flex items-start gap-2.5 text-sm', agree ? 'text-slate-700' : 'text-slate-400')}>
            <input type="checkbox" checked={agreeAi} disabled={!agree} onChange={(e) => setAgreeAi(e.target.checked)} className="mt-0.5 size-4" />
            <span>Optional: an AI tool may draft a short summary of this for the doctor (no name or contact details).</span>
          </label>
          {error && <Alert>{error}</Alert>}
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void yes()} disabled={!agree || busy} loading={busy}>
              Yes, find a doctor
            </Button>
            <Button variant="secondary" onClick={() => void notNow()} disabled={busy}>
              Not now
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
