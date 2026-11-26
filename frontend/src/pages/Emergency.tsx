import { ArrowLeft, Phone, ShieldAlert, Stethoscope, Wind } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Logo } from '../components/Brand'
import { EMERGENCY, HELPLINES } from '../lib/helplines'
import { Card, cx } from '../components/ui'

/*
 * Emergency support: one page anyone can open at any time, signed in or not, so a person in crisis is never stopped by a login screen.
 * Every sentence here is reused from the reviewed list in ml/iris_ml/support.py (it is still an AI-assisted draft pending clinical review).
 * Nothing on this page promises that anyone is coming or says when.
 */

const IN_DANGER = [
  'Call 112 now, or go to the emergency department of the nearest hospital.',
  'If you can, be with someone you trust right now, such as a family member or friend, and tell them how you are feeling.',
  'If you have something near you that you could use to hurt yourself, it may help to move it out of reach or ask someone to keep it for you.',
]

const STEPS = [
  { label: 'Breathe in', seconds: 4 },
  { label: 'Hold', seconds: 4 },
  { label: 'Breathe out', seconds: 4 },
  { label: 'Hold', seconds: 4 },
] as const

/** Slow breathing, paced on screen. It only counts; it never measures or records anything. */
function Breathing() {
  const [on, setOn] = useState(false)
  const [t, setT] = useState(0)                 // seconds since Start; every step is 4 seconds long

  useEffect(() => {
    if (!on) return
    const id = window.setInterval(() => setT((x) => x + 1), 1000)
    return () => window.clearInterval(id)
  }, [on])

  function toggle() {
    setT(0)
    setOn((v) => !v)
  }

  const step = Math.floor(t / 4) % STEPS.length
  const left = STEPS[step].seconds - (t % 4)
  const current = STEPS[step]
  const big = step === 0 || step === 1
  return (
    <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center">
      <div className="grid size-36 shrink-0 place-items-center" aria-hidden>
        <div
          className={cx(
            'grid place-items-center rounded-full bg-brand-100 text-brand-900 transition-all ease-in-out motion-reduce:transition-none',
            on ? 'duration-[4000ms]' : 'duration-300',
            on && big ? 'size-36' : 'size-24',
          )}
        >
          {on && <span className="text-2xl font-semibold tabular-nums">{left}</span>}
        </div>
      </div>
      <div className="space-y-3 text-center sm:text-left">
        <p className="text-lg font-medium text-slate-900" aria-live="polite">
          {on ? current.label : 'Slow breathing'}
        </p>
        <p className="text-sm text-slate-600">
          Breathe in for 4 seconds, hold for 4, breathe out for 4 and hold for 4, for a few minutes. If counting feels uncomfortable, breathe at
          your own pace instead.
        </p>
        <button
          type="button"
          onClick={toggle}
          className="inline-flex h-10 items-center rounded-lg border border-brand-800 px-4 text-sm font-medium text-brand-800 hover:bg-brand-50"
        >
          {on ? 'Stop' : 'Breathe with me'}
        </button>
      </div>
    </div>
  )
}

export default function Emergency() {
  const { user } = useAuth()
  const person = user?.role === 'user'

  return (
    <div className="min-h-dvh bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-16 max-w-3xl items-center justify-between px-5">
          <Link to="/" aria-label="IRIS home">
            <Logo />
          </Link>
          <Link to={user ? '/' : '/login'} className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-slate-600 hover:bg-slate-100">
            <ArrowLeft className="size-4" aria-hidden /> Back to IRIS
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-6 px-5 py-8 sm:py-10">
        <div>
          <h1 className="font-display text-3xl font-medium text-slate-900">Emergency support</h1>
          <p className="mt-2 text-slate-600">You do not have to go through this alone. Please contact one of these now, even if it feels hard.</p>
        </div>

        {/* 112 first and largest: the one number for immediate danger. */}
        <a
          href={`tel:${EMERGENCY.tel}`}
          className="flex items-center justify-between gap-4 rounded-2xl bg-red-700 px-6 py-5 text-white shadow-sm hover:bg-red-800 focus:outline-none focus-visible:ring-4 focus-visible:ring-red-300"
        >
          <span>
            <span className="block text-lg font-semibold">{EMERGENCY.name}</span>
            <span className="block text-sm text-red-100">{EMERGENCY.detail}: police, ambulance and fire</span>
          </span>
          <span className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-xl font-bold text-red-800">
            <Phone className="size-5" aria-hidden /> {EMERGENCY.number}
          </span>
        </a>

        <Card className="p-6">
          <h2 className="flex items-center gap-2 font-medium text-slate-900">
            <ShieldAlert className="size-5 text-red-700" aria-hidden /> If you are in danger right now
          </h2>
          <ol className="mt-4 list-decimal space-y-2.5 pl-5 text-slate-700">
            {IN_DANGER.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ol>
        </Card>

        <Card className="p-6">
          <h2 className="font-medium text-slate-900">Talk to someone now</h2>
          <ul className="mt-4 space-y-3">
            {HELPLINES.map((h) => (
              <li key={h.tel}>
                <a
                  href={`tel:${h.tel}`}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-brand-200 bg-white p-4 hover:bg-brand-50"
                >
                  <span>
                    <span className="block font-medium text-slate-900">{h.name}</span>
                    <span className="block text-sm text-slate-600">{h.detail}</span>
                  </span>
                  <span className="inline-flex h-11 items-center gap-2 rounded-lg bg-brand-800 px-5 text-sm font-semibold text-white">
                    <Phone className="size-4" aria-hidden /> {h.number}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-6">
          <h2 className="flex items-center gap-2 font-medium text-slate-900">
            <Wind className="size-5 text-brand-700" aria-hidden /> If you feel overwhelmed
          </h2>
          <div className="mt-4">
            <Breathing />
          </div>
        </Card>

        {person && (
          <Card className="flex flex-col gap-3 p-6 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="flex items-center gap-2 font-medium text-slate-900">
                <Stethoscope className="size-5 text-brand-700" aria-hidden /> Talk to a doctor
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                A doctor on the IRIS team can talk with you here. They may not be able to answer straight away, so the numbers above are still the
                quickest way to reach someone.
              </p>
            </div>
            <Link
              to="/talk-to-a-doctor"
              className="inline-flex h-10 shrink-0 items-center rounded-lg border border-brand-800 px-4 text-sm font-medium text-brand-800 hover:bg-brand-50"
            >
              Ask for a doctor
            </Link>
          </Card>
        )}

        <p className="text-center text-xs text-slate-500">
          IRIS is not an emergency service. If you need help right now, call 112 or Tele-MANAS 14416.
          <br />
          Prototype: the wording is a draft that a clinician has not reviewed yet.
        </p>
      </main>
    </div>
  )
}
