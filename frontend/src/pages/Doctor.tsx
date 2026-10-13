import { AlertTriangle, Stethoscope } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Alert, Button, Card, Spinner, cx } from '../components/ui'
import { api, ApiError } from '../lib/api'
import type { DoctorCase, DoctorMe, DoctorOffer } from '../lib/types'

const PRIORITY_STYLE: Record<string, string> = {
  high: 'bg-red-50 text-red-800 ring-red-200',
  medium: 'bg-amber-50 text-amber-800 ring-amber-200',
  low: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
}

const when = (iso: string) => new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

function OfferCard({ o, busy, onAccept, onDecline }: { o: DoctorOffer; busy: boolean; onAccept: () => void; onDecline: () => void }) {
  return (
    <Card className="space-y-4 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-slate-900">{o.first_name}</span>
        <span className="text-sm text-slate-500">asked {when(o.created_at)}</span>
        {o.urgent && (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-600 px-2.5 py-0.5 text-xs font-semibold text-white">
            <AlertTriangle className="size-3.5" aria-hidden /> Urgent message
          </span>
        )}
        {o.is_minor && (
          <span className="inline-flex rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-900 ring-1 ring-inset ring-amber-200">
            Under 18
          </span>
        )}
        {o.priority && (
          <span className={cx('inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ring-1 ring-inset', PRIORITY_STYLE[o.priority])}>
            {o.priority} priority
          </span>
        )}
      </div>

      {o.recent_messages.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Recent messages (shared with consent)</p>
          {o.recent_messages.map((m, i) => (
            <p key={i} className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-800">
              {m.text}
              <span className="ml-2 text-xs text-slate-400">{when(m.created_at)}</span>
            </p>
          ))}
        </div>
      )}

      {o.checkin && (
        <p className="text-sm text-slate-700">
          <span className="font-semibold text-slate-900">Latest check-in.</span> Baseline {o.checkin.baseline_risk}
          {o.checkin.phq9 !== null && <>, PHQ-9 {o.checkin.phq9}</>}
          {o.checkin.gad7 !== null && <>, GAD-7 {o.checkin.gad7}</>}
          {o.checkin.safety_flag && <>, safety flag raised</>}.
        </p>
      )}

      <div className="flex gap-3">
        <Button onClick={onAccept} loading={busy} disabled={busy}>Accept</Button>
        <Button variant="secondary" onClick={onDecline} disabled={busy}>Pass</Button>
      </div>
    </Card>
  )
}

/** The doctor's home: the duty switch, open requests they can accept, and the cases they own. */
export default function Doctor() {
  const [me, setMe] = useState<DoctorMe | null>(null)
  const [offers, setOffers] = useState<DoctorOffer[]>([])
  const [cases, setCases] = useState<DoctorCase[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<number | 'duty' | null>(null)

  const refresh = useCallback(() => {
    Promise.all([api.doctorOffers(), api.doctorCases()])
      .then(([o, c]) => {
        setOffers(o)
        setCases(c)
      })
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    api.doctorMe().then(setMe).catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load your profile.'))
    refresh()
    const t = window.setInterval(refresh, 5000)
    return () => window.clearInterval(t)
  }, [refresh])

  async function act(id: number, fn: () => Promise<unknown>) {
    setBusy(id)
    setError('')
    try {
      await fn()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'That did not work. Please try again.')
    } finally {
      setBusy(null)
      refresh()
    }
  }

  async function toggle() {
    if (!me || busy) return
    setBusy('duty')
    setError('')
    try {
      setMe(await api.doctorAvailability(!me.on_duty))
      refresh()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not change your availability.')
    } finally {
      setBusy(null)
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
          <Card className="p-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="font-semibold text-slate-900">{me.on_duty ? 'You are on duty' : 'You are off duty'}</p>
                <p className="text-sm text-slate-600">
                  {me.on_duty ? 'Open requests appear below. You choose whether to accept each one.' : 'No requests are shown to you until you go on duty.'}
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={me.on_duty}
                aria-label="On duty"
                disabled={busy === 'duty'}
                onClick={() => void toggle()}
                className={cx(
                  'relative h-7 w-12 shrink-0 rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600',
                  me.on_duty ? 'bg-brand-700' : 'bg-slate-300',
                  busy === 'duty' && 'opacity-60',
                )}
              >
                <span className={cx('absolute top-0.5 size-6 rounded-full bg-white shadow transition-all', me.on_duty ? 'left-[22px]' : 'left-0.5')} />
              </button>
            </div>
          </Card>

          {me.on_duty && (
            <section className="space-y-3" aria-label="Open requests">
              <h2 className="font-medium text-slate-900">Open requests{offers.length > 0 && ` (${offers.length})`}</h2>
              {offers.length === 0 && <p className="text-sm text-slate-500">No one is waiting right now. This list refreshes by itself.</p>}
              {offers.map((o) => (
                <OfferCard
                  key={o.case_id}
                  o={o}
                  busy={busy === o.case_id}
                  onAccept={() => void act(o.case_id, () => api.acceptOffer(o.case_id))}
                  onDecline={() => void act(o.case_id, () => api.declineOffer(o.case_id))}
                />
              ))}
            </section>
          )}

          {cases.some((c) => c.state === 'closed') && (
            <section className="space-y-2" aria-label="Closed cases">
              <h2 className="font-medium text-slate-900">Closed</h2>
              {cases.filter((c) => c.state === 'closed').map((c) => (
                <Card key={c.case_id} className="flex items-center justify-between gap-3 p-3 text-sm text-slate-600">
                  <span>{c.first_name}, case {c.case_id}</span>
                  <Link to={`/doctor/cases/${c.case_id}`} className="font-medium text-brand-700 hover:underline">View note</Link>
                </Card>
              ))}
            </section>
          )}

          {cases.some((c) => c.state === 'accepted' || c.state === 'in_session') && (
            <section className="space-y-3" aria-label="Your cases">
              <h2 className="font-medium text-slate-900">Your cases</h2>
              {cases.filter((c) => c.state === 'accepted' || c.state === 'in_session').map((c) => (
                <Card key={c.case_id} className="flex items-center justify-between gap-3 p-4 text-sm text-slate-700">
                  <span>
                    <span className="font-semibold text-slate-900">{c.first_name}</span>, accepted {c.accepted_at ? when(c.accepted_at) : ''}
                  </span>
                  <Link to={`/doctor/cases/${c.case_id}`}
                    className="inline-flex h-9 items-center rounded-lg bg-brand-800 px-3 text-sm font-medium text-white hover:bg-brand-900">
                    {c.state === 'accepted' ? 'Review and start' : 'Open conversation'}
                  </Link>
                </Card>
              ))}
            </section>
          )}

          <Card className="space-y-1 p-5 text-sm text-slate-700">
            <p><span className="font-semibold text-slate-900">Specialty.</span> {me.specialty}</p>
            <p><span className="font-semibold text-slate-900">Registration.</span> {me.registration_number}</p>
            <p><span className="font-semibold text-slate-900">Languages.</span> {me.languages.join(', ') || 'Not set'}</p>
            <p className="pt-1 text-slate-500">IRIS does not verify registration numbers; this is a test account.</p>
          </Card>
        </>
      )}
    </div>
  )
}
