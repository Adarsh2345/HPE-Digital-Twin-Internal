import { useState, useEffect, useMemo, type ReactNode } from 'react'
import { Loader2, Play, ChevronDown, CheckCircle2, XCircle, ArrowRight } from 'lucide-react'
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
  cpu: number; memory: number; power: number
  diskIops: number; latency: number; packetLoss: number
}

interface ScenarioAggregate {
  id: string; label: string
  avgCpu: number; avgMemory: number; totalPower: number
  avgLatency: number; avgPacketLoss: number; totalDiskIops: number
  riskLevel: 'Low' | 'Medium' | 'High'; riskScore: number
}

const WORKLOAD_SCENARIOS: { id: string; label: string; description: string; modifiers: ScenarioModifiers }[] = [
  { id: 'normal', label: 'Normal Operations', description: 'Projected post-change baseline', modifiers: { cpu: 1, memory: 1, power: 1, diskIops: 1, latency: 1, packetLoss: 1 } },
  { id: 'peak', label: 'Business Peak Hours', description: 'Heavier utilization during peak demand', modifiers: { cpu: 1.25, memory: 1.2, power: 1.15, diskIops: 1.1, latency: 1.5, packetLoss: 1.3 } },
  { id: 'batch', label: 'Night Batch Processing', description: 'Elevated storage throughput workloads', modifiers: { cpu: 1.1, memory: 1.05, power: 1.1, diskIops: 1.4, latency: 1.1, packetLoss: 1 } },
  { id: 'dr', label: 'Disaster Recovery Mode', description: 'Maximum stress failover conditions', modifiers: { cpu: 1.45, memory: 1.35, power: 1.25, diskIops: 1.2, latency: 1.8, packetLoss: 2.5 } },
]

function SectionLabel({ children }: { children: ReactNode }) {
  return <p className="text-[10px] font-semibold uppercase tracking-widest text-muted mb-3">{children}</p>
}

