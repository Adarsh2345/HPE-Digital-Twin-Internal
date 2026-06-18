import type { ReactNode } from 'react'
import { PageHeader, Card, LoadingSpinner, ErrorBanner } from '../components/ui'
import { usePolling } from '../hooks/usePolling'
import { getHealth, getValidate, getSummary } from '../api/reports'
import { stateBadgeClass } from '../utils/format'

export default function ReportsPage() {
  const health = usePolling(getHealth, 8000)
  const validate = usePolling(getValidate, 8000)
  const summary = usePolling(getSummary, 15000)

  const error = health.error ?? validate.error ?? summary.error

  return (
    <div>
      <PageHeader
        title="Reports Dashboard"
        subtitle="System health, validation, and infrastructure summary"
      />

      {error && <ErrorBanner message={error} />}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Health Report">
          {health.loading ? (
            <LoadingSpinner />
          ) : health.data ? (
            <dl className="space-y-2 text-sm">
              <Row label="Overall Health">
                <span className={`badge capitalize ${stateBadgeClass(health.data.overall_health)}`}>
                  {health.data.overall_health}
                </span>
              </Row>
              <Row label="Critical Nodes">{health.data.critical_nodes.length}</Row>
              <Row label="Warning Nodes">{health.data.warning_nodes.length}</Row>
              <Row label="Chaos Active">{health.data.chaos_active ? 'Yes' : 'No'}</Row>
              <Row label="Tick Count">{health.data.tick_count}</Row>
              <Row label="State Counts">
                <pre className="text-xs font-mono text-muted">
                  {JSON.stringify(health.data.state_counts, null, 2)}
                </pre>
              </Row>
            </dl>
          ) : null}
        </Card>

        <Card title="Validation Report">
          {validate.loading ? (
            <LoadingSpinner />
          ) : validate.data ? (
            <dl className="space-y-2 text-sm">
              <Row label="Allowed">{validate.data.allowed ? 'Yes' : 'No'}</Row>
              <Row label="Violations">{validate.data.reasons.length}</Row>
              <Row label="Warnings">{validate.data.warnings.length}</Row>
              {validate.data.reasons.map((r, i) => (
                <div key={i} className="text-xs text-red-300 font-mono">
                  {r}
                </div>
              ))}
              {validate.data.warnings.map((w, i) => (
                <div key={i} className="text-xs text-yellow-300 font-mono">
                  {w}
                </div>
              ))}
            </dl>
          ) : null}
        </Card>

        <Card title="Full Summary" className="lg:col-span-2">
          {summary.loading ? (
            <LoadingSpinner />
          ) : summary.data ? (
            <pre className="text-xs font-mono text-gray-400 overflow-x-auto max-h-96">
              {JSON.stringify(
                {
                  timestamp: summary.data.timestamp,
                  status: summary.data.status,
                  validation: {
                    allowed: summary.data.validation.allowed,
                    reasons: summary.data.validation.reasons,
                    warnings: summary.data.validation.warnings,
                  },
                  graph_nodes: (summary.data.graph as { nodes?: unknown[] })?.nodes?.length,
                },
                null,
                2,
              )}
            </pre>
          ) : null}
        </Card>
      </div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between items-start gap-4">
      <dt className="text-muted">{label}</dt>
      <dd className="text-gray-300 text-right">{children}</dd>
    </div>
  )
}
