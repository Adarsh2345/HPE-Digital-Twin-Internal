import { useState, useEffect, useMemo, type ReactNode } from 'react'
import { Loader2 } from 'lucide-react'
import { PageHeader, Card, ErrorBanner } from '../components/ui'
import { getActions, runSimulation, type SimulationAction, type SimulationResult } from '../api/simulation'
import { useFetch } from '../hooks/usePolling'
import {
  formatActionLabel,
  formatNumber,
  riskFromSimulation,
  severityBadgeClass,
  shortNodeId,
} from '../utils/format'

const TELEMETRY_INTERVAL_SECONDS = 12

interface NodeMetrics {
  cpu_percent?: number
  memory_percent?: number
  power_watts?: number
  disk_iops?: number
  latency_ms?: number
  packet_loss_percent?: number
}

interface ScenarioModifiers {
  cpu: number
  memory: number
  power: number
  diskIops: number
  latency: number
  packetLoss: number
}

interface ScenarioAggregate {
  id: string
  label: string
  avgCpu: number
  avgMemory: number
  totalPower: number
  avgLatency: number
  avgPacketLoss: number
  totalDiskIops: number
  riskLevel: 'Low' | 'Medium' | 'High'
  riskScore: number
}

const WORKLOAD_SCENARIOS: { id: string; label: string; description: string; modifiers: ScenarioModifiers }[] = [
  {
    id: 'normal',
    label: 'Normal Operations',
    description: 'Projected post-change baseline',
    modifiers: { cpu: 1, memory: 1, power: 1, diskIops: 1, latency: 1, packetLoss: 1 },
  },
  {
    id: 'peak',
    label: 'Business Peak Hours',
    description: 'Heavier utilization during peak demand',
    modifiers: { cpu: 1.25, memory: 1.2, power: 1.15, diskIops: 1.1, latency: 1.5, packetLoss: 1.3 },
  },
  {
    id: 'batch',
    label: 'Night Batch Processing',
    description: 'Elevated storage throughput workloads',
    modifiers: { cpu: 1.1, memory: 1.05, power: 1.1, diskIops: 1.4, latency: 1.1, packetLoss: 1 },
  },
  {
    id: 'dr',
    label: 'Disaster Recovery Mode',
    description: 'Maximum stress failover conditions',
    modifiers: { cpu: 1.45, memory: 1.35, power: 1.25, diskIops: 1.2, latency: 1.8, packetLoss: 2.5 },
  },
]

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

  const scenarioAnalysis = useMemo(
    () => (result ? buildScenarioAnalysis(result) : null),
    [result],
  )

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

      {result && scenarioAnalysis && (
        <Card title="Scenario Impact Analysis" className="mt-4">
          <p className="text-xs text-muted mb-4">
            Projected workload behavior derived from simulation output (final projection step).
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
            {scenarioAnalysis.scenarios.map((scenario) => (
              <div
                key={scenario.id}
                className="px-3 py-3 rounded-lg bg-surface3 border border-border"
              >
                <p className="text-sm font-medium text-white">{scenario.label}</p>
                <p className="text-[11px] text-muted mt-0.5 mb-2">
                  {WORKLOAD_SCENARIOS.find((s) => s.id === scenario.id)?.description}
                </p>
                <span className={`badge ${severityBadgeClass(scenario.riskLevel)}`}>
                  {scenario.riskLevel} Risk
                </span>
                <div className="mt-2 text-[11px] text-gray-400 space-y-0.5">
                  <p>CPU {formatNumber(scenario.avgCpu, 1)}%</p>
                  <p>Power {formatNumber(scenario.totalPower, 0)} W</p>
                </div>
              </div>
            ))}
          </div>

          <div className="overflow-x-auto -mx-5 mb-6">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="table-head">Scenario</th>
                  <th className="table-head">Avg CPU</th>
                  <th className="table-head">Avg Memory</th>
                  <th className="table-head">Total Power</th>
                  <th className="table-head">Avg Latency</th>
                  <th className="table-head">Risk Level</th>
                </tr>
              </thead>
              <tbody>
                {scenarioAnalysis.scenarios.map((scenario) => (
                  <tr key={scenario.id} className="hover:bg-surface3/40 transition">
                    <td className="table-cell font-medium text-white">{scenario.label}</td>
                    <td className="table-cell text-gray-400">{formatNumber(scenario.avgCpu, 1)}%</td>
                    <td className="table-cell text-gray-400">{formatNumber(scenario.avgMemory, 1)}%</td>
                    <td className="table-cell text-gray-400">{formatNumber(scenario.totalPower, 0)} W</td>
                    <td className="table-cell text-gray-400">{formatNumber(scenario.avgLatency, 1)} ms</td>
                    <td className="table-cell">
                      <span className={`badge ${severityBadgeClass(scenario.riskLevel)}`}>
                        {scenario.riskLevel}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div className="px-4 py-3 rounded-lg bg-green-500/10 border border-green-500/20">
              <p className="text-xs text-muted mb-1">Best Case Scenario</p>
              <p className="text-sm font-semibold text-green-400">{scenarioAnalysis.bestCase.label}</p>
              <p className="text-xs text-gray-400 mt-1">
                {formatNumber(scenarioAnalysis.bestCase.avgCpu, 1)}% CPU ·{' '}
                {formatNumber(scenarioAnalysis.bestCase.avgLatency, 1)} ms latency ·{' '}
                {scenarioAnalysis.bestCase.riskLevel} risk
              </p>
            </div>
            <div className="px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/20">
              <p className="text-xs text-muted mb-1">Worst Case Scenario</p>
              <p className="text-sm font-semibold text-red-400">{scenarioAnalysis.worstCase.label}</p>
              <p className="text-xs text-gray-400 mt-1">
                {formatNumber(scenarioAnalysis.worstCase.avgCpu, 1)}% CPU ·{' '}
                {formatNumber(scenarioAnalysis.worstCase.avgLatency, 1)} ms latency ·{' '}
                {scenarioAnalysis.worstCase.riskLevel} risk
              </p>
            </div>
          </div>

          <div className="pt-4 border-t border-border">
            <p className="text-xs text-muted mb-2">Scenario Recommendation</p>
            <ul className="space-y-1.5 text-sm text-gray-300">
              {scenarioAnalysis.recommendations.map((rec, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-accent flex-shrink-0">→</span>
                  {rec}
                </li>
              ))}
            </ul>
          </div>
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

function extractBaselineNodeMetrics(result: SimulationResult): NodeMetrics[] {
  if (result.projections.length > 0) {
    const lastStep = result.projections[result.projections.length - 1]
    const nodes = lastStep.nodes as Record<string, NodeMetrics> | undefined
    if (nodes && Object.keys(nodes).length > 0) {
      return Object.values(nodes)
    }
  }

  const graph = result.projected_graph as
    | { nodes?: { metrics?: NodeMetrics }[] }
    | undefined
  if (graph?.nodes?.length) {
    return graph.nodes
      .map((n) => n.metrics ?? {})
      .filter((m) => typeof m.cpu_percent === 'number' || typeof m.power_watts === 'number')
  }

  return []
}

function aggregateScenarioMetrics(
  baseline: NodeMetrics[],
  modifiers: ScenarioModifiers,
): Omit<ScenarioAggregate, 'id' | 'label' | 'riskLevel' | 'riskScore'> {
  if (baseline.length === 0) {
    return {
      avgCpu: 0,
      avgMemory: 0,
      totalPower: 0,
      avgLatency: 0,
      avgPacketLoss: 0,
      totalDiskIops: 0,
    }
  }

  let cpuSum = 0
  let memSum = 0
  let powerSum = 0
  let latencySum = 0
  let packetSum = 0
  let iopsSum = 0
  let latencyCount = 0
  let packetCount = 0

  for (const node of baseline) {
    cpuSum += Math.min(100, (node.cpu_percent ?? 0) * modifiers.cpu)
    memSum += Math.min(100, (node.memory_percent ?? 0) * modifiers.memory)
    powerSum += (node.power_watts ?? 0) * modifiers.power
    iopsSum += (node.disk_iops ?? 0) * modifiers.diskIops
    if (node.latency_ms != null) {
      latencySum += node.latency_ms * modifiers.latency
      latencyCount++
    }
    if (node.packet_loss_percent != null) {
      packetSum += Math.min(100, node.packet_loss_percent * modifiers.packetLoss)
      packetCount++
    }
  }

  const count = baseline.length
  return {
    avgCpu: cpuSum / count,
    avgMemory: memSum / count,
    totalPower: powerSum,
    avgLatency: latencyCount > 0 ? latencySum / latencyCount : 0,
    avgPacketLoss: packetCount > 0 ? packetSum / packetCount : 0,
    totalDiskIops: iopsSum,
  }
}

function scoreScenarioRisk(
  metrics: Omit<ScenarioAggregate, 'id' | 'label' | 'riskLevel' | 'riskScore'>,
  simulationAllowed: boolean,
): { riskLevel: 'Low' | 'Medium' | 'High'; riskScore: number } {
  let score = 0
  if (metrics.avgCpu >= 85) score += 3
  else if (metrics.avgCpu >= 70) score += 2
  else if (metrics.avgCpu >= 55) score += 1

  if (metrics.avgMemory >= 90) score += 3
  else if (metrics.avgMemory >= 75) score += 2
  else if (metrics.avgMemory >= 60) score += 1

  if (metrics.avgLatency >= 100) score += 3
  else if (metrics.avgLatency >= 50) score += 2
  else if (metrics.avgLatency >= 25) score += 1

  if (metrics.avgPacketLoss >= 2) score += 2
  else if (metrics.avgPacketLoss >= 0.5) score += 1

  if (!simulationAllowed) score += 2

  const riskLevel: 'Low' | 'Medium' | 'High' =
    score >= 6 ? 'High' : score >= 3 ? 'Medium' : 'Low'

  return { riskLevel, riskScore: score }
}

function buildScenarioRecommendations(
  scenarios: ScenarioAggregate[],
  simulationAllowed: boolean,
): string[] {
  const byId = Object.fromEntries(scenarios.map((s) => [s.id, s]))
  const recs: string[] = []

  const peak = byId.peak
  const batch = byId.batch
  const dr = byId.dr
  const normal = byId.normal

  if (normal && normal.riskLevel === 'Low' && simulationAllowed) {
    recs.push('Change is stable under normal operating conditions.')
  }

  if (peak && peak.riskLevel === 'Low') {
    recs.push('Safe for Business Peak — projected headroom remains within acceptable limits.')
  } else if (peak && peak.riskLevel === 'Medium') {
    recs.push('Caution during Business Peak — monitor CPU and latency during high-traffic windows.')
  } else if (peak) {
    recs.push('Not recommended for Business Peak without capacity expansion or load balancing.')
  }

  if (batch && batch.riskLevel !== 'High') {
    recs.push('Suitable for Night Batch — disk throughput increase is within manageable bounds.')
  } else if (batch) {
    recs.push('Night Batch workloads may saturate storage IOPS — schedule during off-peak or add capacity.')
  }

  if (dr && dr.riskLevel === 'High') {
    recs.push('Requires capacity expansion before DR workloads — failover stress exceeds safe thresholds.')
  } else if (dr && dr.riskLevel === 'Medium') {
    recs.push('DR failover is feasible with active monitoring and a staged recovery plan.')
  } else if (dr) {
    recs.push('Disaster Recovery mode projected within safe operating envelope.')
  }

  if (!simulationAllowed) {
    recs.push('Address simulation constraint violations before applying this change to production.')
  }

  return recs.length > 0 ? recs : ['Review projected metrics across all workload scenarios before deployment.']
}

function buildScenarioAnalysis(result: SimulationResult) {
  const baseline = extractBaselineNodeMetrics(result)
  if (baseline.length === 0) return null

  const scenarios: ScenarioAggregate[] = WORKLOAD_SCENARIOS.map((scenario) => {
    const metrics = aggregateScenarioMetrics(baseline, scenario.modifiers)
    const { riskLevel, riskScore } = scoreScenarioRisk(metrics, result.allowed)
    return {
      id: scenario.id,
      label: scenario.label,
      ...metrics,
      riskLevel,
      riskScore,
    }
  })

  const sorted = [...scenarios].sort((a, b) => a.riskScore - b.riskScore)
  const bestCase = sorted[0]
  const worstCase = sorted[sorted.length - 1]

  return {
    scenarios,
    bestCase,
    worstCase,
    recommendations: buildScenarioRecommendations(scenarios, result.allowed),
  }
}
