import { ArrowLeft, ArrowRight, Check, LifeBuoy } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { homeFor, useAuth } from '../auth/AuthContext'
import { HELPLINES } from '../components/Brand'
import { Alert, Button, Card, Spinner, Textarea, TextLink, cx } from '../components/ui'
import { api, ApiError } from '../lib/api'
import { pruneAnswers, visibleQuestions } from '../lib/questionnaire'
import type { Answer, Answers, Question, Questionnaire } from '../lib/types'

const AUTO_ADVANCE_MS = 320
const isAutoAdvance = (q: Question) => q.type === 'single' || q.type === 'frequency' || q.type === 'yesno'

export default function CheckIn() {
  const { user, refresh } = useAuth()
  const navigate = useNavigate()
  const [qn, setQn] = useState<Questionnaire | null>(null)
  const [loadError, setLoadError] = useState('')
  const [answers, setAnswers] = useState<Answers>({})
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmSkip, setConfirmSkip] = useState(false)
  const [done, setDone] = useState(false)
  const heading = useRef<HTMLHeadingElement>(null)
  const timer = useRef<number>(undefined)

  useEffect(() => {
    api
      .questionnaire()
      .then((q) => {
        setQn(q)
        setCurrentId(q.questions[0].id)
      })
      .catch((e) => setLoadError(e instanceof ApiError ? e.message : 'Could not load the check-in.'))
    return () => window.clearTimeout(timer.current)
  }, [])

  useEffect(() => {
    heading.current?.focus({ preventScroll: true })
    window.scrollTo({ top: 0 })
  }, [currentId])

  // Warn before losing an in-progress check-in. Answers are intentionally not persisted in the browser.
  useEffect(() => {
    if (done || !Object.keys(answers).length) return
    const h = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', h)
    return () => window.removeEventListener('beforeunload', h)
  }, [answers, done])

  const visible = useMemo(() => (qn ? visibleQuestions(qn.questions, answers) : []), [qn, answers])

  const finish = useCallback(
    async (skip: boolean, final?: Answers) => {
      if (!qn) return
      setBusy(true)
      setError('')
      try {
        const res = skip ? await api.skipCheckin() : await api.submitCheckin(pruneAnswers(qn.questions, final ?? answers))
        setDone(true)
        const u = await refresh()
        if (res.show_crisis_resources) navigate('/support', { replace: true })
        else navigate(u ? homeFor(u) : '/', { replace: true })
      } catch (e) {
        setError(e instanceof ApiError ? e.message : 'Could not save your check-in. Please try again.')
      } finally {
        setBusy(false)
      }
    },
    [qn, answers, refresh, navigate],
  )

  if (loadError) return <Alert>{loadError}</Alert>
  if (!qn || !currentId) return <Spinner label="Loading check-in" />

  const idx = Math.max(0, visible.findIndex((q) => q.id === currentId))
  const q = visible[idx]
  const isLast = idx === visible.length - 1
  const sectionIdx = qn.sections.findIndex((s) => s.id === q.section)
  const section = qn.sections[sectionIdx]
  const value = answers[q.id]
  const hasAnswer = value !== undefined
  const showImmediateHelp = q.section === 'safety' && typeof answers['s0'] === 'number' && answers['s0'] > 0

  /** Move relative to `fromId` within the list of questions visible for `ans`. */
  function move(ans: Answers, fromId: string, delta: 1 | -1) {
    window.clearTimeout(timer.current)
    const list = visibleQuestions(qn!.questions, ans)
    const i = list.findIndex((x) => x.id === fromId)
    const target = list[i + delta]
    if (target) setCurrentId(target.id)
  }

  function setAnswer(question: Question, v: Answer | undefined) {
    window.clearTimeout(timer.current)
    const next = { ...answers }
    if (v === undefined || (Array.isArray(v) && !v.length) || v === '') delete next[question.id]
    else next[question.id] = v
    const pruned = pruneAnswers(qn!.questions, next)
    setAnswers(pruned)
    // Single-choice questions move on by themselves; the last question waits for an explicit Finish.
    if (v !== undefined && isAutoAdvance(question)) {
      const list = visibleQuestions(qn!.questions, pruned)
      if (list[list.length - 1].id !== question.id) {
        timer.current = window.setTimeout(() => move(pruned, question.id, 1), AUTO_ADVANCE_MS)
      }
    }
  }

  const onNext = () => (isLast ? void finish(false) : move(answers, q.id, 1))
  const onBack = () => move(answers, q.id, -1)

  // Progress inside the current section, so the bar moves smoothly even when branching adds questions.
  const inSection = visible.filter((x) => x.section === q.section)
  const sectionFill = ((inSection.findIndex((x) => x.id === q.id) + (hasAnswer ? 1 : 0)) / inSection.length) * 100

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
            <span className="hidden text-slate-600 sm:inline">Skip the whole check-in?</span>
            <TextLink onClick={() => void finish(true)} disabled={busy}>Yes, skip</TextLink>
            <TextLink onClick={() => setConfirmSkip(false)} className="text-slate-600">Cancel</TextLink>
          </div>
        )}
      </div>

      <nav aria-label="Check-in progress" className="mb-6">
        <ol className="flex gap-1.5">
          {qn.sections.map((s, i) => (
            <li key={s.id} className="flex-1" aria-current={i === sectionIdx ? 'step' : undefined}>
              <div className="h-1.5 overflow-hidden rounded-full bg-slate-200">
                <div
                  className="h-full rounded-full bg-brand-600 transition-[width] duration-300"
                  style={{ width: i < sectionIdx ? '100%' : i === sectionIdx ? `${sectionFill}%` : '0%' }}
                />
              </div>
              <span className={cx('mt-2 hidden text-xs sm:block', i === sectionIdx ? 'font-medium text-slate-900' : 'text-slate-500')}>
                {s.title}
              </span>
            </li>
          ))}
        </ol>
      </nav>

      <Card className="p-6 sm:p-10">
        <div className="flex items-center justify-between gap-3">
          <span className="rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-800">{section.title}</span>
          <span className="text-xs text-slate-500" aria-live="polite">
            Question {idx + 1} of {visible.length}
          </span>
        </div>

        <div key={q.id} className="q-enter mt-8">
          {q.stem && <p className="mb-3 text-sm text-slate-600">{q.stem}</p>}
          <h1
            id="q-prompt"
            ref={heading}
            tabIndex={-1}
            className="font-display text-2xl font-medium leading-snug text-slate-900 outline-none sm:text-[1.75rem]"
          >
            {q.prompt}
            {q.stem ? '?' : ''}
          </h1>

          <div className="mt-7">
            <AnswerInput q={q} value={value} onChange={(v) => setAnswer(q, v)} />
          </div>

          {hasAnswer && q.type !== 'text' && (
            <button
              type="button"
              onClick={() => setAnswer(q, undefined)}
              className="mt-4 text-xs text-slate-500 underline-offset-2 hover:text-slate-800 hover:underline"
            >
              Clear answer
            </button>
          )}
        </div>

        {showImmediateHelp && (
          <div className="mt-8 rounded-lg border border-brand-200 bg-brand-50 p-4 text-sm text-brand-900">
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

        <div className="mt-10 flex items-center justify-between gap-3 border-t border-slate-100 pt-6">
          <Button variant="ghost" onClick={onBack} className={idx === 0 ? 'invisible' : ''} disabled={busy}>
            <ArrowLeft className="size-4" aria-hidden /> Back
          </Button>
          {isLast ? (
            <Button onClick={onNext} loading={busy}>
              <Check className="size-4" aria-hidden /> Finish
            </Button>
          ) : (
            <Button variant={hasAnswer ? 'primary' : 'secondary'} onClick={onNext}>
              {hasAnswer ? 'Next' : 'Skip'} <ArrowRight className="size-4" aria-hidden />
            </Button>
          )}
        </div>
      </Card>
    </div>
  )
}

