import { api } from './client'

export interface GraphNode {
  id: string
  role?: string
  state?: string
  metrics?: Record<string, number | string | boolean>
  [key: string]: unknown
}

export interface GraphEdge {
  source: string
  target: string
  state?: string
  metrics?: Record<string, number | string | boolean>
  [key: string]: unknown
}

export interface TopologyGraph {
  graph?: Record<string, unknown>
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface NodeDetail extends GraphNode {
  neighbors?: string[]
}

export function getTopology() {
  return api<TopologyGraph>('GET', '/api/v1/topology')
}

export function getNodes() {
  return api<GraphNode[]>('GET', '/api/v1/topology/nodes')
}

export function getEdges() {
  return api<GraphEdge[]>('GET', '/api/v1/topology/edges')
}

export function getNode(nodeId: string) {
  return api<NodeDetail>('GET', `/api/v1/topology/node/${encodeURIComponent(nodeId)}`)
}
