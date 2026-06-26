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
import {
  layoutTopologyNodes,
  topologyEdgesToFlow,
  computeZoneBounds,
  type ZoneBounds,
} from '../utils/topologyLayout'
import TopologyNode, { type TopologyFlowNode } from '../components/TopologyNode'
import type { NodeTelemetryDetail } from '../api/telemetry'
import type { Edge } from '@xyflow/react'

const nodeTypes = { topology: TopologyNode }

// ── Fit view on initial load ──────────────────────────────────────────────────
function FitViewOnLoad({ count }: { count: number }) {
  const { fitView } = useReactFlow()
  useEffect(() => {
    if (count === 0) return
    const timer = setTimeout(() => {
      fitView({ padding: 0.06, duration: 350, maxZoom: 1.4 })
    }, 80)
    return () => clearTimeout(timer)
  }, [count, fitView])
  return null
}

// ── Zone background overlay ───────────────────────────────────────────────────
// Rendered as absolutely-positioned divs BEHIND the ReactFlow canvas using
// the RF coordinate system transformed by the current viewport.
// These are purely decorative; pointer-events: none so they never interfere.
function ZoneOverlays({
  zones,
  transform,
}: {
  zones: ZoneBounds[]
  transform: { x: number; y: number; zoom: number }
}) {
  return (
    <>
      {zones.map((zone) => {
        const left = zone.x * transform.zoom + transform.x
        const top  = zone.y * transform.zoom + transform.y
        const w    = zone.width  * transform.zoom
        const h    = zone.height * transform.zoom

        return (
          <div
            key={zone.prefix}
            style={{
              position: 'absolute',
              left,
              top,
              width: w,
              height: h,
              border: `1.5px solid ${zone.theme.border}`,
              borderRadius: 12 * transform.zoom,
              background: zone.theme.bg,
              pointerEvents: 'none',
              zIndex: 0,
              boxSizing: 'border-box',
            }}
          >
            {/* Zone label header */}
            <div
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                display: 'flex',
                alignItems: 'center',
                gap: 6 * transform.zoom,
                padding: `${6 * transform.zoom}px ${10 * transform.zoom}px`,
                borderBottom: `1px solid ${zone.theme.border}`,
                background: `linear-gradient(90deg, ${zone.theme.bg} 0%, transparent 100%)`,
              }}
            >
              {/* Accent dot */}
              <span
                style={{
                  display: 'inline-block',
                  width: 7 * transform.zoom,
                  height: 7 * transform.zoom,
                  borderRadius: '50%',
                  background: zone.theme.header,
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  fontSize: Math.max(9, 11 * transform.zoom),
                  fontWeight: 700,
                  color: zone.theme.header,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  fontFamily: 'ui-monospace, monospace',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {zone.label}
              </span>
              <span
                style={{
                  fontSize: Math.max(8, 9 * transform.zoom),
                  color: zone.theme.header,
                  opacity: 0.5,
                  fontFamily: 'ui-monospace, monospace',
                  marginLeft: 'auto',
                  whiteSpace: 'nowrap',
                }}
              >
                {zone.prefix}
              </span>
            </div>
          </div>
        )
      })}
    </>
  )
}

