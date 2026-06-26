/**
 * topologyLayout.ts
 *
 * Produces a layout that mirrors the reference infrastructure diagram exactly:
 *
 *   [Internet]
 *       |
 *   [DigitalOcean VPC]
 *       |
 *   ┌────────┬────────┬────────┬────────┐
 *   │ tor1   │ tor2   │  mgmt  │storage │
 *   │ zone   │ zone   │  zone  │  zone  │
 *   └────────┴────────┴────────┴────────┘
 *
 * Within each zone nodes are stacked top-to-bottom in this sublayer order:
 *   0 – network/router (tor-router, spine-switch, storage-tor)
 *   1 – primary services (compute-node, storage-controller, middleware,
 *        graph-database, infrastructure-docs, metrics-collector,
 *        metrics-dashboard, object-storage)
 *   2 – leaf/exporters (metrics-exporter, container-metrics)
 *
 * Everything is driven purely from `node.role` and `dropletPrefix(node.id)`.
 * No node IDs are hardcoded. No mock data.
 */

import type { GraphEdge, GraphNode } from '../api/topology'
import { shortNodeId } from './format'
import type { TopologyFlowNode } from '../components/TopologyNode'

// ─── sublayer order within a zone ────────────────────────────────────────────
const ROLE_SUBLAYER: Record<string, number> = {
  // Tier 0 – network gateway (always top of zone)
  'spine-switch':        0,
  'storage-tor':         0,
  'tor-router':          0,

  // Tier 1 – primary services
  'compute-node':        1,
  'storage-controller':  1,
  'object-storage':      1,
  'middleware':          1,
  'graph-database':      1,
  'infrastructure-docs': 1,
  'metrics-collector':   1,
  'metrics-dashboard':   1,

  // Tier 2 – leaf / observability exporters (always bottom of zone)
  'metrics-exporter':    2,
  'container-metrics':   2,
}

function roleSublayer(role: string): number {
  return ROLE_SUBLAYER[role] ?? 1
}

// ─── droplet prefix ───────────────────────────────────────────────────────────
export function dropletPrefix(id: string): string {
  const slash = id.indexOf('/')
  return slash >= 0 ? id.slice(0, slash) : id
}

// ─── zone label from droplet prefix ──────────────────────────────────────────
export function zoneLabel(prefix: string): string {
  const p = prefix.toLowerCase()
  if (p.includes('mgmt') || p.includes('management')) return 'Management'
  if (p.includes('storage'))                           return 'Storage'
  // tor1 / tor2 / any numbered tor → Compute A/B/C…
  const torMatch = p.match(/tor[-_]?(\d+)/)
  if (torMatch) {
    const idx = parseInt(torMatch[1], 10) - 1
    return `Compute ${'ABCDEFGH'[idx] ?? idx + 1}`
  }
  // generic fallback – strip leading digits/dashes, capitalise
  return prefix.replace(/^[^a-zA-Z]+/, '').replace(/[-_]\d+$/, '')
}

// ─── zone colour themes ───────────────────────────────────────────────────────
export interface ZoneTheme {
  header: string
  border: string
  bg: string
  glow: string
}

const ZONE_THEMES: Record<string, ZoneTheme> = {
  'Compute A':  { header: '#00d4aa', border: 'rgba(0,212,170,0.22)',   bg: 'rgba(0,212,170,0.04)',   glow: 'rgba(0,212,170,0.08)' },
  'Compute B':  { header: '#4d9fff', border: 'rgba(77,159,255,0.22)',  bg: 'rgba(77,159,255,0.04)',  glow: 'rgba(77,159,255,0.08)' },
  'Compute C':  { header: '#34d399', border: 'rgba(52,211,153,0.22)',  bg: 'rgba(52,211,153,0.04)',  glow: 'rgba(52,211,153,0.08)' },
  'Management': { header: '#e879f9', border: 'rgba(232,121,249,0.22)', bg: 'rgba(232,121,249,0.04)', glow: 'rgba(232,121,249,0.08)' },
  'Storage':    { header: '#f59e0b', border: 'rgba(245,158,11,0.22)',  bg: 'rgba(245,158,11,0.04)',  glow: 'rgba(245,158,11,0.08)' },
}

