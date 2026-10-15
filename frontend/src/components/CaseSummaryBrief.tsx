import type { CaseSummary } from '../lib/types'

/** The person in a few plain sentences, from their check-in answers and how they have used the chat. The full detail is on the case page. */
export default function CaseSummaryBrief({ s }: { s: CaseSummary }) {
  return <p className="text-sm leading-6 text-slate-600">{s.narrative}</p>
}
