import { AlertCircle, Loader2 } from 'lucide-react'
import {
  useId,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'

const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' ')

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost'
  loading?: boolean
  block?: boolean
}

export function Button({ variant = 'primary', loading, block, className, children, disabled, ...rest }: ButtonProps) {
  const styles = {
    primary: 'bg-brand-800 text-white hover:bg-brand-900 shadow-sm',
    secondary: 'bg-white text-slate-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50',
    ghost: 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
  }[variant]
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx(
        'inline-flex h-11 items-center justify-center gap-2 rounded-lg px-5 text-sm font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-60',
        styles,
        block && 'w-full',
        className,
      )}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  )
}

export function TextLink({ className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={cx('rounded text-sm font-medium text-brand-700 underline-offset-4 hover:underline', className)}
    />
  )
}

const inputBase =
  'block w-full rounded-lg border border-slate-300 bg-white px-3.5 text-sm text-slate-900 shadow-sm ' +
  'placeholder:text-slate-400 focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-600/25'

interface FieldProps {
  label: string
  hint?: string
  optional?: boolean
  error?: string
  children: (id: string, describedBy: string | undefined) => ReactNode
}

export function Field({ label, hint, optional, error, children }: FieldProps) {
  const id = useId()
  const descId = hint || error ? `${id}-desc` : undefined
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 flex items-baseline justify-between text-sm font-medium text-slate-700">
        <span>{label}</span>
        {optional && <span className="text-xs font-normal text-slate-500">Optional</span>}
      </label>
      {children(id, descId)}
      {(error || hint) && (
        <p id={descId} className={cx('mt-1.5 text-xs', error ? 'text-red-700' : 'text-slate-500')}>
          {error ?? hint}
        </p>
      )}
    </div>
  )
}

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={cx(inputBase, 'h-11', className)} />
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={cx(inputBase, 'h-11 pr-8', className)}>
      {children}
    </select>
  )
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...rest} className={cx(inputBase, 'min-h-32 py-3 leading-relaxed', className)} />
}

export function Alert({ children, tone = 'error' }: { children: ReactNode; tone?: 'error' | 'info' }) {
  const styles =
    tone === 'error'
      ? 'border-red-200 bg-red-50 text-red-900'
      : 'border-brand-200 bg-brand-50 text-brand-900'
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={cx('flex gap-2.5 rounded-lg border p-3 text-sm', styles)}>
      <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  )
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return (
    <div role="status" className="grid min-h-[40vh] place-items-center text-slate-500">
      <Loader2 className="size-6 animate-spin" aria-hidden />
      <span className="sr-only">{label}</span>
    </div>
  )
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cx('rounded-xl border border-slate-200 bg-white shadow-sm', className)}>{children}</div>
}

export { cx }
