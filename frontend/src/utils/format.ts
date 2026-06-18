export function formatNumber(n: number, decimals = 0): string {
  return n.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

export function shortNodeId(id: string): string {
  const parts = id.split('/')
  return parts[parts.length - 1] ?? id
}

export function aggregatePowerKw(
  nodes: Record<string, { metrics?: Record<string, number | string | boolean> }>,
): number | null {
  let total = 0
  let count = 0
  for (const node of Object.values(nodes)) {
    const watts = node.metrics?.power_watts
    if (typeof watts === 'number') {
      total += watts
      count++
    }
  }
  if (count === 0) return null
  return total / 1000
}

export function averageCpu(
  nodes: Record<string, { metrics?: Record<string, number | string | boolean> }>,
): number | null {
  let total = 0
  let count = 0
  for (const node of Object.values(nodes)) {
    const cpu = node.metrics?.cpu_percent
    if (typeof cpu === 'number') {
      total += cpu
      count++
    }
  }
  if (count === 0) return null
  return total / count
}

export function averageTemp(
  nodes: Record<string, { metrics?: Record<string, number | string | boolean> }>,
): number | null {
  let total = 0
  let count = 0
  for (const node of Object.values(nodes)) {
    const temp = node.metrics?.temp_c
    if (typeof temp === 'number') {
      total += temp
      count++
    }
  }
  if (count === 0) return null
  return total / count
}

export function riskFromSimulation(allowed: boolean, reasons: string[], warnings: string[]): string {
  if (!allowed || reasons.length > 0) return 'High'
  if (warnings.length > 0) return 'Medium'
  return 'Low'
}

export function formatActionLabel(action: string, params: Record<string, unknown>): string {
  const labels: Record<string, string> = {
    move_server: 'Move Server',
    add_compute: 'Add Compute Node',
    remove_node: 'Remove Node',
    inject_compute: 'Inject Compute Stress',
    inject_network: 'Inject Network Degradation',
    inject_storage: 'Inject Storage Pressure',
    migrate_rack: 'Migrate Rack',
  }
  const base = labels[action] ?? action
  const nodeId = params.node_id ?? params.server_id
  if (nodeId) return `${base}: ${nodeId}`
  return base
}

export interface DriftRow {
  system: string
  issue: string
  severity: 'Critical' | 'Medium' | 'Low'
  recommendation: string
}

const TIER_RECOMMENDATIONS: Record<string, string> = {
  power: 'Rebalance power envelope across racks',
  rack: 'Reapply infrastructure schema',
  compute: 'Validate deployment manifest',
  storage: 'Sync storage configuration',
  network: 'Sync monitoring configuration',
}

export function buildDriftRows(validate: {
  allowed: boolean
  reasons: string[]
  warnings: string[]
  tier_results: Record<string, { violations?: string[]; warnings?: string[]; future_violations?: string[] }>
}): DriftRow[] {
  const rows: DriftRow[] = []
  const seen = new Set<string>()

  const addRow = (row: DriftRow) => {
    const key = `${row.severity}:${row.issue}`
    if (seen.has(key)) return
    seen.add(key)
    rows.push(row)
  }

  for (const reason of validate.reasons) {
    addRow({
      system: extractNodeFromText(reason) ?? 'Infrastructure',
      issue: reason,
      severity: 'Critical',
      recommendation: findTierRecommendation(reason, validate.tier_results),
    })
  }

  for (const warning of validate.warnings) {
    addRow({
      system: extractNodeFromText(warning) ?? 'Infrastructure',
      issue: warning,
      severity: 'Medium',
      recommendation: findTierRecommendation(warning, validate.tier_results),
    })
  }

  for (const [tier, result] of Object.entries(validate.tier_results)) {
    for (const v of result.violations ?? []) {
      addRow({
        system: extractNodeFromText(v) ?? tier,
        issue: v,
        severity: 'Critical',
        recommendation: TIER_RECOMMENDATIONS[tier] ?? 'Review constraint configuration',
      })
    }
    for (const w of result.warnings ?? []) {
      addRow({
        system: extractNodeFromText(w) ?? tier,
        issue: w,
        severity: 'Medium',
        recommendation: TIER_RECOMMENDATIONS[tier] ?? 'Review constraint configuration',
      })
    }
    for (const v of result.future_violations ?? []) {
      addRow({
        system: extractNodeFromText(v) ?? tier,
        issue: v,
        severity: 'Low',
        recommendation: TIER_RECOMMENDATIONS[tier] ?? 'Review constraint configuration',
      })
    }
  }

  return rows
}

function extractNodeFromText(text: string): string | null {
  const match = text.match(/[\w-]+\/[\w-]+|[\w-]+-[\w-]+/g)
  return match?.[0] ?? null
}

function findTierRecommendation(
  text: string,
  tierResults: Record<string, { violations?: string[]; warnings?: string[] }>,
): string {
  for (const [tier, result] of Object.entries(tierResults)) {
    const all = [...(result.violations ?? []), ...(result.warnings ?? [])]
    if (all.some((v) => v === text || text.includes(tier))) {
      return TIER_RECOMMENDATIONS[tier] ?? 'Review constraint configuration'
    }
  }
  return 'Review constraint configuration'
}

export function stateBadgeClass(state?: string): string {
  switch (state?.toLowerCase()) {
    case 'healthy':
    case 'active':
      return 'bg-green-500/15 text-green-400 border-green-500/30'
    case 'warning':
      return 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
    case 'critical':
      return 'bg-red-500/15 text-red-400 border-red-500/30'
    default:
      return 'bg-blue-500/15 text-blue-400 border-blue-500/30'
  }
}

export function severityBadgeClass(severity: string): string {
  switch (severity.toLowerCase()) {
    case 'critical':
    case 'high':
      return 'bg-red-500/15 text-red-400'
    case 'medium':
    case 'warning':
      return 'bg-yellow-500/15 text-yellow-400'
    case 'low':
      return 'bg-blue-500/15 text-blue-400'
    default:
      return 'bg-gray-500/15 text-gray-400'
  }
}
