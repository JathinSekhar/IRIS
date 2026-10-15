import { AlertTriangle } from 'lucide-react'
import type { ReactNode } from 'react'
import type { CaseSummary } from '../lib/types'
import { cx } from './ui'

const LEVEL: Record<string, string> = {
  high: 'text-red-700', severe: 'text-red-700', moderately_severe: 'text-orange-700',
  medium: 'text-amber-700', moderate: 'text-amber-700', mild: 'text-sky-700', low: 'text-emerald-700', minimal: 'text-emerald-700',
}
const nice = (b: string | null | undefined) => (b ? b.replace('_', ' ') : 'n/a')

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-1.5">
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      {children}
    </section>
  )
}

function Row({ label, value, raw }: { label: string; value: string | null | undefined; raw?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 text-sm">
      <span className="text-slate-600">{label}</span>
      <span className={cx('font-semibold capitalize', LEVEL[value ?? ''] ?? 'text-slate-800')}>
        {nice(value)}
        {raw && <span className="ml-1.5 text-xs font-normal normal-case text-slate-400">{raw}</span>}
      </span>
    </div>
  )
}

/** The summary beside the conversation: a few plain sentences, the check-in in three lines, and the AI overview when there is one. */
export default function CaseSummarySimple({ s }: { s: CaseSummary }) {
  const ck = s.checkin
  return (
    <div className="space-y-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <Block title="In short">
        <p className="text-sm leading-6 text-slate-700">{s.narrative}</p>
      </Block>

      <Block title={ck ? `Check-in · ${new Date(ck.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}` : 'Check-in'}>
        {ck ? (
          <div className="divide-y divide-slate-100">
            <Row label="Overall" value={ck.baseline_risk} />
            <Row label="Low mood" value={ck.phq9_band} raw={ck.phq9 !== null ? `${ck.phq9}/27` : undefined} />
            <Row label="Anxiety" value={ck.gad7_band} raw={ck.gad7 !== null ? `${ck.gad7}/21` : undefined} />
          </div>
        ) : (
          <p className="text-sm text-slate-500">No check-in on file.</p>
        )}
        {ck && (ck.safety_flag || ck.urgency_floor === 'medium' || ck.urgency_floor === 'high') && (
          <p className="mt-1 flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-800">
            <AlertTriangle className="size-4 shrink-0" aria-hidden /> Safety answers raised a flag
          </p>
        )}
      </Block>

      {(s.ai_summary || s.ai_pending) && (
        <Block title="Overview">
          {s.ai_summary ? (
            <>
              <p className="text-sm leading-6 text-slate-700">{s.ai_summary}</p>
              <p className="text-xs text-slate-400">{s.ai_disclosure}</p>
            </>
          ) : (
            <p className="text-sm text-slate-500">Being prepared…</p>
          )}
        </Block>
      )}
    </div>
  )
}
