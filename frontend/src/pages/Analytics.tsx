import { useState, useEffect } from 'react'
import { Activity, ChevronRight, BarChart2 } from 'lucide-react'
import { PageHeader, LoadingSpinner, ErrorBanner } from '../components/ui'
import { useFetch } from '../hooks/usePolling'
import { getProfiles, getScenarios, getCorrelations } from '../api/analytics'
import { shortNodeId } from '../utils/format'

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-semibold uppercase tracking-widest text-muted mb-3">{children}</p>
  )
}

function CorrelationBar({ label, value }: { label: string; value: number }) {
  const abs = Math.abs(value)
  const isPos = value >= 0
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-muted w-28 shrink-0 truncate">{label}</span>
      <div className="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${isPos ? 'bg-accent' : 'bg-red-400'}`}
          style={{ width: `${abs * 100}%` }}
        />
      </div>
      <span className={`text-xs font-mono font-semibold w-12 text-right ${abs > 0.7 ? (isPos ? 'text-accent' : 'text-red-400') : 'text-gray-400'}`}>
        {value.toFixed(3)}
      </span>
    </div>
  )
}

function ScenarioPill({ s }: { s: Record<string, unknown> }) {
  const metrics = Object.entries(s).filter(([k]) => k !== 'name' && k !== 'label' && k !== 'scenario_id')
  return (
    <div className="rounded-lg bg-surface3 border border-border px-4 py-3 space-y-2">
      <p className="text-xs font-semibold text-white">
        {String(s.label ?? s.name ?? 'Scenario')}
      </p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {metrics.slice(0, 6).map(([k, v]) => (
          <div key={k} className="flex justify-between">
            <span className="text-[11px] text-muted truncate">{k.replace(/_/g, ' ')}</span>
            <span className="text-[11px] text-gray-300 font-mono ml-2 shrink-0">
              {typeof v === 'number' ? v.toFixed(1) : String(v)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function AnalyticsPage() {
  const profiles = useFetch(getProfiles, [])
  const scenarios = useFetch(getScenarios, [])
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [correlations, setCorrelations] = useState<Record<string, unknown> | null>(null)
  const [corrLoading, setCorrLoading] = useState(false)
  const [corrError, setCorrError] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedNode) { setCorrelations(null); return }
    setCorrLoading(true)
    getCorrelations(selectedNode)
      .then((r) => { setCorrelations(r.correlations); setCorrError(null) })
      .catch((e) => setCorrError(e instanceof Error ? e.message : 'Failed'))
      .finally(() => setCorrLoading(false))
  }, [selectedNode])

  const nodeIds = profiles.data ? Object.keys(profiles.data.node_profiles) : []
  const error = profiles.error ?? scenarios.error

  // Extract correlation pairs as sorted flat list
  const corrPairs = correlations
    ? Object.entries(correlations as Record<string, Record<string, number>>)
        .flatMap(([metricA, targets]) =>
          Object.entries(targets).map(([metricB, v]) => ({
            label: `${metricA.replace(/_/g, ' ')} → ${metricB.replace(/_/g, ' ')}`,
            value: v,
          }))
        )
        .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
        .slice(0, 12)
    : []

  return (
    <div>
      <PageHeader
        title="Analytics"
        subtitle="Node behavior profiles, workload scenarios, and metric correlations"
      />

      {error && <ErrorBanner message={error} />}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* ── Node profiles list ── */}
        <div className="card p-5 flex flex-col">
          <div className="flex items-center justify-between mb-1">
            <SectionLabel>Node profiles</SectionLabel>
            {profiles.data && (
              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${profiles.data.ready ? 'bg-accent/15 text-accent' : 'bg-yellow-500/15 text-yellow-400'}`}>
                {profiles.data.ready ? 'Ready' : 'Training'}
              </span>
            )}
          </div>
          {profiles.loading ? (
            <LoadingSpinner />
          ) : nodeIds.length === 0 ? (
            <p className="text-sm text-muted">No profiles available</p>
          ) : (
            <div className="space-y-1 overflow-y-auto max-h-72 pr-1">
              {nodeIds.map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setSelectedNode(selectedNode === id ? null : id)}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition ${
                    selectedNode === id
                      ? 'bg-accent/10 text-accent border border-accent/25'
                      : 'text-gray-300 hover:bg-surface3 border border-transparent'
                  }`}
                >
                  <span className="font-mono text-xs">{shortNodeId(id)}</span>
                  <ChevronRight className={`w-3.5 h-3.5 transition-transform ${selectedNode === id ? 'rotate-90 text-accent' : 'text-muted'}`} />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* ── Workload scenarios ── */}
        <div className="card p-5 lg:col-span-2">
          <SectionLabel>Workload scenarios</SectionLabel>
          {scenarios.data && (
            <div className="flex items-center gap-3 mb-3">
              <span className="text-xs text-muted">Source: <span className="text-white">{scenarios.data.source}</span></span>
              <span className="text-xs text-muted">Clusters: <span className="text-accent font-semibold">k={scenarios.data.best_k}</span></span>
            </div>
          )}
          {scenarios.loading ? (
            <LoadingSpinner />
          ) : !scenarios.data?.scenarios.length ? (
            <p className="text-sm text-muted">No scenarios available</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 overflow-y-auto max-h-72 pr-1">
              {scenarios.data.scenarios.map((s, i) => (
                <ScenarioPill key={i} s={s as Record<string, unknown>} />
              ))}
            </div>
          )}
        </div>

        {/* ── Correlation panel ── */}
        {selectedNode && (
          <div className="card p-5 lg:col-span-3">
            <div className="flex items-center gap-2 mb-4">
              <BarChart2 className="w-4 h-4 text-accent" />
              <p className="text-sm font-semibold text-white">
                Metric correlations — <span className="text-accent font-mono">{shortNodeId(selectedNode)}</span>
              </p>
            </div>
            {corrLoading ? (
              <LoadingSpinner />
            ) : corrError ? (
              <ErrorBanner message={corrError} />
            ) : corrPairs.length === 0 ? (
              <p className="text-sm text-muted">No correlation data available for this node.</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-2.5">
                {corrPairs.map(({ label, value }) => (
                  <CorrelationBar key={label} label={label} value={value} />
                ))}
              </div>
            )}
            {correlations && corrPairs.length === 0 && (
              <div className="mt-4 flex items-center gap-2 text-muted">
                <Activity className="w-4 h-4" />
                <p className="text-xs">Correlation structure not in expected format for this node.</p>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  )
}
