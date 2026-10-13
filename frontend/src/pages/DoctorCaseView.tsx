import { ArrowLeft } from 'lucide-react'
import { useParams, Link } from 'react-router-dom'
import ConsultThread from '../components/ConsultThread'
import { api } from '../lib/api'

/** One accepted case: the conversation with the person. Worrying language in their lines is flagged for the doctor only. */
export default function DoctorCaseView() {
  const id = Number(useParams().id)
  if (!Number.isFinite(id)) return null
  return (
    <div className="mx-auto max-w-2xl space-y-4 py-8">
      <Link to="/doctor" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-900">
        <ArrowLeft className="size-4" aria-hidden /> Back to cases
      </Link>
      <h1 className="font-display text-2xl font-medium text-slate-900">Conversation</h1>
      <ConsultThread
        load={() => api.doctorCaseMessages(id)}
        send={(t) => api.sendDoctorCaseMessage(id, t)}
        otherName="the person"
        showFlags
      />
      <p className="text-sm text-slate-500">
        Helplines for the person: Tele-MANAS 14416, KIRAN 1800-599-0019, emergency 112. Reading this conversation is recorded in the audit log.
      </p>
    </div>
  )
}
