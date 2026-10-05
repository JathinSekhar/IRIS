import { Phone } from 'lucide-react'

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="size-8" aria-hidden>
        <rect width="32" height="32" rx="8" fill={light ? '#ffffff' : '#1e4d4f'} fillOpacity={light ? 0.12 : 1} />
        <circle cx="16" cy="16" r="8.5" fill="none" stroke="#fff" strokeWidth="2.2" />
        <circle cx="16" cy="16" r="3.4" fill="#7ccdc3" />
      </svg>
      <span className={`font-display text-xl font-semibold tracking-tight ${light ? 'text-white' : 'text-brand-900'}`}>
        IRIS
      </span>
    </span>
  )
}

export const HELPLINES = [
  { name: 'Tele-MANAS', detail: '24x7, free, confidential', number: '14416', tel: '14416' },
  { name: 'KIRAN', detail: 'Mental health rehabilitation helpline', number: '1800-599-0019', tel: '18005990019' },
] as const

export function CrisisStrip() {
  return (
    <p className="flex items-center justify-center gap-2 bg-slate-900 px-4 py-2 text-center text-xs text-slate-200">
      <Phone className="size-3.5 shrink-0" aria-hidden />
      <span>
        In crisis or need to talk now? Call{' '}
        <a href="tel:14416" className="font-semibold text-white underline underline-offset-2">
          Tele-MANAS 14416
        </a>{' '}
        (free, 24x7).
      </span>
    </p>
  )
}
