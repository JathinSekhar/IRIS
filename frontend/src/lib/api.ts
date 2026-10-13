import type {
  Answers,
  ChatMessage,
  CheckinResult,
  Questionnaire,
  RegisterPayload,
  RegisterResult,
  ReviewerCheckin,
  ReviewerCheckinSummary,
  ReviewerMessage,
  ReviewerMessageSummary,
  UrgentAlerts,
  User,
  DoctorMe,
  Consult,
  DoctorOffer,
  DoctorCase,
  ThreadMessage,
  SessionNote,
  SessionNoteInput,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

const FIELD_LABELS: Record<string, string> = {
  email: 'Email',
  password: 'Password',
  full_name: 'Name',
  date_of_birth: 'Date of birth',
  guardian_email: "Guardian's email",
  guardian_name: "Guardian's name",
}

/** FastAPI returns `detail` as a string, or as a list of validation errors. */
function messageFrom(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { loc?: (string | number)[]; msg?: string; type?: string }
    const field = first.loc?.[first.loc.length - 1]
    const label = typeof field === 'string' ? FIELD_LABELS[field] : undefined
    if (first.type === 'string_too_short' && field === 'password') return 'Your password needs at least 8 characters.'
    if (first.type?.startsWith('value_error') && field === 'email') return 'Enter a valid email address.'
    return label ? `${label}: ${first.msg ?? 'is invalid'}` : (first.msg ?? 'Something in the form is invalid.')
  }
  if (status >= 500) return 'Something went wrong on our side. Please try again.'
  return 'Something went wrong. Please try again.'
}

/** Endpoints where a 401 means "wrong credentials / bad link", not "your session expired". */
const NO_REFRESH = [
  '/api/auth/login',
  '/api/auth/register',
  '/api/auth/refresh',
  '/api/auth/logout',
  '/api/auth/forgot-password',
  '/api/auth/reset-password',
]

let refreshing: Promise<boolean> | null = null

/** Ask the server to swap the refresh cookie for a new session. Concurrent callers share one request. */
function refreshSession(): Promise<boolean> {
  refreshing ??= fetch('/api/auth/refresh', { method: 'POST', credentials: 'same-origin' })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

async function request<T>(path: string, init: RequestInit = {}, retried = false): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      credentials: 'same-origin',
      ...init,
      headers: { ...(init.body ? { 'Content-Type': 'application/json' } : {}), ...init.headers },
    })
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.")
  }
  // The short-lived access token expired: renew it once, silently, and repeat the request.
  if (res.status === 401 && !retried && !NO_REFRESH.includes(path) && (await refreshSession())) {
    return request<T>(path, init, true)
  }
  if (res.status === 204) return undefined as T
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, messageFrom(body, res.status))
  return body as T
}

const post = <T>(path: string, data?: unknown) =>
  request<T>(path, { method: 'POST', body: data === undefined ? undefined : JSON.stringify(data) })

export const api = {
  me: () => request<User>('/api/auth/me'),
  login: (email: string, password: string) => post<User>('/api/auth/login', { email, password }),
  register: (data: RegisterPayload) => post<RegisterResult>('/api/auth/register', data),
  logout: () => post<void>('/api/auth/logout'),
  forgotPassword: (email: string) => post<void>('/api/auth/forgot-password', { email }),
  resetPassword: (access_token: string, password: string) =>
    post<void>('/api/auth/reset-password', { access_token, password }),
  acceptConsent: (version: string) => post<User>('/api/consent', { version }),
  questionnaire: () => request<Questionnaire>('/api/checkin/questionnaire'),
  submitCheckin: (answers: Answers) => post<CheckinResult>('/api/checkin', { answers }),
  skipCheckin: () => post<CheckinResult>('/api/checkin', { skipped: true }),
  reviewerQueue: () => request<ReviewerCheckinSummary[]>('/api/reviewer/checkins'),
  reviewerCheckin: (id: number) => request<ReviewerCheckin>(`/api/reviewer/checkins/${id}`),
  sendMessage: (text: string) => post<ChatMessage>('/api/messages', { text }),
  messages: () => request<ChatMessage[]>('/api/messages'),
  doctorMe: () => request<DoctorMe>('/api/doctor/me'),
  doctorAvailability: (on_duty: boolean) => post<DoctorMe>('/api/doctor/availability', { on_duty }),
  currentConsult: () => request<Consult | null>('/api/consults/current'),
  consultNotice: () => request<{ share_notice: string }>('/api/consults/notice'),
  requestDoctor: (share: boolean) => post<Consult>('/api/consults', { share }),
  cancelConsult: (id: number) => post<Consult>(`/api/consults/${id}/cancel`),
  doctorOffers: () => request<DoctorOffer[]>('/api/doctor/offers'),
  doctorCases: () => request<DoctorCase[]>('/api/doctor/cases'),
  acceptOffer: (id: number) => post<DoctorCase>(`/api/doctor/offers/${id}/accept`),
  declineOffer: (id: number) => post<void>(`/api/doctor/offers/${id}/decline`),
  consultMessages: (id: number) => request<ThreadMessage[]>(`/api/consults/${id}/messages`),
  sendConsultMessage: (id: number, text: string) => post<ThreadMessage>(`/api/consults/${id}/messages`, { text }),
  doctorCaseMessages: (id: number) => request<ThreadMessage[]>(`/api/doctor/cases/${id}/messages`),
  sendDoctorCaseMessage: (id: number, text: string) => post<ThreadMessage>(`/api/doctor/cases/${id}/messages`, { text }),
  closeCase: (id: number, note: SessionNoteInput) => post<SessionNote>(`/api/doctor/cases/${id}/close`, note),
  doctorCaseNote: (id: number) => request<SessionNote>(`/api/doctor/cases/${id}/note`),
  reviewerAlerts: () => request<UrgentAlerts>('/api/reviewer/alerts'),
  reviewerMessages: () => request<ReviewerMessageSummary[]>('/api/reviewer/messages'),
  reviewerMessage: (id: number) => request<ReviewerMessage>(`/api/reviewer/messages/${id}`),
  escalateMessage: (id: number, to: 'medium' | 'high', reason: string) =>
    post<ReviewerMessage>(`/api/reviewer/messages/${id}/escalate`, { to, reason }),
  reviewMessage: (id: number, urgency: 'low' | 'medium' | 'high', notes: string) =>
    post<ReviewerMessage>(`/api/reviewer/messages/${id}/review`, { urgency, notes }),
}
