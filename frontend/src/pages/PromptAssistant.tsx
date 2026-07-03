import { useState, useEffect, useRef, type ReactNode } from 'react'
import { Loader2 } from 'lucide-react'
import {
  resolveMetrics,
  formatApiError,
  extractApiErrorDetail,
  mergeSimulationDisplay,
  type ResolveMetricsResponse,
  type ApiErrorDetailItem,
} from '../api/metrics'
import { type SimulationResult } from '../api/simulation'
import {
  formatActionLabel,
  formatNumber,
  riskFromSimulation,
  severityBadgeClass,
  shortNodeId,
} from '../utils/format'

// ── Scenario-analysis helpers (mirrors Simulation.tsx) ──────────────────────
interface ScenarioNodeMetrics {
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

function extractBaselineNodeMetrics(result: SimulationResult): ScenarioNodeMetrics[] {
  if (result.projections.length > 0) {
    const lastStep = result.projections[result.projections.length - 1]
    const nodes = lastStep.nodes as Record<string, ScenarioNodeMetrics> | undefined
    if (nodes && Object.keys(nodes).length > 0) return Object.values(nodes)
  }
  const graph = result.projected_graph as { nodes?: { metrics?: ScenarioNodeMetrics }[] } | undefined
  if (graph?.nodes?.length) {
    return graph.nodes.map((n) => n.metrics ?? {}).filter((m) => typeof m.cpu_percent === 'number' || typeof m.power_watts === 'number')
  }
  return []
}

function aggregateScenarioMetrics(baseline: ScenarioNodeMetrics[], modifiers: ScenarioModifiers): Omit<ScenarioAggregate, 'id' | 'label' | 'riskLevel' | 'riskScore'> {
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

function MetricPill({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <div className="px-4 py-3 rounded-lg bg-surface3 border border-border">
      <p className="text-[10px] text-muted uppercase tracking-wider mb-1">{label}</p>
      <div className="text-sm font-semibold text-white">{value}</div>
      {sub && <p className="text-[11px] text-muted mt-0.5">{sub}</p>}
    </div>
  )
}

// ── Pipeline steps ──────────────────────────────────────────────────────────
const PIPELINE_STEPS = [
  {
    id: 'parse',
    label: 'Parsing intent',
    detail: 'Reading your command and mapping it to a structured action with node IDs and parameters',
  },
  {
    id: 'clone',
    label: 'Cloning topology graph',
    detail: 'Creating an isolated sandbox copy of the live infrastructure graph — your real environment is untouched',
  },
  {
    id: 'mutate',
    label: 'Applying mutation',
    detail: 'Executing the change inside the sandbox — rewiring edges, updating node roles and connectivity',
  },
  {
    id: 'impact',
    label: 'Analysing impact',
    detail: 'Tracing how the change propagates — computing traffic deltas, CPU shifts, and load redistribution across neighbours',
  },
  {
    id: 'project',
    label: 'Projecting future state',
    detail: 'ML behaviour model is forecasting metric trajectories across the next 3 time steps post-change',
  },
  {
    id: 'scenarios',
    label: 'Running workload scenarios',
    detail: 'Re-running the simulation under normal load, business-peak traffic, and batch-job patterns to stress-test the change',
  },
  {
    id: 'validate',
    label: 'Validating constraints',
    detail: 'Checking all 4 tiers — Compute (CPU/memory), Network (latency/loss), Storage (IOPS), Power (watts) — against defined limits',
  },
  {
    id: 'recommend',
    label: 'Generating recommendations',
    detail: 'Analysing violations and warnings to produce plain-English remediation guidance',
  },
]

// Delays spread across realistic backend duration (~10-14s total).
// Parse/clone/mutate are fast (~1-2s total).
// Impact + projection take ~2-3s.
// Scenario loop is the heaviest — runs 2+ full deepcopy+validate cycles (~4-6s).
// Validate + recommend are quick but come after scenarios.
const STEP_DELAYS = [0, 1200, 2400, 3800, 6000, 8400, 11500, 13800]

const EXAMPLE_PROMPTS = [
  'move server-1 to router-2',
  'add compute node server-5 to router-1',
  'remove server-4',
  'inject CPU 92% on server-1',
  'latency 160ms spine-router to router-1',
  '3900 iops on server-2',
]

// ── SimulationStepper ───────────────────────────────────────────────────────
function SimulationStepper({ active }: { active: boolean }) {
  const [currentStep, setCurrentStep] = useState(0)
  const [elapsed, setElapsed]         = useState(0)
  const timers = useRef<ReturnType<typeof setTimeout>[]>([])
  const ticker = useRef<ReturnType<typeof setInterval> | null>(null)

  const lastIdx = PIPELINE_STEPS.length - 1
  const allDone = currentStep > lastIdx

  useEffect(() => {
    if (!active) {
      timers.current.forEach(clearTimeout)
      timers.current = []
      if (ticker.current) clearInterval(ticker.current)
      setCurrentStep(0)
      setElapsed(0)
      return
    }

    setCurrentStep(0)
    setElapsed(0)

    // Advance steps forward only — no cycling back
    STEP_DELAYS.forEach((delay, i) => {
      const t = setTimeout(() => setCurrentStep(i), delay)
      timers.current.push(t)
    })
    // After last step fires, mark all done (currentStep > lastIdx)
    const doneDelay = STEP_DELAYS[lastIdx] + 1200
    const t = setTimeout(() => setCurrentStep(lastIdx + 1), doneDelay)
    timers.current.push(t)

    // Elapsed counter — ticks every second so user sees honest wait time
    ticker.current = setInterval(() => setElapsed(s => s + 1), 1000)

    return () => {
      timers.current.forEach(clearTimeout)
      timers.current = []
      if (ticker.current) clearInterval(ticker.current)
    }
  }, [active])

  return (
    <div className="flex flex-col h-full items-center justify-center px-12">
      <div className="w-full max-w-xs">

        {/* Header + elapsed */}
        <div className="flex items-center justify-between mb-6">
          <p className="text-xs font-semibold text-muted uppercase tracking-widest">Running simulation</p>
          <p className="text-xs text-muted tabular-nums">{elapsed}s</p>
        </div>

        {/* Steps — only ever move forward */}
        <div className="space-y-0">
          {PIPELINE_STEPS.map((step, i) => {
            const done    = allDone || i < currentStep
            const running = !allDone && i === currentStep
            const pending = !allDone && i > currentStep
            return (
              <div key={step.id} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <div className={`w-px flex-1 ${i === 0 ? 'invisible' : done || running ? 'bg-accent/40' : 'bg-border'}`} />
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 my-1 transition-all duration-300 ${
                    done    ? 'bg-accent' :
                    running ? 'bg-accent ring-4 ring-accent/20' :
                              'bg-border'
                  }`} />
                  <div className={`w-px flex-1 ${i === lastIdx ? 'invisible' : done ? 'bg-accent/40' : 'bg-border'}`} />
                </div>
                <div className={`pb-4 pt-0.5 flex-1 transition-opacity duration-300 ${pending ? 'opacity-30' : 'opacity-100'}`}>
                  <p className={`text-sm font-medium ${running ? 'text-white' : done ? 'text-accent/70' : 'text-muted'}`}>
                    {step.label}
                  </p>
                  {running && (
                    <p className="text-xs text-muted mt-0.5">{step.detail}</p>
                  )}
                </div>
                {running && (
                  <div className="flex items-start pt-1.5">
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-accent" />
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* All steps done — waiting for backend response */}
        {allDone && (
          <div className="mt-4 flex items-center gap-3 pl-6">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-accent flex-shrink-0" />
            <p className="text-xs text-muted">Finalising results…</p>
          </div>
        )}

      </div>
    </div>
  )
}

// ── Idle state ──────────────────────────────────────────────────────────────
function RightPanelIdle() {
  return (
    <div className="flex flex-col items-center justify-center h-full px-12 text-center">
      <p className="text-xs font-semibold text-muted uppercase tracking-widest mb-4">Awaiting input</p>
      <p className="text-sm text-gray-400 max-w-sm leading-relaxed">
        Enter a plain-English infrastructure command on the left. The system will parse it, clone the live topology, run a full simulation, and return a validated result.
      </p>
      <div className="mt-10 w-full max-w-xs border-t border-border pt-6 space-y-3 text-left">
        {[
          ['Impact analysis',       'Traces cascading effects across all connected nodes'],
          ['Topology sandbox',      'Mutations run on an isolated clone — live graph is untouched'],
          ['4-tier validation',     'Compute, network, storage, and power constraints checked'],
          ['Workload projection',   'Tested against normal, peak, and batch traffic patterns'],
        ].map(([title, desc]) => (
          <div key={title}>
            <p className="text-xs font-semibold text-gray-300">{title}</p>
            <p className="text-[11px] text-muted leading-snug">{desc}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Configuration confirmation ──────────────────────────────────────────────

type FieldSpec = {
  key: string
  label: string
  hint: string
  type: 'text' | 'number' | 'select'
  default: string | number
  options?: { value: string; label: string }[]
  unit?: string
  required?: boolean
}

type ActionConfig = {
  title: string
  description: string
  fields: FieldSpec[]
}

const RACK_OPTIONS = [
  { value: 'droplet-1-tor1', label: 'Rack 1 (tor1)' },
  { value: 'droplet-2-tor2', label: 'Rack 2 (tor2)' },
]

function buildActionConfig(action: string, parsed: Record<string, unknown>): ActionConfig | null {
  const get = (k: string, fallback: string | number) => parsed[k] ?? fallback

  switch (action) {
    case 'add_compute':
      return {
        title: 'New server configuration',
        description: 'Confirm the settings for the server being added. The simulation will run with these values.',
        fields: [
          {
            key: 'node_id', label: 'Server name', hint: 'e.g. server-5',
            type: 'text', default: String(get('node_id', 'server-5')), required: true,
          },
          {
            key: 'target_rack_id', label: 'Target rack', hint: 'Which rack to provision into',
            type: 'select', default: String(get('target_rack_id', 'droplet-1-tor1')),
            options: RACK_OPTIONS,
          },
          {
            key: 'cpu_pct', label: 'Initial CPU', hint: 'Starting CPU utilisation',
            type: 'number', default: Number(get('cpu_pct', 20)), unit: '%',
          },
          {
            key: 'memory_pct', label: 'Initial memory', hint: 'Starting memory utilisation',
            type: 'number', default: Number(get('memory_pct', 30)), unit: '%',
          },
          {
            key: 'max_power_w', label: 'Max power draw', hint: 'Peak power under full load',
            type: 'number', default: Number(get('max_power_w', 500)), unit: 'W',
          },
          {
            key: 'u_size', label: 'Rack units', hint: 'Physical space consumed',
            type: 'number', default: Number(get('u_size', 2)), unit: 'U',
          },
          {
            key: 'nics', label: 'NICs', hint: 'Network interface count',
            type: 'number', default: Number(get('nics', 2)),
          },
        ],
      }

    case 'remove_node':
      return {
        title: 'Confirm node removal',
        description: 'This will simulate removing the node from the topology. All its connections will be severed.',
        fields: [
          {
            key: 'node_id', label: 'Node to remove', hint: 'The node that will be deleted from the graph',
            type: 'text', default: String(get('node_id', '')), required: true,
          },
        ],
      }

    case 'inject_compute':
      return {
        title: 'Compute stress configuration',
        description: 'Set the stress levels to inject. Leave a field blank to keep the current value.',
        fields: [
          {
            key: 'node_id', label: 'Target server', hint: 'The server to inject load on',
            type: 'text', default: String(get('node_id', '')), required: true,
          },
          {
            key: 'cpu_pct', label: 'CPU utilisation', hint: 'Injected CPU percentage',
            type: 'number', default: Number(get('cpu_pct', 85)), unit: '%',
          },
          {
            key: 'memory_pct', label: 'Memory utilisation', hint: 'Injected memory percentage',
            type: 'number', default: Number(get('memory_pct', 70)), unit: '%',
          },
          {
            key: 'power_w', label: 'Power draw', hint: 'Injected power in watts',
            type: 'number', default: Number(get('power_w', 400)), unit: 'W',
          },
        ],
      }

    case 'inject_network':
      return {
        title: 'Network fault configuration',
        description: 'Configure the network conditions to inject between the two nodes.',
        fields: [
          {
            key: 'source_node_id', label: 'Source node', hint: 'Origin of the degraded link',
            type: 'text', default: String(get('source_node_id', '')), required: true,
          },
          {
            key: 'target_node_id', label: 'Target node', hint: 'Destination of the degraded link',
            type: 'text', default: String(get('target_node_id', '')), required: true,
          },
          {
            key: 'latency_ms', label: 'Added latency', hint: 'Extra round-trip delay to inject',
            type: 'number', default: Number(get('latency_ms', 100)), unit: 'ms',
          },
          {
            key: 'packet_loss_pct', label: 'Packet loss', hint: 'Percentage of packets dropped',
            type: 'number', default: Number(get('packet_loss_pct', 5)), unit: '%',
          },
        ],
      }

    case 'inject_storage':
      return {
        title: 'Storage stress configuration',
        description: 'Set the storage load to inject on the target node.',
        fields: [
          {
            key: 'node_id', label: 'Target node', hint: 'The storage node to stress',
            type: 'text', default: String(get('node_id', '')), required: true,
          },
          {
            key: 'disk_iops', label: 'Disk IOPS', hint: 'Input/output operations per second to inject',
            type: 'number', default: Number(get('disk_iops', 3000)), unit: 'IOPS',
          },
        ],
      }

    case 'move_server':
      return {
        title: 'Server move configuration',
        description: 'Confirm which server is being moved and where it will land.',
        fields: [
          {
            key: 'server_id', label: 'Server to move', hint: 'The server node being relocated',
            type: 'text', default: String(get('server_id', '')), required: true,
          },
          {
            key: 'target_router_id', label: 'Destination router', hint: 'The router the server will connect to after the move',
            type: 'text', default: String(get('target_router_id', '')), required: true,
          },
        ],
      }

    case 'migrate_rack':
      return {
        title: 'Rack migration configuration',
        description: 'Confirm the rack being migrated and its destination.',
        fields: [
          {
            key: 'node_id', label: 'Node to migrate', hint: 'The node being moved between racks',
            type: 'text', default: String(get('node_id', '')), required: true,
          },
          {
            key: 'target_rack_id', label: 'Destination rack', hint: 'Target rack for this migration',
            type: 'select', default: String(get('target_rack_id', 'droplet-1-tor1')),
            options: RACK_OPTIONS,
          },
        ],
      }

    default:
      return null
  }
}

function ConfirmationPanel({
  action,
  parsedParams,
  onConfirm,
  onCancel,
}: {
  action: string
  parsedParams: Record<string, unknown>
  onConfirm: (params: Record<string, unknown>) => void
  onCancel: () => void
}) {
  const config = buildActionConfig(action, parsedParams)
  const [values, setValues] = useState<Record<string, string>>(() => {
    if (!config) return {}
    return Object.fromEntries(config.fields.map(f => [f.key, String(f.default)]))
  })

  if (!config) return null

  const set = (key: string, val: string) => setValues(prev => ({ ...prev, [key]: val }))

  const handleConfirm = () => {
    const out: Record<string, unknown> = { ...parsedParams }
    for (const field of config.fields) {
      const raw = values[field.key]
      if (raw === '' || raw === undefined) continue
      out[field.key] = field.type === 'number' ? parseFloat(raw) || 0 : raw
    }
    onConfirm(out)
  }

  const canSubmit = config.fields
    .filter(f => f.required)
    .every(f => (values[f.key] ?? '').trim() !== '')

  // Separate fields into full-width (text/select) and half-width (number) for grid layout
  const fullFields = config.fields.filter(f => f.type !== 'number')
  const numFields  = config.fields.filter(f => f.type === 'number')

  return (
    <div className="h-full flex flex-col justify-center px-10 py-6">
      {/* Header */}
      <div className="mb-5">
        <p className="text-[10px] font-semibold text-muted uppercase tracking-widest mb-1">Configuration required</p>
        <h2 className="text-sm font-semibold text-white">{config.title}</h2>
        <p className="text-xs text-gray-400 mt-1 leading-relaxed">{config.description}</p>
      </div>

      {/* Full-width fields (text, select) */}
      {fullFields.length > 0 && (
        <div className="space-y-3 mb-4">
          {fullFields.map(field => (
            <div key={field.key}>
              <label className="block text-[11px] font-semibold text-gray-400 mb-1">
                {field.label}{field.required && <span className="text-accent ml-0.5">*</span>}
              </label>
              {field.type === 'select' ? (
                <select
                  value={values[field.key] ?? ''}
                  onChange={e => set(field.key, e.target.value)}
                  className="w-full bg-surface3 border border-border rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-accent/40 transition-colors"
                >
                  {field.options?.map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={values[field.key] ?? ''}
                  onChange={e => set(field.key, e.target.value)}
                  placeholder={field.hint}
                  className="w-full bg-surface3 border border-border rounded px-3 py-2 text-sm text-gray-200 font-mono placeholder:text-faint focus:outline-none focus:border-accent/40 transition-colors"
                />
              )}
            </div>
          ))}
        </div>
      )}

      {/* Number fields in 2-column grid */}
      {numFields.length > 0 && (
        <div className="grid grid-cols-2 gap-3 mb-5">
          {numFields.map(field => (
            <div key={field.key}>
              <label className="block text-[11px] font-semibold text-gray-400 mb-1">{field.label}</label>
              <div className="flex items-center bg-surface3 border border-border rounded overflow-hidden focus-within:border-accent/40 transition-colors">
                <input
                  type="number"
                  value={values[field.key] ?? ''}
                  onChange={e => set(field.key, e.target.value)}
                  className="flex-1 bg-transparent px-3 py-2 text-sm text-gray-200 font-mono focus:outline-none min-w-0"
                />
                {field.unit && (
                  <span className="px-2.5 text-[11px] text-muted border-l border-border bg-surface2 self-stretch flex items-center">
                    {field.unit}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3 pt-1">
        <button
          type="button"
          onClick={handleConfirm}
          disabled={!canSubmit}
          className="px-5 py-2.5 rounded bg-accent text-bg text-sm font-semibold hover:brightness-110 transition disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Run Simulation
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2.5 rounded border border-border text-sm text-muted hover:text-gray-200 transition"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ── Human-readable helpers ──────────────────────────────────────────────────
function buildSummaryText(
  action: string,
  params: Record<string, unknown>,
  allowed: boolean,
  tierResults: Record<string, { passed?: boolean }>,
  scenarioResults: { passed?: boolean }[],
): string {
  const actionMap: Record<string, (p: Record<string, unknown>) => string> = {
    move_server:    (p) => `move ${shortNodeId(String(p.server_id ?? p.node_id ?? 'the server'))} to ${shortNodeId(String(p.target_router_id ?? p.target_router ?? 'the target router'))}`,
    add_compute:    (p) => `add a new compute node to ${shortNodeId(String(p.router_id ?? p.target_router ?? 'the router'))}`,
    remove_node:    (p) => `remove ${shortNodeId(String(p.node_id ?? p.server_id ?? 'the node'))} from the topology`,
    inject_compute: (p) => `inject ${p.cpu_percent ?? '?'}% CPU stress on ${shortNodeId(String(p.node_id ?? p.server_id ?? 'the server'))}`,
    inject_network: (p) => `introduce ${p.latency_ms ?? '?'}ms latency between ${shortNodeId(String(p.source_id ?? ''))} and ${shortNodeId(String(p.target_id ?? ''))}`,
    inject_storage: (p) => `push storage to ${p.iops ?? '?'} IOPS on ${shortNodeId(String(p.node_id ?? p.server_id ?? 'the server'))}`,
    migrate_rack:   (p) => `migrate rack ${shortNodeId(String(p.rack_id ?? 'the rack'))}`,
  }
  const what = actionMap[action]?.(params) ?? action.replace(/_/g, ' ')
  const passedTiers     = Object.values(tierResults).filter(t => t.passed !== false).length
  const totalTiers      = Object.keys(tierResults).length
  const passedScenarios = scenarioResults.filter(s => s.passed !== false).length

  if (allowed) {
    let text = `The request to ${what} passed simulation. `
    if (totalTiers > 0) text += `${passedTiers} of ${totalTiers} infrastructure constraint tiers cleared. `
    if (passedScenarios > 0) text += `Validated under ${passedScenarios} workload scenario${passedScenarios > 1 ? 's' : ''}. `
    text += `Safe to apply.`
    return text
  }
  return `The request to ${what} failed simulation. Constraint violations were detected that must be resolved before this change can be applied. Review the issues below.`
}

type ImpactEntry = {
  name: string
  trafficDelta: number | null
  cpu: number | null
  memory: number | null
  power: number | null
  sentiment: 'positive' | 'neutral' | 'negative'
  headline: string
  detail: string
}

function buildImpactEntries(impact: Record<string, unknown>): ImpactEntry[] {
  const entries: ImpactEntry[] = []
  for (const [nodeId, data] of Object.entries(impact)) {
    if (typeof data !== 'object' || data === null) continue
    const d = data as Record<string, unknown>
    const name = shortNodeId(nodeId)
    const trafficDelta = typeof d.traffic_delta_mbps === 'number' ? d.traffic_delta_mbps : null
    const c = (typeof d.compute === 'object' && d.compute !== null) ? d.compute as Record<string, number> : null
    const cpu    = c?.cpu_percent    ?? null
    const memory = c?.memory_percent ?? null
    const power  = c?.power_watts    ?? null

    let headline = ''
    let sentiment: ImpactEntry['sentiment'] = 'neutral'

    if (trafficDelta !== null && Math.abs(trafficDelta) >= 50) {
      if (trafficDelta < 0) {
        headline = `${Math.abs(trafficDelta)} Mbps offloaded — reduced traffic`
        sentiment = 'positive'
      } else {
        headline = `+${trafficDelta} Mbps additional traffic`
        sentiment = cpu !== null && cpu > 70 ? 'negative' : 'neutral'
      }
    } else if (cpu !== null && cpu > 80) {
      headline = `High CPU load — ${cpu.toFixed(0)}%`
      sentiment = 'negative'
    } else if (cpu !== null && cpu < 30) {
      headline = `Light load — within capacity`
      sentiment = 'positive'
    } else {
      headline = `Within normal operating range`
      sentiment = 'positive'
    }

    const parts: string[] = []
    if (cpu !== null)    parts.push(`CPU ${cpu.toFixed(0)}%`)
    if (memory !== null) parts.push(`Mem ${memory.toFixed(0)}%`)
    if (power !== null)  parts.push(`${power.toFixed(0)} W`)
    const detail = parts.join('  ·  ')

    entries.push({ name, trafficDelta, cpu, memory, power, sentiment, headline, detail })
  }
  return entries
}

const APPLYABLE_ACTIONS = new Set(['add_compute', 'remove_node'])

type ApplyResult = {
  status: string
  action: string
  container_name: string
  host: string
  rack: string
  container_ip?: string
  message: string
}

async function applyToInfrastructure(action: string, params: Record<string, unknown>): Promise<ApplyResult> {
  const res = await fetch('/api/v1/apply/simulate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, params }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail))
  }
  return res.json()
}

async function revertInfrastructure(applied: ApplyResult, params: Record<string, unknown>): Promise<ApplyResult> {
  const res = await fetch('/api/v1/apply/revert', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action:         applied.action,
      container_name: applied.container_name,
      host:           applied.host,
      rack:           applied.rack,
      params,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail))
  }
  return res.json()
}

// ── Results panel ───────────────────────────────────────────────────────────
const ERROR_COPY: Record<string, { title: string; badge: string; blurb: string }> = {
  NLP_ACTION_UNRECOGNISED: {
    title: 'Not understood',
    badge: 'parse error',
    blurb: 'The assistant could not confidently map this request to a supported action. Try rephrasing using the examples below.',
  },
  NLP_UNKNOWN_NODE: {
    title: 'Unknown node',
    badge: 'inventory mismatch',
    blurb: 'The request named a node that does not exist in the current topology.',
  },
  NLP_VALUE_OUT_OF_RANGE: {
    title: 'Invalid value',
    badge: 'validation error',
    blurb: 'The request was understood, but one or more values fall outside the allowed range.',
  },
  NLP_MALFORMED_RESPONSE: {
    title: 'Could not interpret request',
    badge: 'parse error',
    blurb: 'The assistant’s response could not be interpreted. Please rephrase your request.',
  },
  NLP_SERVICE_ERROR: {
    title: 'Assistant unavailable',
    badge: 'service error',
    blurb: 'The natural-language service could not process this request.',
  },
  NLP_UNAVAILABLE: {
    title: 'Assistant unavailable',
    badge: 'service error',
    blurb: 'The natural-language assistant is currently unavailable.',
  },
}

function ResultsPanel({
  resolveResult,
  simResult,
  error,
  errorDetail,
  onPrefill,
}: {
  resolveResult: ResolveMetricsResponse | null
  simResult: SimulationResult | null
  error: string | null
  errorDetail: ApiErrorDetailItem[] | null
  onPrefill: (text: string) => void
}) {
  const [applyDialog, setApplyDialog]       = useState(false)
  const [applyState, setApplyState]         = useState<'idle' | 'loading' | 'done' | 'reverting' | 'reverted' | 'error'>('idle')
  const [applyMessage, setApplyMessage]     = useState<string | null>(null)
  const [appliedResource, setAppliedResource] = useState<ApplyResult | null>(null)
  const [showRawJson, setShowRawJson]       = useState(false)
  const [showErrorJson, setShowErrorJson]   = useState(false)

  const openApplyDialog = () => {
    setApplyState('idle')
    setApplyMessage(null)
    setAppliedResource(null)
    setApplyDialog(true)
  }
  const closeApplyDialog = () => {
    if (applyState === 'loading' || applyState === 'reverting') return
    setApplyDialog(false)
  }

  const display = resolveResult ? mergeSimulationDisplay(resolveResult, simResult) : null
  const meta    = resolveResult?.parser_metadata

  if (error) {
    const primary = errorDetail?.[0]
    const code    = primary?.code
    const copy    = (code && ERROR_COPY[code]) || null
    const title   = copy?.title ?? 'Failed'
    const badge   = copy?.badge ?? 'error'
    const blurb   = copy?.blurb ?? error
    // Sub-details: either nested in the primary item, or one entry per error item
    const subDetails = primary?.details?.length
      ? primary.details
      : (errorDetail && errorDetail.length > 1 ? errorDetail : [])

    return (
      <div className="h-full overflow-y-auto px-8 py-7 space-y-8">
        {/* Verdict */}
        <div>
          <div className="flex items-baseline gap-4 mb-3">
            <span className="text-2xl font-bold tracking-tight text-red-400">
              {title}
            </span>
            <span className="badge text-[10px] font-semibold uppercase tracking-wider bg-red-500/15 text-red-400">
              {badge}
            </span>
          </div>
          <p className="text-sm text-gray-300 leading-relaxed max-w-xl">{blurb}</p>
          <div className="mt-4 h-px bg-red-500/20" />
        </div>

        {/* Reason */}
        <div>
          <SectionLabel>What went wrong</SectionLabel>
          <div className="px-4 py-3 rounded-lg bg-red-500/8 border border-red-500/20 text-sm text-red-300 leading-relaxed">
            {primary?.message ?? error}
          </div>
          {subDetails.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {subDetails.map((d, i) => (
                <li key={i} className="text-xs text-red-300/80 pl-3 border-l border-red-500/30 font-mono">
                  {d.path && <span className="text-red-400/90">{d.path}: </span>}
                  {d.message}
                  {d.value ? <span className="text-muted"> (got: {d.value})</span> : null}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Suggestions */}
        <div>
          <SectionLabel>Try instead</SectionLabel>
          <div className="space-y-2">
            {[
              'add compute node to tor2',
              'add a new server to rack 1',
              'remove server-4',
              'move server-1 to router-2',
            ].map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => onPrefill(s)}
                className="block w-full text-left px-3 py-2 rounded-lg bg-surface3 border border-border text-xs text-gray-300 font-mono hover:border-accent/40 hover:text-accent transition"
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {/* Raw JSON toggle */}
        {errorDetail && (
          <div className="border-t border-border pt-5">
            <button
              type="button"
              onClick={() => setShowErrorJson((v) => !v)}
              className="flex items-center gap-2 text-xs text-muted hover:text-gray-300 transition"
            >
              <span className={`inline-block w-3.5 h-3.5 border border-current rounded-sm transition-transform ${showErrorJson ? 'rotate-90' : ''}`}>
                <svg viewBox="0 0 14 14" fill="currentColor"><path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
              </span>
              {showErrorJson ? 'Hide raw JSON' : 'View raw JSON'}
            </button>
            {showErrorJson && (
              <pre className="mt-3 p-4 rounded-lg bg-surface3 border border-border text-[11px] font-mono text-gray-400 overflow-x-auto max-h-96 leading-relaxed">
                {JSON.stringify(errorDetail, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    )
  }

  if (!resolveResult || !meta || !display) return null

  const risk         = riskFromSimulation(display.allowed, display.reasons, display.warnings)
  const summaryText  = buildSummaryText(display.action, display.params, display.allowed, display.tier_results, display.scenario_results)
  const impactEntries = buildImpactEntries(display.impact_predictions as Record<string, unknown>)
  const tierEntries  = Object.entries(display.tier_results)
  const affectedServices = getAffectedServices(display)
  const blastRadius      = affectedServices.length || getBlastRadiusCount(display)
  const scenarioAnalysis = buildScenarioAnalysis(display)

  return (
    <div className="h-full overflow-y-auto px-8 py-7 space-y-8">

      {/* ── Verdict ── */}
      <div>
        <div className="flex items-baseline gap-4 mb-3">
          <span className={`text-2xl font-bold tracking-tight ${display.allowed ? 'text-accent' : 'text-red-400'}`}>
            {display.allowed ? 'Approved' : 'Blocked'}
          </span>
          <span className={`badge text-[10px] font-semibold uppercase tracking-wider ${severityBadgeClass(risk)}`}>
            {risk} risk
          </span>
        </div>
        <p className="text-sm text-gray-300 leading-relaxed max-w-xl">{summaryText}</p>
        <div className={`mt-4 h-px ${display.allowed ? 'bg-accent/20' : 'bg-red-500/20'}`} />
      </div>

      {/* ── Key metrics row ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricPill label="Blast radius" value={`${blastRadius} nodes`} />
        <MetricPill label="Projection steps" value={display.projection_steps} />
        <MetricPill label="Constraint tiers" value={tierEntries.length} />
        <MetricPill
          label="Recommendation"
          value={
            <span className="text-xs font-normal text-gray-300 leading-snug line-clamp-2">
              {display.recommendations[0] ?? display.warnings[0] ?? (display.allowed ? 'No action required' : 'Review violations')}
            </span>
          }
        />
      </div>

      {/* ── Affected nodes ── */}
      {affectedServices.length > 0 && (
        <div>
          <SectionLabel>Affected nodes</SectionLabel>
          <div className="flex flex-wrap gap-1.5">
            {affectedServices.map((s) => (
              <span key={s} className="text-xs px-2 py-0.5 rounded-full bg-red-500/12 text-red-300 border border-red-500/20 font-mono">
                {shortNodeId(s)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ── What was understood ── */}
      <div>
        <SectionLabel>Interpreted command</SectionLabel>
        <p className="text-sm text-white font-medium mb-3">{formatActionLabel(display.action, display.params)}</p>
        <div className="flex flex-wrap gap-2">
          {Object.entries(display.params)
            .filter(([, v]) => v !== null && v !== undefined && v !== '')
            .map(([k, v]) => (
              <div key={k} className="px-3 py-1.5 bg-surface2 border border-border rounded text-xs">
                <span className="text-muted">{k.replace(/_/g, ' ')}: </span>
                <span className="text-white font-mono">{shortNodeId(String(v))}</span>
              </div>
            ))}
        </div>
      </div>

      {/* ── Constraint tiers ── */}
      {tierEntries.length > 0 && (
        <div>
          <SectionLabel>Infrastructure constraint checks</SectionLabel>
          <div className="grid grid-cols-2 gap-px bg-border rounded overflow-hidden border border-border">
            {tierEntries.map(([tier, tr]) => {
              const passed = tr.passed !== false
              return (
                <div key={tier} className="bg-surface2 px-4 py-3 flex items-center justify-between">
                  <span className="text-sm text-gray-300 capitalize">{tier}</span>
                  <span className={`text-xs font-semibold ${passed ? 'text-accent' : 'text-red-400'}`}>
                    {passed ? 'Pass' : 'Fail'}
                  </span>
                </div>
              )
            })}
          </div>
          <p className="text-[11px] text-muted mt-2">Compute, network, storage, and power limits checked against the simulated topology.</p>
        </div>
      )}

      {/* ── Workload scenarios ── */}
      {display.scenario_results.length > 0 && (
        <div>
          <SectionLabel>Workload scenario validation</SectionLabel>
          <div className="space-y-2">
            {display.scenario_results.map((s, i) => {
              const name   = shortNodeId(String(s.scenario ?? s.node_id ?? `Scenario ${i + 1}`))
              const passed = s.passed !== false
              const label  = name.replace(/_/g, ' ')
              return (
                <div key={i} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                  <span className="text-sm text-gray-300 capitalize">{label}</span>
                  <span className={`text-xs font-semibold ${passed ? 'text-accent' : 'text-red-400'}`}>
                    {passed ? 'Pass' : 'Fail'}
                  </span>
                </div>
              )
            })}
          </div>
          <p className="text-[11px] text-muted mt-2">Normal load, business peak, and batch job patterns tested against the mutated topology.</p>
        </div>
      )}

      {/* ── Workload scenario analysis ── */}
      {scenarioAnalysis && (
        <div>
          <SectionLabel>Workload scenario analysis</SectionLabel>
          <p className="text-xs text-muted mb-3">Projected impact across operating conditions</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
            {scenarioAnalysis.scenarios.map((scenario) => (
              <div key={scenario.id} className="px-4 py-4 rounded-lg bg-surface3 border border-border">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-semibold text-white">{scenario.label}</p>
                  <span className={`badge text-[10px] ${severityBadgeClass(scenario.riskLevel)}`}>{scenario.riskLevel}</span>
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

          <div>
            <p className="text-[11px] font-semibold text-muted uppercase tracking-wider mb-2">Recommendations</p>
            <ul className="space-y-2">
              {scenarioAnalysis.recommendations.map((rec, i) => (
                <li key={i} className="flex gap-2 text-sm text-gray-300">
                  <span className="text-accent shrink-0">→</span>
                  {rec}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* ── Impact on other nodes ── */}
      {impactEntries.length > 0 && (
        <div>
          <SectionLabel>Projected impact on neighbouring nodes</SectionLabel>
          <div className="space-y-px border border-border rounded overflow-hidden">
            {impactEntries.map((entry) => (
              <div key={entry.name} className={`flex items-start justify-between px-4 py-3 bg-surface2 ${
                entry.sentiment === 'negative' ? 'border-l-2 border-yellow-500' :
                entry.sentiment === 'positive' ? 'border-l-2 border-accent' :
                'border-l-2 border-transparent'
              }`}>
                <div>
                  <p className="text-sm font-semibold text-white font-mono">{entry.name}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{entry.headline}</p>
                </div>
                <p className="text-[11px] text-muted text-right font-mono leading-relaxed whitespace-nowrap ml-6 mt-0.5">
                  {entry.detail}
                </p>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-muted mt-2">Projected metric changes on other topology nodes after this change is applied.</p>
        </div>
      )}

      {/* ── Recommendations / issues ── */}
      {(display.recommendations.length > 0 || display.warnings.length > 0 || display.reasons.length > 0) ? (
        <div>
          <SectionLabel>Action required</SectionLabel>
          {display.reasons.length > 0 && (
            <div className="mb-4">
              <p className="text-[11px] font-semibold text-red-400 uppercase tracking-wider mb-2">Blocking violations</p>
              <ul className="space-y-2">
                {display.reasons.map((r, i) => (
                  <li key={i} className="text-sm text-red-300/90 pl-3 border-l border-red-500/40">{r}</li>
                ))}
              </ul>
            </div>
          )}
          {display.warnings.length > 0 && (
            <div className="mb-4">
              <p className="text-[11px] font-semibold text-yellow-400 uppercase tracking-wider mb-2">Warnings</p>
              <ul className="space-y-2">
                {display.warnings.map((w, i) => (
                  <li key={i} className="text-sm text-yellow-300/80 pl-3 border-l border-yellow-500/40">{w}</li>
                ))}
              </ul>
            </div>
          )}
          {display.recommendations.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Recommendations</p>
              <ul className="space-y-2">
                {display.recommendations.map((rec, i) => (
                  <li key={i} className="text-sm text-gray-300 pl-3 border-l border-border">{rec}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : display.allowed ? (
        <div>
          <SectionLabel>Conclusion</SectionLabel>
          <p className="text-sm text-gray-300 leading-relaxed">
            No remediation required. The change passed all constraint tiers and workload scenarios.
            The digital twin ran {display.projection_steps} projection step{display.projection_steps !== 1 ? 's' : ''} and found no issues.
            This change can be applied to the live infrastructure.
          </p>
        </div>
      ) : null}

      {/* ── Apply button ── */}
      {display?.allowed && APPLYABLE_ACTIONS.has(display.action) && (
        <div className="border-t border-border pt-6">
          <p className="text-xs text-muted mb-4 leading-relaxed">
            Simulation passed. This change can be provisioned on live DigitalOcean infrastructure.
          </p>
          <button
            type="button"
            onClick={openApplyDialog}
            className="px-5 py-2.5 rounded bg-accent text-bg text-sm font-semibold hover:brightness-110 transition"
          >
            Apply to Infrastructure
          </button>
        </div>
      )}

      {/* ── Raw JSON toggle ── */}
      <div className="border-t border-border pt-5">
        <button
          type="button"
          onClick={() => setShowRawJson((v) => !v)}
          className="flex items-center gap-2 text-xs text-muted hover:text-gray-300 transition"
        >
          <span className={`inline-block w-3.5 h-3.5 border border-current rounded-sm transition-transform ${showRawJson ? 'rotate-90' : ''}`}>
            <svg viewBox="0 0 14 14" fill="currentColor"><path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/></svg>
          </span>
          {showRawJson ? 'Hide raw JSON' : 'View raw JSON'}
        </button>
        {showRawJson && (
          <pre className="mt-3 p-4 rounded-lg bg-surface3 border border-border text-[11px] font-mono text-gray-400 overflow-x-auto max-h-96 leading-relaxed">
            {JSON.stringify(resolveResult, null, 2)}
          </pre>
        )}
      </div>

      {/* ── Apply dialog ── */}
      {applyDialog && display && (
        <ApplyDialog
          action={display.action}
          params={display.params}
          applyState={applyState}
          applyMessage={applyMessage}
          appliedResource={appliedResource}
          onApply={async () => {
            setApplyState('loading')
            try {
              const r = await applyToInfrastructure(display.action, display.params)
              setAppliedResource(r)
              setApplyMessage(r.message)
              setApplyState('done')
            } catch (e) {
              setApplyMessage(e instanceof Error ? e.message : 'Unknown error')
              setApplyState('error')
            }
          }}
          onRevert={async () => {
            if (!appliedResource) return
            setApplyState('reverting')
            try {
              const r = await revertInfrastructure(appliedResource, display.params)
              setApplyMessage(r.message)
              setApplyState('reverted')
            } catch (e) {
              setApplyMessage(e instanceof Error ? e.message : 'Unknown error')
              setApplyState('error')
            }
          }}
          onClose={closeApplyDialog}
        />
      )}

    </div>
  )
}

// ── Apply dialog ─────────────────────────────────────────────────────────────
function ApplyDialog({
  action, params, applyState, applyMessage, appliedResource,
  onApply, onRevert, onClose,
}: {
  action: string
  params: Record<string, unknown>
  applyState: string
  applyMessage: string | null
  appliedResource: ApplyResult | null
  onApply: () => void
  onRevert: () => void
  onClose: () => void
}) {
  const busy = applyState === 'loading' || applyState === 'reverting'
  const node  = shortNodeId(String(params.node_id ?? params.server_id ?? ''))
  const rack  = shortNodeId(String(params.target_rack_id ?? params.target_droplet ?? ''))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative bg-surface border border-border rounded-lg shadow-2xl w-full max-w-md mx-4">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            <p className="text-[10px] font-semibold text-muted uppercase tracking-widest">DigitalOcean</p>
            <h2 className="text-sm font-semibold text-white mt-0.5">Apply to Infrastructure</h2>
          </div>
          {!busy && (
            <button
              type="button"
              onClick={onClose}
              className="text-muted hover:text-white transition text-lg leading-none"
            >
              ×
            </button>
          )}
        </div>

        {/* Body */}
        <div className="px-6 py-5">

          {/* idle — confirm prompt */}
          {applyState === 'idle' && (
            <div className="space-y-4">
              <p className="text-sm text-gray-300 leading-relaxed">
                This will provision a real change on your live DigitalOcean infrastructure.
                The action is permanent and cannot be undone without using the Revert option.
              </p>
              <div className="bg-surface2 border border-border rounded p-3 space-y-1.5">
                <Row label="Action"    value={action.replace(/_/g, ' ')} />
                {node && <Row label="Node"      value={node} mono />}
                {rack && <Row label="Rack"      value={rack} mono />}
              </div>
              <div className="flex gap-3 pt-1">
                <button
                  type="button"
                  onClick={onApply}
                  className="flex-1 py-2.5 rounded bg-accent text-bg text-sm font-semibold hover:brightness-110 transition"
                >
                  Confirm &amp; Apply
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2.5 rounded border border-border text-sm text-muted hover:text-white transition"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* loading */}
          {applyState === 'loading' && (
            <div className="flex flex-col items-center py-6 gap-4">
              <Loader2 className="w-8 h-8 animate-spin text-accent" />
              <div className="text-center">
                <p className="text-sm font-medium text-white">Provisioning on DigitalOcean</p>
                <p className="text-xs text-muted mt-1">SSHing into droplet and starting container…</p>
              </div>
            </div>
          )}

          {/* done */}
          {applyState === 'done' && appliedResource && (
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <div className="w-2 h-2 rounded-full bg-accent mt-1.5 flex-shrink-0" />
                <div>
                  <p className="text-sm font-semibold text-white">Change applied successfully</p>
                  <p className="text-xs text-gray-400 mt-1 leading-relaxed">{applyMessage}</p>
                </div>
              </div>
              <div className="bg-surface2 border border-border rounded p-3 space-y-1.5">
                <Row label="Container" value={appliedResource.container_name} mono />
                <Row label="Host"      value={appliedResource.host} mono />
                <Row label="Rack"      value={appliedResource.rack} mono />
                {appliedResource.container_ip && <Row label="IP" value={appliedResource.container_ip} mono />}
              </div>
              <div className="border-t border-border pt-4">
                <p className="text-xs text-muted mb-3">Need to undo this? Revert will stop and remove the container.</p>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={onRevert}
                    className="px-4 py-2 rounded border border-border text-sm text-muted hover:text-white hover:border-red-500/50 transition"
                  >
                    Revert Change
                  </button>
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-4 py-2 rounded bg-surface2 border border-border text-sm text-gray-300 hover:text-white transition"
                  >
                    Done
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* reverting */}
          {applyState === 'reverting' && (
            <div className="flex flex-col items-center py-6 gap-4">
              <Loader2 className="w-8 h-8 animate-spin text-accent" />
              <div className="text-center">
                <p className="text-sm font-medium text-white">Reverting change</p>
                <p className="text-xs text-muted mt-1">Stopping and removing container…</p>
              </div>
            </div>
          )}

          {/* reverted */}
          {applyState === 'reverted' && (
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <div className="w-2 h-2 rounded-full bg-yellow-400 mt-1.5 flex-shrink-0" />
                <div>
                  <p className="text-sm font-semibold text-white">Change reverted</p>
                  <p className="text-xs text-gray-400 mt-1 leading-relaxed">{applyMessage}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="w-full py-2 rounded bg-surface2 border border-border text-sm text-gray-300 hover:text-white transition"
              >
                Close
              </button>
            </div>
          )}

          {/* error */}
          {applyState === 'error' && (
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <div className="w-2 h-2 rounded-full bg-red-400 mt-1.5 flex-shrink-0" />
                <div>
                  <p className="text-sm font-semibold text-white">Operation failed</p>
                  <p className="text-xs text-red-300 mt-1 leading-relaxed">{applyMessage}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="w-full py-2 rounded border border-border text-sm text-muted hover:text-white transition"
              >
                Close
              </button>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-[11px] text-muted">{label}</span>
      <span className={`text-[11px] text-gray-200 ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  )
}

// ── Minimal helpers ──────────────────────────────────────────────────────────
function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="text-[11px] font-semibold text-muted uppercase tracking-widest mb-3">{children}</p>
  )
}

// Actions that always need confirmation before simulation
const CONFIRM_ACTIONS = new Set([
  'add_compute', 'remove_node', 'inject_compute',
  'inject_network', 'inject_storage', 'move_server', 'migrate_rack',
])

// ── Main page ────────────────────────────────────────────────────────────────
export default function PromptAssistantPage() {
  const [prompt, setPrompt]               = useState('')
  const [loading, setLoading]             = useState(false)
  const [preResolving, setPreResolving]   = useState(false)
  const [error, setError]                 = useState<string | null>(null)
  const [errorDetail, setErrorDetail]     = useState<ApiErrorDetailItem[] | null>(null)
  const [resolveResult, setResolveResult] = useState<ResolveMetricsResponse | null>(null)
  const [simResult, setSimResult]         = useState<SimulationResult | null>(null)
  const [confirming, setConfirming]       = useState<{ action: string; params: Record<string, unknown>; projectionSteps: number } | null>(null)
  const textareaRef                       = useRef<HTMLTextAreaElement>(null)

  const hasResult = !!resolveResult || !!error
  const showConfirm = !!confirming && !loading && !preResolving && !hasResult

  const handleClear = () => {
    setPrompt('')
    setError(null)
    setErrorDetail(null)
    setResolveResult(null)
    setSimResult(null)
    setConfirming(null)
    textareaRef.current?.focus()
  }

  // Detect action from prompt text WITHOUT hitting the backend.
  // Good enough to decide which config form to show — the real parse happens on confirm.
  const detectAction = (text: string): string | null => {
    const t = text.toLowerCase()
    if (/\badd\b.*(server|compute|node)/.test(t) || /\bnew server\b/.test(t)) return 'add_compute'
    if (/\bremove\b|\bdelete\b|\btake down\b/.test(t)) return 'remove_node'
    if (/\bmove\b|\brelocate\b/.test(t)) return 'move_server'
    if (/\bmigrate\b.*rack/.test(t)) return 'migrate_rack'
    if (/\binject\b.*cpu|\bcpu\b.*%|\bstress\b.*cpu|\bmemory\b.*%|\bram\b/.test(t)) return 'inject_compute'
    if (/\blatency\b|\bpacket.?loss\b|\bbandwidth\b/.test(t)) return 'inject_network'
    if (/\biops\b|\bdisk\b|\bstorage\b.*stress/.test(t)) return 'inject_storage'
    return null
  }

  // Called when user clicks Run Simulation
  const handleSubmit = async () => {
    const text = prompt.trim()
    if (!text) return
    setError(null)
    setErrorDetail(null)
    setResolveResult(null)
    setSimResult(null)

    const action = detectAction(text)
    if (action && CONFIRM_ACTIONS.has(action)) {
      // Pre-resolve via NLP so the form opens pre-filled with whatever the
      // user already typed (node id, percentages, etc.) instead of blank —
      // the user still confirms/edits before the real simulation runs.
      // Uses a lightweight spinner, not the full simulation stepper — this
      // is just a quick parse, not a mutation/validation run.
      setPreResolving(true)
      try {
        const resolved = await resolveMetrics(text)
        const resolvedAction = resolved.parser_metadata.action || action
        setConfirming({
          action: resolvedAction,
          params: resolved.parser_metadata.parsed_params ?? {},
          projectionSteps: 3,
        })
      } catch {
        // Fall back to a blank form if pre-resolution fails — user can fill manually
        setConfirming({ action, params: {}, projectionSteps: 3 })
      } finally {
        setPreResolving(false)
      }
      return
    }

    // blast_radius_query and unknown — go straight to backend
    runFull(text, null)
  }

  // Called when user confirms the config form
  const runWithParams = (action: string, confirmedParams: Record<string, unknown>) => {
    setConfirming(null)
    runFull(prompt.trim(), { action, params: confirmedParams })
  }

  // Single place that hits the backend and sets all result state
  const runFull = async (
    text: string,
    override: { action: string; params: Record<string, unknown> } | null,
  ) => {
    setLoading(true)
    setError(null)
    setErrorDetail(null)
    setResolveResult(null)
    setSimResult(null)
    const startedAt = Date.now()
    // The step-by-step visual is a fixed choreography (STEP_DELAYS), not driven
    // by real backend progress — the actual pipeline (mutate, impact, projection,
    // scenario loop, validation) runs synchronously and often finishes in ~1-3s.
    // Hold the result until the animation has fully played out so steps never
    // appear to be skipped.
    const MIN_DISPLAY_MS = STEP_DELAYS[STEP_DELAYS.length - 1] + 1200
    try {
      let resolved: ResolveMetricsResponse
      if (override) {
        // User confirmed explicit params in the form — re-simulate against
        // those exact values directly (bypasses NLP re-parsing so the
        // confirmed numbers, not the LLM's stale defaults, drive validation).
        resolved = await resolveMetrics(text, {
          action: override.action,
          params: override.params,
        })
      } else {
        // Always run Gemini NLP first — no deterministic shortcuts
        resolved = await resolveMetrics(text)
      }
      const remaining = MIN_DISPLAY_MS - (Date.now() - startedAt)
      if (remaining > 0) await new Promise((r) => setTimeout(r, remaining))
      setResolveResult(resolved)
    } catch (e) {
      const remaining = MIN_DISPLAY_MS - (Date.now() - startedAt)
      if (remaining > 0) await new Promise((r) => setTimeout(r, remaining))
      setError(formatApiError(e))
      setErrorDetail(extractApiErrorDetail(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col -m-6 overflow-hidden" style={{ height: 'calc(100vh - 56px)' }}>

      {/* ── Top bar ── */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-border bg-surface flex items-center justify-between">
        <div>
          <h1 className="text-sm font-semibold text-white tracking-tight">Prompt Assistant</h1>
          <p className="text-xs text-muted mt-0.5">Natural language infrastructure simulation</p>
        </div>
        {(hasResult || showConfirm) && !loading && !preResolving && (
          <button
            type="button"
            onClick={handleClear}
            className="text-xs text-muted hover:text-gray-200 border border-border px-3 py-1.5 rounded transition hover:bg-surface2"
          >
            Clear
          </button>
        )}
      </div>

      {/* ── Split panels ── */}
      <div className="flex flex-1 min-h-0">

        {/* ── LEFT ── */}
        <div className="w-80 flex-shrink-0 flex flex-col border-r border-border bg-surface">

          {/* Input area */}
          <div className="p-5 border-b border-border flex flex-col gap-3">
            <label className="text-[10px] font-semibold text-muted uppercase tracking-widest">
              Command
            </label>
            <textarea
              ref={textareaRef}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe an infrastructure change in plain English…"
              rows={5}
              disabled={loading || preResolving}
              className="w-full bg-surface3 border border-border rounded px-3 py-2.5 text-sm text-gray-200 placeholder:text-faint focus:outline-none focus:border-accent/40 resize-none transition-colors font-sans"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit()
              }}
            />
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-faint">Ctrl + Enter to run</span>
            </div>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={loading || preResolving || !prompt.trim()}
              className="w-full py-2 rounded bg-accent text-bg text-sm font-semibold hover:brightness-110 transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {loading || preResolving
                ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Processing</>
                : 'Run Simulation'
              }
            </button>
          </div>

          {/* Examples */}
          <div className="p-5 flex-1 overflow-y-auto">
            <p className="text-[10px] font-semibold text-muted uppercase tracking-widest mb-3">Examples</p>
            <div className="space-y-1.5">
              {EXAMPLE_PROMPTS.map((example) => (
                <button
                  key={example}
                  type="button"
                  disabled={loading}
                  onClick={() => { setPrompt(example); textareaRef.current?.focus() }}
                  className="w-full text-left text-xs text-muted px-3 py-2 rounded border border-border bg-surface3 hover:text-gray-200 hover:border-accent/30 transition disabled:opacity-40"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* ── RIGHT ── */}
        <div className="flex-1 min-w-0 bg-bg">
          {loading ? (
            <SimulationStepper active={loading} />
          ) : preResolving ? (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <Loader2 className="w-5 h-5 animate-spin text-accent" />
              <p className="text-xs text-muted">Reading your command…</p>
            </div>
          ) : showConfirm ? (
            <ConfirmationPanel
              action={confirming.action}
              parsedParams={confirming.params}
              onConfirm={(params) => runWithParams(confirming.action, params)}
              onCancel={handleClear}
            />
          ) : hasResult ? (
            <ResultsPanel resolveResult={resolveResult} simResult={simResult} error={error} errorDetail={errorDetail} onPrefill={(text) => { handleClear(); setPrompt(text) }} />
          ) : (
            <RightPanelIdle />
          )}
        </div>
      </div>
    </div>
  )
}
