import { Phone } from 'lucide-react'
import { useId } from 'react'
import { Link } from 'react-router-dom'

/** The IRIS mark: a teal tile, an iris ring and a glowing pupil with a highlight. Gradient ids are unique per use, so several marks can share a page. */
export function LogoMark({ className = 'size-8' }: { className?: string }) {
  const id = useId().replace(/:/g, '')
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden>
      <defs>
        <linearGradient id={`${id}t`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2a6a6b" />
          <stop offset="1" stopColor="#143a3c" />
        </linearGradient>
        <radialGradient id={`${id}p`} cx=".38" cy=".35" r=".75">
          <stop offset="0" stopColor="#b8ece4" />
          <stop offset=".55" stopColor="#7ccdc3" />
          <stop offset="1" stopColor="#3fa99d" />
        </radialGradient>
      </defs>
      <rect width="40" height="40" rx="11" fill={`url(#${id}t)`} />
      <rect x=".75" y=".75" width="38.5" height="38.5" rx="10.3" fill="none" stroke="#fff" strokeOpacity=".14" strokeWidth="1.5" />
      <circle cx="20" cy="20" r="11" fill="none" stroke="#fff" strokeWidth="2.4" />
      <circle cx="20" cy="20" r="7.2" fill="none" stroke="#fff" strokeOpacity=".28" strokeWidth="1" />
      <circle cx="20" cy="20" r="4.6" fill={`url(#${id}p)`} />
      <circle cx="18.4" cy="18.3" r="1.25" fill="#fff" fillOpacity=".9" />
    </svg>
  )
}

export function Logo({ light = false }: { light?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark className="size-8 drop-shadow-[0_2px_4px_rgba(20,58,60,0.25)]" />
      <span className={`font-display text-xl font-semibold tracking-[0.04em] ${light ? 'text-white' : 'text-[#163f41]'}`}>
        IRIS
      </span>
    </span>
  )
}

export function CrisisStrip() {
  return (
    <p className="flex items-center justify-center gap-2 bg-slate-900 px-4 py-2 text-center text-xs text-slate-200">
      <Phone className="size-3.5 shrink-0" aria-hidden />
      <span>
        In crisis or need to talk now? Call{' '}
        <a href="tel:14416" className="font-semibold text-white underline underline-offset-2">
          Tele-MANAS 14416
        </a>{' '}
        (free, 24x7).{' '}
        <Link to="/emergency" className="font-semibold text-white underline underline-offset-2">
          Emergency help
        </Link>
      </span>
    </p>
  )
}
