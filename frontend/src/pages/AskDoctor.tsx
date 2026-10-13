import { Phone, Stethoscope } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import ConsultThread from '../components/ConsultThread'
import VideoCall from '../components/VideoCall'
import { Alert, Button, Card, Spinner } from '../components/ui'
import { api, ApiError } from '../lib/api'
import type { Consult } from '../lib/types'

const SHARE_FALLBACK =
  'If you ask to talk to a doctor, the doctor who accepts can read your recent messages here and your check-in answers, so you do not have to repeat yourself. You can cancel your request at any time.'

const HELPLINES: Consult['helplines'] = [
  { name: 'Tele-MANAS', detail: '24x7, free, confidential', number: '14416', tel: '14416' },
  { name: 'KIRAN', detail: 'Mental health helpline', number: '1800-599-0019', tel: '18005990019' },
  { name: 'In immediate danger', detail: 'Emergency services', number: '112', tel: '112' },
]

function Helplines({ lines }: { lines: Consult['helplines'] }) {
  return (
    <div className="space-y-2">
      {lines.map((h) => (
        <a
          key={h.number}
          href={`tel:${h.tel}`}
          className="flex items-center justify-between gap-3 rounded-xl border border-teal-200 bg-white px-4 py-3 hover:bg-teal-50"
        >
          <span>
            <span className="block font-medium text-slate-900">{h.name}</span>
            <span className="block text-sm text-slate-600">{h.detail}</span>
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-lg bg-brand-800 px-3 py-1.5 text-sm font-semibold text-white">
            <Phone className="size-4" aria-hidden /> {h.number}
          </span>
        </a>
      ))}
    </div>
  )
}

/** Ask to talk to a doctor, and see the honest state of that request. Nothing here says a doctor is coming until one has accepted. */
export default function AskDoctor() {
  const [current, setCurrent] = useState<Consult | null | undefined>(undefined)
  const [notice, setNotice] = useState(SHARE_FALLBACK)
  const [agree, setAgree] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const wasAccepted = useRef(false)
  const [ended, setEnded] = useState(false)

  const load = useCallback(() => {
    api.currentConsult().then((c) => {
      if (c?.state === 'accepted') wasAccepted.current = true
      else if (c === null && wasAccepted.current) setEnded(true)
      setCurrent(c)
    }).catch((e) => setError(e instanceof ApiError ? e.message : 'Could not load your request.'))
  }, [])

  useEffect(() => {
    load()
    api.consultNotice().then((n) => setNotice(n.share_notice)).catch(() => undefined)
    const t = window.setInterval(load, 5000)
    return () => window.clearInterval(t)
  }, [load])

  async function request() {
    setBusy(true)
    setError('')
    try {
      setCurrent(await api.requestDoctor(agree))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Your request was not sent. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  async function cancel() {
    if (!current) return
    setBusy(true)
    try {
      await api.cancelConsult(current.id)
      setCurrent(null)
      setAgree(false)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not cancel. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  if (current === undefined && !error) return <Spinner />

  return (
    <div className="mx-auto max-w-2xl space-y-6 py-8">
      <div className="flex items-center gap-3">
        <span className="grid size-11 place-content-center rounded-xl bg-brand-50 text-brand-700">
          <Stethoscope className="size-5" aria-hidden />
        </span>
        <h1 className="font-display text-2xl font-medium text-slate-900">Talk to a doctor</h1>
      </div>

      {error && <Alert>{error}</Alert>}

      {!current && ended && (
        <Card className="space-y-2 p-6">
          <p className="font-semibold text-slate-900">This conversation has ended</p>
          <p className="text-slate-700">Thank you for talking with us. You can ask for a doctor again at any time, and the numbers below are always there.</p>
          <Helplines lines={HELPLINES} />
        </Card>
      )}

      {!current && (
        <Card className="space-y-5 p-6">
          <p className="text-slate-700">
            A doctor on the IRIS team can talk with you. They may not be able to answer straight away. While you wait, the numbers below are always
            there.
          </p>
          <p className="text-sm text-slate-600">{notice}</p>
          <label className="flex items-start gap-3 text-sm text-slate-800">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} className="mt-1 size-4" />
            <span>I agree to share my recent messages and check-in answers with the doctor who accepts.</span>
          </label>
          <Button onClick={() => void request()} disabled={!agree || busy} loading={busy}>
            Ask for a doctor
          </Button>
          <p className="text-sm text-slate-500">
            If you need someone right now, call <a className="font-semibold underline" href="tel:14416">Tele-MANAS 14416</a> or{' '}
            <a className="font-semibold underline" href="tel:112">112</a>.
          </p>
        </Card>
      )}

      {current && (
        <>
          <Card className="space-y-3 p-6">
            <p className="font-semibold text-slate-900">
              {current.state === 'accepted' ? (current.doctor_name ? `${current.doctor_name} has accepted` : 'A doctor has accepted') : 'Your request is open'}
            </p>
            <p className="text-slate-700">{current.status_text}</p>
            {current.state === 'accepted' && current.doctor_registration_number && (
              <p className="text-sm text-slate-600">
                {current.doctor_specialty ? `${current.doctor_specialty}. ` : ''}Registration number: {current.doctor_registration_number}
              </p>
            )}
            {current.state === 'open' && (
              <Button variant="secondary" onClick={() => void cancel()} disabled={busy}>
                Cancel my request
              </Button>
            )}
          </Card>
          {current.state === 'open' && <Helplines lines={current.helplines} />}
          {current.state === 'accepted' && (
            <VideoCall
              post={(kind, payload) => api.consultCallPost(current.id, kind, payload)}
              poll={(after) => api.consultCallPoll(current.id, after)}
              otherName={current.doctor_name ?? 'your doctor'}
            />
          )}
          {current.state === 'accepted' && (
            <ConsultThread
              load={() => api.consultMessages(current.id)}
              send={(t) => api.sendConsultMessage(current.id, t)}
              otherName={current.doctor_name ?? 'your doctor'}
            />
          )}
        </>
      )}

      <p className="text-sm text-slate-500">
        <Link to="/chat" className="font-semibold underline">Back to the chat</Link>
      </p>
    </div>
  )
}
