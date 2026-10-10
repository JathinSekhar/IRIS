import { ArrowUp, ChevronDown, Loader2, Phone } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Alert, cx } from '../components/ui'
import { api, ApiError } from '../lib/api'
import type { CareStatus, ChatMessage, Helpline } from '../lib/types'

const MAX = 5000
const POLL_MS = 8000
const NEAR_BOTTOM_PX = 96
// The same sentence as the reviewed list (ml/iris_ml/support.py EMERGENCY_FOOTER). A backend test keeps these identical.
const EMERGENCY_LINE = 'IRIS is not an emergency service. If you need help right now, call 112 or Tele-MANAS 14416.'

// ---------------------------------------------------------------------------------------------------------------------------------------------
// Pieces
// ---------------------------------------------------------------------------------------------------------------------------------------------

/** Tap-to-call. The numbers come from the server (the reviewed list), never from this file. */
function HelpCard({ lead, lines, strong }: { lead: string; lines: Helpline[]; strong?: boolean }) {
  return (
    <div className={cx('rounded-2xl p-4', strong ? 'bg-brand-50 ring-2 ring-brand-700' : 'bg-brand-50/70 ring-1 ring-brand-200')}>
      <p className="mb-3 text-sm font-medium text-brand-900">{lead}</p>
      <ul className="space-y-2">
        {lines.map((h) => (
          <li key={h.tel}>
            <a
              href={`tel:${h.tel}`}
              className="flex items-center justify-between gap-3 rounded-xl bg-white px-3.5 py-2.5 ring-1 ring-brand-200 hover:bg-brand-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
            >
              <span className="min-w-0">
                <span className="block text-sm font-medium text-slate-900">{h.name}</span>
                <span className="block text-xs text-slate-500">{h.detail}</span>
              </span>
              <span className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-brand-800 px-3 py-1.5 text-sm font-semibold text-white">
                <Phone className="size-3.5" aria-hidden /> {h.number}
              </span>
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}

const DOT: Record<CareStatus, string> = { waiting: 'bg-amber-400', being_read: 'bg-sky-500', reviewed: 'bg-emerald-500' }

/** What is really true about this message: whether a person has opened it. The wording comes from the server. */
function Status({ m }: { m: ChatMessage }) {
  return (
    <p className="flex items-start gap-2 text-xs leading-relaxed text-slate-500" aria-live="polite">
      <span className={cx('mt-1 inline-block size-1.5 shrink-0 rounded-full', DOT[m.care_status], m.care_status === 'being_read' && 'animate-pulse')} />
      <span>{m.status_text}</span>
    </p>
  )
}

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5">
      {items.map((t) => (
        <li key={t}>{t}</li>
      ))}
    </ul>
  )
}

/** IRIS's reply: plain text, no box. One idea is shown; the rest wait behind "More ideas". Helplines are never hidden. */
function Reply({ m, first }: { m: ChatMessage; first: boolean }) {
  const r = m.reply
  const [more, setMore] = useState(false)
  const talked = Boolean(r.companion)          // an AI-written conversational line replaces the fixed opening; the ideas wait behind "More ideas"
  const firstIdea = talked ? undefined : r.self_help[0]
  const otherIdeas = talked ? r.self_help : r.self_help.slice(1)
  const hasMore = otherIdeas.length > 0 || (r.layout === 'tips' && r.reach_out.length > 0)

  return (
    <div className="space-y-4 text-[15px] leading-7 text-slate-700">
      <div className="space-y-3">
        {talked ? (
          <>
            <p className="text-slate-900">{r.companion}</p>
            <p className="text-xs text-slate-400">Written by an AI assistant. A person on our team still reads your message.</p>
          </>
        ) : (
          <>
            <p className="font-semibold text-slate-900">{r.intro}</p>
            {(first || r.layout !== 'tips') && r.listening && <p>{r.listening}</p>}
          </>
        )}

        {r.layout === 'tips' && firstIdea && (
          <p>
            <span className="font-semibold text-slate-900">{firstIdea.title}.</span> {firstIdea.how}
          </p>
        )}
        {r.layout === 'tips' && more && (
          <div className="space-y-3">
            {otherIdeas.map((s) => (
              <p key={s.title}>
                <span className="font-semibold text-slate-900">{s.title}.</span> {s.how}
              </p>
            ))}
            {r.reach_out.length > 0 && <Bullets items={r.reach_out} />}
          </div>
        )}
        {r.layout === 'tips' && hasMore && (
          <button
            type="button"
            onClick={() => setMore((v) => !v)}
            aria-expanded={more}
            className="rounded text-sm font-semibold text-brand-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
          >
            {more ? 'Show less' : 'More ideas'}
          </button>
        )}

        {r.layout === 'support' && r.reach_out.length > 0 && <Bullets items={r.reach_out} />}
        {r.layout === 'celebrate' && r.reach_out[0] && <p className="text-sm text-slate-500">{r.reach_out[0]}</p>}
      </div>

      {r.layout === 'help_now' && (
        <>
          {r.helplines.length > 0 && <HelpCard strong lead={r.crisis_lead} lines={r.helplines} />}
          {r.reach_out.length > 0 && <Bullets items={r.reach_out} />}
        </>
      )}
      {r.layout !== 'help_now' && r.helplines.length > 0 && <HelpCard lead={r.crisis_lead} lines={r.helplines} />}

      <Status m={m} />
    </div>
  )
}

// ---------------------------------------------------------------------------------------------------------------------------------------------
// The page
// ---------------------------------------------------------------------------------------------------------------------------------------------

export default function Chat() {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null)
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [atBottom, setAtBottom] = useState(true)
  const [unseen, setUnseen] = useState(0)

  const list = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const busy = useRef(false)
  const stick = useRef(true)               // the person is at (or has just asked for) the bottom of the conversation
  const justSent = useRef(false)
  const prevLen = useRef(0)

  useEffect(() => {
    api
      .messages()
      .then(setMessages)
      .catch((e) => {
        setMessages([])
        setError(e instanceof ApiError ? e.message : 'Could not load your messages.')
      })
  }, [])

  // Keep the status lines honest: refresh quietly so "a person is reading this now" appears as soon as it is true. This never moves the scroll position.
  useEffect(() => {
    const id = window.setInterval(() => {
      if (busy.current || document.hidden) return
      api.messages().then((m) => !busy.current && setMessages(m)).catch(() => undefined)
    }, POLL_MS)
    return () => window.clearInterval(id)
  }, [])

  function onScroll() {
    const el = list.current
    if (!el) return
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX
    stick.current = near
    setAtBottom(near)
    if (near) setUnseen(0)
  }

  function toBottom(smooth = true) {
    const el = list.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'instant' })
    stick.current = true
    setUnseen(0)
  }

  // When a turn arrives: open at the bottom on first load; otherwise bring the START of the newest turn into view (so a long reply is read from its top),
  // but only if the person is already at the bottom or has just sent. If they have scrolled up to re-read, leave them there and offer a button.
  // Only the message list is scrolled (scrollIntoView would also move the page and push the header out of view).
  useLayoutEffect(() => {
    const el = list.current
    if (!el || !messages) return
    const grew = messages.length > prevLen.current
    const firstLoad = prevLen.current === 0
    prevLen.current = messages.length
    if (!grew) return
    if (firstLoad) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'instant' })
    } else if (stick.current || justSent.current) {
      const turn = el.querySelector<HTMLElement>('[data-turn="last"]')
      if (turn) el.scrollTo({ top: turn.getBoundingClientRect().top - el.getBoundingClientRect().top + el.scrollTop - 8, behavior: 'smooth' })
      justSent.current = false
    } else {
      setUnseen((u) => u + 1)
    }
  }, [messages])

  useEffect(() => {
    if (sending) toBottom()
  }, [sending])

  function grow() {
    const el = input.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 176)}px`
  }
  useEffect(grow, [text])

  async function send(e?: FormEvent) {
    e?.preventDefault()
    const t = text.trim()
    if (!t || sending) return
    setSending(true)
    busy.current = true
    justSent.current = true
    setError('')
    try {
      const m = await api.sendMessage(t)
      setMessages((prev) => [...(prev ?? []), m])
      setText('')
    } catch (err) {
      justSent.current = false
      if (err instanceof ApiError && err.status === 403 && /consent/i.test(err.message)) {
        window.location.assign('/consent')          // the saved session is out of date: reload so the app re-checks consent and asks for it
        return
      }
      setError(err instanceof ApiError ? err.message : 'Your message was not sent. Please try again.')
    } finally {
      setSending(false)
      busy.current = false
      input.current?.focus({ preventScroll: true })
    }
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void send()
    }
  }

  if (!messages) {
    return (
      <div role="status" className="grid min-h-[40vh] flex-1 place-items-center text-slate-500">
        <Loader2 className="size-6 animate-spin" aria-hidden />
        <span className="sr-only">Loading your conversation</span>
      </div>
    )
  }

  const empty = messages.length === 0
  return (
    <div className="relative flex min-h-0 flex-1 flex-col bg-white">
      {/* The conversation. The scrollbar sits at the window edge; the text stays in a centred column. */}
      <div ref={list} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto overscroll-contain" aria-label="Conversation">
        {empty ? (
          <div className="mx-auto grid h-full max-w-3xl place-content-center px-6 text-center">
            <h1 className="font-display text-3xl font-medium text-slate-900 sm:text-4xl">What is on your mind?</h1>
            <p className="mt-3 text-slate-500">Tell us how you are feeling, in your own words. A person on our team will read it, though not always straight away.</p>
          </div>
        ) : (
          <div className="mx-auto w-full max-w-3xl space-y-10 px-4 py-8 sm:px-6">
            {messages.map((m, i) => (
              <div key={m.id} data-turn={i === messages.length - 1 ? 'last' : undefined} className="space-y-6">
                <div className="flex justify-end">
                  <p className="max-w-[80%] whitespace-pre-wrap break-words rounded-3xl bg-slate-100 px-5 py-2.5 text-[15px] leading-7 text-slate-900">{m.text}</p>
                </div>
                <Reply m={m} first={i === 0} />
              </div>
            ))}
            {sending && (
              <div className="flex items-center gap-1.5 text-slate-400" role="status">
                <span className="size-2 animate-pulse rounded-full bg-current" />
                <span className="size-2 animate-pulse rounded-full bg-current [animation-delay:150ms]" />
                <span className="size-2 animate-pulse rounded-full bg-current [animation-delay:300ms]" />
                <span className="sr-only">IRIS is reading your message</span>
              </div>
            )}
          </div>
        )}
      </div>

      {!atBottom && !empty && (
        <button
          type="button"
          onClick={() => toBottom()}
          aria-label={unseen > 0 ? 'Jump to the new reply' : 'Jump to the latest message'}
          className="absolute bottom-[8.25rem] left-1/2 grid size-9 -translate-x-1/2 place-items-center rounded-full bg-white text-slate-700 shadow-md ring-1 ring-slate-200 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
        >
          <ChevronDown className="size-5" aria-hidden />
          {unseen > 0 && <span className="absolute -right-0.5 -top-0.5 size-2.5 rounded-full bg-brand-600" />}
        </button>
      )}

      {/* The message pill, pinned at the bottom. */}
      <form onSubmit={(e) => void send(e)} className="mx-auto w-full max-w-3xl shrink-0 px-4 pb-2 pt-2 sm:px-6">
        {error && (
          <div className="mb-2">
            <Alert>{error}</Alert>
          </div>
        )}
        <div className="flex items-end gap-2 rounded-[1.75rem] bg-slate-100 py-2 pl-5 pr-2 focus-within:bg-white focus-within:shadow-md focus-within:ring-1 focus-within:ring-slate-300">
          <label htmlFor="chat-input" className="sr-only">
            Your message
          </label>
          <textarea
            id="chat-input"
            ref={input}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKey}
            maxLength={MAX}
            rows={1}
            placeholder="Write here"
            className="max-h-44 min-h-9 flex-1 resize-none self-center border-0 bg-transparent py-1.5 text-[15px] leading-6 text-slate-900 placeholder:text-slate-500 focus:outline-none focus:ring-0"
          />
          <button
            type="submit"
            disabled={!text.trim() || sending}
            aria-label="Send"
            className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-800 text-white hover:bg-brand-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {sending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <ArrowUp className="size-[18px]" aria-hidden />}
          </button>
        </div>
        <p className="mt-2 px-2 text-center text-[11px] leading-4 text-slate-500">
          {EMERGENCY_LINE} <a href="tel:112" className="font-semibold text-brand-800 hover:underline">Call 112</a>
        </p>
        <p className="px-2 pb-1 text-center text-[11px] leading-4 text-slate-400">
          Prototype: the wording is a draft that a clinician has not reviewed yet. Not for real use.
          {text.length > MAX - 400 && <span className="ml-2 text-amber-700">{text.length}/{MAX}</span>}
        </p>
      </form>
    </div>
  )
}
