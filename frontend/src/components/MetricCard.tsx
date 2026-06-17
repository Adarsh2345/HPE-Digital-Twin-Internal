import type { LucideIcon } from 'lucide-react'

interface MetricCardProps {
  label: string
  value: string
  subtitle?: string
  subtitleColor?: 'green' | 'red' | 'yellow' | 'muted'
  icon: LucideIcon
  iconColor: string
}

const dotColors = {
  green: 'bg-green-400',
  red: 'bg-red-400',
  yellow: 'bg-yellow-400',
  muted: 'bg-muted',
}

export default function MetricCard({
  label,
  value,
  subtitle,
  subtitleColor = 'muted',
  icon: Icon,
  iconColor,
}: MetricCardProps) {
  return (
    <div className="card p-5 flex items-start justify-between">
      <div>
        <p className="text-sm text-muted mb-2">{label}</p>
        <p className="text-3xl font-bold text-white tracking-tight">{value}</p>
        {subtitle && (
          <div className="flex items-center gap-1.5 mt-2">
            <span className={`w-1.5 h-1.5 rounded-full ${dotColors[subtitleColor]}`} />
            <span className="text-xs text-muted">{subtitle}</span>
          </div>
        )}
      </div>
      <div
        className="w-10 h-10 rounded-lg flex items-center justify-center"
        style={{ backgroundColor: `${iconColor}20` }}
      >
        <Icon className="w-5 h-5" style={{ color: iconColor }} />
      </div>
    </div>
  )
}
