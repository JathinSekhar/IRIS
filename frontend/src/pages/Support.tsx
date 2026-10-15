import { HeartHandshake, Phone } from 'lucide-react'
import { Link } from 'react-router-dom'
import { HELPLINES } from '../components/Brand'
import DoctorOfferCard from '../components/DoctorOfferCard'
import { Card } from '../components/ui'

export default function Support() {
  return (
    <Card className="p-6 sm:p-10">
      <span className="grid size-12 place-items-center rounded-full bg-brand-100 text-brand-800">
        <HeartHandshake className="size-6" aria-hidden />
      </span>
      <h1 className="mt-5 font-display text-3xl font-medium text-slate-900">Thank you for telling us</h1>
      <p className="mt-3 max-w-xl text-slate-600">
        That took courage. You do not have to carry this alone, and there are people ready to listen right now. A trained
        member of our care team will also look at your answers and may reach out.
      </p>

      <DoctorOfferCard className="mt-6" />

      <p className="mt-8 text-sm font-medium text-slate-900">Talk to someone now</p>
      <ul className="mt-3 space-y-3">
        {HELPLINES.map((h) => (
          <li key={h.tel} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 p-4">
            <div>
              <p className="font-medium text-slate-900">{h.name}</p>
              <p className="text-sm text-slate-600">{h.detail}</p>
            </div>
            <a href={`tel:${h.tel}`}
              className="inline-flex h-11 items-center gap-2 rounded-lg bg-brand-800 px-5 text-sm font-medium text-white hover:bg-brand-900">
              <Phone className="size-4" aria-hidden /> {h.number}
            </a>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-sm text-slate-600">
        If you are in immediate danger, call <strong>112</strong> or go to the nearest emergency room.
      </p>

      <Link to="/" className="mt-8 inline-flex h-11 items-center rounded-lg px-1 text-sm font-medium text-brand-700 underline-offset-4 hover:underline">
        Continue to IRIS
      </Link>
    </Card>
  )
}
