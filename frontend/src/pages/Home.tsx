import { CalendarClock, ClipboardCheck, MessageCircle } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import DoctorOfferCard from '../components/DoctorOfferCard'
import { Card } from '../components/ui'

const fmt = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' }) : null

export default function Home() {
  const { user } = useAuth()
  const [offered, setOffered] = useState(false)
  if (!user) return null
  const { checkin } = user
  const completed = checkin.state === 'ok' || checkin.state === 'due'

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="font-display text-3xl font-medium text-slate-900">Hi {user.first_name}</h1>
      <p className="mt-2 text-slate-600">This is your private space. Take your time.</p>

      <DoctorOfferCard className="mt-6" onPresence={setOffered} />

      {!offered && (
      <Card className="mt-8 flex flex-col gap-3 p-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="font-medium text-slate-900">Talk to a doctor</h2>
          <p className="mt-1 text-sm text-slate-600">Ask for a doctor on the IRIS team. They may not be able to answer straight away.</p>
        </div>
        <Link to="/talk-to-a-doctor"
          className="inline-flex h-10 shrink-0 items-center rounded-lg border border-brand-800 px-4 text-sm font-medium text-brand-800 hover:bg-brand-50">
          Ask for a doctor
        </Link>
      </Card>
      )}

      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        <Card className="p-6">
          <MessageCircle className="size-6 text-brand-700" aria-hidden />
          <h2 className="mt-4 font-medium text-slate-900">Talk to IRIS</h2>
          <p className="mt-1.5 text-sm text-slate-600">
            Share what is on your mind. IRIS understands how urgent it is and brings in a person when needed.
          </p>
          <Link to="/chat"
            className="mt-4 inline-flex h-10 items-center rounded-lg bg-brand-800 px-4 text-sm font-medium text-white hover:bg-brand-900">
            Start talking
          </Link>
        </Card>

        <Card className="p-6">
          <ClipboardCheck className="size-6 text-brand-700" aria-hidden />
          <h2 className="mt-4 font-medium text-slate-900">Health check-in</h2>
          {completed ? (
            <p className="mt-1.5 text-sm text-slate-600">
              Completed {fmt(checkin.last_completed_at)}.
              {checkin.state === 'ok' && checkin.next_due_at && (
                <span className="mt-2 flex items-center gap-1.5 text-slate-500">
                  <CalendarClock className="size-4" aria-hidden /> Next one due {fmt(checkin.next_due_at)}
                </span>
              )}
            </p>
          ) : (
            <p className="mt-1.5 text-sm text-slate-600">
              You have not completed your check-in yet. It takes about 6 minutes and helps us support you better.
            </p>
          )}
          {(!completed || checkin.state === 'due') && (
            <Link to="/check-in"
              className="mt-4 inline-flex h-10 items-center rounded-lg bg-brand-800 px-4 text-sm font-medium text-white hover:bg-brand-900">
              {completed ? 'Update my check-in' : 'Start check-in'}
            </Link>
          )}
        </Card>
      </div>
    </div>
  )
}
