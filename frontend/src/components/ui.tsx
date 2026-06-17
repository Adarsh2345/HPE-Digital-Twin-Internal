import type { ReactNode } from 'react'
import { Loader2 } from 'lucide-react'

export function LoadingSpinner({ label = 'Loading...' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-muted">
      <Loader2 className="w-5 h-5 animate-spin text-accent" />
      <span className="text-sm">{label}</span>
    </div>
  )
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
      {message}
    </div>
  )
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <p className="text-base font-medium text-gray-300">{title}</p>
      {description && <p className="mt-2 text-sm text-muted max-w-md">{description}</p>}
    </div>
  )
}

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <h1 className="page-title">{title}</h1>
      {subtitle && <p className="page-subtitle">{subtitle}</p>}
    </div>
  )
}

export function Card({
  title,
  subtitle,
  children,
  className = '',
}: {
  title?: string
  subtitle?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`card p-5 ${className}`}>
      {(title || subtitle) && (
        <div className="mb-4">
          {title && <h2 className="text-base font-semibold text-white">{title}</h2>}
          {subtitle && <p className="text-xs text-muted mt-0.5">{subtitle}</p>}
        </div>
      )}
      {children}
    </div>
  )
}