export function zoneTheme(label: string): ZoneTheme {
  return (
    ZONE_THEMES[label] ?? {
      header: '#94a3b8',
      border: 'rgba(148,163,184,0.18)',
      bg:     'rgba(148,163,184,0.03)',
      glow:   'rgba(148,163,184,0.05)',
    }
  )
}

// ─── layout constants ─────────────────────────────────────────────────────────
const NODE_W         = 160   // node card width  (matches TopologyNode)
const NODE_H         = 72    // node card + badge height (approx)
const NODE_V_GAP     = 14    // vertical gap between nodes in the same zone
const SUBLAYER_GAP   = 24    // extra gap between sublayer groups (0→1, 1→2)
const ZONE_PAD_X     = 20    // horizontal padding inside zone frame
const ZONE_PAD_TOP   = 52    // space for zone header label
const ZONE_PAD_BTM   = 20
const ZONE_H_GAP     = 56    // horizontal gap between zone columns

// Global spine nodes (Internet + VPC) rendered above the zone columns
const SPINE_TOP_Y    = 0
const SPINE_VPC_Y    = 90
const ZONES_START_Y  = 210   // Y where zone columns start

// ─── public types ─────────────────────────────────────────────────────────────
export interface ZoneBounds {
  prefix:  string
  label:   string
  theme:   ZoneTheme
  x:       number   // left edge of zone frame
  y:       number   // top edge of zone frame
  width:   number
  height:  number
}

// ─── helpers ──────────────────────────────────────────────────────────────────

/** Sort nodes within a zone: sublayer asc, then stable by original API order */
function sortZoneNodes(nodes: GraphNode[]): GraphNode[] {
  return [...nodes].sort((a, b) => {
    const sl = roleSublayer(a.role ?? '') - roleSublayer(b.role ?? '')
    return sl !== 0 ? sl : 0  // keep original order within same sublayer
  })
}

/** Height of a zone frame given how many nodes it contains and their sublayers */
function zoneHeight(nodes: GraphNode[]): number {
  if (nodes.length === 0) return ZONE_PAD_TOP + ZONE_PAD_BTM
  const sublayers = [...new Set(nodes.map(n => roleSublayer(n.role ?? '')))]
  const extraGaps = sublayers.length > 1 ? (sublayers.length - 1) * SUBLAYER_GAP : 0
  return (
    ZONE_PAD_TOP +
    nodes.length * NODE_H +
    (nodes.length - 1) * NODE_V_GAP +
    extraGaps +
    ZONE_PAD_BTM
  )
}

/** Width of a zone frame – just wide enough for one node column + padding */
function zoneWidth(): number {
  return NODE_W + ZONE_PAD_X * 2
}

// ─── computeZoneBounds (exported for overlay rendering) ──────────────────────
export function computeZoneBounds(graphNodes: GraphNode[]): ZoneBounds[] {
  if (graphNodes.length === 0) return []

  const droplets = getOrderedDroplets(graphNodes)
  const w = zoneWidth()

  return droplets.map((prefix, colIdx) => {
    const nodes  = graphNodes.filter(n => dropletPrefix(n.id) === prefix)
    const sorted = sortZoneNodes(nodes)
    const h      = zoneHeight(sorted)
    const label  = zoneLabel(prefix)
    const x      = colIdx * (w + ZONE_H_GAP)

    return { prefix, label, theme: zoneTheme(label), x, y: ZONES_START_Y, width: w, height: h }
  })
}

// ─── ordered droplet list (consistent column order) ──────────────────────────
/**
 * Sorts droplets so compute columns come first (left to right),
 * then management, then storage — matching the reference image.
 */
