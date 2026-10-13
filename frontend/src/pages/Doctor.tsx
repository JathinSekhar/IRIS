import { Stethoscope } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Alert, Card, Spinner, cx } from '../components/ui'
import { api, ApiError } from '../lib/api'
import type { DoctorMe } from '../lib/types'

/** The doctor's home: who they are on IRIS, and the one switch that decides whether cases may be offered to them. */
export default function Doctor() {
  const [me, setMe] = useState<DoctorMe | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.doctorMe().then(setMe).catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load your profile.'))
  }, [])

  async function toggle() {
    if (!me || busy) return
    setBusy(true)
    setError('')
    try {
      setMe(await api.doctorAvailability(!me.on_duty))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not change your availability.')
    } finally {
      setBusy(false)
    }
  }

  if (!me && !error) return <Spinner />
  return (
    <div className="mx-auto max-w-2xl space-y-6 py-8">
      <div className="flex items-center gap-3">
        <span className="grid size-11 place-content-center rounded-xl bg-brand-50 text-brand-700">
          <Stethoscope className="size-5" aria-hidden />
        </span>
        <div>
          <h1 className="font-display text-2xl font-medium text-slate-900">Doctor</h1>
          {me && <p className="text-sm text-slate-600">{me.full_name}</p>}
        </div>
      </div>

      {error && <Alert>{error}</Alert>}

      {me && (
        <>
          <Card className="space-y-4 p-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="font-semibold text-slate-900">{me.on_duty ? 'You are on duty' : 'You are off duty'}</p>
                <p className="text-sm text-slate-600">
                  {me.on_duty
                    ? 'New cases can be offered to you. You will choose whether to accept each one.'
                    : 'No cases will be offered to you until you go on duty.'}
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={me.on_duty}
                aria-label="On duty"
                disabled={busy}
                onClick={() => void toggle()}
                className={cx(
                  'relative h-7 w-12 shrink-0 rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600',
                  me.on_duty ? 'bg-brand-700' : 'bg-slate-300',
                  busy && 'opacity-60',
                )}
              >
                <span className={cx('absolute top-0.5 size-6 rounded-full bg-white shadow transition-all', me.on_duty ? 'left-[22px]' : 'left-0.5')} />
              </button>
            </div>
          </Card>

          <Card className="space-y-2 p-6 text-sm text-slate-700">
            <p><span className="font-semibold text-slate-900">Specialty.</span> {me.specialty}</p>
            <p><span className="font-semibold text-slate-900">Registration.</span> {me.registration_number}</p>
            <p><span className="font-semibold text-slate-900">Languages.</span> {me.languages.join(', ') || 'Not set'}</p>
          </Card>

          <p className="text-sm text-slate-500">
            Case offers will appear here once the next step is built. IRIS does not verify registration numbers; this is a test account.
          </p>
        </>
      )}
    </div>
  )
}
