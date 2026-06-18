import { useMemo } from 'react'
import { PageHeader, Card, LoadingSpinner, ErrorBanner, EmptyState } from '../components/ui'
import { usePolling } from '../hooks/usePolling'
import { getValidate } from '../api/reports'
import { buildDriftRows, severityBadgeClass, stateBadgeClass } from '../utils/format'

export default function DriftPage() {
  const { data, loading, error } = usePolling(getValidate, 8000)
  const rows = useMemo(() => (data ? buildDriftRows(data) : []), [data])

  return (
    <div>
      <PageHeader
        title="Drift Detection"
        subtitle="Infrastructure consistency and schema validation"
      />

      {error && <ErrorBanner message={error} />}

      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
          <Card title="Validation Status">
            <div className="flex items-center gap-2">
              <span className={`badge capitalize ${stateBadgeClass(data.allowed ? 'healthy' : 'critical')}`}>
                {data.allowed ? 'Compliant' : 'Violations'}
              </span>
              <span className="text-xs text-muted">
                Updated {new Date(data.timestamp).toLocaleTimeString()}
              </span>
            </div>
          </Card>
          <Card title="Violations">
            <p className="text-2xl font-bold text-white">{data.reasons.length}</p>
            <p className="text-xs text-muted">Critical constraint failures</p>
          </Card>
          <Card title="Warnings">
            <p className="text-2xl font-bold text-white">{data.warnings.length}</p>
            <p className="text-xs text-muted">Non-blocking issues</p>
          </Card>
        </div>
      )}

      <Card title="Drift Detection Results" subtitle="Infrastructure inconsistencies detected">
        {loading ? (
          <LoadingSpinner />
        ) : rows.length === 0 ? (
          <EmptyState
            title="No drift detected"
            description={
              data?.allowed
                ? 'Live infrastructure state passes all constraint validations.'
                : 'No violations returned from validation endpoint.'
            }
          />
        ) : (
          <div className="overflow-x-auto -mx-5">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="table-head">System</th>
                  <th className="table-head">Issue</th>
                  <th className="table-head">Severity</th>
                  <th className="table-head">Recommendation</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i} className="hover:bg-surface3/40 transition">
                    <td className="table-cell font-medium text-white">{row.system}</td>
                    <td className="table-cell text-gray-400">{row.issue}</td>
                    <td className="table-cell">
                      <span className={`badge ${severityBadgeClass(row.severity)}`}>
                        {row.severity}
                      </span>
                    </td>
                    <td className="table-cell text-gray-400">{row.recommendation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