function AnswerInput({ q, value, onChange }: {
  q: Question
  value: Answer | undefined
  onChange: (v: Answer | undefined) => void
}) {
  if (q.type === 'text') {
    const v = typeof value === 'string' ? value : ''
    return (
      <div>
        <Textarea value={v} maxLength={2000} onChange={(e) => onChange(e.target.value)} aria-labelledby="q-prompt"
          className="min-h-40" placeholder="Take your time. Write as much or as little as you like." />
        <p className="mt-1.5 text-xs text-slate-500">Only your care reviewer can read this. {v.length}/2000</p>
      </div>
    )
  }

  if (q.type === 'multi') {
    const sel = Array.isArray(value) ? value : []
    const toggle = (o: number) => onChange(sel.includes(o) ? sel.filter((x) => x !== o) : [...sel, o])
    return (
      <fieldset aria-labelledby="q-prompt">
        <p className="mb-3 text-xs text-slate-500">Select all that apply.</p>
        <div className="grid gap-2.5 sm:grid-cols-2">
          {q.options.map((o) => (
            <Choice key={o.value} type="checkbox" name={q.id} checked={sel.includes(o.value)} onChange={() => toggle(o.value)} label={o.label} />
          ))}
        </div>
      </fieldset>
    )
  }

  const grid = q.type === 'yesno' ? 'grid-cols-2 sm:max-w-sm' : 'grid-cols-1'
  return (
    <fieldset aria-labelledby="q-prompt">
      <div className={cx('grid gap-2.5', grid)}>
        {q.options.map((o) => (
          <Choice key={o.value} type="radio" name={q.id} checked={value === o.value} onChange={() => onChange(o.value)}
            label={o.label} center={q.type === 'yesno'} />
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
          'flex min-h-12 w-full items-center gap-3 rounded-lg border border-slate-300 bg-white px-4 py-3 text-[15px] text-slate-700 transition-colors',
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
