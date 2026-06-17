import { useState, useEffect, type ReactNode } from 'react'
import { Loader2 } from 'lucide-react'
import { PageHeader, Card, ErrorBanner } from '../components/ui'
import { getActions, runSimulation, type SimulationAction, type SimulationResult } from '../api/simulation'
import { useFetch } from '../hooks/usePolling'
import {
  formatActionLabel,
  riskFromSimulation,
  severityBadgeClass,
  shortNodeId,
} from '../utils/format'

const TELEMETRY_INTERVAL_SECONDS = 12

export default function SimulationPage() {
  const { data: actionsData, loading: actionsLoading, error: actionsError } = useFetch(getActions, [])
  const [selectedAction, setSelectedAction] = useState<SimulationAction | null>(null)
  const [params, setParams] = useState<Record<string, string>>({})
  const [projectionSteps, setProjectionSteps] = useState(3)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<SimulationResult | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  useEffect(() => {
    if (actionsData?.actions.length && !selectedAction) {
      const first = actionsData.actions[0]
      setSelectedAction(first)
      const defaults: Record<string, string> = {}
      for (const [key, val] of Object.entries(first.example)) {
        defaults[key] = String(val)
      }
      setParams(defaults)
    }
  }, [actionsData, selectedAction])

  const handleActionChange = (actionName: string) => {
    const action = actionsData?.actions.find((a) => a.action === actionName)
    if (!action) return
    setSelectedAction(action)
    const defaults: Record<string, string> = {}
    for (const [key, val] of Object.entries(action.example)) {
      defaults[key] = String(val)
    }
    setParams(defaults)
    setResult(null)
  }

  const handleRun = async () => {
    if (!selectedAction) return
    setRunning(true)
    setRunError(null)
    setResult(null)
    try {
      const parsedParams: Record<string, unknown> = {}
      for (const [key, val] of Object.entries(params)) {
        const num = Number(val)
        parsedParams[key] = !isNaN(num) && val.trim() !== '' ? num : val
      }
      const res = await runSimulation({
        action: selectedAction.action,
        params: parsedParams,
        projection_steps: projectionSteps,
      })
      setResult(res)
    } catch (e) {
      setRunError(e instanceof Error ? e.message : 'Simulation failed')
    } finally {
      setRunning(false)
    }
  }

  const affectedServices = getAffectedServices(result)
  const blastRadius = affectedServices.length || getBlastRadiusCount(result)
  const downtimeMinutes =
    result?.projections?.length
      ? Math.ceil((result.projections.length * TELEMETRY_INTERVAL_SECONDS) / 60)
      : null

  return (
    <div>
      <PageHeader
        title="Infrastructure Simulation"
        subtitle="What-if analysis with constraint validation"
      />

      {actionsError && <ErrorBanner message={actionsError} />}

      <div className="card p-5 mb-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-muted mb-1.5">Simulation Action</label>
            <select
              value={selectedAction?.action ?? ''}
              onChange={(e) => handleActionChange(e.target.value)}
              disabled={actionsLoading}
              className="w-full bg-surface3 border border-border rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-accent/50"
            >
              {actionsData?.actions.map((a) => (
                <option key={a.action} value={a.action}>
                  [{a.category}] {a.action}
                </option>
              ))}
            </select>
            {selectedAction && (
              <p className="text-xs text-muted mt-1.5">{selectedAction.description}</p>
            )}
          </div>

          <div>
            <label className="block text-xs text-muted mb-1.5">Projection Steps</label>
            <input
              type="number"
              min={1}
              max={10}
              value={projectionSteps}
              onChange={(e) => setProjectionSteps(Number(e.target.value))}
              className="w-full bg-surface3 border border-border rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-accent/50"
            />
          </div>
        </div>

        {selectedAction && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Object.keys(selectedAction.params).map((key) => (
              <div key={key}>
                <label className="block text-xs text-muted mb-1">{key}</label>
                <input
                  value={params[key] ?? ''}
                  onChange={(e) => setParams((p) => ({ ...p, [key]: e.target.value }))}
                  className="w-full bg-surface3 border border-border rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-accent/50"
                />
              </div>
            ))}
          </div>
        )}

        <button
          type="button"
          onClick={handleRun}
          disabled={running || !selectedAction}
          className="btn-primary"
        >
          {running ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Running...
            </>
          ) : (
            'Run Simulation'
          )}
        </button>
      </div>

      {runError && <ErrorBanner message={runError} />}

      {result && (
        <Card title="Simulation Result">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4">
            <ResultField
              label="Change"
              value={formatActionLabel(result.action, result.params)}
            />
            <ResultField
              label="Risk Level"
              value={
                <span className={`badge ${severityBadgeClass(riskFromSimulation(result.allowed, result.reasons, result.warnings))}`}>
                  {riskFromSimulation(result.allowed, result.reasons, result.warnings)}
                </span>
              }
            />
            <ResultField
              label="Estimated Downtime"
              value={downtimeMinutes != null ? `${downtimeMinutes} minutes` : '—'}
            />
            <ResultField label="Blast Radius" value={`${blastRadius} services`} />
            <ResultField
              label="Verdict"
              value={result.verdict}
            />
            <ResultField
              label="Recommendation"
              value={result.recommendations[0] ?? result.warnings[0] ?? (result.allowed ? 'No action required' : 'Review violations')}
            />
          </div>

          {affectedServices.length > 0 && (
            <div>
              <p className="text-xs text-muted mb-2">Affected Services</p>
              <div className="flex flex-wrap gap-2">
                {affectedServices.map((s) => (
                  <span
                    key={s}
                    className="text-xs px-2.5 py-1 rounded-full bg-red-500/15 text-red-300 border border-red-500/20"
                  >
                    {shortNodeId(s)}
                  </span>
                ))}
              </div>
            </div>
          )}

          {result.projections.length > 0 && (
            <div className="mt-4">
              <p className="text-xs text-muted mb-2">Projections ({result.projections.length} steps)</p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr>
                      <th className="table-head">Step</th>
                      <th className="table-head">Data</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.projections.map((p, i) => (
                      <tr key={i}>
                        <td className="table-cell">{i + 1}</td>
                        <td className="table-cell font-mono text-muted">
                          {JSON.stringify(p).slice(0, 120)}...
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {Object.keys(result.tier_results).length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {Object.entries(result.tier_results).map(([tier, tr]) => (
                <span
                  key={tier}
                  className={`badge ${tr.passed === false ? 'bg-red-500/15 text-red-400' : 'bg-green-500/15 text-green-400'}`}
                >
                  {tier}: {tr.passed === false ? 'FAIL' : 'PASS'}
                </span>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  )
}

function ResultField({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <p className="text-xs text-muted mb-0.5">{label}</p>
      <div className="text-sm text-white font-medium">{value}</div>
    </div>
  )
}

function getAffectedServices(result: SimulationResult | null): string[] {
  if (!result) return []
  const services = new Set<string>()

  for (const sr of result.scenario_results) {
    if (sr.passed === false) {
      const id = sr.scenario ?? sr.node_id
      if (typeof id === 'string') services.add(id)
    }
  }

  const impact = result.impact_predictions
  if (impact.nodes_affected && Array.isArray(impact.nodes_affected)) {
    for (const n of impact.nodes_affected) {
      if (typeof n === 'string') services.add(n)
    }
  }

  for (const key of Object.keys(impact)) {
    if (key.includes('/') || key.includes('server') || key.includes('prometheus') || key.includes('grafana')) {
      services.add(key)
    }
  }

  return [...services]
}

function getBlastRadiusCount(result: SimulationResult | null): number {
  if (!result) return 0
  const impact = result.impact_predictions
  if (typeof impact.nodes_affected === 'number') return impact.nodes_affected
  if (Array.isArray(impact.nodes_affected)) return impact.nodes_affected.length
  return result.scenario_results.filter((s) => s.passed === false).length
}
