import { useEffect, useState } from 'react'
import { Search, Bell } from 'lucide-react'
import { checkHealth } from '../api/client'

interface HeaderProps {
  search: string
  onSearchChange: (value: string) => void
}

export default function Header({ search, onSearchChange }: HeaderProps) {
  const [healthy, setHealthy] = useState(false)

  useEffect(() => {
    const poll = async () => setHealthy(await checkHealth())
    poll()
    const id = setInterval(poll, 8000)
    return () => clearInterval(id)
  }, [])

  return (
    <header className="h-14 flex-shrink-0 border-b border-border bg-surface flex items-center justify-between px-6">
      <div>
        <h1 className="text-sm font-semibold text-white">Infrastructure Command Center</h1>
        <p className="text-[11px] text-muted">Real-time monitoring & simulation platform</p>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted" />
          <input
            type="text"
            placeholder="Search nodes..."
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-9 pr-4 py-1.5 w-52 text-sm bg-surface2 border border-border rounded-lg text-gray-200 placeholder:text-faint focus:outline-none focus:border-accent/50"
          />
        </div>

        <button type="button" className="relative p-1.5 text-muted hover:text-gray-200 transition">
          <Bell className="w-4 h-4" />
          {!healthy && (
            <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-red-400" />
          )}
        </button>

        <div className="flex items-center gap-2.5 pl-2 border-l border-border">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-accent to-blue-500 flex items-center justify-center text-xs font-bold text-bg">
            C
          </div>
          <div className="text-xs">
           
            <div className="text-muted">Cloud Operator</div>
          </div>
        </div>
      </div>
    </header>
  )
}
