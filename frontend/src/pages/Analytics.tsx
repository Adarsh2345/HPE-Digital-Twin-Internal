import { useState, useEffect } from 'react'
import { PageHeader, Card, LoadingSpinner, ErrorBanner } from '../components/ui'
import { useFetch } from '../hooks/usePolling'
import { getProfiles, getScenarios, getCorrelations } from '../api/analytics'
import { shortNodeId } from '../utils/format'

export default function AnalyticsPage() {
  const profiles = useFetch(getProfiles, [])
  const scenarios = useFetch(getScenarios, [])
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [correlations, setCorrelations] = useState<Record<string, unknown> | null>(null)
  const [corrLoading, setCorrLoading] = useState(false)
  const [corrError, setCorrError] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedNode) {
      setCorrelations(null)
      return
    }
    setCorrLoading(true)
    getCorrelations(selectedNode)
      .then((r) => {
        setCorrelations(r.correlations)
        setCorrError(null)
      })
      .catch((e) => setCorrError(e instanceof Error ? e.message : 'Failed'))
      .finally(() => setCorrLoading(false))
  }, [selectedNode])

  const nodeIds = profiles.data ? Object.keys(profiles.data.node_profiles) : []
  const error = profiles.error ?? scenarios.error

  return (
    <div>
      <PageHeader
        title="Analytics Dashboard"
        subtitle="Node profiles, workload scenarios, and metric correlations"
      />

      {error && <ErrorBanner message={error} />}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Node Profiles" subtitle={profiles.data ? `Ready: ${profiles.data.ready}` : undefined}>
          {profiles.loading ? (
            <LoadingSpinner />
          ) : nodeIds.length === 0 ? (
            <p className="text-sm text-muted">No profiles available from backend</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {nodeIds.map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setSelectedNode(id)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition ${
                    selectedNode === id
                      ? 'bg-accent-dim text-accent border border-accent/30'
                      : 'bg-surface3 text-gray-300 hover:bg-surface2 border border-transparent'
                  }`}
                >
                  {shortNodeId(id)}
                </button>
              ))}
            </div>
          )}
        </Card>

        <Card
          title="Workload Scenarios"
          subtitle={scenarios.data ? `Source: ${scenarios.data.source}, k=${scenarios.data.best_k}` : undefined}
        >
          {scenarios.loading ? (
            <LoadingSpinner />
          ) : !scenarios.data?.scenarios.length ? (
            <p className="text-sm text-muted">No scenarios from backend</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {scenarios.data.scenarios.map((s, i) => (
                <div key={i} className="px-3 py-2 rounded-lg bg-surface3 text-xs font-mono text-gray-400">
                  {JSON.stringify(s).slice(0, 200)}
                </div>
              ))}
            </div>
          )}
        </Card>

        {selectedNode && (
          <Card title={`Correlations — ${shortNodeId(selectedNode)}`} className="lg:col-span-2">
            {corrLoading ? (
              <LoadingSpinner />
            ) : corrError ? (
              <ErrorBanner message={corrError} />
            ) : (
              <pre className="text-xs font-mono text-gray-400 overflow-x-auto">
                {JSON.stringify(correlations ?? {}, null, 2)}
              </pre>
            )}
          </Card>
        )}
      </div>
    </div>
  )
}
