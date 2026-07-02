import { useMemo } from 'react'
import { ShieldCheck, ShieldAlert, Clock } from 'lucide-react'
import { PageHeader, LoadingSpinner, ErrorBanner, EmptyState } from '../components/ui'
import { usePolling } from '../hooks/usePolling'
import { getValidate } from '../api/reports'
import { buildDriftRows, severityBadgeClass } from '../utils/format'

export default function DriftPage() {
  const { data, loading, error } = usePolling(getValidate, 8000)
  const rows = useMemo(() => (data ? buildDriftRows(data) : []), [data])

  const criticalCount = rows.filter((r) => r.severity?.toLowerCase() === 'critical').length
  const warningCount = rows.filter((r) => r.severity?.toLowerCase() !== 'critical').length

  return (
    <div>
      <PageHeader
        title="Drift Detection"
        subtitle="Infrastructure consistency and constraint validation"
      />

      {error && <ErrorBanner message={error} />}

      {data && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
          {/* Status */}
          <div className={`card p-5 flex items-center gap-4 border-l-2 ${data.allowed ? 'border-l-accent' : 'border-l-red-400'}`}>
            {data.allowed
              ? <ShieldCheck className="w-6 h-6 text-accent shrink-0" />
              : <ShieldAlert className="w-6 h-6 text-red-400 shrink-0" />}
            <div>
              <p className="text-xs text-muted mb-0.5">Validation status</p>
              <p className={`text-sm font-semibold ${data.allowed ? 'text-accent' : 'text-red-400'}`}>
                {data.allowed ? 'Compliant' : 'Violations detected'}
              </p>
              <div className="flex items-center gap-1 mt-1">
                <Clock className="w-2.5 h-2.5 text-muted" />
                <span className="text-[10px] text-muted">{new Date(data.timestamp).toLocaleTimeString()}</span>
              </div>
            </div>
          </div>

          {/* Violations */}
          <div className="card p-5">
            <p className="text-[10px] uppercase tracking-widest text-muted mb-2">Critical violations</p>
            <p className={`text-3xl font-bold ${data.reasons.length > 0 ? 'text-red-400' : 'text-white'}`}>
              {data.reasons.length}
            </p>
            <p className="text-xs text-muted mt-1">Constraint failures</p>
          </div>

          {/* Warnings */}
          <div className="card p-5">
            <p className="text-[10px] uppercase tracking-widest text-muted mb-2">Warnings</p>
            <p className={`text-3xl font-bold ${data.warnings.length > 0 ? 'text-yellow-400' : 'text-white'}`}>
              {data.warnings.length}
            </p>
            <p className="text-xs text-muted mt-1">Non-blocking issues</p>
          </div>
        </div>
      )}

      {/* Summary chips when there are findings */}
      {rows.length > 0 && (
        <div className="flex items-center gap-2 mb-4">
          {criticalCount > 0 && (
            <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-red-500/15 text-red-400 border border-red-500/20">
              {criticalCount} critical
            </span>
          )}
          {warningCount > 0 && (
            <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-yellow-500/15 text-yellow-400 border border-yellow-500/20">
              {warningCount} warning{warningCount > 1 ? 's' : ''}
            </span>
          )}
        </div>
      )}

      <div className="card">
        <div className="px-5 pt-5 pb-4">
          <p className="text-sm font-semibold text-white">Drift detection results</p>
          <p className="text-xs text-muted mt-0.5">Infrastructure inconsistencies and schema violations</p>
        </div>

        {loading ? (
          <div className="px-5 pb-5"><LoadingSpinner /></div>
        ) : rows.length === 0 ? (
          <div className="px-5 pb-5">
            <EmptyState
              title="No drift detected"
              description={
                data?.allowed
                  ? 'Live infrastructure state passes all constraint validations.'
                  : 'No violations returned from validation endpoint.'
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-t border-border">
                  <th className="table-head">System</th>
                  <th className="table-head">Issue</th>
                  <th className="table-head">Severity</th>
                  <th className="table-head">Recommendation</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i} className="hover:bg-surface3/40 transition">
                    <td className="table-cell font-mono text-xs text-white">{row.system}</td>
                    <td className="table-cell text-xs text-gray-400 max-w-xs">{row.issue}</td>
                    <td className="table-cell">
                      <span className={`badge ${severityBadgeClass(row.severity)}`}>{row.severity}</span>
                    </td>
                    <td className="table-cell text-xs text-gray-400 max-w-sm">{row.recommendation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