function dropletSortKey(prefix: string): number {
  const p = prefix.toLowerCase()
  if (p.includes('tor1') || p.match(/tor[-_]?1/)) return 0
  if (p.includes('tor2') || p.match(/tor[-_]?2/)) return 1
  if (p.includes('mgmt') || p.includes('management')) return 8
  if (p.includes('storage')) return 9
  return 5  // generic compute / unknown
}

function getOrderedDroplets(graphNodes: GraphNode[]): string[] {
  return [...new Set(graphNodes.map(n => dropletPrefix(n.id)))]
    .sort((a, b) => dropletSortKey(a) - dropletSortKey(b) || a.localeCompare(b))
}

// ─── Internet + VPC spine nodes ───────────────────────────────────────────────
/**
 * Returns synthetic spine flow-nodes (Internet, VPC) centered above the zones.
 * These are VISUAL-ONLY positional helpers; the actual node IDs come from the
 * backend if they exist, otherwise we skip them. For now the topology API does
 * not return Internet/VPC nodes, so we calculate center positions only to
 * align zone columns.
 */
function spineX(graphNodes: GraphNode[]): number {
  const droplets = getOrderedDroplets(graphNodes)
  const totalWidth =
    droplets.length * zoneWidth() + (droplets.length - 1) * ZONE_H_GAP
  return totalWidth / 2 - NODE_W / 2
}

// ─── main layout function ─────────────────────────────────────────────────────
export function layoutTopologyNodes(
  graphNodes: GraphNode[],
  _graphEdges: GraphEdge[],
): TopologyFlowNode[] {
  if (graphNodes.length === 0) return []

  const droplets  = getOrderedDroplets(graphNodes)
  const w         = zoneWidth()
  const result: TopologyFlowNode[] = []

  droplets.forEach((prefix, colIdx) => {
    const zoneX    = colIdx * (w + ZONE_H_GAP)
    const nodeX    = zoneX + ZONE_PAD_X                     // left edge of node inside zone
    const centerX  = zoneX + w / 2 - NODE_W / 2             // centered node X

    const nodes   = graphNodes.filter(n => dropletPrefix(n.id) === prefix)
    const sorted  = sortZoneNodes(nodes)

    let cursorY = ZONES_START_Y + ZONE_PAD_TOP
    let prevSublayer = -1

    sorted.forEach((node) => {
      const sl = roleSublayer(node.role ?? '')

      // Add extra gap when we cross a sublayer boundary
      if (prevSublayer !== -1 && sl !== prevSublayer) {
        cursorY += SUBLAYER_GAP
      }
      prevSublayer = sl

      result.push({
        id:   node.id,
        type: 'topology',
        position: { x: centerX, y: cursorY },
        data: {
          label:  shortNodeId(node.id),
          fullId: node.id,
          role:   node.role ?? 'unknown',
          droplet: prefix,
          state:  node.state ?? 'unknown',
        },
      })

      cursorY += NODE_H + NODE_V_GAP
    })
  })

  return result
}

// ─── edge → ReactFlow edge ────────────────────────────────────────────────────
export function topologyEdgesToFlow(edges: GraphEdge[]): {
  id: string
  source: string
  target: string
  animated: boolean
  label?: string
  style: Record<string, string | number>
  markerEnd: { type: 'arrowclosed'; color: string }
}[] {
  return edges.map(e => {
    const degraded = e.state === 'degraded' || e.state === 'warning'
    const color    = degraded ? '#f87171' : '#2d4a6e'
    return {
      id:       `${e.source}::${e.target}`,
      source:   e.source,
      target:   e.target,
      animated: degraded,
      label:    undefined,
      style: {
        stroke:      color,
        strokeWidth: degraded ? 2 : 1.5,
      },
      markerEnd: { type: 'arrowclosed' as const, color },
    }
  })
}