function MetricPill({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <div className="px-4 py-3 rounded-lg bg-surface3 border border-border">
      <p className="text-[10px] text-muted uppercase tracking-wider mb-1">{label}</p>
      <div className="text-sm font-semibold text-white">{value}</div>
      {sub && <p className="text-[11px] text-muted mt-0.5">{sub}</p>}
    </div>
  )
}

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
      for (const [key, val] of Object.entries(first.example)) defaults[key] = String(val)
      setParams(defaults)
    }
  }, [actionsData, selectedAction])

  const handleActionChange = (actionName: string) => {
    const action = actionsData?.actions.find((a) => a.action === actionName)
    if (!action) return
    setSelectedAction(action)
    const defaults: Record<string, string> = {}
    for (const [key, val] of Object.entries(action.example)) defaults[key] = String(val)
    setParams(defaults)
    setResult(null)
  }

  const handleRun = async () => {
    if (!selectedAction) return
    setRunning(true); setRunError(null); setResult(null)
    try {
      const parsedParams: Record<string, unknown> = {}
      for (const [key, val] of Object.entries(params)) {
        const num = Number(val)
        parsedParams[key] = !isNaN(num) && val.trim() !== '' ? num : val
      }
      const res = await runSimulation({ action: selectedAction.action, params: parsedParams, projection_steps: projectionSteps })
      setResult(res)
    } catch (e) {
      setRunError(e instanceof Error ? e.message : 'Simulation failed')
    } finally {
      setRunning(false)
    }
  }

  const affectedServices = getAffectedServices(result)
  const blastRadius = affectedServices.length || getBlastRadiusCount(result)
  const downtimeMinutes = result?.projections?.length
    ? Math.ceil((result.projections.length * TELEMETRY_INTERVAL_SECONDS) / 60)
    : null
  const risk = result ? riskFromSimulation(result.allowed, result.reasons, result.warnings) : null
  const scenarioAnalysis = useMemo(() => (result ? buildScenarioAnalysis(result) : null), [result])

  return (
    <div>
      <PageHeader title="Simulation" subtitle="What-if analysis with multi-tier constraint validation" />

      {actionsError && <ErrorBanner message={actionsError} />}

      {/* ── Config panel ── */}
      <div className="card p-5 mb-4">
        <SectionLabel>Configure simulation</SectionLabel>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-xs text-muted mb-1.5">Action</label>
            <div className="relative">
              <select
                value={selectedAction?.action ?? ''}
                onChange={(e) => handleActionChange(e.target.value)}
                disabled={actionsLoading}
                className="w-full appearance-none bg-surface3 border border-border rounded-lg px-3 py-2 pr-8 text-sm text-gray-200 focus:outline-none focus:border-accent/50"
              >
                {actionsData?.actions.map((a) => (
                  <option key={a.action} value={a.action}>{a.action.replace(/_/g, ' ')}</option>
                ))}
              </select>
              <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted pointer-events-none" />
            </div>
            {selectedAction && (
              <p className="text-xs text-muted mt-1.5 leading-relaxed">{selectedAction.description}</p>
            )}
          </div>

          <div>
            <label className="block text-xs text-muted mb-1.5">Projection steps</label>
            <input
              type="number" min={1} max={10} value={projectionSteps}
              onChange={(e) => setProjectionSteps(Number(e.target.value))}
              className="w-full bg-surface3 border border-border rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-accent/50"
            />
            <p className="text-xs text-muted mt-1.5">Number of future time steps to project</p>
          </div>
        </div>

        {selectedAction && Object.keys(selectedAction.params).length > 0 && (
          <div className="mb-4">
            <label className="block text-xs text-muted mb-2">Parameters</label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {Object.entries(selectedAction.params).map(([key, hint]) => (
                <div key={key}>
                  <label className="block text-[11px] text-muted mb-1 capitalize">{key.replace(/_/g, ' ')}</label>
                  <input
                    value={params[key] ?? ''}
                    onChange={(e) => setParams((p) => ({ ...p, [key]: e.target.value }))}
                    placeholder={String(hint)}
                    className="w-full bg-surface3 border border-border rounded-lg px-3 py-2 text-sm text-gray-200 placeholder:text-faint focus:outline-none focus:border-accent/50"
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        <button
          type="button" onClick={handleRun}
          disabled={running || !selectedAction}
          className="btn-primary"
        >
          {running ? (
            <><Loader2 className="w-4 h-4 animate-spin" /> Running simulation…</>
          ) : (
            <><Play className="w-3.5 h-3.5" /> Run Simulation</>
          )}
        </button>
      </div>

      {runError && <ErrorBanner message={runError} />}

      {/* ── Result ── */}
      {result && (
        <div className="space-y-4">
          {/* Verdict banner */}
          <div className={`card p-5 border-l-2 flex items-start gap-4 ${result.allowed ? 'border-l-accent' : 'border-l-red-400'}`}>
            {result.allowed
              ? <CheckCircle2 className="w-5 h-5 text-accent shrink-0 mt-0.5" />
              : <XCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 mb-1 flex-wrap">
                <p className={`text-base font-bold ${result.allowed ? 'text-accent' : 'text-red-400'}`}>
                  {result.allowed ? 'Simulation approved' : 'Simulation blocked'}
                </p>
                {risk && (
                  <span className={`badge ${severityBadgeClass(risk)}`}>{risk} risk</span>
                )}
              </div>
              <p className="text-sm text-gray-300">{formatActionLabel(result.action, result.params)}</p>
              {result.verdict && (
                <p className="text-xs text-muted mt-1">{result.verdict}</p>
              )}
            </div>
          </div>

          {/* Key metrics row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricPill label="Blast radius" value={`${blastRadius} nodes`} />
            <MetricPill label="Projection steps" value={result.projections.length} sub={`${downtimeMinutes ?? 0} min window`} />
            <MetricPill label="Constraint tiers" value={Object.keys(result.tier_results).length} />
            <MetricPill
              label="Recommendation"
              value={
                <span className="text-xs font-normal text-gray-300 leading-snug line-clamp-2">
                  {result.recommendations[0] ?? result.warnings[0] ?? (result.allowed ? 'No action required' : 'Review violations')}
                </span>
              }
            />
          </div>

          {/* Tiers + affected */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Object.keys(result.tier_results).length > 0 && (
              <div className="card p-5">
                <SectionLabel>Constraint tiers</SectionLabel>
                <div className="space-y-2">
                  {Object.entries(result.tier_results).map(([tier, tr]) => (
                    <div key={tier} className="flex items-center justify-between">
                      <span className="text-sm text-gray-300 capitalize">{tier}</span>
                      <span className={`text-xs font-semibold ${tr.passed === false ? 'text-red-400' : 'text-accent'}`}>
                        {tr.passed === false ? 'FAIL' : 'PASS'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(result.reasons.length > 0 || result.warnings.length > 0 || affectedServices.length > 0) && (
              <div className="card p-5">
                {result.reasons.length > 0 && (
                  <>
                    <SectionLabel>Violations</SectionLabel>
                    <ul className="space-y-1.5 mb-4">
                      {result.reasons.map((r, i) => (
                        <li key={i} className="flex gap-2 text-xs text-red-300">
                          <ArrowRight className="w-3 h-3 shrink-0 mt-0.5 text-red-400" />{r}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                {result.warnings.length > 0 && (
                  <>
                    <SectionLabel>Warnings</SectionLabel>
                    <ul className="space-y-1.5 mb-4">
                      {result.warnings.map((w, i) => (
                        <li key={i} className="flex gap-2 text-xs text-yellow-300">
                          <ArrowRight className="w-3 h-3 shrink-0 mt-0.5 text-yellow-400" />{w}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                {affectedServices.length > 0 && (
                  <>
                    <SectionLabel>Affected nodes</SectionLabel>
                    <div className="flex flex-wrap gap-1.5">
                      {affectedServices.map((s) => (
                        <span key={s} className="text-xs px-2 py-0.5 rounded-full bg-red-500/12 text-red-300 border border-red-500/20 font-mono">
                          {shortNodeId(s)}
                        </span>
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Projections — summarised, not raw JSON */}
          {result.projections.length > 0 && (
            <Card title="Future projections" subtitle={`${result.projections.length} steps · ${downtimeMinutes ?? 0}-minute window`}>
              <div className="overflow-x-auto -mx-5">
                <table className="w-full">
                  <thead>
                    <tr>
                      <th className="table-head">Step</th>
                      <th className="table-head">Avg CPU</th>
                      <th className="table-head">Avg Memory</th>
                      <th className="table-head">Avg Latency</th>
                      <th className="table-head">Nodes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.projections.map((p, i) => {
                      const nodes = (p.nodes as Record<string, NodeMetrics>) ?? {}
                      const vals = Object.values(nodes)
                      const avgCpu = vals.length ? vals.reduce((s, n) => s + (n.cpu_percent ?? 0), 0) / vals.length : null
                      const avgMem = vals.length ? vals.reduce((s, n) => s + (n.memory_percent ?? 0), 0) / vals.length : null
                      const avgLat = vals.length ? vals.reduce((s, n) => s + (n.latency_ms ?? 0), 0) / vals.length : null
                      return (
                        <tr key={i} className="hover:bg-surface3/40 transition">
                          <td className="table-cell text-muted">+{i + 1}</td>
                          <td className="table-cell">
                            {avgCpu !== null ? (
                              <span className={avgCpu >= 80 ? 'text-red-400 text-xs font-semibold' : 'text-gray-400 text-xs'}>
                                {formatNumber(avgCpu, 1)}%
                              </span>
                            ) : <span className="text-muted text-xs">—</span>}
                          </td>
                          <td className="table-cell">
                            {avgMem !== null ? (
                              <span className={avgMem >= 85 ? 'text-yellow-400 text-xs font-semibold' : 'text-gray-400 text-xs'}>
                                {formatNumber(avgMem, 1)}%
                              </span>
                            ) : <span className="text-muted text-xs">—</span>}
                          </td>
                          <td className="table-cell text-xs text-gray-400">
                            {avgLat !== null ? `${formatNumber(avgLat, 1)} ms` : '—'}
                          </td>
                          <td className="table-cell text-xs text-muted">{vals.length}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* ── Scenario analysis ── */}
      {result && scenarioAnalysis && (
        <Card title="Workload scenario analysis" subtitle="Projected impact across operating conditions" className="mt-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
            {scenarioAnalysis.scenarios.map((scenario) => (
              <div key={scenario.id} className="px-4 py-4 rounded-lg bg-surface3 border border-border">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-white">{scenario.label}</p>
                  <span className={`badge ${severityBadgeClass(scenario.riskLevel)}`}>{scenario.riskLevel}</span>
                </div>
                <p className="text-[11px] text-muted mb-3">
                  {WORKLOAD_SCENARIOS.find((s) => s.id === scenario.id)?.description}
                </p>
                <div className="space-y-1 text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-muted">CPU</span>
                    <span className={scenario.avgCpu >= 80 ? 'text-red-400 font-semibold' : 'text-gray-300'}>{formatNumber(scenario.avgCpu, 1)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Power</span>
                    <span className="text-gray-300">{formatNumber(scenario.totalPower, 0)} W</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted">Latency</span>
                    <span className="text-gray-300">{formatNumber(scenario.avgLatency, 1)} ms</span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
            <div className="px-4 py-3 rounded-lg bg-accent/8 border border-accent/20">
              <p className="text-xs text-muted mb-1">Best case</p>
              <p className="text-sm font-semibold text-accent">{scenarioAnalysis.bestCase.label}</p>
              <p className="text-xs text-gray-400 mt-1">
                {formatNumber(scenarioAnalysis.bestCase.avgCpu, 1)}% CPU · {formatNumber(scenarioAnalysis.bestCase.avgLatency, 1)} ms · {scenarioAnalysis.bestCase.riskLevel} risk
              </p>
            </div>
            <div className="px-4 py-3 rounded-lg bg-red-500/8 border border-red-500/20">
              <p className="text-xs text-muted mb-1">Worst case</p>
              <p className="text-sm font-semibold text-red-400">{scenarioAnalysis.worstCase.label}</p>
              <p className="text-xs text-gray-400 mt-1">
                {formatNumber(scenarioAnalysis.worstCase.avgCpu, 1)}% CPU · {formatNumber(scenarioAnalysis.worstCase.avgLatency, 1)} ms · {scenarioAnalysis.worstCase.riskLevel} risk
              </p>
            </div>
          </div>

          <div className="pt-4 border-t border-border">
            <SectionLabel>Recommendations</SectionLabel>
            <ul className="space-y-2">
              {scenarioAnalysis.recommendations.map((rec, i) => (
                <li key={i} className="flex gap-2 text-sm text-gray-300">
                  <ArrowRight className="w-4 h-4 text-accent shrink-0 mt-0.5" />
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
    for (const n of impact.nodes_affected) if (typeof n === 'string') services.add(n)
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
    if (nodes && Object.keys(nodes).length > 0) return Object.values(nodes)
  }
  const graph = result.projected_graph as { nodes?: { metrics?: NodeMetrics }[] } | undefined
  if (graph?.nodes?.length) {
    return graph.nodes.map((n) => n.metrics ?? {}).filter((m) => typeof m.cpu_percent === 'number' || typeof m.power_watts === 'number')
  }
  return []
}

function aggregateScenarioMetrics(baseline: NodeMetrics[], modifiers: ScenarioModifiers): Omit<ScenarioAggregate, 'id' | 'label' | 'riskLevel' | 'riskScore'> {
  if (baseline.length === 0) return { avgCpu: 0, avgMemory: 0, totalPower: 0, avgLatency: 0, avgPacketLoss: 0, totalDiskIops: 0 }
  let cpuSum = 0, memSum = 0, powerSum = 0, latencySum = 0, packetSum = 0, iopsSum = 0, latencyCount = 0, packetCount = 0
  for (const node of baseline) {
    cpuSum += Math.min(100, (node.cpu_percent ?? 0) * modifiers.cpu)
    memSum += Math.min(100, (node.memory_percent ?? 0) * modifiers.memory)
    powerSum += (node.power_watts ?? 0) * modifiers.power
    iopsSum += (node.disk_iops ?? 0) * modifiers.diskIops
    if (node.latency_ms != null) { latencySum += node.latency_ms * modifiers.latency; latencyCount++ }
    if (node.packet_loss_percent != null) { packetSum += Math.min(100, node.packet_loss_percent * modifiers.packetLoss); packetCount++ }
  }
  const count = baseline.length
  return { avgCpu: cpuSum / count, avgMemory: memSum / count, totalPower: powerSum, avgLatency: latencyCount > 0 ? latencySum / latencyCount : 0, avgPacketLoss: packetCount > 0 ? packetSum / packetCount : 0, totalDiskIops: iopsSum }
}

function scoreScenarioRisk(metrics: Omit<ScenarioAggregate, 'id' | 'label' | 'riskLevel' | 'riskScore'>, simulationAllowed: boolean): { riskLevel: 'Low' | 'Medium' | 'High'; riskScore: number } {
  let score = 0
  if (metrics.avgCpu >= 85) score += 3; else if (metrics.avgCpu >= 70) score += 2; else if (metrics.avgCpu >= 55) score += 1
  if (metrics.avgMemory >= 90) score += 3; else if (metrics.avgMemory >= 75) score += 2; else if (metrics.avgMemory >= 60) score += 1
  if (metrics.avgLatency >= 100) score += 3; else if (metrics.avgLatency >= 50) score += 2; else if (metrics.avgLatency >= 25) score += 1
  if (metrics.avgPacketLoss >= 2) score += 2; else if (metrics.avgPacketLoss >= 0.5) score += 1
  if (!simulationAllowed) score += 2
  return { riskLevel: score >= 6 ? 'High' : score >= 3 ? 'Medium' : 'Low', riskScore: score }
}

function buildScenarioRecommendations(scenarios: ScenarioAggregate[], simulationAllowed: boolean): string[] {
  const byId = Object.fromEntries(scenarios.map((s) => [s.id, s]))
  const recs: string[] = []
  const { peak, batch, dr, normal } = byId
  if (normal?.riskLevel === 'Low' && simulationAllowed) recs.push('Change is stable under normal operating conditions.')
  if (peak?.riskLevel === 'Low') recs.push('Safe for Business Peak — projected headroom remains within acceptable limits.')
  else if (peak?.riskLevel === 'Medium') recs.push('Caution during Business Peak — monitor CPU and latency during high-traffic windows.')
  else if (peak) recs.push('Not recommended for Business Peak without capacity expansion or load balancing.')
  if (batch && batch.riskLevel !== 'High') recs.push('Suitable for Night Batch — disk throughput increase is within manageable bounds.')
  else if (batch) recs.push('Night Batch workloads may saturate storage IOPS — schedule during off-peak or add capacity.')
  if (dr?.riskLevel === 'High') recs.push('Requires capacity expansion before DR workloads — failover stress exceeds safe thresholds.')
  else if (dr?.riskLevel === 'Medium') recs.push('DR failover is feasible with active monitoring and a staged recovery plan.')
  else if (dr) recs.push('Disaster Recovery mode projected within safe operating envelope.')
  if (!simulationAllowed) recs.push('Address simulation constraint violations before applying this change to production.')
  return recs.length > 0 ? recs : ['Review projected metrics across all workload scenarios before deployment.']
}

function buildScenarioAnalysis(result: SimulationResult) {
  const baseline = extractBaselineNodeMetrics(result)
  if (baseline.length === 0) return null
  const scenarios: ScenarioAggregate[] = WORKLOAD_SCENARIOS.map((scenario) => {
    const metrics = aggregateScenarioMetrics(baseline, scenario.modifiers)
    const { riskLevel, riskScore } = scoreScenarioRisk(metrics, result.allowed)
    return { id: scenario.id, label: scenario.label, ...metrics, riskLevel, riskScore }
  })
  const sorted = [...scenarios].sort((a, b) => a.riskScore - b.riskScore)
  return { scenarios, bestCase: sorted[0], worstCase: sorted[sorted.length - 1], recommendations: buildScenarioRecommendations(scenarios, result.allowed) }
}
