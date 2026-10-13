export type Answer = number | string | number[]
export type Answers = Record<string, Answer>

export interface Option {
  value: number
  label: string
}
export interface Condition {
  question: string
  op: 'gt' | 'eq'
  value: number
}
export type QuestionType = 'text' | 'single' | 'multi' | 'frequency' | 'yesno'
export interface Question {
  id: string
  section: string
  type: QuestionType
  prompt: string
  stem: string | null
  options: Option[]
  show_if: Condition | null
}
export interface Section {
  id: string
  title: string
  description: string
}
export interface Questionnaire {
  version: string
  sections: Section[]
  questions: Question[]
}

export interface CheckinStatus {
  state: 'none' | 'due' | 'ok'
  last_completed_at: string | null
  next_due_at: string | null
  safety_flag: boolean
  prompt: boolean
}
export interface User {
  id: string
  email: string
  full_name: string
  first_name: string
  role: 'user' | 'reviewer' | 'doctor'
  is_minor: boolean
  guardian_consent_status: string | null
  consent_accepted: boolean
  checkin: CheckinStatus
}
export interface CheckinResult {
  id: number
  skipped: boolean
  safety_flag: boolean
  show_crisis_resources: boolean
  created_at: string
}

export interface Scale {
  score: number
  max: number
  band: string
  answered: number
  complete: boolean
}
export interface ReviewerCheckinSummary {
  id: number
  user_name: string
  created_at: string
  baseline_risk: 'unknown' | 'low' | 'medium' | 'high'
  safety_flag: boolean
  escalated: boolean
}

export interface ReviewerCheckin {
  id: number
  user_id: string
  user_name: string
  user_email: string
  created_at: string
  skipped: boolean
  baseline_risk: 'unknown' | 'low' | 'medium' | 'high'
  safety_flag: boolean
  escalated: boolean
  scores: {
    phq9: Scale
    gad7: Scale
    safety: {
      flag: boolean
      tier: number
      tier_label: string
      escalate: boolean
      urgency_floor: 'none' | 'medium' | 'high'
    }
    functioning: number | null
    baseline_risk: string
  }
  answers: Answers
  free_text: string | null
  is_minor: boolean
  emergency_contact: string | null
  date_of_birth: string
}

export interface RegisterResult {
  confirm_email: boolean
  user: User | null
}

export interface RegisterPayload {
  full_name: string
  email: string
  password: string
  date_of_birth: string
  gender?: string
  occupation?: string
  language?: string
  phone?: string
  emergency_contact?: string
  guardian_name?: string
  guardian_email?: string
}

// --- chat ("Talk to IRIS") ---------------------------------------------------------------------------------------------------------------------
export interface ReplyItem {
  title: string
  how: string
}
/** Everything the person may see. The server never sends an urgency label, score or reason. */
export interface Helpline {
  name: string
  detail: string
  number: string
  tel: string
}
/** How to present a reply. Presentation only: never shown to the person as a word. */
export type Layout = 'tips' | 'celebrate' | 'support' | 'help_now'
export interface SupportReply {
  layout: Layout
  helplines: Helpline[]
  intro: string
  listening: string
  self_help: ReplyItem[]
  reach_out: string[]
  crisis_lead: string
  crisis_lines: string[]
  show_crisis_resources: boolean
  emergency_footer: string
  closing: string
  a_person_may_reach_out: boolean
  companion?: string | null
}
export type CareStatus = 'waiting' | 'being_read' | 'reviewed'
export interface ChatMessage {
  id: number
  text: string
  created_at: string
  reply: SupportReply
  care_status: CareStatus
  status_text: string
}

// --- doctor ---------------------------------------------------------------------------------------------------------------------------------
export interface DoctorMe {
  full_name: string
  specialty: string
  registration_number: string
  languages: string[]
  on_duty: boolean
  on_duty_changed_at: string | null
}

// --- reviewer: the human review queue for messages ---------------------------------------------------------------------------------------------
export type Priority = 'low' | 'medium' | 'high'
export interface ReviewerMessageSummary {
  id: number
  user_name: string
  created_at: string
  priority: Priority
  status: string
  rule_flagged: boolean
  reviewer_raised: boolean
  baseline_floor: string
  opened: boolean
  urgent: boolean
}
export interface UrgentAlerts {
  urgent_waiting: number
  urgent_unopened: number
  oldest_unopened_seconds: number | null
  latest_urgent_id: number | null
}
export interface ReviewEvent {
  id: number
  kind: 'escalation' | 'judgement'
  from_urgency: string | null
  to_urgency: string
  notes: string
  reviewer_name: string
  created_at: string
}
export interface ReviewerMessage {
  id: number
  user_id: string
  user_name: string
  user_email: string
  text: string
  created_at: string
  priority: Priority
  initial_priority: string
  status: string
  rule_level: string
  rule_hits: string[]
  baseline_floor: string
  baseline_known: boolean
  baseline_risk: string | null
  checkin_id: number | null
  reasons: string[]
  reviewer_note: string
  model_version: string
  policy_version: string
  reply_shown: SupportReply
  history: ReviewEvent[]
}
