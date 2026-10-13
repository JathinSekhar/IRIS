import { HeartHandshake, LogOut, ShieldCheck, Stethoscope, UserCheck, type LucideIcon } from 'lucide-react'
import { Link, Navigate, Outlet, useLocation } from 'react-router-dom'
import { homeFor, useAuth } from '../auth/AuthContext'
import { CrisisStrip, Logo } from '../components/Brand'
import { Spinner } from '../components/ui'

const FEATURES: { icon: LucideIcon; title: string; text: string }[] = [
  { icon: ShieldCheck, title: 'Confidential', text: 'Only trained reviewers can see what you share.' },
  {
    icon: Stethoscope,
    title: 'Clinically grounded',
    text: 'Uses the same screening questions doctors use: PHQ-9, GAD-7 and C-SSRS.',
  },
  { icon: UserCheck, title: 'People in the loop', text: 'Urgent and uncertain cases always go to a human.' },
]

/** Public pages: split-screen on desktop, single column on mobile. */
export function AuthLayout() {
  const { user, loading } = useAuth()
  if (loading) return <Spinner />
  if (user) return <Navigate to={homeFor(user)} replace />
  return (
    <div className="flex min-h-dvh flex-col">
      <CrisisStrip />
      <div className="grid flex-1 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <aside className="relative hidden overflow-hidden bg-brand-900 p-12 text-brand-50 lg:flex lg:flex-col lg:justify-between">
          <div aria-hidden className="pointer-events-none absolute -right-32 -top-32 size-[28rem] rounded-full border border-white/10" />
          <div aria-hidden className="pointer-events-none absolute -right-12 -top-12 size-[18rem] rounded-full border border-white/10" />
          <Logo light />
          <div className="relative max-w-md">
            <h1 className="font-display text-4xl font-medium leading-tight text-white">
              Support that listens first, and brings in a person when it matters.
            </h1>
            <p className="mt-5 text-base leading-relaxed text-brand-100">
              IRIS understands what you are going through, how urgent it is, and who is best placed to help, with trained
              reviewers making the final call.
            </p>
            <ul className="mt-10 space-y-5 text-sm">
              {FEATURES.map(({ icon: Icon, title, text }) => (
                <li key={title} className="flex gap-3.5">
                  <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-white/10">
                    <Icon className="size-[18px] text-brand-200" aria-hidden />
                  </span>
                  <span>
                    <span className="block font-medium text-white">{title}</span>
                    <span className="text-brand-100">{text}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <p className="relative text-xs text-brand-200/80">
            IRIS is a screening and support-routing tool. It does not diagnose and is not a substitute for professional care.
          </p>
        </aside>
        <main className="flex items-center justify-center px-5 py-10 sm:px-10">
          <div className="w-full max-w-md">
            <div className="mb-8 lg:hidden">
              <Logo />
            </div>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}

/** Authenticated pages. Enforces consent and check-in gates for end users. */
export function AppLayout() {
  const { user, loading, logout } = useAuth()
  const { pathname } = useLocation()
  if (loading) return <Spinner />
  if (!user) return <Navigate to="/login" replace state={{ from: pathname }} />

  if (user.role === 'reviewer') {
    if (!pathname.startsWith('/reviewer')) return <Navigate to="/reviewer" replace />
  } else if (user.role === 'doctor') {
    if (!pathname.startsWith('/doctor')) return <Navigate to="/doctor" replace />
  } else {
    if (pathname.startsWith('/reviewer') || pathname.startsWith('/doctor')) return <Navigate to="/" replace />
    if (!user.consent_accepted && pathname !== '/consent') return <Navigate to="/consent" replace />
  }

  const focused = pathname === '/consent' || pathname === '/check-in' || pathname === '/support'
  // The chat is an app-like screen: it fills the viewport and only its message list scrolls, so the message box never scrolls away.
  const chat = pathname === '/chat'
  return (
    <div className={chat ? 'flex h-dvh flex-col overflow-hidden' : 'flex min-h-dvh flex-col'}>
      <CrisisStrip />
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
          <Link to="/" aria-label="IRIS home">
            <Logo />
          </Link>
          <div className="flex items-center gap-4">
            <span className="hidden text-sm text-slate-600 sm:inline">
              {user.role === 'reviewer' ? 'Reviewer · ' : user.role === 'doctor' ? 'Doctor · ' : ''}
              {user.full_name}
            </span>
            <button
              onClick={() => void logout()}
              className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            >
              <LogOut className="size-4" aria-hidden /> Log out
            </button>
          </div>
        </div>
      </header>
      <main
        className={
          chat
            ? 'flex min-h-0 w-full flex-1 flex-col'
            : focused ? 'mx-auto w-full max-w-3xl flex-1 px-5 py-8 sm:py-12' : 'mx-auto w-full max-w-6xl flex-1 px-5 py-8'
        }
      >
        <Outlet />
      </main>
      {!chat && (
        <footer className="border-t border-slate-200 py-5 text-center text-xs text-slate-500">
          <HeartHandshake className="mr-1 inline size-3.5" aria-hidden />
          IRIS supports, it does not diagnose. Your answers are confidential.
        </footer>
      )}
    </div>
  )
}
