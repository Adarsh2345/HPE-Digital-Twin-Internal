import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Network,
  PlayCircle,
  GitCompareArrows,
  Sparkles,
   ShieldAlert,
} from 'lucide-react'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/topology', label: 'Topology', icon: Network },
  { to: '/simulation', label: 'Simulation', icon: PlayCircle },
  { to: '/prompt', label: 'Prompt Assistant', icon: Sparkles },
  { to: '/drift', label: 'Drift', icon: GitCompareArrows },
  { to: '/anomaly', label: 'Anomaly Detection', icon: ShieldAlert },
]

const stackLinks = [
  { label: 'Prometheus', url: import.meta.env.VITE_PROMETHEUS_URL },
  { label: 'Grafana', url: import.meta.env.VITE_GRAFANA_URL },
  { label: 'InfluxDB', url: import.meta.env.VITE_INFLUXDB_URL },
]

export default function Sidebar() {
  return (
    <aside className="w-56 flex-shrink-0 bg-surface border-r border-border flex flex-col h-full">
      <div className="px-5 py-5 border-b border-border">
        <div className="text-sm font-bold text-white">Digital Twin</div>
        <div className="text-[11px] text-muted mt-0.5">Private Cloud Control Plane</div>
      </div>

      <nav className="flex-1 py-3 overflow-y-auto">
        {navItems.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-3 px-5 py-2.5 text-sm transition-colors border-l-2 ${
                isActive
                  ? 'text-accent border-accent bg-accent-dim'
                  : 'text-muted border-transparent hover:text-gray-200 hover:bg-surface2'
              }`
            }
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-4 border-t border-border">
        <p className="text-[10px] uppercase tracking-wider text-faint font-semibold mb-2">
          Observability Stack
        </p>
        <div className="flex flex-wrap gap-1.5">
          {stackLinks.map(({ label, url }) =>
            url ? (
              <a
                key={label}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[10px] px-2 py-1 rounded bg-surface3 text-muted hover:text-accent border border-border transition"
              >
                {label}
              </a>
            ) : null,
          )}
        </div>
      </div>
    </aside>
  )
}