// ── Inner graph (needs ReactFlowProvider context) ─────────────────────────────
function TopologyGraph() {
  const { data: topology, loading, error } = useFetch(getTopology, [])
  const [nodes, setNodes, onNodesChange] = useNodesState<TopologyFlowNode>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [localSearch, setLocalSearch]   = useState('')
  const [selectedId, setSelectedId]     = useState<string | null>(null)
  const [nodeDetail, setNodeDetail]     = useState<Record<string, unknown> | null>(null)
  const [nodeTelemetry, setNodeTelemetry] = useState<NodeTelemetryDetail | null>(null)
  const [detailError, setDetailError]   = useState<string | null>(null)
  const [viewport, setViewport]         = useState({ x: 0, y: 0, zoom: 1 })
  const [zoneBounds, setZoneBounds]     = useState<ZoneBounds[]>([])

  // ── Filter ──────────────────────────────────────────────────────────────────
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
    return topology.edges.filter(
      (e) => nodeIds.has(e.source) && nodeIds.has(e.target),
    )
  }, [topology, filteredNodes])

  // ── Layout ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!topology) return
    setNodes(layoutTopologyNodes(filteredNodes, topology.edges))
    setEdges(
      topologyEdgesToFlow(displayEdges).map((e) => ({
        ...e,
        markerEnd: { type: MarkerType.ArrowClosed, color: e.markerEnd.color },
      })),
    )
    setZoneBounds(computeZoneBounds(filteredNodes))
  }, [topology, filteredNodes, displayEdges, setNodes, setEdges])

  // ── Node detail polling ─────────────────────────────────────────────────────
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
      setDetailError(
        e instanceof Error ? e.message : 'Failed to load node details',
      )
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

  // ── Derived detail values ───────────────────────────────────────────────────
  const metrics   = (nodeTelemetry?.metrics ?? {}) as Record<string, number>
  const state     = (nodeTelemetry?.state ?? nodeDetail?.state) as string | undefined
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
        {/* ── Graph panel ──────────────────────────────────────────────────── */}
        <div className="flex-1 card overflow-hidden flex flex-col">
          {/* Search bar */}
          <div className="px-4 py-2 border-b border-border flex items-center gap-3">
            <input
              type="search"
              value={localSearch}
              onChange={(e) => setLocalSearch(e.target.value)}
              placeholder="Filter nodes by name or role…"
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
            <div className="flex-1 min-h-0" style={{ position: 'relative' }}>
              {/* Zone overlays rendered behind ReactFlow */}
              <ZoneOverlays zones={zoneBounds} transform={viewport} />

              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onNodeClick={onNodeClick}
                onMove={(_event, vp) => setViewport(vp)}
                nodesConnectable={false}
                nodesDraggable
                minZoom={0.2}
                maxZoom={2}
                className="bg-bg"
                style={{ background: 'transparent' }}
              >
                <FitViewOnLoad count={nodes.length} />
                <Background color="#1a2236" gap={24} size={1} />
                <Controls className="!bg-surface2 !border-border" />
                <MiniMap
                  nodeColor={(n) => {
                    const role = (n.data as { role?: string }).role ?? ''
                    if (role.includes('router') || role.includes('switch')) return '#a78bfa'
                    if (role.includes('storage') || role.includes('object'))  return '#f59e0b'
                    if (role.includes('metrics') || role.includes('dashboard') || role.includes('collector'))
                      return '#e879f9'
                    return '#00d4aa'
                  }}
                  maskColor="rgba(8,11,20,0.82)"
                  className="!bg-surface2 !border-border"
                />
              </ReactFlow>
            </div>
          )}
        </div>

        {/* ── Detail panel ─────────────────────────────────────────────────── */}
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
                  {metrics.cpu_percent != null
                    ? `${metrics.cpu_percent.toFixed(1)}%`
                    : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-muted text-xs mb-0.5">Memory</dt>
                <dd className="text-gray-300">
                  {metrics.memory_percent != null
                    ? `${metrics.memory_percent.toFixed(1)}%`
                    : '—'}
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
                  {metrics.power_watts != null
                    ? `${metrics.power_watts.toFixed(0)} W`
                    : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-muted text-xs mb-0.5">Status</dt>
                <dd>
                  {state ? (
                    <span className={`badge capitalize ${stateBadgeClass(state)}`}>
                      {state}
                    </span>
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

// ── Page export ───────────────────────────────────────────────────────────────
export default function TopologyPage() {
  return (
    <ReactFlowProvider>
      <TopologyGraph />
    </ReactFlowProvider>
  )
}