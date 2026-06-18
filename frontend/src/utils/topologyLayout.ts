import type { GraphEdge, GraphNode } from '../api/topology'
import { shortNodeId } from './format'
import type { TopologyFlowNode } from '../components/TopologyNode'

const ROLE_LAYER: Record<string, number> = {
  'spine-switch': 0,
  'storage-tor': 0,
  'tor-router': 1,
  'compute-node': 2,
  'storage-controller': 2,
  'object-storage': 3,
  'metrics-collector': 2,
  'metrics-dashboard': 2,
  'infrastructure-docs': 2,
  'graph-database': 2,
  middleware: 2,
  'metrics-exporter': 3,
  'container-metrics': 3,
}

const ROLE_ORDER: Record<string, number> = {
  'spine-switch': 0,
  'storage-tor': 1,
  'tor-router': 2,
  'compute-node': 3,
  'storage-controller': 4,
  'object-storage': 5,
  'metrics-collector': 6,
  'metrics-dashboard': 7,
  'infrastructure-docs': 8,
  'graph-database': 9,
  middleware: 10,
  'metrics-exporter': 11,
  'container-metrics': 12,
}

function dropletPrefix(id: string): string {
  const slash = id.indexOf('/')
  return slash >= 0 ? id.slice(0, slash) : id
}

function roleLayer(node: GraphNode): number {
  const role = node.role ?? 'unknown'
  return ROLE_LAYER[role] ?? 2
}

function roleOrder(node: GraphNode): number {
  const role = node.role ?? 'unknown'
  return ROLE_ORDER[role] ?? 50
}

function assignBfsLayers(nodes: GraphNode[], edges: GraphEdge[]): Map<string, number> {
  const ids = new Set(nodes.map((n) => n.id))
  const incoming = new Map<string, number>()
  const adjacency = new Map<string, string[]>()

  for (const id of ids) {
    incoming.set(id, 0)
    adjacency.set(id, [])
  }

  for (const edge of edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target)) continue
    adjacency.get(edge.source)!.push(edge.target)
    incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1)
  }

  const layers = new Map<string, number>()
  const queue: string[] = []

  for (const [id, count] of incoming) {
    if (count === 0) queue.push(id)
  }

  if (queue.length === 0 && nodes.length > 0) {
    const spine = nodes.find((n) => n.role === 'spine-switch')
    queue.push(spine?.id ?? nodes[0].id)
  }

  const visited = new Set<string>()
  while (queue.length > 0) {
    const id = queue.shift()!
    if (visited.has(id)) continue
    visited.add(id)

    const parents = edges
      .filter((e) => e.target === id && layers.has(e.source))
      .map((e) => layers.get(e.source)!)
    const layer = parents.length > 0 ? Math.max(...parents) + 1 : 0
    layers.set(id, layer)

    for (const target of adjacency.get(id) ?? []) {
      if (!visited.has(target)) queue.push(target)
    }
  }

  for (const node of nodes) {
    if (!layers.has(node.id)) {
      layers.set(node.id, roleLayer(node) + 1)
    }
  }

  return layers
}

export function layoutTopologyNodes(
  graphNodes: GraphNode[],
  graphEdges: GraphEdge[],
): TopologyFlowNode[] {
  if (graphNodes.length === 0) return []

  const bfsLayers = assignBfsLayers(graphNodes, graphEdges)
  const droplets = [...new Set(graphNodes.map((n) => dropletPrefix(n.id)))].sort()

  const groups = new Map<string, GraphNode[]>()
  for (const node of graphNodes) {
    const droplet = dropletPrefix(node.id)
    const list = groups.get(droplet) ?? []
    list.push(node)
    groups.set(droplet, list)
  }

  for (const [, list] of groups) {
    list.sort((a, b) => roleOrder(a) - roleOrder(b) || a.id.localeCompare(b.id))
  }

  const dropletX = new Map<string, number>()
  const dropletWidth = 200
  const dropletGap = 80
  droplets.forEach((d, i) => {
    dropletX.set(d, i * (dropletWidth + dropletGap))
  })

  const layerY = new Map<number, number>()
  const layerGap = 120
  const nodeGap = 90

  return graphNodes.map((node) => {
    const droplet = dropletPrefix(node.id)
    const group = groups.get(droplet) ?? [node]
    const indexInGroup = group.findIndex((n) => n.id === node.id)
    const layer = bfsLayers.get(node.id) ?? roleLayer(node)
    const y = (layerY.get(layer) ?? 0) + layer * layerGap
    layerY.set(layer, Math.max(layerY.get(layer) ?? 0, indexInGroup))

    const groupWidth = Math.max(group.length - 1, 0) * nodeGap
    const baseX = (dropletX.get(droplet) ?? 0) + dropletWidth / 2
    const x = baseX - groupWidth / 2 + indexInGroup * nodeGap

    return {
      id: node.id,
      type: 'topology',
      position: { x, y },
      data: {
        label: shortNodeId(node.id),
        fullId: node.id,
        role: node.role ?? 'unknown',
        droplet,
        state: node.state ?? 'unknown',
      },
    }
  })
}

export function topologyEdgesToFlow(edges: GraphEdge[]): {
  id: string
  source: string
  target: string
  animated: boolean
  label?: string
  style: Record<string, string | number>
  markerEnd: { type: 'arrowclosed'; color: string }
}[] {
  return edges.map((e) => {
    const degraded = e.state === 'degraded' || e.state === 'warning'
    const color = degraded ? '#f87171' : '#3d5a80'
    return {
      id: `${e.source}::${e.target}`,
      source: e.source,
      target: e.target,
      animated: degraded,
      label: typeof e.description === 'string' ? undefined : undefined,
      style: {
        stroke: color,
        strokeWidth: degraded ? 2 : 1.5,
      },
      markerEnd: { type: 'arrowclosed' as const, color },
    }
  })
}
