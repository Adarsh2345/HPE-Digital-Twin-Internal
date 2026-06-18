import { memo } from 'react'
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import { stateBadgeClass } from '../utils/format'

export interface TopologyNodeData extends Record<string, unknown> {
  label: string
  fullId: string
  role: string
  droplet: string
  state: string
}

export type TopologyFlowNode = Node<TopologyNodeData, 'topology'>

const ROLE_COLORS: Record<string, { border: string; glow: string; bg: string }> = {
  'spine-switch': { border: '#a78bfa', glow: 'rgba(167,139,250,0.35)', bg: '#1a1530' },
  'storage-tor': { border: '#a78bfa', glow: 'rgba(167,139,250,0.35)', bg: '#1a1530' },
  'tor-router': { border: '#4d9fff', glow: 'rgba(77,159,255,0.35)', bg: '#0f1a2e' },
  'compute-node': { border: '#00d4aa', glow: 'rgba(0,212,170,0.3)', bg: '#0d1f1a' },
  'storage-controller': { border: '#f59e0b', glow: 'rgba(245,158,11,0.3)', bg: '#1f1a0d' },
  'object-storage': { border: '#f59e0b', glow: 'rgba(245,158,11,0.25)', bg: '#1a150d' },
  'metrics-collector': { border: '#e879f9', glow: 'rgba(232,121,249,0.3)', bg: '#1f0f22' },
  'metrics-dashboard': { border: '#e879f9', glow: 'rgba(232,121,249,0.3)', bg: '#1f0f22' },
  'infrastructure-docs': { border: '#94a3b8', glow: 'rgba(148,163,184,0.25)', bg: '#151820' },
  'graph-database': { border: '#94a3b8', glow: 'rgba(148,163,184,0.25)', bg: '#151820' },
  middleware: { border: '#94a3b8', glow: 'rgba(148,163,184,0.25)', bg: '#151820' },
  'metrics-exporter': { border: '#64748b', glow: 'rgba(100,116,139,0.2)', bg: '#111620' },
  'container-metrics': { border: '#64748b', glow: 'rgba(100,116,139,0.2)', bg: '#111620' },
}

function roleStyle(role: string) {
  return ROLE_COLORS[role] ?? { border: '#00d4aa', glow: 'rgba(0,212,170,0.2)', bg: '#111827' }
}

function TopologyNodeComponent({ data, selected }: NodeProps<TopologyFlowNode>) {
  const nodeData = data
  const colors = roleStyle(nodeData.role)
  const isCritical = nodeData.state === 'critical' || nodeData.state === 'warning'
  const borderColor = isCritical ? '#f87171' : colors.border

  return (
    <div
      className="relative flex flex-col items-center"
      style={{ width: 100 }}
    >
      <Handle type="target" position={Position.Top} className="!bg-border !w-2 !h-2 !border-0" />
      <div
        className="rounded-lg px-2 py-2 text-center transition-shadow"
        style={{
          background: colors.bg,
          border: `2px solid ${borderColor}`,
          boxShadow: selected
            ? `0 0 16px ${colors.glow}`
            : `0 0 8px ${isCritical ? 'rgba(248,113,113,0.3)' : colors.glow}`,
          minWidth: 88,
        }}
      >
        <div className="text-[11px] font-semibold text-white leading-tight break-words">
          {nodeData.label}
        </div>
        <div className="text-[9px] text-muted mt-0.5 leading-tight">
          {nodeData.role.replace(/-/g, ' ')}
        </div>
      </div>
      <span
        className={`badge text-[8px] mt-1 capitalize ${stateBadgeClass(nodeData.state)}`}
      >
        {nodeData.state}
      </span>
      <Handle type="source" position={Position.Bottom} className="!bg-border !w-2 !h-2 !border-0" />
    </div>
  )
}

export default memo(TopologyNodeComponent)
