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
  role: 'user' | 'reviewer'
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
