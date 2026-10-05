import { ArrowLeft, ArrowRight, Check, LifeBuoy } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { homeFor, useAuth } from '../auth/AuthContext'
import { HELPLINES } from '../components/Brand'
import { Alert, Button, Card, Spinner, Textarea, TextLink, cx } from '../components/ui'
import { api, ApiError } from '../lib/api'
import { pruneAnswers, visibleQuestions } from '../lib/questionnaire'
import type { Answer, Answers, Question, Questionnaire } from '../lib/types'

export default function CheckIn() {
  const { user, refresh } = useAuth()
  const navigate = useNavigate()
  const [qn, setQn] = useState<Questionnaire | null>(null)
  const [loadError, setLoadError] = useState('')
  const [answers, setAnswers] = useState<Answers>({})
  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmSkip, setConfirmSkip] = useState(false)
  const [done, setDone] = useState(false)
  const heading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    api.questionnaire().then(setQn).catch((e) => setLoadError(e instanceof ApiError ? e.message : 'Could not load the check-in.'))
  }, [])

  useEffect(() => {
    heading.current?.focus({ preventScroll: true })
    window.scrollTo({ top: 0 })
  }, [step])

  // Warn before losing an in-progress check-in. Answers are intentionally not persisted in the browser.
  useEffect(() => {
    if (done || !Object.keys(answers).length) return
    const h = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', h)
    return () => window.removeEventListener('beforeunload', h)
  }, [answers, done])

  const visible = useMemo(() => (qn ? visibleQuestions(qn.questions, answers) : []), [qn, answers])

  if (loadError) return <Alert>{loadError}</Alert>
  if (!qn) return <Spinner label="Loading check-in" />

  const section = qn.sections[step]
  const items = visible.filter((q) => q.section === section.id)
  const last = step === qn.sections.length - 1
  const s0 = answers['s0']
  const showImmediateHelp = typeof s0 === 'number' && s0 > 0

  const setAnswer = (id: string, v: Answer | undefined) =>
    setAnswers((prev) => {
      const next = { ...prev }
      if (v === undefined || (Array.isArray(v) && !v.length) || v === '') delete next[id]
      else next[id] = v
      return pruneAnswers(qn.questions, next)
    })

  async function finish(skip: boolean) {
    setBusy(true)
    setError('')
    try {
      const res = skip ? await api.skipCheckin() : await api.submitCheckin(pruneAnswers(qn!.questions, answers))
      setDone(true)
      const u = await refresh()
      if (res.show_crisis_resources) navigate('/support', { replace: true })
      else navigate(u ? homeFor(u) : '/', { replace: true })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not save your check-in. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  const answered = visible.filter((q) => q.id in answers).length

  return (
    <div>
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-brand-700">Health check-in</p>
          <p className="text-xs text-slate-500">Hi {user?.first_name}. Skip anything you prefer not to answer.</p>
        </div>
        {!confirmSkip ? (
          <TextLink onClick={() => setConfirmSkip(true)} className="text-slate-600">Skip for now</TextLink>
        ) : (
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-600">Skip the whole check-in?</span>
            <TextLink onClick={() => void finish(true)} disabled={busy}>Yes, skip</TextLink>
            <TextLink onClick={() => setConfirmSkip(false)} className="text-slate-600">Cancel</TextLink>
          </div>
        )}
      </div>

      <nav aria-label="Check-in progress" className="mb-6">
        <ol className="flex gap-1.5">
          {qn.sections.map((s, i) => (
            <li key={s.id} className="flex-1" aria-current={i === step ? 'step' : undefined}>
              <div className={cx('h-1.5 rounded-full transition-colors', i < step ? 'bg-brand-700' : i === step ? 'bg-brand-400' : 'bg-slate-200')} />
              <span className={cx('mt-2 hidden text-xs sm:block', i === step ? 'font-medium text-slate-900' : 'text-slate-500')}>
                {s.title}
              </span>
            </li>
          ))}
        </ol>
      </nav>

      <Card className="p-6 sm:p-9">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
          Step {step + 1} of {qn.sections.length}
        </p>
        <h1 ref={heading} tabIndex={-1} className="mt-1 font-display text-2xl font-medium text-slate-900 outline-none sm:text-3xl">
          {section.title}
        </h1>
        <p className="mt-1.5 text-sm text-slate-600">{section.description}</p>

        {items[0]?.stem && (
          <p className="mt-6 rounded-lg bg-slate-50 px-4 py-3 text-sm text-slate-700">{items[0].stem}</p>
        )}

        <div className="mt-6 divide-y divide-slate-100">
          {items.map((q, i) => (
            <div key={q.id} className="py-5 first:pt-0 last:pb-0">
              <QuestionView q={q} index={i + 1} value={answers[q.id]} onChange={(v) => setAnswer(q.id, v)} />
            </div>
          ))}
        </div>

        {section.id === 'safety' && showImmediateHelp && (
          <div className="mt-6 rounded-lg border border-brand-200 bg-brand-50 p-4 text-sm text-brand-900">
            <p className="flex items-center gap-2 font-medium">
              <LifeBuoy className="size-4" aria-hidden /> Thank you for being honest. You are not alone.
            </p>
            <p className="mt-1.5">
              If you are in immediate danger, call <strong>112</strong>. To talk to someone now, call{' '}
              {HELPLINES.map((h, i) => (
                <span key={h.tel}>
                  {i > 0 && ' or '}
                  <a className="font-semibold underline" href={`tel:${h.tel}`}>{h.name} {h.number}</a>
                </span>
              ))}
              .
            </p>
          </div>
        )}

        {error && <div className="mt-6"><Alert>{error}</Alert></div>}

        <div className="mt-8 flex items-center justify-between gap-3 border-t border-slate-100 pt-6">
          <Button variant="ghost" onClick={() => setStep((s) => s - 1)} className={step === 0 ? 'invisible' : ''} disabled={busy}>
            <ArrowLeft className="size-4" aria-hidden /> Back
          </Button>
          <span className="hidden text-xs text-slate-500 sm:block">{answered} answered</span>
          {last ? (
            <Button onClick={() => void finish(false)} loading={busy}>
              <Check className="size-4" aria-hidden /> Finish
            </Button>
          ) : (
            <Button onClick={() => setStep((s) => s + 1)}>
              Continue <ArrowRight className="size-4" aria-hidden />
            </Button>
          )}
        </div>
      </Card>
    </div>
  )
}

function QuestionView({ q, index, value, onChange }: {
  q: Question
  index: number
  value: Answer | undefined
  onChange: (v: Answer | undefined) => void
}) {
  const answered = value !== undefined
  const legend = (
    <legend className="mb-3 flex w-full items-start justify-between gap-4 text-[15px] font-medium leading-snug text-slate-900">
      <span><span className="mr-2 text-slate-400">{index}.</span>{q.prompt}</span>
      {answered && q.type !== 'text' && (
        <button type="button" onClick={() => onChange(undefined)} className="shrink-0 pt-0.5 text-xs font-normal text-slate-500 underline-offset-2 hover:text-slate-800 hover:underline">
          Clear
        </button>
      )}
    </legend>
  )

  if (q.type === 'text') {
    const v = typeof value === 'string' ? value : ''
    return (
      <fieldset>
        {legend}
        <Textarea value={v} maxLength={2000} onChange={(e) => onChange(e.target.value)} aria-label={q.prompt}
          placeholder="Take your time. Write as much or as little as you like." />
        <p className="mt-1.5 text-xs text-slate-500">Only your care reviewer can read this. {v.length}/2000</p>
      </fieldset>
    )
  }

  if (q.type === 'multi') {
    const sel = Array.isArray(value) ? value : []
    const toggle = (o: number) => onChange(sel.includes(o) ? sel.filter((x) => x !== o) : [...sel, o])
    return (
      <fieldset>
        {legend}
        <p className="-mt-1.5 mb-3 text-xs text-slate-500">Select all that apply.</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {q.options.map((o) => (
            <Choice key={o.value} type="checkbox" name={q.id} checked={sel.includes(o.value)} onChange={() => toggle(o.value)} label={o.label} />
          ))}
        </div>
      </fieldset>
    )
  }

  const cols = q.type === 'frequency' ? 'grid-cols-2 sm:grid-cols-4' : q.type === 'yesno' ? 'grid-cols-2 sm:max-w-xs' : 'grid-cols-1'
  return (
    <fieldset>
      {legend}
      <div className={cx('grid gap-2', cols)}>
        {q.options.map((o) => (
          <Choice key={o.value} type="radio" name={q.id} checked={value === o.value} onChange={() => onChange(o.value)}
            label={o.label} center={q.type !== 'single'} />
        ))}
      </div>
    </fieldset>
  )
}

function Choice({ type, name, checked, onChange, label, center }: {
  type: 'radio' | 'checkbox'
  name: string
  checked: boolean
  onChange: () => void
  label: string
  center?: boolean
}) {
  return (
    <label className="flex cursor-pointer">
      <input type={type} name={name} checked={checked} onChange={onChange} className="peer sr-only" />
      <span
        className={cx(
          'flex min-h-11 w-full items-center rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-700 transition-colors',
          'hover:border-slate-400 hover:bg-slate-50',
          'peer-checked:border-brand-700 peer-checked:bg-brand-50 peer-checked:font-medium peer-checked:text-brand-900',
          'peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-brand-600',
          center && 'justify-center text-center',
        )}
      >
        {label}
      </span>
    </label>
  )
}
