import type {
  Answers,
  CheckinResult,
  Questionnaire,
  RegisterPayload,
  ReviewerCheckin,
  User,
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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
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
  register: (data: RegisterPayload) => post<User>('/api/auth/register', data),
  logout: () => post<void>('/api/auth/logout'),
  acceptConsent: (version: string) => post<User>('/api/consent', { version }),
  questionnaire: () => request<Questionnaire>('/api/checkin/questionnaire'),
  submitCheckin: (answers: Answers) => post<CheckinResult>('/api/checkin', { answers }),
  skipCheckin: () => post<CheckinResult>('/api/checkin', { skipped: true }),
  reviewerCheckins: () => request<ReviewerCheckin[]>('/api/reviewer/checkins'),
}
