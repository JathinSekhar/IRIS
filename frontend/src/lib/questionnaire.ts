import type { Answers, Question } from './types'

/** Mirrors `is_visible` in backend/app/services/questionnaire.py. The server re-checks. */
export function isVisible(q: Question, answers: Answers): boolean {
  if (!q.show_if) return true
  const v = answers[q.show_if.question]
  if (typeof v !== 'number') return false
  return q.show_if.op === 'gt' ? v > q.show_if.value : v === q.show_if.value
}

/** Visible questions in definition order, evaluated progressively so parents gate children. */
export function visibleQuestions(questions: Question[], answers: Answers): Question[] {
  const seen: Answers = {}
  const out: Question[] = []
  for (const q of questions) {
    if (isVisible(q, seen)) {
      out.push(q)
      if (q.id in answers) seen[q.id] = answers[q.id]
    }
  }
  return out
}

/** Drop answers whose branch is no longer active (e.g. the user changed s0 back to 0). */
export function pruneAnswers(questions: Question[], answers: Answers): Answers {
  const keep = new Set(visibleQuestions(questions, answers).map((q) => q.id))
  return Object.fromEntries(Object.entries(answers).filter(([id]) => keep.has(id)))
}

export const CONSENT_VERSION = '2026-10'

export const BAND_LABEL: Record<string, string> = {
  minimal: 'Minimal',
  mild: 'Mild',
  moderate: 'Moderate',
  moderately_severe: 'Moderately severe',
  severe: 'Severe',
}
