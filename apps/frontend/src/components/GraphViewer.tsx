'use client'

import React, { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import type { TransactionGraph, GraphNode, GraphEdge } from '@/types'

interface Props {
  graph: TransactionGraph | null
}

interface SimNode extends d3.SimulationNodeDatum, GraphNode {}
interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  type: string
  weight: number
}

const NODE_COLORS: Record<string, string> = {
  user: '#6366f1',
  device: '#a855f7',
  ip: '#9ca3af',
  account: '#22c55e',
}

function nodeSymbol(type: string): d3.SymbolType {
  switch (type) {
    case 'device':
      return d3.symbolSquare
    case 'ip':
      return d3.symbolDiamond
    case 'account':
      return d3.symbolWye
    default:
      return d3.symbolCircle
  }
}

export default function GraphViewer({ graph }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!svgRef.current || !graph || graph.nodes.length === 0) return

    const width = svgRef.current.clientWidth || 500
    const height = 320

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()
    svg.attr('height', height)

    // Zoom layer
    const g = svg.append('g')
    svg.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 3])
        .on('zoom', (event: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
          g.attr('transform', event.transform.toString())
        })
    )

    const nodes: SimNode[] = graph.nodes.map((n) => ({ ...n }))
    const nodeById = new Map(nodes.map((n) => [n.id, n]))

    const links: SimLink[] = graph.edges
      .filter((e) => nodeById.has(e.source) && nodeById.has(e.target))
      .map((e) => ({ ...e, source: e.source, target: e.target }))

    const sim = d3
      .forceSimulation<SimNode>(nodes)
      .force(
        'link',
        d3
          .forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance(80)
      )
      .force('charge', d3.forceManyBody().strength(-150))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide(28))

    // Links
    const linkSel = g
      .append('g')
      .selectAll<SVGLineElement, SimLink>('line')
      .data(links)
      .enter()
      .append('line')
      .attr('stroke', '#374151')
      .attr('stroke-width', (d) => d.weight * 2)
      .attr('stroke-opacity', 0.7)

    // Link labels
    const linkLabel = g
      .append('g')
      .selectAll<SVGTextElement, SimLink>('text')
      .data(links)
      .enter()
      .append('text')
      .attr('fill', '#6b7280')
      .attr('font-size', 9)
      .attr('text-anchor', 'middle')
      .text((d) => d.type.replace(/_/g, ' '))

    // Nodes
    const nodeSel = g
      .append('g')
      .selectAll<SVGPathElement, SimNode>('path')
      .data(nodes)
      .enter()
      .append('path')
      .attr(
        'd',
        (d) =>
          d3.symbol().type(nodeSymbol(d.type)).size(d.risk_score * 600 + 200)() ?? ''
      )
      .attr('fill', (d) => NODE_COLORS[d.type] ?? '#9ca3af')
      .attr('fill-opacity', 0.85)
      .attr('stroke', (d) => (d.suspicious ? '#ef4444' : 'transparent'))
      .attr('stroke-width', 2.5)
      .style('filter', (d) =>
        d.suspicious ? 'drop-shadow(0 0 6px rgba(239,68,68,0.8))' : 'none'
      )
      .call(
        d3
          .drag<SVGPathElement, SimNode>()
          .on('start', (event, d) => {
            if (!event.active) sim.alphaTarget(0.3).restart()
            d.fx = d.x
            d.fy = d.y
          })
          .on('drag', (event, d) => {
            d.fx = event.x
            d.fy = event.y
          })
          .on('end', (event, d) => {
            if (!event.active) sim.alphaTarget(0)
            d.fx = null
            d.fy = null
          })
      )
      .on('mouseover', (event: MouseEvent, d) => {
        if (!tooltipRef.current) return
        tooltipRef.current.style.opacity = '1'
        tooltipRef.current.style.left = `${event.offsetX + 12}px`
        tooltipRef.current.style.top = `${event.offsetY - 10}px`
        tooltipRef.current.innerHTML = `
          <div class="font-semibold">${d.label}</div>
          <div class="text-gray-400">Type: ${d.type}</div>
          <div class="text-gray-400">Risk: ${(d.risk_score * 100).toFixed(0)}%</div>
          ${d.suspicious ? '<div class="text-red-400">⚠ Suspicious</div>' : ''}
        `
      })
      .on('mouseout', () => {
        if (tooltipRef.current) tooltipRef.current.style.opacity = '0'
      })

    // Node labels
    const nodeLabelSel = g
      .append('g')
      .selectAll<SVGTextElement, SimNode>('text')
      .data(nodes)
      .enter()
      .append('text')
      .attr('fill', '#e5e7eb')
      .attr('font-size', 9)
      .attr('text-anchor', 'middle')
      .attr('dy', 22)
      .text((d) => d.label.slice(0, 12))

    sim.on('tick', () => {
      linkSel
        .attr('x1', (d) => (d.source as SimNode).x ?? 0)
        .attr('y1', (d) => (d.source as SimNode).y ?? 0)
        .attr('x2', (d) => (d.target as SimNode).x ?? 0)
        .attr('y2', (d) => (d.target as SimNode).y ?? 0)

      linkLabel
        .attr(
          'x',
          (d) =>
            (((d.source as SimNode).x ?? 0) + ((d.target as SimNode).x ?? 0)) / 2
        )
        .attr(
          'y',
          (d) =>
            (((d.source as SimNode).y ?? 0) + ((d.target as SimNode).y ?? 0)) / 2
        )

      nodeSel.attr(
        'transform',
        (d) => `translate(${d.x ?? 0},${d.y ?? 0})`
      )

      nodeLabelSel
        .attr('x', (d) => d.x ?? 0)
        .attr('y', (d) => d.y ?? 0)
    })

    return () => {
      sim.stop()
    }
  }, [graph])

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 p-4">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold text-white">Entity Graph</h2>
        {/* Legend */}
        <div className="flex gap-3 text-xs text-gray-400">
          {Object.entries(NODE_COLORS).map(([type, color]) => (
            <span key={type} className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-sm" style={{ backgroundColor: color }} />
              {type}
            </span>
          ))}
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full border border-red-500" />
            suspicious
          </span>
        </div>
      </div>
      {!graph ? (
        <div className="flex items-center justify-center h-40 text-gray-500 text-sm">
          Select a transaction to view its entity graph
        </div>
      ) : (
        <div className="relative">
          <svg ref={svgRef} width="100%" className="cursor-grab active:cursor-grabbing" />
          <div
            ref={tooltipRef}
            className="absolute pointer-events-none bg-gray-900 border border-gray-600 text-xs text-white rounded px-2 py-1.5 opacity-0 transition-opacity z-10"
            style={{ transition: 'opacity 0.15s' }}
          />
        </div>
      )}
    </div>
  )
}
