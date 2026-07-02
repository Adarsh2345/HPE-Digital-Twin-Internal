import { CheckCircle2, XCircle, AlertTriangle, Activity } from 'lucide-react'
import { PageHeader, LoadingSpinner, ErrorBanner } from '../components/ui'
import { usePolling } from '../hooks/usePolling'
import { getHealth, getValidate, getSummary } from '../api/reports'
import { stateBadgeClass } from '../utils/format'

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className="text-[10px] font-semibold uppercase tracking-widest text-muted mb-3">{children}</p>
}

function KvRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-border/50 last:border-0">
      <span className="text-xs text-muted">{label}</span>
      <span className="text-xs font-semibold text-white">{children}</span>
    </div>
  )
}

function IssueItem({ text, type }: { text: string; type: 'error' | 'warning' }) {
  return (
    <div className={`flex items-start gap-2 px-3 py-2 rounded-lg text-xs ${type === 'error' ? 'bg-red-500/8 border border-red-500/20 text-red-300' : 'bg-yellow-500/8 border border-yellow-500/20 text-yellow-300'}`}>
      {type === 'error'
        ? <XCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
        : <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />}
      <span>{text}</span>
    </div>
  )
}

export default function ReportsPage() {
  const health = usePolling(getHealth, 8000)
  const validate = usePolling(getValidate, 8000)
  const summary = usePolling(getSummary, 15000)

  const error = health.error ?? validate.error ?? summary.error

  const isHealthy = health.data?.overall_health === 'healthy'
  const isCompliant = validate.data?.allowed

  return (
    <div>
      <PageHeader
        title="Reports"
        subtitle="System health, constraint validation, and infrastructure summary"
      />

      {error && <ErrorBanner message={error} />}

      {/* ── Status strip ── */}
      {(health.data || validate.data) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
          <div className={`card p-4 flex items-center gap-4 border-l-2 ${isHealthy ? 'border-l-accent' : 'border-l-red-400'}`}>
            {isHealthy
              ? <CheckCircle2 className="w-5 h-5 text-accent shrink-0" />
              : <XCircle className="w-5 h-5 text-red-400 shrink-0" />}
            <div>
              <p className="text-xs text-muted">System health</p>
              <p className={`text-sm font-semibold capitalize ${isHealthy ? 'text-accent' : 'text-red-400'}`}>
                {health.data?.overall_health ?? '—'}
              </p>
            </div>
          </div>

          <div className={`card p-4 flex items-center gap-4 border-l-2 ${isCompliant ? 'border-l-accent' : 'border-l-red-400'}`}>
            {isCompliant
              ? <CheckCircle2 className="w-5 h-5 text-accent shrink-0" />
              : <XCircle className="w-5 h-5 text-red-400 shrink-0" />}
            <div>
              <p className="text-xs text-muted">Constraint validation</p>
              <p className={`text-sm font-semibold ${isCompliant ? 'text-accent' : 'text-red-400'}`}>
                {isCompliant ? 'Compliant' : `${validate.data?.reasons.length ?? 0} violations`}
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* ── Health report ── */}
        <div className="card p-5">
          <SectionLabel>Health report</SectionLabel>
          {health.loading ? (
            <LoadingSpinner />
          ) : health.data ? (
            <div className="space-y-0">
              <KvRow label="Overall health">
                <span className={`badge capitalize ${stateBadgeClass(health.data.overall_health)}`}>
                  {health.data.overall_health}
                </span>
              </KvRow>
              <KvRow label="Critical nodes">{health.data.critical_nodes.length}</KvRow>
              <KvRow label="Warning nodes">{health.data.warning_nodes.length}</KvRow>
              <KvRow label="Chaos injection">{health.data.chaos_active ? 'Active' : 'Inactive'}</KvRow>
              <KvRow label="Tick count">{health.data.tick_count}</KvRow>
              {Object.keys(health.data.state_counts ?? {}).length > 0 && (
                <div className="pt-3 mt-1">
                  <p className="text-[10px] uppercase tracking-widest text-muted mb-2">State distribution</p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(health.data.state_counts).map(([state, count]) => (
                      <div key={state} className={`px-2.5 py-1 rounded-full text-xs font-semibold ${stateBadgeClass(state)}`}>
                        {state} · {String(count)}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </div>

        {/* ── Validation report ── */}
        <div className="card p-5">
          <SectionLabel>Validation report</SectionLabel>
          {validate.loading ? (
            <LoadingSpinner />
          ) : validate.data ? (
            <div className="space-y-3">
              <KvRow label="Status">
                <span className={validate.data.allowed ? 'text-accent' : 'text-red-400'}>
                  {validate.data.allowed ? 'Passing' : 'Failing'}
                </span>
              </KvRow>
              <KvRow label="Violations">{validate.data.reasons.length}</KvRow>
              <KvRow label="Warnings">{validate.data.warnings.length}</KvRow>

              {validate.data.reasons.length > 0 && (
                <div className="pt-1 space-y-1.5">
                  <p className="text-[10px] uppercase tracking-widest text-muted">Violations</p>
                  {validate.data.reasons.map((r, i) => (
                    <IssueItem key={i} text={r} type="error" />
                  ))}
                </div>
              )}
              {validate.data.warnings.length > 0 && (
                <div className="pt-1 space-y-1.5">
                  <p className="text-[10px] uppercase tracking-widest text-muted">Warnings</p>
                  {validate.data.warnings.map((w, i) => (
                    <IssueItem key={i} text={w} type="warning" />
                  ))}
                </div>
              )}
            </div>
          ) : null}
        </div>

        {/* ── Summary ── */}
        <div className="card p-5 lg:col-span-2">
          <div className="flex items-center gap-2 mb-4">
            <Activity className="w-4 h-4 text-accent" />
            <p className="text-sm font-semibold text-white">Infrastructure summary</p>
            {summary.data?.timestamp && (
              <span className="text-xs text-muted ml-auto">
                {new Date(summary.data.timestamp).toLocaleTimeString()}
              </span>
            )}
          </div>
          {summary.loading ? (
            <LoadingSpinner />
          ) : summary.data ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {[
                { label: 'Status', value: String(summary.data.status ?? '—') },
                { label: 'Allowed', value: summary.data.validation?.allowed ? 'Yes' : 'No' },
                { label: 'Violations', value: String(summary.data.validation?.reasons?.length ?? 0) },
                { label: 'Graph nodes', value: String((summary.data.graph as { nodes?: unknown[] })?.nodes?.length ?? '—') },
              ].map(({ label, value }) => (
                <div key={label} className="px-4 py-3 rounded-lg bg-surface3 border border-border">
                  <p className="text-[10px] text-muted uppercase tracking-wider mb-1">{label}</p>
                  <p className="text-lg font-bold text-white">{value}</p>
                </div>
              ))}
            </div>
          ) : null}
        </div>

      </div>
    </div>
  )
}
