import { AlertTriangle, ArrowUp } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ApiError } from '../lib/api'
import type { ThreadMessage } from '../lib/types'
import { Alert, cx } from './ui'

const time = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })

/** A two-person conversation (person and doctor). `load` and `send` decide which side of the API this is, so both screens share one component. */
export default function ConsultThread({
  load,
  send,
  otherName,
  showFlags = false,
  active = true,
}: {
  load: () => Promise<ThreadMessage[]>
  send: (text: string) => Promise<ThreadMessage>
  otherName: string
  showFlags?: boolean
  active?: boolean
}) {
  const [items, setItems] = useState<ThreadMessage[]>([])
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
  const list = useRef<HTMLDivElement>(null)
  const count = useRef(0)

  const refresh = useCallback(() => {
    load().then(setItems).catch(() => undefined)
  }, [load])

  useEffect(() => {
    refresh()
    const t = window.setInterval(refresh, 3000)
    return () => window.clearInterval(t)
  }, [refresh])

  useEffect(() => {
    if (items.length !== count.current && list.current) {
      list.current.scrollTo({ top: list.current.scrollHeight, behavior: 'instant' as ScrollBehavior })
      count.current = items.length
    }
  }, [items])

  async function submit(e?: FormEvent) {
    e?.preventDefault()
    const t = text.trim()
    if (!t || sending) return
    setSending(true)
    setError('')
    try {
      const m = await send(t)
      setItems((prev) => [...prev, m])
      setText('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Your message was not sent. Please try again.')
    } finally {
      setSending(false)
    }
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void submit()
    }
  }

  return (
    <div className="flex flex-col rounded-2xl border border-slate-200 bg-white">
      <div ref={list} className="max-h-[50vh] min-h-48 space-y-3 overflow-y-auto p-4" aria-label="Conversation" aria-live="polite">
        {items.length === 0 && <p className="text-sm text-slate-500">No messages yet. Say hello to {otherName}.</p>}
        {items.map((m) => (
          <div key={m.id} className={cx('flex', m.mine ? 'justify-end' : 'justify-start')}>
            <div className={cx('max-w-[85%] rounded-2xl px-4 py-2.5 text-[15px] leading-6', m.mine ? 'bg-brand-800 text-white' : 'bg-slate-100 text-slate-900')}>
              <p className="whitespace-pre-wrap break-words">{m.text}</p>
              <p className={cx('mt-1 flex items-center gap-1.5 text-xs', m.mine ? 'text-white/70' : 'text-slate-500')}>
                {showFlags && (m.flag === 'urgent' || (m.urgent && !m.flag)) && (
                  <span className="inline-flex items-center gap-1 rounded bg-red-600 px-1.5 font-semibold text-white">
                    <AlertTriangle className="size-3.5" aria-hidden /> Urgent
                  </span>
                )}
                {showFlags && m.flag === 'worrying' && (
                  <span className="inline-flex items-center gap-1 font-semibold text-amber-700">
                    <AlertTriangle className="size-3.5" aria-hidden /> Worrying language
                  </span>
                )}
                {time(m.created_at)}
              </p>
            </div>
          </div>
        ))}
      </div>

      {error && (
        <div className="px-4 pb-2">
          <Alert>{error}</Alert>
        </div>
      )}

      {active ? (
        <form onSubmit={(e) => void submit(e)} className="flex items-end gap-2 border-t border-slate-200 p-3">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKey}
            rows={1}
            maxLength={2000}
            placeholder={`Write to ${otherName}`}
            aria-label={`Write to ${otherName}`}
            className="max-h-32 min-h-11 flex-1 resize-none rounded-xl bg-slate-100 px-4 py-2.5 text-[15px] outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
          />
          <button
            type="submit"
            disabled={!text.trim() || sending}
            aria-label="Send"
            className="grid size-11 shrink-0 place-content-center rounded-full bg-brand-800 text-white disabled:bg-slate-300"
          >
            <ArrowUp className="size-5" aria-hidden />
          </button>
        </form>
      ) : (
        <p className="border-t border-slate-200 p-3 text-sm text-slate-500">This conversation has ended.</p>
      )}
    </div>
  )
}
