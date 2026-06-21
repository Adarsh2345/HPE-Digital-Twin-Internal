import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  MarkerType,
  type NodeMouseHandler,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { PageHeader, Card, LoadingSpinner, ErrorBanner } from '../components/ui'
import { getTopology } from '../api/topology'
import { getNode } from '../api/topology'
import { getNodeTelemetry } from '../api/telemetry'
import { useFetch } from '../hooks/usePolling'
import { shortNodeId, stateBadgeClass } from '../utils/format'
import { layoutTopologyNodes, topologyEdgesToFlow } from '../utils/topologyLayout'
import TopologyNode, { type TopologyFlowNode } from '../components/TopologyNode'
import type { NodeTelemetryDetail } from '../api/telemetry'
import type { Edge } from '@xyflow/react'

const nodeTypes = { topology: TopologyNode }

function FitViewOnLoad({ count }: { count: number }) {
  const { fitView } = useReactFlow()
  useEffect(() => {
    if (count === 0) return
    const timer = setTimeout(() => {
      fitView({
  padding: 0.02,
  duration: 300,
  maxZoom: 1.4,
})
    }, 80)
    return () => clearTimeout(timer)
  }, [count, fitView])
  return null
}

function TopologyGraph() {
  const { data: topology, loading, error } = useFetch(getTopology, [])
  const [nodes, setNodes, onNodesChange] = useNodesState<TopologyFlowNode>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [localSearch, setLocalSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [nodeDetail, setNodeDetail] = useState<Record<string, unknown> | null>(null)
  const [nodeTelemetry, setNodeTelemetry] = useState<NodeTelemetryDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)

  const filteredNodes = useMemo(() => {
    if (!topology?.nodes) return []
    const q = localSearch.trim().toLowerCase()
    if (!q) return topology.nodes
    return topology.nodes.filter(
      (n) =>
        n.id.toLowerCase().includes(q) ||
        (n.role ?? '').toLowerCase().includes(q),
    )
  }, [topology, localSearch])

  const displayEdges = useMemo(() => {
    if (!topology?.edges) return []
    const nodeIds = new Set(filteredNodes.map((n) => n.id))
    return topology.edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
  }, [topology, filteredNodes])

  useEffect(() => {
    if (!topology) return
    setNodes(layoutTopologyNodes(filteredNodes, topology.edges))
    setEdges(
      topologyEdgesToFlow(displayEdges).map((e) => ({
        ...e,
        markerEnd: { type: MarkerType.ArrowClosed, color: e.markerEnd.color },
      })),
    )
  }, [topology, filteredNodes, displayEdges, setNodes, setEdges])

  const loadNodeDetail = useCallback(async (nodeId: string) => {
    setDetailError(null)
    try {
      const [detail, telemetry] = await Promise.all([
        getNode(nodeId),
        getNodeTelemetry(nodeId),
      ])
      setNodeDetail(detail)
      setNodeTelemetry(telemetry)
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : 'Failed to load node details')
      setNodeDetail(null)
      setNodeTelemetry(null)
    }
  }, [])

  useEffect(() => {
    if (!selectedId) return
    loadNodeDetail(selectedId)
    const id = setInterval(() => loadNodeDetail(selectedId), 4000)
    return () => clearInterval(id)
  }, [selectedId, loadNodeDetail])

  const onNodeClick: NodeMouseHandler = useCallback((_e, node) => {
    setSelectedId(node.id)
  }, [])

  const metrics = (nodeTelemetry?.metrics ?? {}) as Record<string, number>
  const state = (nodeTelemetry?.state ?? nodeDetail?.state) as string | undefined
  const neighbors = (nodeDetail?.neighbors ?? []) as string[]

  return (
    <div>
      <PageHeader
        title="Infrastructure Topology"
        subtitle={
          topology
            ? `${topology.nodes.length} nodes · ${topology.edges.length} connections`
            : 'Live network graph from backend topology API'
        }
      />

      {error && <ErrorBanner message={error} />}

      <div className="flex gap-4 h-[calc(100vh-180px)]">
        <div className="flex-1 card overflow-hidden flex flex-col">
          <div className="px-4 py-2 border-b border-border flex items-center gap-3">
            <input
              type="search"
              value={localSearch}
              onChange={(e) => setLocalSearch(e.target.value)}
              placeholder="Filter nodes by name or role..."
              className="flex-1 bg-surface3 border border-border rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-accent/50"
            />
            {localSearch && (
              <span className="text-xs text-muted whitespace-nowrap">
                {filteredNodes.length} / {topology?.nodes.length ?? 0} nodes
              </span>
            )}
          </div>

          {loading ? (
            <LoadingSpinner />
          ) : (
            <div className="flex-1 min-h-0">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                nodesConnectable={false}
                nodesDraggable
                minZoom={0.2}
                maxZoom={2}
                className="bg-bg"
              >
                <FitViewOnLoad count={nodes.length} />
                <Background color="#1e2a3f" gap={20} />
                <Controls className="!bg-surface2 !border-border" />
                <MiniMap
                  nodeColor={(n) => {
                    const role = (n.data as { role?: string }).role
                    if (role?.includes('router') || role?.includes('switch')) return '#4d9fff'
                    if (role?.includes('storage') || role?.includes('object')) return '#f59e0b'
                    if (role?.includes('metrics') || role?.includes('dashboard') || role?.includes('collector'))
                      return '#e879f9'
                    return '#00d4aa'
                  }}
                  maskColor="rgba(8,11,20,0.8)"
                  className="!bg-surface2 !border-border"
                />
              </ReactFlow>
            </div>
          )}
        </div>

        <Card title="Node Details" className="w-72 flex-shrink-0 overflow-y-auto">
          {!selectedId ? (
            <p className="text-sm text-muted">Select a node in the graph</p>
          ) : detailError ? (
            <ErrorBanner message={detailError} />
          ) : (
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-muted text-xs mb-0.5">Name</dt>
                <dd className="text-white font-medium">{shortNodeId(selectedId)}</dd>
              </div>
              <div>
                <dt className="text-muted text-xs mb-0.5">Full ID</dt>
                <dd className="text-gray-400 text-xs font-mono break-all">{selectedId}</dd>
              </div>
              <div>
                <dt className="text-muted text-xs mb-0.5">Role</dt>
                <dd className="text-gray-300 capitalize">
                  {String(nodeDetail?.role ?? '—').replace(/-/g, ' ')}
                </dd>
              </div>
              <div>
                <dt className="text-muted text-xs mb-0.5">CPU Usage</dt>
                <dd className="text-gray-300">
                  {metrics.cpu_percent != null ? `${metrics.cpu_percent.toFixed(1)}%` : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-muted text-xs mb-0.5">Memory</dt>
                <dd className="text-gray-300">
                  {metrics.memory_percent != null ? `${metrics.memory_percent.toFixed(1)}%` : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-muted text-xs mb-0.5">Temperature</dt>
                <dd className="text-gray-300">
                  {metrics.temp_c != null ? `${metrics.temp_c.toFixed(1)}°C` : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-muted text-xs mb-0.5">Power</dt>
                <dd className="text-gray-300">
                  {metrics.power_watts != null ? `${metrics.power_watts.toFixed(0)} W` : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-muted text-xs mb-0.5">Status</dt>
                <dd>
                  {state ? (
                    <span className={`badge capitalize ${stateBadgeClass(state)}`}>{state}</span>
                  ) : (
                    '—'
                  )}
                </dd>
              </div>
              {neighbors.length > 0 && (
                <div>
                  <dt className="text-muted text-xs mb-1">Connected To</dt>
                  <dd className="flex flex-wrap gap-1">
                    {neighbors.map((n) => (
                      <button
                        key={n}
                        type="button"
                        onClick={() => setSelectedId(n)}
                        className="text-[10px] px-2 py-0.5 rounded bg-surface3 text-accent border border-border hover:border-accent/40 transition"
                      >
                        {shortNodeId(n)}
                      </button>
                    ))}
                  </dd>
                </div>
              )}
            </dl>
          )}
        </Card>
      </div>
    </div>
  )
}

export default function TopologyPage() {
  return (
    <ReactFlowProvider>
      <TopologyGraph />
    </ReactFlowProvider>
  )
}
