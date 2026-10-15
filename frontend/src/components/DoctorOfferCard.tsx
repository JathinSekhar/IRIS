import { Stethoscope } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../lib/api'
import type { DoctorOfferPrompt } from '../lib/types'
import { Alert, Button, cx } from './ui'

/**
 * IRIS offering a doctor when it sees risk (an explicit message, a High check-in, or a reviewer's suggestion). The person chooses: nothing is shared
 * until they tick the agreement and say yes, and "Not now" shares nothing. Renders nothing when there is no offer waiting.
 * `compact` is for the chat, where it must not push the helplines out of view.
 */
export default function DoctorOfferCard({
  refreshKey = 0,
  className,
  compact = false,
  onPresence,
}: {
  refreshKey?: number
  className?: string
  compact?: boolean
  onPresence?: (showing: boolean) => void
}) {
  const nav = useNavigate()
  const [offer, setOffer] = useState<DoctorOfferPrompt | null>(null)
  const [agree, setAgree] = useState(false)
  const [agreeAi, setAgreeAi] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.doctorOffer().then(setOffer).catch(() => undefined)
  }, [refreshKey])
  useEffect(() => {
    onPresence?.(offer !== null)
  }, [offer, onPresence])

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
    <div role="region" aria-label="Talk to a doctor" className={cx('rounded-2xl border border-brand-200 bg-brand-50/60', compact ? 'p-3' : 'p-4', className)}>
      <div className="flex items-start gap-3">
        <span className="grid size-8 shrink-0 place-content-center rounded-full bg-white text-brand-700 ring-1 ring-brand-200">
          <Stethoscope className="size-4" aria-hidden />
        </span>
        <div className="min-w-0 flex-1 space-y-2">
          <p className="text-sm text-slate-800">
            <span className="font-semibold text-slate-900">{offer.title}</span>{' '}
            {compact ? 'A doctor on the IRIS team may not be able to answer straight away.' : offer.body}
          </p>
          <label className="flex items-start gap-2 text-xs text-slate-700">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-0.5 size-4" />
            <span>I agree to share my recent messages and check-in answers with the doctor who accepts.</span>
          </label>
          {!compact && (
            <label className={cx('flex items-start gap-2 text-xs', agree ? 'text-slate-600' : 'text-slate-400')}>
              <input type="checkbox" checked={agreeAi} disabled={!agree} onChange={(e) => setAgreeAi(e.target.checked)} className="mt-0.5 size-4" />
              <span>Optional: an AI tool may draft a short summary of this for the doctor (no name or contact details).</span>
            </label>
          )}
          {error && <Alert>{error}</Alert>}
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void yes()} disabled={!agree || busy} loading={busy} className={compact ? 'h-9 px-3 text-sm' : undefined}>
              Yes, find a doctor
            </Button>
            <Button variant="secondary" onClick={() => void notNow()} disabled={busy} className={compact ? 'h-9 px-3 text-sm' : undefined}>
              Not now
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
