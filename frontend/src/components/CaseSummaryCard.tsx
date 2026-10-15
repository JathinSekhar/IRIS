import { AlertTriangle, MessageSquareQuote } from 'lucide-react'
import type { ReactNode } from 'react'
import type { CaseSummary } from '../lib/types'
import { Card, cx } from './ui'

const RISK: Record<string, string> = {
  high: 'bg-red-50 text-red-800 ring-red-200',
  medium: 'bg-amber-50 text-amber-800 ring-amber-200',
  low: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  unknown: 'bg-slate-100 text-slate-700 ring-slate-200',
}
const BAND: Record<string, string> = {
  minimal: 'text-emerald-700',
  mild: 'text-sky-700',
  moderate: 'text-amber-700',
  moderately_severe: 'text-orange-700',
  severe: 'text-red-700',
}
const bandLabel = (b: string | null) => (b ? b.replace('_', ' ') : '')

function Chip({ children }: { children: ReactNode }) {
  return <span className="inline-flex rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700">{children}</span>
}

/** A score in plain words first (how they are doing), with the name of the questionnaire as small print for the clinician. */
function Tile({ title, level, levelClass, score, outOf, scale }: { title: string; level: string; levelClass?: string; score: number | null; outOf: number; scale: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      <p className={cx('mt-1.5 text-lg font-semibold capitalize leading-6', levelClass ?? 'text-slate-900')}>{level || 'Not available'}</p>
      {score !== null && (
        <p className="mt-0.5 text-xs text-slate-500">
          {score} out of {outOf} · {scale}
        </p>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      {children}
    </section>
  )
}

const fmt = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })

/** The doctor's summary of a person, structured so it can be scanned in a few seconds: who, check-in at a glance, what they wrote, then the overview. */
export default function CaseSummaryCard({ s, hideHeader = false }: { s: CaseSummary; hideHeader?: boolean }) {
  const p = s.profile
  const ck = s.checkin
  const { chat } = s
  return (
    <Card className="space-y-5 p-5">
      {!hideHeader && (
        <>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-display text-lg font-medium text-slate-900">
          {p.first_name}, {p.age}
        </h2>
        {p.gender && <Chip>{p.gender}</Chip>}
        {p.occupation && <Chip>{p.occupation}</Chip>}
        <Chip>{p.language_name ?? p.language}</Chip>
        {p.is_minor && <span className="inline-flex rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-900 ring-1 ring-inset ring-amber-200">Under 18</span>}
      </div>

        </>
      )}

      {s.narrative && (
        <Section title="In short">
          <p className="text-sm leading-6 text-slate-700">{s.narrative}</p>
        </Section>
      )}

      <Section title={ck ? `Latest check-in · ${fmt(ck.created_at)}` : 'Check-in'}>
        {ck ? (
          <>
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Overall</p>
                <span className={cx('mt-1.5 inline-flex rounded-full px-2.5 py-0.5 text-sm font-semibold capitalize ring-1 ring-inset', RISK[ck.baseline_risk] ?? RISK.unknown)}>
                  {ck.baseline_risk}
                </span>
                <p className="mt-1.5 text-xs text-slate-500">from the check-in</p>
              </div>
              <Tile title="Low mood" level={bandLabel(ck.phq9_band)} levelClass={BAND[ck.phq9_band ?? '']} score={ck.phq9} outOf={27} scale="PHQ-9" />
              <Tile title="Anxiety" level={bandLabel(ck.gad7_band)} levelClass={BAND[ck.gad7_band ?? '']} score={ck.gad7} outOf={21} scale="GAD-7" />
            </div>
            {(ck.safety_flag || ck.urgency_floor === 'medium' || ck.urgency_floor === 'high') && (
              <p className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-800">
                <AlertTriangle className="size-4 shrink-0" aria-hidden />
                Safety answers raised a flag{ck.urgency_floor && ck.urgency_floor !== 'none' ? ` (${ck.urgency_floor} floor)` : ''}.
              </p>
            )}
          </>
        ) : (
          <p className="text-sm text-slate-500">No completed check-in on file.</p>
        )}
      </Section>

      <Section title="What they wrote to IRIS">
        {chat.count === 0 ? (
          <p className="text-sm text-slate-500">Has not written to IRIS yet.</p>
        ) : (
          <>
            <p className="text-sm text-slate-700">
              {chat.count} recent message{chat.count !== 1 ? 's' : ''} ·{' '}
              <span className={chat.concerning > 0 ? 'font-semibold text-amber-800' : ''}>{chat.concerning} with concerning language</span>
              {chat.explicit > 0 && <span className="font-semibold text-red-700"> · {chat.explicit} explicit</span>}
            </p>
            {chat.topics.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {chat.topics.map((t) => (
                  <Chip key={t}>{t}</Chip>
                ))}
              </div>
            )}
            {chat.latest && (
              <blockquote className="flex gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-800">
                <MessageSquareQuote className="mt-0.5 size-4 shrink-0 text-slate-400" aria-hidden />
                <span>{chat.latest}</span>
              </blockquote>
            )}
          </>
        )}
      </Section>

      {(s.ai_summary || (s.ai_pending && !s.ai_summary)) && (
        <Section title="Overview">
          {s.ai_summary ? (
            <>
              <p className="text-sm leading-6 text-slate-800">{s.ai_summary}</p>
              <p className="text-xs text-slate-500">{s.ai_disclosure}</p>
            </>
          ) : (
            <p className="text-sm text-slate-500">A short written overview is being prepared…</p>
          )}
        </Section>
      )}

      <p className="border-t border-slate-100 pt-3 text-xs text-slate-500">
        The profile, check-in and counts are built by plain rules and stay inside IRIS.
      </p>
    </Card>
  )
}
